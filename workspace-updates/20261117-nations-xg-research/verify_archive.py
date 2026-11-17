"""Verify every member, restore to an empty directory, optionally replay numbers."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest', default='manifest.json')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).parent
    manifest = read(root/args.manifest)
    archive = root/manifest['archive']
    assert sha(archive) == manifest['sha256']
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    expected = {entry['member']: entry for entry in manifest['files']}
    with tarfile.open(archive) as tf:
        assert len(tf.getmembers()) == len(expected)
        for member in tf.getmembers():
            assert member.name in expected and member.isfile()
            target = out/member.name
            assert target.resolve().is_relative_to(out.resolve())
            content = tf.extractfile(member).read()
            assert hashlib.sha256(content).hexdigest() == expected[member.name]['sha256']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    result = {'verified_members': len(expected), 'archive_sha256': sha(archive)}
    if args.replay:
        from nations_league import repair, xg_research as xg
        from research.analysis_freeze import verify, digest
        source = Path(xg.__file__).resolve().parents[2]
        for name, expected_sha in manifest['source']['dependencies'].items():
            assert sha(source/name) == expected_sha
        experiment = out/'research/nations-xg-20261117'
        protocol = read(experiment/'protocol.json')
        frozen = verify(read(experiment/'protocol-freeze.json'))
        assert frozen['payload'] == protocol
        paths = {'history': 'canonical-history.json', 'xg': 'data/xg-records.json', 'quotes': 'archived-quotes.json'}
        data = {}
        for name, local in paths.items():
            assert sha(experiment/local) == protocol['inputs'][name]['sha256']
            data[name] = read(experiment/local)
        xg.run(protocol, data['history'], data['xg']['rows'], data['quotes'], out/'replay')
        count = 0
        for old in (experiment/'experiment').glob('*/*-predictions.json'):
            new = out/'replay'/old.relative_to(experiment/'experiment')
            assert read(new) == read(old)
            count += len(read(old))
        original = read(experiment/'experiment/results.json')
        replay = read(out/'replay/results.json')
        assert original['levels'] == replay['levels']
        index = read(experiment/'experiment/index.json')
        predictions = 0
        for path in (experiment/'forward/freezes').glob('*.json'):
            record = verify(read(path))
            fixture = record['fixture']
            for arm, pred in record['payload']['predictions'].items():
                artifact_path = experiment/'experiment'/fixture['league_level']/(arm+'-artifact.json')
                assert sha(artifact_path) == index['routes'][fixture['league_level']][arm]['sha256']
                core = read(artifact_path)['core']
                regenerated = xg.prediction(core, fixture, pred['version'], pred['artifact_sha256'])
                assert regenerated['matrix_hash'] == pred['matrix_hash']
                assert regenerated['primary'] == pred['primary'] and regenerated['total'] == pred['total']
                predictions += 1
        result.update(historical_predictions_identical=count, forward_predictions_identical=predictions,
                      selected_arms_identical=True, runtime_assets_required=False)
    print(json.dumps(result, ensure_ascii=False))
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
