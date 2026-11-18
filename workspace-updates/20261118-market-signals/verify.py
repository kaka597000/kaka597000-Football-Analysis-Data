"""Replay market studies offline from the retained input files and source revision."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

TRIAL = Path(__file__).resolve().parent
DATA = TRIAL.parents[1]
EXPECTED = {'2526': 1737, '2627': 481}
FIELDS = ('score_top1', 'score_top3', 'wdl', 'total_strict_full_win')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def read_rows(path):
    with gzip.open(path, 'rt') as handle:
        return [json.loads(line) for line in handle]


def check_fields(actual, expected, where):
    """Match identities, outcomes, labels and integral values exactly across platforms."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), where + ': fields')
        for key in expected:
            check_fields(actual[key], expected[key], where + '.' + key)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), where + ': length')
        for index, (a, b) in enumerate(zip(actual, expected)):
            check_fields(a, b, f'{where}[{index}]')
    elif isinstance(expected, float):
        require(type(actual) is float and math.isclose(actual, expected, abs_tol=1e-10, rel_tol=1e-9),
                where + ': numerical value')
    else:
        require(type(actual) is type(expected) and actual == expected, where + ': value')


def run(source, *args):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(source / 'runtime'), str(source)]),
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    call = [sys.executable, *map(str, args)]
    print('Replaying', *call[1:], file=sys.stderr, flush=True)
    output = subprocess.check_output(call, cwd=DATA, env=env, text=True)
    return json.loads(output)


def checked_rows(folder, report):
    path = folder / 'rows.jsonl.gz'
    expected = report.pop('row_file_sha256')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'row archive changed: ' + str(path))
    return read_rows(path)


def registered():
    transformer = DATA / 'workspace-updates/20261118-transformer'
    archives = {'2526': transformer / 'history/season-holdout.jsonl.gz',
                '2627': transformer / 'transfer/europe-2627-predictions.jsonl.gz'}
    population = {}
    for season, path in archives.items():
        matches = read_rows(path)
        population[season] = {r['match_id']: r['actual'] for r in matches}
        require(len(population[season]) == len(matches) == EXPECTED[season], 'registered cohort differs')
    require(population['2526'].keys().isdisjoint(population['2627']), 'overlapping registered cohorts')
    return population


def check_seasons(rows, population, label):
    for season, expected in population.items():
        selected = [r for r in rows if r['season'] == season]
        ids = {r['match_id']: r['actual'] for r in selected}
        require(len(ids) == len(selected) and ids == expected, label + ': population, identity or score changed')
    require(len(rows) == sum(EXPECTED.values()), label + ': unexpected season')


def historic_comparison(source, branch, work, population):
    folder = TRIAL / branch
    output = work / Path(branch).name
    run(source, folder / 'evaluate.py', '--source', source, '--out', output)
    saved = read(folder / 'report.json')
    computed = read(output / 'report.json')
    rows = checked_rows(folder, saved)
    rebuilt = checked_rows(output, computed)
    check_fields(computed, saved, branch + '.report')
    for old, new in zip(rows, rebuilt, strict=True):
        check_fields(new, old, branch + '.' + old['match_id'])
    check_seasons(rows, population, branch)
    require(saved['eligible'] == len(rows) and saved['exclusions'] == [], branch + ': unexpected exclusions')
    for season, n in EXPECTED.items():
        study = saved['population'][season]
        require((study['registered'], study['paired'], study['missing']) == (n, n, 0), branch + ': coverage')
        group = [r for r in rows if r['season'] == season]
        for arm, metrics in study['metrics']['arms'].items():
            for key in FIELDS:
                counts = metrics['metrics'][key]
                values = [r['outcomes'][arm][key] for r in group if r['outcomes'][arm][key] is not None]
                require((counts['hits'], counts['n']) == (sum(values), len(values)), branch + ': outcomes')
    return dict(EXPECTED)


def consensus(source, population):
    folder = TRIAL / 'consensus'
    run(source, '-m', 'research_program.book_consensus_study', '--data', DATA, '--out', folder, '--verify')
    rows, report = read_rows(folder / 'predictions.jsonl.gz'), read(folder / 'report.json')
    check_seasons(rows, population, 'consensus')
    complete = {}
    for season, n in EXPECTED.items():
        study = report['seasons'][season]
        selected = [r for r in rows if r['season'] == season]
        valid = sum(len(r['quotes']) >= 3 for r in selected)
        require(study['n'] == n and study['complete_panel_only']['n'] == valid and
                study['reference_fallback'] == n - valid, season + ': bookmaker coverage')
        for arm, stats in study['arms'].items():
            for metric in ('top1', 'top3', 'wdl', 'over_under'):
                require(sum(r['outcomes'][arm][metric] for r in selected) == stats['hits'][metric],
                        season + ': bookmaker hits')
        complete[season] = valid
    require(complete == {'2526': 1736, '2627': 481}, 'unexpected named-brand eligibility')
    return complete


def forward(source, registered_ids):
    reports = {}
    current = run(source, '-m', 'research_program.consensus_forward', 'replay', '--state-dir', DATA)
    require(current['population'] == current['issued'] == len(registered_ids) and
            current['pending'] + current['settled'] == len(registered_ids), 'consensus forward coverage')
    reports['consensus'] = current
    for section, module in [('movement', 'market_path_study'), ('handicap', 'handicap_forward')]:
        batch = TRIAL / section / 'forward'
        first = read(batch / 'first-issue.json')
        receipt = run(source, '-m', 'research_program.' + module, 'replay', '--state-dir', DATA, '--batch', batch)
        fixtures = first['payload']['predictions']
        require(set(fixtures) == registered_ids and receipt['plan_sha256'] == first['record_sha256']
                and receipt['population'] == receipt['issued'] == len(registered_ids)
                and all(len(row['arms']) == 2 for row in fixtures.values()), section + ': issued population')
        reports[section] = receipt
    return reports


def team_markets(source, registered_ids):
    retained = TRIAL / 'team-markets/runs'
    summaries = {}
    for name, pop, collected, found_home, found_away, found_btts in (
            ('20261118-first-eu', 6, 6, 0, 0, 6), ('20261118-epl-us-pilot', 7, 2, 2, 2, 2)):
        folder = retained / name
        receipt = run(source, '-m', 'data_sources.team_market_quotes', '--data-root', DATA, '--verify-run', folder)
        coverage = read(folder / 'coverage.json')
        fixtures = coverage['fixtures']
        identities = {r['match_id'] for r in fixtures}
        require(len(identities) == len(fixtures) == pop and
                (pop, collected, found_home, found_away, found_btts) ==
                tuple(receipt[k] for k in ('registered', 'requests', 'fixtures_with_home_05', 'fixtures_with_away_05', 'fixtures_with_btts')),
                name + ': collection population')
        require(sum(bool(f['home_team_05_books']) for f in fixtures) == found_home and
                sum(bool(f['away_team_05_books']) for f in fixtures) == found_away and
                sum(bool(f['btts_books']) for f in fixtures) == found_btts, name + ': raw market coverage')
        if name == '20261118-first-eu':
            require(identities == registered_ids, 'Brazil team market registered IDs')
        else:
            require(Counter(f['status'] for f in fixtures) == {'COLLECTED': 2, 'MAX_EVENTS': 5},
                    'English source request and exclusion count')
            issued = read(TRIAL / 'team-candidate/england/registration.json')
            require(set(issued['fixture_ids']) == {f['match_id'] for f in fixtures if f['status'] == 'COLLECTED'},
                    'English first issue selection changed')
        summaries[name] = {'registered': pop, 'collected': collected, 'btts': found_btts, 'both_team_05': found_home}
    brazil = run(source, '-m', 'research_program.team_market_candidate', 'replay', '--state-dir', DATA)
    require((brazil['population'], brazil['replayed_fixtures'], brazil['replayed_grids']) == (6, 6, 12),
            'Brazilian team candidate coverage')
    england = run(source, '-m', 'research_program.team_market_pilot', 'replay', '--state-dir', DATA)
    require((england['population'], england['first_issues'], england['real_both_team_05_and_btts'],
             england['replayed_grids']) == (2, 2, 2, 4), 'English team candidate coverage')
    return {'collections': summaries, 'brazil': brazil, 'england': england}


def nations(source):
    folder = TRIAL / 'nations-elo'
    run(source, folder / 'replay.py', '--source', source)
    report = read(folder / 'report.json')
    rows = read_rows(folder / 'predictions.jsonl.gz')
    counts = Counter(row['study'] for row in rows)
    excluded = {r['match_id'] for r in report['historical_eligibility_exclusions']}
    played = {r['match_id'] for r in rows}
    require(len(played) == len(rows) and counts == {'2024': 155, '2026': 52} and
            excluded == {'espn:698999'} and excluded.isdisjoint(played) and
            report['population_2024_before_exclusions'] == counts['2024'] + len(excluded), 'Nations League exclusions')
    for year, size in counts.items():
        require(all(v['n'] == size for v in report['campaigns'][year]['evaluation']['arms'].values()),
                year + ': Nations League evaluation denominator')
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    source = parser.parse_args().source.resolve()
    population = registered()
    ids = set(read(TRIAL / 'registration.json')['forward_ids'])
    require(len(ids) == 6, 'registered Brazil forward population')
    receipt = {'consensus_eligible': consensus(source, population)}
    with tempfile.TemporaryDirectory() as temp:
        for section in ('movement/history', 'handicap'):
            receipt[section] = historic_comparison(source, section, Path(temp), population)
    receipt['brazil_forward'] = forward(source, ids)
    receipt['team_markets'] = team_markets(source, ids)
    receipt['nations'] = nations(source)
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
