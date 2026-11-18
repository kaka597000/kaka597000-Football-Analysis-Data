"""Independently compare paired opening-independent closing forecasts, adding Asian handicap."""

import argparse
from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
MOVEMENT = HERE.parent / 'movement/history'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True, type=Path)
    ap.add_argument('--out', type=Path, default=HERE)
    args = ap.parse_args()
    sys.path.insert(0, str(args.source.resolve() / 'runtime'))
    from research_program import handicap_matrix_study as ah
    from research_program import market_path_study as metrics

    spec = importlib.util.spec_from_file_location('registered_match_sources', MOVEMENT / 'evaluate.py')
    io = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(io)
    if io.sha((HERE / 'protocol.json').read_bytes()) != ah.PROTOCOL:
        raise ValueError('wrong pre-registered handicap study')
    previous = io.read(MOVEMENT / 'report.json')
    rowfile = MOVEMENT / 'rows.jsonl.gz'
    if (
        io.sha(rowfile.read_bytes()) != previous['row_file_sha256']
        or previous['eligible'] != 2218
        or any(r['registered'] != r['paired'] for r in previous['population'].values())
    ):
        raise ValueError('underlying fixture or closing market population changed')
    raw, csv_sha = io.csvs()
    results = []
    exclusions = []
    for entry in io.rows(rowfile):
        filename, lineno = entry['source_row']
        src = raw[filename][lineno - 2]
        if [src['HomeTeam'], src['AwayTeam']] != entry['teams'] or [
            int(src['FTHG']),
            int(src['FTAG']),
        ] != entry['actual']:
            raise ValueError('source-row identity differs')
        try:
            line, h, a = map(float, (src['AHCh'], src['B365CAHH'], src['B365CAHA']))
        except (KeyError, TypeError, ValueError):
            line, h, a = np.nan, np.nan, np.nan
        if not np.isfinite([line, h, a]).all() or min(h, a) <= 1 or not (line * 4).is_integer():
            exclusions.append(
                {
                    'match_id': entry['match_id'],
                    'season': entry['season'],
                    'source': entry['source_row'],
                    'reason': 'incomplete same-book closing handicap',
                }
            )
            continue
        handicap = {'bookmaker': 'bet365', 'line': line, 'home': h, 'away': a}
        values = poisson.pmf(np.arange(26)[:, None], np.asarray(entry['goal_rates'])[None, :])
        base = np.outer(values[:, 0], values[:, 1])
        matrices, diagnostic = ah.project(base / base.sum(), entry['latest'], handicap)
        preds = {k: metrics.forecast(m, entry['latest']['total']['line']) for k, m in matrices.items()}
        baseline, candidate = preds.values()
        old = entry['forecasts']['latest_only']
        if (
            any(baseline[k] != old[k] for k in ('primary', 'top3', 'wdl'))
            or baseline['total']['direction'] != old['total']['direction']
        ):
            raise ValueError('matched closing-only baseline differs')
        # A numerical tie of exact market margins inherits the registered benchmark tiebreak.
        margins = np.array([list(p['wdl_probabilities'].values()) for p in preds.values()])
        np.testing.assert_allclose(margins[0], margins[1], atol=5e-11, rtol=0)
        for side in ('over', 'under'):
            a, b = [p['total']['settlements'][side] for p in preds.values()]
            np.testing.assert_allclose([a['win'], a['loss']], [b['win'], b['loss']], atol=5e-11, rtol=0)
        candidate['wdl'] = baseline['wdl']
        candidate['total']['direction'] = baseline['total']['direction']
        actual = dict(zip(('home', 'away'), entry['actual']))
        scores = {k: metrics.outcome(p, actual) for k, p in preds.items()}
        forecast = {k: {key: v for key, v in p.items() if key != 'matrix'} for k, p in preds.items()}
        results.append(
            {
                **{
                    k: entry[k]
                    for k in (
                        'match_id',
                        'matchday',
                        'season',
                        'cohort',
                        'teams',
                        'actual',
                        'source_row',
                        'latest',
                        'goal_rates',
                    )
                },
                'ah': handicap,
                'diagnostic': diagnostic,
                'forecasts': forecast,
                'outcomes': scores,
            }
        )
    seasons = {}
    for season, initial in previous['population'].items():
        selected = [r for r in results if r['season'] == season]
        errors = {
            k: float(
                np.mean([abs(r['diagnostic'][k] - r['diagnostic']['home_target_share']) for r in selected])
            )
            for k in ('home_reference_share', 'home_adjusted_share')
        }
        seasons[season] = {
            'registered': initial['registered'],
            'paired': len(selected),
            'missing': initial['registered'] - len(selected),
            'closing_handicap_line_counts': dict(Counter(r['ah']['line'] for r in selected)),
            'mean_absolute_home_share_gap': errors,
            'metrics': metrics.summarize(selected, ah.NAMES),
        }
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    zipped = gzip.compress(
        b''.join(
            (json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
            for r in results
        ),
        mtime=0,
    )
    (out / 'rows.jsonl.gz').write_bytes(zipped)
    report = {
        'protocol_sha256': ah.PROTOCOL,
        'source_csv_sha256': csv_sha,
        'registered_rows_sha256': previous['row_file_sha256'],
        'row_file_sha256': io.sha(zipped),
        'eligible': len(results),
        'exclusions': exclusions,
        'population': seasons,
        'role': 'Paired fixed retrospective market recalibration. Both joint score distributions retain the same fair WDL and actual total probability; only score-shape differences can change point picks.',
        'evidence': 'Football-Data historical Bet365 closing fields without provider quote times; no prospective handicap settlement from this historical reconstruction.',
    }
    (out / 'report.json').write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(
        json.dumps(
            {
                season: {k: v['metrics'] for k, v in item['metrics']['arms'].items()}
                for season, item in seasons.items()
            }
        )
    )


if __name__ == '__main__':
    main()
