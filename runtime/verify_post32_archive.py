"""Verify retained evidence parts and every execution member without extraction."""
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def verify(root):
    root = Path(root)
    index = json.loads((root / 'archive-index.json').read_text())
    for item in index['files']:
        path = root / item['path']
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
    execution = json.loads((root / 'execution-index.json').read_text())
    catalog = json.loads((root / 'execution-recovery-catalog.json').read_text())['archives'][0]
    assert catalog['parts'] == execution['parts'] and catalog['members'] == execution['members']
    assert catalog['sha256'] == execution['archive_sha256']
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / 'execution.tar.gz'
        with archive.open('wb') as out:
            for item in execution['parts']:
                path = root / item['relative_path']
                assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
                out.write(path.read_bytes())
        assert sha(archive) == execution['archive_sha256']
        wanted = {x['path']: x for x in execution['members']}; seen = set()
        assert len(wanted) == len(execution['members'])
        with tarfile.open(archive) as t:
            for member in t:
                assert member.isfile() and member.name in wanted and member.name not in seen
                path = Path(member.name)
                assert not path.is_absolute() and '..' not in path.parts
                body = t.extractfile(member).read(); item = wanted[member.name]
                assert len(body) == item['bytes'] and hashlib.sha256(body).hexdigest() == item['sha256']
                seen.add(member.name)
        assert seen == set(wanted)
    print(json.dumps({'archive_files_verified': len(index['files']), 'execution_members_verified': len(seen),
                      'actions_artifact_downloads': 0}))


if __name__ == '__main__':
    verify('workspace-updates/20261112-post32')
