"""Replay the clock readiness audit from retained responses and original freezes."""

import argparse
from collections import Counter
from datetime import timedelta
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from unicodedata import normalize
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware, verify
from research_program.club_market_capture import CHECKPOINTS, attach, bound_odds, fresh_rows
from research_program.market_baseline import MAXIMUM_QUOTE_AGE

BEIJING = ZoneInfo('Asia/Shanghai')

def read(path):
    return json.loads(path.read_bytes())


def checked_body(root, path, digest):
    found = (root / path).resolve()
    if not found.is_relative_to(root.resolve()):
        raise ValueError('evidence path outside archive')
    body = found.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError(f'evidence hash differs: {path}')
    return json.loads(body)


def verify_plan(root, data):
    plan = read(root / 'registered-clock-plan.json')
    sunday_targets = None
    for name in ('j1_register', 'j1_december_register'):
        stored = plan[name]
        original = verify(read(data / stored['source_path']))
        if original['record_sha256'] != stored['record_sha256'] or original['freeze_id'] != stored['freeze_id']:
            raise ValueError('different J1 registration')
        identity = original['payload']['identity']
        fixtures = original['payload']['fixtures']
        specs = {spec['name']: spec for spec in identity['protocol']['windows']}
        for window, record in stored['windows'].items():
            covered = set()
            for wave in record['planned_waves']:
                kickoff = aware(wave['kickoff'])
                if covered.intersection(wave['match_ids']):
                    raise ValueError('duplicate match in planned waves')
                covered.update(wave['match_ids'])
                if not all(aware(fixtures[mid]['kickoff_at']) == kickoff for mid in wave['match_ids']):
                    raise ValueError('planned J1 kickoff differs from registration')
                for tag, offset in CHECKPOINTS.items():
                    due = wave['checkpoints'][tag]
                    deadline = kickoff - timedelta(minutes=offset)
                    if aware(due['deadline']) != deadline or aware(due['opens']) != deadline - MAXIMUM_QUOTE_AGE:
                        raise ValueError('planned node differs from the project cutoff')
            expected = set(identity['slates'][window])
            if name == 'j1_register':
                expected = {mid for mid in expected if aware(fixtures[mid]['kickoff_at']).astimezone(BEIJING).day == 29}
                sunday_targets, = (stage['targets'] for stage in identity['stages'] if stage['stage'] == 'stage_1')
            spec = specs[window]
            if (covered != expected or record['original_fixture_n'] != spec['expected']
                    or record['minimum_timed_markets'] != spec['minimum_strict_line_issues']
                    or record['minimum_nonpush'] != spec['minimum_nonpush_settled']):
                raise ValueError('market audit population or coverage threshold differs')
    european = plan['europe_registered_round2']
    original = checked_body(data, european['source_path'], european['sha256'])
    waves = [{'kickoff': v['scheduled'], 'counts': dict(Counter(i['competition'] for i in v['fixtures'])),
              'match_ids': [i['match_id'] for i in v['fixtures']]} for v in original['waves']]
    if waves != european['waves'] or original['competitions'] != european['competitions']:
        raise ValueError('European previously registered waves differ')
    return plan, sunday_targets, original


def row_index(raw):
    rows = {(row['bookmaker'], row['market_type'], row['period'], row['format'], row.get('line')): row
            for row in raw['odds']}
    if len(rows) != len(raw['odds']):
        raise ValueError('same-book market rows are ambiguous')
    return rows


def j1(root, original):
    current = root / 'j1-11-29-now'
    old = root.parent / 'market-probe'
    snapshots = read(current / 'capture/prepared-fixtures.json')
    input_fixtures = {f['match_id']: f for f in read(current / 'registered-inputs.json')}
    if (set(input_fixtures) != original or len(snapshots) != len(original)
            or {f['match_id'] for f in snapshots} != original
            or read(current / 'capture/receipts.json')['failures']):
        raise ValueError('J1 readiness must preserve the five original matches')
    crosswalk = read(current / 'team-ids.json')
    old_refs = {Path(ref['path']).name: ref for ref in read(old / 'captures.json')}
    previous = {row['match_id']: row for row in read(old / 'matched-fixtures.json')}
    results = {}
    for row in snapshots:
        mid = row['match_id']
        cutoff = aware(row['cutoff_at'])
        evidence = row['market_evidence']
        ref = evidence['odds']
        past = previous[mid]
        if (past['event_id'] != evidence['event_id'] or aware(past['provider_kickoff']) != aware(row['kickoff_at'])
                or (past['home_espn_id'], past['away_espn_id']) != (row['home'], row['away'])):
            raise ValueError('previous quote comparison fixture differs')
        raw = bound_odds(row, current, evidence, crosswalk, cutoff.isoformat())
        replay = attach(input_fixtures[mid], current, evidence, crosswalk, cutoff.isoformat())
        for key in ('market_snapshots', 'market_availability', 'total_quote'):
            if row.get(key) != replay.get(key):
                raise ValueError('J1 public market screen did not reproduce')
        old_ref = old_refs[f"odds-{raw['event_id']}.json"]
        if old_ref['http_status'] != 200 or aware(old_ref['captured_at']) >= aware(ref['requested_at']):
            raise ValueError('previous odds reference is not chronological')
        older = checked_body(old, old_ref['path'], old_ref['sha256'])
        if older['event_id'] != raw['event_id']:
            raise ValueError('previous provider event differs')

        before, after = row_index(older), row_index(raw)
        common = before.keys() & after.keys()
        comparable_open = {k for k in common if before[k]['status'] == after[k]['status'] == 'open'}
        clock_only = sum(before[k]['as_of'] != after[k]['as_of']
                         and before[k]['prices'] == after[k]['prices'] for k in comparable_open)
        now = aware(ref['captured_at'])
        recent_times = [aware(r['as_of']) for r in raw['odds'] if r['status'] == 'open']
        markets = Counter(r['market'] for r in replay['market_snapshots'])
        results[mid] = {
            'provider_match_id': raw['event_id'],
            'captured_at': ref['captured_at'],
            'stale': raw['stale'],
            'raw_rows': len(after),
            'latest_open_row_age_seconds': round((now - max(recent_times)).total_seconds(), 3) if recent_times else None,
            'fresh_wdl_rows': markets['1x2'],
            'fresh_total_rows': markets['totals'],
            'fresh_same_book_pair': replay['market_availability'] == 'FRESH_SAME_BOOK_PAIR',
            'comparable_open_same_market_rows': len(comparable_open),
            'row_clock_changed_without_price_change': clock_only,
        }
    return results


def normalized_name(name):
    return ''.join(c for c in normalize('NFKC', name).casefold() if c.isalnum())


def club_name(name):
    text = name.casefold().replace('æ', 'ae').replace('ø', 'o')
    return ''.join(c for c in normalize('NFKD', text) if c.isalnum())


def registered_europe_events(plan, data, code, reviews):
    folder = data / '20261126-europe-first-display/calendar'
    front = read(folder / f'uefa-{code.lower()}-crosswalk.json')
    raw = gzip.decompress((folder / f'uefa-{code.lower()}.json.gz').read_bytes())
    if front['meta']['http_status'] != 200 or sha256(raw).hexdigest() != front['meta']['sha256']:
        raise ValueError('archived UEFA official calendar checksum differs')
    official = {r['id']: r for r in json.loads(raw)}
    espn_links = {r['espn_event_id']: r for r in front['matches']}
    targets = {}
    for wave in plan['waves']:
        for row in (value for value in wave['fixtures'] if value['competition'] == code.lower()):
            mid = row['match_id']
            match = official[row['uefa_id']]
            link = espn_links[mid.removeprefix('espn:')]
            kickoff = aware(wave['scheduled'])
            if (kickoff != aware(match['kickOffTime']['dateTime']) or kickoff != aware(link['kickoff_utc'])
                    or match['competition']['code'] != code or match['status'] != 'UPCOMING'
                    or match['competition']['age'] != 'ADULT' or match['competition']['sex'] != 'MALE'
                    or match['round']['metaData']['name'] != 'League Phase'
                    or int(match['matchday']['sequenceNumber']) != row['official_matchday']
                    or row['uefa_id'] != link['uefa_match_id']):
                raise ValueError('UEFA and original ESPN fixture evidence differs')
            aliases = []
            for side, espn_name in zip(('home', 'away'), row['teams'], strict=True):
                uefa_team = match[side + 'Team']
                if link[side + '_espn'] != espn_name or link[side + '_uefa_id'] != uefa_team['id']:
                    raise ValueError('original ordered UEFA and ESPN teams differ')
                texts = {espn_name, uefa_team['internationalName']}
                translations = uefa_team['translations']
                for key in ('shortName', 'displayName', 'displayOfficialName'):
                    texts.update(translations[key].values())
                review = reviews.get(mid)
                if review and review['side'] == side:
                    if review['uefa_official_name_en'] != translations['displayOfficialName']['EN']:
                        raise ValueError('reviewed provider name does not point to the original official club')
                    texts.add(review['provider_name'])
                aliases.append({club_name(n) for n in texts})
            targets[mid] = (row, kickoff, aliases)
    if len(targets) != plan['competitions'][code.lower()]['registered']:
        raise ValueError('wrong original European population')
    return targets


def catalogs(root, europe_plan, data_root):
    the_odds = root / 'the-odds-api-catalog'
    receipt = read(the_odds / 'request-receipt.json')
    odds_body = checked_body(the_odds, 'sports-catalog.redacted.json', receipt['catalog_sha256'])
    expected_active = {'J League', 'UEFA Europa League', 'UEFA Europa Conference League'}
    active = expected_active.intersection(row['title'] for row in odds_body if row['active'])
    if (active != expected_active or receipt['http_status'] != 200
            or len(odds_body) != receipt['catalog_entry_count']
            or receipt['quota_headers']['x-requests-last'] != '0'):
        raise ValueError('catalog readiness proof differs')

    infer = root / 'europe-infer-catalog'
    refs = read(infer / 'http-log.json')
    pages = ['league-football-unfiltered', 'league-football-page-2', 'league-football-page-3']
    boards = {}
    for ref in refs:
        host = urlsplit(ref['url'])
        if host.scheme != 'https' or host.netloc != 'api.infersports.dev':
            raise ValueError('InferSports response URL differs')
        if ref['status'] == 200:
            boards[ref['name']] = checked_body(infer, ref['body_file'], ref['sha256'])
    seen = {}
    cursor = None
    for page in pages:
        ref = next(x for x in refs if x['name'] == page)
        params = parse_qs(urlsplit(ref['url']).query)
        if params.get('cursor') != ([cursor] if cursor else None):
            raise ValueError('unfiltered league catalog pagination differs')
        board = boards[page]
        for row in board['data']:
            if row['id'] in seen or row['sport'] != 'football':
                raise ValueError('duplicate or wrong sport in the catalog')
            seen[row['id']] = row['name']
        cursor = board['page']['next_cursor']
    if cursor is not None:
        raise ValueError('public league catalog not exhausted')
    wanted = {'UEL': 'lg_NW0GJ4SZ', 'UECL': 'lg_PVTBWSDE'}
    if any(seen[id] != name for name, id in wanted.items()):
        raise ValueError('European league identifiers differ')
    europe_events = {}
    reviews = read(infer / 'reviewed-team-names.json')
    for ref in refs:
        u = urlsplit(ref['url'])
        if u.path != '/v1/events':
            continue
        p = parse_qs(u.query)
        key, = (k for k, v in wanted.items() if p.get('league') == [v])
        if key in europe_events or p.get('date') != ['2026-12-10'] or p.get('timezone') != ['UTC']:
            raise ValueError('different or duplicated European date probe')
        board = boards.get(ref['name'])
        targets = registered_europe_events(europe_plan, data_root, key, reviews)
        matches, exact_matches = {}, []
        for row in (board['data'] if board is not None else []):
            if (row['league']['id'], row['league']['name'], row['status']) != (wanted[key], key, 'scheduled'):
                raise ValueError('unexpected calendar event scope')
            teams = [row[side + '_team'] for side in ('home', 'away')]
            candidates = [(mid, target) for mid, (target, kickoff, known) in targets.items()
                          if aware(row['scheduled_at']) == kickoff
                          and all(club_name(t['name']) in names for t, names in zip(teams, known, strict=True))]
            if len(candidates) != 1 or candidates[0][0] in matches:
                raise ValueError('calendar event does not uniquely match the original European fixture')
            mid, original = candidates[0]
            if [normalized_name(t['name']) for t in teams] == [normalized_name(n) for n in original['teams']]:
                exact_matches.append(mid)
            matches[mid] = {'uefa_id': original['uefa_id'], 'provider_event_id': row['id'],
                            'kickoff_at': row['scheduled_at'],
                            'provider_home': teams[0], 'provider_away': teams[1]}
        if len({row['provider_event_id'] for row in matches.values()}) != len(matches):
            raise ValueError('provider event mapped more than once')
        europe_events[key] = {
            'http_status': ref['status'],
            'catalog_events_returned': len(board['data']) if board is not None else None,
            'registered': len(targets),
            'exact_ordered_scheduled_matches': sorted(exact_matches),
            'confirmed_provider_crosswalk': matches,
            'next_cursor': board['page']['next_cursor'] if board is not None else None,
        }
    quote_samples = {}
    for code, mid in (('UEL', 'espn:401915487'), ('UECL', 'espn:401915796')):
        matched = europe_events[code]['confirmed_provider_crosswalk'][mid]
        event = matched['provider_event_id']
        key = 'odds-' + code.lower()
        ref = next(r for r in refs if r['name'] == key)
        url = urlsplit(ref['url'])
        parsed = parse_qs(url.query)
        if (url.path != f'/v1/events/{event}/odds' or parsed.get('period') != ['full_time']
                or set(parsed.get('markets', [''])[0].split(',')) != {'1x2', 'totals'}):
            raise ValueError('representative quote query differs from the matched fixture')
        if ref['status'] != 200:
            quote_samples[code] = {'match_id': mid, 'http_status': ref['status']}
            continue
        raw = boards[key]
        captured = aware(ref['response_received_at_utc'])
        if (raw['event_id'] != event or not aware(ref['request_started_at_utc']) <= captured
                < aware(matched['kickoff_at'])):
            raise ValueError('representative odds response linkage or clock differs')
        evidence = {'captured_at': ref['response_received_at_utc'], 'sha256': ref['sha256'], 'url': ref['url']}
        fresh = fresh_rows(raw, evidence, mid, captured)
        books = {market: {r['bookmaker'] for r in fresh if r['market'] == market} for market in ('1x2', 'totals')}
        open_times = [aware(r['as_of']) for r in raw['odds'] if r['status'] == 'open']
        quote_samples[code] = {'match_id': mid, 'http_status': 200, 'stale': raw['stale'],
                               'raw_market_rows': len(row_index(raw)), 'fresh_market_rows': len(fresh),
                               'fresh_same_book_pair': bool(books['1x2'] & books['totals']),
                               'latest_open_row_age_seconds': round((captured - max(open_times)).total_seconds(), 3)
                               if open_times else None}
    return {
        'the_odds_api': {
            'catalog_active_titles': sorted(active),
            'credits_remaining_reported': int(receipt['quota_headers']['x-requests-remaining']),
            'odds_requests': 0,
        },
        'infer_europe': {'league_catalog_unique': len(seen), 'leagues': wanted, 'event_probes': europe_events,
                         'quote_samples': quote_samples},
    }


def weekend_score_watch(root, targets):
    first = read(root.parent / 'j1-weekend-results/20261128/first-window.json')
    row = first['original_frozen_comprehensive']
    counts = {'first_exact_score': row['scores']['score_top1']['hits'],
              'three_exact_scores': row['scores']['score_top3']['hits'], 'wdl': row['wdl_hits']}
    remaining = row['registered'] - row['settled']
    return {'settled': row['settled'], 'remaining': remaining, 'registered': row['registered'],
            'selected_seats_pending': row['selected']['occupied'] - row['selected']['settled'],
            'more_hits_to_reach_numeric_threshold': {
                k: ceil(Fraction(str(targets[k])) * row['registered']) - value for k, value in counts.items()},
            'original_formal_quote_coverage': first['formal']['strictly_eligible_market'],
            'independent_first_delivery': first['formal']['independent_first_delivery']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True, help='the pinned original data checkout')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    plan, targets, europe = verify_plan(root, args.data_root / 'workspace-updates')
    sunday = plan['j1_register']['windows']['nov28_29']['planned_waves']
    original = {mid for wave in sunday for mid in wave['match_ids']}
    print(json.dumps({'j1_current': j1(root, original),
                      'catalogs': catalogs(root, europe, args.data_root / 'workspace-updates'),
                      'remaining_score_watch': weekend_score_watch(root, targets)},
                     ensure_ascii=False, sort_keys=True, indent=2))
