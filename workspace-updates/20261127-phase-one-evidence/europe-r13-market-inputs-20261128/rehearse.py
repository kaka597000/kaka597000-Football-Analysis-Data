"""Verify the European intake and real price modes with retained source responses."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from market_inputs import ARM_1X2, ARM_FULL, model_prices, prepare, read
from automation.market_identity import scheduled_competition
from research.analysis_freeze import aware
from research_program.club_market_capture import attach
from research_program.future_validation import write_new

MID = 'espn:401915487'


def checked(body, digest):
    if sha256(body).hexdigest() != digest:
        raise ValueError('rehearsal original bytes do not match')
    return body


def european_inputs(data, bundle):
    plan = read(bundle / 'europe-market-fallback-study-20261128/round2-uel-research-cutoff-revision.json')
    collection = bundle / 'europe-market-collector-20261128'
    fixtures = read(collection / 'fixtures-uel.json')
    teams = read(collection / 'team-ids.json')
    season = data / 'workspace-updates/20261126-europe-first-display'
    calendar = season / 'calendar'
    espn = read(calendar / 'captures.json')['uel']['2026-12-10']
    board = checked((calendar / 'uel-2026-12-10.json.gz').read_bytes(), espn['archive_sha256'])
    body = checked(gzip.decompress(board), espn['source_sha256'])
    capture = bundle / 'market-readiness-20261128/europe-infer-catalog'
    refs = {row['name']: row for row in read(capture / 'http-log.json')}
    schedule = read(calendar / 'uefa-uel-crosswalk.json')
    venues = read(season / 'prematch/venue-opening/verified.json')
    with TemporaryDirectory(prefix='uel-retained-price-input-') as folder:
        root = Path(folder)
        (root / 'board.json').write_bytes(body)
        fixture = next(row for row in fixtures if row['match_id'] == MID)
        evidence = {'event_id': fixture['market_provider_event_id'],
                    'espn': {'file': 'board.json', 'url': espn['url'], 'captured_at': espn['observed_at'],
                             'sha256': espn['source_sha256']}}
        for key in ('events', 'odds'):
            item = refs[key + '-uel']
            if item['status'] != 200:
                raise ValueError('retained European market response failed')
            file = key + '.json'
            (root / file).write_bytes(checked((capture / item['body_file']).read_bytes(), item['sha256']))
            evidence[key] = {'file': file, 'url': item['url'], 'requested_at': item['request_started_at_utc'],
                             'captured_at': item['response_received_at_utc'], 'sha256': item['sha256']}
        received = [aware(evidence[key]['captured_at']) for key in ('espn', 'events', 'odds')]
        cutoff = max(aware(plan['recorded_at']), *received).isoformat()
        verified = prepare(plan, fixtures, [dict(fixture, market_evidence=evidence)], root, teams, cutoff)
    states = {row['fixture']['match_id']: row['market_state'] for row in verified['fixtures']}
    if verified['same_fixture_pairs'] or any(verified['eligible'].values()) or states.get(MID) != 'NO_FRESH_1X2':
        raise ValueError('the stale European response must not supply model prices')
    if sum(state == 'NO_RETAINED_CAPTURE' for state in states.values()) != 17:
        raise ValueError('a missing European capture disappeared from the original population')
    return verified, model_roster(data, fixtures, json.loads(body), schedule, venues, plan)


def model_roster(data, fixtures, board, schedule, venues, plan):
    path = data / 'workspace-updates' / plan['payload']['r7_estimator']['path']
    checked(path.read_bytes(), plan['payload']['r7_estimator']['sha256'])
    with tarfile.open(path) as archive:
        anchor = json.load(archive.extractfile('main/forward.json'))
    events = {'espn:' + row['id']: row for row in board['events']}
    official = {'espn:' + row['espn_event_id']: row for row in schedule['matches']}
    verified_venues = {row['match_id']: row for row in venues['fixtures']
                       if row['window'] == 'round2' and row['competition'] == 'uel'}
    model_teams, records = set(), []
    for fixture in fixtures:
        mid = fixture['match_id']
        event, binding, venue = events[mid], official[mid], verified_venues[mid]
        competition, sides = scheduled_competition(event)
        name = [sides[key]['displayName'] for key in ('home', 'away')]
        if ([fixture[key] for key in ('home', 'away')] !=
                ['espn:' + sides[key]['id'] for key in ('home', 'away')]
                or name != [binding['home_espn'], binding['away_espn']] or name != venue['teams']
                or venue['uefa_id'] != binding['uefa_match_id']
                or venue['uefa_id'] != plan['payload']['fixtures'][mid]['uefa_id']
                or not aware(event['date']) == aware(fixture['kickoff_at']) == aware(binding['kickoff_utc'])
                or any(key not in anchor['state']['goals']['teams'] or key not in anchor['state']['pi'] for key in name)):
            raise ValueError('R13 ordered model team or registered ground differs')
        neutral = competition.get('neutralSite')
        if neutral is not None and type(neutral) is not bool:
            raise ValueError('unexpected neutral-site evidence')
        model_teams.update(name)
        records.append(dict(match_id=mid, model_teams=name, neutral=neutral, official_venue=venue['stadium'],
                            venue_country=venue['country'], home_club_country=venue['home_club_country'],
                            outside_home_club_country=venue['outside_home_club_country']))
    if len(model_teams) != 36 or len(records) != 18:
        raise ValueError('model-roster coverage differs from the locked European slate')
    return {'exact_model_teams': len(model_teams), 'through': anchor['through'], 'fixtures': records}


def replay_positive_j1(bundle):
    samples = [('market-t24-wave-1400', '.', 'espn:401877516', 'SAME_BOOK_PAIR'),
               ('market-t24-wave-1400', '.', 'espn:401877542', 'SAME_BOOK_PAIR'),
               ('market-readiness-20261128/j1-11-29-now', 'capture', 'espn:401877540', '1X2_ONLY')]
    results = {}
    for folder, capture, mid, expected in samples:
        root = bundle / folder
        fixture, = (row for row in read(root / capture / 'prepared-fixtures.json') if row['match_id'] == mid)
        evidence = fixture['market_evidence']
        formed = attach(fixture, root, evidence, {'jpn.1': fixture['market_team_ids']}, fixture['cutoff_at'])
        prices = model_prices(formed)
        arms = prices['arms']
        if (prices['market_state'] != expected or not arms.get(ARM_1X2) or arms[ARM_1X2]['total'] is not None
                or arms[ARM_1X2]['paired_market'] or ((ARM_FULL in arms) != (expected == 'SAME_BOOK_PAIR'))
                or (ARM_FULL in arms and arms[ARM_FULL]['h2h'] != arms[ARM_1X2]['h2h'])):
            raise ValueError('same-book and independent 1X2 replay no longer separate correctly')
        results[mid] = prices
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent.parent
    market, roster = european_inputs(args.data_root, bundle)
    write_new(args.out, {'mode': 'RETAINED_CAPTURE_REHEARSAL', 'markets': market, 'europe_model_roster': roster,
                         'positive_quote_shapes_j1': replay_positive_j1(bundle)})
