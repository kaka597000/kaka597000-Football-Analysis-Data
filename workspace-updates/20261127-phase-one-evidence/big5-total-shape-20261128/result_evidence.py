"""Verify retained regulation results and independent actual kickoff evidence."""
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from research.analysis_freeze import aware
from research_program.display_window_review import summary_kickoff


LEAGUES = {
    'eng.1': ('2026-27 English Premier League', '47'),
    'esp.1': ('2026-27 LALIGA', '87'),
    'fra.1': ('2026-27 Ligue 1', '53'),
    'ger.1': ('2026-27 German Bundesliga', '54'),
    'ita.1': ('2026-27 Italian Serie A', '55'),
}


def require(check, message):
    if not check:
        raise ValueError(message)


def score(value):
    require(type(value) in (str, int) and re.fullmatch(r'0|[1-9][0-9]*', str(value)), 'invalid goal count')
    return int(value)


def utc(value):
    if isinstance(value, datetime):
        require(value.utcoffset() is not None, 'timezone missing')
        return value.astimezone(timezone.utc)
    return aware(value).astimezone(timezone.utc)


def retained(root, ref, at):
    rel = Path(ref['path'])
    path = (root / rel).resolve()
    require(not rel.is_absolute() and path.is_relative_to(root), 'receipt path outside evidence directory')
    captured = utc(ref['captured_at'])
    require(ref['http_status'] == 200 and captured <= at, 'unsuccessful or future capture')
    if ref.get('requested_at') is not None:
        require(utc(ref['requested_at']) <= captured, 'request after capture')
    body = path.read_bytes()
    if body.startswith(b'\x1f\x8b'):
        body = gzip.decompress(body)
    require(sha256(body).hexdigest() == ref['sha256'], 'receipt checksum mismatch')
    return body, captured


def endpoint(url, hosts, path, key, value):
    uri = urlsplit(url)
    require(uri.scheme == 'https' and uri.hostname in hosts and uri.port in (None, 443)
            and uri.username is None and uri.password is None and not uri.fragment
            and uri.path == path and parse_qs(uri.query, keep_blank_values=True) == {key: [value]},
            'URL does not identify the registered event')


def espn_event(f, raw):
    event_id = f['match_id'].removeprefix('espn:')
    require(f['match_id'] == 'espn:' + event_id and event_id.isascii() and event_id.isdigit(),
            'invalid ESPN match ID')
    header = raw['header']
    game, = header['competitions']
    require(str(header['id']) == str(game['id']) == event_id and header['league']['slug'] == f['cohort']
            and header['season']['year'] == 2026 and header['season']['name'] == LEAGUES[f['cohort']][0]
            and utc(game['date']) == utc(f['kickoff_at']), 'ESPN event, season or schedule differs')
    return game


def espn(f, raw):
    game = espn_event(f, raw)
    status = game['status']
    typ = status['type']
    require(typ['state'] == 'post' and typ['completed'] is True and typ['name'] == 'STATUS_FULL_TIME'
            and typ['shortDetail'] == 'FT' and status.get('period', 2) == 2
            and raw['format']['regulation']['periods'] == 2
            and raw['format']['regulation']['clock'] == 2700, 'ESPN regulation full time unconfirmed')
    require(not any(e.get('shootout') is True for e in raw.get('keyEvents', [])), 'ESPN shootout')
    sides = {entry['homeAway']: entry for entry in game['competitors']}
    require(len(game['competitors']) == 2 and set(sides) == {'home', 'away'} and f['home'] != f['away'],
            'ESPN side identities ambiguous')
    goals = []
    for side in ('home', 'away'):
        team = sides[side]
        halves = team['linescores']
        require('espn:' + str(team['team']['id']) == f[side] and team.get('shootoutScore') is None
                and len(halves) == 2 and all(v.get('period', i) == i for i, v in enumerate(halves, 1)),
                'ESPN teams or two half scores differ')
        n = score(team['score'])
        require(sum(score(v['displayValue']) for v in halves) == n, 'ESPN half scores disagree')
        goals.append(n)
    return tuple(goals)


def fotmob(f, raw):
    binding = f['fotmob']
    general, header = raw['general'], raw['header']
    status = header['status']
    ids = [str(binding[k]) for k in ('home_id', 'away_id')]
    require(str(general['matchId']) == str(binding['match_id']) and len(set(ids)) == 2
            and str(general['leagueId']) == str(binding['league_id']) == LEAGUES[f['cohort']][1]
            and general['gender'] == 'male'
            and [str(general[k]['id']) for k in ('homeTeam', 'awayTeam')] == ids
            and [str(team['id']) for team in header['teams']] == ids
            and utc(status['utcTime']) == utc(general['matchTimeUTCDate']) == utc(f['kickoff_at']),
            'FotMob registered identities or schedule differ')
    require(status['started'] is True and status['finished'] is True and status['cancelled'] is False
            and status['awarded'] is False and status['reason']['short'] == 'FT'
            and status['whoLostOnPenalties'] is None and not status.get('whoLostOnAggregated'),
            'FotMob regulation full time unconfirmed')
    halves = status['halfs']
    require('firstExtraHalfStarted' in halves and not any(v for k, v in halves.items() if 'extra' in k.lower()),
            'FotMob extra time unclear')
    # These service strings have no offset. They verify period order, never an absolute kickoff time.
    clocks = [datetime.strptime(halves[k], '%d.%m.%Y %H:%M:%S') for k in
              ('firstHalfStarted', 'firstHalfEnded', 'secondHalfStarted', 'secondHalfEnded', 'gameEnded')]
    require(clocks[0] < clocks[1] <= clocks[2] < clocks[3] <= clocks[4], 'FotMob period clocks inconsistent')
    goals = tuple(score(t['score']) for t in header['teams'])
    require(status['scoreStr'].replace(' ', '') == '-'.join(map(str, goals)), 'FotMob score fields disagree')
    return goals


def verify_results(fixtures, root, receipts, at):
    root, at = Path(root).resolve(), utc(at)
    evidence = {mid: {'scores': set(), 'starts': set(), 'sources': set(), 'issues': [],
                      'final_receipts': [], 'kickoff_receipts': []} for mid in fixtures}
    for ref in receipts:
        mid, provider = ref['match_id'], ref['provider']
        require(mid in fixtures and provider in ('espn', 'fotmob'), 'receipt outside registered population')
        f, found = fixtures[mid], evidence[mid]
        require(f['match_id'] == mid and f['cohort'] in LEAGUES, 'invalid registered fixture')
        try:
            body, captured = retained(root, ref, at)
            raw = json.loads(body)
            details = {k: ref[k] for k in ('provider', 'path', 'sha256', 'source_url')}
            details['captured_at'] = captured.isoformat()
            if provider == 'espn':
                endpoint(ref['source_url'], {'site.api.espn.com', 'site.web.api.espn.com'},
                         f"/apis/site/v2/sports/soccer/{f['cohort']}/summary", 'event', mid.removeprefix('espn:'))
                game = espn_event(f, raw)
                status = game['status']['type']
                if status['state'] == 'in' and status['completed'] is False:
                    observed_start = summary_kickoff(body, ref['source_url'], dict(f, competition=f['cohort']), captured)
                    found['starts'].add(observed_start)
                    found['kickoff_receipts'].append(dict(details, actual_kickoff_at=observed_start.isoformat()))
                    continue
                require(captured >= utc(f['kickoff_at']) + timedelta(minutes=90), 'capture before scheduled regulation elapsed')
                goals = espn(f, raw)
                try:
                    observed_start = summary_kickoff(body, ref['source_url'], dict(f, competition=f['cohort']), captured)
                except (ValueError, TypeError, KeyError) as error:
                    found['issues'].append('ESPN actual kickoff unverified: ' + str(error))
                    observed_start = None
                if observed_start is not None:
                    require(captured >= observed_start + timedelta(minutes=90), 'capture before regulation elapsed')
                    found['starts'].add(observed_start)
                    found['kickoff_receipts'].append(dict(details, actual_kickoff_at=observed_start.isoformat()))
            else:
                require(captured >= utc(f['kickoff_at']) + timedelta(minutes=90), 'capture before scheduled regulation elapsed')
                require(isinstance(f.get('fotmob'), dict), 'no registered FotMob binding')
                endpoint(ref['source_url'], {'www.fotmob.com', 'fotmob.com'}, '/api/data/matchDetails',
                         'matchId', str(f['fotmob']['match_id']))
                goals = fotmob(f, raw)
            found['scores'].add(goals)
            found['sources'].add(provider)
            found['final_receipts'].append(dict(details, regulation_score=list(goals)))
        except (ValueError, KeyError, TypeError, OSError, EOFError, AttributeError) as error:
            found['issues'].append(f'{provider} evidence rejected: {error}')
    output = {}
    for mid, found in evidence.items():
        scores, starts = found['scores'], found['starts']
        if len(scores) > 1:
            found['issues'].append('conflicting regulation scores')
        if len(starts) > 1:
            found['issues'].append('conflicting actual kickoff clocks')
        agreed = len(scores) == 1 and len(starts) <= 1
        output[mid] = dict(actual=list(next(iter(scores))) if agreed else None,
                           actual_kickoff_at=next(iter(starts)).astimezone(timezone.utc).isoformat() if len(starts) == 1 else None,
                           result_sources=sorted(found['sources']), issues=sorted(set(found['issues'])),
                           final_receipts=found['final_receipts'], kickoff_receipts=found['kickoff_receipts'],
                           both_providers=agreed and found['sources'] == {'espn', 'fotmob'})
    return output
