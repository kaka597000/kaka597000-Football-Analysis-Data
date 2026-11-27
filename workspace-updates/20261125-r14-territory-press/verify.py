"""Verify R14 source bindings, raw extraction, settlements, fits and first issues."""

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from tables import CODES, check, first_issues, lines, read, replay_tables, sha

VERSION = 'R14-territory-press-hurdle-1'
BUNDLE = '20261125-r14-territory-press'
BASELINES = dict(r5='20261123-all-scope-kpi', r7='20261123-prematch-literature',
                 r10='20261125-r10-shot-conversion')
ISSUES = dict(r5='forward-first-issues.tar.gz', r7='first-issues.tar.gz', r10='forward/first-issues.tar.gz')
PROTOCOL = 'research/20261125-r14/protocol.json'
R11_HASHES = {'manifest.json': 'd76cdbc338407c9962122f70aa69a071c0df51203fc2cb6e74d9a722054543bb',
              'extension.tar.gz': 'd5d39eb5ad1cab389ad2bcf9414e6168c23a7d1a682ca037000b0f46ea2889cc'}


def files(root):
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob('*'))
            if p.is_file() and not any(s.startswith('.') or s == '__pycache__' for s in p.relative_to(root).parts)}


def unpack(archive, target):
    with tarfile.open(archive, 'r:gz') as tar:
        names = set()
        for member in tar:
            path = Path(member.name)
            check((member.isfile() or member.isdir()) and not path.is_absolute() and '..' not in path.parts
                  and path not in names, (archive, member.name))
            names.add(path)
            tar.extract(member, target, filter='data')


def baselines(root, data, manifest, independent):
    folders = {k: data / 'workspace-updates' / v for k, v in BASELINES.items()}
    folders['r11'] = root / 'inputs/r11'
    check(all(sha(folders['r11'] / n) == v for n, v in R11_HASHES.items()), 'original R11 PR #48 bytes')
    archives = {k: [f'models/{code}.tar.gz' for code in CODES] for k in ('r5', 'r7')}
    archives.update(r10=['replay/main.tar.gz'], r11=['extension.tar.gz'])
    if independent:
        archives['r10'] += ['replay/independent.tar.gz', 'inputs/independent.tar.gz']
    if manifest['forward_included']:
        for k, name in ISSUES.items():
            archives[k].append(name)
    for k, folder in folders.items():
        m = folder / 'manifest.json'
        check(sha(m) == manifest['baseline_manifest_sha256'][k], (k, 'manifest SHA-256'))
        checksums = read(m)['files']
        for name in archives[k]:
            check(sha(folder / name) == checksums[name], (k, name))
    return folders


def rebuild_inputs(root, temp, study, parents):
    understat = temp / 'understat'
    unpack(root / 'inputs/understat.tar.gz', understat)
    derived = ('events.jsonl', 'sources.jsonl', 'reports/coverage.json')
    expected = {name: sha(understat / name) for name in derived}
    for name in derived:
        (understat / name).unlink()
    subprocess.run([sys.executable, '-B', str(understat / 'extract.py')], cwd=understat, check=True,
                   stdout=subprocess.DEVNULL)
    check({name: sha(understat / name) for name in derived} == expected, 'raw Understat extraction')
    sources = lines(understat / 'sources.jsonl')
    for record in sources:
        path = understat / record['source_file']
        with gzip.open(path, 'rb') as stream:
            decoded = hashlib.file_digest(stream, 'sha256').hexdigest()
        check(decoded == record['source_payload_sha256'] and sha(path) == record['source_gzip_sha256'],
              record['source_file'])
    inputs = read(study / 'inputs.json')
    events = understat / 'events.jsonl'
    with events.open('rb') as stream:
        count = sum(bool(row.strip()) for row in stream)
    check((expected['events.jsonl'], count, sha(parents['r11'] / 'manifest.json')) ==
          (inputs['events_sha256'], inputs['source_events'], inputs['extension_manifest_sha256']), 'study inputs')

    # R11's intake script downloads current quotes. Check the archived physical CSV rows offline.
    extension = temp / 'extension'
    unpack(parents['r11'] / 'extension.tar.gz', extension)
    raw = {}
    for item in read(extension / 'manifest.json')['sources']:
        path = extension / item['file']
        check(sha(path) == item['sha256'], item['file'])
        with path.open(encoding='utf-8-sig', newline='') as stream:
            raw[item['league']] = (item['sha256'], list(csv.DictReader(stream)))
    fixtures = lines(extension / 'fixture-panels.jsonl')
    panel = {(g['competition'], g['id']): g for g in fixtures}
    check(len(panel) == len(fixtures), 'R11 duplicate panel fixture')
    with (extension / 'market-rows.csv').open(encoding='utf-8-sig', newline='') as stream:
        for market in csv.DictReader(stream):
            code = market['competition']
            g = panel.pop((code, market['id']))
            digest, records = raw[code]
            pos = int(market['csv_row_physical']) - 2
            check(0 <= pos < len(records), (code, 'R11 source row'))
            row = records[pos]
            stamp = row['Date'].strip()
            day = datetime.strptime(stamp, '%d/%m/%Y').date().isoformat() if '/' in stamp else stamp
            check(digest == g['source_sha256'] == market['source_sha256'] and day == g['date'] == market['date']
                  and all(row[k].strip() == g[s] == market[s] for k, s in [('HomeTeam', 'home'), ('AwayTeam', 'away')])
                  and all(int(float(row[k])) == g[s] == int(market[s]) for k, s in [('FTHG', 'home_goals'),
                                                                                    ('FTAG', 'away_goals')])
                  and all((row[k] or '').strip() == market[k] for k in ('B365H', 'B365D', 'B365A', 'B365>2.5',
                                                                         'B365<2.5')), (code, market['id']))
    check(not panel, 'R11 panel fixtures missing archived first prices')
    return events


def stamp(s):
    value = datetime.fromisoformat(s)
    check(value.utcoffset() is not None, ('missing offset', s))
    return value


def receipt(folder, ref):
    name = ref['file']
    check(Path(name).name == name, 'receipt filename')
    body = read(folder / name)
    digest = body.pop('record_sha256')
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    check(digest == ref['sha256'] == hashlib.sha256(encoded).hexdigest() and body['freeze_id'] == ref['id']
          and body['recorded_at'] == ref['recorded_at'] and body['stage'] == 'prematch' and body['revision'] == 1
          and body['previous_sha256'] is None and body['evaluation_slot'] == 'FIRST_PREMATCH', ('receipt', name))
    return dict(body, record_sha256=digest)


def verify_issues(root, temp, parents, study):
    for key, archive in ISSUES.items():
        unpack(parents[key] / archive, temp / key)
    unpack(root / 'forward/first-issues.tar.gz', temp / 'issued')
    unpack(root / 'forward/ranked.tar.gz', temp / 'ranked')
    check(first_issues(temp / 'issued', temp / 'ranked') == (root / 'forward/first-issues.csv').read_bytes(),
          'forward table')
    ledgers = {}
    for k, folder in dict(r5=temp / 'r5/issued', r7=temp / 'r7', r10=temp / 'r10', r14=temp / 'issued').items():
        index = read(folder / 'receipts.json')
        plan = receipt(folder, index['registration'])
        check(set(index['matches']) == set(plan['payload']['fixtures']), (k, 'registration population'))
        ledgers[k] = folder, index['matches'], plan
    folder, matches, plan = ledgers['r14']
    identity, fixtures = plan['payload']['identity'], plan['payload']['fixtures']
    check(plan['payload']['track'] == 'research-r14-territory-press-20261125' and set(identity['competitions']) == set(CODES)
          and identity['protocol_sha256'] == sha(root / 'protocol.json')
          and identity['study_inputs_sha256'] == sha(study / 'inputs.json')
          and identity['events_sha256'] == read(study / 'inputs.json')['events_sha256']
          and identity['archive_manifest_sha256'] == {k: sha(p / 'manifest.json') for k, p in parents.items()},
          'R14 registration provenance')
    for k in ISSUES:
        check(identity[k + '_registration'] == ledgers[k][2]['record_sha256'], (k, 'registration'))
    eligible = {mid for mid, g in ledgers['r10'][2]['payload']['fixtures'].items() if g['cohort'] in CODES}
    expired = set(identity['already_started'])
    check(set(matches).isdisjoint(expired) and set(matches) | expired == eligible, 'in-scope R10 population')
    groups = defaultdict(list)
    for mid, ref in matches.items():
        r = receipt(folder, ref)
        g, payload = r['fixture'], r['payload']
        parents_by_id = [receipt(ledgers[k][0], ledgers[k][1][mid]) for k in ('r5', 'r7', 'r10')]
        r5, r7, r10 = parents_by_id
        for other in [fixtures[mid], *(v['fixture'] for v in parents_by_id)]:
            check(all(g[k] == other[k] for k in ('match_id', 'cohort', 'stage', 'home', 'away', 'kickoff_at')), mid)
        timeline = [stamp(o['recorded_at']) for o in [*parents_by_id, plan]]
        timeline += [stamp(g['cutoff_at']), stamp(r['recorded_at']), stamp(g['kickoff_at'])]
        tips = payload['forecasts']
        code = g['cohort']
        fname = study / 'main' / code / 'forward.json'
        recipe = read(fname)
        check(timeline == sorted(timeline) and timeline[-2] < timeline[-1]
              and payload['registration_sha256'] == plan['record_sha256']
              and payload['recipe_sha256'] == identity['recipe_sha256'][code] == sha(fname)
              and payload['training_through'] == recipe['through']
              and payload['fit_sha256'] == recipe['fit_sha256'] and payload['baseline_sha256'] == recipe['baseline_sha256']
              and payload['odds_source_first_issue'] == r5['record_sha256']
              and payload['r7_first_issue'] == r7['record_sha256'] and payload['r10_first_issue'] == r10['record_sha256']
              and tips['r7'] == r7['payload']['forecasts']['candidate'] and tips['r10'] == r10['payload']['forecasts']['candidate']
              and tips['market'] == r5['payload']['forecasts']['market'] and payload['prices'] == r5['payload']['prices']
              and payload['line'] == r5['payload']['line'], ('forward provenance', mid))
        first = tips['candidate']
        check(len(first['top3']) == len(set(first['top3'])) == 3 and first['primary'] == first['top3'][0], mid)
        groups[code].append((-payload['quality']['p_first'], timeline[-1], mid, first['top3'], ref))
    ranked = receipt(temp / 'ranked', read(temp / 'ranked/plan.json'))
    ri = ranked['payload']['identity']
    check(ri['source_registration'] == plan['record_sha256'] and ranked['payload']['fixtures'] == fixtures,
          'ranked parent')
    selected = ri['selected']
    check({k for k, v in selected.items() if v} == set(groups), 'ranked cohorts')
    for code, rows in groups.items():
        expected = sorted(rows)[:3]
        for record, (neg_prob, kickoff, mid, top, ref) in zip(selected[code], expected, strict=True):
            check((record['match_id'], record['top3'], record['first_issue'], record['first_probability']) ==
                  (mid, top, ref, -neg_prob) and stamp(ref['recorded_at']) <= stamp(ranked['recorded_at']) < kickoff,
                  ('rank', code, mid))
    return len(matches), sum(len(v) for v in selected.values())


def compare_value(a, b, where):
    if isinstance(a, dict) and isinstance(b, dict):
        check(a.keys() == b.keys(), (where, 'keys', sorted(a.keys() ^ b.keys())))
        for key in a:
            compare_value(a[key], b[key], where + '/' + key)
    elif isinstance(a, list) and isinstance(b, list):
        check(len(a) == len(b), (where, 'length'))
        for i, (left, right) in enumerate(zip(a, b)):
            compare_value(left, right, where + '/' + str(i))
    elif type(a) is float and type(b) is float:
        check(math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-9), (where, 'numeric mismatch'))
    else:
        check(type(a) == type(b) and a == b, (where, 'value mismatch'))


def compare_replay(original, trained):
    a, b = files(original), files(trained)
    check(a.keys() == b.keys(), ('retrained file inventory', sorted(a.keys() ^ b.keys())))
    for name in a:
        if sha(a[name]) == sha(b[name]):
            continue
        if name.endswith('.jsonl.gz'):
            compare_value(lines(a[name]), lines(b[name]), name)
        elif name.endswith('.json'):
            left, right = read(a[name]), read(b[name])
            if name.endswith('/forward.json'):
                for doc, path in ((left, a[name]), (right, b[name])):
                    check(doc.pop('fit_sha256') == sha(path.with_name('fit.json')), (name, 'fit hash'))
            compare_value(left, right, name)
        else:
            raise ValueError('different retrained artifact ' + name)


def retrain(source, parents, events, study, temp):
    env = dict(os.environ, PYTHONPATH=str(source / 'runtime'), PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1',
               MPLCONFIGDIR=str(temp / 'matplotlib'))
    cmd = [sys.executable, '-B', '-m', 'research_program.territory_study', '--events', str(events)]
    for name in ('r5', 'r7', 'r10', 'r11'):
        cmd.extend(['--' + name, str(parents[name])])
    if read(study / 'inputs.json')['independent_requested']:
        early = temp / 'early'
        unpack(parents['r10'] / 'inputs/independent.tar.gz', early)
        cmd.extend(['--independent', str(early)])
    first, repeat = temp / 'training-a', temp / 'training-b'
    for dest in (first, repeat):
        print('Starting ' + dest.name, flush=True)
        subprocess.run([*cmd, '--out', str(dest)], env=env, cwd=temp, check=True)
    check({n: sha(p) for n, p in files(first).items()} == {n: sha(p) for n, p in files(repeat).items()},
          'two fresh training runs differ')
    print('Both fresh replay trees are byte-identical.', flush=True)
    compare_replay(study, first)


def verify(root, data, source, *, quick=False):
    manifest = read(root / 'manifest.json')
    check(manifest['version'] == read(root / 'protocol.json')['version'] == VERSION, 'protocol version')
    check({n: sha(p) for n, p in files(root).items() if n != 'manifest.json'} == manifest['files'],
          'R14 file inventory or checksum')
    check(sha(root / 'protocol.json') == sha(source / PROTOCOL)
          and all(sha(source / n) == v for n, v in manifest['source_files'].items()), 'source files or protocol differ')
    with tempfile.TemporaryDirectory(prefix='r14-verify-') as tmp:
        temp = Path(tmp)
        study = temp / 'study'
        unpack(root / 'replay/forecasts.tar.gz', study)
        parents = baselines(root, data, manifest, read(study / 'inputs.json')['independent_requested'])
        events = rebuild_inputs(root, temp, study, parents)
        for name, value in replay_tables(study).items():
            check((root / 'replay' / name).read_bytes() == value, ('PR table', name))
        check(sha(root / 'replay/metrics.json') == sha(study / 'metrics.json'), 'published metrics copy')
        for code in CODES:
            with tarfile.open(parents['r7'] / f'models/{code}.tar.gz') as tar:
                baseline_hash = hashlib.file_digest(tar.extractfile('main/forward.json'), 'sha256').hexdigest()
            check(read(study / 'main' / code / 'forward.json')['baseline_sha256'] == baseline_hash, (code, 'R7 anchor'))
        if manifest['forward_included']:
            print('Verified first issues and ranked slots:', *verify_issues(root, temp, parents, study), flush=True)
        print('Verified archived raw, model bindings, counts, comparisons, diagnostics and weights.', flush=True)
        if not quick:
            retrain(source, parents, events, study, temp)
            print('Archived selections, counts, coefficients and policies agree with the rebuild.', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--data-root', type=Path, help='data repository containing workspace-updates')
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--quick', action='store_true', help='verify the package without the two fresh replay runs')
    opt = ap.parse_args()
    root = opt.bundle.resolve()
    verify(root, (opt.data_root or root.parent.parent).resolve(), opt.source.resolve(), quick=opt.quick)
