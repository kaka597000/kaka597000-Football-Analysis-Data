"""Bind both future J1 windows to the original and newly captured calendar bytes."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import display_window_review as review, goal_state_forward as ledger

from official import official_rows


ROOT = Path(__file__).resolve().parent
ANNUAL_ARCHIVE = ROOT.parent / '20261125-j1-stage-windows/evidence/prematch-07.tar.gz'
EARLY_EVIDENCE = ROOT.parent / '20261126-r26-j1-first-stage/evidence'
LATE_EVIDENCE = ROOT / 'evidence'
ANNUAL_SHA = '88ae1a444b952f521beda041b3c8cc4784421e88484032a3450e9075fb0c2fa4'


def read(path):
    return json.loads(path.read_bytes())


def sha(body):
    return hashlib.sha256(body).hexdigest()


def checked_response(body, manifest):
    if (manifest['http_status'] != 200 or len(body) != manifest['bytes']
            or sha(body) != manifest['sha256']):
        raise ValueError('calendar response differs from its capture: ' + manifest['url'])
    return json.loads(body)


def event_identity(event):
    game, = event['competitions']
    if (event['season']['type'] != 14287 or event['season']['slug'] != 'regular-season'
            or event['status']['type']['state'] != 'pre' or event['status']['type']['name'] != 'STATUS_SCHEDULED'
            or not game['timeValid'] or aware(event['date']) != aware(game['date'])):
        raise ValueError('scheduled regular J1 match required: ' + event['id'])
    return matchup(game, event['date'])


def matchup(game, kickoff):
    teams = {r['homeAway']: 'espn:' + str(r['team']['id']) for r in game['competitors']}
    if set(teams) != {'home', 'away'} or teams['home'] == teams['away']:
        raise ValueError('oriented J1 team identity required')
    return dict(match_id='espn:' + game['id'], cohort='jpn.1', stage='Japanese J1 League',
                kickoff_at=aware(kickoff).isoformat(), **teams)


def board_events(board):
    if [r['slug'] for r in board['leagues']] != ['jpn.1']:
        raise ValueError('calendar is outside J1')
    return board['events']


def merge(checked, rows):
    for row in rows:
        mid = row['match_id']
        if mid in checked and row != checked[mid]:
            raise ValueError('calendar snapshots disagree: ' + mid)
        checked[mid] = row


def inputs():
    protocol = read(ROOT / 'protocol.json')
    windows = protocol['windows']
    with tarfile.open(ANNUAL_ARCHIVE) as archive:
        annual = archive.extractfile('raw/espn_calendar_2026.json').read()
    if sha(annual) != ANNUAL_SHA:
        raise ValueError('original annual calendar bytes differ')
    events = board_events(json.loads(annual))
    confirmed = {}
    with tarfile.open(EARLY_EVIDENCE / 'public-source-snapshots.tar.gz') as archive:
        for item in read(EARLY_EVIDENCE / 'calendar-manifest.json'):
            if item['label'] in ('next_1205', 'next_1206'):
                board = checked_response(archive.extractfile(item['raw_file']).read(), item)
                merge(confirmed, map(event_identity, board_events(board)))
        for item in read(EARLY_EVIDENCE / 'next-supplementary-manifest.json'):
            raw = archive.extractfile('extra-calendar/' + item['raw_file']).read()
            header = checked_response(raw, item)['header']
            event, = header['competitions']
            if (header['league']['slug'] != 'jpn.1' or header['season']['type'] != 14287
                    or event['id'] != item['event_id'] or event['status']['type']['state'] != 'pre'
                    or event['status']['type']['name'] != 'STATUS_SCHEDULED'):
                raise ValueError('supplementary match is not scheduled in regular J1')
            merge(confirmed, [matchup(event, event['date'])])
    for item in read(LATE_EVIDENCE / 'request-manifest.json'):
        board = checked_response((LATE_EVIDENCE / item['raw_file']).read_bytes(), item)
        merge(confirmed, map(event_identity, board_events(board)))
    slates = {}
    fixtures = []
    for window in windows:
        start, end = aware(window['from']), aware(window['until'])
        rows = [event_identity(e) for e in events if start <= aware(e['date']) < end]
        if len(rows) != window['expected'] or len({r[s] for r in rows for s in ('home', 'away')}) != 20:
            raise ValueError('annual calendar does not hold a full J1 round: ' + window['name'])
        slates[window['name']] = sorted(r['match_id'] for r in rows)
        fixtures.extend(rows)
    if len(fixtures) != len(confirmed) or {r['match_id']: r for r in fixtures} != confirmed:
        raise ValueError('fresh schedule confirmations differ from the original full population')
    return annual, fixtures, slates


def check_registration(fixtures, slates):
    path = ROOT / 'registration'
    plan = ledger._read(path, read(path / 'plan.json'))
    parent_path = ROOT / 'source-registration'
    parent = ledger._read(parent_path, read(parent_path / 'receipts.json')['registration'])
    identity = plan['payload']['identity']
    if (identity['calendar_sha256'] != ANNUAL_SHA or identity['slates'] != slates
            or identity['protocol_sha256'] != sha((ROOT / 'protocol.json').read_bytes())
            or identity['original_registration'] != parent['record_sha256']
            or parent['payload']['identity']['manifest_sha256'] != sha((LATE_EVIDENCE / 'request-manifest.json').read_bytes())
            or plan['payload']['fixtures'] != {r['match_id']: r for r in fixtures}
            or plan['payload']['fixtures'] != parent['payload']['fixtures']):
        raise ValueError('preregistered fixture, protocol or evidence identity differs')
    with TemporaryDirectory(prefix='j1-stage-check-') as tmp:
        summary = review.review(plan, ledger_root=tmp, result_state=tmp, evidence_root=tmp,
                                at=plan['recorded_at'])
    if summary['combined']['pending_n'] != len(fixtures) or summary['combined']['phase_pass']:
        raise ValueError('an unissued prospective window was awarded credit')
    return summary


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--prepare', type=Path, help='write verified inputs for the one-time registration')
    args = cli.parse_args()
    annual, fixtures, slates = inputs()
    if args.prepare:
        args.prepare.mkdir(parents=True)
        (args.prepare / 'annual.json').write_bytes(annual)
        (args.prepare / 'fixtures.json').write_text(json.dumps(fixtures, indent=2) + '\n')
    else:
        summary = check_registration(fixtures, slates)
        official = official_rows(LATE_EVIDENCE, fixtures, slates)
        if official != read(LATE_EVIDENCE/'jleague-december-comparison.json'):
            raise ValueError('retained J.League comparison differs from the original public response')
        summary['official_calendar'] = official
        print(json.dumps(summary, ensure_ascii=False, indent=2))
