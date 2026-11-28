"""Verify the separate Frosinone–Parma comprehensive first and its lineup sources."""

import gzip
import json
import unicodedata

from data_sources.research_supplement import home_away
from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha
from result_evidence import endpoint, espn_event, retained
from settlement import DIRECTIONS, read


MID = 'espn:401875081'
SIDES = ('home', 'away')


def name_key(name):
    return ''.join(char for char in unicodedata.normalize('NFKD', name.casefold()) if char.isalnum())


def confirmed_lineups(fixture, root, receipts, at):
    sources = {ref['provider']: ref for ref in receipts}
    if len(receipts) != 2 or set(sources) != {'espn', 'fotmob'}:
        raise ValueError('two distinct lineup sources are required')
    binding = fixture['fotmob']
    endpoint(sources['espn']['source_url'], {'site.api.espn.com'},
             '/apis/site/v2/sports/soccer/ita.1/summary', 'event', MID.removeprefix('espn:'))
    endpoint(sources['fotmob']['source_url'], {'www.fotmob.com'},
             '/api/data/matchDetails', 'matchId', binding['match_id'])
    espn, fotmob = (json.loads(retained(root, sources[provider], at)[0]) for provider in ('espn', 'fotmob'))
    game = espn_event(fixture, espn)
    home_away(game['competitors'], fixture)
    espn_status = game['status']['type']
    general, header = fotmob['general'], fotmob['header']
    fm_status = header['status']
    lineup = fotmob['content']['lineup']
    ids = [binding[side + '_id'] for side in SIDES]
    if (espn_status['state'] != 'pre' or espn_status['completed'] is not False
            or general['gender'] != 'male' or str(general['matchId']) != binding['match_id']
            or str(general['leagueId']) != binding['league_id']
            or [str(general[side + 'Team']['id']) for side in SIDES] != ids
            or [str(team['id']) for team in header['teams']] != ids
            or aware(fm_status['utcTime']) != aware(general['matchTimeUTCDate'])
            or aware(fm_status['utcTime']) != aware(fixture['kickoff_at'])
            or any(fm_status[field] is not False for field in ('started', 'finished', 'cancelled'))
            or lineup['lineupType'] != 'standard' or str(lineup['matchId']) != binding['match_id']):
        raise ValueError('the lineup sources are not the bound prematch and confirmed squads')
    rosters = home_away(espn['rosters'], fixture)
    result = {}
    for side, side_id in zip(SIDES, ids):
        fm_team = lineup[side + 'Team']
        espn_players = [p['athlete']['displayName'] for p in rosters[side]['roster'] if p['starter'] is True]
        fm_players = [p['name'] for p in fm_team['starters']]
        if (str(fm_team['id']) != side_id or len(espn_players) != 11 or len(fm_players) != 11
                or len({name_key(name) for name in espn_players}) != 11
                or sorted(map(name_key, espn_players)) != sorted(map(name_key, fm_players))
                or rosters[side]['formation'] != fm_team['formation']):
            raise ValueError('starting eleven or formation differs across sources')
        result[side] = {'formation': fm_team['formation'], 'players': espn_players}
    return result


def frosinone_first(bundle, fixture, pair, *, as_of):
    root = (bundle / 'comprehensive/frosinone-parma').resolve()
    if not root.exists():
        return None
    record = verify(json.loads(gzip.decompress((root / 'first.json.gz').read_bytes())))
    issued = aware(record['recorded_at'])
    if as_of < issued:
        return None
    identity, payload = record['fixture'], record['payload']
    at, kickoff = map(aware, (identity['cutoff_at'], fixture['kickoff_at']))
    receipts = read(root / 'receipts.json')
    if (record['match_id'] != MID or record['stage'] != 'prematch' or record['track'] != 'comprehensive'
            or record['revision'] != 1 or record['previous_sha256'] is not None
            or record['evaluation_slot'] != 'FIRST_PREMATCH'
            or any(identity[key] != fixture[key] for key in ('match_id', 'cohort', 'home', 'away'))
            or aware(identity['kickoff_at']) != kickoff
            or not aware(pair['recorded_at']) <= at <= issued < kickoff
            or payload['current_test_reference']['sha256'] != pair['sha256']
            or payload['lineup_receipts_sha256'] != sha(root / 'receipts.json')
            or payload['recent_process_sha256'] != sha(bundle / 'recent-process/verified.json')
            or not record['selection_audit']['top3_ready']):
        raise ValueError('comprehensive first or input chronology differs from the registered fixture')
    if confirmed_lineups(fixture, root, receipts, at) != payload['lineup_evidence']['xi']:
        raise ValueError('confirmed lineup differs from the frozen comprehensive first')
    picks = payload['displayed_scores']
    if len(picks) != 3 or len(set(picks)) != 3 or picks[0] != payload['primary']:
        raise ValueError('the frozen comprehensive first requires three distinct ordered scores')
    return {'freeze_id': record['freeze_id'], 'sha256': record['record_sha256'],
            'recorded_at': record['recorded_at'],
            'forecast': {'primary': picks[0], 'top3': picks, 'wdl': DIRECTIONS[payload['wdl']]}}
