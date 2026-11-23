"""Check the 20 coverage rows, database readback and quota accounting independently of credentials."""
from pathlib import Path
import csv
import hashlib
import json

root=Path(__file__).resolve().parent
read=lambda name:json.loads((root/name).read_bytes())
audit=read('database-audit.json')
summary=read('coverage-summary.json')
bundle=read('bundle.json')
with (root/'coverage.csv').open(encoding='utf-8-sig',newline='') as stream:
    rows=list(csv.DictReader(stream))
catalog={v['competition']:v for v in audit['directory']}
training={v['competition']:v['games'] for v in audit['training_eligible']}
review={v['competition']:v for v in audit['published_review']}
price={v['competition']:v for v in audit['archive_prices']}
market={(v['competition'],v['endpoint']):v for v in audit['trial_details_by_competition']}
fixtures={(v['competition'],v['feed']):v for v in audit['records']}
assert len(rows)==len(catalog)==summary['scopes']==20
assert set(catalog)=={r['范围代码'] for r in rows}
for r in rows:
    c=r['范围代码']
    assert (catalog[c]['provider_code'] or '')==r['凤凰目录代码']
    assert int(r['核准完赛场次'])==training.get(c,0)
    assert int(r['比赛列表记录'])==fixtures.get((c,'trial'),{}).get('records',0)
    assert int(r['公开历史比赛'])==fixtures.get((c,'archive'),{}).get('records',0)
    assert int(r['逐场盘口详情'])==market.get((c,'all'),{}).get('matches',0)
    assert int(r['定点快照场次'])==market.get((c,'snapshot'),{}).get('matches',0)
    assert int(r['近七日供应商复盘记录'])==review.get(c,{}).get('provider_reviews',0)
    assert int(r['近七日供应商复盘场次'])==review.get(c,{}).get('matches',0)
    assert int(r['公开欧赔变动条数'])==price.get(c,{}).get('price_nodes',0)
assert sum(int(r['公开有价场次']) for r in rows)==3322
assert sum(int(r['近七日供应商复盘场次']) for r in rows)==summary['provider_review_scope_matches']==audit['review_detail_matches']
assert sum(int(r['逐场盘口详情']) for r in rows)==summary['requested_all']
assert sum(bool(int(r['比赛列表记录']) or int(r['近七日供应商复盘场次'])) for r in rows)==summary['competitions_with_event_data']
assert sum(summary['queue_at_capture'].values())==summary['queue_rows']
assert all(v['agreed']==v['links'] and v['disputed']==0 for v in audit['direct_cross_checks'])
assert sum(bundle['receipt_types'].values())==bundle['frozen_response_receipts']==summary['raw_payload_verifications']
assert summary['quota_last_success']['remaining']==0 and len(summary['unsubscribed_codes'])==14
proof=read('restore-verification.json')
assert proof['restore_matches_unified_sql_audit'] and proof['sqlite_quick_check']=='ok' and proof['foreign_key_violations']==0
assert proof['receipt_count']==bundle['frozen_response_receipts']
assert proof['original_database_audit_sha256']==hashlib.sha256((root/'database-audit.json').read_bytes()).hexdigest()
print('Verified 20 competitions, authenticated/archive/publisher denominators and the restore receipt.')
