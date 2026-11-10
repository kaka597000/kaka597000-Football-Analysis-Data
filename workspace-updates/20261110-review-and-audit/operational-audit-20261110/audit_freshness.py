import json,gzip,hashlib,csv,collections,traceback
from pathlib import Path
from datetime import datetime,timezone
B=Path(__file__).parent;D=Path('/workspace/kaka597000-Football-Analysis-Data');R=Path('/workspace/WCPP/runtime/active-model.json');now=datetime.now(timezone.utc)
inc=[json.loads(line)for line in (D/'normalized-results.jsonl').read_text().splitlines()if line.strip()];valid={};bad=[];conflicts=set()
for row in inc:
 try:
  ref=row['raw_reference'];p=(D/ref['path']).resolve();assert p.is_relative_to(D)
  raw=gzip.decompress(p.read_bytes());assert hashlib.sha256(raw).hexdigest()==ref['sha256']
  j=json.loads(raw);h=j['header'];c=h['competitions'][0];assert c['status']['type']['completed']is True and j['format']['regulation']['periods']==2
  assert row['match_id']=='espn:'+str(h['id']);assert row['score_basis']=='regulation_90'
  teams={t['homeAway']:t for t in c['competitors']}
  for side in ['home','away']:
   t=teams[side];assert row[side]=='espn:'+str(t['team']['id']);periods=t['linescores'][:2];assert len(periods)==2
   assert row[side+'_goals']==sum(float(x.get('value',x.get('displayValue')))for x in periods)
  known=datetime.fromisoformat(row['known_at']);kick=datetime.fromisoformat(row.get('kickoff_at',c['date']).replace('Z','+00:00'));assert known<=now and known>=kick
  assert kick.date().isoformat()==row['date']
  key=(row['cohort'],row['match_id']);score=(row['home_goals'],row['away_goals'])
  if key in valid and score!=(valid[key]['home_goals'],valid[key]['away_goals']):conflicts.add(key)
  valid[key]=row
 except (AssertionError,KeyError,ValueError,OSError,TypeError)as e:bad.append({'match_id':row.get('match_id'),'error_type':type(e).__name__,'check_line':traceback.extract_tb(e.__traceback__)[-1].lineno,'detail':str(e)})
for key in conflicts:valid.pop(key,None)
reg=json.loads(R.read_text());ci=json.loads((D/'candidate-index.json').read_text());out=[]
for cohort,route in reg['models'].items():
 available=[v for (k,_),v in valid.items()if k==cohort];latest=max((v['date']for v in available),default=None);candidate=ci['models'].get(cohort,{})
 for role,prefix in [('current',''),('test','test_')]:
  p=Path(route[prefix+'artifact_path']);data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==route[prefix+'artifact_sha256'];a=json.loads(data)
  # Current legacy execution uses the anchor. ML test must use its own fit cutoff.
  engine=route.get(prefix+'engine','legacy_weighted_anchor'if role=='current'else'legacy_ml')
  executed=a.get('anchor',a)if role=='current'else a
  end=executed.get('train_end')or executed.get('core',{}).get('fit_end')
  after=[v for v in available if end and v['date']>end]
  out.append({'cohort':cohort,'role':role,'engine':engine,'version':executed.get('version'),'active_training_end':end,'latest_verified_local_result':latest,'newer_verified_matches':len(after),'gap_days':(datetime.fromisoformat(latest)-datetime.fromisoformat(end)).days if end and latest and latest>end else 0,'candidate_fit_end':candidate.get('fit_end'),'candidate_status':candidate.get('status'),'candidate_baseline_top1':candidate.get('baseline_top1_hits'),'candidate_top1':candidate.get('candidate_top1_hits'),'candidate_audit_n':candidate.get('audit_n'),'artifact_path':str(p),'artifact_sha256':route[prefix+'artifact_sha256'],'newer_match_ids':[v['match_id']for v in after]})
report={'observed_at':now.isoformat(),'registry_sha256':hashlib.sha256(R.read_bytes()).hexdigest(),'local_results_sha256':hashlib.sha256((D/'normalized-results.jsonl').read_bytes()).hexdigest(),'input_observations':len(inc),'verified_unique_matches':len(valid),'rejected':bad,'conflicting_match_count':len(conflicts),'routes':out,'limitations':['Local persisted evidence only; not complete latest fixtures audit','Raw hash, identity and period score checked; competition/phase retains collector classification','Missing historical first-known timestamps not reconstructed','Candidate diagnostic baseline is not the active current/test model; not promotion evidence']}
(B/'freshness.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
with (B/'训练鲜度.csv').open('w',encoding='utf-8-sig',newline='')as f:
 keys=[k for k in out[0]if k!='newer_match_ids'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(out)
print('raw checks',len(inc),'verified unique',len(valid),'rejected',len(bad),'conflicts',len(conflicts));print('routes with newer verified data',sum(x['newer_verified_matches']>0 for x in out),'of',len(out))
for x in out[::2]:print(x['cohort'],x['active_training_end'],x['latest_verified_local_result'],x['newer_verified_matches'])
