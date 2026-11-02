import hashlib,json
from pathlib import Path
b=Path(__file__).resolve().parent;m=json.loads((b/'core-parts.json').read_text());p=b/m['whole_name']
if p.exists():raise SystemExit('Target already exists; no overwrite.')
h=hashlib.sha256()
with p.open('xb') as out:
 for c in m['ordered_parts']:
  x=(b/c['name']).read_bytes()
  if len(x)!=c['bytes'] or hashlib.sha256(x).hexdigest()!=c['sha256']:raise SystemExit('Part checksum mismatch: '+c['name'])
  out.write(x);h.update(x)
if h.hexdigest()!=m['whole_sha256']:raise SystemExit('Joined archive mismatch')
print('JOINED_AND_VERIFIED',p)
