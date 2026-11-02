"""Fetch fixed base and restore it plus this delta; never overwrite a workspace."""
import argparse,json,subprocess,tarfile,sys,hashlib
from pathlib import Path
from apply_increment import apply,sha

def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--base-packages');a=p.parse_args();here=Path(__file__).resolve().parent;repo=here.parents[1];stage=Path(a.stage).resolve()
 if stage.exists():raise SystemExit('Destination exists. Choose a new staging directory; nothing overwritten.')
 m=json.loads((here/'manifest.json').read_text());base=Path(a.base_packages).resolve() if a.base_packages else repo/'.recovery-cache/workspace-backup-20261102'
 if not a.base_packages:
  if subprocess.run(['git','-C',str(repo),'cat-file','-e',m['base_commit']+'^{commit}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
   subprocess.run(['git','-C',str(repo),'fetch','--depth=1','origin','refs/tags/'+m['base_tag']],check=True)
  if not base.exists():
   cache=base.parent;cache.mkdir(parents=True,exist_ok=True);proc=subprocess.Popen(['git','-C',str(repo),'archive',m['base_commit'],'workspace-backup-20261102'],stdout=subprocess.PIPE)
   with tarfile.open(fileobj=proc.stdout,mode='r|') as tar:
    for member in tar:
     target=(cache/member.name).resolve()
     if not target.is_relative_to(cache) or not (member.isfile() or member.isdir()):raise ValueError('Unsafe base archive')
     tar.extract(member,cache,filter='data')
   if proc.wait()!=0:raise RuntimeError('Base extraction failed')
 checks=json.loads((base/'CONTROL-SHA256.json').read_text())
 for name,digest in checks.items():assert sha(base/name)==digest,'Base control checksum mismatch'
 subprocess.run([sys.executable,str(base/'restore.py'),'--packages',str(base),'--stage',str(stage)],check=True)
 result=apply(here,base,stage)
 subprocess.run([sys.executable,str(base/'incoming-core/restore_incoming.py'),'--stage',str(stage/'incoming-20261102')],check=True)
 (stage/'RECOVERY-RECEIPT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));print('Read FINAL-HANDOFF.md; restore Git metadata/secure settings before activating. No production paths were replaced.')
if __name__=='__main__':main()
