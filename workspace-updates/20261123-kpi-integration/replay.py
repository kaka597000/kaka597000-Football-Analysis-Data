"""Report today's project targets on existing historical score picks, without refitting."""
import argparse
from collections import defaultdict
import gzip
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sys
import tarfile

ARCHIVE = Path(__file__).resolve().parents[1] / '20261123-prematch-literature'
WINDOWS = {'main': ('evaluation', 'recent'), 'pre2010': ('pre2010',)}


def checksum(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def load_windows(scope, manifest):
    if set(scope) != set(manifest['scope']) or len(scope) != len(manifest['scope']):
        raise ValueError('competition scope differs from the archived study')
    windows = defaultdict(list)
    for code in scope:
        relative = f'models/{code}.tar.gz'
        path = ARCHIVE / relative
        if checksum(path) != manifest['files'][relative]:
            raise ValueError(f'archive checksum mismatch for {code}')
        with tarfile.open(path) as archive:
            for study, expected in WINDOWS.items():
                member = f'{study}/forecasts.jsonl.gz'
                if study == 'pre2010' and member not in archive.getnames():
                    continue
                with archive.extractfile(member) as stream, gzip.open(stream, 'rt', encoding='utf-8') as lines:
                    for line in lines:
                        row = json.loads(line)
                        if row['cohort'] != code or row['window'] not in expected:
                            raise ValueError(f'wrong competition or window in {relative}/{member}')
                        windows[row['window']].append(row)
    return windows


def report(source):
    sys.path.insert(0, str(source.resolve() / 'runtime'))
    from research_program.kpi_targets import CURRENT_SCHEMA, TARGETS
    from research_program.paired_kpi_inference import compare

    manifest_path = ARCHIVE / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    scope = [c['code'] for c in json.loads((source / 'configs/analysis-scope.json').read_bytes())['competitions']]
    published = ARCHIVE / 'results/scores.json'
    if checksum(published) != manifest['files']['results/scores.json']:
        raise ValueError('archived score table checksum mismatch')
    original = json.loads(published.read_bytes())
    def compare_archive(rows, stored):
        checked = compare(rows, baseline='r6', candidate='candidate', draws=1000)
        for track, stats in checked['tracks'].items():
            for metric, value in stats['metrics'].items():
                if [value['hits'], value['eligible']] != stored['scores'][track]['counts'][metric]:
                    raise ValueError(f'archived counts differ for {track}/{metric}')
        return checked

    results = {}
    for window, rows in load_windows(scope, manifest).items():
        fingerprint = sha256('\n'.join(sorted(r['cohort'] + '|' + r['id'] for r in rows)).encode()).hexdigest()
        if fingerprint != original[window]['fixture_set_sha256']:
            raise ValueError(f'fixture population differs in {window}')
        analysis = compare_archive(rows, original[window]['overall'])
        by_competition = defaultdict(list)
        for row in rows:
            by_competition[row['cohort']].append(row)
        if set(by_competition) != set(original[window]['competitions']):
            raise ValueError(f'competition coverage differs in {window}')
        competitions = {}
        for code, games in by_competition.items():
            checked = compare_archive(games, original[window]['competitions'][code])
            metrics = checked['tracks']['candidate']['metrics']
            competitions[code] = {
                'population': len(games), 'common_pushes': checked['common_total_pushes'],
                'metrics': {k: {f: v[f] for f in ('hits', 'eligible', 'issued', 'resolved_gate_denominator')}
                            for k, v in metrics.items()},
                'four_targets_on_fixed_population': all(
                    v['resolved_gate_rate'] is not None and v['resolved_gate_rate'] >= v['target']
                    for v in metrics.values()),
            }
        results[window] = {
            'fixture_set_sha256': fingerprint, 'population': analysis['population'],
            'competitions': competitions,
            'common_pushes': analysis['common_total_pushes'], 'tracks': analysis['tracks'],
            'paired': analysis['paired'],
        }
    return {
        'evidence': 'HISTORICAL_RESEARCH_FORECASTS', 'archive_manifest_sha256': checksum(manifest_path),
        'original_source': manifest['source_commit'], 'current_target_protocol': CURRENT_SCHEMA,
        'targets': TARGETS, 'windows': results,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.source), sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False))
