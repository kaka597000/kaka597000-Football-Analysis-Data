"""Read-only verification of the review archive and directly browsable copies."""
import hashlib,json,tarfile
from pathlib import Path
R=Path(__file__).parent
m=json.loads((R/'manifest.json').read_text());a=R/m['archive']
assert hashlib.sha256(a.read_bytes()).hexdigest()==m['sha256']
with tarfile.open(a,'r:gz') as tf:
 assert sorted(x.name for x in tf.getmembers())==sorted(x['member'] for x in m['files'])
 for row in m['files']:
  raw=tf.extractfile(row['member']).read();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
  p=R/row['member']
  if p.exists():assert raw==p.read_bytes()
for row in m.get('additional_files',[]):assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256']
print(json.dumps({'status':'PASS','archive_members':len(m['files']),'additional_files':len(m.get('additional_files',[])),'archive_sha256':m['sha256']}))
