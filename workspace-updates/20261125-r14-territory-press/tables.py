"""Independently settle the R14 forecast ledgers and render the data-PR tables."""

from collections import Counter, defaultdict
import csv
from datetime import date
import gzip
import hashlib
import io
import json
import math

CODES = ('eng.1', 'esp.1', 'ger.1', 'ita.1', 'fra.1')
METRICS = ('score_top1', 'score_top3', 'wdl', 'actual_ou')
FEATURES = ('own_xg_attack', 'opponent_xg_concession', 'own_deep_attack',
            'opponent_deep_concession', 'own_pressing', 'opponent_pressing')
PAIRS = {name: (name, 'candidate') for name in ('r7', 'r10', 'market', 'xg', 'xg_matched_dose')}
PAIRS.update(same_runtime=('local_r7', 'local_candidate'), fixed_increment=('fixed_xg', 'fixed_full'))
SETTLEMENTS = ('FULL_WIN', 'HALF_WIN', 'PUSH', 'HALF_LOSS', 'FULL_LOSS')


def check(ok, message):
    if not ok:
        raise ValueError(str(message))


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(s) for s in stream if s.strip()]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def csv_bytes(rows):
    text = io.StringIO(newline='')
    csv.writer(text, lineterminator='\n').writerows(rows)
    return text.getvalue().encode('utf-8')


def indicators(row, prediction):
    h, a = row['actual']
    score = f'{h}-{a}'
    direction = 'home' if h > a else 'away' if a > h else 'draw'
    top = prediction.get('top3')
    if top:
        check(len(top) == len(set(top)) == 3 and top[0] == prediction['primary'], (row['id'], top))
    pay = None
    if prediction.get('total_side'):
        line, side = row['line'], prediction['total_side']
        check(side in ('over', 'under') and prediction['total_line'] == line, (row['id'], 'total'))
        ticks = round(4 * line)
        check(ticks == 4 * line, (row['id'], 'quarter line'))
        legs = (ticks - 1, ticks + 1) if ticks % 2 else (ticks, ticks)
        diff = [((h + a) * 4 - leg) * (1 if side == 'over' else -1) for leg in legs]
        pay = SETTLEMENTS[2 - sum((d > 0) - (d < 0) for d in diff)]
    return (score == prediction['primary'] if prediction.get('primary') else None,
            score in top if top else None, direction == prediction['wdl'] if prediction.get('wdl') else None,
            pay == 'FULL_WIN' if pay and pay != 'PUSH' else None), pay


def diagnostics(row, observed):
    process = row['process']
    x = row['features']
    check(len(x) == 2 and all(len(side) == 6 and all(math.isfinite(v) and abs(v) <= 1 for v in side)
                              for side in x), (row['id'], 'design'))
    counts = Counter()
    for j, name in enumerate(('nonzero_xg', 'nonzero_territory', 'nonzero_press')):
        counts[name] = int(any(side[k] for side in x for k in (2*j, 2*j+1)))
    old, new = observed['r7'][0], observed['candidate'][0]
    for i, name in enumerate(('first', 'three')):
        counts[name + '_gained'] = int(bool(new[i]) and not old[i])
        counts[name + '_lost'] = int(bool(old[i]) and not new[i])
    day, cutoff = map(date.fromisoformat, (row['date'], process['cutoff']))
    check(process['competition'] == row['cohort'] and process['date'] == row['date'] and cutoff <= day,
          (row['id'], 'feature identity'))
    for side in ('home', 'away'):
        history = list(map(date.fromisoformat, process[side + '_history_dates']))
        check(len(history) <= 8 and all(d < cutoff and (day-d).days <= 150 for d in history),
              (row['id'], 'history cutoff', side))
        counts[side + '_method/' + process[side + '_method']] += 1
        counts[side + '_status/' + process[side + '_status']] += 1
    counts['fixture_audit/' + process['target_fixture_audit']['status']] += 1
    return counts


def weights(study, modes):
    table = [['panel', 'competition', 'phase', 'arm', 'through', 'validation_through', 'validation_games',
              'training_games', 'games_with_signal', 'fit_games', 'scoring_fit_sides', 'positive_fit_sides',
              'ridge', 'feature_limit', 'coefficient_bound', 'shift_limit', 'ipf_rtol', 'ipf_max_iter',
              'score_dose', 'wdl_dose', 'total_dose', 'feature', 'scoring_beta', 'positive_beta']]
    for mode in modes:
        for code in CODES:
            folder = study / mode / code
            fit = read(folder / 'fit.json')
            check(fit['competition'] == code and fit['training_through'] < fit['bounds'][0]
                  <= fit['validation_through'] < fit['bounds'][1], (mode, code, 'calendar'))
            phases = [('train', fit['training_through'], fit['fitted'], fit['doses'])]
            if mode == 'main':
                forward = read(folder / 'forward.json')
                check(forward['fit_sha256'] == sha(folder / 'fit.json') and forward['competition'] == code,
                      (code, 'forward fit binding'))
                phases.append(('forward', forward['through'], dict(full=forward['fitted'], xg=forward['xg_fitted']),
                               dict(full=forward['doses'], xg=forward['xg_doses'])))
            for phase, through, fits, doses in phases:
                check(set(fits) == set(doses) == {'full', 'xg'}, (mode, code, phase))
                for arm in ('xg', 'full'):
                    f = fits[arm]
                    features = FEATURES[:2] if arm == 'xg' else FEATURES
                    check(f['xg_only'] is (arm == 'xg') and tuple(f['features']) == features
                          and (f['ridge'], f['coefficient_bound'], f['shift_limit']) == (24, 1.5, .65)
                          and (phase != 'train' or f['training_games'] == fit['train_n'])
                          and 0 <= f['fit_games'] <= f['games_with_signal'] <= f['training_games'],
                          (mode, code, phase, arm, 'weight metadata'))
                    counts = [f[k] for k in table[0][7:18]]
                    policy = [doses[arm][k] for k in ('score', 'wdl', 'total')]
                    check(all(v in (0., .5, 1.) for v in policy), (code, arm, 'dose'))
                    for feature, s, p in zip(features, f['scoring_beta'], f['positive_beta'], strict=True):
                        check(all(math.isfinite(v) and abs(v) <= 1.5 for v in (s, p)), (code, feature))
                        table.append([mode, code, phase, arm, through, fit['validation_through'],
                                      fit['validation_n'], *counts, *policy, feature, s, p])
    return csv_bytes(table)


def first_issues(folder, ranked):
    ref = read(ranked / 'plan.json')
    selected = read(ranked / ref['file'])['payload']['identity']['selected']
    rank = {v['match_id']: i for group in selected.values() for i, v in enumerate(group, 1)}
    table = [['competition', 'match_id', 'kickoff', 'first_issue', 'recorded_at', 'home', 'away',
              'first', 'second', 'third', 'wdl', 'line', 'total_side', 'r7_first', 'r10_first', 'xg_first',
              'home_history_games', 'away_history_games', 'competition_rank']]
    for mid, receipt in sorted(read(folder / 'receipts.json')['matches'].items()):
        record = read(folder / receipt['file'])
        p, g = record['payload'], record['fixture']
        candidate = p['forecasts']['candidate']
        table.append([g['cohort'], mid, g['kickoff_at'], record['freeze_id'], record['recorded_at'],
                      p['home_name'], p['away_name'], *candidate['top3'], candidate['wdl'], p['line'],
                      candidate['total_side'], *(p['forecasts'][k]['primary'] for k in ('r7', 'r10', 'xg')),
                      *(len(p['process'][s + '_history_dates']) for s in ('home', 'away')), rank.get(mid)])
    return csv_bytes(table)


def replay_tables(study):
    modes = ['main', 'independent'] if read(study / 'inputs.json')['independent_requested'] else ['main']
    reports = read(study / 'metrics.json')
    groups = defaultdict(list)
    seen = set()
    for mode in modes:
        check({p.name for p in (study / mode).iterdir() if p.is_dir()} == set(CODES), (mode, 'leagues'))
        for code in CODES:
            rows = lines(study / mode / code / 'forecasts.jsonl.gz')
            check(rows, (mode, code, 'empty ledger'))
            for r in rows:
                key = (code, r['id'])
                check(r['cohort'] == code and key not in seen, (mode, key))
                seen.add(key)
                observed = {a: indicators(r, p) for a, p in r['forecast'].items()}
                detail = diagnostics(r, observed)
                for scope in (code, 'ALL'):
                    groups[r['window'], scope].append((code + '|' + r['id'], observed, detail))

    check(set(reports) == {w for w, _ in groups}, 'replay window inventory')
    totals = [['window', 'competition', 'arm', 'metric', 'hits', 'denominator', *SETTLEMENTS]]
    paired = [['window', 'competition', 'comparison', 'metric', 'paired', 'control_hits', 'candidate_hits',
               'net', 'disagreements', 'ci_low_pp', 'ci_high_pp']]
    audit = [['window', 'competition', 'diagnostic', 'count']]
    for window, report in sorted(reports.items()):
        whole = groups[window, 'ALL']
        ids = '\n'.join(sorted(mid for mid, _, _ in whole)).encode()
        check(hashlib.sha256(ids).hexdigest() == report['fixture_set_sha256'], (window, 'fixture hash'))
        arms = {arm for _, values, _ in whole for arm in values}
        check(set(report['competitions']) == {c for w, c in groups if w == window and c != 'ALL'},
              (window, 'cohort inventory'))
        for code, summary in [('ALL', report['overall']), *sorted(report['competitions'].items())]:
            rows = groups[window, code]
            check(set(summary['scores']) == arms and set(summary['comparisons']) >= PAIRS.keys(),
                  (window, code, 'arms or comparisons'))
            detail = Counter()
            for _, _, diagnostics_row in rows:
                detail.update(diagnostics_row)
            for k, v in summary['coverage_and_changes'].items():
                if k in detail:
                    check(v == detail[k], (window, code, k))
            for k in sorted(detail):
                audit.append([window, code, k, detail[k]])
            for arm, saved in sorted(summary['scores'].items()):
                values = [v[arm] for _, v, _ in rows if arm in v]
                pay = Counter(p for _, p in values if p)
                check(len(rows) == saved['games'] and pay == saved['settlements'], (window, code, arm, 'settlements'))
                for i, metric in enumerate(METRICS):
                    available = [v[i] for v, _ in values if v[i] is not None]
                    count = [sum(available), len(available)]
                    check(count == saved['counts'][metric], (window, code, arm, metric))
                    totals.append([window, code, arm, metric, *count, *(pay[k] for k in SETTLEMENTS)])
            for name, (a, b) in PAIRS.items():
                saved = summary['comparisons'][name]
                values = [(v[a][0], v[b][0]) for _, v, _ in rows if a in v and b in v]
                for i, metric in enumerate(METRICS):
                    pairs = [(u[i], v[i]) for u, v in values if u[i] is not None and v[i] is not None]
                    old, new = sum(u for u, _ in pairs), sum(v for _, v in pairs)
                    count = [len(pairs), old, new, new-old, sum(u != v for u, v in pairs)]
                    if not saved:
                        check(not pairs, (window, code, name, metric, 'missing pairs'))
                        continue
                    item = saved[metric]
                    check(count == [item[k] for k in paired[0][4:9]], (window, code, name, metric, 'paired'))
                    paired.append([window, code, name, metric, *count, *(item['delta_pp_ci95'] or ['', ''])])
    return {'competition-metrics.csv': csv_bytes(totals), 'comparisons.csv': csv_bytes(paired),
            'diagnostics.csv': csv_bytes(audit), 'weights.csv': weights(study, modes)}
