"""Reconcile archived time splits and measure what the tested scores could cover."""

from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from research_program.paired_kpi_inference import compare


ROOT = Path(__file__).resolve().parents[1]
STUDIES = {
    25: ('j1-allocation', ('candidate', 'full_dose')),
    26: ('j1-first-stage', ('full_dose',)),
    27: ('j1-score-calibration', ('half_dose', 'full_dose')),
    29: ('j1-score-dispersion', ('half_dose', 'full_dose')),
    30: ('europe-score-dispersion', ('third_half', 'third_full', 'rank_half', 'rank_full')),
    31: ('uel-outcome-calibration', ('half', 'full')),
    32: ('europe-one-all', ('half', 'full')),
    33: ('europe-shot-score', ('quarter', 'half', 'full')),
    34: ('europe-winning-margin', ('half', 'full')),
    35: ('europe-close-score-agreement', ('first_agreement', 'three_agreement')),
    36: ('europe-three-goal-coverage', ('third_coverage', 'half_rank', 'full_rank')),
    37: ('europe-exactly-three', ('third_coverage', 'half_rank', 'full_rank')),
}
J1 = (25, 26, 27, 29)
EUROPE = (30, 31, 32, 33, 34, 35, 36, 37)
SCOPES = {
    'jpn.1': ('r7', J1, dict(validation=218, late_2025=162, early_2026_27=150, evaluation=312)),
    'uefa.europa.conf': ('r13', tuple(n for n in EUROPE if n != 31), dict(validation=54, evaluation=54)),
    'uefa.europa': ('r13', EUROPE, dict(validation=72, evaluation=72)),
}
METRICS = ('score_top1', 'score_top3')
IDENTITY = ('id', 'cohort', 'stage', 'date', 'home', 'away', 'actual', 'line', 'source_sha256')


def inputs():
    rows, hashes = {}, {}
    for study, (name, _) in STUDIES.items():
        directory = ROOT / f'20261126-r{study}-{name}'
        checksums = {path.removeprefix('./'): digest for digest, path in
                     (line.split('  ', 1) for line in (directory/'SHA256SUMS').read_text().splitlines())}
        evaluation = 'forecasts' if study in J1 else 'evaluation'
        for phase, basename in (('validation', 'validation'), ('evaluation', evaluation)):
            relative = ('' if study == 25 else 'replay/') + basename + '.jsonl.gz'
            path = directory / relative
            raw = path.read_bytes()
            digest = sha256(raw).hexdigest()
            if digest != checksums[relative]:
                raise ValueError(f'original forecast archive differs: {path}')
            hashes[str(path.relative_to(ROOT))] = digest
            rows[study, phase] = [json.loads(line) for line in gzip.decompress(raw).splitlines() if line]
    return rows, hashes


def control_rows(rows, baseline):
    return {row['id']: ({key: row[key] for key in IDENTITY}, row.get('window'),
                        row['forecast'][baseline], row['forecast']['market']) for row in rows}


def paired(rows, baseline, arm):
    report = compare(rows, baseline=baseline, candidate=arm)
    return {metric: dict(
        baseline_hits=report['tracks'][baseline]['metrics'][metric]['hits'],
        candidate_hits=report['tracks'][arm]['metrics'][metric]['hits'],
        **{key: report['paired'][metric][key] for key in
           ('eligible', 'gained', 'lost', 'net_hits', 'date_cluster_ci')},
    ) for metric in METRICS}


def scope(data, cohort, baseline, studies, window, expected):
    phase = 'validation' if window == 'validation' else 'evaluation'
    original = None
    variants = {}
    first_options, three_options = defaultdict(set), defaultdict(set)
    for study in studies:
        rows = [row for row in data[study, phase] if row['cohort'] == cohort
                and (window == phase or row.get('window') == window)]
        control = control_rows(rows, baseline)
        if len(rows) != expected or len(control) != expected:
            raise ValueError(f'{cohort} {window} R{study} does not cover its original complete population')
        if original is None:
            original = control
            market = paired(rows, baseline, 'market')
        if original != control:
            raise ValueError(f'{cohort} {window} R{study} has a different fixture, result, baseline or market')
        for arm in STUDIES[study][1]:
            name = f'R{study}.{arm}'
            comparison = paired(rows, baseline, arm)
            if any(item['eligible'] != expected for item in comparison.values()):
                raise ValueError(f'{cohort} {window} {name} lacks one or more original ordered scores')
            variants[name] = comparison
            for row in rows:
                mid = row['id']
                actual = '-'.join(map(str, row['actual']))
                forecast, old = (row['forecast'][key] for key in (arm, baseline))
                if actual != old['primary'] and actual == forecast['primary']:
                    first_options[mid].add(name)
                if actual not in old['top3'] and actual in forecast['top3']:
                    three_options[mid].add(name)

    first_hits, three_hits = (market[metric]['baseline_hits'] for metric in METRICS)
    rescues = {}
    within_original_three = 0
    for mid in sorted(first_options.keys() | three_options.keys()):
        identity, _, forecast, _ = original[mid]
        actual = '-'.join(map(str, identity['actual']))
        first, three = sorted(first_options.get(mid, ())), sorted(three_options.get(mid, ()))
        within_original_three += bool(first) and actual in forecast['top3']
        rescues[mid] = dict(actual=actual, original_three=forecast['top3'], correct_first_variants=first,
                            new_three_variants=three)
    dates = sorted({identity['date'] for identity, _, _, _ in original.values()})
    return dict(fixtures=expected, dates=dict(first=dates[0], last=dates[-1], count=len(dates)), baseline=baseline,
                original_hits=dict(first=first_hits, three=three_hits), against_historical_market=market,
                illustrative_stage_counts=dict(first=(expected+4)//5, three=(2*expected+4)//5),
                hindsight_coverage=dict(first=first_hits+len(first_options), three=three_hits+len(three_options),
                                        first_rescues_within_original_three=within_original_three,
                                        first_rescues_outside_original_three=len(first_options)-within_original_three,
                                        new_three_fixtures=len(three_options)),
                variants=variants, rescue_fixtures=rescues)


def audit():
    data, provenance = inputs()
    return dict(mode='HISTORICAL_DATE_SPLIT_DIAGNOSTIC', source_archives=provenance, scopes={
        cohort: {window: scope(data, cohort, baseline, studies, window, count)
                 for window, count in windows.items()}
        for cohort, (baseline, studies, windows) in SCOPES.items()
    })


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2, allow_nan=False))
