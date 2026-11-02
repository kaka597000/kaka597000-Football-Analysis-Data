import argparse,pathlib,json,hashlib,zipfile,subprocess,sys
p=pathlib.Path(__file__).resolve().parent;ap=argparse.ArgumentParser();ap.add_argument('--stage',required=True);a=ap.parse_args();m=json.loads((p/'parts.json').read_text());archive=p/'core.tar.gz'
if not archive.exists():
 h=hashlib.sha256()
 with archive.open('xb') as out:
  for x in m['ordered_parts']:
   b=(p/x['name']).read_bytes();assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'];out.write(b);h.update(b)
 assert h.hexdigest()==m['whole_sha256']
else:assert hashlib.sha256(archive.read_bytes()).hexdigest()==m['whole_sha256']
with zipfile.ZipFile(p/'control.zip') as z:
 for n in z.namelist():
  assert (p/n).resolve().is_relative_to(p)
 z.extractall(p)
subprocess.run([sys.executable,str(p/'restore.py'),'--packages',str(p),'--stage',a.stage,'--groups','core'],check=True)
