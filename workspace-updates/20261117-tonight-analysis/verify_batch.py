"""Offline matrix replays and immutable evidence checks; no forecast publication."""
import argparse,hashlib,json,math,os,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
R=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['legacy','fixed','xg','records']);args=ap.parse_args()
sources={'legacy':'/workspace/Football-Analysis','fixed':'/workspace/Football-Analysis-nations-repair-20261116','xg':'/workspace/Football-Analysis-xg-retained-7dc5','records':'/workspace/Football-Analysis-xg-research-20261117'}
sys.path.insert(0,sources[args.kind]+'/runtime')
from research.analysis_freeze import verify,digest,aware
checked=0
if args.kind=='legacy':
 from nations_league.model import distribution
 index=read('/workspace/nations-model-20261110/models/candidates.json')
 for rec in read(R/'nations/paired/receipts.json'):
  r=verify(read(rec['path']));f=r['fixture']
  for role in ('current','test'):
   ref=index['routes'][f['league_level']][role];a=read(ref['path']);assert sha(ref['path'])==ref['sha256']
   matrix,_,_=distribution(a['core'],role,f);pred=r['payload'][role]
   assert digest(matrix.tolist())==pred['matrix_hash'];checked+=1
elif args.kind=='fixed':
 from nations_league import repair
 index=read('/workspace/WCPP/research/nations-repair-20261116/experiment-v4/candidates.json')
 for file in (R/'nations/fixed').glob('401*.json'):
  bundle=read(file);f=bundle['fixture']
  for role,pred in bundle['payload']['predictions'].items():
   ref=index['routes'][f['league_level']][role];a=read(ref['path']);assert sha(ref['path'])==ref['sha256'] and a['dependencies']==repair.dependency_identity()
   matrix,_,_=repair.distribution(a['core'],a['recipe'],f,a['numeric_role'],a['temperature'])
   assert digest(matrix.tolist())==pred['matrix_hash'];checked+=1
  for role,pred in bundle['payload']['venue_sensitivity'].items():
   a=read(index['routes'][f['league_level']][role]['path']);matrix,_,_=repair.distribution(a['core'],a['recipe'],dict(f,neutral=True),a['numeric_role'],a['temperature'])
   assert digest(matrix.tolist())==pred['matrix_hash'];checked+=1
elif args.kind=='xg':
 from nations_league import repair,xg_research
 from v2.model import rates
 index=read('/workspace/WCPP/research/nations-xg-20261117/experiment/index.json')
 for file in (R/'nations/xg').glob('401*.json'):
  bundle=read(file);f=bundle['fixture']
  for role,pred in dict(bundle['payload']['predictions']).items():
   ref=index['routes'][f['league_level']][role];a=read(ref['path']);assert sha(ref['path'])==ref['sha256'] and a['engine_sha256']==sha(xg_research.__file__)
   h,aw,_=rates(a['core'],f);matrix=repair.probability_matrix(h,aw);assert digest(matrix.tolist())==pred['matrix_hash'];checked+=1
  for role,pred in bundle['payload']['venue_sensitivity'].items():
   a=read(index['routes'][f['league_level']][role]['path']);h,aw,_=rates(a['core'],dict(f,neutral=True));matrix=repair.probability_matrix(h,aw)
   assert digest(matrix.tolist())==pred['matrix_hash'];checked+=1
else:
 from prediction_engine import predict_models
 from research_program.future_validation import quote_audit
 from v2.model import total_settlement
 errors=[]
 for p in read(R/'publication/issued-analyses.json'):
  r=verify(read(p['freeze']['path']));assert r['payload']==p['payload'] and r['fixture']==p['fixture']
  f=p['fixture'];assert quote_audit(f)['eligible'];assert r['selection_audit']['top3_ready']
  try:predict_models(f,Path('/workspace/WCPP/runtime/active-model.json'))
  except ValueError as e:errors.append({'match_id':f['match_id'],'current':'UNAVAILABLE','test':'UNAVAILABLE','actual_error':str(e)})
  else:raise AssertionError('Unexpected active route; review needed')
 for rec in read(R/'publication/freeze-receipts.json'):
  r=verify(read(rec['path']));archived=R/'publication/freezes'/(rec['freeze_id']+'.json');assert archived.read_bytes()==Path(rec['path']).read_bytes()
  if r['stage']=='prematch':assert aware(r['fixture']['cutoff_at'])<=aware(r['recorded_at'])<aware(r['fixture']['kickoff_at'])
  checked+=1
 xgrows=read('/workspace/WCPP/research/nations-xg-20261117/data/xg-records.json')['rows']
 valid=[x for x in xgrows if all(type(v) in (int,float) and math.isfinite(v) for field in ('expected','actual','shotmap') for v in x['values'][field])]
 assert len(valid)==29
 for x in valid:assert sha(x['source_path'])==x['source_sha256']
 # Exact known settlements: integer 2 pushes; under 3.25 at 3 wins half;
 # over 2.75 at 3 wins half. These validate the actual report's line semantics.
 m=np.zeros((51,51));m[1,1]=1;assert total_settlement(m,2.,'under')['push']==1
 m[:]=0;m[2,1]=1;assert total_settlement(m,3.25,'under')['half_win']==1 and total_settlement(m,2.75,'over')['half_win']==1
 # Detect real environment credentials without printing their contents.
 creds={k:v for k,v in os.environ.items() if len(v)>=16 and '\n' not in v and not v.startswith('/') and any(s in k.lower() for s in ('token','secret','api_key','password','infer','odds','football','bsd','openfoot'))}
 for file in R.rglob('*'):
  if not file.is_file():continue
  b=file.read_bytes()
  for key,value in creds.items():assert value.encode() not in b,('secret match',file.name,key)
 (R/'publication/active-route-status.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
result={'kind':args.kind,'checks':checked,'status':'PASS','verified_at_utc':datetime.now(timezone.utc).isoformat(),'source':sources[args.kind]}
with (R/'publication'/('verification-'+args.kind+'.json')).open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
