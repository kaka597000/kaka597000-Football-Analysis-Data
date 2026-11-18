"""Compare one source checkout to retained production inputs without issuing a forecast."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile


def read(path):
    return json.loads(path.read_bytes())


def unpack(archive, prefix, root):
    with tarfile.open(archive) as tar:
        for member in tar:
            path = Path(member.name)
            if member.isfile() and path.is_relative_to(prefix):
                destination = root / path.relative_to(prefix)
                if not destination.resolve().is_relative_to(root.resolve()):
                    raise ValueError('archive member outside destination')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(tar.extractfile(member).read())


def brazil(data, amended):
    from runtime.automation.market_snapshot import build

    root = data / 'market/runs/44212218194-1-bra1'
    meta = read(root / 'source-metadata.json')
    channel = read(root / 'market-channel.json')
    readouts = {}
    for label, time in [('original', channel['created_at']), ('after_alias_review', '2026-11-18T01:17:26Z')]:
        result = build(root, meta['odds'], meta['identity'], cutoff=time,
                       now=datetime.fromisoformat(time), competition='bra.1', market_max_age_seconds=3600)
        rows = [r for s in result['snapshots'] for r in s['observations'] if r['field'] == 'market_quote']
        target_rows = [r for r in rows if r['match_id'] == 'espn:401841313']
        other = sorted(json.dumps([r['match_id'], r['value']], sort_keys=True)
                       for r in rows if r['match_id'] != 'espn:401841313')
        readouts[label] = {'as_of': time, 'eligible': result['eligible_fixture_count'],
                           'covered': result['covered_fixture_count'], 'quotes': len(rows),
                           'flamengo_athletico_pr': dict(Counter(r['value']['market'] for r in target_rows)),
                           'other_quotes_sha256': hashlib.sha256(json.dumps(other).encode()).hexdigest()}
    assert readouts['original']['covered'] == 5 and readouts['original']['quotes'] == 208
    assert readouts['after_alias_review']['covered'] == (6 if amended else 5)
    assert readouts['after_alias_review']['eligible'] == 6
    return readouts


def market_replay(data, temp, amended):
    from runtime.automation.market_bridge import attach_total_quote

    root = temp / 'market'
    archive = data / 'workspace-updates/20261118-repository-audit/repository-audit-evidence.tar.gz'
    unpack(archive, 'infer-replay', root)
    path = root / 'market-channel.json'
    shutil.copyfile(root / 'new-code-today-identity-review.json', path)
    channel = read(path)
    assert channel['retrospective_identity_replay']
    statuses = {}
    for saved in channel['snapshots']:
        target = saved['target']
        f = dict(target, home=target['home_id'], away=target['away_id'])
        _, audit = attach_total_quote(f, root, now=datetime.fromisoformat(f['cutoff_at']))
        statuses[f['match_id']] = audit['status']
    assert len(statuses) == 8 and list(statuses.values()).count('ATTACHED') == (0 if amended else 7)
    return statuses


def reviews(data, temp, amended):
    from runtime.automation.nations_repair_cycle import cycle, resolve_results
    from runtime.nations_league import repair_forward, xg_research
    from v5.paired_review import review

    bundle = data / 'future/nations-repair-bundle'
    state = data / 'future/nations-repair-state'
    results = resolve_results(state, read(state / 'results.json'))
    archive = data / 'workspace-updates/20261118-all-analysis-review'
    report = repair_forward.review(bundle, results)
    assert report == read(archive / 'repair-complete-forward-review.json')
    xg = temp / 'xg'
    unpack(data / 'workspace-updates/20261117-nations-xg-research/nations-xg-evidence.tar.gz',
           'research/nations-xg-20261117/forward', xg)
    ids = {fixture['match_id'] for fixture in read(xg / 'plan.json')['payload']['fixtures_identity']}
    xg_report = xg_research.review_forward(xg, [r for r in results if r['match_id'] in ids])
    assert xg_report == read(archive / 'xg-first-forward-review.json')
    record = read(bundle / 'freezes/espn-401861190.json')
    preds = record['payload']['predictions']
    pair = {'match_id': record['match_id'], 'fixture': record['fixture'],
            'current_model': preds['old_current'], 'test_model': preds['old_test']}
    actual = next(r for r in results if r['match_id'] == record['match_id'])
    swapped = dict(actual, home=actual['away'], away=actual['home'])
    try:
        admitted = review([pair], [swapped])['finished']
    except ValueError as exc:
        if 'identity mismatch' not in str(exc):
            raise
        admitted = 0
    assert admitted == (0 if amended else 1)

    runs = [state / 'runs' / name for name in ('20261118T002745607941.json', '20261118T005946604794.json')]
    for run in runs:
        retained = read(run)['report']
        assert retained['result_requests'] == 0 and all(retained[k] == v for k, v in report.items())
    old_freeze = next((state / 'freezes').glob('*/000008.json'))
    assert read(runs[1])['freeze_receipt']['sha256'] == read(old_freeze)['record_sha256']
    result = {'repair_matches_equal_to_archive': report['settled'],
              'xg_matches_equal_to_archive': xg_report['comparison']['finished'],
              'swapped_teams_counted': admitted, 'previous_duplicate_bytes': old_freeze.stat().st_size + runs[1].stat().st_size}
    if amended:
        copy = temp / 'completed-state'
        copy.mkdir()
        shutil.copytree(state / 'raw', copy / 'raw')
        shutil.copyfile(state / 'results.json', copy / 'results.json')
        first = cycle(bundle, copy, max_requests=0)
        def inventory():
            return {path.relative_to(copy): hashlib.sha256(path.read_bytes()).hexdigest()
                    for name in ('runs', 'freezes') for path in (copy / name).rglob('*.json')}
        before = inventory()
        again = cycle(bundle, copy, max_requests=0)
        assert first['review_freeze_id'] == again['review_freeze_id'] and inventory() == before
        assert again['review_publication'] == 'REUSED_COMPLETED_REVIEW' and again['result_requests'] == 0
        result['repeat_extra_files'] = len(inventory()) - len(before)
        result['repeat_file_contents_identical'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--version', choices=['before', 'after'], required=True)
    args = parser.parse_args()
    source, data = args.source.resolve(), args.data.resolve()
    sys.path[:0] = [str(source), str(source / 'runtime'), str(source / 'runtime/v5')]
    amended = args.version == 'after'
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        result = {'version': args.version, 'brazil': brazil(data, amended),
                  'infer_replay_status_by_match': market_replay(data, temp, amended),
                  'review': reviews(data, temp, amended)}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
