"""Append a technical follow-up; do not call APIs or modify access rules."""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from data_sources.clients import PROVIDERS, QUARANTINED_CREDENTIAL_NAMES
from research.analysis_freeze import save, verify

R = Path(__file__).resolve().parent
D = Path('/workspace/kaka597000-Football-Analysis-Data/workspace-updates/20261113-cloudflare-remediation')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads(p.read_text())
def write(p, value):
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
if D.exists() or (R/'delivery.json').exists():
    raise SystemExit('Existing delivery: do not replace or duplicate the freeze.')
names = ['report.md','findings.md','sources.json','search-log.json','environment-observation.json',
         'freeze_and_archive.py']
bindings = set(QUARANTINED_CREDENTIAL_NAMES)
for spec in PROVIDERS.values():
    bindings.update(spec.get('aliases', []))
    if 'env' in spec:
        bindings.add(spec['env'])
secrets = [os.environ[n].encode() for n in bindings if os.environ.get(n)]
for name in names:
    content = (R/name).read_bytes()
    assert not any(x in content for x in secrets), 'credential match; value suppressed'
    if name.endswith('.json'):
        read(R/name)
environment = read(R/'environment-observation.json')
assert environment['api_requests_this_followup'] == 0
assert not environment['cloudflare_zone_permission_test_performed']
now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
payload = {'report_markdown':(R/'report.md').read_text(),
           'source_commit':subprocess.check_output(['git','-C','/workspace/Football-Analysis','rev-parse','HEAD'],text=True).strip(),
           'evidence_sha256':{name:sha(R/name) for name in names},
           'followup_business_api_requests':0,'skip_rules_created':0,'support_request_sent':False,
           'access_restoration_verified':False,'code_changed':False,
           'decision':'SERVICE_OWNER_RULE_INVESTIGATION_REQUIRED; NO_ACCESS_CONTROL_BYPASS'}
fixture = {'match_id':'api-403-diagnosis:20261113-0959','cohort':'data-source-audit',
           'kickoff_at':'2026-11-13T09:59:00+08:00','cutoff_at':now}
receipt = save(payload,fixture,stage='review',track='api-access-diagnosis',
               idempotency_key='20261113-cloudflare-official-remediation-followup-1')
record = verify(read(Path(receipt['path'])))
assert record['previous_sha256'] == '7e5cf04084993f2c629b1913e384de7f8761438982fb058f8fbcfd268585afae'
write(R/'delivery.json',{'receipt':receipt,'previous_freeze_id':'8cb6f28a707daf65-v000001',
                       'service_access_restored':False,'environment_published':False})
D.mkdir(parents=True)
for name in names + ['delivery.json']:
    shutil.copy2(R/name,D/name)
(D/'freeze').mkdir()
shutil.copy2(receipt['path'],D/'freeze/000002.json')
members = [{'path':str(p.relative_to(D)),'sha256':sha(p),'bytes':p.stat().st_size}
           for p in sorted(D.rglob('*')) if p.is_file()]
for m in members:
    assert sha(D/m['path']) == m['sha256']
write(D/'manifest.json',{'schema':'WCPP-CLOUDFLARE-REMEDIATION-EVIDENCE-1','members':members,
                        'freeze_receipt':receipt,'configured_credential_matches':0,
                        'source_commit':payload['source_commit'],'business_api_requests':0,
                        'data_parent_commit':subprocess.check_output(['git','-C',str(D.parents[1]),'rev-parse','HEAD'],text=True).strip()})
print(json.dumps({'freeze':receipt,'files_verified':len(members)},ensure_ascii=False))
