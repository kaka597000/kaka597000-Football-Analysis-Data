"""Independent settlement, paired date bootstrap and source-to-feature audit of R14."""
import argparse
import gzip
import hashlib
import json
import math
import tarfile
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from itertools import groupby
from pathlib import Path

import numpy as np


KPI = ('score_top1', 'score_top3', 'wdl', 'actual_ou')
METRICS = ('xg_for', 'xg_against', 'deep_for', 'deep_against', 'ppda')
SETTLEMENT = ('FULL_LOSS', 'HALF_LOSS', 'PUSH', 'HALF_WIN', 'FULL_WIN')
COMPARISONS = {**{a: (a, 'candidate') for a in ('r7', 'r10', 'market', 'xg', 'xg_matched_dose')},
               'same_runtime': ('local_r7', 'local_candidate'), 'fixed_increment': ('fixed_xg', 'fixed_full')}
SIDES = ('home', 'away')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def grade(row, arm):
    h, a = row['actual']
    p = row['forecast'].get(arm, {})
    actual = f'{h}-{a}'
    first, three = p.get('primary'), p.get('top3')
    if three:
        require(len(three) == len(set(three)) == 3 and three[0] == first, 'malformed score ranking')
    result = 'draw' if h == a else ('home' if h > a else 'away')
    direction = p.get('total_side')
    settlement = None
    if direction:
        line = row['line']
        require(p.get('total_line') == line and direction in ('over', 'under'), 'issued total line differs')
        q = round(4 * line)
        require(math.isclose(q, 4 * line), 'invalid Asian line')
        legs = (q - 1, q + 1) if q % 2 else (q, q)
        net = sum((4 * (h+a) > leg) - (4 * (h+a) < leg) for leg in legs)
        settlement = SETTLEMENT[2 + net * (1 if direction == 'over' else -1)]
    vals = (first == actual if first else None, actual in three if three else None,
            p['wdl'] == result if p.get('wdl') else None,
            settlement == 'FULL_WIN' if settlement not in (None, 'PUSH') else None)
    return vals, settlement


@lru_cache(maxsize=128)
def day_weights(n):
    rng = np.random.default_rng(20261123)
    return np.array([np.bincount(rng.choice(n, n), minlength=n) for _ in range(1000)])


def compare(rows, left, right, grades):
    by_day = defaultdict(lambda: np.zeros((4, 4), dtype=int))
    for i, r in enumerate(rows):
        for j, (a, b) in enumerate(zip(grades[left][i][0], grades[right][i][0])):
            if a is not None and b is not None:
                by_day[r['date']][j] += [1, int(a), int(b and not a), int(a and not b)]
    if not by_day:
        return {}
    daily = np.stack([by_day[d] for d in sorted(by_day)])
    simulations = (day_weights(len(daily)) @ daily.reshape(len(daily), -1)).reshape(1000, 4, 4)
    results = {}
    for j, (n, old, gained, lost) in enumerate(daily.sum(axis=0).tolist()):
        draws = simulations[:,j,:]
        valid = draws[draws[:,0] > 0]
        delta = (gained - lost)
        ci = np.percentile((valid[:,2] - valid[:,3]) / valid[:,0], [2.5, 97.5]) * 100 if len(valid) else None
        results[KPI[j]] = dict(paired=n, control_hits=old, candidate_hits=old + delta,
                               gained=gained, lost=lost, net=delta, disagreements=gained + lost,
                               delta_pp=100 * delta/n if n else None, delta_pp_ci95=ci.tolist() if ci is not None else None)
    return results


def inspect_group(rows, stored):
    arms = set(stored['scores']) | {a for pair in COMPARISONS.values() for a in pair}
    grades = {a:[grade(r, a) for r in rows] for a in arms}
    rates, paired = {}, {}
    for arm, score in stored['scores'].items():
        counts = {k:[sum(v[j] is True for v,_ in grades[arm]), sum(v[j] is not None for v,_ in grades[arm])]
                  for j,k in enumerate(KPI)}
        settles = Counter(s for _,s in grades[arm] if s)
        require(score['games'] == len(rows) and score['counts'] == counts and score['settlements'] == dict(settles),
                'score or settlement reconciliation failed: ' + arm)
        rates[arm] = dict(counts=counts, settlements={k:settles[k] for k in SETTLEMENT})
        qrows = [(r, r['quality'][arm]) for r in rows if arm in r.get('quality', {})]
        if qrows:
            loss = np.mean([-math.log(max(1e-300,q['p_observed'])) for _,q in qrows])
            wdl = np.mean([-math.log(max(1e-300,q['wdl'][0 if r['actual'][0] > r['actual'][1] else
                            2 if r['actual'][0] < r['actual'][1] else 1])) for r,q in qrows])
            require(np.allclose([loss,wdl,np.mean([q['p_first'] for _,q in qrows])],
                                [score['score_log_loss'],score['wdl_log_loss'],score['mean_first_probability']],
                                atol=1e-12, rtol=0), 'probability summary differs')
            rates[arm].update(score_log_loss=float(loss), wdl_log_loss=float(wdl))
    for key, (old, new) in COMPARISONS.items():
        result = compare(rows, old, new, grades)
        published = stored['comparisons'][key]
        require(result.keys() == published.keys(), 'paired population differs')
        for k, state in result.items():
            for field, value in published[k].items():
                if field == 'delta_pp_ci95' and value is not None:
                    require(np.allclose(state[field], value, atol=1e-12, rtol=0), f'interval differs: {key} {k}')
                else:
                    require(state[field] == value, f'paired statistic differs: {key} {k} {field}')
        paired[key] = result
    x = np.array([r['features'] for r in rows])
    extra = {k:int(np.any(x[:,:,lo:lo+2] != 0, axis=(1,2)).sum()) for k,lo in
             [('nonzero_xg',0), ('nonzero_territory',2), ('nonzero_press',4)]}
    for short, k in [('first','score_top1'), ('three','score_top3')]:
        for direction in ('gained', 'lost'):
            extra[short + '_' + direction] = paired['r7'][k][direction]
    require(extra == stored['coverage_and_changes'], 'coverage or discordant counts differ')
    exposure = Counter()
    ages = []
    for r in rows:
        m = r['process']
        require(m['cutoff'] == r['date'], 'unexpected retrospective feature cutoff')
        exposure['any_history'] += m['available']
        exposure['two_ids'] += all(m[s+'_id'] is not None for s in SIDES)
        for metric in METRICS:
            measures = [m[s + '_exposure'][metric] for s in SIDES]
            exposure['both_' + metric] += min(measures) > 0
            exposure['any_' + metric] += max(measures) > 0
        for s in SIDES:
            days = m[s+'_history_dates']
            require(len(days) <= 8 and all(d < m['cutoff'] for d in days), 'nonhistorical source day')
            if days:
                ages.append((date.fromisoformat(r['date']) - date.fromisoformat(days[-1])).days)
            exposure['method_' + m[s+'_method']] += 1
        if 'target_fixture_audit' in m:
            exposure['pair_' + m['target_fixture_audit']['status']] += 1
    return dict(n=len(rows), n_dates=len({r['date'] for r in rows}),
                dates=[min(r['date'] for r in rows), max(r['date'] for r in rows)], exposure=exposure,
                latest_observation_age_days=[min(ages), float(np.median(ages)), max(ages)] if ages else None,
                scores=rates, comparisons=paired, **extra)


def inspect_window(rows, reported):
    keys = [r['cohort']+'|'+r['id'] for r in rows]
    require(len(keys) == len(set(keys)) and sha('\n'.join(sorted(keys)).encode()) == reported['fixture_set_sha256'],
            'fixture denominator digest differs')
    output = {'overall': inspect_group(rows, reported['overall']), 'competitions': {}}
    for code,t in reported['competitions'].items():
        output['competitions'][code] = inspect_group([r for r in rows if r['cohort'] == code], t)
    return output


def feature_index(source):
    by_league = defaultdict(list)
    for row in source:
        by_league[row['competition']].append(row)
    lookup, fixtures = defaultdict(list), defaultdict(list)
    for code, rows in by_league.items():
        seed = np.array([1.35,6.,220.,20.])
        sums = np.tile(seed, (2,1))*40
        counts = np.full((2,4), 40)
        for day, items in groupby(sorted(rows, key=lambda r: (r['date'][:10],r.get('source_match_id') or '')),
                                  lambda r:r['date'][:10]):
            norm = sums/counts
            for r in items:
                oriented = []
                for side in SIDES:
                    vals = np.array([r.get(side+'_'+k) for k in ('xg','deep','ppda_att','ppda_def')], dtype=float)
                    vals[(vals < 0) | ~np.isfinite(vals)] = np.nan
                    if not np.isfinite(vals[2:]).all():
                        vals[2:] = np.nan
                    oriented.append(vals)
                for j,s in enumerate(SIDES):
                    own, against = oriented[j],oriented[1-j]
                    derived = [own[0],against[0],own[1],against[1],own[2],own[3]]
                    reference = [norm[j,0],norm[1-j,0],norm[j,1],norm[1-j,1],norm[j,2],norm[j,3]]
                    team=r.get(s+'_id')
                    if team is not None:
                        lookup[code,str(team)].append((day, derived, reference))
                    sums[j] += np.nan_to_num(own)
                    counts[j] += np.isfinite(own)
                if r.get('home_id') is not None and r.get('away_id') is not None:
                    fixtures[code,day].append((str(r['home_id']),str(r['away_id']),r['source_match_id'],r['source_sha256']))
    return lookup, fixtures


def check_features(rows, source):
    histories, fixture_index = feature_index(source)
    errors = np.zeros(6)
    signed = Counter()
    for r in rows:
        team_values = []
        meta = r['process']
        target = date.fromisoformat(r['date'])
        for side in SIDES:
            hist = histories[r['cohort'], meta[side+'_id']]
            end = bisect_left(hist, (r['date'],))
            retained = [(day,obs,exp) for day,obs,exp in hist[max(0,end-8):end]
                        if (target-date.fromisoformat(day)).days <= 150]
            require(meta[side+'_history_dates'] == [day for day,_,_ in retained], 'wrong history window')
            observed = np.array([1.35,1.35,6.,6.,220.,20.])*4
            expected = observed.copy()
            n = np.zeros(6, dtype=int)
            for _,actual,ref in retained:
                for i,value in enumerate(actual):
                    if math.isfinite(value):
                        observed[i]+=value
                        expected[i]+=ref[i]
                        n[i]+=1
            require(meta[side+'_exposure'] == dict(zip(METRICS,n[:5].tolist())), 'metric exposure differs')
            attack = [math.log(v/e) for v,e in zip(observed[:4],expected[:4])]
            # Independently compute the inverse PPDA ratio directly.
            ppda = (expected[4]/expected[5]) / (observed[4]/observed[5])
            signed['positive_pressing' if ppda > 1+1e-12 else
                   'negative_pressing' if ppda < 1-1e-12 else 'neutral_pressing'] += 1
            team_values.append(np.clip([*attack, math.log(ppda)], -1, 1))
        h,a=team_values
        actual = np.array([[v[0],o[1],v[2],o[3],v[4],o[4]] for v,o in ((h,a),(a,h))])
        errors = np.maximum(errors,np.max(np.abs(actual-np.array(r['features'])),axis=0))
        if 'target_fixture_audit' not in meta:
            continue
        day = fixture_index[r['cohort'],r['date']]
        ids = meta['home_id'],meta['away_id']
        paired = [f for f in day if f[:2] == ids]
        if None in ids:
            status = 'unresolved'
        elif not day:
            status = 'date_absent'
        elif len(paired)==1:
            status = 'matched'
        elif paired:
            status = 'ambiguous'
        else:
            status = 'disagreement' if any(set(ids)&set(f[:2]) for f in day) else 'pair_absent'
        audit = meta['target_fixture_audit']
        require(audit['status'] == status, 'source pair audit differs')
        if status=='matched':
            require((audit['source_match_id'],audit['source_sha256']) == paired[0][2:], 'wrong source pair provenance')
    require(np.max(errors) < 2e-12, 'signed source features differ')
    return dict(games=len(rows), feature_cells=12*len(rows), max_abs_error_by_column=errors.tolist(), **signed)


def run(main, source_path, r10):
    reported=json.loads((main/'metrics.json').read_text())
    source=source_path.read_bytes()
    require(sha(source)==json.loads((main/'inputs.json').read_text())['events_sha256'], 'source hash differs')
    control_file=r10/'replay/main.tar.gz'
    require(sha(control_file.read_bytes())==json.loads((r10/'manifest.json').read_text())['files']['replay/main.tar.gz'],
            'R10 main archive hash differs')
    windows=defaultdict(list)
    checked=0
    with tarfile.open(control_file) as t:
        for p in sorted((main/'main').glob('*/forecasts.jsonl.gz')):
            code=p.parent.name
            refbytes=gzip.decompress(t.extractfile(f'main/{code}/forecasts.jsonl.gz').read())
            ref={r['id']:r for r in map(json.loads,refbytes.splitlines())}
            with gzip.open(p,'rt') as f:
                for row in map(json.loads,f):
                    if row['window'] != 'november_extension':
                        other=ref.pop(row['id'])
                        for field in ('cohort','home','away','date','actual','line','source_sha256'):
                            require(row[field]==other[field], 'R10 reference fixture differs')
                        for arm,old in [('r7','r7'),('r10','candidate'),('market','market')]:
                            require(row['forecast'][arm]==other['forecast'][old], 'published control differs')
                        checked+=1
                    windows[row['window']].append(row)
            require(not ref, 'some original R10 fixtures omitted')
    all_rows=[r for group in windows.values() for r in group]
    require(len({(r['cohort'],r['id']) for r in all_rows})==len(all_rows), 'overlapping windows')
    return dict(metrics_sha256=sha((main/'metrics.json').read_bytes()), source_sha256=sha(source),
                verified_original_controls=checked, signed_features=check_features(all_rows,map(json.loads,source.splitlines())),
                windows={w:inspect_window(rows,reported[w]) for w,rows in sorted(windows.items())})


def verify_early(r10, source_archive, aggregate):
    from research_program import territory_early as early

    product=json.loads(aggregate.read_text())
    groups,member=early.load_source(source_archive)
    require(product['csv_sha256']==member, 'secondary member digest differs')
    all_rows=[]
    checks={}
    with early.verified_tar(r10,'inputs/independent.tar.gz') as inp, early.verified_tar(r10,'replay/independent.tar.gz') as refs:
        for code in early.study.CODES:
            raw=groups[code]
            games=sorted(map(json.loads,inp.extractfile('panels/'+code+'.jsonl')), key=lambda g:(g['date'],g['id']))
            full_pairs,_=early.pair_fixtures(raw,games,code)
            def keys(pairs):
                return {(g['id'],h['team'],a['team'],h['date'],a['date']) for g,h,a in pairs}
            ids=keys(full_pairs)
            bare_source=[{k:r[k] for k in ('h_a','team','date')} for r in reversed(raw)]
            bare_games=[{k:g[k] for k in ('id','competition','date','home','away')} for g in games]
            blind,_=early.pair_fixtures(bare_source,bare_games,code)
            require(keys(blind)==ids, 'fixture identities changed after removing outcome/metric fields')
            prefix_counts={}
            for cutoff in ('2017-07-01','2018-07-01','2019-01-01'):
                prefix,_=early.pair_fixtures([r for r in bare_source if r['date'][:10]<cutoff],
                                             [g for g in bare_games if g['date']<cutoff],code)
                require(keys(prefix)=={r for r in ids if r[3][:10]<cutoff}, 'later source or target changed a prior link')
                prefix_counts[cutoff]=len(prefix)
            rows,fit=early.replay(code,raw,inp,refs)
            require(json.loads(json.dumps(fit))==product['leagues'][code], 'early fit or eligibility differs')
            events,_=early.source_history(raw,full_pairs,code)
            checks[code]=dict(label_blind_reversed_source_pairs=len(ids), prefix_pairs=prefix_counts,
                              features=check_features(rows,events))
            all_rows.extend(rows)
    scores=inspect_window(all_rows,product['metrics'])
    scores['verification']=checks
    return scores


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for flag in ('r10','out'):
        ap.add_argument('--'+flag,type=Path,required=True)
    ap.add_argument('--main',type=Path)
    ap.add_argument('--source',type=Path)
    ap.add_argument('--early-aggregate',type=Path)
    ap.add_argument('--archive',type=Path,help='optional pinned Kaggle ZIP for a secondary audit')
    args=ap.parse_args()
    if args.early_aggregate:
        result=verify_early(args.r10,args.archive,args.early_aggregate)
    else:
        if not args.main or not args.source:
            ap.error('main audit requires --main and --source')
        result=run(args.main,args.source,args.r10)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
