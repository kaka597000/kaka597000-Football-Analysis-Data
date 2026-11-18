"""Use the unchanged historical goal-strength estimator on the full later season to date."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tarfile

import numpy as np


HERE = Path(__file__).resolve().parent
DATA = HERE.parents[2]
SEQUENCE = DATA/'workspace-updates/20261118-sequence/history'
GOALS_ARCHIVE = DATA/'workspace-updates/20261112-elo-kelly/diagnostic-results.tar.gz'
GOAL_SHA = '365afaab307a091c75292757be62707b3fcfd13c240ec7b4f6fdf2ade1a1157d'
GOAL_CODE_SHA = '6595e9cf714b4f9ecab0ce3eb669610ea4e38cc0b3f64ae7360bed4b3433e3c8'
CUTOFF_DAY = '2026-11-17'
PRICE_FIELDS = ('B365CH','B365CD','B365CA','B365C>2.5','B365C<2.5')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def new_games(root, cohort_names):
    games, panels, inventory, exclusions = [], {}, {}, []
    references = json.loads((root/'raw/source-metadata.json').read_bytes())
    if {r['file'] for r in references} != {f'2627_{c}.csv' for c in cohort_names} or len(references) != 5:
        raise ValueError('one complete source extract for each league is required')
    for source in sorted(references, key=lambda r:r['file']):
        f = root/'raw'/source['file']
        raw = f.read_bytes()
        if source['sha256'] != sha(raw):
            raise ValueError('new season file hash mismatch')
        league = f.stem.split('_')[1]
        records = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
        counted = []
        for line,r in enumerate(records,2):
            if not r.get('Date'):
                if any(r.values()): raise ValueError('fixture with missing date')
                continue
            day = datetime.strptime(r['Date'],'%d/%m/%Y').date().isoformat()
            if day > CUTOFF_DAY or not r['FTHG'] or not r['FTAG']:
                exclusions.append({'source_file':f.name,'source_line':line,
                                   'reason':'after_date_cutoff' if day > CUTOFF_DAY else 'without_regulation_result'})
                continue
            goals = [int(r[k]) for k in ('FTHG','FTAG')]
            if r['Div'] != league or len({r['HomeTeam'],r['AwayTeam']}) != 2 or min(goals) < 0:
                raise ValueError('malformed labeled fixture')
            g = {'source_file':f.name,'source_line':line,'cohort':cohort_names[league],'game_date':day,
                 'home':r['HomeTeam'],'away':r['AwayTeam'],'home_goals':goals[0],'away_goals':goals[1]}
            counted.append(day)
            games.append(g)
            try:
                prices = np.array([float(r[k]) for k in PRICE_FIELDS])
                if not np.isfinite(prices).all() or min(prices) <= 1:
                    raise ValueError('invalid decimal price')
                h,d,a,o,u = prices.tolist()
                panels[(f.name,line)]={'h2h':{'home':h,'draw':d,'away':a},'total':{'line':2.5,'over':o,'under':u}}
            except (ValueError, TypeError, KeyError):
                panels[(f.name,line)]=None
        inventory[cohort_names[league]]={'played_in_source':len(counted),'first':min(counted), 'last':max(counted)}
    return games, panels, inventory, exclusions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=HERE)
    args=parser.parse_args();source=args.source.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(source/'runtime'),str(SEQUENCE),str(HERE.parent/'history')]
    from research_program import elo_kelly_ablation as goal
    from research_program import sequence_history
    from run_models import encoded,evaluate
    from run_study import apply_holdout,summarize
    from publication import deliver

    if sha(Path(goal.__file__).read_bytes()) != GOAL_CODE_SHA:
        raise ValueError('retained PR32 goal intensity code differs')
    with tarfile.open(GOALS_ARCHIVE) as tf: raw_models=tf.extractfile('candidate-models.json').read()
    if sha(raw_models) != GOAL_SHA: raise ValueError('PR32 coefficient archive differs')
    models=json.loads(raw_models)
    past, benchmark, past_source = sequence_history._historical_inputs(DATA)
    new,panels,inventory,exclusions = new_games(HERE,goal.PROTOCOL['leagues'])
    old_max=max(r['game_date'] for r in past)
    if old_max!='2026-05-24' or not all(r['game_date']>'2026-08-01' for r in new):
        raise ValueError('later-season transfer overlaps past model data')
    all_games=past+new
    predictor_input=[]; id_for={}
    for row in all_games:
        season, league = Path(row['source_file']).stem.split('_')
        day,h,a=row['game_date'],row['home'],row['away']
        mid=goal.digest([league,day,h,a]); key=row['source_file'],row['source_line']
        if key in id_for: raise ValueError('duplicate source row')
        id_for[key]=mid
        predictor_input.append({'id':mid,'league':league,'date':day,'season':season,'home':h,'away':a,
                                'hg':row['home_goals'],'ag':row['away_goals']})
    if len(set(id_for.values()))!=len(id_for):
        raise ValueError('duplicate football fixture across seasons')
    computed={}
    for f in goal.feature_rows(predictor_input):
        if f['season'] not in ('2526','2627'):continue
        model=models[f['league']]['goals']
        if model['train_end']>=f['date']:raise ValueError('lookahead in original goal model')
        computed[f['id']]=goal.predict(model,f)
    benchmark=[r for r in benchmark if r['season']=='2526']
    old_errors=[float(np.max(np.abs(computed[r['match_id']]-r['rates']))) for r in benchmark]
    if len(old_errors)!=1737 or max(old_errors)>1e-12:
        raise ValueError(f'previous goal strengths were not reproduced, n={len(old_errors)} max={max(old_errors)}')
    eligible=[];excluded_counts=defaultdict(Counter)
    for row in new:
        key=(row['source_file'],row['source_line']);mid=id_for[key];reasons=[]
        if mid not in computed:reasons.append('insufficient_prior_goals_model_history')
        if panels[key] is None:reasons.append('missing_or_invalid_complete_Bet365_closing_panel')
        if reasons:
            exclusions.append(dict(row,match_id=mid,reasons=reasons))
            for why in reasons:excluded_counts[row['cohort']][why]+=1
            continue
        eligible.append(dict(row,match_id=mid,season='2627',historical_proxy=True,rates=computed[mid].tolist(),market=panels[key]))
    eligible=sequence_history.rolling_sequences(all_games,eligible)
    base_seq=json.loads((HERE/'sequence-before-season.json').read_bytes())
    trans=json.loads((HERE/'transformer-before-season.json').read_bytes())
    results=[]
    for row in eligible:
        if not max(base_seq['cutoff_at'],trans['cutoff_at'])[:10]<row['game_date']:
            raise ValueError('model cutoff overlaps target match')
        row['baseline_matrix']=sequence_history.fixed_market_baseline(row['rates'],row['market'])
        old,=evaluate(base_seq,[row])
        pred=apply_holdout(trans,row,old)
        pred['teams']=[row['home'],row['away']]
        pred['source']=[row['source_file'],row['source_line']]
        pred['raw_prices']=row['market']
        pred['goal_rates']=row['rates']
        pred['sequence_sources']=row['sequence_sources']
        results.append(pred)
    byleague={}
    for name,item in inventory.items():
        selected=[r for r in results if r['cohort']==name]
        item['evaluated']=len(selected)
        item['excluded_played']=item['played_in_source']-len(selected)
        item['reason_counts']=dict(excluded_counts[name])
        byleague[name]=summarize(selected)
    report={'schema':'TRANSFORMER-LATER-SEASON-REPLAY-1','method':'Archived original goals-only Poisson intensity coefficients and code. Each target uses results from strictly earlier dates. Fixed market projection constrained by Bet365 1X2 and 2.5 closing prices. Upstream history and downstream five-game histories are rebuilt separately.','population_rule':'All labeled 2026/27 fixtures in the five downloaded source files with match date through 2026-11-17 inclusive.','exclusions':exclusions,'inventory':inventory,'population_played_in_source':len(new),'evaluated':len(results),'coverage':len(results)/len(new),'original_prior_holdout_intensities':{'n':len(old_errors),'max_abs_error':max(old_errors),'runtime_sha256':GOAL_CODE_SHA,'weights_sha256':GOAL_SHA,'training_end_by_league':{k:m['goals']['train_end'] for k,m in models.items()}},'last_model_training_game':old_max,'residual_model_preseason_cutoff':base_seq['cutoff_at'],'residual_models':{s:sha((HERE/f'{s}-before-season.json').read_bytes()) for s in ('sequence','transformer')},'source_csv':json.loads((HERE/'raw/source-metadata.json').read_bytes()),'history_archive_sha256':past_source['archive_sha256'],'comparison':summarize(results),'by_cohort':byleague,'evidence':'Later chronological fixtures disjoint from the 3,036 residual-training observations. Data were retrieved after completion; individual quote times and original availability of results are not certified. The model recipe was decided after the season began. Not a prospective issue, a deployment of active Current, or a project-wide unseen-data claim.'}
    digest=b''.join((json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode() for r in results)
    deliver(out/'europe-2627-predictions.jsonl.gz',gzip.compress(digest,mtime=0))
    report['prediction_archive_sha256']=sha((out/'europe-2627-predictions.jsonl.gz').read_bytes())
    deliver(out/'europe-2627-validation.json',encoded(report))
    print(json.dumps({'n':len(results),'population':len(new),'arms':{k:v['hits'] for k,v in report['comparison']['arms'].items()}},sort_keys=True))

if __name__=='__main__':
    main()
