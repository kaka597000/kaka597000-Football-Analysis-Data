"""Verify durable evidence and independently recompute policy settlement counts."""
import argparse,collections,hashlib,json,tarfile
from pathlib import Path

def sha(body):return hashlib.sha256(body).hexdigest()
def verify(out=None):
 root=Path(__file__).resolve().parent;manifest=json.loads((root/'manifest.json').read_text())
 body=(root/manifest['archive']).read_bytes()
 assert len(body)==manifest['bytes'] and sha(body)==manifest['sha256']
 expected={r['path']:r for r in manifest['members']};assert len(expected)==len(manifest['members'])
 saved={}
 with tarfile.open(root/manifest['archive']) as tar:
  for member in tar:
   p=Path(member.name);assert member.isfile() and not p.is_absolute() and '..' not in p.parts
   assert member.name in expected and member.name not in saved
   raw=tar.extractfile(member).read();wanted=expected[member.name]
   assert len(raw)==wanted['bytes'] and sha(raw)==wanted['sha256'];saved[member.name]=raw
 assert set(saved)==set(expected)
 for p in root.rglob('*.json'):
  name=str(p.relative_to(root))
  if name in saved:assert p.read_bytes()==saved[name]
 def read(name):return json.loads(saved[name])
 tests=read('integration-summary.json');assert tests['failed_suites']==tests['skipped']==0 and tests['test_executions']==982
 replay=read('infer-replay/summary.json')
 assert replay['before']['covered_fixture_count']==0
 assert replay['after_today_alias_review']['covered_fixture_count']==replay['population']==8
 assert replay['after_today_alias_review']['verified_quote_count']==51 and replay['retrospective_identity_replay']
 assert replay['legacy_capture_time_proxy'] and replay['new_forecasts']==0
 for original in read('retained-original-paths.json'):
  assert sha(saved[original['archived_relative_path']])==original['sha256']
 rows=read('total-objectives/rows.json');report=read('total-objectives/report.json');groups=report['model_groups']
 assert len(rows)==report['policy_rows']==776
 assert len({r['match_id'] for r in rows})==report['unique_matches']==18
 assert len({(r['experiment'],r['track'],r['match_id']) for r in rows})==report['matrix_quote_pairs']==194
 for group,policies in groups.items():
  experiment,track=group.split(':');subset=[r for r in rows if (r['experiment'],r['track'])==(experiment,track)]
  base={r['match_id']:r for r in subset if r['policy']=='settlement_balance'}
  for policy,summary in policies.items():
   selected=[r for r in subset if r['policy']==policy];counts=collections.Counter(r['settlement'] for r in selected)
   assert len(selected)==summary['n'] and counts==collections.Counter(summary['settlements'])
   non=len(selected)-counts['push'];assert non==summary['non_push_n']
   assert summary['strict_full_win_rate']==counts['win']/non
   assert summary['net_full_wins']==counts['win']-sum(r['settlement']=='win' for r in base.values())
   for row in selected:
    original=base[row['match_id']]
    assert all(row[k]==original[k] for k in ('record_sha256','matrix_hash','line','bookmaker','quote_time','actual'))
 assert report['original_forecasts_unchanged'] and report['new_future_samples']==0
 assets=read('active-assets-verified.json');assert assets['verified_artifacts']==38 and not assets['active_model_changed']
 if out:
  out=Path(out);out.mkdir(parents=True,exist_ok=False)
  for name,raw in saved.items():
   p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 print(json.dumps({'verified_members':len(saved),'tests':tests['test_executions'],'replay_covered':8,'replay_quotes':51,'unique_matches':18,'matrix_quote_pairs':194,'policy_rows':776,'new_future_samples':0,'active_model_changed':False}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out');verify(p.parse_args().out)
