"""Verify and restore into a NEW directory; never overwrite running assets."""
import argparse,hashlib,json,pathlib,tarfile,tempfile
p=argparse.ArgumentParser();p.add_argument('--stage',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parent;stage=pathlib.Path(a.stage).resolve();assert not stage.exists(),'No overwrite allowed';m=json.loads((root/'manifest.json').read_text())
with tempfile.TemporaryDirectory(dir=stage.parent) as tmp:
 archive=pathlib.Path(tmp)/'artifacts.tar.gz';whole=hashlib.sha256();size=0
 with archive.open('xb') as dest:
  for entry in m['ordered_parts']:
   part=(root/entry['path']).resolve();assert part.is_relative_to(root)
   b=part.read_bytes();assert len(b)==entry['bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256'];dest.write(b);whole.update(b);size+=len(b)
 assert whole.hexdigest()==m['archive_sha256'] and size==m['archive_bytes']
 stage.mkdir();seen=set()
 with tarfile.open(archive,'r:gz') as tar:
  for entry in tar:
   dest=(stage/entry.name).resolve();assert dest.is_relative_to(stage) and (entry.isfile() or entry.isdir())
   if entry.isfile():
    assert entry.name not in seen;seen.add(entry.name)
   tar.extract(entry,stage,filter='data')
print(json.dumps({'stage':str(stage),'verified_archive_sha256':whole.hexdigest(),'files':len(seen),'active_assets_replaced':False}))
