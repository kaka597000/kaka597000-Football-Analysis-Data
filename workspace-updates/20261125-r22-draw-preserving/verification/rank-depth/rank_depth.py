#!/usr/bin/env python3
"""Rebuild the locked R7 grids and audit one fixed 2-2 replacement rule offline."""

import argparse
from collections import Counter
import csv
from datetime import date, timezone
import gzip
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
DEFINITION = HERE / 'definition.json'
FORWARD_ADDENDUM = HERE / 'forward-availability-addendum.json'
ARMS = {'r7': 'r7', 'market': 'market', 'r21': 'r21', 'r22': 'candidate'}
TARGET = '2-2'
HISTORICAL_WINDOWS = ('evaluation', 'recent')
BUCKETS = ('rank_4', 'rank_5', 'rank_6', 'ranks_7_10', 'ranks_11_plus', 'outside_grid')
SCORE = re.compile(r'(0|[1-9][0-9]*)-(0|[1-9][0-9]*)')
PROBABILITY_TOLERANCE = 1e-12
NUMERICAL_ENV = {
    'OPENBLAS_CORETYPE': 'Haswell', 'NPY_DISABLE_CPU_FEATURES': 'AVX512F',
    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
    'NUMEXPR_NUM_THREADS': '1',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


class LockedData:
    def __init__(self, root, reference):
        self.root = root
        self.packages = reference['packages']
        self.pins = reference['files_sha256']
        self.used = {}
        self.manifests = {}

    def file(self, package, name):
        relative = f'{self.packages[package]}/{name}'
        expected = self.pins.get(relative)
        if expected is None:
            if package not in self.manifests:
                self.manifests[package] = read_json(self.file(package, 'manifest.json'))['files']
            expected = self.manifests[package][name]
        path = self.root / relative
        if relative not in self.used:
            require(digest(path.read_bytes()) == expected, f'input SHA-256 differs: {relative}')
            self.used[relative] = expected
        return path

    def member(self, package, archive, bundle, name, expected=None):
        member = bundle.getmember(name)
        require(member.isfile(), f'expected a regular archive member: {archive}::{name}')
        with bundle.extractfile(member) as stream:
            raw = stream.read()
        relative = f'{self.packages[package]}/{archive}::{name}'
        got = digest(raw)
        require(expected is None or got == expected, f'input member SHA-256 differs: {relative}')
        self.used[relative] = got
        return raw


def configure_runtime(source, reference, work):
    for relative, expected in reference['files_sha256'].items():
        require(digest((source / relative).read_bytes()) == expected, f'project code SHA-256 differs: {relative}')
    os.environ.update(NUMERICAL_ENV)
    os.environ['MPLCONFIGDIR'] = str(work / 'matplotlib')
    os.environ['XDG_CACHE_HOME'] = str(work / 'cache')
    os.environ['TMPDIR'] = str(work)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / 'runtime'))


def index_rows(rows, key):
    result = {}
    for row in rows:
        item = key(row)
        require(item not in result, f'duplicate fixture: {item}')
        result[item] = row
    return result


def top_three(pick, label, *, allow_missing=False):
    scores = pick.get('top3')
    if allow_missing and scores is None and pick.get('primary') is None:
        return None
    require(isinstance(scores, list) and len(scores) == len(set(scores)) == 3
            and all(SCORE.fullmatch(s) for s in scores) and pick['primary'] == scores[0],
            f'invalid ordered top three: {label}')
    return scores


def inputs_at_rank(matrix, four_arms, label):
    import numpy as np
    from research_program.three_arm_model import top_three_scores

    require(matrix.ndim == 2 and min(matrix.shape) >= 3
            and np.isfinite(matrix).all() and (matrix >= 0).all()
            and abs(matrix.sum() - 1.0) <= PROBABILITY_TOLERANCE, f'invalid probability grid: {label}')
    flat = matrix.ravel(order='C')
    order = np.argsort(-flat, kind='stable')
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, matrix.size + 1)
    cols = matrix.shape[1]
    scores = ['%d-%d' % divmod(int(i), cols) for i in order[:4]]
    require(scores[:3] == top_three_scores(matrix) == four_arms['r7'],
            f'R7 ordered top three differ: {label} {scores[:3]} != {four_arms["r7"]}')
    p3, p4 = (float(flat[i]) for i in order[2:4])
    available = [picks for picks in four_arms.values() if picks is not None]
    absent = all(TARGET not in picks for picks in available)
    if absent and len(available) < len(four_arms):
        absent = None
    row = {f'{arm}_top3': '|'.join(picks) if picks is not None else None for arm, picks in four_arms.items()}
    row.update(r7_rank_3=scores[2], r7_rank_4=scores[3], r7_p_rank_3=p3, r7_p_rank_4=p4,
               r7_rank_2_2=int(ranks[2 * cols + 2]), r7_p_2_2=float(matrix[2, 2]),
               r7_p_rank_3_minus_p_2_2=p3 - float(matrix[2, 2]), r7_rank_3_4_exact_tie=p3 == p4,
               all_four_absent_2_2=absent, trigger=absent if scores[3] == TARGET else False)
    return row, ranks, [float(flat[i]) for i in order[:3]]


def rank_bucket(rank):
    if rank is None:
        return 'outside_grid'
    if rank <= 3:
        return 'ranks_1_3'
    if rank <= 6:
        return f'rank_{rank}'
    return 'ranks_7_10' if rank <= 10 else 'ranks_11_plus'


def probability_error(checks, label):
    error = max(abs(want - got) for want, got in checks)
    require(error <= PROBABILITY_TOLERANCE, f'R7 probability check differs: {label} ({error:.17g})')
    return error


def check_history_identity(game, archived, window, line):
    actual = [game['home_goals'], game['away_goals']]
    identity = {key: game[key] for key in ('id', 'stage', 'date', 'home', 'away', 'source_sha256')}
    identity.update(actual=actual, cohort=game['competition'], window=window, line=line)
    require(all(archived[k] == value for k, value in identity.items()),
            f'historical fixture identity differs: {game["competition"]}/{game["id"]}')


def grid_row(row, matrix):
    return {**{key: row[key] for key in ('competition', 'match_id', 'window')}, 'matrix': matrix.tolist()}


def read_history(data, work, spec, locked):
    from research_program import all_scope_model, all_scope_study, continuation_scores, r8_score_study
    from research_program.r9_team_shape import actual_rank

    def decoded_forecasts(raw):
        rows = (json.loads(line) for line in gzip.decompress(raw).splitlines())
        return index_rows((row for row in rows if row['window'] in HISTORICAL_WINDOWS), lambda row: row['id'])

    reference = data.file('r22', 'verification/independent/ordered-ranks.csv')
    with reference.open(encoding='utf-8', newline='') as stream:
        independent = index_rows((row for row in csv.DictReader(stream) if row['window'] in HISTORICAL_WINDOWS),
                                 lambda row: (row['competition'], row['match_id']))
    rows, grids = [], []
    for competition in spec['populations']['competitions']:
        pins = locked['competitions'][competition]
        archive = f'models/{competition}.tar.gz'
        with tarfile.open(data.file('r5', archive)) as bundle:
            panel = data.member('r5', archive, bundle, 'panel.jsonl', pins['panel_sha256'])
        panel_file = work / f'{competition}-panel.jsonl'
        panel_file.write_bytes(panel)
        games = all_scope_study.check_panel(panel_file, competition)
        with tarfile.open(data.file('r7', archive)) as bundle:
            fit = json.loads(data.member('r7', archive, bundle, 'main/fit.json', pins['r7_fit_sha256']))
            signed_r7 = decoded_forecasts(data.member('r7', archive, bundle, 'main/forecasts.jsonl.gz',
                                                        pins['r7_forecasts_sha256']))
        rel = f'replay/reference/main/{competition}/forecasts.jsonl.gz'
        r21_raw = data.file('r21', rel).read_bytes()
        require(digest(r21_raw) == pins['r21_forecasts_sha256'], f'R21/R22 forecast binding differs: {competition}')
        signed_r21 = decoded_forecasts(r21_raw)
        signed_r22 = decoded_forecasts(data.file('r22', rel).read_bytes())
        validation_start, evaluation_start, recent_start = fit['bounds']
        validation = sum(game['date'] < validation_start for game in games)
        start = sum(game['date'] < evaluation_start for game in games)
        require(fit['version'] == continuation_scores.VERSION and fit['competition'] == competition
                and fit['source_panel_sha256'] == pins['panel_sha256'] and len(games) == pins['base_fixtures']
                and fit['training_games'] == validation and fit['training_through'] == games[validation - 1]['date']
                and fit['training_through'] < validation_start < evaluation_start < recent_start
                and start - validation == fit['selection']['validation_games'] == pins['validation_fixtures'],
                f'locked R7 training, validation or panel differs: {competition}')
        held = games[start:]
        require({game['id'] for game in held} == signed_r7.keys() == signed_r21.keys() == signed_r22.keys(),
                f'historical fixture population differs: {competition}')
        priors, features, _ = continuation_scores.inputs(games, competition)
        matrices = r8_score_study.matrices(priors[start:], features[start:], fit)
        counts = Counter()
        for game, matrix in zip(held, matrices, strict=True):
            mid = game['id']
            label = f'{competition}/{mid}'
            line = all_scope_model.actual_line(game)
            window = 'evaluation' if game['date'] < recent_start else 'recent'
            counts[window] += 1
            old, parent, record = signed_r7[mid], signed_r21[mid], signed_r22[mid]
            fp = record['forecast']
            require(game['score_basis'] == 'regulation_90' and old['forecast']['candidate'] == fp['r7']
                    and parent['forecast']['r7'] == fp['r7'] and parent['forecast']['market'] == fp['market']
                    and parent['forecast']['candidate'] == fp['r21'], f'archived score basis or arms differ: {label}')
            picks = {arm: top_three(fp[key], f'{label}/{arm}') for arm, key in ARMS.items()}
            source = independent.pop((competition, mid))
            require(all(source[arm].split('|') == value for arm, value in picks.items()),
                    f'independent ordered rows differ: {label}')
            row, ranks, probabilities = inputs_at_rank(matrix, picks, label)

            # The trigger above sees only the four forecasts and the matrix.
            for archived in (old, parent, record):
                check_history_identity(game, archived, window, line)
            require(record['prices'] == parent['prices'] == {key: game.get(key) for key in ('h2h', 'total')}
                    and record['market_time_basis'] == parent['market_time_basis'] == game.get('market_time_basis')
                    and record['kickoff'] == parent['kickoff'], f'archived prices or kickoff differ: {label}')
            actual = tuple(record['actual'])
            score = '%d-%d' % actual
            require((source['date'], source['window'], source['actual']) == (game['date'], window, score),
                    f'independent fixture or score differs: {label}')
            inside = all(0 <= goal < size for goal, size in zip(actual, matrix.shape, strict=True))
            rank = int(ranks[actual[0] * matrix.shape[1] + actual[1]]) if inside else None
            if inside:
                require(rank == actual_rank(matrix, actual), f'R7 stable tied rank differs: {label}')
            archive_q, r22_q = old['quality']['candidate'], record['quality']['r7']
            comparisons = [(q['p_first'], probabilities[0]) for q in (archive_q, r22_q)]
            comparisons += [(q['p_three'], sum(probabilities)) for q in (archive_q, r22_q)]
            comparisons += list(zip(r22_q['p_ordered'], probabilities, strict=True))
            if inside:
                comparisons += [(q['p_observed'], float(matrix[actual])) for q in (archive_q, r22_q)]
            error = probability_error(comparisons, label)

            old_top3 = picks['r7']
            modified = old_top3[:2] + [TARGET] if row['trigger'] else old_top3
            old_hit, new_hit = score in old_top3, score in modified
            missed = all(score not in values for values in picks.values())
            gained, lost = row['trigger'] and score == TARGET, row['trigger'] and score == old_top3[2]
            bucket = rank_bucket(rank)
            require(gained == (new_hit and not old_hit) and lost == (old_hit and not new_hit)
                    and (not gained or missed) and (not missed or bucket in BUCKETS),
                    f'paired outcome or rank inconsistent: {label}')
            row = dict(competition=competition, match_id=mid, window=window, date=game['date'],
                       home=game['home'], away=game['away'], source_sha256=game['source_sha256'],
                       market_time_basis=record['market_time_basis'], **row, actual=score,
                       r7_p_actual=float(matrix[actual]) if inside else None, r7_actual_rank=rank,
                       r7_actual_rank_bucket=bucket, all_four_missed=missed,
                       r7_top3_hit=old_hit, edited_r7_top3_hit=new_hit, gained=gained, lost_original_third=lost,
                       edited_r7_top3='|'.join(modified), r7_probability_max_abs_error=error)
            rows.append(row)
            grids.append(grid_row(row, matrix))
        for window in HISTORICAL_WINDOWS:
            require(counts[window] == pins[f'{window}_fixtures'], f'{competition}/{window} denominator differs')
    require(not independent, 'unmatched fixtures in independent ordered table')
    return rows, grids


def receipt_name(receipt):
    name = receipt['file']
    require(PurePosixPath(name).name == name and name == receipt['id'] + '.json'
            and re.fullmatch(r'[0-9a-f]+-v000001\.json', name), f'invalid first-issue receipt file: {name}')
    return name


def archived_issue_folder(data, work, package, archive, prefix, match_ids):
    folder = work / package
    folder.mkdir()
    with tarfile.open(data.file(package, archive)) as bundle:
        raw = data.member(package, archive, bundle, prefix + 'receipts.json')
        (folder / 'receipts.json').write_bytes(raw)
        index = json.loads(raw)
        for receipt in [index['registration']] + [index['matches'][mid] for mid in match_ids]:
            name = receipt_name(receipt)
            (folder / name).write_bytes(data.member(package, archive, bundle, prefix + name))
    return folder


def checked_first(data, package, match_ids):
    from research_program.territory_forward import FirstIssues

    path = data.file(package, 'forward/receipts.json')
    index = read_json(path)
    ids = index['matches'] if match_ids is None else match_ids
    for receipt in [index['registration']] + [index['matches'][mid] for mid in ids]:
        data.file(package, 'forward/' + receipt_name(receipt))
    return FirstIssues.load(path.parent)


def quote_clocks(evidence, cutoff, label):
    from research.analysis_freeze import aware

    quotes = {'market': evidence} if 'source_sha256' in evidence else evidence
    clocks = {f'{market}_{field}': quote.get(field) for market, quote in quotes.items()
              for field in ('observed_at', 'quoted_at')}
    require(all(aware(stamp) <= cutoff for stamp in clocks.values() if stamp),
            f'archived quote after its own cutoff: {label}')
    return clocks


def read_forward(data, work, spec, locked, lock):
    from research.analysis_freeze import aware
    from research_program import all_scope_model, continuation_forward
    from research_program.territory_forward import FirstIssues

    current = checked_first(data, 'r22', None)
    registration = current.registration
    target = spec['populations']['forward']
    require(len(current.matches) == target['eligible']
            and registration['record_sha256'] == target['source_registration_sha256']
            and registration['recorded_at'] == target['source_registration_recorded_at'],
            'R22 original registration or denominator differs')
    match_ids = sorted(current.matches)
    r5 = FirstIssues.load(archived_issue_folder(data, work, 'r5', 'forward-first-issues.tar.gz', 'issued/', match_ids))
    r7 = FirstIssues.load(archived_issue_folder(data, work, 'r7', 'first-issues.tar.gz', '', match_ids))
    r21 = checked_first(data, 'r21', match_ids)
    identity = registration['payload']['identity']
    for name, batch in (('r5', r5), ('r7', r7), ('r21', r21)):
        require(identity[f'{name}_registration'] == batch.registration['record_sha256'],
                f'R22 earlier registration differs: {name}')
    require(r21.registration['record_sha256'] == lock['r21_parent']['forward_registration_sha256'],
            'R21 original registration differs from R22 source lock')

    recipes = {}
    for competition in spec['populations']['competitions']:
        archive = f'models/{competition}.tar.gz'
        recipe_sha = locked['competitions'][competition]['r7_recipe_sha256']
        with tarfile.open(data.file('r7', archive)) as bundle:
            recipe = json.loads(data.member('r7', archive, bundle, 'main/forward.json', recipe_sha))
        require(recipe['version'] == continuation_forward.model.VERSION and recipe['competition'] == competition
                and recipe['fit_sha256'] == locked['competitions'][competition]['r7_fit_sha256']
                and recipe_sha == r7.registration['payload']['identity']['recipe_sha256'][competition],
                f'R7 first-issue recipe differs: {competition}')
        recipes[competition] = recipe, recipe_sha

    rows, grids = [], []
    for mid in match_ids:
        recorded = current.matches[mid]['recorded_at']
        record = current.match(registration['payload']['fixtures'][mid], aware(recorded))
        fx, payload = record['fixture'], record['payload']
        competition = fx['cohort']
        label = f'{competition}/{mid}'
        cutoff = aware(fx['cutoff_at'])
        r5_record, r7_record, r21_record = (batch.match(fx, cutoff) for batch in (r5, r7, r21))
        for batch, first in ((current, record), (r5, r5_record), (r7, r7_record), (r21, r21_record)):
            require(first['recorded_at'] == batch.matches[mid]['recorded_at'], f'receipt clock differs: {label}')
        raw, old, previous = (first['payload'] for first in (r5_record, r7_record, r21_record))
        odds_cutoff = r5_record['fixture']['cutoff_at']
        recipe, recipe_sha = recipes[competition]
        require(aware(r5_record['recorded_at']) <= aware(r7_record['fixture']['cutoff_at'])
                and aware(r7_record['recorded_at']) <= aware(r21_record['fixture']['cutoff_at'])
                and payload['history_cutoff'] == cutoff.date().isoformat()
                and date.fromisoformat(recipe['through']) < aware(r7_record['fixture']['cutoff_at']).date()
                and date.fromisoformat(payload['training_through']) < cutoff.date(), f'first-issue timing differs: {label}')
        require(r5_record['record_sha256'] == old['input_sha256'] == previous['odds_source_first_issue']
                == payload['odds_source_first_issue'] and r7_record['record_sha256'] == previous['r7_first_issue']
                == payload['r7_first_issue'] and r21_record['record_sha256'] == payload['r21_first_issue']
                and recipe_sha == old['model_sha256'] == previous['baseline_sha256'] == payload['baseline_sha256']
                and recipe['through'] == old['training_through'] == payload['r7_training_through']
                and odds_cutoff == previous['odds_cutoff_at'] == payload['odds_cutoff_at'],
                f'first-issue input/recipe binding differs: {label}')
        require(previous['prices'] == raw['prices'] == payload['prices']
                and previous['market_evidence'] == raw['market_evidence'] == payload['market_evidence'],
                f'frozen market source or prices differ: {label}')
        clocks = quote_clocks(raw['market_evidence'], aware(odds_cutoff), label)

        fp = payload['forecasts']
        require(fp['r7'] == old['forecasts']['candidate'] == previous['forecasts']['r7']
                and fp['market'] == raw['forecasts']['market'] == old['forecasts']['market']
                == previous['forecasts']['market'] and fp['r21'] == previous['forecasts']['candidate'],
                f'frozen arm differs from its first issue: {label}')
        game = continuation_forward.frozen_game(fx, raw)
        game['date'] = aware(fx['kickoff_at']).astimezone(timezone.utc).date().isoformat()
        line = all_scope_model.actual_line(game)
        require(line == raw['line'] == old['line'] == previous['line'] == payload['line'],
                f'frozen actual line differs: {label}')
        matrix = continuation_forward.matrix(game, recipe)
        picks = {arm: top_three(fp[key], f'{label}/{arm}', allow_missing=arm != 'r7') for arm, key in ARMS.items()}
        features, _, probabilities = inputs_at_rank(matrix, picks, label)
        error = probability_error([(old['quality']['p_first'], probabilities[0]),
                                   (old['quality']['p_three'], sum(probabilities))], label)
        row = dict(competition=competition, match_id=mid, window='frozen_45',
                   home_id=fx['home'], away_id=fx['away'], home=payload['home_name'], away=payload['away_name'],
                   kickoff_at=fx['kickoff_at'], r22_cutoff_at=fx['cutoff_at'], r22_recorded_at=recorded,
                   r5_cutoff_at=odds_cutoff, r5_recorded_at=r5_record['recorded_at'],
                   r7_recorded_at=r7_record['recorded_at'], r21_recorded_at=r21_record['recorded_at'],
                   r22_first_sha256=record['record_sha256'], r21_first_sha256=r21_record['record_sha256'],
                   r7_first_sha256=r7_record['record_sha256'], r5_first_sha256=r5_record['record_sha256'],
                   r7_recipe_sha256=recipe_sha, market_mode=raw['market_mode'], total_line=line,
                   timestamped_quote_fields=sum(bool(stamp) for stamp in clocks.values()),
                   market_clocks=json.dumps(clocks, sort_keys=True, separators=(',', ':')),
                   **features, r7_probability_max_abs_error=error)
        rows.append(row)
        grids.append(grid_row(row, matrix))
    return rows, grids


def summarize_history(rows):
    missed = [row for row in rows if row['all_four_missed']]
    counts = Counter(row['r7_actual_rank_bucket'] for row in missed)
    gained = sum(row['gained'] for row in rows)
    lost = sum(row['lost_original_third'] for row in rows)
    old_hits = sum(row['r7_top3_hit'] for row in rows)
    new_hits = sum(row['edited_r7_top3_hit'] for row in rows)
    require(new_hits - old_hits == gained - lost and sum(counts[bin] for bin in BUCKETS) == len(missed),
            'rank counts or net changes do not reconcile')
    return dict(eligible=len(rows), ordered_r7_top3_verified=len(rows), all_four_missed=len(missed),
                **{bin: counts[bin] for bin in BUCKETS},
                beyond_rank_10_or_outside_grid=counts['ranks_11_plus'] + counts['outside_grid'],
                actual_2_2_among_all_four_missed=sum(row['actual'] == TARGET for row in missed),
                all_four_absent_2_2=sum(row['all_four_absent_2_2'] for row in rows),
                r7_rank_4_is_2_2=sum(row['r7_rank_4'] == TARGET for row in rows),
                triggered=sum(row['trigger'] for row in rows), gained=gained, lost_original_third=lost,
                net=gained - lost, r7_top3_hits=old_hits, edited_r7_top3_hits=new_hits,
                r7_rank_3_4_exact_ties=sum(row['r7_rank_3_4_exact_tie'] for row in rows),
                max_abs_probability_error=max(row['r7_probability_max_abs_error'] for row in rows))


def summarize_forward(rows):
    availability = {f'{arm}_ordered_top3_available': sum(row[f'{arm}_top3'] is not None for row in rows)
                    for arm in ARMS}
    complete = sum(all(row[f'{arm}_top3'] is not None for arm in ARMS) for row in rows)
    known = sum(row['trigger'] is not None for row in rows)
    return dict(eligible=len(rows), ordered_r7_top3_verified=len(rows),
                **availability, four_ordered_top3_available=complete,
                r7_rank_3_4_and_2_2_probability_available=sum(row['r7_rank_2_2'] > 0 for row in rows),
                original_timestamps_verified=len(rows),
                line_available=sum(row['total_line'] is not None for row in rows),
                timestamped_market_quote_available=sum(row['timestamped_quote_fields'] > 0 for row in rows),
                all_four_absent_2_2=sum(row['all_four_absent_2_2'] is True for row in rows),
                r7_rank_4_is_2_2=sum(row['r7_rank_4'] == TARGET for row in rows),
                trigger_determinable=known, trigger_unknown=len(rows) - known,
                triggered=sum(row['trigger'] is True for row in rows),
                r7_rank_3_4_exact_ties=sum(row['r7_rank_3_4_exact_tie'] for row in rows),
                max_abs_probability_error=max(row['r7_probability_max_abs_error'] for row in rows))


def summarize(mode, rows, spec):
    summarize_group = summarize_history if mode == 'history' else summarize_forward
    windows = HISTORICAL_WINDOWS if mode == 'history' else ('frozen_45',)
    groups = []
    for window in windows:
        batch = [row for row in rows if row['window'] == window]
        total = summarize_group(batch)
        target = spec['populations']['forward' if mode == 'forward' else window]
        require(total['eligible'] == target['eligible'], f'{window} predeclared denominator differs')
        if mode == 'history':
            require(total['all_four_missed'] == target['expected_four_arm_misses'],
                    f'{window} four-arm misses disagree with the prior coverage diagnostic')
        groups.append(dict(window=window, competition='total', **total))
        for competition in spec['populations']['competitions']:
            stats = summarize_group([row for row in batch if row['competition'] == competition])
            groups.append(dict(window=window, competition=competition, **stats))
    return groups


def write_csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n',
                    encoding='utf-8')


def write_outputs(mode, folder, rows, grids, groups, data, source, spec):
    folder.mkdir()
    write_csv(folder / 'fixtures.csv', rows)
    write_csv(folder / 'by-league.csv', groups)
    write_json(folder / 'summary.json', {'mode': mode, 'groups': groups,
                                         'grid_shapes': sorted({(len(g['matrix']), len(g['matrix'][0])) for g in grids})})
    with (folder / 'r7-grids.jsonl.gz').open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as archive:
            for grid in grids:
                archive.write((json.dumps(grid, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8'))

    project_code = {}
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(source / 'runtime'):
                project_code[path.relative_to(source).as_posix()] = digest(path.read_bytes())
    refs = spec['references']
    provenance = {
        'mode': mode,
        'definition': {'file': 'definition.json', 'sha256': digest(DEFINITION.read_bytes()), 'saved_at': spec['saved_at']},
        'script': {'file': Path(__file__).name, 'sha256': digest(Path(__file__).read_bytes())},
        'source': {key: value for key, value in refs['source'].items() if key != 'checkout'}
                  | {'imported_runtime_files_sha256': project_code},
        'data': {key: refs['data'][key] for key in ('repository', 'commit', 'r22_locked_parent_commit', 'packages')}
                | {'consumed_files_and_archive_members_sha256': data.used},
        'runtime': {'python': sys.version.split()[0], 'numerical_env': NUMERICAL_ENV,
                    'packages': {name: version(name) for name in spec['runtime']['packages']}},
        'results_sha256': {path.name: digest(path.read_bytes()) for path in sorted(folder.iterdir())},
    }
    if mode == 'forward':
        provenance['forward_availability_addendum'] = dict(file=FORWARD_ADDENDUM.name,
                                                           sha256=digest(FORWARD_ADDENDUM.read_bytes()))
    write_json(folder / 'provenance.json', provenance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('history', 'forward'))
    parser.add_argument('--source', type=Path, required=True, help='pinned Football-Analysis checkout')
    parser.add_argument('--data-root', type=Path, required=True, help='pinned Football-Analysis-Data checkout')
    parser.add_argument('--out-dir', type=Path, help='new directory, defaults to MODE beside this script')
    args = parser.parse_args()
    source, data_root = args.source.resolve(), args.data_root.resolve()
    output = (args.out_dir or HERE / args.mode).resolve()
    require(not output.exists(), f'output directory already exists: {output}')
    require(not any(output.is_relative_to(root) for root in (source, data_root)), 'output belongs outside input checkouts')
    spec = read_json(DEFINITION)
    if args.mode == 'forward':
        require(read_json(FORWARD_ADDENDUM)['definition_sha256'] == digest(DEFINITION.read_bytes()),
                'forward availability addendum belongs to a different definition')
    data = LockedData(data_root, spec['references']['data'])
    lock = read_json(data.file('r22', 'source-lock.json'))
    locked = read_json(data.file('r22', 'replay/reference/inputs.json'))
    require(lock['protocol_sha256'] == locked['protocol_sha256']
            == spec['references']['source']['files_sha256'][lock['protocol_path']]
            and lock['final_source_commit'] == spec['references']['source']['commit'], 'R22 source lock differs')
    with TemporaryDirectory(dir=output.parent, prefix='.r22-rank-depth-') as temporary:
        work = Path(temporary)
        configure_runtime(source, spec['references']['source'], work)
        if args.mode == 'history':
            rows, grids = read_history(data, work, spec, locked)
        else:
            rows, grids = read_forward(data, work, spec, locked, lock)
        groups = summarize(args.mode, rows, spec)
        staged = work / 'result'
        write_outputs(args.mode, staged, rows, grids, groups, data, source, spec)
        staged.rename(output)
    for stats in groups:
        if stats['competition'] == 'total':
            print(json.dumps(stats, sort_keys=True))


if __name__ == '__main__':
    main()
