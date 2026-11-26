"""Rebuild the November 26 J1 form evidence from seven verified FotMob matches."""

import hashlib
import json
import math
from pathlib import Path
from statistics import mean
import tarfile

from research.analysis_freeze import aware, verify


ROOT = Path(__file__).resolve().parent
INPUTS = {
    'identity': ('20261125-j1-stage-windows/weekend-preparation/two-windows.jsonl',
                 'a151ff6a1b22b87c937b55d570ef3c2effa95a258b73808043223d7e5fa83f16'),
    'results': ('20261126-r26-j1-first-stage/evidence/prior-review-crosscheck.json',
                '4623c3edbc60ca6d51b212c135dd585bd25d4def588290a331c3007dac3b466a'),
    'form': ('20261126-r26-j1-first-stage/evidence/j1-last-five.json',
             'f1aab63424743bac02c08afc8e1d699f7ec5dd573be5bb0cbe4392de860f9852'),
    'december': ('20261126-j1-december-windows/registration/836802cb5ce13a38-v000001.json',
                 'afb624d5b154d982c7cd8df4d685b24afda8b66ddf031d670751e21ed3838cd3'),
}
SIDES = ('home', 'away')


def sha(body):
    return hashlib.sha256(body).hexdigest()


def locked(key):
    name, digest = INPUTS[key]
    body = (ROOT.parent / name).read_bytes()
    if sha(body) != digest:
        raise ValueError('original evidence differs: ' + key)
    return body


def read_capture(archive, meta, fixture):
    fid = fixture['fotmob_match_id']
    file = 'raw/' + fid + '.json'
    source = 'https://www.fotmob.com/api/data/matchDetails?matchId=' + fid
    start, stop = (aware(meta[f'retrieved_{point}_utc']) for point in ('start', 'end'))
    if (meta['url'] != source or meta['raw_file'] != file or meta['http_status'] != 200
            or not aware(fixture['kickoff_at_utc']) < start <= stop):
        raise ValueError('unverified FotMob capture: ' + fid)
    body = archive.extractfile(file).read()
    if len(body) != meta['response_bytes'] or sha(body) != meta['response_sha256']:
        raise ValueError('captured response differs: ' + fid)
    return json.loads(body)


def verified_result(raw, fixture, prior):
    general = raw['general']
    status = raw['header']['status']
    event_time = aware(fixture['kickoff_at_utc'])
    expected = [int(x.strip()) for x in prior['result_90'].split('-')]
    teams = [general[side + 'Team'] for side in SIDES]
    display = raw['header']['teams']
    halfs = status['halfs']
    if (prior['status'] != 'FT' or prior['stage'] != 'regular'
            or aware(prior['kickoff_beijing']) != event_time
            or general['matchId'] != fixture['fotmob_match_id']
            or general['gender'] != 'male' or general['leagueId'] != fixture['fotmob_league_id']
            or general['parentLeagueId'] != 223 or general['matchRound'] != fixture['fotmob_tournamentStage']
            or [team['name'] for team in teams] != [fixture['fotmob_' + side] for side in SIDES]
            or [prior[side + '_id'] for side in SIDES] != ['espn:' + fixture[side]['espn_id'] for side in SIDES]
            or [team['id'] for team in display] != [team['id'] for team in teams]
            or aware(general['matchTimeUTCDate']) != event_time or aware(status['utcTime']) != event_time
            or not general['finished'] or not status['finished'] or status['reason']['short'] != 'FT'
            or status['cancelled'] or status['awarded'] or status['whoLostOnPenalties'] is not None
            or not halfs['gameEnded'] or halfs['firstExtraHalfStarted'] or halfs['secondExtraHalfStarted']
            or [int(x.strip()) for x in status['scoreStr'].split('-')] != expected
            or [team['score'] for team in display] != expected):
        raise ValueError('fixture, orientation or verified 90-minute result differs: ' + fixture['mid'])
    return expected, [team['id'] for team in teams]


def values(groups, key):
    entries = {tuple(row['stats']) for group in groups for row in group['stats']
               if row['key'] == key and row['type'] != 'title'}
    score, = entries
    pair = [float(x) for x in score]
    if len(pair) != 2 or any(not math.isfinite(x) or x < 0 for x in pair):
        raise ValueError('invalid two-sided FotMob metric: ' + key)
    return pair


def process(raw, team_ids):
    groups = raw['content']['stats']['Periods']['All']['stats']
    xg, shots, on_target = [values(groups, key) for key in ('expected_goals', 'total_shots', 'ShotsOnTarget')]
    if any(not a.is_integer() or not b.is_integer() or b > a for a, b in zip(shots, on_target, strict=True)):
        raise ValueError('invalid official shot counts')
    shotmap = raw['content']['shotmap']['shots']
    shot_values = {team: [] for team in team_ids}
    if len({item['id'] for item in shotmap}) != len(shotmap):
        raise ValueError('shotmap repeats a shot identity')
    for s in shotmap:
        v = s['expectedGoals']
        if (s['period'] not in ('FirstHalf', 'SecondHalf') or s['teamId'] not in shot_values
                or type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1):
            raise ValueError('shotmap not covered by a finite regulation-time xG')
        shot_values[s['teamId']].append(v)
    if [len(shot_values[t]) for t in team_ids] != shots:
        raise ValueError('shotmap count differs from the official team count')
    shot_sums = [round(math.fsum(shot_values[t]), 6) for t in team_ids]
    return dict(xg=xg, shots=[int(v) for v in shots], shots_on_target=[int(v) for v in on_target],
                shotmap_xg=shot_sums, shotmap_delta=[round(a-b, 6) for a, b in zip(shot_sums, xg)])


def new_process():
    ids = [json.loads(line) for line in locked('identity').splitlines()]
    target = {r['fotmob_match_id']: r for r in ids if r['window_date_beijing'] == '2026-11-25'}
    results = {r['match_id']: r for r in json.loads(locked('results'))['matches']}
    requests = json.loads((ROOT / 'fotmob/request-manifest.json').read_bytes())
    if len(requests) != 7 or {r['match_id'] for r in requests} != set(target):
        raise ValueError('recorded process coverage must retain the full 11/25 slate')
    stops, matches = [], {}
    with tarfile.open(ROOT / 'fotmob/responses.tar.gz') as archive:
        for meta in requests:
            fixture = target[meta['match_id']]
            mid = fixture['mid']
            raw = read_capture(archive, meta, fixture)
            observed = aware(meta['retrieved_end_utc'])
            started = aware(meta['retrieved_start_utc'])
            if stops and (started - stops[-1]).total_seconds() < 2:
                raise ValueError('FotMob same-service pacing differs from the collection record')
            stops.append(observed)
            goals, teams = verified_result(raw, fixture, results[mid])
            matches[mid] = dict(match_id=mid, fotmob_match_id=fixture['fotmob_match_id'],
                                team_ids=[results[mid][s + '_id'] for s in SIDES], fotmob_team_ids=teams, goals=goals,
                                kickoff_at=fixture['kickoff_at_utc'], observed_at=observed.isoformat(),
                                url=meta['url'], sha256=meta['response_sha256'], **process(raw, teams))
    return matches, max(stops)


def process_mean(rows, metric):
    measured = [row[metric] for row in rows if None not in row[metric]]
    return dict(n=len(measured), for_=round(mean(v[0] for v in measured), 3) if measured else None,
                against=round(mean(v[1] for v in measured), 3) if measured else None)


def team_form(base, matches):
    rows = []
    updates = 0
    for old in base['fixtures']:
        row = dict(old, shotmap_xg_with_reported_fallback=old['xg'])
        new = matches.get(old['match_id'])
        if new:
            side = SIDES.index(old['side'])
            pair = slice(None, None, 1 - 2 * side)
            if (base['id'] != new['team_ids'][side] or old['goals'] != new['goals'][pair]
                    or aware(old['kickoff_at']) != aware(new['kickoff_at'])):
                raise ValueError('process capture differs from the original goal row')
            row.update(xg=new['xg'][pair], shots_on_target=new['shots_on_target'][pair],
                       shotmap_xg_with_reported_fallback=new['shotmap_xg'][pair],
                       process_capture=dict(observed_at=new['observed_at'], url=new['url'], sha256=new['sha256']))
            updates += 1
        rows.append(row)
    return dict(name=base['name'], fixtures=rows, updated_team_matches=updates,
                original=dict(xg=process_mean(base['fixtures'], 'xg'),
                              shots_on_target=process_mean(base['fixtures'], 'shots_on_target')),
                refreshed=dict(xg=process_mean(rows, 'xg'), shots_on_target=process_mean(rows, 'shots_on_target'),
                               shotmap_xg_with_reported_fallback=process_mean(rows, 'shotmap_xg_with_reported_fallback')))


def replay():
    matches, cutoff = new_process()
    plan = verify(json.loads(locked('december')))
    december = plan['payload']['fixtures']
    early = plan['payload']['identity']['slates']['dec04_06']
    late = plan['payload']['identity']['slates']['dec12_13']
    old_form = {team['id']: team for match in json.loads(locked('form')).values() for team in match.values()}
    for window in (early, late):
        seen_teams = {december[mid][s] for mid in window for s in SIDES}
        if len(window) != 10 or seen_teams != set(old_form) or cutoff >= min(aware(december[m]['kickoff_at']) for m in window):
            raise ValueError('process evidence is outside the registered J1 competition and dates')
    teams = {tid: team_form(t, matches) for tid, t in sorted(old_form.items())}
    if len(teams) != 20 or any(len(v['fixtures']) != 5 for v in teams.values()):
        raise ValueError('the original five-fixture team populations differ')
    coverage = {metric: {track: sum(t[track][metric]['n'] for t in teams.values())
                          for track in ('original', 'refreshed')}
                for metric in ('xg', 'shots_on_target')}
    return dict(observed_at=cutoff.isoformat(), match_process=matches, teams=teams,
                updated_team_matches=sum(t['updated_team_matches'] for t in teams.values()),
                coverage_on_100_team_matches=coverage, december_registration=plan['record_sha256'],
                next_window={m: december[m] for m in early})


if __name__ == '__main__':
    print(json.dumps(replay(), ensure_ascii=False, indent=2, allow_nan=False))
