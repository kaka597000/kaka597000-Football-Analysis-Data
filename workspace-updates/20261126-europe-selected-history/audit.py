"""Replay the existing selected-three ranking on verified European matchdays."""

from collections import Counter, defaultdict
import gzip
from hashlib import file_digest
from importlib.util import module_from_spec, spec_from_file_location
import json
from operator import itemgetter
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from research.analysis_freeze import aware
from research_program.paired_kpi_inference import _decisions
from research_program.ranked_score_study import rank, sweep

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'20261126-europe-first-display'
sys.path.insert(0, str(ORIGINAL))
import prepare
from result_intake import assemble, endpoint, official_bindings, raw_result


SOURCE_ROOT = HERE.parent/'20261125-r13-domestic-form'
REPLAY = SOURCE_ROOT/'replay/forecasts.tar.gz'
REPLAY_SHA = '66dd22e8b4b5da665203776b404ecc6204fa833b61beb4b429c975a3be78655f'
IDENTITIES = SOURCE_ROOT/'inputs/continental.tar.gz'
IDENTITIES_SHA = 'bc104871d05f8bef3800eb42d4b8e9e1739eed60969ca2feb2b24ec7673d905b'
HOLDOUT = HERE.parent/'20261126-r30-europe-score-dispersion/replay/evaluation.jsonl.gz'
HOLDOUT_SHA = '94256bef415d6ed8bda59b52831e5196bf5f929a194716cf2e64037926cb4353'
SCOPES = {code: matchday-1 for code, _, _, _, matchday in prepare.COMPETITIONS.values()}
RANGE = {'fromDate': ['2026-09-16'], 'toDate': ['2026-11-05']}
IDENTITY = ('cohort', 'stage', 'date', 'home', 'away', 'actual', 'line', 'source_sha256')
METRICS = ('score_top1', 'score_top3')


def check_hash(path, digest):
    with path.open('rb') as stream:
        if file_digest(stream, 'sha256').hexdigest() != digest:
            raise ValueError('original archive checksum differs: ' + path.name)


def index(rows, key):
    result = {}
    for row in rows:
        identifier = key(row)
        if identifier in result:
            raise ValueError(f'duplicate source row for {identifier}')
        result[identifier] = row
    return result


def prior_rows():
    for path, digest in ((REPLAY, REPLAY_SHA), (IDENTITIES, IDENTITIES_SHA), (HOLDOUT, HOLDOUT_SHA)):
        check_hash(path, digest)
    by_id = itemgetter('id')
    with gzip.open(HOLDOUT, 'rt', encoding='utf-8') as stream:
        held = index(map(json.loads, stream), by_id)
    with tarfile.open(IDENTITIES) as archive:
        target_ids = index((row for row in map(json.loads, archive.extractfile('continental/identities.jsonl'))
                            if row['id'] in held), by_id)
    if target_ids.keys() != held.keys():
        raise ValueError('incomplete archived target kickoff identities')
    prior = {}
    with tarfile.open(REPLAY) as archive:
        for code in SCOPES:
            with gzip.open(archive.extractfile(code+'/forecasts.jsonl.gz'), 'rt', encoding='utf-8') as stream:
                rows = index((row for row in map(json.loads, stream) if row['id'] in held), by_id)
            if len(rows) != 18*SCOPES[code]:
                raise ValueError('archived R13 forecast population differs: ' + code)
            for mid, row in rows.items():
                control, fixture = held[mid], target_ids[mid]
                if (row['cohort'] != code or fixture['competition'] != code or fixture['date'] != row['date']
                        or fixture['panel_source_sha256'] != row['source_sha256'] or len(fixture['source_sha256']) != 64
                        or row['stage'] != 'league-phase' or any(row[k] != control[k] for k in IDENTITY)
                        or row['forecast']['candidate'] != control['forecast']['r13']
                        or row['forecast']['market'] != control['forecast']['market']):
                    raise ValueError('R13 forecast, result, market or original ordered identity differs: ' + mid)
            prior[code] = rows
    return prior, target_ids


def club_crosswalks():
    registered = prepare.register(False)
    today = {mid: row['fixture'] for scope in registered.values() for mid, row in scope['today'].items()}
    bindings = official_bindings(today)
    clubs = defaultdict(dict)
    for mid, fixture in today.items():
        matching = clubs[fixture['cohort']]
        for side in ('home', 'away'):
            provider_id, official_id = fixture[side], bindings[mid][side]
            if provider_id in matching or official_id in matching.values():
                raise ValueError('each registered club must map once on the original round')
            matching[provider_id] = official_id
    if set(clubs) != SCOPES.keys() or any(len(group) != 36 for group in clubs.values()):
        raise ValueError('incomplete verified club universe')
    return clubs


def original_rounds(code, capture, originals, target_ids, clubs):
    if (endpoint(capture['url'])[:2] != ('uefa', code) or capture['http_status'] != 200
            or any(parse_qs(urlsplit(capture['url']).query).get(key) != value for key, value in RANGE.items())):
        raise ValueError('original UEFA capture scope differs')
    source = raw_result(HERE/'evidence', capture['path'], capture['sha256'])
    official = index(json.loads(source), lambda game: (
        str(game['homeTeam']['id']), str(game['awayTeam']['id']), aware(game['kickOffTime']['dateTime'])))
    if len(official) != len(originals) or len({str(game['id']) for game in official.values()}) != len(official):
        raise ValueError('official record count differs from the complete ESPN archive')
    rounds, fixtures, bindings, score_conflicts = defaultdict(list), {}, {}, {}
    stage, = (item[1] for item in prepare.COMPETITIONS.values() if item[0] == code)
    for mid, ref in originals.items():
        source_id = target_ids[mid]
        kickoff = aware(source_id['kickoff_utc'])
        home, away = ('espn:'+str(source_id[key]) for key in ('home_id', 'away_id'))
        lookup = clubs[home], clubs[away], kickoff
        game = official.pop(lookup)
        matchday = int(game['matchday']['sequenceNumber'])
        fixtures[mid] = dict(match_id=mid, cohort=code, stage=stage, kickoff_at=kickoff.isoformat(), home=home, away=away)
        binding = dict(id=str(game['id']), home=clubs[home], away=clubs[away], matchday=matchday)
        bindings[mid] = binding
        score = game['score']
        if score.get('total', score['regular']) != score['regular']:
            score_conflicts[mid] = dict(uefa_id=binding['id'], regular=score['regular'], total=score['total'])
        picks = ref['forecast']['candidate']
        _decisions(picks, None, ref['line'])
        rounds[matchday].append(dict(match_id=mid, uefa_match_id=binding['id'], kickoff_at=kickoff.isoformat(),
                                    home=source_id['home_name'], away=source_id['away_name'], clubs=(home, away),
                                    primary=picks['primary'], top3=picks['top3'],
                                    first_probability=ref['quality']['candidate']['p_first'],
                                    market=ref['forecast']['market'],
                                    espn_identity_sha256=source_id['source_sha256'],
                                    panel_sha256=ref['source_sha256']))
    if official or set(rounds) != set(range(1, 1+SCOPES[code])):
        raise ValueError('official results do not cover exactly the registered historical rounds')
    return rounds, fixtures, bindings, score_conflicts


def certify(manifest, captures, fixtures, bindings):
    spec = spec_from_file_location('europe_first_display_review', ORIGINAL/'review.py')
    first_review = module_from_spec(spec)
    spec.loader.exec_module(first_review)
    at = max(aware(item['captured_at']) for item in captures)
    with TemporaryDirectory(prefix='europe-selected-history-') as directory:
        state = Path(directory)/'results'
        intake = assemble(manifest, state, fixtures, bindings, at)
        results, issues = first_review.results(state, fixtures, at, bindings)
    return results, issues, intake['captures_with_errors']


def attach_score(row, ref, confirmed, captures_by_sha):
    if confirmed is None:
        score = None
        source = None
    else:
        score = [confirmed['home'], confirmed['away']]
        capture = captures_by_sha[confirmed['source']['sha256']]
        source = dict(provider=confirmed['provider'], path=capture['path'], sha256=capture['sha256'])
        if score != ref['actual']:
            raise ValueError('verified score differs from the original held-out label: ' + ref['id'])
    _, market_hits, _ = _decisions(row['market'], score, ref['line'])
    return dict(row, actual='-'.join(map(str, score)) if score is not None else None, score_source=source,
                market_score_hits={m: market_hits[m] for m in METRICS})


def resolve_conflict(conflict, result, captures):
    if result is None:
        return dict(conflict, verified_source=None, verified_score=None)
    source = captures[result['source']['sha256']]
    if result['provider'] != 'espn' or source['uefa_match_id'] != conflict['uefa_id']:
        raise ValueError('score-field conflict needs the matching ESPN regulation evidence')
    response = json.loads(raw_result(HERE/'evidence', source['path'], source['sha256']))
    game, = response['header']['competitions']
    halves = {team['homeAway']: [int(period['displayValue']) for period in team['linescores']]
              for team in game['competitors']}
    score = [result['home'], result['away']]
    if (any(len(periods) != 2 for periods in halves.values())
            or any(team.get('shootoutScore') not in (None, '', 0, '0') for team in game['competitors'])
            or [sum(halves[side]) for side in ('home', 'away')] != score):
        raise ValueError('the independent first- and second-half scores must match the verified result')
    return dict(conflict, verified_source=source, verified_score=score, espn_halves=halves)


def grade(rows, clubs):
    if len(rows) != 18 or Counter(club for row in rows for club in row['clubs']) != Counter(clubs.keys()):
        raise ValueError('expected all 36 clubs once in a complete matchday')
    scores = {row['match_id']: row['actual'] for row in rows if row['actual'] is not None}
    selected = rank(rows)
    result = sweep(selected, scores)
    first_hits = sum(row['primary'] == row['actual'] for row in rows)
    market = {}
    for metric in METRICS:
        matched = [row for row in selected if row['market_score_hits'][metric] is not None]
        market[metric] = dict(eligible=len(matched), market_hits=sum(row['market_score_hits'][metric] for row in matched),
                              r13_hits=sum(row['actual'] == row['primary'] if metric == 'score_top1'
                                           else row['actual'] in row['top3'] for row in matched))
    times = sorted(aware(row['kickoff_at']) for row in rows)
    return dict(fixtures=len(rows), verified_regulation=len(scores), first_kickoff=times[0].astimezone(prepare.BEIJING).isoformat(),
                last_kickoff=times[-1].astimezone(prepare.BEIJING).isoformat(),
                full_round_first_hits=first_hits, full_round_three_hits=sum(row['actual'] in row['top3'] for row in rows),
                at_least_three_first_hits_available=first_hits >= 3 if len(scores) == len(rows) else None,
                batch=result, selected_market=market, selected=[row['match_id'] for row in selected],
                matches=sorted(rows, key=lambda row: (row['kickoff_at'], row['match_id'])))


def audit():
    originals, target_ids = prior_rows()
    clubs = club_crosswalks()
    manifest = HERE/'evidence/captures.json'
    captures = prepare.read(manifest)
    official = index((item for item in captures if endpoint(item['url'])[0] == 'uefa'), lambda item: endpoint(item['url'])[1])
    if official.keys() != SCOPES.keys():
        raise ValueError('both official historical schedules are required')
    by_digest = index(captures, itemgetter('sha256'))
    projections, fixtures, bindings, conflicts = {}, {}, {}, {}
    for code in SCOPES:
        projections[code], seen, bound, score_conflicts = original_rounds(code, official[code], originals[code], target_ids, clubs[code])
        fixtures.update(seen)
        bindings.update(bound)
        conflicts.update(score_conflicts)
    confirmed, issues, source_issues = certify(manifest, captures, fixtures, bindings)
    conflicts = {mid: resolve_conflict(conflict, confirmed.get(mid), by_digest) for mid, conflict in conflicts.items()}
    summaries = {}
    for code in SCOPES:
        rounds = {day: [attach_score(row, originals[code][row['match_id']], confirmed.get(row['match_id']), by_digest)
                        for row in group] for day, group in projections[code].items()}
        grades = {day: grade(rounds[day], clubs[code]) for day in sorted(rounds)}
        totals = Counter()
        market = {metric: Counter() for metric in METRICS}
        for row in grades.values():
            totals.update(row['batch'])
            for metric in METRICS:
                market[metric].update(row['selected_market'][metric])
        summaries[code] = dict(official_round_source=official[code], selected_summary=dict(totals), selected_market=market,
                               potential_sweeps_if_selected_after_results=sum(r['at_least_three_first_hits_available'] is True
                                                                              for r in grades.values()),
                               fully_verified_rounds=sum(r['verified_regulation'] == r['fixtures'] for r in grades.values()),
                               matchdays=grades)
    return dict(mode='HISTORICAL_REPLAY', forecast_sha256=REPLAY_SHA, target_identity_sha256=IDENTITIES_SHA,
                fixed_holdout_sha256=HOLDOUT_SHA, score_field_conflicts=conflicts, result_issues=issues,
                source_issues=source_issues, competitions=summaries)


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2, allow_nan=False))
