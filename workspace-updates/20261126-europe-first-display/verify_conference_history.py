"""Rehearse official round coverage and ESPN first-half clocks on real Conference matches."""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory

from review import results

import prepare
import result_intake
from research.analysis_freeze import aware


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE/'result-intake-preflight'
HISTORY = HERE.parent/'20261105-europa-conference-analysis/parts/analysis.tar.gz.part000'
HISTORY_SHA = '2470d20a20ca1b346792b6d9b1725e32255e047ca899a8baf81143f81796e299'
SCHEDULE_SHA = 'a44996b55f666fa31d7ddf633642d2954e9b41866625177d4de0381f23f29786'
SCHEDULE_MEMBER = 'WCPP/reports/europa-conference-20261105/data/raw/espn-uefa.europa.conf-'
DAY = '2026-11-05'
ROUND = 3
SAMPLES = {
    'espn:401915740': (2, 1),
    'espn:401915821': (0, 1),
    'espn:401915831': (0, 0),
}


def previous_roster():
    code, stage, season_type, _, _ = prepare.COMPETITIONS['uecl']
    if sha256(HISTORY.read_bytes()).hexdigest() != HISTORY_SHA:
        raise ValueError('historical ESPN schedule archive differs')
    with tarfile.open(HISTORY) as archive:
        raw = archive.extractfile(SCHEDULE_MEMBER+'scoreboard-20261105.json').read()
        metadata = json.load(archive.extractfile(SCHEDULE_MEMBER+'metadata.json'))
    board = json.loads(raw)
    url = f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={DAY.replace("-", "")}'
    if (sha256(raw).hexdigest() != SCHEDULE_SHA or len(raw) != metadata['bytes']
            or metadata['sha256'] != SCHEDULE_SHA or metadata['url'] != url or metadata['http_status'] != 200
            or [group['slug'] for group in board['leagues']] != [code]):
        raise ValueError('historical ESPN pregame identity differs')
    fixtures = {}
    for event in board['events']:
        game, = event['competitions']
        kickoff = aware(event['date'])
        teams = {row['homeAway']: 'espn:' + str(row['team']['id']) for row in game['competitors']}
        mid = 'espn:' + event['id']
        if (kickoff.date().isoformat() != DAY or aware(game['date']) != kickoff
                or mid in fixtures or event['id'] != game['id']
                or aware(metadata['queried_at']) >= kickoff or teams.keys() != {'home', 'away'}
                or len(game['competitors']) != 2 or teams['home'] == teams['away']
                or event['status']['type']['name'] != 'STATUS_SCHEDULED'
                or event['season'] != {'year': 2026, 'type': season_type, 'slug': 'league-phase'}):
            raise ValueError('historical scheduled slot differs: ' + mid)
        fixtures[mid] = dict(teams, match_id=mid, kickoff_at=kickoff.isoformat(), cohort=code, stage=stage)
    if len(fixtures) != 18 or not SAMPLES.keys() <= fixtures.keys():
        raise ValueError('the historical comparison requires its complete 18-match slate')
    return fixtures, metadata


def official_roster(fixtures, capture):
    code = prepare.COMPETITIONS['uecl'][0]
    registered = {mid: row['fixture'] for mid, row in prepare.register(False)['uecl']['today'].items()}
    crosswalk = result_intake.official_bindings(registered)
    clubs = {row[side]: crosswalk[mid][side] for mid, row in registered.items() for side in ('home', 'away')}
    body = result_intake.raw_result(EVIDENCE, capture['path'], capture['sha256'])
    games = json.loads(body)
    official = {(str(game['homeTeam']['id']), str(game['awayTeam']['id']),
                 aware(game['kickOffTime']['dateTime'])): game for game in games}
    if len(official) != len(games) or len(games) != len(fixtures) or len(set(clubs.values())) != 36:
        raise ValueError('the independent source requires one final for each original match')
    bindings = {}
    for mid, fixture in fixtures.items():
        home, away = (clubs[fixture[side]] for side in ('home', 'away'))
        game = official[home, away, aware(fixture['kickoff_at'])]
        binding = dict(id=str(game['id']), home=home, away=away, matchday=ROUND)
        status, score = result_intake.uefa_score(game, fixture, binding, aware(capture['captured_at']))
        if fixture['cohort'] != code or status != 'FINISHED' or score is None:
            raise ValueError('the official historical match is missing its regulation result: ' + mid)
        bindings[mid] = binding
    if len({row['id'] for row in bindings.values()}) != 18:
        raise ValueError('official historical IDs must be one-to-one')
    return bindings


def verify():
    fixtures, schedule = previous_roster()
    official, = (capture for capture in prepare.read(EVIDENCE/'captures.json')
                 if result_intake.endpoint(capture['url'])[1] == 'uefa.europa.conf')
    bindings = official_roster(fixtures, official)
    sources = EVIDENCE/'uecl-espn'
    summaries = prepare.read(sources/'captures.json')
    if (len(summaries) != len(SAMPLES)
            or {result_intake.endpoint(entry['url'])[2] for entry in summaries} != SAMPLES.keys()):
        raise ValueError('the ESPN results differ from the declared historical test cases')
    at = max(aware(entry['captured_at']) for entry in [official, *summaries])
    with TemporaryDirectory(prefix='uecl-result-review-') as directory:
        root = Path(directory)
        evidence = [(official, EVIDENCE)] + [(entry, sources) for entry in summaries]
        for entry, source in evidence:
            result_intake.raw_result(source, entry['path'], entry['sha256'])
            shutil.copyfile(source/entry['path'], root/entry['path'])
        manifest = root/'captures.json'
        manifest.write_text(json.dumps([official, *summaries]), encoding='utf-8')
        state = root/'state'
        intake = result_intake.assemble(manifest, state, fixtures, bindings, at)
        finalized, errors = results(state, fixtures, at, bindings)
    if finalized.keys() != fixtures.keys() or errors or intake['captures_with_errors']:
        raise ValueError('real historical regulation scores did not survive the original review')
    clocks = {}
    for mid, expected in SAMPLES.items():
        result = finalized[mid]
        actual = (result['home'], result['away'])
        kickoff = result['actual_kickoff']
        if (actual != expected or result['confirmed_result_sources'].keys() != {'espn', 'uefa'} or kickoff is None):
            raise ValueError('historical first-half clock or dual-source result differs: ' + mid)
        scheduled = aware(fixtures[mid]['kickoff_at'])
        start = aware(kickoff['actual_kickoff_at'])
        clocks[mid] = dict(uefa_match_id=bindings[mid]['id'], regulation_score=list(actual),
                           scheduled=scheduled.astimezone(prepare.BEIJING).isoformat(), actual_kickoff=kickoff,
                           difference_seconds=(start-scheduled).total_seconds())
    return dict(competition='uefa.europa.conf', registered_historical_fixtures=len(fixtures),
                verified_regulation_scores=len(finalized), provider_clock_samples=len(clocks),
                scheduled_source=schedule, official_source=official, clock_evidence=clocks)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
