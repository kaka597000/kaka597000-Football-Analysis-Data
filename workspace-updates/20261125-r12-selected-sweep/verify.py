"""Independent reproduction of slot ordering, exact-score sweeps and signed R12 future rankings."""
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent
R10=ROOT.parent/'20261125-r10-shot-conversion'
spec=importlib.util.spec_from_file_location('r10_verify',R10/'verify.py')
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def rows(t,path):
    return list(map(json.loads,gzip.GzipFile(fileobj=t.extractfile(path))))


def estimate(p,three,pick,market,shots,weights):
    h,a=map(int,pick['primary'].split('-'))
    direction='home' if h>a else 'away' if a>h else 'draw'
    x=[1,6*(p/three-1/3),min(h,a)>0,h==a,(min(h+a,5)-2)/2,direction!=pick['wdl'],
       pick['primary']==market.get('primary'),not market.get('primary'),bool(shots)]
    z=math.log(p/(1-p))+sum(a*b for a,b in zip(x,weights,strict=True))
    return 1/(1+math.exp(-z))


def counts(ordered):
    exact=[r['primary']==r['actual'] for r in ordered]
    topthree=[r['actual'] in r['top3'] for r in ordered]
    return dict(planned_slots=3,occupied=len(ordered),settled=len(ordered),primary_hits=sum(exact),
        displayed_three_hits=sum(topthree),complete_batches=int(len(ordered)==3),
        primary_sweeps=int(len(ordered)==3 and all(exact)),displayed_three_sweeps=int(len(ordered)==3 and all(topthree)),
        pending=0)


def check_summary(batches,metrics):
    v.require(metrics['batch_dates']==len(batches) and metrics['candidate_pool']==sum(b['n'] for b in batches),'dated group totals')
    for a in ('control','candidate'):
        for k,n in metrics[a].items():v.require(n==sum(b[a][k] for b in batches),(a,k))
    v.require(metrics['sweep_change']['net']==metrics['candidate']['primary_sweeps']-metrics['control']['primary_sweeps'],'sweep delta')
    v.require(metrics['seat_change']['net']==metrics['candidate']['primary_hits']-metrics['control']['primary_hits'],'seat delta')


def replay():
    totals={}
    with tarfile.open(ROOT/'replay.tar.gz') as study:
        metrics=v.tar_json(study,'metrics.json')
        v.require(metrics==json.loads((ROOT/'metrics.json').read_bytes()),'metrics copy')
        for mode,summary in metrics.items():
            batches=[]
            with tarfile.open(R10/'replay'/(mode+'.tar.gz')) as source:
                for c,group in summary['competitions'].items():
                    folder=mode+'/'+c+'/'
                    baseline=rows(source,folder+'forecasts.jsonl.gz');pool=rows(study,folder+'pool.jsonl.gz')
                    fits=v.tar_json(study,folder+'fit.json');dates=defaultdict(list)
                    def early(r):
                        if mode=='main':return r['window']=='evaluation'
                        if mode=='independent':return r['date']<'2019-01-01'
                        return r['window']=='elite_known'
                    allowed={r['id']:r for r in baseline if not early(r)}
                    v.require(len(allowed)==len(pool) and set(allowed)=={r['id'] for r in pool} and
                              fits['fit_games']==sum(early(r) for r in baseline),c)
                    for r in pool:
                        b=allowed[r['id']];qual=b['quality']['candidate'];forecast=b['forecast'];p=forecast['candidate']
                        v.require(r['primary']==p['primary'] and r['top3']==p['top3'] and
                                  r['actual']=='-'.join(map(str,b['actual'])) and r['date']==b['date'] and
                                  (fits['through'] is None or r['date']>fits['through']),r['id'])
                        adjusted=estimate(qual['p_first'],qual['p_three'],p,forecast['market'],b['shot_ready'],fits['coef'])
                        v.require(r['raw']==qual['p_first'] and math.isclose(adjusted,r['adjusted'],abs_tol=1e-12),r['id'])
                        dates[r['date']].append(r)
                    seen=set();c_batches=rows(study,folder+'batches.jsonl.gz')
                    for b in c_batches:
                        day=b['date'];v.require(day not in seen and b['n']==len(dates[day]),day);seen.add(day)
                        for arm,field in [('control','raw'),('candidate','adjusted')]:
                            selected=sorted(dates[day],key=lambda r:(-r[field],r['id']))[:3]
                            v.require(b[arm]==dict(ids=[r['id'] for r in selected],**counts(selected)),(day,arm))
                    v.require(seen==set(dates),c);check_summary(c_batches,group);batches+=c_batches
            check_summary(batches,summary['overall']);totals[mode]=summary['overall']['control']['complete_batches']
    return totals


def future():
    with (tarfile.open(ROOT/'forward.tar.gz') as t, tarfile.open(R10/'forward/first-issues.tar.gz') as source,
          tarfile.open(R10/'forward/ranked.tar.gz') as r10):
        receipt=v.tar_json(t,'plan.json');plan=v.record(v.tar_json(t,receipt['file']),receipt)
        old=v.tar_json(r10,'plan.json');refs=v.tar_json(source,'receipts.json');ident=plan['payload']['identity']
        v.require(ident['r10_ranking_sha256']==old['sha256'] and ident['source_registration']==refs['registration']['sha256'],
                  'source registrations')
        weights_path=ROOT/'forward-weights.json';weights=json.loads(weights_path.read_bytes())
        v.require(v.sha(weights_path.read_bytes())==ident['weights_sha256'],'future weights')
        groups=defaultdict(list)
        for mid,ref in refs['matches'].items():
            rec=v.record(v.tar_json(source,ref['file']),ref);f=rec['fixture'];p=rec['payload'];q=p['quality']
            pick=p['forecasts']['candidate'];c=f['cohort']
            score=estimate(q['p_first'],q['p_three'],pick,p['forecasts']['market'],p['shot_ready'],weights[c]['coef'])
            groups[c].append((score,datetime.fromisoformat(f['kickoff_at']),mid,pick,ref))
        for c,actual in ident['choices'].items():
            best=sorted(groups[c],key=lambda x:(-x[0],x[1],x[2]))[:3];v.require(len(best)==len(actual),c)
            for (score,_,mid,pick,ref),r in zip(best,actual,strict=True):
                v.require(mid==r['match_id'] and r['top3']==pick['top3'] and r['primary']==pick['primary'] and
                          math.isclose(r['adjusted'],score,abs_tol=1e-12) and r['first_issue']==ref,mid)
        return sum(len(v) for v in ident['choices'].values())


if __name__=='__main__':
    m=json.loads((ROOT/'manifest.json').read_bytes())
    for file,expected in m['files'].items():
        with (ROOT/file).open('rb') as f:v.require(hashlib.file_digest(f,'sha256').hexdigest()==expected,file)
    print(json.dumps(dict(complete_batches=replay(),future_ranked_slots=future(),status='verified')))
