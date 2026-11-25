"""Offline verification of the R20 halftime observations against R5 and the original ESPN bytes."""

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import json
from pathlib import Path
import re
import sys

from bundle_io import digest as checksum, file_sha as sha, require

R15_DIR = '20261125-r15-j1-lineups'
R15_MANIFEST = '97a3cdc153035f4c1bea4f292cbb5a2cec7351deec2cbf4c92f199ec4f09f243'
R18_ARCHIVE = '16fbb7bd3ee55d01b4f5713237cd0fd909fde61af8fe2fdee6b85b4a51f76201'
R18_RECEIPTS = '0a9de0ba4f2e2b1a4ad63821b1ea335cbbdbecc73a4dd47f1d88d8552132a30a'
R18_REGISTRATION = '9ba2b89ecb7e504ce9eef40701cbf002082c7548df3f06bce458b286852249be'
PROTOCOL_SHA = '1d9e483923e84facc6f674411dc8e25c8543453d9778a671acd9dd1498aa1d30'
PREREGISTRATION = 'bffa6a29e70fa8573cdc0f6f7e19cd2ec8bff71c'
SIDES = ('home', 'away')
INTAKE_FILES = {'matches.jsonl', 'source-index.jsonl', 'late-seven-excluded.jsonl',
                'late-seven-source-index.jsonl', 'coverage.json', 'README.md', 'rebuild.py'}
EXCLUSION = '2026-11-25_seven_late_j1_events_separate_from_2822_historical_training_population'


def read(path):
    return json.loads(path.read_bytes())


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def unique(items, key):
    indexed = {r[key]: r for r in items}
    require(len(items) == len(indexed), ('duplicate identity', key))
    return indexed


def utc(stamp):
    at = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    require(at.tzinfo is not None, ('missing timezone', stamp))
    return at.astimezone(timezone.utc)


def jsonl(row):
    return (json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()


def integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'(0|[1-9]\d*)(\.\d+)?', str(value)):
        return None
    try:
        n = Decimal(value)
        return int(n) if n == n.to_integral_value() else None
    except InvalidOperation:
        return None


def raw_halves(body, mid, kickoff, ids, final):
    """Preserve both ordered linescore cells and their exclusion reasons, including partial invalid rows."""
    doc = json.loads(body)
    header = doc['header']
    game, = header['competitions']
    eid = mid.removeprefix('espn:')
    status = game['status']['type']
    require(header['league']['slug'] == 'jpn.1' and str(header['id']) == str(game['id']) == eid
            and utc(game['date']) == utc(kickoff), ('summary identity', mid))
    require(status['name'] == 'STATUS_FULL_TIME' and status['state'] == 'post' and status['completed'] is True
            and status['detail'] == 'FT' and game['status'].get('period') in (None, 2)
            and not any(e.get('shootout') is True or (e.get('period') or {}).get('number', 0) > 2 for e in doc.get('keyEvents') or []),
            ('regulation full time', mid))
    fmt = doc.get('format') or {}
    reg = fmt.get('regulation') or {}
    require(not fmt.get('overtime') and reg.get('periods') in (None, 2) and reg.get('clock') in (None, 2700),
            ('regulation format', mid))
    sides = unique(game['competitors'], 'homeAway')
    require(set(sides) == set(SIDES), ('ordered competitor pair', mid))
    full, first, second, display, reasons = [], [], [], {}, []
    for i, side in enumerate(SIDES):
        team = sides[side]
        goals = integer(team.get('score'))
        require(str(team['team']['id']) == str(ids[i]) and goals is not None and goals == final[i]
                and team.get('shootoutScore') in (None, '', 0, '0'), ('team or regulation FT', mid, side))
        full.append(goals)
        lines = team.get('linescores')
        display[side] = []
        values = [None, None]
        if not isinstance(lines, list) or len(lines) != 2:
            reasons.append(side + '_linescores_not_exactly_two_periods')
        else:
            for period, cell in enumerate(lines, 1):
                shown = cell.get('displayValue') if isinstance(cell, dict) else None
                display[side].append(shown)
                if not isinstance(cell, dict):
                    reasons.append(f'{side}_period_{period}_not_object')
                    continue
                if cell.get('period', period) != period:
                    reasons.append(f'{side}_period_{period}_label_mismatch')
                values[period - 1] = integer(shown) if isinstance(shown, str) else None
                if values[period - 1] is None:
                    reasons.append(f'{side}_period_{period}_display_value_invalid')
            if None not in values and sum(values) != goals:
                reasons.append(side + '_halves_do_not_sum_to_full')
        first.append(values[0])
        second.append(values[1])
    return full, first, second, display, reasons


def r15_inputs(data, temp):
    """Reuse the audited R15 response and original schedule readers from the pinned data release."""
    pkg = data / 'workspace-updates' / R15_DIR
    require(sha(pkg / 'manifest.json') == R15_MANIFEST, 'original R15 data manifest')
    m = read(pkg / 'manifest.json')
    names = ['baselines.py', 'common.py', 'intake.py', 'starters.py', 'intake.tar.gz', 'extract_v1.py', 'replay/inputs.json']
    for name in names + [n for n in m['files'] if n.startswith('raw/')]:
        require(sha(pkg / name) == m['files'][name], ('R15 archived input', name))
    sys.path.insert(0, str(pkg))
    from baselines import read_baselines
    from common import unpack
    from intake import clock, open_raw, receipt_info
    from starters import rebuild_rows, verify_targets
    inputs = read(pkg / 'replay/inputs.json')
    games, controls = read_baselines(data, inputs)
    meta = temp / 'r15-meta'
    unpack(pkg / 'intake.tar.gz', meta)
    raw, receipts = open_raw(pkg, meta, temp)
    targets = verify_targets(meta, raw, games)
    normalized = rebuild_rows(meta, raw, inputs, pkg / 'extract_v1.py')
    by_sha = unique(rows(meta / 'raw-index.jsonl'), 'sha256')
    captures = {k: {(r['url'], clock(r), receipt_info(r)) for r in group if r['http_status'] == 200} for k, group in receipts.items()}
    return games, controls, raw, targets, rows(normalized), by_sha, captures


def source_manifest(intake):
    manifest = read(intake / 'artifact-manifest.json')
    listed = unique(manifest['files'], 'path')
    require(manifest['schema'] == 'r20-j1-halves-artifacts-v1' and listed.keys() == INTAKE_FILES, 'halves intake inventory')
    for name, ref in listed.items():
        path = intake / name
        require(not path.is_symlink() and path.is_file() and path.stat().st_size == ref['bytes'] and sha(path) == ref['sha256'],
                ('halves intake file or length', name))
    return manifest


def history(data, intake, temp):
    source_manifest(intake)
    games, controls, raw, targets, normalized, raw_index, captures = r15_inputs(data, temp)
    checked = unique(rows(intake / 'source-index.jsonl'), 'match_id')
    require(checked.keys() == games.keys() and len(normalized) == len(games) == 2822, 'whole registered R5 denominator')
    derived = temp / 'raw-derived-halves.jsonl'
    failures, reason_counts, accepted = [], Counter(), Counter()
    with derived.open('xb') as stream:
        for obs in normalized:
            eid = obs['source_match_id']
            mid = 'espn:' + eid
            game, target, source = games[mid], targets[eid], checked[mid]
            key = obs['source_sha256']
            require((obs['source_url'], obs['source_query_time_utc'], ('summary', eid)) in captures[key]
                    and (target['scoreboard_url'], target['scoreboard_query_time_utc'], ('scoreboard', str(target['season'])))
                    in captures[target['scoreboard_sha256']], ('original acquisition receipts', mid))
            ids = [game[side + '_id'] for side in SIDES]
            scores = [game[side + '_goals'] for side in SIDES]
            full, first, second, display, errors = raw_halves(gzip.decompress((raw / (key + '.json.gz')).read_bytes()),
                                                             mid, game['kickoff_at'], ids, scores)
            reason = ';'.join(errors) if errors else None
            row = dict(match_id=mid, home_id=ids[0], away_id=ids[1],
                       kickoff_utc=utc(game['kickoff_at']).isoformat(timespec='seconds').replace('+00:00', 'Z'),
                       full=full, half1=first, half2=second, source_sha256=key, eligible=not errors, reason=reason)
            stream.write(jsonl(row))
            origin = source['raw_origin']
            expected = dict(match_id=mid, competition='jpn.1', r5_registered=True, date_r5=target['date'],
                            date_final_checkpoint=obs['date'], home_id_r5=ids[0], away_id_r5=ids[1],
                            source_summary_url=obs['source_url'], source_query_time_utc=obs['source_query_time_utc'],
                            source_sha256=key, raw_origin=origin, raw_gzip_bytes=raw_index[key]['gzip_bytes'],
                            raw_gzip_member_sha256=raw_index[key]['gzip_sha256'],
                            raw_body_sha256_verified=True, checkpoint_home_goals=[str(g) for g in full],
                            raw_linescore_display_values=display, identity_source_url=target['scoreboard_url'],
                            identity_source_query_time_utc=target['scoreboard_query_time_utc'],
                            identity_source_sha256=target['scoreboard_sha256'], eligible=not errors, reason=reason)
            require(expected == source and origin['kind'] == 'r15_original_evidence_shard'
                    and Path(origin['path']).parts[-3:] == (R15_DIR, 'raw', raw_index[key]['archive'])
                    and origin['member'] == key + '.json.gz', ('source index / shard location', mid))
            if errors:
                failures.append(row)
                reason_counts.update(errors)
            else:
                accepted[game['date'][:4]] += 1
    require(derived.read_bytes() == (intake / 'matches.jsonl').read_bytes(), 'raw-derived ordered training JSONL differs')
    coverage = read(intake / 'coverage.json')
    metadata = temp / 'r15-meta'
    refs = {Path(r['path']).name: r for r in coverage['inputs']}
    originals = [metadata / n for n in ('events.jsonl', 'r5-targets.jsonl', 'snapshot-manifest.json', 'coverage-audit.json')]
    originals.extend(sorted((data / 'workspace-updates' / R15_DIR / 'raw').glob('part-*.tar')))
    require(len(refs) == len(coverage['inputs']) and set(refs) == {p.name for p in originals} | {'final-90-evidence.jsonl'},
            'collector snapshot input inventory')
    for path in originals:
        require(refs[path.name]['sha256'] == sha(path) and refs[path.name]['bytes'] == path.stat().st_size,
                ('original snapshot, target or acquisition shard', path.name))
    require(coverage['source_snapshot_as_of_utc'] == read(metadata / 'snapshot-manifest.json')['snapshot_as_of_utc']
            and all(coverage[k] == len(games) for k in ('ft90_confirmed_rows', 'r5_membership_verified_rows',
                           'r5_date_and_side_identity_match_rows', 'raw_summary_sha256_verified_rows')),
            'historical capture clock or registered population')
    require((coverage['rows'], coverage['unique_match_ids'], coverage['eligible'], coverage['ineligible']) ==
            (len(games), len(checked), sum(accepted.values()), len(failures))
            and dict(reason_counts) == coverage['failure_reason_event_counts'], 'collector coverage or reasons differ')
    return derived, games, controls, failures


def excluded(intake, r18_root, plan, late_receipts):
    """Recheck the seven exclusions against the original R18-certified summary bodies."""
    events = plan['payload']['identity']['evidence']['events']
    claims = unique(rows(intake / 'late-seven-excluded.jsonl'), 'match_id')
    index = unique(rows(intake / 'late-seven-source-index.jsonl'), 'match_id')
    original_ref, = (r for r in read(intake / 'coverage.json')['inputs'] if Path(r['path']).name == 'final-90-evidence.jsonl')
    require(len(late_receipts) == original_ref['bytes'] and checksum(late_receipts) == original_ref['sha256'],
            'original late acquisition index')
    late = unique([r for r in map(json.loads, late_receipts.splitlines()) if r['league_slug'] == 'jpn.1'], 'event_id')
    require(len(claims) == 7 and claims.keys() == index.keys() == events.keys(), 'registered seven late fixtures')
    require(not (claims.keys() & {r['match_id'] for r in rows(intake / 'matches.jsonl')}), 'late game in training')
    for mid, event in events.items():
        item, row, ref = index[mid], claims[mid], event['espn']
        require(event['verdict'] == 'official_and_espn_ft_agree' and ref['identity_verified'] is True,
                ('retained original R18 certification', mid))
        body = (r18_root / 'objects' / ref['sha256']).read_bytes()
        require(checksum(body) == ref['sha256'], ('original late raw body', mid))
        ids = [event['fixture'][s].removeprefix('espn:') for s in SIDES]
        receipt = late[mid.removeprefix('espn:')]
        require((receipt['espn_summary_url'], receipt['espn_summary_raw_path'], receipt['espn_summary_raw_sha256'],
                 receipt['espn_summary_capture_time_utc']) == (ref['url'], ref['file'], ref['sha256'], ref['query_time']),
                ('November 25 final source receipt', mid))
        full, first, second, display, errors = raw_halves(body, mid, event['fixture']['kickoff_at'], ids, event['score'])
        reason = ';'.join([EXCLUSION, *errors])
        require((row['home_id'], row['away_id']) == tuple(ids) and utc(row['kickoff_utc']) == utc(event['fixture']['kickoff_at'])
                and (row['full'], row['half1'], row['half2'], row['source_sha256'], row['eligible'], row['reason'])
                == (full, first, second, ref['sha256'], False, reason), ('excluded late record', mid))
        require((item['full'], item['half1'], item['half2'], item['source_sha256'], item['source_url'], item['capture_time_utc'],
                 item['raw_linescore_display_values'], item['eligible'], item['reason'])
                == (full, first, second, ref['sha256'], ref['url'], ref['query_time'], display, False, reason)
                and Path(item['source_path']).as_posix().endswith('/' + ref['file']), ('late raw index', mid))
    return len(claims)
