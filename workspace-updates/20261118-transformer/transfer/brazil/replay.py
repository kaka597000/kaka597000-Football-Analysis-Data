"""Re-evaluate the nine archived Brazil Current first issues with locked before-season coefficients."""
import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parents[1]
UPDATES = EXPERIMENT.parent
EARLY_CUTOFF = '2026-08-01T00:00:00Z'


def read(path):
    return json.loads(path.read_bytes())


def read_rows(path):
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(stamp):
    value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('explicit timestamp required')
    return value


def same_refit(early, final):
    before, after = read(early), read(final)
    if before['cutoff_at'] != EARLY_CUTOFF or before['training_matches'] != 3036:
        raise ValueError(f'unexpected training scope: {early.name}')
    if {k: v for k, v in before.items() if k != 'cutoff_at'} != {k: v for k, v in after.items() if k != 'cutoff_at'}:
        raise ValueError(f'season-boundary fitted coefficients differ: {early.name}')
    return before


def replay(source, transformer_file, sequence_file, out):
    sequence_history = UPDATES / '20261118-sequence/history'
    trial_history = EXPERIMENT / 'history'
    sys.path[:0] = [str(sequence_history.parent), str(source / 'runtime'), str(source), str(sequence_history), str(trial_history)]
    from verify import compare as compare_reference
    from research_program import three_arm_model
    from run_models import evaluate, encoded
    from run_study import apply_holdout, summarize

    transformer = same_refit(transformer_file, trial_history / 'artifact.json')
    alternatives = same_refit(sequence_file, sequence_history / 'artifact.json')
    if transformer['sample_sha256'] != alternatives['sample_sha256']:
        raise ValueError('four-arm transfer does not share the same training population')
    training = [r for season in ('2425', '2526') for r in read_rows(sequence_history / f'samples-{season}.jsonl.gz')]
    latest = max(r['game_date'] for r in training)
    if (len({r['match_id'] for r in training}) != 3036 or latest != '2026-05-24'
            or {r['cohort'] for r in training} != {'eng.1', 'ita.1', 'ger.1', 'fra.1', 'esp.1'}):
        raise ValueError('training source population does not agree with historic results')

    previous = read(sequence_history / 'brazil-transfer-validation.json')
    source_files = [
        UPDATES / '20261118-three-arm/training/actual_current.jsonl.gz',
        sequence_history / 'brazil/sequences.json',
        sequence_history / 'brazil-transfer-rows.jsonl.gz',
    ]
    if any(sha(p) != previous['source_sha256'][p.name] for p in source_files):
        raise ValueError('archived first issue, history or previous score comparison changed')
    past = [r for r in read_rows(source_files[0]) if r['cohort'] == 'bra.1']
    ledger = read(source_files[1])
    saved_three = {r['match_id']: r for r in read_rows(source_files[2])}
    if len(past) != 9 or set(ledger) != {r['match_id'] for r in past}:
        raise ValueError('unexpected archived Brazil first-issue population')
    rows, missing = [], []
    for row in past:
        mid = row['match_id']
        evidence = ledger[mid]
        cutoff = instant(row['cutoff_at'])
        kickoff = instant(row['kickoff_at'])
        if (evidence['population'] != 'archived_current' or cutoff != instant(evidence['cutoff_at'])
                or kickoff != instant(evidence['kickoff_at']) or not instant(EARLY_CUTOFF) <= cutoff < kickoff):
            raise ValueError(f'original forecast timing conflict for {mid}')
        for matches in evidence['lineage'].values():
            for match in matches['matches']:
                if match and (instant(match['observed_at']) > cutoff or instant(match['kickoff_at']).date() >= kickoff.date()):
                    raise ValueError(f'late original history for {mid}')
        if row['market'] is None:
            missing.append(mid)
            continue
        if any(sum(step[-1] for step in team) != 5 for team in evidence['sequence']):
            raise ValueError(f'incomplete eligible sequence for {mid}')
        market = three_arm_model._quote_values(row['market'], cutoff)
        baseline = three_arm_model._market_matrix(three_arm_model._matrix(row['current_matrix']), market)
        rows.append(dict(row, sequence=evidence['sequence'], baseline_matrix=baseline, game_date=kickoff.date().isoformat()))

    historical_three = evaluate(alternatives, rows)
    compare_reference({r['match_id']: r for r in historical_three}, saved_three, 'archived Brazil reference forecasts')
    evaluated = [apply_holdout(transformer, row, old) for row, old in zip(rows, historical_three, strict=True)]
    report = {
        'scope': 'Retrospective transfer to all earlier Brazilian Current freezes with paired source-timed 1X2 and totals.',
        'status': 'RESEARCH_REPLAY', 'real_forward': False, 'registered_archived_forecasts': len(past),
        'eligible': len(evaluated), 'coverage': len(evaluated) / len(past), 'missing_paired_market': missing,
        'training_matches': len(training), 'last_training_result_date': latest, 'replay_training_cutoff': EARLY_CUTOFF,
        'training_population_sha256': transformer['sample_sha256'], 'evaluation_match_ids': [r['match_id'] for r in evaluated],
        'same_refitted_weights_as_final': True, 'matched_original_three_arms': True,
        'source_hashes': {str(p.relative_to(UPDATES)): sha(p) for p in [*source_files, transformer_file, sequence_file]},
        'same_day_ranges': 'Both eligible fixtures are November 14, 2026. A matchday block confidence interval needs additional days.',
        'summary': summarize(evaluated),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / 'rows.jsonl.gz').write_bytes(gzip.compress(
        b''.join(json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n' for r in evaluated),
        mtime=0))
    (out / 'report.json').write_bytes(encoded(report))
    print(json.dumps({key: v['hits'] for key, v in report['summary']['arms'].items()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--transformer', type=Path, default=HERE.parent / 'transformer-before-season.json')
    parser.add_argument('--sequence', type=Path, default=HERE.parent / 'sequence-before-season.json')
    parser.add_argument('--out', type=Path, default=HERE)
    args = parser.parse_args()
    replay(args.source.resolve(), args.transformer.resolve(), args.sequence.resolve(), args.out.resolve())
