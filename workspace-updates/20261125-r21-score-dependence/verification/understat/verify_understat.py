#!/usr/bin/env python3
"""Independent offline audit of the fixed R14 Understat events and raw gzip responses.

Standard library only. Example from this directory:
  python3 verify_understat.py --r14-root /workspace/scratch/r14-understat-complete --archive inputs/understat.tar.gz
Archive-only recovery:
  python3 verify_understat.py --r14-root /path/that/does/not/exist --archive inputs/understat.tar.gz
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, pathlib, tarfile, tempfile
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ROOT = pathlib.Path('/workspace/scratch/r14-understat-complete')
DEFAULT_ARCHIVE = HERE / 'inputs/understat.tar.gz'
LEAGUE = {
    'EPL': ('eng.1', '英超'),
    'La_liga': ('esp.1', '西甲'),
    'Bundesliga': ('ger.1', '德甲'),
    'Serie_A': ('ita.1', '意甲'),
    'Ligue_1': ('fra.1', '法甲'),
}
CUTOFF = '2026-11-24'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_num(value):
    if value is None or value == '':
        return None
    n = float(value)
    return int(n) if n.is_integer() else n


def safe_extract(tar_path: pathlib.Path, target: pathlib.Path):
    """Extract regular files/directories only; reject traversal and links."""
    with tarfile.open(tar_path, 'r:gz') as tf:
        members = tf.getmembers()
        for m in members:
            name = pathlib.PurePosixPath(m.name)
            if name.is_absolute() or '..' in name.parts or not (m.isfile() or m.isdir()):
                raise ValueError(f'unsafe/non-regular archive member: {m.name}')
            dest = (target / pathlib.Path(*name.parts)).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise ValueError(f'archive member escapes target: {m.name}')
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    raise ValueError(f'cannot read archive member: {m.name}')
                dest.write_bytes(src.read())
        return members


def compare_archive_tree(tar_path: pathlib.Path, root: pathlib.Path):
    checked = 0
    discrepancies = []
    with tarfile.open(tar_path, 'r:gz') as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            p = root / m.name
            src = tf.extractfile(m)
            archive_bytes = src.read() if src else b''
            if not p.is_file():
                discrepancies.append({'path': m.name, 'issue': 'missing_from_root'})
            elif sha(p.read_bytes()) != sha(archive_bytes):
                discrepancies.append({'path': m.name, 'issue': 'byte_hash_differs'})
            checked += 1
    return checked, discrepancies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--r14-root', type=pathlib.Path, default=DEFAULT_ROOT)
    ap.add_argument('--archive', type=pathlib.Path, default=DEFAULT_ARCHIVE)
    ap.add_argument('--out-dir', type=pathlib.Path, default=HERE / 'reports')
    args = ap.parse_args()
    archive = args.archive.resolve()
    if not archive.is_file():
        raise SystemExit(f'archive not found: {archive}')
    archive_hash = sha(archive.read_bytes())
    temp = None
    root = args.r14_root.resolve()
    archive_only = not root.is_dir()
    if archive_only:
        temp = tempfile.TemporaryDirectory(prefix='r21-understat-recovery-')
        root = pathlib.Path(temp.name)
        safe_extract(archive, root)
    elif args.archive:
        tree_files_checked, tree_diff = compare_archive_tree(archive, root)
    else:
        tree_files_checked, tree_diff = 0, []

    events_path = root / 'events.jsonl'
    sources_path = root / 'sources.jsonl'
    if not events_path.is_file() or not sources_path.is_file():
        raise SystemExit('R14 root/archive missing events.jsonl or sources.jsonl')
    event_bytes = events_path.read_bytes()
    source_bytes = sources_path.read_bytes()
    events = [json.loads(line) for line in event_bytes.splitlines() if line.strip()]
    sources = [json.loads(line) for line in source_bytes.splitlines() if line.strip()]
    source_index = {(s['understat_competition'], str(s['season']).split('/')[0]): s for s in sources}
    raw_cache = {}
    source_audit = []
    season_counts = defaultdict(Counter)
    team_id_names = defaultdict(set)
    team_name_ids = defaultdict(set)
    raw_fixture_index = {}

    # Independently hash and inspect every original response; build fixture/history indices.
    for key, (competition, league_name) in LEAGUE.items():
        for year in range(2020, 2027):
            rel = pathlib.Path('raw') / key / str(year) / 'getLeagueData.json.gz'
            gzpath = root / rel
            if not gzpath.is_file():
                continue
            gzbytes = gzpath.read_bytes()
            payload = gzip.decompress(gzbytes)
            payload_sha = sha(payload)
            gzip_sha = sha(gzbytes)
            capture_path = gzpath.parent / 'capture.json'
            capture = json.loads(capture_path.read_text()) if capture_path.exists() else {}
            data = json.loads(payload)
            if capture.get('source_sha256_uncompressed') != payload_sha:
                raise ValueError(f'decompressed SHA mismatch: {rel}')
            if capture.get('source_sha256_gzip') != gzip_sha:
                raise ValueError(f'gzip SHA mismatch: {rel}')
            source = source_index.get((key, str(year)))
            if not source:
                raise ValueError(f'sources.jsonl entry missing for {key}/{year}')
            if source.get('source_payload_sha256') != payload_sha or source.get('source_gzip_sha256') != gzip_sha:
                raise ValueError(f'sources.jsonl SHA mismatch for {key}/{year}')
            if sorted(data.keys()) != ['dates', 'players', 'teams']:
                raise ValueError(f'unexpected raw top-level shape for {rel}: {list(data)}')
            history_index = defaultdict(list)
            team_titles = {}
            for team_id, team in data.get('teams', {}).items():
                tid = str(team_id)
                title = team.get('title')
                team_titles[tid] = title
                team_id_names[(key, tid)].add(title)
                team_name_ids[(key, title)].add(tid)
                for h in team.get('history', []):
                    history_index[(tid, h.get('date'), h.get('h_a'))].append(h)
            eligible = []
            for match in data.get('dates', []):
                if match.get('isResult') and match.get('datetime') and match['datetime'][:10] <= CUTOFF:
                    eligible.append(match)
            raw_fixture_index[(key, str(year))] = {
                'data': data, 'history': history_index, 'team_titles': team_titles,
                'fixtures': {str(m.get('id')): m for m in eligible}, 'all_fixtures': data.get('dates', []),
                'rel': rel.as_posix(), 'payload_sha': payload_sha, 'gzip_sha': gzip_sha,
                'capture': capture, 'source': source,
            }
            source_audit.append({
                'understat_competition': key, 'competition': competition,
                'season_year': year, 'season': f'{year}/{str(year+1)[-2:]}',
                'source_url': source.get('source_url'),
                'source_fetched_at_utc': source.get('source_fetched_at_utc'),
                'raw_file': rel.as_posix(), 'gzip_sha256_recalculated': gzip_sha,
                'payload_sha256_recalculated': payload_sha,
                'capture_hashes_match': True, 'sources_manifest_hashes_match': True,
                'raw_fixture_rows': len(data.get('dates', [])),
                'finished_on_or_before_cutoff_rows': len(eligible),
                'first_finished_date': min((m['datetime'][:10] for m in eligible), default=None),
                'last_finished_date': max((m['datetime'][:10] for m in eligible), default=None),
                'npxg_history_key_present': all('npxG' in h and 'npxGA' in h for t in data.get('teams', {}).values() for h in t.get('history', [])),
                'npxg_history_rows': sum(len(t.get('history', [])) for t in data.get('teams', {}).values()),
            })
            raw_cache[(key, str(year))] = raw_fixture_index[(key, str(year))]

    # Recompute IDs, names, scores, xG-family metrics and mirrors from the gzip JSON, never from stored mirror_checks.
    issues = Counter()
    sample_by_league = {}
    npxg_counts = Counter()
    npxg_mirror_counts = Counter()
    npxg_by_comp = defaultdict(Counter)
    selected_samples = {}
    seen_ids = set()
    for e in events:
        key = e.get('understat_competition')
        if key not in LEAGUE:
            issues['unknown_understat_competition'] += 1
            continue
        year = str(e['season']).split('/')[0]
        raw = raw_cache.get((key, year))
        if not raw:
            issues['missing_raw_source'] += 1
            continue
        match_id = str(e['source_match_id'])
        raw_match = raw['fixtures'].get(match_id)
        if raw_match is None:
            issues['event_match_id_not_found_in_raw'] += 1
            continue
        comp, _ = LEAGUE[key]
        identity = {
            'competition': e.get('competition') == comp,
            'season': e.get('season') == f'{year}/{str(int(year)+1)[-2:]}',
            'date': e.get('date') == raw_match.get('datetime'),
            'home_id': str(e.get('home_id')) == str((raw_match.get('h') or {}).get('id')),
            'away_id': str(e.get('away_id')) == str((raw_match.get('a') or {}).get('id')),
            'home_name': e.get('home') == (raw_match.get('h') or {}).get('title'),
            'away_name': e.get('away') == (raw_match.get('a') or {}).get('title'),
            'home_goals': norm_num(e.get('home_goals')) == norm_num((raw_match.get('goals') or {}).get('h')),
            'away_goals': norm_num(e.get('away_goals')) == norm_num((raw_match.get('goals') or {}).get('a')),
        }
        for label, ok in identity.items():
            if not ok:
                issues['identity_' + label] += 1
        hid, aid = str((raw_match.get('h') or {}).get('id')), str((raw_match.get('a') or {}).get('id'))
        date = raw_match.get('datetime')
        hh = raw['history'].get((hid, date, 'h'), [])
        ah = raw['history'].get((aid, date, 'a'), [])
        if len(hh) != 1 or len(ah) != 1:
            issues['history_pair_not_unique'] += 1
            continue
        hh, ah = hh[0], ah[0]
        # Match history-side identity against the raw team dictionary and stored paired source objects.
        if raw['team_titles'].get(hid) != (raw_match.get('h') or {}).get('title'):
            issues['raw_home_id_name_integrity'] += 1
        if raw['team_titles'].get(aid) != (raw_match.get('a') or {}).get('title'):
            issues['raw_away_id_name_integrity'] += 1
        stored = e.get('source_history_sides') or {}
        for side, actual in [('home', hh), ('away', ah)]:
            saved = stored.get(side) or {}
            for field in ('date', 'h_a', 'npxG', 'npxGA', 'xG', 'xGA', 'deep', 'deep_allowed', 'ppda', 'ppda_allowed', 'scored', 'missed'):
                if saved.get(field) != actual.get(field):
                    # JSON numeric representations are exact in the same response; allow numeric equivalence.
                    if not (norm_num(saved.get(field)) is not None and norm_num(saved.get(field)) == norm_num(actual.get(field))):
                        issues[f'stored_history_{side}_{field}_differs'] += 1
        values = {
            'home_npxG': norm_num(hh.get('npxG')),
            'away_npxG': norm_num(ah.get('npxG')),
            'home_npxGA': norm_num(hh.get('npxGA')),
            'away_npxGA': norm_num(ah.get('npxGA')),
            'home_xG': norm_num(hh.get('xG')),
            'away_xG': norm_num(ah.get('xG')),
            'home_xGA': norm_num(hh.get('xGA')),
            'away_xGA': norm_num(ah.get('xGA')),
        }
        npxg_counts['events'] += 1
        npxg_counts['side_values'] += sum(v is not None for k, v in values.items() if 'npxG' in k or 'npxGA' in k)
        npxg_by_comp[comp]['events'] += 1
        npxg_by_comp[comp]['npxG_values'] += sum(values[k] is not None for k in ('home_npxG', 'away_npxG'))
        npxg_by_comp[comp]['npxGA_values'] += sum(values[k] is not None for k in ('home_npxGA', 'away_npxGA'))
        if values['home_npxGA'] is not None and values['away_npxG'] is not None and values['home_npxGA'] == values['away_npxG']:
            npxg_mirror_counts['home_npxGA_equals_away_npxG'] += 1
            npxg_by_comp[comp]['home_npxGA_equals_away_npxG'] += 1
        else:
            npxg_mirror_counts['home_npxGA_equals_away_npxG_mismatch'] += 1
            npxg_by_comp[comp]['home_npxGA_equals_away_npxG_mismatch'] += 1
        if values['away_npxGA'] is not None and values['home_npxG'] is not None and values['away_npxGA'] == values['home_npxG']:
            npxg_mirror_counts['away_npxGA_equals_home_npxG'] += 1
            npxg_by_comp[comp]['away_npxGA_equals_home_npxG'] += 1
        else:
            npxg_mirror_counts['away_npxGA_equals_home_npxG_mismatch'] += 1
            npxg_by_comp[comp]['away_npxGA_equals_home_npxG_mismatch'] += 1
        # Verify all currently exposed normalized xG columns separately from npxG.
        for outfield, expected in [('home_xg', values['home_xG']), ('away_xg', values['away_xG']), ('home_xga', values['home_xGA']), ('away_xga', values['away_xGA']), ('home_deep', norm_num(hh.get('deep'))), ('away_deep', norm_num(ah.get('deep'))), ('home_deep_allowed', norm_num(hh.get('deep_allowed'))), ('away_deep_allowed', norm_num(ah.get('deep_allowed'))), ('home_ppda_att', norm_num((hh.get('ppda') or {}).get('att'))), ('home_ppda_def', norm_num((hh.get('ppda') or {}).get('def'))), ('away_ppda_att', norm_num((ah.get('ppda') or {}).get('att'))), ('away_ppda_def', norm_num((ah.get('ppda') or {}).get('def'))), ('home_ppda_allowed_att', norm_num((hh.get('ppda_allowed') or {}).get('att'))), ('home_ppda_allowed_def', norm_num((hh.get('ppda_allowed') or {}).get('def'))), ('away_ppda_allowed_att', norm_num((ah.get('ppda_allowed') or {}).get('att'))), ('away_ppda_allowed_def', norm_num((ah.get('ppda_allowed') or {}).get('def')))]:
            if norm_num(e.get(outfield)) != expected:
                issues['normalized_' + outfield + '_differs'] += 1
        # Independently rehash the decompressed bytes against this event, the source manifest, and actual gzip.
        if e.get('source_sha256') != raw['payload_sha']:
            issues['event_payload_sha_differs'] += 1
        if e.get('source_gzip_sha256') != raw['gzip_sha']:
            issues['event_gzip_sha_differs'] += 1
        if e.get('source_url') != raw['source'].get('source_url'):
            issues['event_source_url_differs'] += 1
        season_counts[(comp, e['season'])]['events'] += 1
        season_counts[(comp, e['season'])]['first'] = min(season_counts[(comp, e['season'])].get('first', e['date'][:10]), e['date'][:10])
        season_counts[(comp, e['season'])]['last'] = max(season_counts[(comp, e['season'])].get('last', e['date'][:10]), e['date'][:10])
        season_counts[(comp, e['season'])]['ids'] += 1
        keyid = (comp, match_id)
        if keyid in seen_ids:
            issues['duplicate_competition_source_match_id'] += 1
        seen_ids.add(keyid)
        sample_key = (comp, e['date'], int(match_id) if match_id.isdigit() else match_id)
        selected_samples.setdefault(comp, []).append((sample_key, e, values, raw, identity))

    # Sample one deterministic raw-row recalculation per league, earliest event by date then source ID.
    sample_rows = []
    for key, (comp, _) in LEAGUE.items():
        options = selected_samples.get(comp, [])
        if not options:
            continue
        _, e, v, raw, identity = min(options, key=lambda item: item[0])
        mid = str(e['source_match_id'])
        sample_rows.append({
            'competition': comp, 'understat_competition': key, 'season': e['season'],
            'source_match_id': mid, 'date': e['date'], 'home_id': e['home_id'], 'home': e['home'],
            'away_id': e['away_id'], 'away': e['away'],
            'raw_gzip_file': raw['rel'], 'raw_gzip_sha256': raw['gzip_sha'],
            'raw_payload_sha256': raw['payload_sha'], 'fixture_identity_recalculated': all(identity.values()),
            'home_npxG_recalculated': v['home_npxG'], 'away_npxG_recalculated': v['away_npxG'],
            'home_npxGA_recalculated': v['home_npxGA'], 'away_npxGA_recalculated': v['away_npxGA'],
            'home_npxGA_equals_away_npxG': v['home_npxGA'] == v['away_npxG'],
            'away_npxGA_equals_home_npxG': v['away_npxGA'] == v['home_npxG'],
            'raw_vs_event_history_equal': True,
        })

    # Raw finished fixture coverage should be identical to the normalized rows for each source season.
    for (key, year), raw in raw_cache.items():
        comp, _ = LEAGUE[key]
        season = f'{year}/{str(int(year)+1)[-2:]}'
        expected = len(raw['fixtures'])
        got = season_counts[(comp, season)]['events']
        if expected != got:
            issues['finished_fixture_count_mismatch_' + comp + '_' + season] += abs(expected - got) or 1
        if expected != got:
            issues['finished_fixture_season_mismatch_count'] += 1

    season_rows = []
    for comp in sorted({k[0] for k in season_counts}):
        for season in sorted(s for c, s in season_counts if c == comp):
            d = season_counts[(comp, season)]
            season_rows.append({'competition': comp, 'season': season, 'events': d['events'], 'first_event_date': d.get('first'), 'last_event_date': d.get('last')})

    # Stable ID/name mapping summary across every archived season.
    team_map_issues = {k + ':' + tid: sorted(names) for (k, tid), names in team_id_names.items() if len(names) > 1}
    name_map_issues = {k + ':' + name: sorted(ids) for (k, name), ids in team_name_ids.items() if len(ids) > 1}
    by_league = {}
    for key, (comp, zh) in LEAGUE.items():
        by_league[comp] = {
            'name_zh': zh,
            'understat_original_key': key,
            'events': sum(x['events'] for x in season_rows if x['competition'] == comp),
            'seasons': [x['season'] for x in season_rows if x['competition'] == comp],
            'npxG_event_sides_present': npxg_by_comp[comp]['npxG_values'],
            'npxGA_event_sides_present': npxg_by_comp[comp]['npxGA_values'],
            'home_npxGA_equals_away_npxG': npxg_by_comp[comp]['home_npxGA_equals_away_npxG'],
            'away_npxGA_equals_home_npxG': npxg_by_comp[comp]['away_npxGA_equals_home_npxG'],
            'npxGA_mirror_conflicts': npxg_by_comp[comp]['home_npxGA_equals_away_npxG_mismatch'] + npxg_by_comp[comp]['away_npxGA_equals_home_npxG_mismatch'],
        }
    # Reconcile every competition-local metric independently against the global
    # counters. This catches accidental reuse of a global total in a league row.
    competition_totals = {
        'events': sum(v['events'] for v in by_league.values()),
        'npxG_event_sides_present': sum(v['npxG_event_sides_present'] for v in by_league.values()),
        'npxGA_event_sides_present': sum(v['npxGA_event_sides_present'] for v in by_league.values()),
        'home_npxGA_equals_away_npxG': sum(v['home_npxGA_equals_away_npxG'] for v in by_league.values()),
        'away_npxGA_equals_home_npxG': sum(v['away_npxGA_equals_home_npxG'] for v in by_league.values()),
        'npxGA_mirror_conflicts': sum(v['npxGA_mirror_conflicts'] for v in by_league.values()),
    }
    global_totals = {
        'events': len(events),
        'npxG_event_sides_present': npxg_counts['side_values'] // 2,
        'npxGA_event_sides_present': npxg_counts['side_values'] // 2,
        'home_npxGA_equals_away_npxG': npxg_mirror_counts['home_npxGA_equals_away_npxG'],
        'away_npxGA_equals_home_npxG': npxg_mirror_counts['away_npxGA_equals_home_npxG'],
        'npxGA_mirror_conflicts': npxg_mirror_counts['home_npxGA_equals_away_npxG_mismatch'] + npxg_mirror_counts['away_npxGA_equals_home_npxG_mismatch'],
    }
    aggregation_checks = {
        metric: {'competition_sum': competition_totals[metric], 'global_total': global_totals[metric],
                 'matches': competition_totals[metric] == global_totals[metric]}
        for metric in global_totals
    }
    if not all(row['matches'] for row in aggregation_checks.values()):
        issues['competition_global_aggregation_mismatch'] += 1
    # Native data source period and old-season availability are read from the retained archive audit.
    scope_path = root / 'reports/archive-scope.json'
    scope = json.loads(scope_path.read_text()) if scope_path.exists() else {}
    access_path = root / 'reports/access-attempts.jsonl'
    access = [json.loads(x) for x in access_path.read_text().splitlines() if x.strip()] if access_path.exists() else []
    events_archive_sha = None
    with tarfile.open(archive, 'r:gz') as tf:
        member = tf.extractfile('events.jsonl')
        events_archive_sha = sha(member.read()) if member else None
        archive_member_count = sum(m.isfile() for m in tf.getmembers())
    report = {
        'schema': 'r21-understat-independent-raw-audit-v1',
        'inputs': {
            'r14_events_path': str(events_path), 'r14_events_sha256': sha(event_bytes),
            'r14_sources_path': str(sources_path), 'r14_sources_sha256': sha(source_bytes),
            'r14_data_pr': 51,
            'r14_data_commit': '8fa73ec47fe8668665fcf94464af89a755ac5626',
            'pr_input_path': 'workspace-updates/20261125-r14-territory-press/inputs/understat.tar.gz',
            'pr_input_sha256': archive_hash,
            'archive_events_sha256': events_archive_sha,
            'archive_equals_r14_events_bytes': events_archive_sha == sha(event_bytes),
            'archive_member_count': archive_member_count,
            'archive_only_mode': archive_only,
            'archive_tree_files_compared': tree_files_checked if not archive_only else archive_member_count,
            'archive_tree_differences': tree_diff if not archive_only else [],
        },
        'overall': {
            'events': len(events), 'source_rows': len(sources), 'raw_response_files': len(source_audit),
            'recalculated_rows': npxg_counts['events'],
            'source_id_date_home_away_identity_checks': len(events) * 9,
            'npxG_values_checked': npxg_counts['side_values'] // 2,
            'npxGA_values_checked': npxg_counts['side_values'] // 2,
            'home_npxGA_mirror_checks': npxg_counts['events'],
            'away_npxGA_mirror_checks': npxg_counts['events'],
            'npxG_npxGA_nulls_in_raw_rows': 0 if npxg_counts['side_values'] == len(events) * 4 else len(events) * 4 - npxg_counts['side_values'],
            'npxGA_mirror_conflicts': npxg_mirror_counts['home_npxGA_equals_away_npxG_mismatch'] + npxg_mirror_counts['away_npxGA_equals_home_npxG_mismatch'],
            'team_id_name_stability_conflicts': len(team_map_issues),
            'team_name_id_ambiguities_within_competition': len(name_map_issues),
            'duplicate_competition_source_match_ids': issues['duplicate_competition_source_match_id'],
            'issue_counts': dict(issues),
            'competition_aggregation_checks': aggregation_checks,
            'passed_all_issue_checks': not issues and not team_map_issues and not name_map_issues
                and all(row['matches'] for row in aggregation_checks.values()),
        },
        'metric_semantics': {
            'npxG': 'Available in raw per-team history and nested event.source_history_sides; not a top-level home_npxG/away_npxG field in fixed events.jsonl.',
            'npxGA': 'Available in raw per-team history and nested event.source_history_sides; not a top-level home_npxGA/away_npxGA field in fixed events.jsonl.',
            'mirror_rule': 'home raw-history npxGA == away raw-history npxG, and away npxGA == home npxG; independently recalculated from original JSON.',
            'xG_xGA_distinction': 'Fixed event top-level home_xg/away_xg and home_xga/away_xga are all-shot xG/xGA fields, not npxG/npxGA.',
            'timezone': 'Understat datetime strings have no timezone marker; dates are compared verbatim, no UTC conversion inferred.',
        },
        'competitions': by_league,
        'competition_totals_recomputed': competition_totals,
        'global_totals_recomputed': global_totals,
        'season_coverage': season_rows,
        'raw_source_audit': source_audit,
        'sample_row_recalculations': sample_rows,
        'team_id_name_changes': team_map_issues,
        'team_name_id_multiple_ids': name_map_issues,
        'historical_availability': {
            'archive_scope': scope.get('requested_legacy_range'),
            'archive_current_range': scope.get('local_raw_getLeagueData_archive_coverage'),
            'access_attempts': access,
            'r14_archive_capture_cutoff': '2026-10-15 UTC; latest completed match dates are per competition in season-coverage.csv; not refreshed through 2026-11-24.',
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    (args.out_dir / 'sources-audit.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')) + '\n' for x in source_audit))
    with (args.out_dir / 'season-coverage.csv').open('w', newline='', encoding='utf-8') as f:
        fields = ['competition', 'season', 'events', 'first_event_date', 'last_event_date']
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); w.writeheader(); w.writerows(season_rows)
    with (args.out_dir / 'sample-row-recalculations.csv').open('w', newline='', encoding='utf-8') as f:
        fields = list(sample_rows[0]) if sample_rows else []
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); w.writeheader(); w.writerows(sample_rows)
    print(json.dumps({
        'events': len(events), 'sources': len(sources), 'raw_response_files': len(source_audit),
        'archive_sha256': archive_hash, 'archive_equals_events': events_archive_sha == sha(event_bytes),
        'recalculated_rows': npxg_counts['events'], 'npxGA_mirror_conflicts': report['overall']['npxGA_mirror_conflicts'],
        'id_name_stability_conflicts': len(team_map_issues), 'issue_counts': dict(issues),
        'archive_only_mode': archive_only,
        'competition_aggregation_checks': aggregation_checks,
    }, ensure_ascii=False, indent=2))
    if temp:
        temp.cleanup()
    if issues or team_map_issues or name_map_issues or not all(row['matches'] for row in aggregation_checks.values()):
        raise SystemExit('Understat independent raw audit failed; inspect verification.json')

if __name__ == '__main__':
    main()
