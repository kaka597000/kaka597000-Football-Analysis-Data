"""Build separate European collector inputs and replay the two real source samples."""

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automation.market_identity import scheduled_competition
from research.analysis_freeze import aware
from research_program.goal_state_forward import _read as locked_record
from research_program.club_market_capture import require_market_scope


COMPETITIONS = {'uel': 'uefa.europa', 'uecl': 'uefa.europa.conf'}
SAMPLES = {'uel': 'espn:401915487', 'uecl': 'espn:401915796'}
UTC_DAY = '2026-12-10'


def read(path):
    return json.loads(path.read_bytes())


def digest(body):
    return sha256(body).hexdigest()


def write(out, name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                            encoding='utf-8')


def original_board(folder, captures, short):
    ref = captures[short][UTC_DAY]
    stored = (folder / f'{short}-{UTC_DAY}.json.gz').read_bytes()
    body = gzip.decompress(stored)
    if (ref['status'] != 200 or digest(stored) != ref['archive_sha256']
            or digest(body) != ref['source_sha256']):
        raise ValueError('registered scoreboard checksum or status differs')
    return json.loads(body), body, ref


def inputs(data, readiness):
    season = data / 'workspace-updates/20261126-europe-first-display'
    official = read(season / 'capture-plan/round2.json')
    captures = read(season / 'calendar/captures.json')
    provider = read(readiness / 'verified.json')['catalogs']['infer_europe']['event_probes']
    planned = {r['match_id']: dict(r, kickoff=wave['scheduled']) for wave in official['waves'] for r in wave['fixtures']}
    fixtures, teams, boards = {}, {}, {}
    for short, league in COMPETITIONS.items():
        registration = season / 'registration'
        plan = locked_record(registration, read(registration / f'{short}.json'))
        if plan['freeze_id'] != official['competitions'][short]['window_registration']:
            raise ValueError('different original European window registration')
        registered = plan['payload']['fixtures']
        expected = set(plan['payload']['identity']['windows']['round2']['ids'])
        board, body, ref = original_board(season / 'calendar', captures, short)
        if [r['slug'] for r in board['leagues']] != [league]:
            raise ValueError('ESPN scoreboard competition differs')
        matches = provider[short.upper()]['confirmed_provider_crosswalk']
        if set(matches) != expected or expected != {mid for mid, row in planned.items() if row['competition'] == short}:
            raise ValueError('provider calendar must cover the original round')
        fixtures[short], teams[league], boards[short] = [], {}, (body, ref)
        seen = set()
        for event in board['events']:
            mid = 'espn:' + event['id']
            row, matched = planned[mid], matches[mid]
            _, ordered = scheduled_competition(event)
            kickoff = aware(event['date'])
            if (mid in seen or row['uefa_id'] != matched['uefa_id']
                    or kickoff != aware(row['kickoff']) or kickoff != aware(matched['kickoff_at'])
                    or kickoff != aware(registered[mid]['kickoff_at']) or registered[mid]['cohort'] != league
                    or any(registered[mid][side] != row[side] for side in ('home', 'away'))
                    or aware(ref['observed_at']) >= kickoff
                    or event['status']['type']['name'] != 'STATUS_SCHEDULED'
                    or [('espn:' + ordered[s]['id'], ordered[s]['displayName']) for s in ('home', 'away')]
                    != [(row[s], name) for s, name in zip(('home', 'away'), row['teams'], strict=True)]):
                raise ValueError('ordered clubs or schedule differs from original registration')
            seen.add(mid)
            fixture = dict(registered[mid], competition=league, kickoff_at=kickoff.isoformat(),
                           score_basis='regulation_90', provider_season=event['season'],
                           market_provider_event_id=matched['provider_event_id'])
            require_market_scope(fixture)
            fixtures[short].append(fixture)
            for side in ('home', 'away'):
                source_team = matched['provider_' + side]
                teams[league][row[side]] = {'espn_name': ordered[side]['displayName'],
                                           'provider_name': source_team['name'], 'provider_id': source_team['id']}
        if seen != matches.keys() or len(seen) != 18 or len(teams[league]) != 36:
            raise ValueError('wrong original competition or role count')
        fixtures[short].sort(key=lambda f: (aware(f['kickoff_at']), f['match_id']))
    return fixtures, teams, boards


def replay(source, readiness, fixtures, teams, boards):
    sys.path.insert(0, str(source.resolve()))
    from scripts import capture_public_club_markets as collector

    evidence = readiness / 'europe-infer-catalog'
    refs = {row['name']: row for row in read(evidence / 'http-log.json')}
    archive = {}
    samples = []
    for short, mid in SAMPLES.items():
        fixture, = (row for row in fixtures[short] if row['match_id'] == mid)
        samples.append(fixture)
        original, ref = boards[short]
        archive[ref['url']] = (original, {'url': ref['url'], 'captured_at': ref['observed_at'],
                                         'sha256': ref['source_sha256']})
        for name in (f'events-{short}', f'odds-{short}'):
            market = refs[name]
            body = (evidence / market['body_file']).read_bytes()
            if market['status'] != 200 or digest(body) != market['sha256']:
                raise ValueError('retained public market response differs')
            archive[market['url']] = (body, {key: market[key] for key in ('url', 'sha256')} |
                                      {'requested_at': market['request_started_at_utc'],
                                       'captured_at': market['response_received_at_utc']})
    # Replay only asks the collector for evidence already archived for these two fixtures.
    cutoff = max(aware(ref['captured_at']) for _, ref in archive.values())
    supplied = []

    def return_archived(url, path):
        body, ref = archive[url]
        supplied.append(url)
        path.write_bytes(body)
        return dict(ref, file=path.name)

    class ReplayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cutoff.astimezone(tz or timezone.utc)

    with TemporaryDirectory(prefix='europe-market-replay-') as scratch:
        out = Path(scratch) / 'settled'
        with patch.object(collector, 'board_fetch', side_effect=lambda url, _public, path: return_archived(url, path)), \
                patch.object(collector, 'provider_fetch', side_effect=return_archived), \
                patch.object(collector, 'datetime', ReplayClock), patch.object(collector, 'sleep'):
            results = collector.collect(samples, teams, out)
        report = read(out / 'receipts.json')
        if (len(supplied) != len(archive) or set(supplied) != set(archive) or report['failures']
                or report['fresh_total'] or set(r['match_id'] for r in results) != set(SAMPLES.values())
                or any(row['market_snapshots'] for row in results)):
            raise ValueError('archived collector samples did not reproduce')
        return {'capture_cutoff_utc': cutoff.isoformat(), 'live_requests': 0, 'replayed_matches': len(results),
                'replayed_responses': len(supplied), 'fresh_total': report['fresh_total'],
                'registered_by_cohort': {COMPETITIONS[key]: len(rows) for key, rows in fixtures.items()},
                'samples': {r['match_id']: {'provider_event_id': r['market_evidence']['event_id'],
                                           'availability': r['market_availability'],
                                           'odds_sha256': r['market_evidence']['odds']['sha256']} for r in results}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-data', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent.parent / 'market-readiness-20261128'
    planned, crosswalk, raw_boards = inputs(args.original_data, evidence)
    verified = replay(args.source, evidence, planned, crosswalk, raw_boards)
    args.out.mkdir(parents=True, exist_ok=False)
    for short, rows in planned.items():
        write(args.out, f'fixtures-{short}.json', rows)
    write(args.out, 'team-ids.json', crosswalk)
    write(args.out, 'replay.json', verified)
