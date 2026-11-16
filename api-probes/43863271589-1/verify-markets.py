import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--code',required=True);p.add_argument('--state',required=True);p.add_argument('--out',required=True);a=p.parse_args()
sys.path.insert(0,str(Path(a.code)/'runtime'))
from automation import market_snapshot,infer_market_snapshot
from automation.market_bridge import attach_total_quote
from research.analysis_freeze import verify
from v2_test.data_contract import aware
root=Path(a.root);summary=json.loads((root/'summary.json').read_text());fixtures=verify(json.loads((Path(a.state)/'future/nations-repair-bundle/plan.json').read_text()))['payload']['fixtures_identity']
rebuilt={}
for provider,adapter in [('the-odds-api',market_snapshot),('infersports',infer_market_snapshot)]:
 d=root/provider
 if not (d/'market-channel.json').is_file():continue
 saved=json.loads((d/'market-channel.json').read_text())
 if saved.get('schema')!='WCPP-MARKET-CHANNEL-1':
  rebuilt[provider]={'status':saved.get('status'),'not_rebuilt':'no complete channel'};continue
 meta=json.loads((d/'source-metadata.json').read_text());now=aware(saved['created_at'])
 if provider=='the-odds-api':
  result=adapter.build(d,meta['odds'],meta['identity'],cutoff=now.isoformat(),now=now,market_max_age_seconds=3600)
 else:
  day=summary['providers'][provider]['requested_fixture_date_utc']
  targets=[f for f in fixtures if f['league_level'] in ('A','C') and f['kickoff_at'][:10]==day and aware(f['kickoff_at'])>now]
  result=adapter.build(d,meta['events'],meta['odds'],meta['identity'],cutoff=now.isoformat(),now=now,fixtures=targets)
 for key,value in result.items():
  assert saved[key]==value,(provider,key)
 rebuilt[provider]={'rebuilt_from_raw_identically':True,'quotes':result['verified_quote_count'],'eligible':result['eligible_fixture_count'],'covered':result['covered_fixture_count']}
now=datetime.now(timezone.utc);attachments=[]
for original in fixtures:
 if aware(original['kickoff_at'])<=now:continue
 fixture=dict(original,cutoff_at=now.isoformat());fixture.pop('total_quote',None);fixture.pop('market_attachment',None)
 result,audit=attach_total_quote(fixture,root,provider_order=('the-odds-api','infersports'),bookmaker_order=('pinnacle',),now=now)
 attachments.append({'match_id':fixture['match_id'],'home_name':fixture['home_name'],'away_name':fixture['away_name'],'date_utc':fixture['kickoff_at'][:10],'grade':fixture['league_level'],'status':audit['status'],'total_quote':result.get('total_quote'),'audit':audit})
report={'schema':'WCPP-CONFIGURED-API-INDEPENDENT-VERIFICATION-1','verified_at':now.isoformat(),'run_id':root.name,'source_code_commit':'4c6061dd5eb2e4af77f18e64bd908a2847f039d0','probe_summary_sha256':hashlib.sha256((root/'summary.json').read_bytes()).hexdigest(),'source_rebuild':rebuilt,'model_input_load_acceptance':{'tested':len(attachments),'attached':sum(x['status']=='ATTACHED' for x in attachments),'fixtures':attachments},'network_calls':0,'prediction_freezes_written':0,'old_freezes_backfilled':False,'model_parameters_changed':False,'future_accuracy_validated':False,'scope':'Read-only reconstruction of real provider evidence and dry model-input attachment; original fixtures are never changed.'}
Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'rebuild':rebuilt,'model_input_load_tested':len(attachments),'attached':report['model_input_load_acceptance']['attached']},ensure_ascii=False))
