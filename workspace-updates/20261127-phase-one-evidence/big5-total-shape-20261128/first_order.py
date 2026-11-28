"""Test an R8 first-score switch within the original R7 three."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from research.analysis_freeze import verify
from research_program import continuation_study as archive
from research_program import europe_score_dispersion as input_files
from research_program.goal_state_study import sha, write_new
from research_program.paired_kpi_inference import compare
from research_program.r8_score_study import read
from research_program.ucl_zero_goals import IDENTITY, reference_rows

from replay import verified_grids


FIRST = 'score_top1'


def order(baseline, new_first):
    if new_first not in baseline['top3'] or new_first == baseline['primary']:
        return baseline
    return dict(baseline, primary=new_first, top3=[new_first, *(s for s in baseline['top3'] if s != new_first)])


def score_cell(text):
    return tuple(map(int, text.split('-')))


def switches(original, alternate, grid, gaps):
    baseline, r8 = original['forecast']['candidate'], alternate['forecast']['candidate']
    if (any(original[key] != alternate[key] for key in IDENTITY)
            or alternate['forecast']['r7'] != baseline
            or any(baseline[key] != r8[key] for key in ('wdl', 'total_side', 'total_line'))):
        raise ValueError('archived R7 and R8 fixtures, results or invariant picks differ')
    eligible = baseline['primary'] != r8['primary'] and r8['primary'] in baseline['top3']
    distance = float(grid[score_cell(baseline['primary'])] - grid[score_cell(r8['primary'])]) if eligible else None
    if distance is not None and distance < -1e-12:
        raise ValueError('the frozen R7 first is below its second choice on the reproduced grid')
    result = {'R8_original': r8}
    for arm, threshold in gaps.items():
        result[arm] = order(baseline, r8['primary']) if threshold is not None and eligible and distance <= threshold else baseline
        if set(result[arm]['top3']) != set(baseline['top3']):
            raise ValueError('a switch changed an original top-three member')
    return {**{key: original[key] for key in IDENTITY}, 'forecast': result,
            'eligible_ordinal_disagreement': eligible,
            'r7_probability_gap': round(distance, 12) if eligible else None}


def summarize(rows, gaps):
    base = None
    figures = {}
    for arm in ('R8_original', *gaps):
        if arm == 'r7':
            continue
        pair = compare(rows, baseline='r7', candidate=arm)
        if base is None:
            base = {'score': pair['tracks']['r7']['metrics'], 'first_changes': 0}
        first_changes = sum(row['forecast'][arm]['primary'] != row['forecast']['r7']['primary'] for row in rows)
        figures[arm] = {'score': pair['tracks'][arm]['metrics'], 'first_changes': first_changes,
                        'paired_first': pair['paired'][FIRST], 'paired_three': pair['paired']['score_top3']}
        if arm in gaps and pair['paired']['score_top3']['net_hits'] != 0:
            raise ValueError('an ordinal switch altered three-score hits')
    return {'n': len(rows), 'r8_first_disagreements': figures['R8_original']['first_changes'],
            'r8_first_already_in_r7_three': sum(row['eligible_ordinal_disagreement'] for row in rows),
            'arms': {'r7': base, **figures}}


def run(data, bundle, out):
    study = bundle / 'first-order'
    plan = read(study / 'protocol.json')
    lock = verify(read(study / 'protocol-freeze.json'))
    base_plan = bundle / 'protocol.json'
    if (sha(study / 'protocol.json') != lock['payload']['protocol_sha256']
            or sha(base_plan) != plan['r7_archive_lock_sha256']):
        raise ValueError('the prespecified ordinal study inputs differ')
    periods, gaps = plan['windows'], plan['maximum_gaps']
    reports, across = {}, []
    with TemporaryDirectory(prefix='big-five-first-order-') as temp:
        root = Path(temp)
        input_files.unpack(data, plan['r8_archive'], root / 'r8')
        for code, files in read(base_plan)['archives'].items():
            league = root / code
            for name, item in files.items():
                input_files.unpack(data, item, league / name)
            base, grids = verified_grids(league, code, periods['selection']['from'], periods['next_season_check']['before'])
            lookup = root / 'r8/main' / code
            if read(lookup / 'fit.json')['calibration_through'] >= periods['selection']['from']:
                raise ValueError('R8 was calibrated within the test sample')
            alternate = reference_rows(lookup / 'predictions.jsonl.gz')
            if {ref['id'] for ref in base} != alternate.keys():
                raise ValueError('the historical R7 and R8 populations differ')
            rows = [switches(ref, alternate[ref['id']], grid, gaps) for ref, grid in zip(base, grids, strict=True)]
            results = {}
            for tag, cut in periods.items():
                split = [row for row in rows if cut['from'] <= row['date'] < cut['before']]
                results[tag] = summarize(split, gaps)
                across.extend(dict(row, period=tag) for row in split)
            selection = results['selection']['arms']
            chosen = min(gaps, key=lambda arm: (-selection[arm]['score'][FIRST]['hits'], gaps[arm] or 0))
            delta = {key: 0 if chosen == 'r7' else results[key]['arms'][chosen]['paired_first']['net_hits']
                     for key in ('same_season_check', 'next_season_check')}
            reports[code] = {'selected': chosen, 'check_first_net': delta,
                             'passes_historical_screen': min(delta.values()) >= 0 and max(delta.values()) > 0,
                             'periods': results}
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'verified.json', {'stage': plan['evidence'], 'protocol_freeze': lock['freeze_id'],
                                     'leagues': reports, 'fixtures': len(across)})
    archive.put(out / 'fixtures.jsonl.gz', across)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root, Path(__file__).resolve().parent, args.out)
