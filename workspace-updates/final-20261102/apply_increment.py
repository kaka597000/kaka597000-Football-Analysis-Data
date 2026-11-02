"""Apply a verified delta only to a matching, separately restored base directory."""
import argparse,json,tarfile,hashlib,shutil,tempfile
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()

def apply(packages,base_packages,stage):
 packages=Path(packages).resolve();stage=Path(stage).resolve();base_packages=Path(base_packages).resolve()
 m=json.loads((packages/'manifest.json').read_text());base={x['path']:x for x in json.loads((base_packages/'files.json').read_text())};archive=packages/'changes.tar.gz'
 assert sha(archive)==m['archive_sha256'],'Increment archive mismatch'
 for entry in m['changed_files']:
  target=(stage/entry['path']).resolve()
  if not target.is_relative_to(stage):raise ValueError('unsafe target')
  if entry['kind']=='modified':
   assert target.is_file() and sha(target)==base[entry['path']]['sha256'],'Base differs; preserve local files before applying'
  else:assert not target.exists(),'Added target already exists; no overwrite'
 with tempfile.TemporaryDirectory(prefix='recovery-delta-',dir=stage.parent) as tmp:
  tmp=Path(tmp)
  with tarfile.open(archive,'r:gz') as tar:
   for member in tar.getmembers():
    target=(tmp/member.name).resolve()
    if not member.isfile() or not target.is_relative_to(tmp) or target.exists():raise ValueError('unsafe archive')
    tar.extract(member,tmp,filter='data')
  for entry in m['changed_files']:
   f=tmp/entry['path'];assert f.is_file() and f.stat().st_size==entry['bytes'] and sha(f)==entry['sha256'],'Changed file mismatch'
  for entry in m['changed_files']:
   target=stage/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(tmp/entry['path'],target)
 expected=dict(base);expected.update({x['path']:x for x in m['changed_files']})
 for name,entry in expected.items():
  f=stage/name;assert f.is_file() and f.stat().st_size==entry['bytes'] and sha(f)==entry['sha256'],'Combined restore mismatch: '+name
 return {'status':'passed','combined_files_verified':len(expected),'delta_files':len(m['changed_files']),'deletions_applied':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--packages',default=str(Path(__file__).resolve().parent));p.add_argument('--base-packages',required=True);p.add_argument('--stage',required=True);a=p.parse_args();print(json.dumps(apply(a.packages,a.base_packages,a.stage)))
