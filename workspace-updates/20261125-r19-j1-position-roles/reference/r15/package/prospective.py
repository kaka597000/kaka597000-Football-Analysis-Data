"""Package, verify or independently recalculate an already-issued R15 prematch slate."""
import argparse
from functools import partial
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True

from common import (ARCHIVES, PROTOCOL, PROTOCOL_SHA, REGISTRATION, SOURCE_COMMIT, digest, encode,
                    member, read, replay_environment, require, safe_name, sha, tar_gz, unpack, utc, valid_sha)
from intake import open_raw
from prospective_records import (CODE, DISPLAY_DIR, FIRSTS, TRACK, audit_batch, batch, checked_archive,
                                 collect_display, file_reader, freeze_hash, originals, scope)
from starters import rebuild_rows
from verify import SCHEMA, check_blas, dependencies, source_pin

FORMAT = 'r15-j1-prospective-firsts-v1'
HERE = Path(__file__).resolve().parent
COMPANION = Path('workspace-updates/20261125-r15-j1-lineups-forward/first-issues.tar.gz')
ISSUE_FILE = re.compile(r'[0-9a-f]{16}-v000001\.json')


def study_identity(pkg, data):
    m = read(pkg/'manifest.json')
    require(m['schema'] == SCHEMA and m['source_commit'] == m['source']['commit'] == SOURCE_COMMIT
            and m['source']['registration'] == REGISTRATION and m['source']['protocol_sha256'] == PROTOCOL_SHA
            and m['dependencies'] == dependencies(), 'retrospective study source or baseline pins')
    study = pkg/'replay'
    hashes = {n: sha(study/n) for n in ('inputs.json','fit.json','forward.json')}
    require(all(m['files']['replay/'+k] == v for k,v in hashes.items()), 'signed training recipe file hashes')
    inputs, recipe = read(study/'inputs.json'), read(study/'forward.json')
    require(inputs['protocol_sha256'] == PROTOCOL_SHA and inputs['formal_kpi_eligible'] is False
            and recipe['study_inputs_sha256'] == hashes['inputs.json'] and recipe['fit_sha256'] == hashes['fit.json']
            and recipe['games'] == 2822 and recipe['competition'] == CODE and all(recipe.get(k) == v for k,v in inputs.items())
            and m['rosters_sha256'] == inputs['rosters_sha256'], 'full-calendar R15 recipe and roster snapshot')
    with tarfile.open(checked_archive(data, 'r10', ARCHIVES['r10'][1])) as tar:
        shot_hash = digest(member(tar, 'main/jpn.1/forward.json'))
    identity = {k: inputs[k] for k in ('version','protocol_sha256','panel_sha256','rosters_sha256','roster_coverage',
                                      'roster_manifest_sha256','roster_snapshot_at')}
    identity.update(study_inputs_sha256=hashes['inputs.json'], fit_sha256=hashes['fit.json'],
                    recipe_sha256={CODE: hashes['forward.json']}, r7_forward_sha256=inputs['baseline_sha256'],
                    r10_recipe_sha256=shot_hash, archive_manifest_sha256={k: a[3] for k,a in ARCHIVES.items()})
    return m, identity


def signed_files(get, canonical=None, binding=None, expected=None, index_hash=None):
    """Take one copy per actual v1 record. Check against the independently held store when supplied."""
    files = {}
    def remember(name):
        require(name == 'receipts.json' or ISSUE_FILE.fullmatch(name), ('research receipt path', name))
        files[name] = get(name)
        return files[name]
    plan, matches = batch(remember, TRACK, expected)
    require(len(matches) == len(plan['payload']['fixtures']) == 10, 'complete independent ten-fixture R15 issue required')
    if index_hash is not None:
        require(valid_sha(index_hash) and digest(files['receipts.json']) == index_hash, 'independent firsts index checksum')
    scope_bytes = encode(scope(plan))
    if canonical is not None:
        original = file_reader(canonical, '.'+TRACK+'-registration.json')
        require(json.loads(original) == scope(plan), 'canonical research registration binding')
        if binding is not None:
            require(binding == original, 'packaged registration binding differs from the independent store')
        scope_bytes = original
        for r in (plan, *matches.values()):
            path = freeze_hash(scope(r)) + '/000001.json'
            require(file_reader(canonical, path) == files[r['freeze_id']+'.json'], ('canonical first bytes', r['match_id']))
    else:
        require(valid_sha(index_hash) and binding is not None and json.loads(binding) == scope(plan),
                'external firsts index fingerprint and original binding required')
        scope_bytes = binding
    return plan, matches, {'firsts/'+k: v for k,v in files.items()} | {'canonical-registration.json': scope_bytes}


def plan_evidence(pkg, data, display_dir, get, canonical=None, binding=None, expected=None, index_hash=None, issue_dir=None):
    plan, records, files = signed_files(get, canonical, binding, expected, index_hash)
    study_hash = sha(pkg/'manifest.json')
    m, study = study_identity(pkg, data)
    sources, observations = originals(data)
    display_files, display, recommendations = collect_display(partial(file_reader, display_dir), sources['r10'][0],
                                                              utc(plan['payload']['identity']['inputs_cutoff_at']))
    audit = audit_batch(plan, records, sources, observations, display, recommendations, study)
    for row in audit['slots']:
        if row['status'] != 'started':
            continue
        key = freeze_hash(dict(track=TRACK, stage='prematch', match_id=row['match_id']))
        if canonical is not None:
            require(not os.path.lexists(canonical/key/'000001.json'),
                    ('excluded fixture has a canonical R15 research first', row['match_id']))
        if issue_dir is not None:
            require(not os.path.lexists(issue_dir/(key[:16]+'-v000001.json')), ('excluded fixture in local R15 issues', row['match_id']))
    audit['receipts_sha256'] = digest(files['firsts/receipts.json'])
    files.update({'display/'+k: v for k,v in display_files.items()})
    files['audit.json'] = encode(audit)
    require(sha(pkg/'manifest.json') == study_hash, 'training manifest changed during prospective audit')
    manifest = dict(schema=FORMAT, source_commit=SOURCE_COMMIT, study_manifest_sha256=study_hash,
                    registration_sha256=plan['record_sha256'], receipts_sha256=audit['receipts_sha256'],
                    source_registrations={k:v[2] for k,v in FIRSTS.items()},
                    files={k:digest(v) for k,v in sorted(files.items())})
    files['manifest.json'] = encode(manifest)
    return files, audit, m


def archive_parts(path):
    """Only prematch receipt, first-display and audit files are valid members."""
    files = {}
    display_name = re.compile(r'display/(?:registration/(?:plan\.json|[0-9a-f]{16}-v000001\.json)|'
                              r'(?:nov25|nov28_29)/(?:entries\.json|message\.txt|publication\.json|[0-9a-f]{16}-v000001\.json))')
    with tarfile.open(path, 'r|*') as tar:
        for entry in tar:
            name = safe_name(entry.name)
            require(name not in files and entry.isfile() and (
                name in ('manifest.json', 'audit.json', 'canonical-registration.json','firsts/receipts.json')
                or name.startswith('firsts/') and ISSUE_FILE.fullmatch(name[7:])
                or display_name.fullmatch(name)), ('unexpected prospective archive member', name))
            files[name] = tar.extractfile(entry).read()
    return files


def pack(args):
    pkg, data, display = locations(args)
    return pack_firsts(pkg, data, display, args.issues, args.freeze_root, args.out)


def pack_firsts(pkg, data, display, issues, freeze_root, out):
    target = out.absolute()
    updates = data/'workspace-updates'
    protected = [pkg, display, updates/DISPLAY_DIR, issues, freeze_root, *(updates/v[0] for v in ARCHIVES.values())]
    require(not target.is_symlink() and not any(target.resolve().is_relative_to(p.resolve()) for p in protected),
            'choose a companion archive outside the source, official publications, first store and study package')
    files, audit, _ = plan_evidence(pkg, data, display, partial(file_reader, issues), freeze_root, issue_dir=issues)
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as tmp:
        staged = Path(tmp)/'firsts.tar.gz'
        tar_gz(staged, files)
        bundle_hash = sha(staged)
        try:
            os.link(staged, target)
        except FileExistsError:
            require(not target.is_symlink() and target.is_file() and sha(target) == bundle_hash,
                    ('different existing prospective archive', str(target)))
    return report('pack', bundle_hash, audit)


def compare_prepared(plan, records, prepared):
    fixtures, payloads, identity = prepared
    require(set(payloads) == set(records) == set(fixtures), 'recalculated fixture population')
    for mid, payload in payloads.items():
        signed = dict(records[mid]['payload'])
        require(signed.pop('registration_sha256') == plan['record_sha256']
                and freeze_hash(payload) == freeze_hash(signed) == plan['payload']['identity']['payload_sha256'][mid],
                ('recalculated payload differs from its issued hash', mid))
    body = dict(track=TRACK, fixtures=fixtures, identity=identity)
    require(freeze_hash(body) == freeze_hash(plan['payload']), 'recalculated registration, seats or model provenance')


def prepare_at_issue(prepare, folders, study, training, protocol, display, plan, records, tmp):
    # Give the model only the original clock. Its rankings, scores and probabilities must come from independent inputs.
    clock = dict(track=plan['track'], recorded_at=plan['recorded_at'],
                 payload=dict(identity=dict(inputs_cutoff_at=plan['payload']['identity']['inputs_cutoff_at'])))
    prepared = prepare(folders, study, training, protocol, display, clock, tmp)
    compare_prepared(plan, records, prepared)


def replay_worker():
    from research_program import lineup_forward
    p = json.load(sys.stdin)
    run = Path(p['tmp'])
    plan, records = batch(partial(file_reader, run/'firsts'), TRACK, p['registration_sha256'])
    prepare_at_issue(lineup_forward._prepare, {k:Path(v) for k,v in p['folders'].items()},
                     Path(p['study']), Path(p['rosters']), Path(p['protocol']), run/'display', plan, records, run/'model')


def recalculate(pkg, data, source, m, files, registration):
    require(source_pin(source, SOURCE_COMMIT) == m['source'], 'pinned forward source tree')
    with TemporaryDirectory(prefix='r15-forward-verify-') as folder:
        tmp = Path(folder)
        for name, body in files.items():
            if name.startswith(('firsts/','display/')):
                path = tmp/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
        # Only prospective recipes, compressed originals and the historical input snapshot enter this path.
        raw_files = {p.relative_to(pkg).as_posix() for p in (pkg/'raw').iterdir()}
        require(raw_files == {n for n in m['files'] if n.startswith('raw/')}, 'roster original chunk inventory')
        for name in ('intake.tar.gz','extract_v1.py',*sorted(raw_files)):
            require(sha(pkg/name) == m['files'][name], ('verified roster input', name))
        meta = tmp/'intake'
        unpack(pkg/'intake.tar.gz', meta)
        raw, _ = open_raw(pkg, meta, tmp)
        training = rebuild_rows(meta, raw, read(pkg/'replay/inputs.json'), pkg/'extract_v1.py')
        archive = tmp/'source.tar'
        with archive.open('xb') as stream:
            subprocess.run(['git','-C',str(source),'archive',SOURCE_COMMIT,'runtime',PROTOCOL,'configs/analysis-scope.json'],
                           stdout=stream, check=True)
        code = tmp/'source'
        with tarfile.open(archive) as tar:
            tar.extractall(code, filter='data')
        env = replay_environment(os.pathsep.join((str(HERE), str(code/'runtime'))), tmp)
        check_blas(env, tmp)
        (tmp/'model').mkdir()
        config = dict(study=str(pkg/'replay'), tmp=str(tmp), rosters=str(training), protocol=str(code/PROTOCOL),
                      registration_sha256=registration, folders={k:str(data/'workspace-updates'/v[0]) for k,v in ARCHIVES.items()})
        subprocess.run([sys.executable,'-B','-c','from prospective import replay_worker\nreplay_worker()'],
                       env=env, cwd=tmp, input=encode(config), check=True)


def locations(args):
    pkg = args.study_package.resolve()
    data = (args.data_root or pkg.parents[1]).resolve()
    display = (args.display_windows or data/'workspace-updates'/DISPLAY_DIR).resolve()
    return pkg, data, display


def report(mode, checksum, audit):
    return dict(mode=mode, bundle_sha256=checksum, source_commit=SOURCE_COMMIT,
                **{k:audit[k] for k in ('registration_sha256','receipts_sha256','registered','started','issued','market_coverage')})


def verify_bundle(args):
    pkg, data, display = locations(args)
    bundle_hash = sha(args.bundle)
    files = archive_parts(args.bundle)
    expected, audit, m = plan_evidence(pkg, data, display, lambda n: files['firsts/'+n], args.freeze_root,
                                       files['canonical-registration.json'], args.registration_sha256, args.receipts_sha256)
    require(files == expected, 'prospective archive inventory, original bytes, study binding or audit differs')
    if args.command == 'recalc':
        recalculate(pkg, data, args.source.resolve(), m, expected, audit['registration_sha256'])
    require(sha(args.bundle) == bundle_hash, 'prospective archive changed during verification')
    return report(args.command, bundle_hash, audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('pack','verify','recalc'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--study-package', type=Path, required=True, help='verified R15 historical evidence package')
        cmd.add_argument('--data-root', type=Path, help='data checkout containing R5, R7, R10 and display windows')
        cmd.add_argument('--display-windows', type=Path, help='original J1 first-display archive')
        if name == 'pack':
            cmd.add_argument('--issues', type=Path, required=True, help='already-issued R15 directory with receipts.json')
            cmd.add_argument('--freeze-root', type=Path, required=True, help='independent original first-issue store')
            cmd.add_argument('--out', type=Path, required=True, help='new standalone .tar.gz companion')
        else:
            cmd.add_argument('--bundle', type=Path, required=True)
            anchor = cmd.add_mutually_exclusive_group(required=True)
            anchor.add_argument('--freeze-root', type=Path, help='compare every original freeze byte to the live first store')
            anchor.add_argument('--receipts-sha256', help='independently retained SHA-256 of the original issued receipts.json')
            cmd.add_argument('--registration-sha256', help='also check an independently retained registration record SHA')
            if name == 'recalc':
                cmd.add_argument('--source', type=Path, required=True, help='Git checkout containing the pinned R15 source')
    args = parser.parse_args()
    print(json.dumps(pack(args) if args.command == 'pack' else verify_bundle(args), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
