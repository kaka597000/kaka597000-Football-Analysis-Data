"""Recover the exact training rows and independently derive each side's starter IDs from ESPN bytes."""
from collections import Counter, defaultdict
import gzip
import json
import os
import shutil
import subprocess
import sys

from baselines import board_events, fixture
from common import ARCHIVES, IDS_SHA, NUMERICAL_ENV, PANEL_SHA, SIDES, digest, fold, read, require, rows, sha, unique, utc
from intake import EXTRACT_SHA, FINAL_EXTRACT_SHA, clock, receipt_hash, receipt_info

POSITIONS = {'G': 'G', 'GK': 'G', 'GOALKEEPER': 'G', 'D': 'D', 'DEFENDER': 'D',
             'M': 'M', 'MIDFIELDER': 'M', 'F': 'F', 'FORWARD': 'F'}


def raw_json(raw, key):
    return json.loads(gzip.decompress((raw / (key + '.json.gz')).read_bytes()))


def verify_captures(meta, raw, targets, captures):
    """Check the collector's HTTP-200 parsing receipts, including captures outside the training snapshot."""
    as_of = utc(read(meta / 'snapshot-manifest.json')['snapshot_as_of_utc'])
    for key, receipts in captures.items():
        for r in receipts:
            kind, token = receipt_info(r)
            require(utc(clock(r)) <= as_of, ('receipt after snapshot', r['url']))
            if kind == 'summary' and 'source_match_id' in r:
                # Repeat-capture receipts record the kickoff in event_date. The response date is checked below.
                kickoff = r.get('date')
                if 'date' not in r and (r.get('fresh_recheck') is True or r.get('recovery_attempt_after_503') is True):
                    kickoff = r.get('event_date')
                require(kickoff == targets[token]['date'], ('request target date', token))
            if r['http_status'] != 200:
                continue
            if kind == 'scoreboard' and 'events' in r:
                board = raw_json(raw, key)
                events = [dict(id=e['id'], date=e['date'], name=e['name'], status=e['status']['type']['state'])
                          for e in board['events']]
                require([v['slug'] for v in board['leagues']] == ['jpn.1'] and events == r['events']
                        and len(events) == r['event_count'], ('pilot schedule evidence', token))
            if kind != 'summary':
                continue
            try:
                d = raw_json(raw, key)
                header = d['header']
                match = header['competitions'][0]
            except (KeyError, IndexError, ValueError, TypeError):
                require(r.get('parse_error') is True or r.get('identity_match') is False, ('unparsed receipt', token))
                continue
            if 'verified_event_id' in r:
                actual = str(header['id'])
                require((r['verified_event_id'], r['event_date'], r['lineup_sides'], r['identity_match'])
                        == (actual, match['date'], len(d.get('rosters') or []),
                            actual == token and match['date'] == targets[token]['date']), ('summary checkpoint', token))
                if 'scoreboard_identity_match' in r:
                    observed = fixture(header)
                    fields = ('date', 'home_id', 'away_id', 'home_goals', 'away_goals')
                    matches = actual == token and all(observed[k] == targets[token][k] for k in fields)
                    require(r['scoreboard_identity_match'] is matches and targets[token]['membership_verified'] is True,
                            ('repeat capture scoreboard identity', token))
                    if r.get('recovery_attempt_after_503') is True:
                        blocks = unique(d.get('rosters', []), 'homeAway')
                        audit = {}
                        for side in SIDES:
                            roster = blocks[side]['roster']
                            starters = [p for p in roster if p.get('starter') is True]
                            audit[side] = dict(roster_count=len(roster), starter_count=len(starters),
                                               starter_ids_complete=all((p.get('athlete') or {}).get('id') for p in starters),
                                               starter_positions_complete=all(p.get('position') for p in starters))
                        qualifies = matches and observed['status'] == 'STATUS_FULL_TIME' and all(
                            v['starter_count'] == 11 and v['starter_ids_complete'] and v['starter_positions_complete']
                            for v in audit.values())
                        require(r['lineup_sides_audit'] == audit and r['qualifies'] is qualifies, ('recovery audit', token))
                    else:
                        require(r['r5_membership_verified'] is True and r['status'] == observed['status'],
                                ('repeat capture status', token))
            else:
                teams = [dict(team_id=str(c['team']['id']), name=c['team']['displayName'],
                              side=c['homeAway'], score=c['score']) for c in match['competitors']]
                require((str(header['id']), match['date'], match['status']['type']['state'], teams)
                        == (token, r['date'], r['status'], r['competitors']), ('pilot summary', token))


def verify_targets(meta, raw, games):
    annual = {}
    receipts = rows(meta / 'sources/scoreboard-index.jsonl')
    require(sorted(r['season'] for r in receipts) == list(range(2018, 2027)), 'annual scoreboard seasons')
    for r in receipts:
        key = receipt_hash(r)
        require(receipt_info(r) == ('scoreboard', str(r['season'])) and r['http_status'] == 200, 'annual receipt')
        events = board_events(gzip.decompress((raw / (key+'.json.gz')).read_bytes()))
        require(len(events) == r['event_count'], ('scoreboard event count', key))
        for eid, e in events.items():
            require(eid not in annual, ('duplicate annual fixture', eid))
            annual[eid] = dict(fixture(e), competition='jpn.1', season=r['season'], source_match_id=eid,
                               scoreboard_url=r['url'], scoreboard_sha256=key, scoreboard_raw_gzip=r['raw_gzip'],
                               scoreboard_query_time_utc=clock(r))
    require(annual == unique(rows(meta / 'targets.jsonl'), 'source_match_id'), 'annual index differs from raw')
    panel = {g['id'].removeprefix('espn:'): g for g in games.values()}
    extra = {k: v for k, v in annual.items() if k not in panel}
    require(len(extra) == 249 and extra == unique(rows(meta / 'annual-source-only-extras.jsonl'), 'source_match_id'),
            'annual-only fixtures')
    targets = unique(rows(meta / 'r5-targets.jsonl'), 'source_match_id')
    require(targets.keys() == panel.keys() and sha(meta / 'r5-target-ids.txt') == IDS_SHA, 'R5 intake population')
    for eid, g in panel.items():
        a = annual[eid]
        require(a['status'] == 'STATUS_FULL_TIME' and a['completed'] is True and utc(a['date']) == utc(g['kickoff_at'])
                and all(a[s] == g[s] and a[s+'_id'] == g[s+'_id'] and a[s+'_goals'] == str(g[s+'_goals']) for s in SIDES),
                ('R5 / annual scoreboard identity', eid))
        require(targets[eid] == dict(a, panel_id=g['id'], panel_date=g['date'], panel_home=g['home'],
                                     panel_away=g['away'], membership_verified=True), ('intake target', eid))
    recon = read(meta / 'r5-reconciliation.json')
    require((recon['fixed_package_sha256'], recon['panel_member_sha256'], recon['panel_id_list_sha256'],
             recon['panel_rows'], recon['r5_ids_matching_annual_scoreboard'], recon['annual_scoreboard_ids'],
             recon['annual_source_only_extras'], recon['identity_mismatches'], recon['r5_ids_absent_from_annual_scoreboard'])
            == (ARCHIVES['r5'][2], PANEL_SHA, IDS_SHA, len(panel), len(panel), len(annual), len(extra), 0, []),
            'intake reconciliation')
    audit = read(meta / 'coverage-audit.json')
    counts = dict(Counter(g['date'][:4] for g in games.values()))
    require(recon['r5_panel_year_counts'] == audit['historical_target_ids_by_year'] == counts
            and len(annual) == audit['scoreboard_target_rows']
            and len(panel) == audit['scoreboard_historical_completed_through_2026-11-21'], 'intake calendar counts')
    return targets


def rebuild_rows(meta, raw, inputs, extractor):
    manifest = read(meta / 'snapshot-manifest.json')
    a = read(meta / 'coverage-audit.json')
    require(manifest['schema'] == 'j1-lineups-history-intake-snapshot-v1'
            and sha(meta / 'snapshot-manifest.json') == inputs['roster_manifest_sha256']
            and sha(meta / 'coverage-audit.json') == manifest['coverage_audit_sha256']
            and manifest['snapshot_as_of_utc'] == inputs['roster_snapshot_at'] == a['report_as_of_utc']
            and manifest['r5_panel_package_sha256'] == ARCHIVES['r5'][2]
            and manifest['r5_panel_member_sha256'] == PANEL_SHA
            and len(rows(meta / 'checkpoint.jsonl')) == a['summary_checkpoint_lines'], 'snapshot or audit binding')
    index = rows(meta / 'event-index.jsonl')
    keys = unique(index, 'source_sha256')
    record = read(meta / 'extractor.json')
    require(sha(extractor) == EXTRACT_SHA, 'version-1 offline extractor')
    observed = meta / 'observed-extract.py'
    if record['observed_sha256'] != EXTRACT_SHA:
        require(sha(observed) == record['observed_sha256'], 'collector script receipt')
    if manifest.get('all_target_ids_attempted') is True:
        require(record['replay_extractor_sha256'] == record['observed_sha256'] == FINAL_EXTRACT_SHA,
                'final checkpoint extractor checksum')
        extractor = observed
        selected = raw
    else:
        require(record['replay_extractor_sha256'] == EXTRACT_SHA, 'early checkpoint extractor checksum')
        selected = meta / 'training-bodies'
        selected.mkdir()
        for key in keys:
            os.link(raw / (key + '.json.gz'), selected / (key + '.json.gz'))
    shutil.copyfile(extractor, meta / 'extract.py')
    output = meta / 'regenerated.jsonl'
    subprocess.run([sys.executable, '-I', '-B', str(meta / 'extract.py'), '--raw-dir', str(selected),
                    '--out', str(output)], env=os.environ | NUMERICAL_ENV, check=True, stdout=subprocess.DEVNULL)
    # The extractor iterates a directory. Preserve the actual snapshot order for equal date/ID variants.
    with output.open('rb') as stream:
        bodies = {}
        for line in stream:
            key = json.loads(line)['source_sha256']
            require(key not in bodies, ('duplicate rebuilt response', key))
            bodies[key] = line
    require(bodies.keys() == keys.keys(), 'raw-derived event inventory')
    path = meta / 'events.jsonl'
    with path.open('xb') as stream:
        for r in index:
            line = bodies[r['source_sha256']]
            require(digest(line) == r['row_sha256'] and json.loads(line)['source_match_id'] == r['source_match_id'],
                    ('raw-derived event row', r['source_match_id']))
            stream.write(line)
    require(sha(path) == inputs['rosters_sha256'] == manifest['events_jsonl_sha256']
            and len(index) == manifest['events_jsonl_rows'] == inputs['roster_rows']
            and len({r['source_match_id'] for r in index}) == manifest['unique_source_match_ids']
            == a['unique_extracted_summary_events'], 'exact training bytes or row counts')
    return path


def raw_starters(blocks, side, team):
    choices = [r for r in blocks if r.get('homeAway') == side]
    if len(choices) != 1:
        return None, 'missing_or_ambiguous_roster_side', 0
    roster, = choices
    team_blocks = [b for b in blocks if str((b.get('team') or {}).get('id')) == team]
    if len(team_blocks) != 1 or team_blocks[0] is not roster:
        # Without a block belonging uniquely to both this team and this side, it has no verified starters.
        return None, 'not_eleven_explicit_starters', 0
    selected = [p for p in roster.get('roster', []) if p.get('starter') is True
                or isinstance(p.get('starter'), str) and p['starter'].casefold() == 'true']
    n = len(selected)
    if n != 11:
        return None, 'not_eleven_explicit_starters', n
    result = {}
    for p in selected:
        athlete = p.get('athlete') or {}
        pid = athlete.get('id')
        if type(pid) not in (str, int) or not str(pid).strip() or str(pid).strip() in result:
            return None, 'missing_or_duplicate_player_id', n
        position = p.get('position') or athlete.get('position') or {}
        tokens = (position.get('displayName') or position.get('name'), position.get('abbreviation'))
        values = {POSITIONS[str(t).strip().upper()] for t in tokens if str(t).strip().upper() in POSITIONS}
        if len(values) != 1:
            return None, 'unknown_or_ambiguous_position', n
        result[str(pid).strip()] = values.pop()
    return [dict(id=k, position=v) for k, v in sorted(result.items())], 'complete', n


def raw_result(d, target, r, capture):
    key, eid = r['source_sha256'], target['source_match_id']
    require(any(receipt_info(c) == ('summary', eid) and c['http_status'] == 200 and c['url'] == r['source_url']
                and clock(c) == r['source_query_time_utc'] for c in capture[key]), ('summary source identity', eid, key))
    require((r['identity_source_sha256'], r['identity_source_url'], r['identity_source_query_time_utc'])
            == tuple(target['scoreboard_' + k] for k in ('sha256', 'url', 'query_time_utc')),
            ('scoreboard provenance', eid))
    header = d.get('header', {})
    matches = header.get('competitions', [])
    if len(matches) != 1 or header.get('league', {}).get('slug') != 'jpn.1' or str(header.get('id')) != eid:
        return None
    match, = matches
    status = match.get('status', {})
    state = status.get('type', {})
    fmt = d.get('format') or {}
    reg = fmt.get('regulation') or {}
    events = d.get('keyEvents') or []
    if (str(match.get('id')) != eid or match.get('date') != target['date'] or state.get('name') != 'STATUS_FULL_TIME'
            or state.get('state') != 'post' or state.get('completed') is not True or status.get('period') not in (None, 2)
            or reg.get('periods') not in (None, 2) or reg.get('clock') not in (None, 2700) or fmt.get('overtime')
            or any((e.get('period') or {}).get('number', 0) > 2 or e.get('shootout') is True for e in events)):
        return None
    sides = match.get('competitors', [])
    if len(sides) != 2 or {s.get('homeAway') for s in sides} != set(SIDES):
        return None
    for s in sides:
        side = s['homeAway']
        if str(s['team'].get('id')) != target[side+'_id'] or str(s.get('score')) != target[side+'_goals']:
            return None
    return {side: raw_starters(d.get('rosters') or [], side, target[side+'_id']) for side in SIDES}


def normalize(meta, raw, capture, games, inputs, extractor):
    targets = verify_targets(meta, raw, games)
    verify_captures(meta, raw, targets, capture)
    training = rebuild_rows(meta, raw, inputs, extractor)
    grouped = defaultdict(list)
    audit = read(meta / 'coverage-audit.json')
    tally = dict.fromkeys(audit['field_coverage_counts_among_extracted_rows'], 0)
    years = Counter()
    for r in rows(training):
        eid = r['source_match_id']
        require(eid in targets, ('training row outside the registered panel', eid))
        result = raw_result(raw_json(raw, r['source_sha256']), targets[eid], r, capture)
        grouped[eid].append((r, result))
        if r['identity_match'] is True:
            years[r['date'][:4]] += 1
        flags = dict(finished_event_status=r['regulation_final_status'], two_competitor_sides_unique=not r['duplicate_or_missing_sides'],
                     home_and_away_11_starters=all(r[s+'_lineup_audit']['starter_count']==11 for s in SIDES),
                     home_and_away_starter_ids_complete=all(r[s+'_lineup_audit']['starter_player_id_complete'] for s in SIDES),
                     home_and_away_starter_positions_complete=all(r[s+'_lineup_audit']['starter_positions_complete'] for s in SIDES),
                     event_date_home_away_ids_and_scores_match_scoreboard=r['identity_match'],
                     r5_membership_verified=r['r5_membership_verified'],
                     with_source_url_sha_and_query_time=all(r['source_'+k] for k in ('url','sha256','query_time_utc')),
                     with_scoreboard_verification_url_sha_and_query_time=all(r['identity_source_'+k] for k in ('url','sha256','query_time_utc')),
                     post_match_evidence_flagged=r['lineup_is_post_match_evidence'], extra_time_explicitly_indicated=r['extra_time_indicated'],
                     shootout_explicitly_indicated=r['shootout_indicated'])
        for k,v in flags.items():
            tally[k] += bool(v)
    require(dict(years) == audit['identity_verified_summary_rows_by_year']
            and tally == audit['field_coverage_counts_among_extracted_rows'], 'raw-derived acquisition coverage counts')
    attempts = defaultdict(list)
    for key, receipts in capture.items():
        for c in receipts:
            kind, token = receipt_info(c)
            if kind == 'summary':
                require(token in targets, ('summary request outside R5', token))
                attempts[token].append(dict(sha256=key, http_status=c['http_status'], query_time_utc=clock(c)))
    slots = []
    for g in sorted(games.values(), key=lambda v: (v['date'], v['id'])):
        eid = g['id'].removeprefix('espn:')
        reports = grouped[eid]
        valid = [(r, result) for r, result in reports if result is not None]
        audit = dict(source_rows=len(reports), rejected_rows=len(reports)-len(valid),
                     source_sha256=sorted(r['source_sha256'] for r, _ in valid),
                     sources=[{k: r[k] for k in ('source_sha256', 'source_url', 'source_query_time_utc',
                                                 'identity_source_sha256')} for r, _ in reports])
        sides = {}
        for side in SIDES:
            options = [v[side] for _, v in valid]
            players, status, n = options[0] if options else (None, 'identity_mismatch' if reports else 'missing_event', 0)
            if any(q != options[0] for q in options[1:]):
                players, status = None, 'conflicting_sources'
            sides[side + '_starters'] = players
            audit[side] = dict(status=status, explicit_starters=n,
                               attack=sum(p['position'] in ('M', 'F') for p in players or []),
                               defence=sum(p['position'] in ('G', 'D') for p in players or []))
        if {p['id'] for p in sides['home_starters'] or []} & {p['id'] for p in sides['away_starters'] or []}:
            for side in SIDES:
                sides[side+'_starters'] = None
                audit[side].update(status='player_on_both_sides', attack=0, defence=0)
        captured = sorted(attempts[eid], key=lambda x: (x['query_time_utc'], x['sha256']))
        acquisition = 'in_training_snapshot' if reports else 'attempted_without_snapshot_row' if captured else 'no_capture'
        slots.append(dict(match_id=g['id'], date=g['date'], fold=fold(g['date']), home_id=g['home_id'],
                          away_id=g['away_id'], acquisition=acquisition, receipts=captured, source=audit, **sides))
    return training, slots
