"""Complete the existing frozen 18-match queue and review the 52-match history."""
import hashlib,json,sys,shutil
from pathlib import Path
R=Path(__file__).parent;D=Path('/workspace/kaka597000-Football-Analysis-Data');SRC=Path('/workspace/Football-Analysis-xg-research-20261117')
sys.path[:0]=[str(SRC),str(SRC/'runtime'),str(SRC/'runtime/v5')]
from runtime.automation.nations_repair_cycle import result_from_raw,cycle
from runtime.publication import atomic_json
from runtime.storage_lock import exclusive_lock
from research.analysis_freeze import verify,digest
from v5.paired_review import review
from nations_league.repair_forward import validate_result
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,x):
 with (R/n).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
results=[r for r in read(R/'verified-results.json') if r['competition']=='uefa.nations']
state=D/'future/nations-repair-state';bundle=D/'future/nations-repair-bundle'
plan=verify(read(bundle/'plan.json'));fixtures={f['match_id']:f for f in plan['payload']['fixtures_identity']}
if (R/'forward-state-receipt.json').exists():
 saved=read(R/'forward-state-receipt.json');assert saved['settled']==18 and len(read(state/'results.json'))==18
 added=saved['added'];verify(read(saved['freeze_receipt']['path']))
else:
 with exclusive_lock(state/'.cycle.lock'):
  before=read(state/'results.json');out=list(before);known={r['match_id']:r for r in before};added=[]
  for r in results:
   mid=r['match_id']
   if mid in known:
    assert (known[mid]['home_goals'],known[mid]['away_goals'])==(r['home_goals'],r['away_goals']);continue
   src=Path(r['source_path']);target=state/'raw'/src.name
   with target.open('xb') as f:f.write(src.read_bytes())
   meta=src.with_suffix('.capture.json')
   if meta.exists():shutil.copyfile(meta,state/'raw'/meta.name)
   new=result_from_raw(fixtures[mid],target,r['source_url'],r['observed_at']);assert new
   out.append(dict(new,source_path=str(target.relative_to(state))));added.append(mid)
  assert out[:len(before)]==before and len(out)==len({x['match_id'] for x in out})==18
  atomic_json(state/'results.json',out)
 report=cycle(bundle,state,max_requests=0,max_seconds=40)
 assert report['settled']==18 and report['pending']==[] and report['result_requests']==0
 latest=max((state/'runs').glob('*.json'));run=read(latest);receipt=run['freeze_receipt'];verify(read(receipt['path']))
 write('forward-state-receipt.json',{'before_settled':len(before),'added':added,'settled':18,'pending':[],'result_requests':0,'new_inference':False,'run_path':str(latest),'run_sha256':sha(latest),'freeze_receipt':receipt,'official_conflict_resolution':str(R/'friendly-results/denmark-conflict-resolution.json')})
prior=Path('/workspace/WCPP/reports/nations-review-20261117-0818')
allresults=read(prior/'cumulative-inputs.json')['original_results']+read(prior/'verified-results.json')+results
assert len(allresults)==len({r['match_id'] for r in allresults})==52
pairs=[];refs=[]
for r in allresults:
 p=Path('/workspace/WCPP/forecasts/issued-analyses')/digest({'match_id':r['match_id'],'stage':'prematch','track':'nations-paired-candidates'})/'000001.json'
 z=verify(read(p));assert z['revision']==1
 # Older saved result schemas omit competition identity. Add fixture context
 # only to the verification call; the verifier independently re-parses raw IDs,
 # dates, stage and period scores. Original saved results remain unchanged.
 contextual={k:z['fixture'][k] for k in ('match_id','cohort','stage','home','away','kickoff_at')}
 validate_result(dict(contextual,**r),z['fixture'])
 pairs.append({'match_id':r['match_id'],'current_model':z['payload']['current'],'test_model':z['payload']['test']})
 refs.append({'path':str(p),'sha256':z['record_sha256'],'freeze_id':z['freeze_id']})
cumulative=review(pairs,allresults)
write('cumulative-first-candidates-52.json',cumulative)
write('cumulative-inputs.json',{'unique_matches':52,'results':allresults,'first_candidate_refs':refs,'prior_review_path':str(prior),'no_revisions_pooled':True})
print(json.dumps({'forward_settled':18,'added':len(added),'cumulative':52,'models':cumulative['models']},ensure_ascii=False))
