"""Check the two original Asian Elite fixtures against the independent FotMob FT responses."""
from datetime import timedelta, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path

from research.analysis_freeze import aware


DATA = Path(__file__).resolve().parent / 'afc-finals'
MATCHES = {
    'espn:401912596': ('6050014', ('espn:7102', 6582, 'Gamba Osaka'), ('espn:17757', 165255, 'Port FC')),
    'espn:401912597': ('6050015', ('espn:7115', 4397, 'Kashima Antlers'),
                       ('espn:7119', 46038, 'Jeonbuk Hyundai Motors FC')),
}


def crosscheck(rows, as_of):
    checks = {}
    if rows.keys() != MATCHES.keys():
        raise ValueError('the independent AFC source must join both original registered fixtures')
    for line in (DATA / 'captures.jsonl').read_bytes().splitlines():
        rec = json.loads(line)
        mid = 'espn:' + rec['espn_event_id']
        fid, home, away = MATCHES[mid]
        at = aware(rec['captured_at_utc'])
        if at > aware(as_of):
            continue
        stamp = at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        if (mid in checks or rec['fotmob_match_id'] != fid or rec['http_status'] != 200
                or rec['url'] != 'https://www.fotmob.com/api/data/matchDetails?matchId=' + fid
                or rec['path'] != f'raw/fotmob-live/{fid}-final-refresh-{stamp}.json'
                or aware(rec['requested_at_utc']) > at):
            raise ValueError('duplicate or invalid FotMob acquisition for ' + mid)
        body = gzip.decompress((DATA / (fid + '.json.gz')).read_bytes())
        if sha256(body).hexdigest() != rec['sha256'] or len(body) != rec['bytes']:
            raise ValueError('independent AFC result source bytes differ')
        obj = json.loads(body)
        game, header = obj['general'], obj['header']
        fixture, actual = rows[mid]['fixture'], rows[mid]['actual']
        kickoff = aware(fixture['kickoff_at'])
        teams, status = header['teams'], header['status']
        if (fixture['cohort'] != 'afc.champions:ELITE:league_phase' or fixture['stage'] != 'league_phase'
                or game['matchId'] != fid or game['leagueId'] != 943984 or game['leagueRoundName'] != '5'
                or aware(game['matchTimeUTCDate']) != kickoff or aware(status['utcTime']) != kickoff
                or at < kickoff + timedelta(minutes=90) or len(teams) != 2):
            raise ValueError('independent AFC competition, stage, teams or kickoff differ')
        for side, team, identity in zip(('home', 'away'), teams, (home, away), strict=True):
            eid, provider_id, name = identity
            if (fixture[side] != eid or (team['id'], team['name']) != (provider_id, name)
                    or game[side + 'Team'] != {'id': provider_id, 'name': name}):
                raise ValueError('independent ordered team identity differs: ' + mid)
        goals = [team['score'] for team in teams]
        halves = status['halfs']
        if (not (game['started'] and game['finished'] and status['started'] and status['finished'])
                or not halves['secondHalfEnded'] or not halves['gameEnded']
                or obj['ongoing'] or status['cancelled'] or status['awarded'] or status.get('whoLostOnPenalties')
                or any(v for k, v in halves.items() if 'extra' in k.lower())
                or status['reason']['short'] != 'FT' or status['reason']['longKey'] != 'finished'
                or any(type(goal) is not int or goal < 0 for goal in goals)
                or status['scoreStr'] != ' - '.join(map(str, goals)) or actual != goals):
            raise ValueError('independent regulation final differs from the certified ESPN result: ' + mid)
        checks[mid] = dict(verdict='fotmob_and_espn_ft_agree', goals=goals, url=rec['url'],
                           source_sha256=rec['sha256'], observed_at=rec['captured_at_utc'])
    return checks
