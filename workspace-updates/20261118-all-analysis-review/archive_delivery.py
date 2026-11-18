"""Persist the finished review and raw evidence without touching old predictions."""
import hashlib,json,os,shutil,tarfile
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).parent;D=Path('/workspace/kaka597000-Football-Analysis-Data');OUT=D/'workspace-updates/20261118-all-analysis-review'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
paths=sorted(p for p in R.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
creds={k:v for k,v in os.environ.items() if len(v)>=16 and '\n' not in v and not v.startswith('/') and any(s in k.lower() for s in ('token','secret','api_key','password','infer','odds','football','bsd','openfoot'))}
for p in paths:
 data=p.read_bytes()
 for key,value in creds.items():assert value.encode() not in data,('secret match',p.name,key)
OUT.mkdir(exist_ok=False);archive=OUT/'review-evidence.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=6) as tf:
 for p in paths:tf.add(p,arcname=str(p.relative_to(R)),recursive=False)
for p in R.iterdir():
 if p.is_file() and p.suffix in ('.json','.md','.csv','.py'):shutil.copyfile(p,OUT/p.name)
shutil.copytree(R/'review-freezes',OUT/'review-freezes')
receipts=read(R/'review-freeze-receipts.json')+[read(R/'scope-lock-receipt.json')]
prior=[]
for rel in ('workspace-updates/20261117-tonight-analysis/manifest.json','workspace-updates/20261117-internationals-prematch/manifest.json','workspace-updates/20261117-nations-xg-research/manifest.json','workspace-updates/20261116-nations-repair/archive-index.json'):
 prior.append({'path':rel,'sha256':sha(D/rel)})
manifest={'schema':'WCPP-ALL-ANALYSIS-REVIEW-ARCHIVE-1','created_at':datetime.now(timezone.utc).isoformat(),'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'original_root':str(R),'files':[{'member':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p),'original_path':str(p)} for p in paths],'prior_evidence_manifests':prior,'review_freezes':[{'path':r['path'],'freeze_id':r['freeze_id'],'record_sha256':r['sha256'],'file_sha256':sha(r['path'])} for r in receipts],'forward_state':read(R/'forward-state-receipt.json'),'scope':'11 unique matches; Japan revision separate; 77 original prematch freezes unchanged; no fabricated historical forecasts'}
with tarfile.open(archive,'r:gz') as tf:
 for p in manifest['files']:assert hashlib.sha256(tf.extractfile(p['member']).read()).hexdigest()==p['sha256']
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'verified_members':len(paths)},ensure_ascii=False))
