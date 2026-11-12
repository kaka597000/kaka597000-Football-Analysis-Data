"""Verify retained probe/attachment evidence; this does not re-date quotes."""
import hashlib
import json
from pathlib import Path
import tarfile


def verify(root):
    root = Path(root)
    index = json.loads((root / 'archive-index.json').read_text())
    archive = root / index['evidence_archive']
    assert archive.resolve().is_relative_to(root.resolve())
    assert archive.stat().st_size == index['bytes']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == index['archive_sha256']
    wanted = {item['path']: item for item in index['members']}
    assert len(wanted) == len(index['members'])
    saved = {}
    with tarfile.open(archive) as stream:
        for member in stream:
            path = Path(member.name)
            assert member.isfile() and not path.is_absolute() and '..' not in path.parts
            assert member.name in wanted and member.name not in saved
            body = stream.extractfile(member).read()
            expected = wanted[member.name]
            assert len(body) == expected['bytes']
            assert hashlib.sha256(body).hexdigest() == expected['sha256']
            saved[member.name] = body
    assert set(saved) == set(wanted)
    for name in ('integration-summary.json', 'live-attachment-acceptance.json'):
        assert (root / name).read_bytes() == saved[name]
    tests = json.loads(saved['integration-summary.json'])
    assert tests['failed_suites'] == tests['skipped'] == 0
    live = json.loads(saved['live-attachment-acceptance.json'])
    assert live['attached'] == live['fixtures'] == len(live['outcomes']) == 8
    assert live['active_artifacts_verified'] == 38
    assert live['new_forecast_frozen'] is False and live['new_settled_ou_samples'] == 0
    channel = json.loads(saved['live-validated/market-channel.json'])
    assert channel['covered_fixture_count'] == channel['eligible_fixture_count'] == 8
    assert channel['verified_quote_count'] == 93
    for snap in channel['snapshots']:
        body = {k: v for k, v in snap.items() if k != 'snapshot_sha256'}
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == snap['snapshot_sha256']
        for row in snap['observations']:
            for meta in (row['evidence'], row['identity_evidence']):
                assert hashlib.sha256(saved['live-validated/' + meta['file']]).hexdigest() == meta['sha256']
    assert index['new_frozen_forecasts'] == index['new_settled_totals_samples'] == 0
    assert index['active_model_changed'] is False
    print(json.dumps({'verified_members': len(saved), 'source_commit': index['source_commit'],
                      'real_quote_rows': 93, 'input_attachments': 8, 'new_settled_samples': 0}))


if __name__ == '__main__':
    verify('workspace-updates/20261112-market-fallback')
