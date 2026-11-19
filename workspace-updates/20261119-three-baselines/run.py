"""Fixed offline three-arm comparison; never writes production or frozen assets."""
import argparse
import gzip
import hashlib
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar


def weights(rows, half_life=365):
    end=max(datetime.fromisoformat(r['date']) for r in rows)
    return np.array([2**(-(end-datetime.fromisoformat(r['date'])).days/half_life) for r in rows])


def ratio_fit(rows):
    # v2.fit_baseline equations, with the protocol's common 365-day decay.
    w=weights(rows); den=w.sum()
    hm=sum(r['home_goals']*v for r,v in zip(rows,w))/den
    am=sum(r['away_goals']*v for r,v in zip(rows,w))/den
    base=(hm+am)/2; teams={}
    for r,v in zip(rows,w):
        for t,gf,ga,ef,ea in [(r['home'],r['home_goals'],r['away_goals'],hm,am),(r['away'],r['away_goals'],r['home_goals'],am,hm)]:
            x=teams.setdefault(t,np.zeros(4)); x+=v*np.array([gf,ga,ef,ea])
    return {'method':'v01_baseline','home_mean':float(hm),'away_mean':float(am),'teams':{t:{'attack':float((v[0]+8*base)/(v[2]+8*base)),'concede':float((v[1]+8*base)/(v[3]+8*base))} for t,v in teams.items()},'nuisance':{'poisson':0}}


def rho_fit(model, rows, rates):
    lh,la=np.array([rates(model,r)[:2] for r in rows]).T
    hg=np.array([r['home_goals'] for r in rows]);ag=np.array([r['away_goals'] for r in rows]);w=weights(rows)
    def loss(rho):
        tau=np.ones(len(rows))
        for mask,t in [((hg==0)&(ag==0),1-lh*la*rho),((hg==0)&(ag==1),1+lh*rho),((hg==1)&(ag==0),1+la*rho),((hg==1)&(ag==1),np.full(len(rows),1-rho))]:tau[mask]=t[mask]
        return -float(np.dot(w,np.log(tau))/w.sum())
    fit=minimize_scalar(loss,bounds=(-.08,.006),method='bounded')
    if not fit.success:raise ValueError('rho fit failed')
    return float(fit.x)


def score(m,actual):
    flat=m.ravel();order=np.argsort(-flat,kind='stable')[:3]
    top=[list(map(int,np.unravel_index(i,m.shape))) for i in order]
    return {'primary':top[0],'top3':top,'top1_hit':int(top[0]==actual),'top3_hit':int(actual in top),'score_log_loss':-math.log(max(float(m[tuple(actual)]),1e-300)),'actual_probability':float(m[tuple(actual)])}


def summarize(rows, names, draws=3000):
    dates=sorted({r['date'] for r in rows});groups=[np.array([i for i,r in enumerate(rows) if r['date']==d]) for d in dates]
    rng=np.random.default_rng(20261007)
    # Date-cluster weights preserve unequal cluster sizes without flattening each draw.
    counts=rng.multinomial(len(groups),np.ones(len(groups))/len(groups),size=draws)
    sizes=np.array([len(g) for g in groups]);den=counts@sizes
    def ci(values):
        totals=np.array([np.sum(values[g]) for g in groups])
        return list(map(float,np.quantile((counts@totals)/den,[.025,.975])))
    output={}; base=names[0]
    for name in names:
        vals={k:np.array([r['arms'][name][k] for r in rows]) for k in ('top1_hit','top3_hit','score_log_loss')}
        output[name]={'n':len(rows),'top1_hits':int(vals['top1_hit'].sum()),'top3_hits':int(vals['top3_hit'].sum()),'top1':float(vals['top1_hit'].mean()),'top3':float(vals['top3_hit'].mean()),'score_log_loss':float(vals['score_log_loss'].mean()),'date_cluster_95_ci':{k:ci(v) for k,v in vals.items()},'unseen_team_matches':sum(bool(r['arms'][name]['unseen_teams']) for r in rows)}
        if name!=base:
            b=np.array([r['arms'][base]['top1_hit'] for r in rows]);a=vals['top1_hit']
            output[name]['vs_simple']={'wrong_to_right':int(((a==1)&(b==0)).sum()),'right_to_wrong':int(((a==0)&(b==1)).sum()),'net_hits':int((a-b).sum()),'changed_primary':sum(r['arms'][name]['primary']!=r['arms'][base]['primary'] for r in rows),'differences':{k:{'mean':float((v-np.array([r['arms'][base][k] for r in rows])).mean()),'date_cluster_95_ci':ci(v-np.array([r['arms'][base][k] for r in rows]))} for k,v in vals.items()}}
    return output


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    here=Path(__file__).resolve().parent; protocol=json.loads((here/'protocol.json').read_text())
    for name,h in protocol['source_file_sha256'].items():
        if hashlib.sha256((args.source/'runtime/v2'/name).read_bytes()).hexdigest()!=h:raise ValueError('source identity mismatch: '+name)
    sys.path.insert(0,str(args.source/'runtime/v2'))
    from model import fit_strength, rates, matrix, partitions
    from training_inputs import history_inputs
    raw=gzip.decompress((here/'EPL-history.json.gz').read_bytes())
    if hashlib.sha256(raw).hexdigest()!=protocol['input_sha256']:raise ValueError('input identity mismatch')
    rows=history_inputs(json.loads(raw));train,unused1,unused2,test=partitions(rows)
    assert max(r['date'] for r in train)<min(r['date'] for r in test)
    args.out.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone(timedelta(hours=8))).isoformat()
    simple=ratio_fit(train);adjusted=fit_strength(train,half_life=365,ridge=8);rho=rho_fit(adjusted,train,rates)
    names=protocol['arms'];pred=[];errors=[]
    for r in test:
        item={k:r[k] for k in ('match_id','cohort','date','home','away')};item.update(actual=[r['home_goals'],r['away_goals']],train_end=train[-1]['date'],date_only_cutoff=r['date'],arms={})
        for name,model,family,nuisance in [(names[0],simple,'poisson',0),(names[1],adjusted,'poisson',0),(names[2],adjusted,'dixon_coles',rho)]:
            try:
                lh,la,missing=rates(model,r);m=matrix(lh,la,family,nuisance,1)
                item['arms'][name]={**score(m,item['actual']),'rates':[lh,la],'unseen_teams':missing,'matrix_sha256':hashlib.sha256(m.tobytes()).hexdigest()}
            except ValueError as e:
                item['arms'][name]={'error':str(e)};errors.append({'match_id':r['match_id'],'arm':name,'error':str(e)})
        pred.append(item)
    common=[r for r in pred if all('error' not in r['arms'][n] for n in names)]
    report={'status':'DATE_ISOLATED_DEVELOPMENT_NOT_FUTURE_VALIDATION','started_at':started,'finished_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'protocol_sha256':hashlib.sha256((here/'protocol.json').read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'dataset_n':len(rows),'split':{n:{'n':len(b),'first_date':b[0]['date'],'last_date':b[-1]['date']} for n,b in zip(['train','unused_calibration','unused_selection','evaluation'],[train,unused1,unused2,test])},'target_n':len(test),'common_n':len(common),'coverage_by_arm':{n:sum('error' not in r['arms'][n] for r in pred) for n in names},'excluded_from_common':len(pred)-len(common),'errors':errors,'fitted_rho':rho,'rho_near_bound':min(abs(rho+.08),abs(rho-.006))<1e-4,'metrics':summarize(common,names),'historical_first_known_missing':sum(not r.get('first_known_at') for r in rows),'future_frozen_n':None,'future_status':'NOT_AVAILABLE_NOT_ZERO_HITS','fit_end_before_all_targets':True,'production_changed':False}
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (args.out/'rows.jsonl.gz').write_bytes(gzip.compress(('\n'.join(json.dumps(r,ensure_ascii=False) for r in pred)+'\n').encode(),mtime=0))
    (args.out/'development-fits.json').write_text(json.dumps({'simple':simple,'opponent':adjusted,'rho':rho,'status':'OFFLINE_ONLY_NOT_REGISTERED'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
