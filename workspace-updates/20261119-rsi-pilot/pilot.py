"""Bounded RSI pilot: freeze once, certify results, report; never optimize or deploy."""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
SOURCE=Path('/workspace/Football-Analysis')
sys.path.insert(0,str(SOURCE/'runtime/v2'))
from model import fit_strength, rates, matrix
sys.path.insert(0,str(SOURCE/'runtime'))
from research.analysis_freeze import save, verify, aware, digest
from automation.research_api import certify_result
from research_program.portfolio_lifecycle import decide as lifecycle_decide
spec=importlib.util.spec_from_file_location('fixed_baselines',HERE.parent/'20261119-three-baselines/run.py')
baselines=importlib.util.module_from_spec(spec);spec.loader.exec_module(baselines)
ARMS=('simple_ratio_poisson','opponent_poisson')

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc)
def write_new(path,data):
    with Path(path).open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')

def check_training(rows,fixtures,cutoff):
    if len({(r['date'],r['home'],r['away']) for r in rows})!=len(rows):raise ValueError('duplicate training identity')
    if len(fixtures)!=10 or len({f['match_id'] for f in fixtures})!=10:raise ValueError('exact registered ten required')
    for f in fixtures:
        if not aware(f['cutoff_at'])==cutoff<aware(f['kickoff_at']):raise ValueError('non-prematch cutoff')
        if f['cohort']!='eng.1' or f['stage']!='regular-season' or f['status']!='scheduled':raise ValueError('fixture scope/state')
    for r in rows:
        if (r['cohort']!='EPL' or r['score_basis']!='regulation_90' or aware(r['observed_at'])>cutoff
            or r['date']>=cutoff.date().isoformat()):raise ValueError('later or incompatible training input')
        if any(r['date']==f['kickoff_at'][:10] and r['home']==f['model_home'] and r['away']==f['model_away'] for f in fixtures):raise ValueError('target leaked into training')
        if set(r)-{'match_id','cohort','date','home','away','home_goals','away_goals','score_basis','source_url','observed_at','neutral'}:raise ValueError('unapproved training field')

def freeze():
    policy=read(HERE/'protocol.json');fixtures=policy['fixtures'];cutoff=aware(policy['cutoff_at']);rows=json.loads(gzip.decompress((HERE/'training.json.gz').read_bytes()))
    if now()>=min(aware(f['kickoff_at']) for f in fixtures):raise ValueError('pilot already started')
    for path,h in policy['identities'].items():
        if sha(path)!=h:raise ValueError('locked input/source changed: '+path)
    check_training(rows,fixtures,cutoff)
    out=HERE/'batch';out.mkdir(exist_ok=False)
    models={ARMS[0]:baselines.ratio_fit(rows),ARMS[1]:fit_strength(rows,half_life=365,ridge=8)}
    write_new(out/'fits.json',models)
    pf=dict(fixtures[0],match_id='rsi:eng.1:20261121-23:pilot1')
    plan=save({'protocol':policy,'fits_sha256':sha(out/'fits.json')},pf,stage='prematch',track='rsi-bounded-plan',root=out/'records')
    write_new(out/'plan-receipt.json',plan);records=[];displays=[]
    for fixture in fixtures:
        query={'home':fixture['model_home'],'away':fixture['model_away'],'neutral':False};arms={}
        for name,model in models.items():
            try:
                lh,la,missing=rates(model,query)
                if missing:raise ValueError('unseen team, pilot requires current-season identity')
                m=matrix(lh,la);flat=np.argsort(-m.ravel(),kind='stable')[:3];scores=['%d-%d'%np.unravel_index(i,m.shape) for i in flat]
                arms[name]={'status':'PREDICTED','primary':scores[0],'matrix_top3':scores,'matrix':m.tolist(),'matrix_sha256':digest(m.tolist()),'rates':[lh,la],'selection':'statistical mode, not comprehensive recommendation'}
            except ValueError as e:arms[name]={'status':'ABSTAIN','reason':str(e)}
        receipt=save({'plan_sha256':plan['sha256'],'arms':arms},fixture,stage='prematch',track='rsi-two-arm-research',root=out/'records');records.append(receipt)
        # Actual displayed fields frozen independently. Missing comprehensive evidence is not replaced with model ranks.
        display={'status':'ABSTAIN','first_score':None,'alternatives':[{'score':None,'path':'待核实主队占优路径'},{'score':None,'path':'待核实客队反击/平局路径'}],'text':f"{fixture['model_home']} — {fixture['model_away']}：综合第一比分待定；备选一待定，备选二待定。当前只发布独立研究预测，尚无充分比赛路径证据。",'reason':'No verified current xG/personnel/path review in this offline pilot; do not relabel matrix Top3 or compared_scores as displayed recommendations.','research_receipt_sha256':receipt['sha256']}
        displays.append(save(display,fixture,stage='prematch',track='rsi-user-display',root=out/'records'))
    write_new(out/'index.json',{'plan':plan,'predictions':records,'displays':displays})
    print(json.dumps({'registered':len(fixtures),'research_records':len(records),'display_records':len(displays),'plan':plan},ensure_ascii=False))

def load_batch(batch):
    index=read(batch/'index.json');plan=verify(read(index['plan']['path']));policy=plan['payload']['protocol'];records={};fixtures={f['match_id']:f for f in policy['fixtures']}
    if plan['revision']!=1 or plan['stage']!='prematch' or plan['record_sha256']!=index['plan']['sha256']:raise ValueError('original plan required')
    for path,h in policy['identities'].items():
        if sha(path)!=h:raise ValueError('locked implementation/input changed')
    if sha(batch/'fits.json')!=plan['payload']['fits_sha256']:raise ValueError('artifact changed')
    for ref in index['predictions']:
        r=verify(read(ref['path']));f=r['fixture'];mid=f['match_id']
        if mid not in fixtures or f!=fixtures[mid] or mid in records or r['revision']!=1 or r['stage']!='prematch' or r['track']!='rsi-two-arm-research':raise ValueError('frozen identity changed')
        if not aware(f['cutoff_at'])<=aware(plan['recorded_at'])<=aware(r['recorded_at'])<aware(f['kickoff_at']):raise ValueError('freeze chronology')
        if r['payload']['plan_sha256']!=plan['record_sha256'] or set(r['payload']['arms'])!=set(ARMS):raise ValueError('plan or arm mismatch')
        for arm in r['payload']['arms'].values():
            if arm['status']=='ABSTAIN':continue
            m=np.array(arm['matrix']);top=['%d-%d'%np.unravel_index(i,m.shape) for i in np.argsort(-m.ravel(),kind='stable')[:3]]
            if not np.isfinite(m).all() or (m<0).any() or abs(m.sum()-1)>1e-9 or digest(arm['matrix'])!=arm['matrix_sha256'] or arm['primary']!=top[0] or arm['matrix_top3']!=top:raise ValueError('invalid matrix/selection')
        records[mid]=r
    if set(records)!=set(fixtures):raise ValueError('missing registered prediction/abstention')
    return policy,records

def decision(policy,completed,paired,net,loss_delta,at):
    if completed<10:
        return 'CLOSED_INCOMPLETE_AT_DEADLINE' if at>=aware(policy['review_deadline']) else 'PENDING'
    if paired<10:return 'CLOSED_INCOMPLETE_COVERAGE'
    if net<=0:return 'RETIRED_PILOT_NO_TOP1_GAIN'
    if loss_delta>0:return 'RETIRED_PILOT_PROBABILITY_REGRESSION'
    return 'RETAIN_SIGNAL_REQUEST_HUMAN_REVIEW_FOR_ONE_EXTENSION'

def review(state,out):
    policy,records=load_batch(HERE/'batch');at=now();retained={};issues=[]
    path=state/'normalized-results.jsonl'
    if path.exists():
        for line in path.read_text().splitlines():
            row=json.loads(line);mid=row.get('match_id')
            if mid not in records:continue
            try:r=certify_result(row,records[mid]['fixture'],state,at);retained.setdefault(mid,[]).append(r)
            except (ValueError,KeyError,OSError) as e:issues.append({'match_id':mid,'reason':str(e)})
    result={};conflicted=set()
    for mid,rs in retained.items():
        if len({(r['home'],r['away']) for r in rs})!=1:issues.append({'match_id':mid,'reason':'conflicting verified results'});conflicted.add(mid)
        else:result[mid]=rs[0]
    details=[];governance=[]
    for mid,r in records.items():
        actual=result.get(mid);outcomes={};failures=[]
        if actual:
            h,a=actual['home'],actual['away'];score=f'{h}-{a}'
            for name,arm in r['payload']['arms'].items():
                if arm['status']!='PREDICTED':continue
                m=np.array(arm['matrix']);pr=m[h,a] if h<m.shape[0] and a<m.shape[1] else 0;wd=np.array([np.tril(m,-1).sum(),np.trace(m),np.triu(m,1).sum()]);target=np.array([h>a,h==a,h<a])
                outcomes[name]={'score_top1':score==arm['primary'],'score_top3':score in arm['matrix_top3'],'score_log_loss':float(-np.log(max(pr,1e-300))),'wdl_brier':float(np.square(wd-target).sum()),'total_settlement':None}
                if not outcomes[name]['score_top1']:failures.append({'arm':name,'mode':'outside_top3' if not outcomes[name]['score_top3'] else 'ranking_within_top3','actual':score,'issued_primary':arm['primary'],'evidence':actual['source'],'next_change':None})
        details.append({'match_id':mid,'actual':actual,'outcomes':outcomes,'failure_modes':failures})
        governance.append({'match_id':mid,'matchday':r['fixture']['kickoff_at'][:10],'outcomes':outcomes if actual else None})
    paired=[r for r in details if set(r['outcomes'])==set(ARMS)];metrics={n:{'n':sum(n in r['outcomes'] for r in details),'top1_hits':sum(r['outcomes'].get(n,{}).get('score_top1',False) for r in details),'top3_hits':sum(r['outcomes'].get(n,{}).get('score_top3',False) for r in details)} for n in ARMS}
    gained=sum(r['outcomes'][ARMS[1]]['score_top1'] and not r['outcomes'][ARMS[0]]['score_top1'] for r in paired);lost=sum(r['outcomes'][ARMS[0]]['score_top1'] and not r['outcomes'][ARMS[1]]['score_top1'] for r in paired)
    delta=float(np.mean([r['outcomes'][ARMS[1]]['score_log_loss']-r['outcomes'][ARMS[0]]['score_log_loss'] for r in paired])) if paired else None
    for n in ARMS:
        for k in ('score_log_loss','score_top1','score_top3'):metrics[n][k]=float(np.mean([r['outcomes'][n][k] for r in details if n in r['outcomes']])) if metrics[n]['n'] else None
        if not metrics[n]['n']:metrics[n]['top1_hits']=metrics[n]['top3_hits']=None
    report={'reviewed_at':at.isoformat(),'registered_n':10,'verified_completed_n':len(result),'paired_n':len(paired),'pending_or_unverified_n':10-len(result),'metrics':metrics,'gained':gained,'lost':lost,'net_hits':gained-lost,'log_loss_delta':delta,'decision':decision(policy,len(result),len(paired),gained-lost,delta,at),'existing_lifecycle_diagnostic':lifecycle_decide(governance,list(ARMS),ARMS[0]),'issues':issues,'rows':details,'automatic_actions':[],'human_review_required':True,'promotion_allowed':False,'next_change':None}
    write_new(out,report);print(json.dumps({k:report[k] for k in ['registered_n','verified_completed_n','paired_n','decision']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True);sub.add_parser('freeze');r=sub.add_parser('review');r.add_argument('--state',type=Path,required=True);r.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.cmd=='freeze':freeze()
    else:review(a.state,a.out)
