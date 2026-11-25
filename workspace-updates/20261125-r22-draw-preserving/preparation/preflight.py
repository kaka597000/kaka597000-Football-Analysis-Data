#!/usr/bin/env python3
"""Read-only R22 readiness check; no fitting, issuance, or seat ranking."""
import argparse,hashlib,json,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
LOCK=HERE/'source-lock.json'
DATA_ROOT=Path(__file__).resolve().parents[3]
R21=DATA_ROOT/'workspace-updates/20261125-r21-score-dependence'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tree_sha(root):
 import hashlib
 h=hashlib.sha256()
 for f in sorted(x for x in root.rglob('*') if x.is_file()):
  h.update(f.relative_to(root).as_posix().encode());h.update(b'\0');h.update(hashlib.sha256(f.read_bytes()).digest())
 return h.hexdigest()

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args();source=args.source.resolve();lock=json.loads(LOCK.read_bytes()); issues=[]
 protocol=source/lock['protocol_path']
 if not protocol.is_file() or sha(protocol)!=lock['protocol_sha256']:issues.append('R22 protocol file/hash differs from preregistration lock')
 commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 prereg=subprocess.check_output(['git','-C',str(source),'rev-parse',lock['preregistration_commit']],text=True).strip()
 if prereg!=lock['preregistration_commit']:issues.append('preregistration source commit unavailable')
 # Data branch must ultimately include the latest public R21 PR #61 head and its pushed numeric fix.
 data_head=subprocess.check_output(['git','-C',str(DATA_ROOT),'rev-parse','HEAD'],text=True).strip()
 ancestor=subprocess.run(['git','-C',str(DATA_ROOT),'merge-base','--is-ancestor',lock['current_public_data_pr61_head'],'HEAD']).returncode==0
 if not ancestor:issues.append('data worktree does not contain the exact public R21 PR #61 base commit')
 if commit!=lock['final_source_commit']:issues.append('source checkout is not the final pinned R22 commit')
 r21lock=json.loads((R21/'source-lock.json').read_bytes())
 for path,expected in [('replay/reference/metrics.json',None),('forward/receipts.json',lock['r21_parent']['forward_receipts_file_sha256']),('inputs/source-inputs.json',lock['r21_parent']['source_inputs_manifest_sha256']),('inputs/understat.tar.gz',r21lock['understat_archive_sha256'])]:
  f=R21/path
  if not f.is_file():issues.append('missing R21 parent '+path)
  elif expected and sha(f)!=expected:issues.append('R21 parent hash mismatch '+path)
 for rel,key in [('replay/reference','replay_reference_tree_sha256'),('replay/repeat','replay_repeat_tree_sha256'),('forward','forward_tree_sha256')]:
  if tree_sha(R21/rel)!=lock['r21_parent'][key]:issues.append('R21 parent tree hash mismatch '+rel)
 if lock['final_source_commit'] is None:issues.append('final R22 source commit is not locked')
 study_cli=source/'runtime/research_program/draw_preserving_study.py'
 model=source/'runtime/research_program/draw_preserving.py'
 if not model.is_file():issues.append('R22 score-grid model module missing')
 if not study_cli.is_file():issues.append('R22 fit/replay CLI not yet available')
 print(json.dumps({'status':'READY' if not issues else 'PREPARATION_BLOCKED','executor':'current Codex driver','source_worktree_head':commit,'preregistration_commit':prereg,'final_source_commit_locked':lock['final_source_commit'],'data_worktree_head':data_head,'r21_parent_base':lock['current_public_data_pr61_head'],'issues':issues,'side_effects':False},indent=2))
 return 0 if not issues else 2
if __name__=='__main__':raise SystemExit(main())
