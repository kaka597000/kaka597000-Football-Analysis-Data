import concurrent.futures
import json
import sys
from pathlib import Path
import fetch_base as fetcher

fetcher.ROOT = Path('/workspace/recovery-history-packages-20261102')
fetcher.BASE = 'https://raw.githubusercontent.com/kaka597000/kaka597000-Football-Analysis-Data/a0635b6551ba7a31c524ba3b25aee7e0ccbb8430/'
tree = json.loads(Path('/workspace/recovery-tools/old-handoff-tree.json').read_text())
assert tree.get('truncated') is False
group = sys.argv[1] if len(sys.argv) > 1 else 'audit-history'
assert group in ('audit-history', 'models-history', 'data-history')
entries = [e for e in tree['tree'] if e['type'] == 'blob' and e['path'].startswith(group + '-parts/')]
print(json.dumps({'files': len(entries), 'bytes': sum(e['size'] for e in entries)}), flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    jobs = [pool.submit(fetcher.fetch, e) for e in entries]
    for i, job in enumerate(concurrent.futures.as_completed(jobs), 1):
        job.result()
        if i % 10 == 0 or i == len(jobs):
            print(f'Verified {i}/{len(jobs)}', flush=True)
print('All historical archive Git blobs verified.', flush=True)
