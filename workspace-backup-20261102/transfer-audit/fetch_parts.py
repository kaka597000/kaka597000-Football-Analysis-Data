import argparse,hashlib,json,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--group',choices=['core','models-history','audit-history','data-history'],default='core');a=p.parse_args();base='https://raw.githubusercontent.com/kaka597000/kaka597000-Football-Analysis-Data/handoff/wcpp-20261102/';folder=a.group+'-parts/';out=Path('.');req=lambda u:urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'WCPP-handoff-restore'}),timeout=120);m=json.load(req(base+folder+'parts.json'));target=out/m['whole_name']
if target.exists():raise SystemExit('Target exists; no overwrite')
h=hashlib.sha256()
with target.open('xb') as f:
 for part in m['ordered_parts']:
  file=out/part['name']
  if not file.exists():
   with req(base+folder+part['name']) as src,file.open('xb') as dst:
    while chunk:=src.read(1024*1024):dst.write(chunk)
  data=file.read_bytes()
  if len(data)!=part['bytes'] or hashlib.sha256(data).hexdigest()!=part['sha256']:raise SystemExit('Part mismatch: '+part['name'])
  f.write(data);h.update(data);print('VERIFIED',part['name'],flush=True)
if h.hexdigest()!=m['whole_sha256']:raise SystemExit('Joined file checksum mismatch')
print('JOINED_AND_VERIFIED',target)
