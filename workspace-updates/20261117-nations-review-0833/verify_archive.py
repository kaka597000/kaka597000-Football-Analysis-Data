"""Read-only offline replay from the archive; no API, model loading or fitting."""
import argparse,hashlib,json,sys,tarfile,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);args=p.parse_args()
source=Path(args.source).resolve();sys.path[:0]=[str(source/'runtime'),str(source/'runtime/v5')]
from research.analysis_freeze import verify
from nations_league.repair_forward import review
from v5.paired_review import review as paired_review
D=Path(__file__).resolve().parent;read=lambda p:json.loads(Path(p).read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=read(D/'manifest.json');archive=D/manifest['archive']['file'];assert sha(archive.read_bytes())==manifest['archive']['sha256']
with tempfile.TemporaryDirectory(prefix='nations-review-replay-') as tmp:
 root=Path(tmp)
 with tarfile.open(archive,'r:gz') as tar:
  members={m.name:m for m in tar.getmembers()};assert set(members)=={x['path'] for x in manifest['files']}
  for item in manifest['files']:
   member=members[item['path']];assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
   body=tar.extractfile(member).read();assert sha(body)==item['sha256'] and len(body)==item['bytes']
   target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
 def local(path):
  parts=Path(path).parts
  if 'WCPP' in parts:return root.joinpath('WCPP',*parts[parts.index('WCPP')+1:])
  if 'kaka597000-Football-Analysis-Data' in parts:return root.joinpath('kaka597000-Football-Analysis-Data',*parts[parts.index('kaka597000-Football-Analysis-Data')+1:])
  raise ValueError('unsupported evidence path')
 R=root/'WCPP/reports/nations-review-20261117-0818';lock=read(R/'review-scope-lock.json');metrics=read(R/'metrics.json')
 results=[dict(r,source_path=str(local(r['source_path']))) for r in read(R/'verified-results.json')]
 forward=review(local(lock['repair_bundle']),results);assert forward==metrics['repair_original_forward']
 pairs=[]
 for item in lock['fixtures']:
  ref=item['tracks']['candidate']['first'];z=verify(read(local(ref['path'])));assert z['record_sha256']==ref['sha256']
  pairs.append(dict(match_id=z['match_id'],current_model=z['payload']['current'],test_model=z['payload']['test']))
 assert paired_review(pairs,results)==metrics['candidate_models']['first']
 cumulative=read(R/'cumulative-inputs.json');oldresults=[dict(r,source_path=str(local(r['source_path']))) for r in cumulative['original_results']];oldpairs=[]
 for ref in cumulative['first_candidate_receipts']:
  z=verify(read(local(ref['path'])));assert z['record_sha256']==ref['sha256'];oldpairs.append(dict(match_id=z['match_id'],current_model=z['payload']['current'],test_model=z['payload']['test']))
 assert paired_review(oldpairs+pairs,oldresults+results)==metrics['cumulative_first_candidates']
 delivery=read(R/'delivery.json');record=verify(read(local(delivery['report_receipt']['path'])))
 assert record['payload']['report_markdown']==(R/'复盘报告.md').read_text()
 assert record['payload']['metrics']==metrics
 for row in metrics['comprehensive']['rows']:
  result=next(r for r in results if r['match_id']==row['match_id']);h,a=result['home_goals'],result['away_goals']
  assert row['primary_hit']==(row['primary']==f'{h}-{a}' if row['primary'] is not None else None)
  assert row['wdl_hit']==(row['wdl']==('主胜' if h>a else '客胜' if h<a else '平局'))
  if row['total_direction'] in ['大','小']:
   line=row['total_line'];legs=[line] if line*2==int(line*2) else [line-.25,line+.25]
   net=sum(int(h+a<v)-int(h+a>v) for v in legs)/len(legs)
   if row['total_direction']=='大':net=-net
   assert row['total_settlement']=={1:'win',.5:'half_win',0:'push',-.5:'half_loss',-1:'loss'}[net]
 print(json.dumps(dict(status='PASS',archive_sha256=manifest['archive']['sha256'],archive_files=len(manifest['files']),manual_replayed=10,original_pair_replayed=10,cumulative_first_replayed=44,original_forward_population=18,original_forward_settled=10,original_forward_pending=8,report_freeze_verified=delivery['report_receipt']['freeze_id'],network_requests=0,inference_runs=0,training_runs=0),ensure_ascii=False))
