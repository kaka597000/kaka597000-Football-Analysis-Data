"""Offline mixed-revision import check; no hydration, network or real state writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

BASE = '6639867d502a2dfe53a9a235c8761f8ee6b91533'
OVERLAY = (
    'runtime/automation/prospective_cycle.py',
    'runtime/automation/market_bridge.py',
    'runtime/automation/result_queue.py',
    'runtime/research_program/promotion_review.py',
    'runtime/v2_test/evaluation.py',
    'runtime/research_program/future_identity.py',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(repo, data, base=BASE):
    domestic_path = data/'future/bundle-v2/manifest.json'
    ucl_path = data/'future/ucl-bundle-v2/manifest.json'
    domestic = json.loads(domestic_path.read_text())
    ucl = json.loads(ucl_path.read_text())
    locks = dict(domestic['protocol']['source_files_sha256'])
    for path, expected in ucl['protocol']['files_sha256'].items():
        if '/Football-Analysis/runtime/' in path:
            if path in locks and locks[path] != expected:
                raise ValueError('protocol source lock conflict')
            locks[path] = expected
    locks['/workspace/Football-Analysis/runtime/research_program/ucl_refresh_review.py'] = ucl['review_source_sha256']
    locks = {'runtime/'+path.split('/runtime/', 1)[1]: expected for path, expected in locks.items()}
    if set(OVERLAY).intersection(locks):
        raise ValueError('overlay would replace source-locked code')
    with tempfile.TemporaryDirectory(prefix='wcpp-overlay-smoke-') as folder:
        root = Path(folder)
        archive = root/'base.tar'
        subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar',
                        '--output='+str(archive), base], check=True)
        checkout = root/'code'; checkout.mkdir()
        with tarfile.open(archive) as handle:
            handle.extractall(checkout, filter='data')
        before = {name: sha(checkout/name) for name in locks}
        if before != locks:
            raise ValueError('base sources differ from locked protocols')
        overlay = {}
        for name in OVERLAY:
            destination = checkout/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo/name, destination)
            overlay[name] = sha(destination)
        after = {name: sha(checkout/name) for name in locks}
        if after != before:
            raise ValueError('overlay changed locked sources')
        probe = """import json
from pathlib import Path
import runtime.automation.prospective_cycle as cycle
import runtime.research_program.future_identity as identity
base=Path.cwd().resolve()
files={name:str(Path(module.__file__).resolve().relative_to(base))
       for name,module in [('prospective_cycle',cycle),('future_identity',identity)]}
assert callable(cycle.cycle) and callable(identity.validate_plan_packages)
print(json.dumps({'imports':'PASS','files':files},sort_keys=True))
"""
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
        imported = subprocess.run([sys.executable, '-c', probe], cwd=checkout,
                                  env=env, check=True, capture_output=True, text=True)
        return {
            'schema': 'WCPP-OFFLINE-OVERLAY-COMPATIBILITY-1',
            'base_commit': base,
            'overlay_files_sha256': overlay,
            'protocol_manifest_files_sha256': {
                str(domestic_path.relative_to(data)):sha(domestic_path),
                str(ucl_path.relative_to(data)):sha(ucl_path)},
            'locked_sources_before_sha256': before,
            'locked_sources_after_sha256': after,
            'locked_sources_unchanged': before == after == locks,
            'import_probe': json.loads(imported.stdout),
            'network_requests': 0,
            'hydration_performed': False,
            'real_state_writes': False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.repo.resolve(), args.data.resolve())
    with args.out.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'status':'PASS', 'locked_sources':len(result['locked_sources_before_sha256']),
                      'overlay_files':len(result['overlay_files_sha256']),
                      'imports':result['import_probe']['imports']}))


if __name__ == '__main__':
    main()
