"""Verify R9 file hashes, replay the four KPIs, and validate the first-issue receipts."""

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(source):
    manifest = read(ROOT / 'manifest.json')
    for name, expected in manifest['files'].items():
        require(checksum(ROOT / name) == expected, name)
    sys.path.insert(0, str(source / 'runtime'))
    from research.analysis_freeze import verify as verify_record
    from research_program import continuation_report as report
    from research_program import goal_state_forward as ledger
    from research_program.r8_score_study import extract

    windows = defaultdict(list)
    with tarfile.open(ROOT / 'replay/artifacts.tar.gz') as tar:
        for member in tar.getmembers():
            if member.name.endswith('/forecasts.jsonl.gz'):
                with gzip.GzipFile(fileobj=tar.extractfile(member)) as records:
                    for line in records:
                        r = json.loads(line)
                        windows[r['window']].append(r)
    metrics = read(ROOT / 'replay/metrics.json')
    require(set(windows) == set(metrics), 'window coverage')
    for window, rows in windows.items():
        table = metrics[window]
        groups = defaultdict(list)
        for row in rows:
            groups[row['cohort']].append(row)
            for arm in ('r7', 'r8', 'candidate', 'full_dose'):
                forecast = row['forecast'][arm]
                score = '%d-%d' % tuple(row['actual'])
                rank = row['actual_rank'][arm]
                require(len(set(forecast['top3'])) == 3 and forecast['top3'][0] == forecast['primary'], row['id'])
                require((score == forecast['primary']) == (rank == 1) and
                        (score in forecast['top3']) == (rank <= 3), row['id'] + ' rank')
        require(len({(r['cohort'], r['id']) for r in rows}) == len(rows), window + ' duplicate')
        for group, sample in [(table['overall'], rows), *((table['competitions'][k], v) for k, v in groups.items())]:
            for arm, original in group['scores'].items():
                recalculated = report.rates(sample, arm)
                require(recalculated['counts'] == original['counts'] and
                        recalculated['settlements'] == original['settlements'], window + ' counts ' + arm)
            for name, arms in [('r7', ('r7', 'candidate')), ('r8', ('r8', 'candidate')),
                               ('market', ('market', 'candidate')), ('both_local', ('local_r7', 'local_candidate'))]:
                require(report.paired(sample, *arms) == group['comparisons'][name], window + ' comparisons ' + name)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        extract(ROOT / 'forward/first-issues.tar.gz', target / 'issued')
        require(ledger.review(target/'issued', [], target, by_competition=True) == read(target/'issued/pending.json'),
                'R9 prospective registration')
        extract(ROOT / 'review/evidence.tar.gz', target / 'review')
        for arm in ('R7', 'R8'):
            group = target / 'review' / arm
            data = read(group / 'results.json')
            require(ledger.review(group/'issues', data, group/'evidence') == read(ROOT/'review'/arm/'metrics.json'),
                    arm + ' verified actuals')
            require(ledger.review(group/'issues', data, group/'evidence', by_competition=True)
                    == read(ROOT/'review'/arm/'competition-metrics.json'), arm + ' competition scores')
            receipt = verify_record(read(ROOT/'review'/arm/'review-freeze.json'))
            require(receipt['payload']['results_sha256'] == checksum(group / 'results.json') and
                    receipt['payload']['metrics_sha256'] == checksum(ROOT/'review'/arm/'metrics.json'),
                    arm + ' review hash')
    return {w: len(rows) for w, rows in windows.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='R9 Football-Analysis checkout')
    print(verify(parser.parse_args().source.resolve()))
