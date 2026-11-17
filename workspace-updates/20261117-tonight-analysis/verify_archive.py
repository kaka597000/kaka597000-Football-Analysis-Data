"""Verify the long-lived archive without writing or publishing anything."""
import hashlib,json,tarfile
from pathlib import Path
R=Path(__file__).parent
m=json.loads((R/'manifest.json').read_text())
a=R/m['archive']
assert hashlib.sha256(a.read_bytes()).hexdigest()==m['archive_sha256']
with tarfile.open(a,'r:gz') as tf:
 assert sorted(x.name for x in tf.getmembers())==sorted(x['member'] for x in m['files'])
 for row in m['files']:
  b=tf.extractfile(row['member']).read()
  assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
  p=R/row['member']
  if p.exists():assert p.read_bytes()==b
 for row in m['canonical_freeze_restore_mapping']:
  assert hashlib.sha256(tf.extractfile(row['member']).read()).hexdigest()==row['file_sha256']
print(json.dumps({'status':'PASS','archive_members':len(m['files']),'freezes':len(m['canonical_freeze_restore_mapping']),'archive_sha256':m['archive_sha256']}))
