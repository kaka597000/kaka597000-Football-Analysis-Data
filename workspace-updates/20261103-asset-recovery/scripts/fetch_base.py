import concurrent.futures
import hashlib
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path('/workspace/recovery-packages-20261102')
TREE = json.loads(Path('/workspace/recovery-base-tree-20261103.json').read_text())
BASE = 'https://raw.githubusercontent.com/kaka597000/kaka597000-Football-Analysis-Data/466fd626a47481e70b176a9a69c58224d7d1bf63/workspace-backup-20261102/'

def digest(path, size):
    h = hashlib.sha1(b'blob ' + str(size).encode() + b'\0')
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def fetch(entry):
    path = ROOT / entry['path']
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('unsafe path')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size == entry['size'] and digest(path, entry['size']) == entry['sha']:
        return
    part = path.with_name(path.name + '.partial')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(BASE + urllib.parse.quote(entry['path'], safe='/'), timeout=45) as r, part.open('wb') as f:
                while chunk := r.read(1024 * 1024):
                    f.write(chunk)
            if part.stat().st_size != entry['size'] or digest(part, entry['size']) != entry['sha']:
                raise ValueError('Git blob identity mismatch: ' + entry['path'])
            part.replace(path)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)

if __name__ == '__main__':
    entries = [x for x in TREE['tree'] if x['type'] == 'blob']
    assert TREE.get('truncated') is False
    print(json.dumps({'files': len(entries), 'bytes': sum(x['size'] for x in entries)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, e): e for e in entries}
        for i, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            job.result()
            if i % 10 == 0 or i == len(entries):
                print(f'Verified {i}/{len(entries)}', flush=True)
    print('All fixed-commit Git blobs verified.', flush=True)
