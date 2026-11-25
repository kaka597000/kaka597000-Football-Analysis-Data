"""Build or verify an immutable, offline R20 J1 halftime research release."""

import argparse
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

from bundle_io import archive, checked_file, digest, encoded, first_files, install, members, require, write
import evidence as ev
from study_checks import OUTPUTS, audit

HERE = Path(__file__).resolve().parent
SLUG = '20261125-r20-j1-halftime'
SCHEMA = 'r20-j1-halftime-data-v1'
FOLDERS = dict(r5='20261123-all-scope-kpi', r7='20261123-prematch-literature', r10='20261125-r10-shot-conversion')
ENV = dict(OPENBLAS_CORETYPE='Haswell', NPY_DISABLE_CPU_FEATURES='AVX512F', OPENBLAS_NUM_THREADS='1',
           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONHASHSEED='0',
           PYTHONDONTWRITEBYTECODE='1', GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='', GIT_NO_REPLACE_OBJECTS='1')


def inventory(folder):
    paths = sorted(folder.rglob('*'))
    require(folder.is_dir() and not any(p.is_symlink() for p in paths), ('directory inventory', folder))
    return {p.relative_to(folder).as_posix(): ev.sha(p) for p in paths if p.is_file()}


def unpack(source, root):
    for name, body in members(source).items():
        write(root, name, body)


def r18_subset(source):
    require(ev.sha(source) == ev.R18_ARCHIVE, 'separately verified R18 data archive')
    files = members(source)
    selected = {k: v for k, v in files.items() if k.startswith('firsts/')}
    receipts = json.loads(selected['firsts/receipts.json'])
    require(digest(selected['firsts/receipts.json']) == ev.R18_RECEIPTS
            and receipts['registration']['sha256'] == ev.R18_REGISTRATION, 'original R18 receipt pins')
    plan = json.loads(selected['firsts/' + receipts['registration']['file']])
    for event in plan['payload']['identity']['evidence']['events'].values():
        key = 'objects/' + event['espn']['sha256']
        require(digest(files[key]) == event['espn']['sha256'], 'original R18 excluded match summary')
        selected[key] = files[key]
    require(len(selected) == 19, 'R18 twelve originals and seven raw summaries')
    return selected


def late_bytes(folder, supplied=None):
    ref, = (v for v in ev.read(folder / 'coverage.json')['inputs'] if Path(v['path']).name == 'final-90-evidence.jsonl')
    path = supplied or Path(ref['path'])
    body = path.read_bytes()
    require(digest(body) == ref['sha256'] and len(body) == ref['bytes'], 'original late index digest or size')
    return body


def intake_files(folder, late_receipts):
    ev.source_manifest(folder)
    files = {n: checked_file(folder, n).read_bytes() for n in sorted(ev.INTAKE_FILES | {'artifact-manifest.json'})}
    files['acquisition/final-90-evidence.jsonl'] = late_receipts
    return files


def inspect_sources(data, intake, r18, tmp, late_receipts):
    halves, games, controls, failures = ev.history(data, intake, tmp)
    files, parent = first_files(r18 / 'firsts', ev.R18_REGISTRATION, ev.R18_RECEIPTS)
    extras = ev.excluded(intake, r18, parent, late_receipts)
    return halves, games, controls, failures, dict(scheduled=len(games), eligible=len(games) - len(failures),
        ineligible=len(failures), separate_late_exclusions=extras, r18_originals=len(files), halves_sha256=ev.sha(halves),
        intake_manifest_sha256=ev.sha(intake / 'artifact-manifest.json'), r15_manifest_sha256=ev.R15_MANIFEST)


def stage_source(source, revision, tmp):
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'final 40-character R20 source commit required')
    code = tmp / 'source'
    with (tmp / 'code.tar').open('xb') as stream:
        subprocess.run(['git', '-C', str(source), 'archive', revision, 'runtime', 'research/' + SLUG, 'configs/analysis-scope.json'],
                       env=os.environ | ENV, check=True, stdout=stream)
    with tarfile.open(tmp / 'code.tar') as tar:
        tar.extractall(code, filter='data')
    require(ev.sha(code / 'research' / SLUG / 'protocol.json') == ev.PROTOCOL_SHA == ev.sha(HERE / 'protocol.json'),
            'preregistered protocol differs from final source or package')
    return code


def native_forward(study, parent, issued, registration, receipts, tmp, canonical=None):
    from research_program import halftime_state_forward as model
    files, plan = first_files(issued, registration, receipts)
    reg = model._first_ref(issued, ev.read(issued / 'receipts.json')['registration'], model.TRACK + '-registration')
    require(reg == plan, 'R20 registration readback differs')
    at = model.aware(plan['payload']['identity']['inputs_cutoff_at'])
    fixtures, payloads, identity, locks = model._prepare(study, parent, at)
    require(all(ev.sha(p) == sha for p, sha in locks.items()), 'changed forward inputs')
    if canonical is None:
        # Restore only the genuine bytes in temporary scope lookup locations for the native read-only verifier.
        canonical = tmp / 'scope-reader'
        for name, body in files.items():
            file = write(canonical / 'issued', name, body)
            if name != 'receipts.json':
                r = json.loads(body)
                scope = {k: r[k] for k in ('match_id', 'track', 'stage')}
                dest = canonical / 'scopes' / model.digest(scope) / '000001.json'
                dest.parent.mkdir(parents=True)
                os.link(file, dest)
    index = model._readback(canonical, fixtures, payloads, identity)
    require(len(fixtures) == len(payloads) == len(index['matches']) == 10 and identity['filled'] == 3
            and ev.sha(parent / 'receipts.json') == ev.R18_RECEIPTS, 'R18 target population or original three seats')
    return dict(registration_sha256=registration, receipts_sha256=receipts, at=at.isoformat(),
                recorded_at=reg['recorded_at'], issued=len(payloads), selected=identity['selected'],
                without_total_line=identity['without_total_line'], ranking=identity['ranking'],
                payload_sha256={k: model.digest(v) for k, v in payloads.items()})


def fresh_studies(code, folders, halves, tmp):
    env = os.environ | ENV | dict(PYTHONPATH=str(code / 'runtime'), MPLCONFIGDIR=str(tmp / 'mpl'))
    runs = []
    for n in (1, 2):
        out = tmp / f'fresh-{n}'
        args = [sys.executable, '-B', '-m', 'research_program.halftime_state_study']
        for k, v in folders.items():
            args += ['--' + k, str(v)]
        subprocess.run(args + ['--halves', str(halves), '--out', str(out)], cwd=tmp, env=env,
                       check=True, stdout=subprocess.DEVNULL)
        runs.append(out)
    require(inventory(runs[0]) == inventory(runs[1]) and set(inventory(runs[0])) == set(OUTPUTS),
            'two new independent pinned-source refits differ')
    return runs[0]


def check_historical(study, repeat):
    first, second = inventory(study), inventory(repeat)
    require(study.resolve() != repeat.resolve() and first == second and set(first) == set(OUTPUTS),
            'two actual historical runs and exact output inventories required')
    require(all(not (study / n).samefile(repeat / n) for n in OUTPUTS), 'original and repeat share an output inode')
    return first, second


def compare_fresh(fresh, originals):
    for name in OUTPUTS:
        a, b = (folder / name for folder in (fresh, originals))
        if name.endswith('.gz'):
            require(gzip.decompress(a.read_bytes()) == gzip.decompress(b.read_bytes()), ('new predictions or seats differ', name))
        else:
            require(a.read_bytes() == b.read_bytes(), ('new fit, inputs, or metrics differ', name))


def verify_release(args, release, tmp):
    manifest = ev.read(checked_file(release, 'manifest.json'))
    require(manifest['schema'] == SCHEMA and manifest['registration_commit'] == ev.PREREGISTRATION
            and manifest['protocol_sha256'] == ev.PROTOCOL_SHA and manifest['r18_package_sha256'] == ev.R18_ARCHIVE,
            'release provenance differs')
    actual = inventory(release)
    actual.pop('manifest.json')
    require(actual == manifest['files'], 'release file inventory or byte hash differs')
    require(manifest['source_commit'] == args.source_commit, 'different final R20 source commit')
    code = stage_source(args.source, args.source_commit, tmp)
    sys.path.insert(0, str(code / 'runtime'))
    folders = {k: args.data_root / 'workspace-updates' / v for k, v in FOLDERS.items()}
    intake, r18, issued = (tmp / n for n in ('intake', 'r18', 'firsts'))
    for archive_name, location in (('halves-intake.tar.gz', intake), ('r18-reference.tar.gz', r18), ('ten-firsts.tar.gz', issued)):
        unpack(release / archive_name, location)
    halves, games, controls, failures, report = inspect_sources(args.data_root, intake, r18, tmp, late_bytes(intake, intake / 'acquisition/final-90-evidence.jsonl'))
    require(manifest['sources'] == report and ev.sha(halves) == ev.read(release / 'study/inputs.json')['halves_sha256'],
            'raw-derived training input or source snapshot differs')
    published = release / 'study'
    require(manifest['two_original_refits'] == [inventory(published)] * 2, 'actual independent run fingerprints differ')
    tables = audit(published, games, controls, failures)
    require({p.name: p.read_bytes() for p in (release / 'tables').iterdir()} == tables, 'evidence tables differ')
    fresh = fresh_studies(code, folders, halves, tmp)
    compare_fresh(fresh, published)
    result = native_forward(published, r18 / 'firsts', issued, args.registration_sha256, args.receipts_sha256, tmp)
    require(manifest['forward'] == result, 'independently reconstructed firsts differ')
    return dict(source_commit=args.source_commit, sources=report, two_original_runs_equal=True,
                two_new_runs_equal=True, new_and_original_studies_equal=True, forward=result)


def stage(args, target, tmp):
    histories = check_historical(args.study, args.repeat)
    originals, _ = first_files(args.firsts, args.registration_sha256, args.receipts_sha256)
    canonical, _ = first_files(args.canonical / 'issued', args.registration_sha256, args.receipts_sha256)
    require(originals == canonical and not args.firsts.resolve().is_relative_to(args.canonical.resolve()),
            'separate genuine R20 export and canonical first bytes required')
    target.mkdir()
    late_receipts = late_bytes(args.intake, args.late_receipts)
    archive(target / 'halves-intake.tar.gz', intake_files(args.intake, late_receipts))
    archive(target / 'r18-reference.tar.gz', r18_subset(args.r18_bundle))
    archive(target / 'ten-firsts.tar.gz', originals)
    for name in OUTPUTS:
        write(target / 'study', name, checked_file(args.study, name).read_bytes())
    r18 = tmp / 'r18'
    unpack(target / 'r18-reference.tar.gz', r18)
    halves, games, controls, failures, report = inspect_sources(args.data_root, args.intake, r18, tmp, late_receipts)
    require(ev.sha(halves) == ev.read(args.study / 'inputs.json')['halves_sha256'], 'actual study used different halves')
    for name, body in audit(args.study, games, controls, failures).items():
        write(target / 'tables', name, body)
    code = stage_source(args.source, args.source_commit, tmp)
    sys.path.insert(0, str(code / 'runtime'))
    result = native_forward(args.study, r18 / 'firsts', args.firsts, args.registration_sha256, args.receipts_sha256, tmp, args.canonical)
    write(target, 'manifest.json', encoded(dict(schema=SCHEMA, source_commit=args.source_commit,
          registration_commit=ev.PREREGISTRATION, protocol_sha256=ev.PROTOCOL_SHA, r18_package_sha256=ev.R18_ARCHIVE,
          two_original_refits=list(histories), sources=report, forward=result, files=inventory(target))))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    cmds = p.add_subparsers(dest='command', required=True)
    for mode in ('evidence', 'pack', 'verify'):
        cmd = cmds.add_parser(mode)
        cmd.add_argument('--data-root', type=Path, default=HERE.parents[1])
        if mode in ('evidence', 'pack'):
            cmd.add_argument('--late-receipts', type=Path, help='relocated original final-90-evidence.jsonl')
            for name in ('intake', 'r18-bundle'):
                cmd.add_argument('--' + name, type=Path, required=True)
        if mode == 'evidence':
            cmd.add_argument('--study', type=Path)
            cmd.add_argument('--repeat', type=Path)
            continue
        cmd.add_argument('--source', type=Path, required=True)
        cmd.add_argument('--source-commit', required=True)
        cmd.add_argument('--registration-sha256', required=True)
        cmd.add_argument('--receipts-sha256', required=True)
        cmd.add_argument('--release', type=Path, default=HERE / 'release')
        if mode == 'pack':
            for name in ('study', 'repeat', 'firsts', 'canonical'):
                cmd.add_argument('--' + name, type=Path, required=True)
    return p


def main():
    args = parser().parse_args()
    for k, v in vars(args).copy().items():
        if isinstance(v, Path):
            setattr(args, k, v.resolve())
    with TemporaryDirectory(prefix='r20-offline-') as temporary:
        tmp = Path(temporary)
        os.environ['MPLCONFIGDIR'] = str(tmp / 'mpl')
        if args.command == 'evidence':
            r18 = tmp / 'r18'
            for name, body in r18_subset(args.r18_bundle).items():
                write(r18, name, body)
            halves, games, controls, failures, result = inspect_sources(args.data_root, args.intake, r18, tmp, late_bytes(args.intake, args.late_receipts))
            require((args.study is None) == (args.repeat is None), 'supply both original study directories')
            if args.study:
                check_historical(args.study, args.repeat)
                require(ev.sha(halves) == ev.read(args.study / 'inputs.json')['halves_sha256'], 'study used different halves')
                result['historical_tables'] = sorted(audit(args.study, games, controls, failures))
        elif args.command == 'verify':
            result = verify_release(args, args.release, tmp)
        else:
            protected = [args.source, args.intake, args.study, args.repeat, args.canonical, args.firsts, args.r18_bundle,
                         Path('/workspace/WCPP/forecasts/issued-analyses').resolve()]
            require(all(not args.release.is_relative_to(p) and not p.is_relative_to(args.release) for p in protected),
                    'package output overlaps source, original inputs or canonical store')
            args.release.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=args.release.parent, prefix='.r20-build-') as local:
                prepared = Path(local) / 'release'
                stage(args, prepared, tmp)
                # The verification process imports precisely its own clean source tree and archived originals.
                cmd = [sys.executable, '-B', str(HERE / 'package.py'), 'verify', '--release', str(prepared),
                       '--source', str(args.source), '--source-commit', args.source_commit, '--data-root', str(args.data_root),
                       '--registration-sha256', args.registration_sha256, '--receipts-sha256', args.receipts_sha256]
                result = json.loads(subprocess.check_output(cmd, env=os.environ | ENV, cwd=tmp))
                install(prepared, args.release)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    # These are set before importing any numerical model in this interpreter.
    os.environ.update(ENV)
    main()
