"""Replay the official J.League match-card bindings for the ten registered November fixtures."""

import argparse
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from publication import deliver
from research.analysis_freeze import aware, save, verify
from research_program import display_window_review as display
from research_program import goal_state_forward as ledger
from research_program import jleague_kickoff_proof as evidence
from research_program import nov25_first_review as historical
from research_program.goal_state_study import sha
from research_program.three_arm_review import _results


HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent / '20261127-europe-round1-review'
REGISTRATION = HERE.parent / '20261125-j1-stage-windows/registration'
ORIGINAL = HERE.parent / '20261126-r26-j1-first-stage'
OLD_RESULTS = HERE.parent / '20261126-j1-forward-result-review/nov25-state'
OLD_OFFICIAL = HERE.parent / '20261125-forward-settlement/nov25/evidence.tar.gz'
PACKET = HERE / 'kickoff-packet.json'


def read(path):
    return json.loads(path.read_bytes())


def original_inputs():
    plan = ledger._read(REGISTRATION, read(REGISTRATION / 'plan.json'))
    campaign, universe, slates, _ = display._registered(plan)
    review = verify(read(REVIEW / 'review-freeze.json'))
    plan_path = REVIEW / 'j1-capture-plan.json'
    if review['stage'] != 'review' or review['payload']['j1_capture_plan_sha256'] != sha(plan_path):
        raise ValueError('earlier J1 schedule evidence differs')
    slate = read(plan_path)['windows']['nov28_29']
    entries = [fixture for wave in slate['waves'] for fixture in wave['fixtures']]
    sources = read(HERE / 'captures.json')
    by_url = {row['url']: row for row in sources}
    publication = ledger._read(ORIGINAL / 'nov28_29', read(ORIGINAL / 'nov28_29/publication.json'))
    if (len(by_url) != len(sources) or len(entries) != 10 or set(slates['nov28_29']) != {e['match_id'] for e in entries}
            or by_url.keys() != {row['official_match_url'] for row in entries}
            or slate['registration'] != plan['freeze_id'] or slate['score_display_freeze'] != publication['freeze_id']):
        raise ValueError('expected the complete original J1 weekend and its official URLs')
    mapped = {}
    for row in entries:
        mid = row['match_id']
        source = by_url[row['official_match_url']]
        fixture = universe[mid]
        names = {side: row['official_' + side] for side in ('home', 'away')}
        body = evidence.raw(HERE, source, aware(fixture['kickoff_at']))
        identity = historical.official_binding(body, source, fixture, names)
        mapped[mid] = dict(identity=identity, source=source)
    return campaign, universe, dict(registration_sha256=plan['record_sha256'], bindings=mapped,
                                     capture_plan_sha256=sha(plan_path))


def seal(plan, payload):
    fixtures = [entry['identity']['fixture'] for entry in payload['bindings'].values()]
    cutoff = max(aware(entry['source']['captured_at_utc']) for entry in payload['bindings'].values())
    first_start = min(aware(fixture['kickoff_at']) for fixture in fixtures)
    fixture = dict(match_id='j1-official-kickoff:' + plan['record_sha256'], kickoff_at=first_start.isoformat(),
                   cutoff_at=cutoff.isoformat())
    ref = save(payload, fixture, stage='prematch', track=evidence.TRACK, idempotency_key=sha(HERE/'captures.json'))
    record = verify(read(Path(ref['path'])))
    if record['record_sha256'] != ref['sha256']:
        raise ValueError('different official J.League binding seal')
    body = json.dumps(dict(binding_record=record, captures={}), ensure_ascii=False, indent=2) + '\n'
    deliver(PACKET, body.encode('utf-8'))


def verify_previous_minutes(fixtures):
    reference = read(REVIEW / 'j1-capture-plan.json')['november_25_start_rehearsal']
    if sha(OLD_OFFICIAL) != reference['archive_sha256']:
        raise ValueError('original J.League archive differs')
    historical_fixtures = {mid: fixtures[mid] for mid in reference['matches']}
    cutoff = max(aware(json.loads(line)['known_at'])
                 for line in (OLD_RESULTS / 'normalized-results.jsonl').read_text().splitlines())
    outcomes, issues = _results(OLD_RESULTS, historical_fixtures, cutoff)
    if issues or outcomes.keys() != historical_fixtures.keys():
        raise ValueError('previous J1 final scores did not reproduce')
    labels = {mid: dict(home_goals=row['home'], away_goals=row['away'], observed_at=row['source']['captured_at'])
              for mid, row in outcomes.items()}
    mapping, captures = {}, {}
    with TemporaryDirectory(prefix='j1-official-replay-') as folder, tarfile.open(OLD_OFFICIAL) as archive:
        root = Path(folder)
        finale = [json.loads(line) for line in archive.extractfile('snapshot/jleague-live-captures.jsonl').read().splitlines()]
        for code, (event, home, away) in historical.J1_CARDS.items():
            mid = 'espn:' + event
            mapping[mid] = dict(fixture=fixtures[mid], code=code, url=historical.J1_URL.format(code),
                                section=historical.J1_ROUND, home=list(home), away=list(away))
            final = max((row for row in finale if row['http_status'] == 200 and
                         (row.get('jleague_match_code') or row.get('match_code')) == code),
                        key=lambda row: aware(row['captured_at_utc']))
            for phase, item in (('live', reference['matches'][mid]['official_kickoff_source']), ('final', final)):
                file = f'{phase}-{code}.html'
                (root / file).write_bytes(archive.extractfile('intake/' + item['path']).read())
                captures.setdefault(mid, []).append(dict(item, code=code, raw_file=file))
        starts, audits = evidence.compare_sources(captures, mapping, historical_fixtures, root, cutoff, {}, labels)
    for mid, originally in reference['matches'].items():
        interval = starts.get(mid, {}).get('actual_kickoff_interval')
        if (not interval or audits[mid]['issues'] or not audits[mid]['official_final']
                or any(aware(value) != aware(originally['official_interval'][key]) for key, value in interval.items())):
            raise ValueError('previous J1 start interval or final does not reproduce: ' + mid)
    return dict(fixtures=len(historical_fixtures), official_minutes=len(starts), independent_finals=len(outcomes))


def replay(plan, fixtures, payload):
    packet = read(PACKET)
    record = packet['binding_record']
    cutoff = aware(record['recorded_at'])
    mapping = evidence.bindings(packet, plan, fixtures, HERE, cutoff)
    if (record['payload'] != payload or packet['captures']
            or mapping.keys() != payload['bindings'].keys()):
        raise ValueError('pregame packet does not reproduce its first binding')
    verified = display.review(plan, ledger_root=ORIGINAL / 'nov28_29', result_state=OLD_RESULTS,
                              evidence_root=ORIGINAL / 'evidence', kickoff_evidence_root=HERE,
                              jleague_kickoffs=packet, at=cutoff)
    row = verified['windows']['nov28_29']
    if row['registered_n'] != 10 or row['completed_n'] != 0 or row['jleague_kickoff_evidence']:
        raise ValueError('a scheduled capture was promoted to actual kickoff evidence')
    return dict(bound=len(mapping), expected_matchdays=sorted({item['section'] for item in mapping.values()}),
                actual_starts_verified=0, pending_results=10, freeze_id=record['freeze_id'],
                previous_round=verify_previous_minutes(fixtures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issue', action='store_true')
    args = parser.parse_args()
    plan, fixtures, payload = original_inputs()
    if args.issue and not PACKET.exists():
        seal(plan, payload)
    print(json.dumps(replay(plan, fixtures, payload), ensure_ascii=False))
