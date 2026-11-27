"""Independently count the published panels, compare controls and export the fitted coefficients."""
from collections import Counter, defaultdict
from datetime import date
from itertools import groupby
import math
import re

from common import FEATURES, FOLDS, SIDES, csv_data, fold, read, require, rows, sha, unique

TARGETS = dict(score_top1=.20, score_top3=.40, wdl=.65, actual_ou=.70)
PAIRS = {k: (k, 'candidate') for k in ('r5', 'r7', 'r10', 'market', 'form_only', 'form_matched_dose')}
PAIRS.update(fixed_increment=('fixed_form', 'fixed_full'), same_runtime=('local_r7', 'local_candidate'))
ARMS = sorted({a for pair in PAIRS.values() for a in pair})
BATCHES = {'evaluation': (85, 49, 36, [85, 63, 49]), 'recent': (31, 20, 11, [31, 28, 20])}
ZERO_SETTLEMENTS = dict.fromkeys(('FULL_WIN', 'HALF_WIN', 'PUSH', 'HALF_LOSS', 'FULL_LOSS'), 0)


def rate(n, d):
    return n / d if d else None


def verify_prior(slots, audits):
    by_team = defaultdict(list)
    for day, group in groupby(slots, key=lambda r: r['date']):
        today = list(group)
        ordinal = date.fromisoformat(day).toordinal()
        for s in today:
            mid = s['match_id']
            r = audits[mid]
            require((r['date'], r['fold'], r['source']) == (day, s['fold'], s['source']), ('raw roster audit', mid))
            m = r['prior']
            require((m['date'], m['cutoff'], m['match_id']) == (day, day, mid), ('feature identity', mid))
            for side in SIDES:
                team = s[side + '_id']
                p = m[side]
                hist = [h for h in by_team[team] if h[0] >= ordinal - 365]
                recent = [h for h in hist if h[0] >= ordinal - 90]
                require((p['club_key'], p['team_id'], p['identity_source'], p['club_games_365'], p['form_games'])
                        == ('espn:' + team, team, 'schedule_id', len(hist), min(len(recent), 6)), ('club history', mid, side))
                rosters = []
                for offset, key in enumerate(('previous', 'penultimate'), 1):
                    expected, players = None, None
                    if len(recent) >= offset:
                        stamp, _, players = recent[-offset]
                        tied = [h[1] for h in recent if h[0] == stamp]
                        if len(tied) > 1:
                            players = None
                        status = 'tied_date' if len(tied)>1 else 'missing_roster' if players is None else 'complete'
                        expected = dict(date=date.fromordinal(stamp).isoformat(), match_ids=tied, status=status,
                                        roster_available=players is not None)
                    require(p[key] == expected, ('immediate earlier appearance', mid, side, key))
                    rosters.append(players)
                for role, positions in (('attack', 'MF'), ('defence', 'GD')):
                    n = sum(player['position'] in positions for player in rosters[0] or [])
                    require(p[role] == dict(players=n, rating_available=bool(n),
                                            retention_available=bool(n) and rosters[1] is not None), (mid, side, role))
            both = all(m[s]['previous'] and m[s]['previous']['roster_available'] for s in SIDES)
            require(m['both_prior_rosters'] is both, ('prior availability', mid))
        for s in today:
            for side in SIDES:
                by_team[s[side+'_id']].append((ordinal, s['match_id'], s[side+'_starters']))


def coverage(group):
    sources = [r['source'] for r in group]
    prior = [r['prior'] for r in group]
    both = sum(all(r[s]['status'] == 'complete' for s in SIDES) for r in sources)
    any_side = sum(any(r[s]['status'] == 'complete' for s in SIDES) for r in sources)
    sides = {}
    for side in SIDES:
        sides[side] = dict(source_status=dict(Counter(r[side]['status'] for r in sources)),
                           min_explicit_starters=min(r[side]['explicit_starters'] for r in sources),
                           min_form_games=min(m[side]['form_games'] for m in prior),
                           min_club_games_365=min(m[side]['club_games_365'] for m in prior))
        for role in ('attack', 'defence'):
            sides[side][role] = dict(source_group=sum(r[side][role] > 0 for r in sources),
                                     prior_rating=sum(m[side][role]['rating_available'] for m in prior),
                                     prior_retention=sum(m[side][role]['retention_available'] for m in prior))
    return dict(fixtures=len(group), status='COMPLETE' if both == len(group) else 'PARTIAL' if any_side else 'NO_VERIFIED_ROSTERS',
                source_rows=sum(r['source_rows'] for r in sources), rejected_source_rows=sum(r['rejected_rows'] for r in sources),
                missing_source_fixtures=sum(not r['source_rows'] for r in sources),
                both_complete_rosters=both, any_complete_side=any_side, sides=sides,
                **{k: sum(r[k] for r in prior) for k in ('both_prior_rosters', 'personnel_neutral', 'all_neutral')})


def indicators(row, pick):
    mid = row['id']
    # Both registered J1 windows have zero measured lines in their verified R5 panels.
    require(row['line'] is None and all(pick.get(k) is None for k in ('total_line','total_side','settlement')),
            ('unobserved actual-OU line or settlement', mid))
    top = pick.get('top3')
    first = pick.get('primary')
    if top is not None:
        require(isinstance(top, list) and len(top) == len(set(top)) == 3 and first == top[0]
                and all(re.fullmatch(r'(0|[1-9][0-9]?)-(0|[1-9][0-9]?)', s) for s in top), ('ordered scores', mid))
    h, a = row['actual']
    actual = f'{h}-{a}'
    wdl = pick.get('wdl')
    require(wdl in ('home', 'away', 'draw', None), ('WDL', mid))
    result = 'home' if h>a else 'away' if a>h else 'draw'
    return dict(score_top1=None if first is None else first == actual, score_top3=None if top is None else actual in top,
                wdl=None if wdl is None else wdl == result, actual_ou=None)


def check_forecasts(records, games, originals, audits):
    expected = [k for k in sorted(games, key=lambda k: (games[k]['date'], k))
                if fold(games[k]['date']) in BATCHES]
    require([r['id'] for r in records] == expected, 'complete ordered test forecasts')
    for r in records:
        mid = r['id']
        g = games[mid]
        identity = dict(id=mid, cohort='jpn.1', window=fold(g['date']), date=g['date'], stage=g['stage'],
                        source_sha256=g['source_sha256'], home=g['home'], away=g['away'],
                        actual=[g['home_goals'],g['away_goals']], line=None)
        require(g['total'] is None and all(r[k] == v for k,v in identity.items()), ('R5 test identity', mid))
        for k in ('home_id','away_id','kickoff_at','h2h','total','market_time_basis','bookmaker','paired_market','sources'):
            require(r[k] == g.get(k), ('original market or schedule', k, mid))
        require(r['target_roster_audit'] == audits[mid]['source'] and r['process'] == audits[mid]['prior'],
                ('target or prior audit', mid))
        x = r['features']
        require(len(x) == 2 and all(len(v) == 6 and all(math.isfinite(t) and abs(t) <= 1 for t in v) for v in x)
                and r['process']['personnel_neutral'] == (not any(any(v[2:]) for v in x))
                and r['process']['all_neutral'] == (not any(any(v) for v in x)), ('feature design', mid))
        require(sorted(r['forecast']) == ARMS, ('forecast arms', mid))
        for label, original in originals.items():
            ref = original[mid]
            require(all(ref[k] == v for k,v in identity.items())
                    and r['forecast'][label] == ref['forecast']['candidate']
                    and r['forecast']['market'] == ref['forecast']['market'], ('published comparator', label, mid))
        q = r['quality']['candidate']
        require(0 <= q['p_first'] <= q['p_three'] <= 1 and 0 <= q['p_observed'] <= 1
                and len(q['wdl']) == 3 and all(0 <= p <= 1 for p in q['wdl']) and math.isclose(sum(q['wdl']), 1.),
                ('candidate probabilities', mid))


def selected_days(group):
    days = []
    for day, fixtures in groupby(group, key=lambda r: r['date']):
        ordered = sorted(fixtures, key=lambda r: (-r['quality']['candidate']['p_first'], r['id']))
        seats = []
        for i,r in enumerate(ordered[:3], 1):
            p = r['forecast']['candidate']
            actual = '-'.join(map(str, r['actual']))
            seats.append(dict(seat=i, id=r['id'], p_first=r['quality']['candidate']['p_first'], primary=p['primary'],
                              top3=p['top3'], actual=actual, first_hit=p['primary'] == actual, three_hit=actual in p['top3']))
        days.append(dict(date=day, window=ordered[0]['window'], fixtures=len(ordered), selected=seats,
                         three_first_sweep=all(x['first_hit'] for x in seats) if len(seats)==3 else None))
    return days


def seat_rates(seats):
    n, f, t = len(seats), sum(s['first_hit'] for s in seats), sum(s['three_hit'] for s in seats)
    return dict(selected=n, first_hits=f, ordered_three_hits=t, first_rate=rate(f,n), ordered_three_rate=rate(t,n))


def ranking(days):
    full = [d for d in days if d['fixtures']>=3]
    seats = [s for d in days for s in d['selected']]
    sweep = sum(d['three_first_sweep'] for d in full)
    return dict(days=len(days), fixtures=sum(d['fixtures'] for d in days), full_days=len(full), short_days=len(days)-len(full),
                three_first_sweeps=sweep, three_first_sweep_rate=rate(sweep,len(full)), individual=seat_rates(seats),
                per_seat={str(i): seat_rates([s for s in seats if s['seat']==i]) for i in (1,2,3)})


def count_window(window, group, days, report, tables):
    n = len(group)
    require(report['population'] == n == FOLDS[window] and report['measured_lines'] == 0 and
            report['formal_kpi_eligible'] is False and report['mode'] == 'retrospective_prior_match_rosters',
            ('fixed evaluation population', window))
    require(set(report['scores']) == set(ARMS) and set(report['paired']) == set(PAIRS), ('metric arms', window))
    require(report['bootstrap'] == dict(unit='whole match date', confidence=.95, repetitions=5000,
                                        seed=20261123, per_metric_percentile_intervals=True), ('date bootstrap', window))
    obs = {arm: [indicators(r, r['forecast'][arm]) for r in group] for arm in ARMS}
    for arm, results in obs.items():
        expected = {}
        for metric,target in TARGETS.items():
            eligible = [v[metric] for v in results if v[metric] is not None]
            hits, size = sum(eligible), len(eligible)
            expected[metric] = dict(hits=hits, eligible=size, eligible_rate=rate(hits,size), issued=size,
                                    registered_coverage=size/n, resolved_gate_denominator=n, resolved_gate_rate=hits/n,
                                    target=target)
            tables['metric-counts'].append([window,arm,metric,hits,size,rate(hits,size),n,hits/n])
        require(report['scores'][arm] == dict(metrics=expected,total_settlements=ZERO_SETTLEMENTS), (window, arm, 'scores'))
    for label,(a,b) in PAIRS.items():
        recorded = report['paired'][label]
        require((recorded['baseline'],recorded['candidate']) == (a,b) and set(recorded['metrics']) == set(TARGETS),
                ('paired comparison',label))
        for metric in TARGETS:
            old = [v[metric] for v in obs[a]]
            new = [v[metric] for v in obs[b]]
            pairs = [(x,y,r['date']) for x,y,r in zip(old,new,group,strict=True) if x is not None and y is not None]
            gained = sum(y and not x for x,y,_ in pairs)
            lost = sum(x and not y for x,y,_ in pairs)
            size, net = len(pairs), gained-lost
            fixed = sum(map(bool,new)) - sum(map(bool,old))
            vals = dict(eligible=size,resolved_gate_denominator=n,coverage=size/n,gained=gained,lost=lost,
                        tied=size-gained-lost,net_hits=net,net_rate=rate(net,size),matchday_clusters=len({d for _,_,d in pairs}),
                        fixed_population_net_hits=fixed,fixed_population_net_rate=fixed/n)
            saved = recorded['metrics'][metric]
            require(all(saved[k]==v for k,v in vals.items()), (window,label,metric,'paired counts'))
            if not size:
                require(saved['date_cluster_ci'] is None, (window,label,metric,'unavailable CI'))
            if metric == 'actual_ou':
                require(saved['fixed_population_date_cluster_ci']==[0.,0.], (window,label,'zero-line fixed CI'))
            tables['paired-counts'].append([window,label,metric,size,gained,lost,size-gained-lost,net,fixed,n])
    summaries = {scope: ranking(part) for scope,part in
                 [('all',days),('full',[d for d in days if d['fixtures']>=3]),('short',[d for d in days if d['fixtures']<3])]}
    require(summaries == report['ranking'], ('daily rank & seats',window))
    all_days = summaries['all']
    require((len(days),all_days['full_days'],all_days['short_days'],[x['selected'] for x in all_days['per_seat'].values()])
            == BATCHES[window], ('original whole calendar',window))
    for scope, val in summaries.items():
        for seat, measures in {'all':val['individual'],**val['per_seat']}.items():
            tables['day-counts'].append([window,scope,seat,val['days'],val['fixtures'],val['full_days'],val['short_days'],
                                         val['three_first_sweeps'],measures['selected'],measures['first_hits'],measures['ordered_three_hits']])


def weights(study, slots):
    fit, fw = (read(study/name) for name in ('fit.json','forward.json'))
    through = {k:max(s['date'] for s in slots if s['fold']==k) for k in FOLDS}
    require(fit['training_games']==FOLDS['train'] and fit['validation_games']==FOLDS['validation']
            and fit['training_through']==through['train'] and fit['validation_through']==through['validation']
            and fit['bounds']==['2024-01-01','2025-01-01','2026-01-01']
            and fit['features']==fw['features']==list(FEATURES) and fw['through']==through['recent'] and fw['games']==2822
            and fw['fit_sha256']==sha(study/'fit.json') and fw['study_inputs_sha256']==sha(study/'inputs.json')
            and fw['doses']==fit['doses'], 'fit, forward or calendar bindings')
    config = ('ridge','coefficient_bound','feature_limit','shift_limit','ipf_rtol','ipf_max_iter')
    registered_config = (24., 1.5, 1., .65, 1e-12, 1024)
    counts = ('training_games','games_with_signal','fit_games','scoring_fit_sides','positive_fit_sides')
    for arm in ('full', 'form'):
        trials = fit['trials'][arm]
        require([r['dose'] for r in trials] == [0., .5, 1.], ('validation doses', arm))
        best = dict(score=min(trials, key=lambda r: (-r['first'], -r['three'], r['loss'], r['dose']))['dose'],
                    wdl=max(trials, key=lambda r: r['wdl'])['dose'],
                    total=max(trials, key=lambda r: r['total'] / max(1, r['total_n']))['dose'])
        require(fit['doses'][arm] == best, ('validation-only dose choice', arm))
    require(all(fw[k] == v for k,v in read(study/'inputs.json').items()), 'forward input provenance')
    table = [['phase','through','validation_through','arm',*counts,*config,'score_dose','wdl_dose','total_dose',
              'feature','scoring_beta','positive_beta']]
    for phase, artifact, stop, n in [('train',fit,through['train'],1912),('forward',fw,through['recent'],2822)]:
        require(set(artifact['fitted'])==set(artifact['doses'])=={'full','form'}, 'fitted arms')
        for arm in ('full','form'):
            p, d = artifact['fitted'][arm], artifact['doses'][arm]
            features = FEATURES[:2] if arm=='form' else FEATURES
            require(p['form_only'] is (arm=='form') and p['features']==list(features) and p['training_games']==n
                    and p['version']==fit['version']==fw['version']=='R15-J1-prior-starters-1'
                    and p['estimator']=='R14-territory-press-hurdle-1' and tuple(p[k] for k in config)==registered_config
                    and 0<=p['fit_games']<=p['games_with_signal']<=n and 0<=p['positive_fit_sides']<=p['scoring_fit_sides']<=2*n
                    and set(d)=={'score','wdl','total'} and all(value in (0.,.5,1.) for value in d.values()), ('weight dimensions',phase,arm))
            for feature, score, positive in zip(features,p['scoring_beta'],p['positive_beta'],strict=True):
                require(max(abs(score),abs(positive))<=p['coefficient_bound'] and math.isfinite(score) and math.isfinite(positive),
                        ('coefficient',phase,arm,feature))
                table.append([phase,stop,through['validation'],arm,*[p[k] for k in (*counts,*config)],
                              d['score'],d['wdl'],d['total'],feature,score,positive])
    return csv_data(table)


def derive(study, games, originals, slots):
    audit_rows = rows(study/'roster-coverage.jsonl.gz')
    audits = unique(audit_rows,'id')
    require(list(audits)==[s['match_id'] for s in slots], 'all R5 audit slots in fixed order')
    verify_prior(slots,audits)
    overall = coverage(audit_rows)
    folds = {k:coverage([r for r in audit_rows if r['fold']==k]) for k in FOLDS}
    require(read(study/'coverage.json')==dict(overall=overall,folds=folds,outside_panel_rows=0), 'source/fold coverage')
    inputs = read(study/'inputs.json')
    require(inputs['roster_coverage']==overall['status'] and inputs['outside_panel_rows']==0
            and inputs['formal_kpi_eligible'] is False and inputs['competition']=='jpn.1'
            and inputs['roster_rows']==overall['source_rows'], 'replay input coverage')
    forecasts = rows(study/'forecasts.jsonl.gz')
    check_forecasts(forecasts,games,originals,audits)
    tables = {'metric-counts':[['window','arm','metric','hits','eligible','eligible_rate','fixed_population','gate_rate']],
              'paired-counts':[['window','comparison','metric','paired','gained','lost','tied','net','fixed_net','fixed_population']],
              'day-counts':[['window','scope','seat','days','fixtures','full_days','short_days','sweeps','selected','first_hits','ordered_three_hits']]}
    reports = read(study/'metrics.json')
    days = []
    require(set(reports)==set(BATCHES), 'metrics windows')
    for window in BATCHES:
        group = [r for r in forecasts if r['window']==window]
        daily = selected_days(group)
        count_window(window,group,daily,reports[window],tables)
        require(reports[window]['coverage']==folds[window] and reports[window]['study_roster_coverage']==overall['status'],
                ('window coverage',window))
        days.extend(daily)
    require(days==rows(study/'selected-days.jsonl.gz'), 'day ledger seats and results')
    return {k+'.csv':csv_data(v) for k,v in tables.items()} | {'weights.csv':weights(study,slots)}
