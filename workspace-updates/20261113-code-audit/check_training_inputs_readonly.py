"""Compare input admission on existing data without training or writing state."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SOURCE = Path('/workspace/Football-Analysis')
STATE = Path('/workspace/kaka597000-Football-Analysis-Data')
OUT = Path(__file__).with_name('training-inputs-readonly.json')
sys.path.insert(0, str(SOURCE / 'runtime'))
from automation import trainer

old = subprocess.check_output(['git', 'show',
    'a342384242140c613033bd7f830569f3ae92babd:runtime/automation/trainer.py'], cwd=SOURCE)
namespace = {'__file__': trainer.__file__, '__name__': 'audit_original_trainer'}
exec(compile(old, trainer.__file__, 'exec'), namespace)
now = datetime.now(timezone.utc)
files = [STATE / x for x in ('seed/training.json.gz', 'seed/manifest.json',
                             'normalized-results.jsonl', 'config/scopes.json')]
def hashes():
    return {str(p.relative_to(STATE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if p.exists()}
before = hashes()
results = {}
for name, load in [('before', namespace['_load']), ('after', trainer._load)]:
    scopes, rows, quarantine, excluded = load(STATE, now)
    results[name] = {'scopes': len(scopes), 'accepted_rows': len(rows),
                     'quarantined': len(quarantine), 'excluded': len(excluded),
                     'quarantine_reasons': dict(Counter(q['reason'] for q in quarantine)),
                     'source_status': dict(Counter(r['source_evidence_status'] for r in rows))}
assert before == hashes(), 'state changed during comparison'
with OUT.open('x') as handle:
    json.dump({'checked_at': now.isoformat(), 'input_files_sha256': before,
               'state_bytes_unchanged': True, 'training_performed': False,
               'network_requests': 0, 'comparison': results}, handle, indent=2)
print(json.dumps(results))
