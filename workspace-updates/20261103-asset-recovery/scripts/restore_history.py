import csv
import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('base_restore', '/workspace/recovery-packages-20261102/restore.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
group = sys.argv[1] if len(sys.argv) > 1 else 'audit-history'
assert group in ('audit-history', 'models-history', 'data-history')
packages = Path('/workspace/recovery-history-packages-20261102') / (group + '-parts')
stage = Path('/workspace/recovered-' + group + '-20261102')
assert not stage.exists(), 'No overwrite permitted'
m = json.loads((packages / 'parts.json').read_text())
print(json.dumps(m)[:500], flush=True)
entries = m.get('ordered_parts', m.get('parts'))
paths = []
whole = hashlib.sha256()
for entry in entries:
    p = packages / entry['name']
    assert p.stat().st_size == entry['bytes'] and base.sha(p) == entry['sha256']
    with p.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            whole.update(chunk)
    paths.append(p)
with zipfile.ZipFile('/workspace/recovery-packages-20261102/incoming-core/control.zip') as z:
    archive = json.loads(z.read(group + '.manifest.json'))
    rows = list(csv.DictReader(io.StringIO(z.read('files.csv').decode())))
expected = {r['path']: r for r in rows if r['archive_group'] == group}
assert whole.hexdigest() == m['whole_sha256'] == archive['sha256']
assert sum(p.stat().st_size for p in paths) == archive['bytes']
stage.mkdir()
seen = set()
with io.BufferedReader(base.Parts(paths)) as stream, tarfile.open(fileobj=stream, mode='r|gz') as tar:
    for member in tar:
        dest = (stage / member.name).resolve()
        assert member.isfile() and dest.is_relative_to(stage) and member.name in expected and member.name not in seen
        entry = expected[member.name]
        assert member.size == int(entry['bytes'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with tar.extractfile(member) as src, dest.open('xb') as out:
            while chunk := src.read(1024 * 1024):
                h.update(chunk)
                out.write(chunk)
        assert h.hexdigest() == entry['sha256'], member.name
        seen.add(member.name)
        if len(seen) % 2000 == 0:
            print('Verified ' + str(len(seen)), flush=True)
assert seen == set(expected) and len(seen) == archive['files']
receipt = {'verified_files': len(seen), 'archive_sha256': whole.hexdigest(), 'production_overwritten': False}
(stage / 'RECOVERY-RECEIPT.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt), flush=True)
