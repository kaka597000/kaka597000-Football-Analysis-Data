"""Replay two source-labelled Bet365 observations on the retained European research fixtures."""

import argparse
from collections import Counter
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

import numpy as np
from scipy.stats import poisson

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[3]
UPDATES = DATA / 'workspace-updates'
OLD = UPDATES / '20261118-sequence/history'
TRANS = UPDATES / '20261118-transformer'
PREFIX = 'WCPP/research/remaining-nine-20261105/raw/'


def read(path):
    return json.loads(path.read_bytes())


def rows(path):
    with gzip.open(path, 'rt') as stream:
        return [json.loads(line) for line in stream]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def csvs():
    old = read(OLD / 'sequence-inputs.json')
    archive = DATA / old['archive_path']
    if sha(archive.read_bytes()) != old['archive_sha256']:
        raise ValueError('market CSV bundle checksum mismatch')
    content = {}
    with tarfile.open(archive) as tar:
        for base, digest in old['csv_sha256'].items():
            if base.startswith('2526_'):
                raw = tar.extractfile(PREFIX + base).read()
                if sha(raw) != digest:
                    raise ValueError('past season raw source changed')
                content[base] = raw
    for item in read(TRANS / 'transfer/raw/source-metadata.json'):
        raw = (TRANS / 'transfer/raw' / item['file']).read_bytes()
        if sha(raw) != item['sha256']:
            raise ValueError('new season raw source changed')
        content[item['file']] = raw
    if len(content) != 10:
        raise ValueError('five sources in each of the two seasons required')
    return (
        {k: list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))) for k, raw in content.items()},
        {k: sha(raw) for k, raw in content.items()},
    )


def panel(record, prefix):
    fields = [record.get(prefix + k) for k in ('H', 'D', 'A', '>2.5', '<2.5')]
    try:
        values = np.asarray(fields, dtype=float)
    except (ValueError, TypeError):
        return None
    if not np.isfinite(values).all() or min(values) <= 1:
        return None
    h, d, a, o, u = values.tolist()
    return {
        'bookmaker': 'bet365',
        'h2h': {'home': h, 'draw': d, 'away': a},
        'total': {'line': 2.5, 'over': o, 'under': u},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=HERE)
    args = ap.parse_args()
    sys.path.insert(0, str(args.source.resolve() / 'runtime'))
    from research_program import market_path_study as study

    if sha((HERE.parent / 'protocol.json').read_bytes()) != study.PROTOCOL:
        raise ValueError('different pre-registered recipe')
    raw, index = csvs()
    samples = {r['match_id']: r for r in rows(OLD / 'samples-2526.jsonl.gz')}
    files = {
        '2526': TRANS / 'history/season-holdout.jsonl.gz',
        '2627': TRANS / 'transfer/europe-2627-predictions.jsonl.gz',
    }
    all_rows = []
    result = {}
    exclusions = []
    for season, path in files.items():
        entries = rows(path)
        seen = set()
        for r in entries:
            mid = r['match_id']
            if mid in seen:
                raise ValueError('duplicated target fixture')
            seen.add(mid)
            if season == '2526':
                old = samples[mid]
                fname, lineno = old['source_file'], old['source_line']
                teams = [old['home'], old['away']]
                rates = old['rates']
                original = old['market']
            else:
                fname, lineno = r['source']
                teams = r['teams']
                rates = r['goal_rates']
                original = r['raw_prices']
            raw_row = raw[fname][lineno - 2]
            actual = [int(raw_row['FTHG']), int(raw_row['FTAG'])]
            day = datetime.strptime(raw_row['Date'], '%d/%m/%Y').date().isoformat()
            if (
                teams != [raw_row['HomeTeam'], raw_row['AwayTeam']]
                or day != r['matchday']
                or actual != r['actual']
                or not fname.startswith(season + '_')
            ):
                raise ValueError('bad source fixture join')
            early, latest = panel(raw_row, 'B365'), panel(raw_row, 'B365C')
            if latest is None or {k: latest[k] for k in ('total', 'h2h')} != original:
                raise ValueError('benchmark closing quote not reproduced')
            if early is None:
                exclusions.append(
                    {
                        'season': season,
                        'match_id': mid,
                        'source': [fname, lineno],
                        'reason': 'incomplete earlier Bet365 panel',
                    }
                )
                continue
            values = poisson.pmf(np.arange(26)[:, None], np.asarray(rates)[None, :])
            base = np.outer(values[:, 0], values[:, 1])
            if abs(base.sum() - 1) > 1e-10:
                raise ValueError('goal scores support truncated')
            estimates = study.arms(base / base.sum(), early, latest)
            preds = {}
            outcomes = {}
            for k, matrix in estimates.items():
                forecast = study.forecast(matrix, latest['total']['line'])
                outcomes[k] = study.outcome(forecast, {'home': actual[0], 'away': actual[1]})
                preds[k] = {key: v for key, v in forecast.items() if key != 'matrix'}
            check = preds['latest_only']
            published = r['forecasts']['baseline']
            if (
                any(check[k] != published[k] for k in ('primary', 'wdl'))
                or check['total']['direction'] != published['total']['direction']
                or abs(check['primary_probability'] - published['primary_probability']) > 1e-12
            ):
                raise ValueError('original closing-market benchmark differs')
            all_rows.append(
                {
                    'match_id': mid,
                    'cohort': r['cohort'],
                    'season': season,
                    'matchday': day,
                    'teams': teams,
                    'actual': actual,
                    'source_row': [fname, lineno],
                    'early': early,
                    'latest': latest,
                    'goal_rates': rates,
                    'total_movement': study.move_type(early, latest),
                    'forecasts': preds,
                    'outcomes': outcomes,
                }
            )
        selected = [r for r in all_rows if r['season'] == season]
        result[season] = {
            'registered': len(entries),
            'paired': len(selected),
            'missing': len(entries) - len(selected),
            'dates': [min(r['matchday'] for r in selected), max(r['matchday'] for r in selected)],
            'total_movement_counts': dict(Counter(r['total_movement'] for r in selected)),
            'metrics': study.summarize(selected),
        }
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    content = b''.join(
        (json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
        for r in all_rows
    )
    zipped = gzip.compress(content, mtime=0)
    (out / 'rows.jsonl.gz').write_bytes(zipped)
    report = {
        'protocol_sha256': study.PROTOCOL,
        'observations': 'Earlier sampled B365 and closing B365C fields. No individual price timestamps or true first-book opening certified.',
        'scope': 'Frozen design retrospective. Scores and source snapshots retrieved after the matches.',
        'population': result,
        'exclusions': exclusions,
        'source_csv_sha256': index,
        'reference_sources_sha256': {
            str(p.relative_to(DATA)): sha(p.read_bytes())
            for p in (*files.values(), OLD / 'samples-2526.jsonl.gz')
        },
        'row_file_sha256': sha(zipped),
        'eligible': len(all_rows),
    }
    (out / 'report.json').write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(
        json.dumps(
            {
                season: {k: v['metrics'] for k, v in item['metrics']['arms'].items()}
                for season, item in result.items()
            }
        )
    )


if __name__ == '__main__':
    main()
