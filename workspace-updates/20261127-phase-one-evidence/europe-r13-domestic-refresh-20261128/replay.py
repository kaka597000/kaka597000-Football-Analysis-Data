"""Replay the R13 domestic eligibility and measure fresh next-window coverage."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from datetime import date, timedelta, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import runpy
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

import numpy as np

from research.analysis_freeze import aware, verify
from research_program.domestic_form import DomesticHistory, team_id
from research_program.goal_state_study import read_lines


COHORTS = {'uel': 'uefa.europa', 'uecl': 'uefa.europa.conf'}
KEYS = ('competition', 'date', 'home_id', 'away_id', 'home_goals', 'away_goals')
DELTA_FILES = ('known-league-delta.jsonl', 'new-league-delta.jsonl', 'october-league-delta.jsonl')
CAPTURE_FOLDERS = ('espn-november', 'espn-october', 'suisse-supplement')


def read(path):
    return json.loads(path.read_bytes())


def digest(body):
    return sha256(body).hexdigest()


def checked(path, expected_hash):
    body = path.read_bytes()
    if digest(body) != expected_hash:
        raise ValueError('input content mismatch: ' + str(path))
    return body


def verified_original(data, specs):
    source = data / 'workspace-updates'
    payloads = {key: checked(source / ref['path'], ref['sha256']) for key, ref in specs.items()}
    registered_hash = json.loads(payloads['original_manifest'])['files']['inputs/domestic.tar.gz']
    if registered_hash != specs['original_domestic']['sha256']:
        raise ValueError('original R13 archive is different from its source manifest')
    return payloads


def extract_month(root, captures, plan):
    responses, sources = [], {}
    requested = set(plan['requested_top_flight_leagues'])
    rows = read(captures / 'evidence.json')
    if set(row['competition'] for row in rows) != requested or len(rows) != len(requested):
        raise ValueError('one recorded response or failure per planned league is required')
    raw_folder = root / 'raw'
    raw_folder.mkdir()
    for row in rows:
        comp = row['competition']
        url = urlsplit(row['url'])
        if ((url.scheme, url.netloc, url.path) != (
                'https', 'site.api.espn.com', f'/apis/site/v2/sports/soccer/{comp}/scoreboard')
                or parse_qs(url.query) != {'dates': [plan['espn_month']], 'limit': ['1000']}
                or aware(row['requested_at_utc']) > aware(row['received_at_utc'])):
            raise ValueError('different public scoreboard or acquire time: ' + comp)
        sources[comp] = {'http_status': row['http_status'], 'received_at_utc': row['received_at_utc'],
                         'events_returned': 0, 'leagues': [], 'status': 'HTTP_NOT_USABLE'}
        if not row.get('path'):
            if row['http_status'] == 200:
                raise ValueError('response body is missing')
            continue
        original = (captures / row['path']).resolve()
        if not original.is_relative_to(captures.resolve()):
            raise ValueError('raw path is outside the retained capture directory')
        stored = original.read_bytes()
        if len(stored) != row['bytes'] or digest(stored) != row['sha256']:
            raise ValueError('retained capture bytes do not match: ' + comp)
        if row['http_status'] != 200:
            continue
        body = gzip.decompress(stored) if stored.startswith(b'\x1f\x8b') else stored
        document = json.loads(body)
        leagues = [r for r in document.get('leagues', ()) if r.get('slug') == comp]
        events = document.get('events')
        if not leagues or not isinstance(events, list) or len(events) >= 1000:
            sources[comp]['status'] = 'NO_COMPLETE_MATCHING_SCOREBOARD'
            continue
        sources[comp].update(events_returned=len(events), leagues=[r['name'] for r in leagues],
                             status='VERIFIED_SCOREBOARD')
        local = raw_folder / (comp + '.json.gz')
        zipped = gzip.compress(body, mtime=0)
        local.write_bytes(zipped)
        responses.append({
            'competition': comp, 'source_sha256': digest(body), 'gzip_sha256': digest(zipped),
            'query_period': plan['espn_month'], 'url': row['url'], 'event_count': len(events),
            'raw_gzip': local.relative_to(root).as_posix(), 'raw_bytes': len(body),
            'gzip_bytes': len(zipped), 'captured_at': row['received_at_utc'],
        })
    manifest = {'responses': responses, 'failed_queries': []}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    namespace = runpy.run_path(str(root / 'extract.py'))
    extract = namespace['extract']
    extract.__globals__['END'] = date.fromisoformat(plan['exclusive_date_cutoff_utc']) - timedelta(days=1)
    with redirect_stdout(io.StringIO()):
        extract()
    window = [row for row in read_lines(root / 'domestic.jsonl')
              if row['date'].replace('-', '').startswith(plan['espn_month'])]
    report = read(root / 'coverage.json')
    return window, sources, report


def reconcile(original, monthly):
    prior = {row['id']: row for row in original}
    prior_competitions = {row['competition'] for row in original}
    if len(prior) != len(original):
        raise ValueError('original R13 event IDs are not unique')
    known, expanded, conflicts, repeated = [], [], [], 0
    for row in monthly:
        prior_row = prior.get(row['id'])
        if prior_row is not None:
            if any(prior_row[key] != row[key] for key in KEYS):
                conflicts.append({'match_id': row['id'], 'original': {k: prior_row[k] for k in KEYS},
                                  'new': {k: row[k] for k in KEYS}, 'new_source_sha256': row['source_sha256']})
            else:
                repeated += 1
        elif row['competition'] in prior_competitions:
            known.append(row)
        else:
            expanded.append(row)
    return known, expanded, repeated, conflicts


def coverage(plan, histories, cutoff):
    output = {}
    for short, cohort in COHORTS.items():
        children = []
        frequencies = {name: Counter() for name in histories}
        for wave in plan['waves']:
            target = aware(wave['scheduled']).astimezone(timezone.utc).date().isoformat()
            for fixture in (row for row in wave['fixtures'] if row['competition'] == short):
                ids = [team_id(fixture[k].removeprefix('espn:')) for k in ('home', 'away')]
                levels = {}
                for name, history in histories.items():
                    design, n = history.context(ids, target, cutoff=cutoff)
                    latest = [date.fromordinal(history.dates[mid][-1]).isoformat() if count else None
                              for mid, count in zip(ids, n, strict=True)]
                    levels[name] = {'usable_games': n, 'latest_known_domestic_day': latest,
                                    'has_rest_or_recent_load_difference': bool(np.any(design[:, 2:]))}
                    sides = sum(count > 0 for count in n)
                    frequencies[name][('neither', 'one', 'both')[sides]] += 1
                    frequencies[name]['usable_sides'] += sides
                children.append({'match_id': fixture['match_id'], 'teams': fixture['teams'], 'ids': ids,
                                 'levels': levels})
        if len(children) != 18 or len({mid for row in children for mid in row['ids']}) != 36:
            raise ValueError('next-window competition is not the original full field')
        output[cohort] = {'registered_fixtures': len(children),
                          'coverage_counts': {k: dict(v) for k, v in frequencies.items()},
                          'fixtures': children}
    return output


def swiss_source_check(data, bundle):
    folder = bundle / 'suisse-supplement'
    expected = {
        'sui-20261121': ('scoreboard', {'dates': ['20261121'], 'limit': ['1000']}),
        'sui-20261025': ('scoreboard', {'dates': ['20261025'], 'limit': ['1000']}),
        'sui-thun-season-2026': ('teams/3024/schedule', {'season': ['2026']}),
    }
    rows = read(folder / 'evidence.json')
    if {row['name'] for row in rows} != set(expected) or len(rows) != len(expected):
        raise ValueError('Swiss supplemental source scope differs')
    intake = {}
    for row in rows:
        ref = urlsplit(row['url'])
        suffix, params = expected[row['name']]
        if ((ref.scheme, ref.netloc, ref.path) != ('https', 'site.api.espn.com',
                    '/apis/site/v2/sports/soccer/sui.1/' + suffix)
                or parse_qs(ref.query) != params or aware(row['requested_at_utc']) > aware(row['received_at_utc'])):
            raise ValueError('Swiss query source or clock differs')
        path = (folder / row['path']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Swiss raw reference outside retained folder')
        body = checked(path, row['sha256'])
        if row['http_status'] != 200 or len(body) != row['bytes']:
            raise ValueError('Swiss raw response differs from the acquired supplement')
        doc = json.loads(body)
        if suffix == 'scoreboard':
            league, = doc['leagues']
            if league['slug'] != 'sui.1':
                raise ValueError('Swiss returned nonmatching domestic league')
            season = league['season']
        else:
            if doc['team']['id'] != '3024':
                raise ValueError('Swiss team endpoint did not return FC Thun')
            season = doc['season']
        if len(doc['events']) != row['event_count'] or doc['events']:
            raise ValueError('check this new Swiss candidate before adding it to R13')
        intake[row['name']] = {'events': len(doc['events']), 'season': season['displayName'],
                               'season_year': season['year'], 'http_status': row['http_status']}

    original = data / 'workspace-updates/20261126-europe-first-display/prematch/uecl-process'
    refs = read(original / 'captures.json')
    checks = {
        '5804302': ('2026-11-21T17:00:00+00:00', [10192, 10191], [3, 2]),
        '5804283': ('2026-10-25T13:00:00+00:00', [10191, 7896], [2, 3]),
    }
    secondary = {}
    for mid, (kickoff, teams, score) in checks.items():
        name = 'match-' + mid + '.json.gz'
        value = refs[name]
        body = gzip.decompress((original / name).read_bytes())
        url = urlsplit(value['url'])
        if (value['http_status'] != 200 or digest(body) != value['sha256']
                or (url.scheme, url.netloc, url.path) != ('https', 'www.fotmob.com', '/api/data/matchDetails')
                or parse_qs(url.query).get('matchId') != [mid]):
            raise ValueError('archived Swiss secondary evidence differs')
        doc = json.loads(body)
        header = doc['header']
        status = header['status']
        if (str(doc['general']['matchId']) != mid or doc['general']['leagueId'] != 937880
                or aware(status['utcTime']) != aware(kickoff) or [v['id'] for v in header['teams']] != teams
                or [v['score'] for v in header['teams']] != score or not status['finished']
                or status['reason']['short'] != 'FT' or status['halfs']['firstExtraHalfStarted']
                or status['awarded'] or status['cancelled'] or status['whoLostOnPenalties']):
            raise ValueError('secondary Swiss result identity or regulation evidence differs')
        secondary[mid] = {'kickoff_utc': kickoff, 'teams': [v['name'] for v in header['teams']],
                          'regulation_result': score, 'source': value}
    return {'espn_queries': intake, 'fotmob_confirmed_regulation': secondary,
            'joined_espn_event_ids': 0, 'r13_extra_rows': 0}


def replay(data, bundle):
    plan_path = bundle / 'protocol.json'
    plan = read(plan_path)
    seal = verify(read(bundle / 'protocol-freeze.json'))
    if seal['payload']['protocol_sha256'] != digest(plan_path.read_bytes()):
        raise ValueError('refresh plan differs from its protocol receipt')
    october_plan_path = bundle / 'october-plan.json'
    october_plan = read(october_plan_path)
    october_seal = verify(read(bundle / 'october-plan-freeze.json'))
    if (october_seal['payload']['plan_sha256'] != digest(october_plan_path.read_bytes())
            or october_plan['primary_refresh_protocol'] != seal['record_sha256']
            or october_plan['exclusive_date_cutoff_utc'] != plan['exclusive_date_cutoff_utc']):
        raise ValueError('October supplement differs from the primary scope')
    raw = verified_original(data, plan['original_inputs'])
    with TemporaryDirectory(prefix='domestic-refresh-') as scratch:
        root = Path(scratch)
        with tarfile.open(fileobj=io.BytesIO(raw['original_domestic'])) as archive:
            old_file = root / 'domestic-original.jsonl'
            old_file.write_bytes(archive.extractfile('domestic/domestic.jsonl').read())
            (root / 'extract.py').write_bytes(archive.extractfile('domestic/extract.py').read())
        old = list(read_lines(old_file))
        if len(old) != 21497:
            raise ValueError('original R13 domestic archive does not match the full-study population')
        month, receipts, provenance = extract_month(root, bundle / 'espn-november', plan)
        known, novel, repeated, disputes = reconcile(old, month)
        october_root = root / 'october'
        october_root.mkdir()
        (october_root / 'extract.py').write_bytes((root / 'extract.py').read_bytes())
        october_fixtures, october_receipts, october_provenance = extract_month(
            october_root, bundle / 'espn-october', october_plan)
        core = old + known + novel
        october_known, october_novel, october_repeated, october_conflicts = reconcile(core, october_fixtures)
        october = october_known + october_novel
        histories = {'original': DomesticHistory(old), 'known_leagues': DomesticHistory(old + known),
                     'expanded_recent': DomesticHistory(core), 'october_and_november': DomesticHistory(core + october)}
        reports = coverage(json.loads(raw['registered_europe_window']), histories, plan['exclusive_date_cutoff_utc'])

    last_day_counts = {group: history.through for group, history in histories.items()}
    extra = Counter(row['competition'] for row in novel)
    existing_codes = {row['competition'] for row in old}
    extended = Counter(row['competition'] for row in novel + october if row['competition'] not in existing_codes)
    return {
        'evidence_phase': plan['evidence_phase'],
        'protocol_freeze': seal['freeze_id'],
        'october_plan_freeze': october_seal['freeze_id'],
        'exclusive_date_cutoff_utc': plan['exclusive_date_cutoff_utc'],
        'original_domestic_fixture_n': len(old),
        'all_observed_domestic_latest_date': last_day_counts,
        'known_league_unique_additions': Counter(row['competition'] for row in known),
        'new_league_november_only_additions': dict(extra),
        'new_league_prior_share_at_cutoff': {name: round(40 / (40 + n), 9) for name, n in extra.items()},
        'november_duplicate_existing_matches': repeated,
        'domestic_conflicts_quarantined': disputes,
        'extraction_exclusions': provenance['exclusions'],
        'extraction_conflicts_quarantined': provenance['conflicts_excluded'],
        'additional_phase_slugs_as_reported': Counter(row['phase_evidence']['season_name'] for row in known + novel),
        'new_rows_without_period_value': sum(row['regulation_period'] is None for row in known + novel),
        'source_receipts': receipts,
        'october_source_receipts': october_receipts,
        'october_unique_additions': Counter(row['competition'] for row in october),
        'october_duplicate_existing_matches': october_repeated,
        'october_conflicts_quarantined': october_conflicts,
        'october_extraction_exclusions': october_provenance['exclusions'],
        'october_extraction_conflicts_quarantined': october_provenance['conflicts_excluded'],
        'october_additional_phase_slugs': Counter(row['phase_evidence']['season_name'] for row in october),
        'october_new_rows_without_period_value': sum(row['regulation_period'] is None for row in october),
        'october_november_new_league_prior_share_at_cutoff': {
            name: round(40 / (40 + n), 9) for name, n in extended.items()
        },
        'swiss_supplement': swiss_source_check(data, bundle),
        'coverage': reports,
    }, known, novel, october


def emit(folder, report, known, novel, october):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'verified.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    for name, rows in zip(DELTA_FILES, (known, novel, october), strict=True):
        (folder / name).write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))


def verify_review(bundle, output):
    review = verify(read(bundle / 'review-freeze.json'))
    payload = review['payload']
    protocols = {
        name: verify(read(bundle / name))['record_sha256']
        for name in ('protocol-freeze.json', 'october-plan-freeze.json')
    }
    if (review['stage'] != 'review' or review['model_promotion'] or payload['source_protocols'] != protocols
            or review['evaluation_slot'] != 'SEPARATE_REVISION_OR_STAGE'):
        raise ValueError('wrong domestic coverage review receipt')
    for name in ('verified.json', *DELTA_FILES):
        checked(output / name, payload['sha256_files'][name])
    for folder in CAPTURE_FOLDERS:
        name = f'{folder}/evidence.json'
        checked(bundle / name, payload['sha256_files'][name])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    emit(args.out, *replay(args.data_root.resolve(), bundle))
    verify_review(bundle, args.out)
