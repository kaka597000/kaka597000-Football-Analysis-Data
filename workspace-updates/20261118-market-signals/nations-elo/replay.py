"""Offline, pinned-source replay of the Nations League independent Elo comparison."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tarfile

import numpy as np


HERE = Path(__file__).resolve().parent
DATA = HERE.parents[2]
UPDATES = DATA / 'workspace-updates'
LEVELS = 'ABCD'
KEYS = ('primary_hit', 'wdl_hit', 'total_hit')


def read(path):
    return json.loads(path.read_bytes())


def check(raw, expected):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f'archive identity mismatch: {expected}')
    return raw


def source(entry):
    return check(gzip.decompress((HERE / 'inputs' / entry['file']).read_bytes()), entry['raw_sha256'])


def history():
    index = read(UPDATES / '20261116-nations-repair/archive-index.json')
    entry, = [e for e in index['files'] if e['original_path'] == '/workspace/WCPP/research/nations-repair-20261116/database-v2/nations.sqlite']
    with tarfile.open(DATA / entry['archive']) as tar:
        raw = check(tar.extractfile(entry['member']).read(), entry['sha256'])
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.deserialize(raw)
    rows = [dict(r) for r in db.execute("""
        SELECT event_key AS match_id, date, kickoff_at, h.name AS home, a.name AS away,
            league_level AS level, season_year AS season, neutral, home_90, away_90
        FROM events e JOIN teams h ON e.home_id=h.team_id JOIN teams a ON e.away_id=a.team_id
        WHERE e.competition='uefa.nations' AND e.stage='league-phase' AND e.training_eligible=1
            AND e.season_year <= 2024 ORDER BY date, match_id
    """)]
    db.close()
    for r in rows:
        r['score'] = [r.pop('home_90'), r.pop('away_90')]
        r['neutral'] = bool(r['neutral'])
        for side in ('home', 'away'):
            r[side] = elo.ALIASES.get(r[side], r[side])
    return rows, {k:entry[k] for k in ('archive', 'member', 'sha256')}


def original_pairs():
    from research.analysis_freeze import verify

    intake = UPDATES / '20261118-all-analysis-review/cumulative-inputs.json'
    bundle = UPDATES / '20261110-nations-model'
    ledger = read(intake)
    labels = {r['match_id']: r for r in ledger['results']}
    previous_report = read(intake.with_name('cumulative-first-candidates-52.json'))
    paired = {r['match_id']: r for r in previous_report['paired_rows']}
    manifest = read(bundle / 'manifest.json')
    originals = {r['path']: r for r in manifest['files']}
    records = []
    with tarfile.open(bundle / 'nations-model-evidence.tar.gz') as tar:
        for item in ledger['first_candidate_refs']:
            archived = originals[item['path']]
            raw = check(tar.extractfile(archived['archive_path']).read(), archived['sha256'])
            doc = verify(json.loads(raw))
            f = doc['fixture']
            r = labels[f['match_id']]
            if not (doc['record_sha256'] == item['sha256'] and doc['evaluation_slot'] == 'FIRST_PREMATCH'
                    and doc['revision'] == 1 and f['stage'] == 'league-phase' and doc['stage'] == 'prematch'
                    and datetime.fromisoformat(doc['recorded_at']) < datetime.fromisoformat(f['kickoff_at'])
                    and r['score_basis'] == 'regulation_90' and r['event_status'] == 'FT'
                    and all(f[side] == (r.get(side) or 'espn:' + r[side + '_team_id']) for side in ('home','away'))):
                raise ValueError(f"original first issue, team identity or regulation score mismatch for {f['match_id']}")
            if r.get('kickoff_at') and datetime.fromisoformat(r['kickoff_at']) != datetime.fromisoformat(f['kickoff_at']):
                raise ValueError(f"schedule mismatch for {f['match_id']}")
            score = [r['home_goals'], r['away_goals']]
            arms = {}
            for role, name in (('current','当前模型'), ('test','test模型')):
                original = doc['payload'][role]
                pred = elo.selections(original['matrix'], score)
                if (pred['primary'] != original['primary']
                        or pred['wdl'] != {'主胜':'home','客胜':'away','平局':'draw'}[original['wdl_reference']]
                        or any(pred[k] != paired[f['match_id']]['models'][name][k] for k in KEYS[:2])):
                    raise ValueError('frozen picks differ from the original reviewed record')
                pred.update(version=original['version'], original_total_quote=original.get('actual_line'))
                arms['frozen_'+role] = pred
            row = {'match_id': f['match_id'], 'date': f['date'], 'kickoff_at': f['kickoff_at'], 'level': f['league_level'],
                   'neutral': f['neutral'], 'score': score, 'first_issued_at': doc['recorded_at'],
                   'first_input_cutoff': f['cutoff_at'], 'freeze_id': doc['freeze_id'], 'freeze_sha256': doc['record_sha256'],
                   'result_source': {'url':r['source_url'], 'observed_at':r['observed_at'], 'sha256':r['source_sha256']},
                   'arms': arms}
            for side in ('home','away'):
                team = f[side + '_name']
                row[side] = elo.ALIASES.get(team, team)
            records.append(row)
    if len({r['match_id'] for r in records}) != len(records) or set(labels) != {r['match_id'] for r in records}:
        raise ValueError('original pair ledger did not reconcile')
    return sorted(records, key=lambda r:(r['date'],r['match_id'])), {
        'first_issue_manifest': str((bundle/'manifest.json').relative_to(DATA)),
        'original_archive_sha256':manifest['archive_sha256'], 'result_ledger':str(intake.relative_to(DATA)),
        'result_ledger_sha256': hashlib.sha256(intake.read_bytes()).hexdigest()}


def attach(r, ratings):
    if any(r[side] not in ratings for side in ('home','away')):
        raise ValueError('unresolved national team: ' + r['match_id'])
    return dict(r, ratings=[ratings[r[side]] for side in ('home','away')])


def summary(rows):
    arms = {}
    for arm in rows[0]['arms']:
        preds = [r['arms'][arm] for r in rows]
        arms[arm] = {**{key:sum(p[key] for p in preds) for key in KEYS}, 'n':len(rows),
                     'score_log_loss':float(np.mean([p['score_log_loss'] for p in preds]))}
    paired = {}
    for arm in arms:
        if arm == 'elo':
            continue
        effect = {}
        for key in KEYS:
            changes = [int(r['arms']['elo'][key])-int(r['arms'][arm][key]) for r in rows]
            effect[key] = {'gained':changes.count(1),'lost':changes.count(-1),'net':sum(changes)}
        paired[arm] = effect
    return {'arms':arms,'elo_minus_reference':paired}


def verify_poisson_fit(group, refit, retained):
    """Both coefficient vectors must solve the same strictly convex score equations."""
    x = np.vstack([elo.design(*r['ratings'], r['neutral'], refit['include_elo']) for r in group])
    goals = np.asarray([r['score'] for r in group]).ravel()
    roots = []
    for model in (refit, retained):
        weights = np.asarray(model['coefficients'])
        rates = np.exp(x @ weights)
        gradient = x.T @ (rates - goals) / len(goals)
        if not np.isfinite(gradient).all() or np.max(np.abs(gradient)) > 1.01e-7:
            raise ValueError('coefficient vector violates the training solver gradient tolerance')
        hessian = x.T @ (rates[:, None] * x) / len(goals)
        # A Newton step from the two nearly stationary points removes differences
        # caused by a BLAS-dependent final BFGS stopping iteration.
        roots.append(weights - np.linalg.solve(hessian, gradient))
    np.testing.assert_allclose(roots[0], roots[1], rtol=0, atol=1e-10,
                               err_msg='refit and archive do not identify the same Poisson optimum')


def fit_and_evaluate(entry, prior, targets, campaign, retained_fits=None):
    world = elo.international_matches(source(entry),entry['committed_at'][:10])
    joining = {(r['date'], r['home'], r['away']):r for r in world if r['tournament']=='UEFA Nations League'}
    # Dates of predictions in the evaluation are later than the Git revision. Keep the
    # ratings fixed at the source vintage throughout each evaluation period.
    snapshot_day = entry['committed_at'][:10]
    if any(r['date'] >= snapshot_day for r in prior) or any(
            entry['committed_at'] >= r.get('first_input_cutoff',r['date']) for r in targets):
        raise ValueError('snapshot did not exist by target cutoff or training data overlap')
    ratings = elo.dated_ratings(world, [snapshot_day, *(r['date'] for r in prior)])
    prepared = []
    for r in prior:
        match = joining[(r['date'],r['home'],r['away'])]
        if match['score'] != r['score']:
            raise ValueError('Nations training label differs from the before-evaluation world snapshot')
        prepared.append(attach(dict(r,neutral=match['neutral']), ratings[r['date']]))
    fits = {}
    for level in LEVELS:
        group = [r for r in prepared if r['level']==level]
        fits[level] = {'elo':elo.fit(group,True), 'venue_only':elo.fit(group,False)}
        if retained_fits is not None:
            for arm, refit in fits[level].items():
                verify_poisson_fit(group, refit, retained_fits[level][arm])
    output = []
    for target in targets:
        row = attach(target, ratings[snapshot_day])
        row['arms'] = dict(row.get('arms',{}))
        for arm, artifact in fits[row['level']].items():
            pmf=elo.forecast(artifact, row['ratings'], row['neutral'])
            row['arms'][arm]=elo.selections(pmf,row['score'])
        output.append(row)
    details = {'world_raw_results': len(world), 'calibration_matches':len(prepared), 'last_calibration_result':max(r['date'] for r in prior),
               'last_world_result':max(r['date'] for r in world), 'rating_vintage':entry['committed_at'],
               'snapshot_url':entry['source_url'], 'world_raw_sha256':entry['raw_sha256'], 'fits':fits,
               'evaluation':summary(output), 'by_grade': {l:summary([r for r in output if r['level']==l]) for l in LEVELS}}
    for r in output:
        r.update(study=campaign,rating_vintage=entry['committed_at'])
    return details, output


def replay(retained_report=None):
    sources = {e['file']:e for e in read(HERE/'inputs/sources.json')}
    historical, historic_lineage = history()
    original, issued_lineage = original_pairs()
    disputed, = [r for r in historical if (r['date'],r['home'],r['away']) == elo.ABANDONED]
    raw_abandoned = source(sources['abandonment-698999.json.gz'])
    if b'match abandoned' not in raw_abandoned.lower() or disputed['match_id'] != 'espn:698999':
        raise ValueError('abandonment source mismatch')
    historical = [r for r in historical if r['match_id'] != disputed['match_id']]
    old = [r for r in historical if r['season'] < 2024]
    new = [r for r in historical if r['season'] == 2024]
    summaries, forecasts = {}, []
    for year, prior, targets in ((2024,old,new),(2026,historical,original)):
        retained_fits = None if retained_report is None else retained_report['campaigns'][str(year)]['fits']
        summaries[str(year)], rows = fit_and_evaluate(sources[f'world-{year}.csv.gz'],prior,targets,str(year),retained_fits)
        forecasts.extend(rows)
    inventory = []
    for file, entry in sources.items():
        if file.startswith('schedule-'):
            page = json.loads(source(entry))
            league, = page['leagues']
            if league['slug']!='uefa.nations':
                raise ValueError('schedule queried wrong competition')
            future = [e['id'] for e in page['events'] if e['date'] >= entry['capture_at'] and e['status']['type']['state']=='pre']
            inventory.append({'url':entry['source_url'], 'captured_at':entry['capture_at'], 'events':len(page['events']),
                              'scheduled_after_capture':future,'source_sha256':entry['raw_sha256']})
    return {'study_version':'1','population_2024_before_exclusions':len(new)+1,
            'historical_eligibility_exclusions':[{'match_id':disputed['match_id'],'date':disputed['date'],'home':disputed['home'],
                'away':disputed['away'],'database_score':disputed['score'],'world_score':[0,0],'reason':'match abandoned; conflicting 90-minute/awarded score'}],
            'archive_lineage':{'uefa_nations_repaired_database':historic_lineage,'november_first_issues':issued_lineage},
            'protocol_sha256':hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),'team_aliases':elo.ALIASES,
            'campaigns':summaries,'future':inventory,'issued_forward':0,
            'rating_inputs_existed_before_matches':True,'elo_method_selected_after_matches':True,
            'historical_intake_first_known_certified':False,'active_promotion':False}, forecasts


def compare(actual, saved, path='root'):
    if isinstance(saved,dict):
        if actual.keys()!=saved.keys(): raise ValueError(path + ': fields')
        for k in saved: compare(actual[k],saved[k],path+'.'+k)
    elif isinstance(saved,list):
        if len(actual)!=len(saved): raise ValueError(path + ': length')
        for i,(a,b) in enumerate(zip(actual,saved)): compare(a,b,path+'.'+str(i))
    elif isinstance(saved,float):
        # Identical model decisions and counts are checked below. Only re-fitted
        # model probabilities, log scores and verified coefficients vary with BFGS.
        refitted = any(marker in path for marker in ('.arms.elo.', '.arms.venue_only.'))
        if '.coefficients.' in path:
            atol, rtol = 1e-7, 0.
        elif refitted and ('.wdl_probabilities.' in path or path.endswith(('p_observed_score','p_over_2_5'))):
            atol, rtol = 1e-7, 0.
        elif refitted and path.endswith('.score_log_loss'):
            atol, rtol = 5e-7, 1e-7
        else:
            atol, rtol = 1e-12, 1e-12
        if not np.isclose(actual, saved, rtol=rtol, atol=atol):
            raise ValueError(f'{path}: {actual!r} differs from {saved!r} (atol={atol}, rtol={rtol})')
    elif actual!=saved:
        raise ValueError(path+': value')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    sys.path.insert(0,str(args.source.resolve()/'runtime'))
    from nations_league import elo_reference as elo
    retained = None if args.out else read(HERE/'report.json')
    report, rows=replay(retained)
    if args.out:
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n')
        (args.out/'predictions.jsonl.gz').write_bytes(gzip.compress(b''.join(
            (json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode() for r in rows),mtime=0))
    else:
        compare(report,retained)
        compare(rows,[json.loads(line) for line in gzip.open(HERE/'predictions.jsonl.gz','rt')])
    print(json.dumps({c:d['evaluation']['arms'] for c,d in report['campaigns'].items()},sort_keys=True))
