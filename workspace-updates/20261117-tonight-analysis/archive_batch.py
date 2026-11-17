"""Archive this completed evidence batch without changing any frozen record."""
import hashlib,json,os,shutil,subprocess,tarfile
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).parent
D=Path('/workspace/kaka597000-Football-Analysis-Data/workspace-updates/20261117-tonight-analysis')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):
 with Path(p).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
assets=R/'retained-assets';assets.mkdir(exist_ok=False)
mapping=[];seen=set()
def retain(path,expected=None):
 p=Path(path);h=sha(p)
 if expected:assert h==expected, str(p)
 if str(p) in seen:return
 seen.add(str(p));target=assets/(h+'-'+p.name)
 if not target.exists():shutil.copyfile(p,target)
 mapping.append({'original_path':str(p),'archive_path':str(target.relative_to(R)),'sha256':h,'bytes':p.stat().st_size})
indices={
 'legacy':'/workspace/nations-model-20261110/models/candidates.json',
 'fixed':'/workspace/WCPP/research/nations-repair-20261116/experiment-v4/candidates.json',
 'xg':'/workspace/WCPP/research/nations-xg-20261117/experiment/index.json'}
used=[]
for kind,path in indices.items():
 retain(path);idx=read(path)
 for league in ('A','B'):
  roles=('current','test') if kind=='legacy' else ('fixed_current','fixed_test','challenger') if kind=='fixed' else ('goals',idx['selected'][league])
  for role in roles:
   ref=idx['routes'][league][role];retain(ref['path'],ref['sha256']);a=read(ref['path'])
   used.append({'kind':kind,'league':league,'role':role,**ref})
   for key in ('dataset','protocol','engine'):
    if a.get(key+'_path'):retain(a[key+'_path'],a[key+'_sha256'])
   for p,h in a.get('dependencies',{}).items():retain(p,h)
   for obj in a.get('inputs',{}).values():retain(obj['path'],obj['sha256'])
retain('/workspace/Football-Analysis-xg-retained-7dc5/runtime/nations_league/xg_research.py')
retain('/workspace/WCPP/research/nations-xg-20261117/protocol.json')
retain('/workspace/WCPP/runtime/active-model.json')
write(assets/'index.json',{'used_artifacts':used,'path_mapping':mapping,'note':'Full original indices retained; only the fourteen A/B artifacts actually used in this batch are included. Other routes remain in the prior evidence archives.'})
sources=[]
for p in ('/workspace/Football-Analysis','/workspace/Football-Analysis-nations-repair-20261116','/workspace/Football-Analysis-xg-retained-7dc5','/workspace/Football-Analysis-xg-research-20261117'):
 sources.append({'path':p,'commit':subprocess.check_output(['git','-C',p,'rev-parse','HEAD'],text=True).strip(),'status':subprocess.check_output(['git','-C',p,'status','--porcelain'],text=True)})
write(R/'publication/source-commits.json',sources)
creds={k:v for k,v in os.environ.items() if len(v)>=16 and '\n' not in v and not v.startswith('/') and any(s in k.lower() for s in ('token','secret','api_key','password','infer','odds','football','bsd','openfoot'))}
files=sorted(p for p in R.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for p in files:
 b=p.read_bytes()
 for key,value in creds.items():assert value.encode() not in b,('secret match',p.name,key)
D.mkdir(exist_ok=False)
archive=D/'tonight-evidence.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=6) as tf:
 for p in files:tf.add(p,arcname=str(p.relative_to(R)),recursive=False)
for name in ('publication','japan-revision'):
 shutil.copytree(R/name,D/name)
for name in ('verify_batch.py','archive_batch.py'):
 shutil.copyfile(R/name,D/name)
prior=[]
for rel in ('workspace-updates/20261117-nations-xg-research/manifest.json','workspace-updates/20261116-nations-repair/archive-index.json','workspace-updates/20261117-internationals-prematch/manifest.json'):
 p=D.parents[1]/rel;prior.append({'path':rel,'sha256':sha(p)})
manifest={'schema':'WCPP-TONIGHT-ARCHIVE-1','created_at':datetime.now(timezone.utc).isoformat(),'archive':archive.name,'archive_sha256':sha(archive),'bytes':archive.stat().st_size,'original_root':str(R),'source_commits':sources,'prior_source_archives':prior,
 'files':[{'member':str(p.relative_to(R)),'original_path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in files],
 'canonical_freeze_restore_mapping':[{'member':'publication/freezes/'+x['freeze_id']+'.json','original_path':x['path'],'file_sha256':sha(x['path'])} for x in read(R/'publication/freeze-receipts.json')]}
with tarfile.open(archive,'r:gz') as tf:
 for item in manifest['files']:assert hashlib.sha256(tf.extractfile(item['member']).read()).hexdigest()==item['sha256']
write(D/'manifest.json',manifest)
print(json.dumps({'archive':str(archive),'sha256':sha(archive),'files':len(files),'used_artifacts':len(used),'bytes':archive.stat().st_size,'verified_members':len(files)},ensure_ascii=False))
