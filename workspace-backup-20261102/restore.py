"""Verify and restore a private workspace backup into a NEW directory only."""
import argparse,hashlib,json,tarfile,sqlite3,io
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
class Parts(io.RawIOBase):
 def __init__(self,paths):self.paths=iter(paths);self.f=None
 def readable(self):return True
 def readinto(self,b):
  while True:
   if self.f is None:
    try:self.f=next(self.paths).open('rb')
    except StopIteration:return 0
   n=self.f.readinto(b)
   if n:return n
   self.f.close();self.f=None

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--packages',default=str(Path(__file__).resolve().parent));ap.add_argument('--stage',required=True);a=ap.parse_args();src=Path(a.packages).resolve();dest=Path(a.stage).resolve()
 if dest.exists():raise SystemExit('Stage already exists. No overwrite allowed.')
 m=json.loads((src/'parts.json').read_text());paths=[];whole=hashlib.sha256();size=0
 for entry in m['parts']:
  p=src/'parts'/entry['name'];assert p.stat().st_size==entry['bytes'] and sha(p)==entry['sha256'],'Part hash mismatch'
  with p.open('rb') as f:
   while b:=f.read(1024*1024):whole.update(b);size+=len(b)
  paths.append(p)
 assert size==m['whole_bytes'] and whole.hexdigest()==m['whole_sha256'],'Whole archive hash mismatch'
 dest.mkdir(parents=True)
 with io.BufferedReader(Parts(paths)) as stream,tarfile.open(fileobj=stream,mode='r|gz') as tar:
  for member in tar:
   target=(dest/member.name).resolve()
   if not member.isfile() or not target.is_relative_to(dest) or target.exists():raise ValueError('Unsafe or duplicate archive member')
   tar.extract(member,dest,filter='data')
 count=0;dbs=0
 for entry in json.loads((src/'files.json').read_text()):
  p=dest/entry['path'];assert p.is_file() and p.stat().st_size==entry['bytes'] and sha(p)==entry['sha256'],entry['path']
  if entry.get('sqlite_consistent_backup'):
   c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);assert c.execute('pragma quick_check').fetchone()[0]=='ok';c.close();dbs+=1
  count+=1
 print(json.dumps({'verified_files':count,'databases_checked':dbs,'stage':str(dest),'production_overwritten':False}))
 print('Read README.md and excluded.json before activating. Supply secrets through secure environment settings.')
if __name__=='__main__':main()
