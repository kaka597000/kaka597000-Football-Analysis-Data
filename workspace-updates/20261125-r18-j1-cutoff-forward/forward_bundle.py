"""Package and recalculate already issued R18 firsts in an isolated offline checkout."""

import argparse
from datetime import timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

from bundle_io import archive, checked_file, digest, encoded, file_sha, first_files, install, members, require, write
import evidence_slice as slice_

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / 'source-commit.txt').read_text().strip()
FORMAT = 'r18-j1-cutoff-forward-v1'
TAR = 'firsts-and-evidence.tar.gz'
R15_MANIFEST = '97a3cdc153035f4c1bea4f292cbb5a2cec7351deec2cbf4c92f199ec4f09f243'
R15_ARCHIVE = 'f56f8308cb3741e17340ecb6802579d401b6280b98feb24773f506fdf1bad7f7'
R15_RECEIPTS = '6ee26b469e23febecde863caf0f4f07bcf96b5e42362a4ed66a7e3400e86bb52'
STUDY = '20261125-r15-j1-lineups'
DISPLAY = '20261125-j1-stage-windows'
NUMERICAL = dict(NPY_DISABLE_CPU_FEATURES='AVX512F', OPENBLAS_CORETYPE='Haswell', OPENBLAS_NUM_THREADS='1',
                 OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONHASHSEED='0')


def read(path):
    return json.loads(path.read_bytes())


def original_inputs(args, tmp):
    updates = args.data_root / 'workspace-updates'
    pkg = updates / STUDY
    require(file_sha(pkg / 'manifest.json') == R15_MANIFEST, 'immutable R15 evidence manifest differs')
    manifest = read(pkg / 'manifest.json')
    folders = {k: args.data_root / v['directory'] for k, v in manifest['dependencies'].items()}
    for k, folder in folders.items():
        require(file_sha(folder / 'manifest.json') == manifest['dependencies'][k]['manifest_sha256'],
                f'original {k} manifest differs')
    study = args.study or pkg / 'replay'
    for name in ('fit.json', 'forward.json', 'inputs.json'):
        require(file_sha(study / name) == manifest['files']['replay/' + name], f'R15 original {name} differs')
    firsts = args.r15_firsts or updates / '20261125-r15-j1-lineups-forward/first-issues.tar.gz'
    if firsts.is_file():
        require(file_sha(firsts) == R15_ARCHIVE, 'R15 firsts archive differs')
    else:
        require(file_sha(checked_file(firsts, 'receipts.json')) == R15_RECEIPTS, 'R15 original firsts index differs')
    events = args.rosters
    if events is None:
        # Import only the original, digest-checked R15 reconstruction helpers.
        names = ('common.py', 'intake.py', 'starters.py', 'baselines.py', 'extract_v1.py', 'intake.tar.gz')
        for name in (*names, *(n for n in manifest['files'] if n.startswith('raw/'))):
            require(file_sha(checked_file(pkg, name)) == manifest['files'][name], f'R15 reconstruction input {name}')
        sys.path.append(str(pkg))
        from common import unpack
        from intake import open_raw
        from starters import rebuild_rows
        meta = tmp / 'original-r15'
        unpack(pkg / 'intake.tar.gz', meta)
        raw, _ = open_raw(pkg, meta, tmp)
        events = rebuild_rows(meta, raw, read(study / 'inputs.json'), pkg / 'extract_v1.py')
    required = read(study / 'inputs.json')
    require(file_sha(events) == required['rosters_sha256']
            and file_sha(events.parent / 'snapshot-manifest.json') == required['roster_manifest_sha256'],
            'original roster snapshot differs')
    return folders, study, events, firsts, updates / DISPLAY


def original_annual(f, display, supplied, tmp):
    path = display / 'registration/calendar-provenance.json'
    require(file_sha(path) == f.CALENDAR_PROVENANCE_SHA, 'original annual provenance differs')
    row, = (v['source_capture'] for v in read(path)['later_capture'] if v['year'] == 2026)
    body = slice_.read_annual(display, row)
    if supplied is not None:
        require(supplied.read_bytes() == body, 'supplied annual calendar differs from #51 original')
    return write(tmp, 'annual.json', body)


def prepare(f, inputs, intake, annual, at, tmp, *, pending=False):
    tmp.mkdir()
    folders, study, events, firsts, display = inputs
    return f._prepare(folders, study, events, firsts, intake, display, annual, at, tmp, allow_pending=pending)


def check_cutoff(f, plan):
    original = f._first(plan, f.TRACK + '-registration')
    at = f.aware(original['payload']['identity']['inputs_cutoff_at'])
    require(at.utcoffset() == timezone.utc.utcoffset(None), 'original cutoff must be UTC')
    return at


def mirror(f, files, root):
    """Restore the original bytes in the native reader's two lookup locations without issuing any record."""
    for name, body in files.items():
        path = write(root, 'issued/' + name, body)
        if name != 'receipts.json':
            record = json.loads(body)
            scope = {k: record[k] for k in ('match_id', 'track', 'stage')}
            dest = root / 'scopes' / f.digest(scope) / '000001.json'
            dest.parent.mkdir(parents=True)
            os.link(path, dest)


def check_full(f, inputs, intake, annual, at, tmp, canonical):
    fixtures, payloads, identity = prepare(f, inputs, intake, annual, at, tmp)
    f._check_issued(canonical, fixtures, payloads, identity)
    require(len(fixtures) == len(payloads) == 10 and identity['filled'] == 3
            and identity['evidence']['dual_ft90'] == 7, 'incomplete R18 batch')
    return identity


def describe(f, plan, index, payloads, sources, file_count):
    identity = plan['payload']['identity']
    return dict(source_commit=SOURCE, registration_sha256=plan['record_sha256'],
                registered_at_utc=f.aware(plan['recorded_at']).astimezone(timezone.utc).isoformat(),
                cutoff_utc=identity['inputs_cutoff_at'], dual_ft90=identity['evidence']['dual_ft90'],
                historical_slots=identity['r15_history_coverage'], calendar=identity['evidence']['calendar']['counts'],
                doses=identity['doses'], unpriced=len(identity['unpriced']), seats=identity['selected'],
                raw_acquisitions=len(sources['acquisitions']), unique_raw_bodies=file_count,
                prior_evidence={m: dict(espn_sha256=e['espn']['sha256'], official_sha256=e['official']['sha256'],
                                        dual_ft90_at=e['ft_pair_observed_at_utc'], score=e['score'],
                                        starters={s: e['roster_coverage'][s]['status'] for s in f.SIDES})
                                for m, e in sorted(identity['evidence']['events'].items())},
                matches={m: dict(payload_sha256=f.digest(p), features_sha256=f.digest(p['features']),
                                 features_changed=p['features_changed'], same_decisions=p['forecasts']['candidate'] == p['forecasts']['r15'],
                                 rank=p['rank'], seat=p['seat'], r15_rank=p['r15_rank'], r15_seat=p['r15_seat'],
                                 first_sha256=index['matches'][m]['sha256'],
                                 issued_at_utc=index['matches'][m]['recorded_at_utc'])
                         for m, p in sorted(payloads.items())})


def shared_reference(data, path, sources):
    path = path.resolve()
    require(path.is_relative_to(data.resolve()), 'shared review must already be inside the portable data checkout')
    name = path.relative_to(data.resolve()).as_posix()
    checksum = file_sha(checked_file(data, name))
    at, names, bodies = slice_.shared_bodies(path, sources)
    require(names and checksum == file_sha(path), 'shared final review changed or has no cited bodies')
    return dict(path=name, sha256=checksum, as_of=at, members=names), bodies


def verify(f, args, inputs, annual, release, tmp):
    pins = read(checked_file(release, 'pins.json'))
    require(pins['format'] == FORMAT and pins['source_commit'] == SOURCE, 'release schema or source commit differs')
    require((args.registration_sha256 is None) == (args.receipts_sha256 is None), 'supply both external first pins')
    if args.registration_sha256 is not None:
        require((pins['registration_sha256'], pins['receipts_sha256']) == (args.registration_sha256, args.receipts_sha256),
                'release differs from independent firsts pins')
    require({p.name for p in release.iterdir()} == {TAR, 'sources.json', 'pins.json'}, 'unexpected release inventory')
    raw_archive = checked_file(release, TAR)
    require(file_sha(raw_archive) == pins['archive_sha256']
            and file_sha(checked_file(release, 'sources.json')) == pins['sources_sha256'], 'release file digest differs')
    sources = read(release / 'sources.json')
    contents = members(raw_archive)
    files = {n[7:]: b for n, b in contents.items() if n.startswith('firsts/')}
    require({n: digest(b) for n, b in files.items()} == pins['original_bytes_sha256'], 'original first byte hashes differ')
    canonical = tmp / 'reader'
    mirror(f, files, canonical)
    originals, plan = first_files(canonical / 'issued', pins['registration_sha256'], pins['receipts_sha256'])
    at = check_cutoff(f, plan)
    signed = plan['payload']['identity']['evidence']
    bodies = {n: b for n, b in contents.items() if not n.startswith('firsts/')}
    if pins['shared_review'] is not None:
        ref = pins['shared_review']
        path = checked_file(args.data_root, ref['path'])
        require(file_sha(path) == ref['sha256'], 'shared final review SHA differs')
        expected, shared = shared_reference(args.data_root, path, sources)
        require(expected == ref and not (bodies.keys() & shared.keys()), 'duplicate or different shared raw members')
        bodies.update(shared)
    intake = tmp / 'retained-intake'
    logs, projected = slice_.materialize(f, bodies, sources, signed, intake, at)
    fixtures, payloads, identity = prepare(f, inputs, intake, annual, at, tmp / 'replay')
    evidence = identity['evidence']
    require(evidence['acquisition_log_sha256'] == projected, 'model did not consume exactly the selected log rows')
    # The signed registration binds all original log bytes, even the AFC rows. Their hashes were
    # independently checked above. Only this metadata field differs for a projection of cited bodies.
    evidence['acquisition_log_sha256'] = {n: digest(logs[n]) for n in slice_.LOGS}
    _, early, _ = f._windows(inputs[-1])
    require(slice_.source_index(f, early, intake, evidence, at, logs) == sources,
            'raw source uses, clocks or independently reconstructed coverage differ')
    require(evidence == signed and len(payloads) == 10 and identity['filled'] == 3 and evidence['dual_ft90'] == 7,
            'the seven raw-certified histories or the ten target slots differ')
    index = f._check_issued(canonical, fixtures, payloads, identity)
    if getattr(args, 'full_intake', None) or getattr(args, 'review_bundle', None):
        if args.review_bundle and pins['input_review_sha256']:
            require(file_sha(args.review_bundle) == pins['input_review_sha256'], 'original nine-match review SHA differs')
        full = input_intake(f, args, at, tmp, calendar_fallback=intake)
        check_full(f, inputs, full, annual, at, tmp / 'untrimmed-replay', canonical)
    if getattr(args, 'restore', None):
        protected_output(f, args.restore, release, *inputs[0].values(), *inputs[1:])
        stage_files(originals, args.restore)
    result = describe(f, plan, index, payloads, sources, sum(k.startswith('objects/') for k in bodies))
    result['full_source_rechecked'] = bool(getattr(args, 'full_intake', None) or getattr(args, 'review_bundle', None))
    return result


def input_intake(f, args, at, tmp, *, calendar_fallback=None):
    root = getattr(args, 'intake', None) or getattr(args, 'full_intake', None) or calendar_fallback
    if args.review_bundle is None:
        require(root is not None, 'original intake directory required')
        return root
    require(root is not None, 'supply the intake directory with the four dated calendar files')
    return slice_.nine_intake(f, args.review_bundle, root, at, tmp / 'nine-j1')


def stage_files(files, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as scratch:
        stage = Path(scratch) / 'export'
        for name, body in files.items():
            write(stage, name, body)
        install(stage, target)


def protected_output(f, out, *sources):
    out = out.resolve()
    for parent in out.parents:
        require(not (parent / 'receipts.json').is_file() and not (parent / 'issued/receipts.json').is_file(),
                f'output overlaps firsts directory: {parent}')
    for path in (Path(f.ledger.DEFAULT_ROOT), *sources):
        if path is not None:
            path = path.resolve()
            require(not out.is_relative_to(path) and not path.is_relative_to(out), f'output overlaps input or store: {path}')


def pack(f, args, inputs, annual, tmp):
    protected_output(f, args.out, args.source, args.firsts, args.canonical, args.intake, args.review_bundle,
                     args.share_review, *inputs[0].values(), *inputs[1:])
    require(not args.firsts.resolve().is_relative_to(args.canonical.resolve()),
            'provide the independent export as well as the canonical track')
    originals, plan = first_files(args.canonical / 'issued', args.registration_sha256, args.receipts_sha256)
    exported, _ = first_files(args.firsts, args.registration_sha256, args.receipts_sha256)
    require(exported == originals, 'export differs byte-for-byte from the canonical firsts')
    at = check_cutoff(f, plan)
    parent_sha = file_sha(args.review_bundle) if args.review_bundle else None
    intake = input_intake(f, args, at, tmp)
    identity = check_full(f, inputs, intake, annual, at, tmp / 'full', args.canonical)
    evidence = identity['evidence']
    _, early, _ = f._windows(inputs[-1])
    logs = slice_.original_logs(f, intake, evidence, at)
    sources = slice_.source_index(f, early, intake, evidence, at, logs)
    files = slice_.package_inputs(intake, sources, logs)
    shared = None
    if args.share_review:
        shared, bodies = shared_reference(args.data_root, args.share_review, sources)
        for key, body in bodies.items():
            require(files.pop(key) == body, 'shared review differs from the actually consumed bytes')
    files.update({'firsts/' + n: b for n, b in originals.items()})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent, prefix='.r18-package-') as scratch:
        release = Path(scratch) / 'release'
        write(release, 'sources.json', encoded(sources))
        archive(release / TAR, files)
        pins = dict(format=FORMAT, source_commit=SOURCE, registration_sha256=args.registration_sha256,
                    receipts_sha256=args.receipts_sha256, archive_sha256=file_sha(release / TAR),
                    shared_review=shared, input_review_sha256=parent_sha,
                    sources_sha256=file_sha(release / 'sources.json'), original_bytes_sha256={n: digest(b) for n, b in originals.items()})
        write(release, 'pins.json', encoded(pins))
        # A completely fresh reader must recover all ten original payloads before any output is made visible.
        check_dir = tmp / 'independent'
        check_dir.mkdir()
        checking = argparse.Namespace(data_root=args.data_root, registration_sha256=args.registration_sha256,
                                      receipts_sha256=args.receipts_sha256)
        result = verify(f, checking, inputs, annual, release, check_dir)
        if parent_sha:
            require(file_sha(args.review_bundle) == parent_sha, 'input review changed during packaging')
        install(release, args.out)
    result['full_source_rechecked'] = True
    return result


def probe(f, args, inputs, annual, tmp):
    now = f._now()
    at = f.aware(args.as_of).astimezone(timezone.utc) if args.as_of else now
    require(at <= now, 'future probe clock')
    intake = input_intake(f, args, at, tmp)
    fixtures, payloads, identity = prepare(f, inputs, intake, annual, at, tmp / 'probe', pending=True)
    full = identity['evidence']
    logs = slice_.original_logs(f, intake, full, at)
    display = inputs[-1]
    _, early, _ = f._windows(display)
    sources = slice_.source_index(f, early, intake, full, at, logs)
    packed = slice_.package_inputs(intake, sources, logs)
    reduced = tmp / 'projected'
    _, projected = slice_.materialize(f, packed, sources, full, reduced, at)
    if payloads:
        slots, recovered, projected_identity = prepare(f, inputs, reduced, annual, at, tmp / 'projected-model')
        derived = projected_identity['evidence']
        require(slots == fixtures and f.digest(recovered) == f.digest(payloads), 'projected ten-target forecasts differ')
    else:
        derived, _ = f._evidence(reduced, display, early, at, annual)
    agreed = sorted(m for m, e in full['events'].items() if e['verdict'] == f.AGREED)
    require(derived['calendar'] == full['calendar'] and derived['acquisition_log_sha256'] == projected
            and all(derived['events'][m] == full['events'][m] for m in agreed)
            and derived['pending'] == full['pending'], 'projection changed a verified fixture or coverage')
    if payloads:
        derived['acquisition_log_sha256'] = {n: digest(logs[n]) for n in slice_.LOGS}
        require(f.digest(projected_identity) == f.digest(identity), 'projected model registration or seats differ')
    return dict(mode='unsigned_input_probe', cutoff_utc=at.isoformat(), source_commit=SOURCE, original_targets=len(fixtures),
                dual_ft90=len(agreed), verified_events=agreed, pending=full['pending'], historical_slots=identity['r15_history_coverage'],
                calendar=full['calendar']['counts'], preview_payloads=len(payloads), acquisitions=len(sources['acquisitions']),
                verified_preview_payloads=len(payloads), selected=identity.get('selected', {}),
                official_final_kinds={use['subject']: entry['kind'] for entry in sources['acquisitions']
                                      for use in entry['uses'] if use['role'] == 'official_final'},
                unique_raw_bodies=sum(k.startswith('objects/') for k in packed), doses=identity['doses'])


def worker(args, tmp):
    from research_program import lineup_cutoff_forward as f
    if args.command == 'pins':
        folder = args.canonical / 'issued'
        index = read(checked_file(folder, 'receipts.json'))
        registration, receipts = index['registration']['sha256'], file_sha(folder / 'receipts.json')
        files, plan = first_files(folder, registration, receipts)
        check_cutoff(f, plan)
        records = {m: json.loads(files[r['file']])['payload'] for m, r in index['matches'].items()}
        payloads = {m: {k: v for k, v in p.items() if k != 'registration_sha256'} for m, p in records.items()}
        f._check_issued(args.canonical, plan['payload']['fixtures'], payloads, plan['payload']['identity'])
        return dict(registration_sha256=registration, receipts_sha256=receipts)
    inputs = original_inputs(args, tmp)
    annual = original_annual(f, inputs[-1], getattr(args, 'annual_calendar', None), tmp)
    if args.command == 'inputs':
        firsts = inputs[3]
        name = 'firsts/receipts.json'
        body = members(firsts, lambda n: n == name)[name] if firsts.is_file() else (firsts / 'receipts.json').read_bytes()
        require(digest(body) == R15_RECEIPTS, 'R15 firsts independently retained index differs')
        old = json.loads(body)
        at = max(f.aware(ref['recorded_at']) for ref in old['matches'].values())
        _, early, weekend = f._windows(inputs[-1])
        _, original, _ = f._originals(firsts, tmp, weekend, early, at)
        with inputs[2].open('rb') as stream:
            count = sum(1 for _ in stream)
        return dict(source_commit=SOURCE, rosters_sha256=file_sha(inputs[2]), r15_history_rows=count, r15_firsts=len(original),
                    annual_sha256=file_sha(annual), r15_manifest_sha256=R15_MANIFEST)
    if args.command == 'probe':
        return probe(f, args, inputs, annual, tmp)
    if args.command == 'pack':
        return pack(f, args, inputs, annual, tmp)
    return verify(f, args, inputs, annual, args.release, tmp)


def no_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg'):
        raise RuntimeError('network access is disabled during R18 replay')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest='command', required=True)
    for mode in ('inputs', 'pins', 'probe', 'pack', 'verify'):
        cmd = cmds.add_parser(mode)
        cmd.add_argument('--source', type=Path, required=True, help='local source Git checkout with the exact committed object')
        if mode in ('pins', 'pack'):
            cmd.add_argument('--canonical', type=Path, required=True, help='original R18 track directory containing issued/ and scopes/')
        if mode == 'pins':
            continue
        cmd.add_argument('--data-root', type=Path, default=HERE.parents[1])
        cmd.add_argument('--study', type=Path, help='exact R15 fit/input/forward directory; defaults to archived R15 replay/')
        cmd.add_argument('--rosters', type=Path, help='optional exact R15 events.jsonl next to its original manifest')
        cmd.add_argument('--r15-firsts', type=Path, help='optional original R15 firsts export; defaults to pinned data archive')
        cmd.add_argument('--annual-calendar', type=Path, help='cross-check a relocated original against the #51 archive')
        if mode in ('probe', 'pack'):
            cmd.add_argument('--intake', type=Path, required=True, help='nine-match intake with calendar audit')
        if mode == 'probe':
            cmd.add_argument('--as-of', help='optional observed ISO clock for a read-only coverage probe')
        if mode in ('probe', 'pack', 'verify'):
            cmd.add_argument('--review-bundle', type=Path, help='complete nine-match offline review, supplies acquisitions instead of live intake')
        if mode in ('pack', 'verify'):
            cmd.add_argument('--registration-sha256', required=mode == 'pack')
            cmd.add_argument('--receipts-sha256', required=mode == 'pack')
        if mode == 'pack':
            cmd.add_argument('--firsts', type=Path, required=True, help='actual R18 exported firsts directory')
            cmd.add_argument('--out', type=Path, default=HERE / 'release')
            cmd.add_argument('--share-review', type=Path, help='reference existing identical raw members in a nine-final archive in the data checkout')
        if mode == 'verify':
            cmd.add_argument('--release', type=Path, default=HERE / 'release')
            cmd.add_argument('--full-intake', type=Path, help='add independent verification against original untrimmed captures')
            cmd.add_argument('--restore', type=Path, help='recover the 12 unchanged original files into an independent directory')
    a = parser.parse_args()
    args = {k: str(v.absolute()) if isinstance(v, Path) else v for k, v in vars(a).items()}
    paths = [k for k, v in vars(a).items() if isinstance(v, Path)]
    require(re.fullmatch('[0-9a-f]{40}', SOURCE), 'pinned full source commit required')
    # Force Git to use only local objects even for a partial/promisor checkout.
    env = dict(os.environ, **NUMERICAL, GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='', GIT_NO_REPLACE_OBJECTS='1',
               GIT_TERMINAL_PROMPT='0', PYTHONDONTWRITEBYTECODE='1')
    with TemporaryDirectory(prefix='r18-offline-') as scratch:
        tmp = Path(scratch).resolve()
        source_root = tmp / 'source'
        with (tmp / 'code.tar').open('xb') as stream:
            subprocess.run(['git', '-C', str(a.source), 'archive', SOURCE, 'runtime', 'research/20261125-r18-j1-cutoff',
                            'research/20261125-r15-j1', 'configs/analysis-scope.json'], stdout=stream, env=env, check=True)
        with tarfile.open(tmp / 'code.tar') as tar:
            tar.extractall(source_root, filter='data')
        env.update(MPLCONFIGDIR=str(tmp / 'mpl'))
        # -I excludes caller PYTHONPATH, user site, and the caller's working directory.
        code = """import argparse,json,sys
from pathlib import Path
spec=json.load(sys.stdin)
sys.path[:0]=spec['imports']
from forward_bundle import SOURCE,encoded,no_network,worker
if SOURCE != spec['source_commit']: raise ValueError('source pin changed during local checkout')
sys.addaudithook(no_network)
args=spec['args']
for k in spec['paths']: args[k]=Path(args[k])
sys.stdout.buffer.write(encoded(worker(argparse.Namespace(**args),Path(spec['tmp']))))
"""
        spec = dict(args=args, paths=paths, tmp=str(tmp), source_commit=SOURCE, imports=[str(HERE), str(source_root / 'runtime')])
        subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=tmp, env=env, input=encoded(spec), check=True)


if __name__ == '__main__':
    main()
