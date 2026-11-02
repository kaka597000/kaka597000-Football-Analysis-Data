"""Restore reviewed archives into a NEW staging directory; never overwrite a checkout."""
import argparse,csv,hashlib,json,sqlite3,tarfile
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--packages',required=True);p.add_argument('--stage',required=True);p.add_argument('--groups',nargs='+',default=['core']);a=p.parse_args()
 source=Path(a.packages).resolve();stage=Path(a.stage).resolve()
 if stage.exists():raise SystemExit('Stage exists: choose a new directory. No overwrite performed.')
 for group in a.groups:
  m=json.loads((source/(group+'.manifest.json')).read_text());file=source/m['path']
  if digest(file)!=m['sha256']:raise SystemExit('Archive SHA256 mismatch: '+group)
 stage.mkdir(parents=True)
 for group in a.groups:
  m=json.loads((source/(group+'.manifest.json')).read_text());file=source/m['path']
  with tarfile.open(file,'r:gz') as tar:
   members=tar.getmembers()
   for t in members:
    target=(stage/t.name).resolve()
    if not target.is_relative_to(stage) or not t.isfile() or target.exists():raise SystemExit('Unsafe or duplicate archive entry: '+t.name)
   tar.extractall(stage,filter='data')
  print('EXTRACTED',group)
 verified=0
 with (source/'files.csv').open() as stream:
  for row in csv.DictReader(stream):
   if row['archive_group'] not in a.groups:continue
   target=stage/row['path']
   if not target.is_file() or target.stat().st_size!=int(row['bytes']) or digest(target)!=row['sha256']:raise SystemExit('Restored file mismatch: '+row['path'])
   verified+=1
 root=stage/'WCPP';reg=json.loads((root/'runtime/active-model.json').read_text());artifacts=0
 for co,entry in reg['models'].items():
  for key,hkey in [('artifact_path','artifact_sha256'),('test_artifact_path','test_artifact_sha256')]:
   if not entry.get(key):continue
   old=Path(entry[key]);file=root/old.relative_to('/workspace/WCPP')
   if digest(file)!=entry[hkey]:raise SystemExit('Active model mismatch: '+co)
   artifacts+=1
 for rel in ['data/unified/WCPP_统一赛事库.sqlite','packages/core-2026-09-29/WCPP_赛事数据库_统一合并版_2026-09-29.sqlite']:
  db=root/rel;c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.execute('pragma query_only=on');assert c.execute('pragma quick_check').fetchone()[0]=='ok';c.close()
 print(json.dumps({'verified_files':verified,'active_artifacts':artifacts,'cohorts':len(reg['models']),'stage':str(stage),'production_directories_changed':False}))
 print('STOP: Inspect the target workspace and preserve its local edits before moving staged WCPP into place.')
if __name__=='__main__':main()
