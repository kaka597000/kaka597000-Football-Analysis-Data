"""Lock the complete November 17 analysis population before fetching results."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
R=Path(__file__).parent
S=Path('/workspace/Football-Analysis-xg-research-20261117')
sys.path.insert(0,str(S/'runtime'))
from research.analysis_freeze import verify,save
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 with Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
inputs=[Path('/workspace/WCPP/reports/tonight-20261117-2100/publication/issued-analyses.json'),Path('/workspace/kaka597000-Football-Analysis-Data/workspace-updates/20261117-internationals-prematch/publication/published-analysis.json')]
issued=[row for p in inputs for row in read(p)]
assert len(issued)==11
fixtures={r['fixture']['match_id']:r['fixture'] for r in issued};assert len(fixtures)==11
frozen=R/'original-freezes';frozen.mkdir(exist_ok=True)
rows=[]
for p in Path('/workspace/WCPP/forecasts/issued-analyses').glob('*/*.json'):
 try:r=read(p)
 except (ValueError,OSError):continue
 if r.get('stage')!='prematch':continue
 mid=r['fixture']['match_id']
 is_batch=mid in ('international-friendlies-20261117-three-match-batch','nations-tonight-20261117-eight-match-analysis')
 if mid not in fixtures and not is_batch:continue
 verify(r)
 assert datetime.fromisoformat(r['recorded_at'])<datetime.fromisoformat(r['fixture']['kickoff_at'].replace('Z','+00:00'))
 copy=frozen/(r['freeze_id']+'.json')
 if copy.exists():assert copy.read_bytes()==p.read_bytes()
 else:copy.write_bytes(p.read_bytes())
 rows.append({'match_id':mid,'track':r['track'],'freeze_id':r['freeze_id'],'recorded_at':r['recorded_at'],'original_path':str(p),'archived_path':str(copy),'file_sha256':sha(p),'record_sha256':r['record_sha256']})
rows.sort(key=lambda x:(x['match_id'],x['track'],x['recorded_at']))
first={}
for row in rows:first.setdefault((row['match_id'],row['track']),row['freeze_id'])
for row in rows:row['evaluation_role']='FIRST_PREMATCH' if first[row['match_id'],row['track']]==row['freeze_id'] else 'SEPARATE_REVISION'
locked={'scope_date_bjt':'2026-11-17','locked_at':datetime.now(timezone.utc).isoformat(),'independent_matches':11,'fixtures':list(fixtures.values()),'issued_inputs':[{'path':str(p),'sha256':sha(p)} for p in inputs],'frozen_records':rows,'policy':'First prematch per original track is primary; Japan revision and evening reference updates remain separate. No best-of-model/arm/version selection. All 13 xG arms are preserved, selected arms fixed before outcomes.'}
write(R/'review-scope-lock.json',locked)
shell={'match_id':'all-analysis-review-20261117','kickoff_at':max(f['kickoff_at'] for f in fixtures.values()),'cutoff_at':locked['locked_at']}
receipt=save(locked,shell,stage='review',track='review-scope-lock')
write(R/'scope-lock-receipt.json',receipt)
print(json.dumps({'matches':11,'frozen_records':len(rows),'tracks':sorted(set(x['track'] for x in rows)),'lock_freeze':receipt},ensure_ascii=False))
