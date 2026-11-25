"""Check the original historical population, same-match controls, paired counts, and short-day seats."""

from collections import defaultdict
import csv
import gzip
from io import StringIO
import json

from bundle_io import require
from evidence import read, unique

OUTPUTS = ('fit.json', 'forward.json', 'inputs.json', 'metrics.json', 'forecasts.jsonl.gz', 'seats.jsonl.gz')


def read_rows(path):
    with gzip.open(path, 'rb') as stream:
        return [json.loads(line) for line in stream]


def table(rows):
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def window(day):
    for name, end in (('training', '2024-01-01'), ('validation', '2025-01-01'), ('evaluation', '2026-01-01')):
        if day < end:
            return name
    return 'recent'


def audit(study, games, controls, failures):
    fit, recipe, metrics = (read(study / f'{n}.json') for n in ('fit', 'forward', 'metrics'))
    predicted = unique(read_rows(study / 'forecasts.jsonl.gz'), 'id')
    days = unique(read_rows(study / 'seats.jsonl.gz'), 'date')
    bad = {r['match_id'] for r in failures}
    folds = defaultdict(list)
    for mid, game in games.items():
        folds[window(game['date'])].append(mid)
    require(fit['coverage'] == {w: dict(fixtures=len(ids), verified_halves=sum(m not in bad for m in ids))
                                for w, ids in folds.items()}, 'full denominators by original registered window')
    require(recipe['training_games'] == len(games) and fit['doses'] == recipe['doses']
            and fit['calibration']['training_observed'] == fit['coverage']['training']['verified_halves']
            and recipe['calibration']['training_observed'] == len(games) - len(bad), 'two calibration populations and validation doses')
    require(predicted.keys() == set(folds['evaluation'] + folds['recent']), 'all evaluation and recent slots')
    by_day = defaultdict(list)
    for mid, row in predicted.items():
        g, picks = games[mid], row['forecast']
        r5, r7, r10 = (controls[k][mid] for k in ('r5', 'r7', 'r10'))
        require(row['date'] == g['date'] and row['actual'] == [g['home_goals'], g['away_goals']]
                and row['window'] == window(g['date']) and row['line'] == r5['line'] == r7['line'] == r10['line']
                and picks['r5'] == r5['forecast']['candidate']
                and picks['r7'] == r7['forecast']['candidate'] and picks['r10'] == r10['forecast']['candidate']
                and picks['market'] == r5['forecast']['market'] == r7['forecast']['market'] == r10['forecast']['market'],
                ('same-game controls', mid))
        if row['line'] is None:
            require(all(p.get('total_line') is None and p.get('total_side') is None for p in picks.values()),
                    ('invented or mismatched total', mid))
        if not any(fit['doses'].values()):
            require(picks['candidate'] == picks['r7'], ('zero-dose decisions', mid))
        by_day[row['date']].append(row)
    require(days.keys() == by_day.keys(), 'all registered dates')
    seat_table, kpis, paired, weights = [], [], [], []
    for d, candidates in sorted(by_day.items()):
        day = days[d]
        ranked = sorted(candidates, key=lambda r: (-r['quality']['candidate']['p_first'], r['id']))[:3]
        require([s['id'] for s in day['selected']] == [r['id'] for r in ranked]
                and len(candidates) == day['fixtures'], ('selected seats and short days', d))
        for seat, (s, r) in enumerate(zip(day['selected'], ranked, strict=True), 1):
            p = r['forecast']['candidate']
            actual = '-'.join(map(str, r['actual']))
            expected = dict(seat=seat, id=r['id'], p_first=r['quality']['candidate']['p_first'], primary=p['primary'],
                            top3=p['top3'], actual=actual, first_hit=actual == p['primary'], three_hit=actual in p['top3'])
            require(expected == s, ('per-seat forecast', d, seat))
            seat_table.append(dict(window=day['window'], date=d, fixtures=len(candidates), **(s | {'top3': '|'.join(p['top3'])}),
                                   three_first_sweep=day['three_first_sweep']))
        sweep = all(s['first_hit'] for s in day['selected']) if len(ranked) == 3 else None
        require(day['three_first_sweep'] == sweep, ('short/full exact-first sweep', d))
    for w, summary in metrics.items():
        n = len(folds[w])
        require(summary['registered'] == n and summary['observed_lines'] == sum(predicted[m]['line'] is not None for m in folds[w]),
                ('registered OU coverage', w))
        for track, totals in summary['tracks'].items():
            for metric, v in totals['metrics'].items():
                require(v['resolved_gate_denominator'] == n and 0 <= v['hits'] <= v['eligible'] <= n,
                        ('track denominator', w, track, metric))
                kpis.append(dict(window=w, track=track, metric=metric, **v))
        for baseline, items in summary['paired'].items():
            for metric, v in items.items():
                require(v['resolved_gate_denominator'] == n and v['eligible'] == v['gained'] + v['lost'] + v['tied']
                        and v['net_hits'] == v['gained'] - v['lost'], ('paired gain/loss counts', w, baseline, metric))
                paired.append(dict(window=w, baseline=baseline, metric=metric, **{k: json.dumps(x, separators=(',', ':'))
                              if isinstance(x, list) else x for k, x in v.items()}))
    for label, calibration in (('before_2024', fit['calibration']), ('through_2026_11_21', recipe['calibration'])):
        weights.append(dict(fit=label, observations=calibration['training_observed'], home_share=calibration['shares'][0],
                            away_share=calibration['shares'][1], leading=calibration['leading'], trailing=calibration['trailing'],
                            score_dose=fit['doses']['score'], wdl_dose=fit['doses']['wdl'], total_dose=fit['doses']['total']))
    failed = [dict(match_id=r['match_id'], window=window(games[r['match_id']]['date']), reason=r['reason'],
                   source_sha256=r['source_sha256']) for r in failures]
    return {'window-kpis.csv': table(kpis), 'paired-intervals.csv': table(paired), 'selected-seats.csv': table(seat_table),
            'weights.csv': table(weights), 'ineligible.csv': table(failed)}
