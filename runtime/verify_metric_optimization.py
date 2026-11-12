"""Verify the retained optimization evidence without extracting or running it."""
import hashlib
import json
from pathlib import Path
import tarfile


def verify(root):
    root = Path(root)
    index = json.loads((root / 'archive-index.json').read_text())
    archive = root / index['archive']
    assert archive.resolve().is_relative_to(root.resolve())
    assert archive.stat().st_size == index['archive_bytes']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == index['archive_sha256']
    wanted = {item['path']: item for item in index['members']}
    assert len(wanted) == len(index['members'])
    seen = set()
    with tarfile.open(archive) as stream:
        for member in stream:
            path = Path(member.name)
            assert member.isfile() and not path.is_absolute() and '..' not in path.parts
            assert member.name in wanted and member.name not in seen
            body = stream.extractfile(member).read()
            expected = wanted[member.name]
            assert len(body) == expected['bytes']
            assert hashlib.sha256(body).hexdigest() == expected['sha256']
            seen.add(member.name)
    assert seen == set(wanted)
    tests = json.loads((root / 'test-summary.json').read_text())
    assert tests == index['tests'] and tests['failed'] == tests['skipped'] == 0
    assert tests['registry_verified_artifacts'] == 38
    assert index['active_model_promoted'] is False
    print(json.dumps({'verified_members': len(seen), 'source_commit': index['source_commit'],
                      'test_executions': tests['test_executions'], 'model_promoted': False}))


if __name__ == '__main__':
    verify('workspace-updates/20261112-metric-optimization')
