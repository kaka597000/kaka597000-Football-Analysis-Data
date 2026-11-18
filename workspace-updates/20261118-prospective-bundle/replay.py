"""Replay the two archived protocols in a fresh worker with their locked runtime installed."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

SOURCE = Path('/workspace/Football-Analysis')
sys.path[:0] = [str(SOURCE), str(SOURCE / 'runtime')]
from runtime.automation import prospective_cycle as cycle


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return path


def frozen_files(future):
    paths = list((future / 'bundle-v2').rglob('*')) + list((future / 'ucl-bundle-v2').rglob('*'))
    paths += list((future / 'state/freezes').rglob('*.json'))
    return {str(p.relative_to(future)): file_hash(p) for p in paths if p.is_file()}


def reexport(root, manifest, domestic, work):
    def locate(receipt):
        return dict(receipt, path=str(cycle.resolve(root, manifest, receipt['path'])))
    prefix = 'domestic' if domestic else 'ucl'
    def input_file(name, value):
        return write(work / (prefix + '-' + name + '.json'), value)
    protocol = input_file('protocol', manifest['protocol'])
    packages = []
    roles = ('current_receipt', 'candidate_receipt') if domestic else ('baseline', 'refreshed')
    for item in manifest['packages']:
        packages.append({**item, **{role: locate(item[role]) for role in roles}})
    pairs = input_file('packages', packages)
    out = work / (prefix + '-export')
    if domestic:
        plans = dict(manifest['plans'], plans=[locate(r) for r in manifest['plans']['plans']])
        exported = cycle.export_bundle(out, protocol, input_file('plans', plans), pairs,
                                       queue_path=input_file('queue', manifest['queue']),
                                       freeze_root=root.parent / 'state/freezes')
    else:
        exported = cycle.export_ucl_bundle(out, protocol, input_file('plan', locate(manifest['plan'])), pairs)
    assert cycle.check_bundle(out, schema=manifest['schema']) == exported
    content = {k: v for k, v in exported.items() if k not in ('created_at', 'manifest_sha256')}
    if domestic:
        # Directory enumeration order differs across filesystems. Slots are a membership set in the cycle.
        content['protected_first_slots'] = sorted(content['protected_first_slots'],
                                                  key=lambda slot: (slot['match_id'], slot['record_sha256']))
    return digest(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--future', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # Stable, empty staging paths also make the two re-export alias tables comparable.
    work = Path('/workspace/bundle-verification')
    work.mkdir()
    future = work / 'future'
    for folder in ('bundle-v2', 'ucl-bundle-v2', 'state', 'ucl-state'):
        shutil.copytree(args.future / folder, future / folder)
    original = frozen_files(future)
    assert original == frozen_files(args.future)
    def no_network(url):
        raise AssertionError('unexpected network call in offline replay')
    evidence = {'frozen_files': len(original), 'frozen_tree_sha256': digest(original)}
    for domestic in (True, False):
        folder, state = ('bundle-v2', 'state') if domestic else ('ucl-bundle-v2', 'ucl-state')
        root = future / folder
        manifest = cycle.check_bundle(root, schema=cycle.SCHEMA if domestic else cycle.UCL_SCHEMA)
        previous = cycle.read(sorted((future / state / 'runs').glob('*.json'))[-1])
        if domestic:
            assert cycle.hydrate(root) == manifest
        with patch.object(cycle, 'check_bundle', wraps=cycle.check_bundle) as checks:
            if domestic:
                report = cycle.cycle(root, max_captures=0, max_result_requests=0, fetcher=no_network)
            else:
                report = cycle.ucl_cycle(root, max_result_requests=0, fetcher=no_network)
        assert not report['result_requests'] and not report['failures']
        # The archived transport ran with its own polling budget and wall clock.
        operational = {'reviewed_at', 'result_requests', 'result_attempted_ids', 'failures'}
        scores = {k: v for k, v in report.items() if k not in operational}
        assert scores == {k: v for k, v in previous.items() if k not in operational}
        for alias in manifest['capture_assets']:
            assert file_hash(Path(alias)) == manifest['aliases'][alias]
        evidence[folder] = {'manifest_sha256': manifest['manifest_sha256'],
                            'objects': len(manifest['objects']),
                            'object_bytes': sum(v['bytes'] for v in manifest['objects'].values()),
                            'verified_capture_paths': len(manifest['capture_assets']),
                            'cycle_object_inventory_passes': checks.call_count,
                            'population': report['population'],
                            'paired': report['captured_population' if domestic else 'first_paired'],
                            'completed': report['completed'],
                            'pending': report['pending'] if domestic else len(report['pending_results']),
                            'missing': report['missing_first_pairs'] if domestic else len(report['missing_first_pairs']),
                            'network_requests': report['result_requests'], 'complete_review_sha256': digest(scores),
                            'reexport_content_sha256': reexport(root, manifest, domestic, work)}
    assert frozen_files(future) == original
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
