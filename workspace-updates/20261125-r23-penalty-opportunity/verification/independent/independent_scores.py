"""Check R23 held-out score rankings using the original R7 grids and raw Understat observations."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import tarfile
import tempfile

import numpy as np

from audit_signal import exposure, LEAGUES
from research_program import continuation_forward, continuation_scores, r8_score_study
from research_program.territory_study import extensions


def require(condition, message):
    if not condition:
        raise ValueError(message)


def member(bundle, name):
    with tarfile.open(bundle, 'r:gz') as archive:
        found = archive.getmember(name)
        require(found.isfile(), f'{name} is not a file in {bundle.name}')
        return archive.extractfile(found).read()


def histories(events):
    teams = defaultdict(list)
    league = defaultdict(list)
    seen = set()
    for raw in events.open(encoding='utf-8'):
        game = json.loads(raw)
        code, mid = game['competition'], str(game['source_match_id'])
        require((code, mid) not in seen, 'duplicate Understat ID')
        seen.add((code, mid))
        day = game['date'][:10]
        _, pair = exposure(game)
        if pair is not None:
            league[code].append((day, mid, (pair[0] + pair[1]) / 2))
        for side, ix in (('home', 0), ('away', 1)):
            own = None if pair is None else (pair[ix], pair[1-ix])
            teams[code, str(game[side+'_id'])].append((day, mid, own))
    for group in teams.values():
        group.sort()
    league_days, means = {}, {}
    for code, observations in league.items():
        observations.sort()
        league_days[code] = [r[0] for r in observations]
        means[code] = np.cumsum([r[2] for r in observations]) / np.arange(1, len(observations)+1)
    return teams, league_days, means


def get_features(code, process, index):
    teams, league_days, means = index
    day = process['cutoff']
    end = bisect_left(league_days[code], day)
    league_mean = float(means[code][end-1]) if end else 0.
    require(process['league_n'] == 2*end, f'{code} league exposure at {day}')
    if end:
        require(math.isclose(process['league_mean'], league_mean, abs_tol=1e-12), 'league mean')
    profile = {}
    for side in ('home', 'away'):
        meta = process[side]
        team = meta['source_team_id']
        games = teams.get((code, str(team)), ())
        stop = bisect_left(games, (day,))
        recent = games[max(0, stop-12):stop]
        require([str(r['source_id']) for r in meta['games']] == [r[1] for r in recent], 'source IDs')
        valid = [r[2] for r in recent if r[2] is not None]
        require(len(valid) == meta['n'], 'club exposure')
        profile[side] = [max(-.75, min(.75, (math.fsum(p[i] for p in valid)-len(valid)*league_mean)/(len(valid)+8)))
                         for i in (0,1)]
    return np.array((profile['home'][0],profile['away'][1],profile['away'][0],profile['home'][1]))


def verify_score(prior, feature, beta, dose, expected, label):
    home, away = np.indices(prior.shape)
    hx = beta[0]*feature[0] + beta[1]*feature[1]
    ax = beta[0]*feature[2] + beta[1]*feature[3]
    lifted = prior * np.exp(home*hx + away*ax)
    lifted /= lifted.sum()
    mixed = (1-dose)*prior + dose*lifted
    cells = sorted(np.ndindex(prior.shape), key=lambda ij:(-mixed[ij], ij))
    pick = [f'{h}-{a}' for h,a in cells[:3]]
    require(pick == expected['top3'] and pick[0] == expected['primary'], f'{label} rank differs')
    return float(mixed[cells[0]]), float(sum(mixed[cell] for cell in cells[:3]))


def verify(study, root, events):
    updates = root/'workspace-updates'
    envelope = updates/'20261125-r21-score-dependence'
    archive = envelope/'inputs/r11/extension.tar.gz'
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name in ('fixture-panels.jsonl', 'market-rows.csv'):
            (directory/name).write_bytes(member(archive,name))
        extras = extensions(directory)
    index = histories(events)
    output = defaultdict(Counter)
    for code in LEAGUES:
        folder=study/'main'/code
        fit=json.loads((folder/'fit.json').read_bytes())
        r5=updates/'20261123-all-scope-kpi/models'/(code+'.tar.gz')
        r7=updates/'20261123-prematch-literature/models'/(code+'.tar.gz')
        games=[json.loads(r) for r in member(r5,'panel.jsonl').splitlines()]
        settings=json.loads(member(r7,'main/fit.json'))
        frozen=json.loads(member(r7,'main/forward.json'))
        with gzip.open(folder/'forecasts.jsonl.gz','rt') as forecasts:
            rows={}
            for row in map(json.loads,forecasts):
                require(row['id'] not in rows, 'duplicate R23 event')
                rows[row['id']]=row
        anchors,features,_=continuation_scores.inputs(games,code)
        retained=[i for i,game in enumerate(games) if game['id'] in rows]
        grids=r8_score_study.matrices(anchors[retained],features[retained],settings)
        history=[(games[i],p) for i,p in zip(retained,grids,strict=True)]
        history.extend((g,continuation_forward.matrix(g,frozen)) for g in extras[code] if g['id'] in rows)
        for game,prior in history:
            mid=game['id']
            row=rows.pop(mid)
            x=get_features(code,row['process'],index)
            require(np.allclose(x,row['features'],rtol=0,atol=1e-12),'source features '+mid)
            truth=f'{game["home_goals"]}-{game["away_goals"]}'
            require(truth == '-'.join(map(str,row['actual'])), 'score label '+mid)
            for arm,dose in (('r7',0.),('candidate',fit['dose']),('full_dose',1.)):
                expected=row['forecast'][arm]
                one,three=verify_score(prior,x,fit['fitted']['beta'],dose,expected,mid+'/'+arm)
                quality=row['quality'][arm]
                require(abs(one-quality['p_first'])<1e-12 and abs(three-quality['p_three'])<1e-12, 'probabilities '+mid)
                require(all(expected.get(k)==row['forecast']['r7'].get(k) for k in ('wdl','total_line','total_side')),
                        'changed market directions '+mid)
                output[row['window'],arm].update(n=1,first=truth==expected['primary'],three=truth in expected['top3'])
        require(not rows, f'{code} unmatched R23 rows')
    return {window:{arm:dict(c) for (w,arm),c in sorted(output.items()) if w==window}
            for window in sorted({key[0] for key in output})}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','data-root','events'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(verify(args.study,args.data_root,args.events),indent=2,sort_keys=True))
