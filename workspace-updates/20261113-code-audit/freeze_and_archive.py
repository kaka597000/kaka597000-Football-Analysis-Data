"""Freeze the completed technical audit and archive its inspectable evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

SOURCE = Path('/workspace/Football-Analysis')
DATA = Path('/workspace/kaka597000-Football-Analysis-Data')
REPORTS = Path(__file__).resolve().parent
DEST = DATA / 'workspace-updates/20261113-code-audit'
sys.path.insert(0, str(SOURCE))
from scripts.check_repository import BINDINGS
from research.analysis_freeze import save, verify

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if DEST.exists():
    raise SystemExit('Existing audit archive; never replace it.')
delivery = read(REPORTS / 'delivery-receipt.json')
tests = read(REPORTS / 'test-summary.json')
ci = read(REPORTS / 'source-main-ci.json')
assert ci['conclusion'] == 'success'
assert tests['strict_integration']['failures'] == tests['strict_integration']['skips'] == 0
assert delivery['source_main'] == subprocess.check_output(
    ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
files = sorted(p for p in REPORTS.rglob('*') if p.is_file() and p.name != 'TEAM.md')
secrets = [os.environ[n].encode() for n in BINDINGS if len(os.environ.get(n, '')) >= 8]
for path in files:
    body = path.read_bytes()
    assert not any(secret in body for secret in secrets), 'configured credential match; value suppressed'
    if path.suffix == '.json':
        read(path)
now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
payload = {'report': (REPORTS / '审计与交付.md').read_text(),
           'source_commit': delivery['source_main'], 'delivery': delivery,
           'evidence_sha256': {str(p.relative_to(REPORTS)): sha(p) for p in files},
           'active_model_changed': False, 'environment_published': False,
           'formal_prediction_kpi_eligible': False, 'historical_or_future_gain_claimed': False}
fixture = {'match_id': 'code-audit:20261113:full', 'cohort': 'technical-audit',
           'kickoff_at': read(REPORTS / 'baseline-health.json')['checked_at_beijing'],
           'cutoff_at': now}
receipt = save(payload, fixture, stage='review', track='code-quality-audit',
               idempotency_key='20261113-full-code-audit-v1')
verify(read(Path(receipt['path'])))
DEST.mkdir(parents=True)
for path in files:
    target = DEST / path.relative_to(REPORTS)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
(DEST / 'freeze').mkdir()
shutil.copy2(receipt['path'], DEST / 'freeze' / Path(receipt['path']).name)
write(DEST / 'freeze-receipt.json', receipt)
members = [{'path': str(p.relative_to(DEST)), 'sha256': sha(p), 'bytes': p.stat().st_size}
           for p in sorted(DEST.rglob('*')) if p.is_file()]
write(DEST / 'manifest.json', {
    'schema': 'WCPP-CODE-AUDIT-ARCHIVE-1', 'created_at_beijing': now,
    'source_main': delivery['source_main'], 'freeze_receipt': receipt,
    'members': members, 'configured_credential_matches': 0,
    'data_parent_commit': subprocess.check_output(['git', '-C', str(DATA), 'rev-parse', 'HEAD'], text=True).strip(),
    'restore': 'Clone data repository and verify members SHA256; no expiring Actions artifact required.',
    'existing_model_archives_reused': True, 'prediction_kpi_eligible': False})
for member in members:
    assert sha(DEST / member['path']) == member['sha256']
print(json.dumps({'archive': str(DEST), 'members_verified': len(members), 'freeze': receipt}, ensure_ascii=False))
