"""Replay R39 match selection with the same original score on every fixture."""

from collections import Counter, defaultdict
import gzip
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from operator import itemgetter
from pathlib import Path
import tarfile
from unicodedata import normalize
from urllib.parse import parse_qs, urlsplit

from research.analysis_freeze import aware
from research_program.display_window_review import summary_kickoff
from research_program.paired_kpi_inference import _decisions
from research_program.ranked_score_study import rank, sweep

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'20261126-europe-selected-history'
loader = spec_from_file_location('europe_selected_history', PRIOR/'audit.py')
prior = module_from_spec(loader)
loader.loader.exec_module(prior)
from result_intake import raw_result, uefa_score


CODE = 'uefa.europa.conf'
R35 = HERE.parent/'20261126-r35-europe-close-score-agreement/replay'
CONTROL_HASHES = {
    'train': 'b7925eb229bada6c06c99e7ce588c26219839d2914b1324178b0f11d6fa7eb7b',
    'validation': 'd54da7ee4b61f575218426f2d33e90c0ebbf4fef7396e32437548533ae662cab',
    'evaluation': '46fda69e115d628277f54cdbdaca9c0bdd8070ffa9d354769929767bbdf010ec',
}
HOLDOUT_SHA = '46e6553ebd9888575cf3c23a9f8904b934efac746ed0c4550a6bdff6b973d745'
RANGES = (('2025-10-01', '2025-11-06'), ('2025-11-07', '2025-12-19'))
SUMMARY_FIELDS = ('primary_sweeps', 'primary_hits', 'displayed_three_hits')


def historical_inputs():
    for archive, digest in ((prior.REPLAY, prior.REPLAY_SHA), (prior.IDENTITIES, prior.IDENTITIES_SHA),
                            (PRIOR/'history.json', HOLDOUT_SHA)):
        prior.check_hash(archive, digest)
    controls = {}
    for window, digest in CONTROL_HASHES.items():
        path = R35/f'{window}.jsonl.gz'
        prior.check_hash(path, digest)
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            records = prior.index((row for row in map(json.loads, handle) if row['cohort'] == CODE), itemgetter('id'))
        if len(records) != 54 or controls.keys() & records.keys():
            raise ValueError('R35 controls must cover the original disjoint windows')
        controls.update(records)
    with tarfile.open(prior.REPLAY) as bundle:
        with gzip.open(bundle.extractfile(CODE+'/forecasts.jsonl.gz'), 'rt', encoding='utf-8') as handle:
            originals = prior.index((row for row in map(json.loads, handle) if row['stage'] == 'league-phase'), itemgetter('id'))
    with tarfile.open(prior.IDENTITIES) as bundle:
        identities = prior.index((row for row in map(json.loads, bundle.extractfile('continental/identities.jsonl'))
                                  if row['id'] in originals), itemgetter('id'))
    if originals.keys() != controls.keys() or identities.keys() != controls.keys():
        raise ValueError('R13 and R35 must bind the same complete historical population')
    for mid, row in originals.items():
        fixture, control = identities[mid], controls[mid]
        original = dict(r13=row['forecast']['candidate'], r7=row['forecast']['r7'], market=row['forecast']['market'])
        if (fixture['competition'] != CODE or fixture['date'] != row['date']
                or fixture['panel_source_sha256'] != row['source_sha256']
                or any(control[key] != row[key] for key in prior.IDENTITY)
                or any(control['forecast'][key] != value for key, value in original.items())
                or abs(control['original_p_first'] - row['quality']['candidate']['p_first']) > 2e-9
                or type(control['paired_inputs']) is not bool
                or (control['paired_inputs'] and control['comparators_agree'] is not True)):
            raise ValueError('archived scores, inputs or probabilities differ: ' + mid)
        for arm in ('r9', 'r10'):
            _decisions(control['forecast'][arm], None, row['line'])
    return originals, controls, identities


def normalized(name):
    return ''.join(ch for ch in normalize('NFKD', name.casefold()) if ch.isalnum())


def same_club(fixture, side, opponent, aliases):
    espn_id, name = fixture[f'{side}_id'], fixture[f'{side}_name']
    if espn_id in aliases:
        mapping = aliases[espn_id]
        return (name, opponent['internationalName'].strip(), str(opponent['id'])) == (
            mapping['espn'], mapping['uefa'], mapping['uefa_id'])
    choices = {opponent['internationalName']}
    for key in ('displayName', 'shortName', 'displayOfficialName'):
        choices.update(opponent['translations'].get(key, {}).values())
    return any(normalized(name) == normalized(choice) for choice in choices if isinstance(choice, str))


def verify_resumption(record, source_identity, binding, score):
    capture = record['capture']
    observed = aware(capture['captured_at'])
    body = raw_result(HERE/'evidence', capture['path'], capture['sha256'])
    data = json.loads(body)
    header = data['header']
    game, = header['competitions']
    started = summary_kickoff(body, capture['url'], dict(match_id=record['espn_match_id'], competition=CODE,
                              home='espn:'+source_identity['home_id'], away='espn:'+source_identity['away_id']), observed)
    times = {}
    for kind, period in (('halftime', 1), ('start-2nd-half', 2), ('end-regular-time', 2)):
        event, = (event for event in data['keyEvents'] if event['type']['type'] == kind and event['period']['number'] == period)
        times[kind] = aware(event['wallclock'])
    scheduled, archived = (aware(record[key]) for key in ('uefa_scheduled_at', 'espn_archived_at'))
    halftime, restarted, finished = (times[k] for k in ('halftime', 'start-2nd-half', 'end-regular-time'))
    halves = {team['homeAway']: [int(part['displayValue']) for part in team['linescores']] for team in game['competitors']}
    regulation, status = data['format']['regulation'], game['status']['type']
    if (capture['http_status'] != 200 or header['season']['year'] != 2025 or header['season']['type'] != 13694
            or (status['name'], status['completed']) != ('STATUS_FULL_TIME', True)
            or (regulation['periods'], regulation['clock']) != (2, 2700)
            or aware(game['date']) != archived or aware(source_identity['kickoff_utc']) != archived
            or binding['id'] != record['uefa_match_id'] or binding['matchday'] != record['matchday']
            or not scheduled <= started < halftime < archived <= restarted < finished <= observed
            or started.date() != scheduled.date() or restarted.date() != archived.date()
            or started.date() == restarted.date()
            or any(len(values) != 2 for values in halves.values())
            or tuple(sum(halves[side]) for side in ('home', 'away')) != score
            or any(team.get('shootoutScore') not in (None, '', 0, '0') for team in game['competitors'])):
        raise ValueError('the two independently timed halves do not support the documented resumption')
    return dict(record, first_half_started=started.isoformat(), first_half_ended=halftime.isoformat(),
                second_half_started=restarted.isoformat(), full_time=finished.isoformat(), halves=halves,
                regulation=list(score))


def previous_rounds(originals, identities):
    captures = prior.prepare.read(HERE/'evidence/captures.json')
    aliases = prior.prepare.read(HERE/'club-aliases.json')
    if len(captures) != len(RANGES):
        raise ValueError('both official date ranges are required')
    official = defaultdict(list)
    for capture, (start, end) in zip(captures, RANGES, strict=True):
        url = urlsplit(capture['url'])
        query = dict(competitionId=['2019'], seasonYear=['2026'], limit=['100'], offset=['0'], fromDate=[start], toDate=[end])
        if ((url.scheme, url.netloc, url.path) != ('https', 'match.uefa.com', '/v5/matches')
                or parse_qs(url.query) != query or capture['http_status'] != 200):
            raise ValueError('verified previous-season UEFA endpoint differs')
        body = raw_result(HERE/'evidence', capture['path'], capture['sha256'])
        for game in json.loads(body):
            official[aware(game['kickOffTime']['dateTime'])].append((game, capture))
    rounds, clubs, seen = defaultdict(list), {}, set()
    revision = prior.prepare.read(HERE/'evidence/resumption.json')
    resumption = None
    old = {mid: row for mid, row in originals.items() if row['date'] < '2026-07-01'}
    for mid, row in old.items():
        fixture = identities[mid]
        revised = mid == revision['espn_match_id']
        kickoff = aware(revision['uefa_scheduled_at'] if revised else fixture['kickoff_utc'])
        matches = [(g, meta) for g, meta in official[kickoff]
                   if all(same_club(fixture, side, g[side+'Team'], aliases) for side in ('home', 'away'))]
        if len(matches) != 1:
            raise ValueError('expected one official ordered fixture at the recorded kickoff: ' + mid)
        game, capture = matches[0]
        official_id, matchday = str(game['id']), int(game['matchday']['sequenceNumber'])
        binding = dict(id=official_id, matchday=matchday)
        for side in ('home', 'away'):
            provider_id, uefa_id = fixture[f'{side}_id'], str(game[side+'Team']['id'])
            if clubs.setdefault(provider_id, uefa_id) != uefa_id:
                raise ValueError('a club changed its independently matched official identity')
            binding[side] = uefa_id
        status, score = uefa_score(game, dict(cohort=CODE, kickoff_at=kickoff.isoformat()), binding,
                                   aware(capture['captured_at']), season_year='2026')
        if status != 'FINISHED' or score != tuple(row['actual']) or official_id in seen:
            raise ValueError('official previous-season outcome or identity differs: ' + mid)
        if revised:
            resumption = verify_resumption(revision, fixture, binding, score)
        seen.add(official_id)
        rounds[matchday].append(dict(match_id=mid, uefa_match_id=official_id, kickoff_at=kickoff.isoformat(),
                                    home=fixture['home_name'], away=fixture['away_name'],
                                    clubs=[fixture['home_id'], fixture['away_id']], actual=f'{score[0]}-{score[1]}',
                                    source_sha256=capture['sha256']))
    if (resumption is None or len(seen) != sum(map(len, official.values())) or len(clubs) != 36 or len(set(clubs.values())) != 36
            or any(Counter(club for row in group for club in row['clubs']) != Counter(clubs.keys()) for group in rounds.values())):
        raise ValueError('previous-season matches must cover the same 36 independently identified clubs per round')
    return rounds, clubs, resumption


def held_rounds():
    history = prior.prepare.read(PRIOR/'history.json')['competitions'][CODE]['matchdays']
    return {int(day): [dict(match, source_sha256=match['score_source']['sha256']) for match in round_['matches']]
            for day, round_ in history.items()}


def candidate(row, original, evidence):
    score = '-'.join(map(str, original['actual']))
    pick = original['forecast']['candidate']
    first = pick['primary']
    if score != row['actual'] or first != pick['top3'][0]:
        raise ValueError('round score evidence differs from the archive: ' + row['match_id'])
    _, market, _ = _decisions(original['forecast']['market'], original['actual'], original['line'])
    controls = {arm: evidence['forecast'][arm]['primary'] for arm in ('r9', 'r10')}
    supported = evidence['paired_inputs'] and all(value == first for value in controls.values())
    keys = ('match_id', 'uefa_match_id', 'kickoff_at', 'home', 'away', 'actual', 'source_sha256')
    return dict({key: row[key] for key in keys}, primary=first, top3=pick['top3'],
                first_probability=original['quality']['candidate']['p_first'], evidence_available=evidence['paired_inputs'],
                supported=supported, comparisons=controls, market={m: market[m] for m in ('score_top1', 'score_top3')})


def grade_round(rows):
    by_score = rank(rows)
    with_agreement = [*rank([row for row in rows if row['supported']]),
                      *rank([row for row in rows if not row['supported']])][:3]
    scores = {row['match_id']: row['actual'] for row in rows}
    result = {}
    for arm, selected in (('original', by_score), ('agreement', with_agreement)):
        result[arm] = dict(selected=[row['match_id'] for row in selected], **sweep(selected, scores),
                           market={metric: dict(covered=sum(row['market'][metric] is not None for row in selected),
                                                hits=sum(row['market'][metric] is True for row in selected))
                                   for metric in ('score_top1', 'score_top3')})
    return dict(registered=len(rows), evidence_available=sum(row['evidence_available'] for row in rows),
                supported=sum(row['supported'] for row in rows), first_hits=sum(row['actual'] == row['primary'] for row in rows),
                three_hits=sum(row['actual'] in row['top3'] for row in rows), arms=result,
                matches=sorted(rows, key=lambda row: (row['kickoff_at'], row['match_id'])))


def evaluate(rounds, window, originals, controls):
    if (sorted(rounds) != window['matchdays'] or any(len(rows) != 18 for rows in rounds.values())
            or len({row['match_id'] for rows in rounds.values() for row in rows}) != window['fixtures']):
        raise ValueError('the registered season should have six or three complete official rounds')
    grades = {day: grade_round([candidate(row, originals[row['match_id']], controls[row['match_id']]) for row in rounds[day]])
              for day in sorted(rounds)}
    totals = {arm: {metric: sum(row['arms'][arm][metric] for row in grades.values()) for metric in SUMMARY_FIELDS}
              for arm in ('original', 'agreement')}
    delta = {metric: totals['agreement'][metric] - totals['original'][metric] for metric in SUMMARY_FIELDS}
    advances = min(delta.values()) >= 0 and any(delta[metric] > 0 for metric in ('primary_sweeps', 'primary_hits'))
    changes = sum(set(row['arms']['original']['selected']) != set(row['arms']['agreement']['selected']) for row in grades.values())
    return dict(season=window['season'], fixtures=window['fixtures'], matchdays=grades, totals=totals, paired_net=delta,
                rounds_with_different_members=changes, window_screen_passed=advances)


def audit():
    protocol = (HERE/'protocol.json').read_bytes()
    policy = json.loads(protocol)
    originals, controls, identities = historical_inputs()
    old, binding, resumption = previous_rounds(originals, identities)
    windows = {key: evaluate(rounds, policy['windows'][key], originals, controls)
               for key, rounds in (('screen', old), ('holdout', held_rounds()))}
    arms = windows['screen']['matchdays'][resumption['matchday']]['arms']
    resumption['selected_by'] = [arm for arm, grade in arms.items() if resumption['espn_match_id'] in grade['selected']]
    return dict(version=policy['version'], label=policy['label'], protocol_sha256=sha256(protocol).hexdigest(),
                previous_season_clubs=binding, controls=CONTROL_HASHES,
                regulation_history_sha256=HOLDOUT_SHA, windows=windows,
                verified_resumption=resumption,
                prospective_screen_passed=all(row['window_screen_passed'] for row in windows.values()))


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2, allow_nan=False))
