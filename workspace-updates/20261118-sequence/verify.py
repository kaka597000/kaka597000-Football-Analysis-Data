"""Replay the registered sequence experiment offline from archived inputs and fitted weights."""
import argparse
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tarfile
from unittest.mock import patch

import numpy as np

EXPERIMENT = Path(__file__).resolve().parent
DATA = EXPERIMENT.parents[1]
PREVIOUS = EXPERIMENT.with_name('20261118-three-arm')
REGISTRATION = '8969e0945ad7a24d666ba0000bfd5c115fa461d961ef0760b6ba104e936a0db3'
BASELINE_ARCHIVE = '3f842a58a73eb453d354e8a770c934378785714189c2e73bf190f77596534e49'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def checked(path, expected):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'checksum mismatch: ' + str(path))
    return raw


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(path):
    with gzip.open(path, 'rt', encoding='utf-8') as rows:
        return [json.loads(row) for row in rows]


def compare(actual, expected, name):
    if isinstance(expected, dict):
        require(actual.keys() == expected.keys(), name + ': fields differ')
        for key in expected:
            compare(actual[key], expected[key], name + '.' + key)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), name + ': length differs')
        if expected and isinstance(expected[0], (list, float)):
            np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-13, err_msg=name)
        else:
            for i, value in enumerate(expected):
                compare(actual[i], value, name)
    elif isinstance(expected, float):
        require(math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-13), name + ': number differs')
    else:
        require(actual == expected, name + ': value differs')


def verify_development(source):
    from research.analysis_freeze import aware
    from research_program import sequence_history, sequence_models, three_arm_model
    history = EXPERIMENT / 'history'
    data_manifest = read(history / 'sequence-inputs.json')
    games, targets, origin = sequence_history._historical_inputs(DATA)
    for key, value in origin.items():
        require(data_manifest[key] == value, 'European source inputs differ: ' + key)
    for name, count in (('samples-2425.jsonl.gz', 1299), ('samples-2526.jsonl.gz', 1737)):
        entry = data_manifest['files'][name]
        checked(history / name, entry['sha256'])
        require(entry['n'] == count, 'input inventory differs for ' + name)
    raw = sequence_history.rolling_sequences(games, targets)
    train, holdout = (records(history / f'samples-{s}.jsonl.gz') for s in ('2425', '2526'))
    require(len(games) == data_manifest['source_games'] and len(train) == 1299 and len(holdout) == 1737
            and train + holdout == raw, 'European retained histories, dated results or markets differ from raw data')
    report = read(history / 'season-validation.json')
    path_map = {'sequence_history.py': Path(sequence_history.__file__), 'sequence_models.py': Path(sequence_models.__file__)}
    for name, checksum in report['sources_sha256'].items():
        checked(path_map.get(name, history / name), checksum)
    runner = load_module(history / 'run_models.py')
    early, final = (read(history / name) for name in ('season-training-artifact.json', 'artifact.json'))
    for artifact, count, cutoff in ((early, len(train), runner.STUDY_CUTOFF), (final, len(raw), runner.TRIAL_CUTOFF)):
        require(artifact['cutoff_at'] == cutoff and artifact['training_matches'] == count
                and artifact['version'] == sequence_models.VERSION and artifact['seed'] == sequence_models.SEED
                and artifact['active_model_changed'] is False and artifact['lstm_config'] == sequence_models.LSTM_CONFIG
                and artifact['lightgbm_config'] == sequence_models.TREE_CONFIG and artifact['ridge'] == sequence_models.RIDGE
                and artifact['max_abs_tilt'] == sequence_models.MAX_TILT
                and len(artifact['lightgbm']['trees']) == sequence_models.TREE_CONFIG['rounds'], 'fitted split or fixed recipe differs')
    require(max(r['game_date'] for r in train) < early['cutoff_at'][:10] < min(r['game_date'] for r in holdout)
            and len({r['match_id'] for r in raw}) == len(raw), 'training and holdout not chronologically disjoint')
    prepared = [dict(row, baseline_matrix=sequence_history.fixed_market_baseline(row['rates'], row['market']))
                for row in holdout]
    replay = runner.evaluate(early, prepared)
    compare(replay, records(history / 'season-holdout.jsonl.gz'), 'European holdout predictions and outcomes')
    compare(runner.summarize(replay), report['study'], 'development report')
    cohorts = {r['cohort'] for r in replay}
    require(cohorts == set(report['by_cohort']), 'omitted competition')
    for cohort in cohorts:
        compare(runner.summarize([r for r in replay if r['cohort'] == cohort]), report['by_cohort'][cohort], cohort)
    brazil = history / 'brazil'
    rebuilt, _ = load_module(brazil / 'prepare.py').build(read(brazil / 'historical_sources.json'))
    require(rebuilt == read(brazil / 'sequences.json'), 'Brazil historical inputs differ from retained source bytes')
    transfer = read(history / 'brazil-transfer-validation.json')
    transfer_artifact = read(history / 'brazil-transfer-artifact.json')
    require(transfer_artifact == dict(final, cutoff_at=transfer['cutoff']) and transfer['fit_n'] == len(raw),
            'Brazil transfer weights differ from the complete fixed European fit')
    retained = PREVIOUS / 'training/actual_current.jsonl.gz'
    locations = {retained.name: retained, 'sequences.json': brazil / 'sequences.json'}
    for name, checksum in transfer['source_sha256'].items():
        checked(locations.get(name, history / name), checksum)
    prior = [r for r in records(retained) if r['cohort'] == 'bra.1']
    inventory = {r['match_id']: r for r in transfer['inventory']}
    require(set(inventory) == {r['match_id'] for r in prior} and len(inventory) == len(transfer['inventory']),
            'Brazil transfer inventory differs')
    eligible = []
    for row in prior:
        mid = row['match_id']
        cutoff = aware(row['cutoff_at'])
        require(inventory[mid]['eligible'] == bool(row['market']) and cutoff == aware(rebuilt[mid]['cutoff_at']),
                mid + ': archived market coverage or cutoff differs')
        if row['market']:
            quote = three_arm_model._quote_values(row['market'], cutoff)
            pmf = three_arm_model._market_matrix(np.asarray(row['current_matrix']), quote)
            eligible.append(dict(row, sequence=rebuilt[mid]['sequence'], baseline_matrix=pmf,
                                 game_date=aware(row['kickoff_at']).date().isoformat()))
    results = runner.evaluate(transfer_artifact, eligible)
    compare(results, records(history / 'brazil-transfer-rows.jsonl.gz'), 'Brazil transfer predictions')
    compare(runner.summarize(results), transfer['summary'], 'Brazil transfer results')
    return {'europe_training': len(train), 'europe_replayed_holdout': len(replay),
            'brazil_histories': len(rebuilt), 'brazil_market_transfer_replays': len(results)}


def verify_graph(source):
    tactics = EXPERIMENT / 'tactics'
    manifest = read(tactics / 'reproduction.json')
    for name, checksum in manifest['repeated_training_outputs_byte_equal'].items():
        checked(tactics / name, checksum)
    checked(source / 'runtime/research_program/tactical_graph.py', manifest['extractor_and_model_source_sha256'])
    design = json.loads(checked(tactics / 'design.json', manifest['design_sha256']))
    report = read(tactics / 'report.json')
    split, matches = report['split'], report['match_metrics']
    require(manifest['upstream_revision'] == design['source_commit'] == report['source_revision']
            and not design['heldout_tuning'] and split['training_dates'][1] < split['holdout_dates'][0]
            and len(report['source_sha256']) == 52 and split['train_matches'] == 36
            and len({m['match_id'] for m in matches}) == len(matches) == split['test_matches'] == 15,
            'graph split or sources differ')
    coverage = report['coverage']['holdout']
    for key, reported in coverage.items():
        require(sum(m['counts'].get(key, 0) for m in matches) == reported, 'graph coverage differs: ' + key)
    n = coverage['evaluated']
    for arm, summary in report['arms'].items():
        hits = sum(m['arms'][arm]['top1_hits'] for m in matches)
        loss = sum(m['arms'][arm]['log_loss_sum'] for m in matches)
        compare(dict(hits=hits, evaluated=n, top1_rate=hits/n, log_loss=loss/n), summary, 'graph.' + arm)
    net = report['arms']['directed_graph']['hits'] - report['arms']['node_and_dyad']['hits']
    require(report['graph_minus_node_and_dyad']['net_hits'] == net, 'incorrect graph net gains')
    return {'graph_holdout_fixtures': len(matches), 'graph_eligible_passes': n}


def verify_quality(directory):
    from data_sources import research_supplement as supplement
    from research.analysis_freeze import aware
    cache_receipt = supplement.verify_only(DATA, directory)
    index = read(directory / 'latest.json')
    checked(directory / index['latest'], index['snapshot_sha256'])
    plan, fixtures, histories, membership, originals = supplement.original_inputs(DATA)
    by_id = {f['match_id']: f for f in fixtures}
    previous = {}
    previous_started_at = None
    paths = sorted((directory / 'runs').glob('*.json'))
    require(paths and paths[-1] == directory / index['latest'], 'quality index omits the latest observation')
    stages = ('original_first_issue', 'latest_observation')
    for path in paths:
        run = read(path)
        start, end = aware(run['started_at']), aware(run['observed_through'])
        require(start <= end and plan['record_sha256'] == run['registered_plan'] and histories == run['history']
                and set(by_id) == {r['match_id'] for r in run['fixtures']}
                and len(run['fixtures']) == run['registered'] == 6, 'quality population differs')
        quotes = supplement.markets(DATA, set(by_id), start) if run['status'] != 'batch_closed' else {}
        for row in run['fixtures']:
            mid = row['match_id']
            fixture = by_id[mid]
            kickoff = aware(fixture['kickoff_at'])
            old = previous.get(mid, {})
            require(row['history_ids'] == membership[mid] and row['original_lineup'] == originals[mid]
                    and row['original_market'] == plan['payload']['markets'][mid]
                    and aware(row['kickoff_at']) == kickoff and aware(row['first_cutoff_at']) == aware(fixture['cutoff_at']),
                    mid + ': supplemental enrollment or cutoff differs')
            carried = bool(old and start >= kickoff)
            lineups = row['current_lineup'] or {}
            window = supplement.lineup_window(kickoff, end, {} if carried else lineups, old.get('lineup_window_evidence'))
            require(row['lineup_window_evidence'] == window and row['quality']['lineup_window'] == window['state'],
                    mid + ': earliest T-90 confirmation or window coverage differs')
            if carried:
                expected = dict(old, quality=dict(old['quality'], lineup_window=window['state']), lineup_window_evidence=window)
                expected.setdefault('market_cutoff_at', previous_started_at)
                require(row == expected, mid + ': closed fixture observation changed')
                previous[mid] = row
                continue
            require(aware(row.get('market_cutoff_at', run['started_at'])) == start, mid + ': market selection cutoff changed')
            entrants = lineups.get('facts', {}).get('starters', {})
            confirmed = all(len(entrants.get(s, [])) == len(set(entrants.get(s, []))) == 11 for s in supplement.SIDES)
            if lineups.get('status') == 'ok':
                require(aware(lineups['observed_at']) <= end and aware(lineups['observed_at']) < kickoff,
                        mid + ': late first XI')
            ids = [membership[mid].get(s) for s in supplement.SIDES]
            shots = [supplement.prematch_observation(run['previous_games_espn'].get(i), kickoff)
                     .get('facts', {}).get('statistics', {}) for i in ids]
            xgs = [supplement.prematch_observation(run['previous_games_bsd'].get(i), kickoff) for i in ids]
            reported = all(x.get('status') == 'ok' and all(any(x['facts']['teams'][side][field] is not None
                           for field in ('expected_goals', 'xg_actual')) for side in supplement.SIDES) for x in xgs)
            first = {'confirmed_lineups': originals[mid]['facts']['both_elevens'], 'timed_h2h_and_total': bool(row['original_market'])}
            latest = {'confirmed_lineups': confirmed, 'fresh_h2h_and_total': mid in quotes,
                      'both_prior_games_shots': all(s.get(t, {}).get('totalShots') is not None for s in shots for t in supplement.SIDES),
                      'both_prior_games_xg': all(supplement.has_real_xg(x) for x in xgs),
                      'both_prior_games_reported_xg': reported,
                      'open_file_date_and_teams': bool((row['openfootball'] or {}).get('date_and_sides_verified'))}
            require(row['latest_valid_market'] == quotes.get(mid) and row['quality'][stages[0]] == first
                    and row['quality'][stages[1]] == latest, mid + ': source market or field coverage differs')
            previous[mid] = row
        previous_started_at = run['started_at']
        require(supplement.quality_counts(run['fixtures']) == run['coverage_counts'], 'quality totals differ from verified rows')
    require(all(index[k] == run[k] for k in ('coverage_counts', 'status', 'observed_through', 'registered')),
            'quality display differs from latest receipt')
    return {'verified_quality_fixtures': len(by_id), 'verified_quality_prior_games': cache_receipt['prior_game_count']}


def verify_forward(source):
    from prediction_engine import legacy
    from research.analysis_freeze import aware
    from research_program import sequence_forward as forward, sequence_models, three_arm_model
    from research_program import three_arm_forward as market_forward
    protocol = json.loads(checked(EXPERIMENT / 'registration/protocol.json', REGISTRATION))
    batch = EXPERIMENT / 'forward'
    plan, population, captures = forward.inspect_batch(batch)
    body = plan['payload']
    bindings = body['binding']
    require(bindings['registration_sha256'] == REGISTRATION and len(population) == 6
            and set(population) == set(captures) and body['automatic_promotion'] is False, 'registered first issues missing')
    for key, module in (('sequence_model_source_sha256', sequence_models), ('market_model_source_sha256', three_arm_model),
                        ('market_capture_source_sha256', market_forward), ('capture_source_sha256', forward)):
        checked(Path(module.__file__), bindings[key])
    checked(DATA / protocol['scoreboard_source'], protocol['scoreboard_sha256'])
    registry_key = bindings['registry_sha256']
    registry = json.loads(checked(DATA / 'future/bundle-v2/objects' / registry_key, registry_key))
    route = registry['models']['bra.1']
    require(registry['status'] == 'ACTIVE_RESEARCH' and route.get('current_engine', 'legacy_weighted_anchor')
            == 'legacy_weighted_anchor', 'different active Current route')
    archive = DATA / 'workspace-updates/20261115-remaining-nations-brazil/remaining-evidence.tar.gz'
    checked(archive, BASELINE_ARCHIVE)
    member = 'WCPP/models/weighted-20261012/bra.1/artifact.json'
    with tarfile.open(archive) as buf:
        original = buf.extractfile(member).read()
    require(hashlib.sha256(original).hexdigest() == route['artifact_sha256'] and route['artifact_path'].endswith('/' + member),
            'restored active weights differ from registered route')
    anchor = json.loads(original)['anchor']
    candidate = json.loads(checked(EXPERIMENT / 'history/artifact.json', bindings['artifact_sha256']))
    calibration = json.loads(checked(PREVIOUS / 'training/artifact.json', bindings['market_artifact_sha256']))
    cutoff = plan['fixture']['cutoff_at']
    require(max(aware(a['cutoff_at']) for a in (candidate, calibration)) <= aware(cutoff)
            and calibration['market_weight'] == 1.0, 'fit cutoff or preregistered market weight differs')
    channels = [p.parent for p in (DATA / 'market/runs').glob('*-bra1/market-channel.json')
                if hashlib.sha256(p.read_bytes()).hexdigest() == bindings['channel_sha256']]
    require(len(channels) == 1, 'expected exactly one retained source market channel')
    fixtures, markets, sources = market_forward.batch_inputs(channels[0], PREVIOUS / 'identity', 'bra.1', cutoff)
    forward.check_enrollment(protocol, fixtures, cutoff)
    require(fixtures == body['fixtures'] and markets == body['markets'] and sources == body['sources'] and all(markets.values()),
            'registered market or identity differs from original ESPN and bookmaker responses')
    require(list(protocol['arms']) == body['arms'], 'issued arms differ from preregistration')
    alias = market_forward.first_path(batch, plan['match_id'], forward.PLAN_TRACK)
    require(alias.read_bytes() == (batch / 'plan.json').read_bytes(), 'first plan and display alias differ')
    summary = read(batch / 'summary.json')
    indexed = {row['match_id']: row for row in summary['matches']}
    require(summary['population'] == len(summary['matches']) == len(population)
            and summary['plan_sha256'] == plan['record_sha256'] and set(indexed) == set(population)
            and summary['automatic_promotion'] is False, 'registered forecast summary differs')
    seen = {}
    for fixture in fixtures:
        mid = fixture['match_id']
        freeze = captures[mid]
        issued = aware(freeze['recorded_at'])
        quote, payload = markets[mid], freeze['payload']
        canonical = market_forward.first_path(batch, mid, forward.SCORE_TRACK)
        summary_row = indexed[mid]
        require(canonical.read_bytes() == (batch / summary_row['file']).read_bytes()
                and summary_row['record_sha256'] == freeze['record_sha256'] and summary_row['status'] == payload['status']
                and summary_row['recorded_at'] == freeze['recorded_at'], mid + ': summary or first record differs')
        panels = [forward.team_schedule(EXPERIMENT / 'forward/history', fixture[side], fixture=fixture, seen=seen)
                  for side in ('home', 'away')]
        require(panels == body['history'][mid] and payload['status'] == 'ISSUED_REAL_MARKET', mid + ': history or status changed')
        native = payload['native_current']
        checked(source / 'runtime/v5/weighted_model.py', native['engine_sha256'])
        require(native['artifact_sha256'] == route['artifact_sha256'], mid + ': active weights differ')
        class IssueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return issued.astimezone(tz)
        inputs = dict(fixture, total_quote=market_forward.total_quote(quote))
        with patch.object(legacy, 'datetime', IssueClock):
            restored = legacy.predict(anchor, inputs)
        require(restored['version'] == native['version'], mid + ': active version differs')
        compare(restored['matrix'], native['matrix'], mid + ': active distribution')
        baseline = three_arm_model.apply(calibration, restored['matrix'], quote, cohort=fixture['cohort'], cutoff_at=cutoff)['market']
        matrices = sequence_models.apply(candidate, baseline, [p['features'] for p in panels])
        for arm, matrix in matrices.items():
            arm = 'market_baseline' if arm == 'baseline' else arm
            frozen = payload['arms'][arm]
            require({k: frozen[k] for k in ('primary','wdl','total')} == summary_row['arms'][arm],
                    mid + ': published selections disagree with first issue')
            compare(matrix, frozen['matrix'], mid + '.' + arm + '.matrix')
            picks = three_arm_model.score_picks(matrix, line=quote['total']['line'])
            compare(picks, {k:v for k,v in frozen.items() if k not in ('matrix', 'matrix_sha256')}, mid + '.' + arm)
    published = read(batch / 'review.json')
    receipt = published.pop('freeze_receipt')
    frozen_review = forward.verify(read(batch / receipt['path']))
    require(frozen_review['payload'] == published and receipt['sha256'] == frozen_review['record_sha256']
            and frozen_review['stage'] == 'review' and frozen_review['track'] == 'sequence-research-review'
            and published['plan_sha256'] == plan['record_sha256'] and published['population'] == len(fixtures)
            and published['settled'] + published['pending'] == len(fixtures), 'review display differs from its immutable record')
    return {'registered': len(population), 'restored_active_current': len(fixtures), 'source_verified_markets': len(markets),
            'unique_prior_games': len(seen), 'forward_matrix_and_pick_replays': len(fixtures) * 3}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    args = p.parse_args()
    source = args.source.resolve()
    sys.path[:0] = [str(source), str(source / 'runtime')]
    out = {**verify_development(source), **verify_graph(source), **verify_forward(source), **verify_quality(EXPERIMENT / 'coverage')}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
