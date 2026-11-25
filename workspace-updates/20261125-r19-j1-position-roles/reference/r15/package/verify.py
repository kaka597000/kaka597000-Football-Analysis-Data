"""Offline R15 light verification and duplicate full retraining from original responses."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True

from baselines import read_baselines
from common import (ARCHIVES, NUMERICAL_ENV, OUTPUTS, PROTOCOL, PROTOCOL_SHA, REGISTRATION, SOURCE_COMMIT, WORKFLOW,
                    digest, inventory, read, replay_environment, require, rows, sha, unpack)
from intake import open_raw
from data_readme import render
from replay import derive
from starters import normalize

HERE = Path(__file__).resolve().parent
SCHEMA = 'r15-j1-lineup-evidence-v1'


def git(source, *args):
    return subprocess.check_output(['git','-C',str(source),*args])


def source_pin(source, commit):
    require(isinstance(commit,str) and re.fullmatch('[0-9a-f]{40}',commit), 'a complete source commit SHA is required')
    require(commit == SOURCE_COMMIT, ('final R15 source revision', SOURCE_COMMIT, commit))
    require(git(source,'rev-parse','--verify',commit+'^{commit}').decode().strip()==commit, 'source commit object')
    require(digest(git(source,'show',commit+':'+PROTOCOL))==PROTOCOL_SHA, 'registered protocol bytes at source pin')
    modules = ('lineup_study', 'lineup_history', 'territory_hurdle', 'paired_kpi_inference')
    return dict(repository='kaka597000/Football-Analysis', commit=commit, registration=REGISTRATION,
                protocol_sha256=PROTOCOL_SHA, runtime_tree=git(source,'rev-parse',commit+':runtime').decode().strip(),
                module_sha256={name: digest(git(source,'show',f'{commit}:runtime/research_program/{name}.py'))
                               for name in modules},
                requirements_sha256=digest(git(source,'show',commit+':requirements.txt')))


def dependencies():
    return {k:dict(directory='workspace-updates/'+v[0],archive=v[1],archive_sha256=v[2],manifest_sha256=v[3])
            for k,v in ARCHIVES.items()}


def reconstruct(pkg, data_root, tmp):
    study = pkg/'replay'
    require({p.name for p in study.iterdir()}==set(OUTPUTS), 'replay file inventory')
    inputs = read(study/'inputs.json')
    require(inputs['protocol_sha256']==PROTOCOL_SHA, 'replay protocol checksum')
    games, originals = read_baselines(data_root,inputs)
    meta = tmp/'intake'
    unpack(pkg/'intake.tar.gz',meta)
    raw, capture = open_raw(pkg,meta,tmp)
    training,slots = normalize(meta,raw,capture,games,inputs,pkg/'extract_v1.py')
    tables = derive(study,games,originals,slots)
    counts = dict(fixture_slots=len(slots), training_rows=inputs['roster_rows'], original_bodies=len(capture),
                  capture_receipts=sum(map(len,capture.values())), folds={})
    for s in slots:
        f = counts['folds'].setdefault(s['fold'],dict(fixtures=0,missing_event=0,both_complete=0))
        f['fixtures'] += 1
        f['missing_event'] += s['source']['source_rows']==0
        f['both_complete'] += all(s['source'][k]['status']=='complete' for k in ('home','away'))
    tables['README.md'] = render(tables, slots, counts, inputs)
    return training,slots,tables,counts


def compare_values(reference, reproduced, key):
    if type(reference) is float and type(reproduced) is float:
        require(math.isfinite(reference) and math.isclose(reference,reproduced,rel_tol=1e-7,abs_tol=1e-9),
                ('retrained float',key,reference,reproduced))
    elif type(reference) is dict and type(reproduced) is dict:
        require(reference.keys()==reproduced.keys(), ('retrained fields',key))
        for k,v in reference.items():
            compare_values(v,reproduced[k],key+'/'+k)
    elif type(reference) is list and type(reproduced) is list:
        require(len(reference)==len(reproduced), ('retrained length',key))
        for i,(a,b) in enumerate(zip(reference,reproduced)):
            compare_values(a,b,key+'/'+str(i))
    else:
        require(type(reference) is type(reproduced) and reference==reproduced, ('retrained value',key,reference,reproduced))


def check_blas(env, cwd):
    # Probe the actual CPU dispatch and BLAS libraries with the numerical worker's environment.
    probe = (
        'import json, platform\n'
        'from numpy._core._multiarray_umath import __cpu_features__\n'
        'import scipy.linalg.blas\n'
        'from threadpoolctl import threadpool_info\n'
        'print(json.dumps([platform.machine(), threadpool_info(), __cpu_features__.get("AVX512F")]))'
    )
    result = subprocess.check_output([sys.executable, '-B', '-c', probe], cwd=cwd, env=env)
    machine, pools, avx512f = json.loads(result)
    libraries = [pool for pool in pools if pool['user_api'] == 'blas']
    print(json.dumps(dict(machine=machine, blas=libraries)), flush=True)
    require(env.get('NPY_DISABLE_CPU_FEATURES') == NUMERICAL_ENV['NPY_DISABLE_CPU_FEATURES'] and avx512f is False,
            'refit requires NPY_DISABLE_CPU_FEATURES=AVX512F and disabled AVX512F in NumPy')
    require(machine.lower() in ('x86_64', 'amd64') and libraries and all(
        pool['internal_api'] == 'openblas' and pool['architecture'] == 'Haswell' and pool['num_threads'] == 1
        for pool in libraries), 'refit requires single-thread x86-64 Haswell OpenBLAS for NumPy and SciPy')


def repeat(pkg, data_root, source, pin, training, tmp):
    require(source_pin(source,pin['commit'])==pin, 'source receipt')
    # Export the pinned Git objects. Uncommitted files in a shared checkout cannot enter either run.
    archive = tmp/'source.tar'
    with archive.open('xb') as stream:
        subprocess.run(['git','-C',str(source),'archive',pin['commit'],'runtime',PROTOCOL,'requirements.txt'],
                       stdout=stream,check=True)
    code = tmp/'source'
    with tarfile.open(archive) as tar:
        tar.extractall(code,filter='data')
    env = replay_environment(str(code/'runtime'), tmp)
    check_blas(env, tmp)
    args = [sys.executable,'-B','-m','research_program.lineup_study']
    for label,base in ARCHIVES.items():
        args.extend(['--'+label,str(data_root/'workspace-updates'/base[0])])
    args.extend(['--rosters',str(training)])
    first,second = tmp/'run-1',tmp/'run-2'
    for folder in (first,second):
        subprocess.run([*args,'--out',str(folder)],cwd=tmp,env=env,check=True)
    first_hashes = inventory(first)
    require(first_hashes==inventory(second) and set(first_hashes)==set(OUTPUTS), 'two fresh trainings differ in bytes')
    for name in OUTPUTS:
        path, other = pkg/'replay'/name, first/name
        if sha(path)==sha(other):
            continue
        a,b = (rows(p) if name.endswith('.gz') else read(p) for p in (path,other))
        if name=='forward.json':
            for obj,folder in [(a,pkg/'replay'),(b,first)]:
                require(obj.pop('fit_sha256')==sha(folder/'fit.json'), 'forward references its own fit')
        compare_values(a,b,name)


def verify(pkg, data_root, source=None, full=False):
    pkg, data_root = pkg.resolve(),data_root.resolve()
    manifest = read(pkg/'manifest.json')
    require(manifest['schema']==SCHEMA and manifest['dependencies']==dependencies(), 'R15 bundle version or dependencies')
    require(inventory(pkg,('manifest.json',))==manifest['files'], 'R15 file inventory or checksum')
    require(sha(pkg.parents[1]/'.github/workflows'/WORKFLOW)==manifest['workflow_sha256'], 'data CI workflow checksum')
    pin = manifest['source']
    require(pin['commit']==manifest['source_commit']==SOURCE_COMMIT and re.fullmatch('[0-9a-f]{40}',pin['commit'])
            and pin['registration']==REGISTRATION and pin['protocol_sha256']==PROTOCOL_SHA, 'registered source pin')
    if source:
        require(source_pin(source,pin['commit'])==pin, 'source tree or dependencies differ')
    with TemporaryDirectory(prefix='r15-verify-') as d:
        tmp = Path(d)
        training, slots, tables, counts = reconstruct(pkg,data_root,tmp)
        require(counts==manifest['counts'] and sha(training)==manifest['rosters_sha256'], 'reconstructed counts or input digest')
        require(rows(pkg/'normalized-starters.jsonl.gz')==slots, 'direct raw-derived starters or missing slots')
        for name,body in tables.items():
            require((pkg/name).read_bytes()==body, ('recounted table',name))
        if full:
            require(source is not None,'--full requires --source pointing to the source Git repository')
            repeat(pkg,data_root,source,pin,training,tmp)
    return dict(mode='full' if full else 'light',source=pin['commit'],**counts)


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,default=HERE)
    p.add_argument('--data-root',type=Path)
    p.add_argument('--source',type=Path)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--light',action='store_true')
    mode.add_argument('--full',action='store_true')
    a = p.parse_args()
    print(json.dumps(verify(a.package,a.data_root or a.package.resolve().parents[1],a.source,a.full),sort_keys=True))
