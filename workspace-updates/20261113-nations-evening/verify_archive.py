"""Verify archived bytes and freeze chains; optionally restore into a new staging directory."""
import argparse,hashlib,json,tarfile
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text())
def verify(stage=None):
 root=Path(__file__).resolve().parent;repo=root.parent.parent
 m=read(root/'manifest.json');r=read(root/'recovery-map.json');retained={};archives=0
 for e in m['sidecar_files']:
  p=root/e['path'];assert sha(p.read_bytes())==e['sha256'],e['path']
 assert sha((root/m['archive']).read_bytes())==m['archive_sha256']
 with tarfile.open(root/m['archive']) as t:
  for e in m['members']:
   b=t.extractfile(e['archive_member']).read();assert sha(b)==e['sha256'];retained[e['original_path']]=b
 archives+=1
 for name,meta in r['reused_archives'].items():
  p=repo/name;assert sha(p.read_bytes())==meta['sha256'],name
  with tarfile.open(p) as t:
   for e in r['reused_files']:
    if e['repository_archive']!=name:continue
    b=t.extractfile(e['archive_member']).read();assert sha(b)==e['sha256'];retained[e['original_path']]=b
  archives+=1
 records={}
 for name,b in retained.items():
  if '/forecasts/issued-analyses/' not in name or not name.endswith('.json'):continue
  x=json.loads(b);body={k:v for k,v in x.items() if k!='record_sha256'}
  assert sha(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())==x['record_sha256'],name
  records[name]=x
 for name,x in records.items():
  if x['revision']==1:assert x['previous_sha256'] is None
  else:
   p=str(Path(name).with_name(f'{x["revision"]-1:06d}.json'));assert records[p]['record_sha256']==x['previous_sha256'],name
 if stage is not None:
  stage=Path(stage);assert not stage.exists(),'staging destination must be new';stage.mkdir(parents=True)
  for name,b in retained.items():
   relative=Path(name).relative_to('/workspace');assert '..' not in relative.parts
   p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 return {'status':'PASS','archives':archives,'retained_files':len(retained),'freeze_chain_records':len(records),'staging':str(stage) if stage else None,'source_checkout_separate':m['source_commit'],'no_source_or_freeze_mutation':True}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stage');a=p.parse_args();print(json.dumps(verify(a.stage),ensure_ascii=False))
