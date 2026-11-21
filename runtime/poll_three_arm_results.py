"""Poll registered Brazil matches still missing certified regulation scores after kickoff + 2h."""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

if __package__:
    from .source_review_api import (ESPN, ScoreboardQueue, append, aware, regulation_row,
                                  certify_result, read_predictions, read_results)
else:
    from source_review_api import (ESPN, ScoreboardQueue, append, aware, regulation_row,
                                 certify_result, read_predictions, read_results)
from publication import deliver
from storage_lock import exclusive_lock

SCOPE = {'competition': 'bra.1', 'cohort': 'bra.1', 'stages': ['regular']}


def _fetch(url):
    # curl's deadline covers DNS, TLS, and the entire body. No retry or redirects.
    return subprocess.run(
        ['curl', '--disable', '--proto', '=https', '--silent', '--show-error', '--fail',
         '--max-time', '6', '--max-filesize', '12000000', url],
        check=True, timeout=6, capture_output=True,
    ).stdout


def _registered_events(registration, plan, fixtures, state):
    if (registration['schema'] != 'THREE-ARM-RESEARCH-REGISTRATION-1'
            or aware(registration['recorded_at']) > aware(plan['recorded_at'])):
        raise ValueError('invalid prematch registration')
    path = (state / registration['scoreboard_source']).resolve()
    if not path.is_relative_to(state):
        raise ValueError('scoreboard outside retained state')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != registration['scoreboard_sha256']:
        raise ValueError('registered scoreboard checksum mismatch')
    board = json.loads(raw)
    if [league['slug'] for league in board['leagues']] != ['bra.1']:
        raise ValueError('registered scoreboard league mismatch')
    events = {}
    for item in registration['fixtures']:
        mid = item['match_id']
        if mid in events or mid not in fixtures or not re.fullmatch(r'espn:[0-9]+', mid):
            raise ValueError('unexpected registered fixture')
        frozen = fixtures[mid]
        if (item['cohort'] != 'bra.1' or item['stage'] != 'regular'
                or any(frozen[k] != item[k] for k in ('home', 'away', 'cohort', 'stage'))
                or aware(frozen['kickoff_at']) != aware(item['kickoff_at'])):
            raise ValueError('registered fixture differs from frozen plan')
        event, = [event for event in board['events'] if str(event['id']) == mid[5:]]
        competition, = event['competitions']
        sides = {t['homeAway']: 'espn:' + str(t['team']['id']) for t in competition['competitors']}
        if (len(competition['competitors']) != 2 or sides != {k: item[k] for k in ('home', 'away')}
                or aware(event['date']) != aware(frozen['kickoff_at'])):
            raise ValueError('registered scoreboard fixture identity conflict')
        events[mid] = event
    if set(events) != set(fixtures):
        raise ValueError('registered population differs from frozen plan')
    return events


def _retain(state, raw, captured, url):
    digest = hashlib.sha256(raw).hexdigest()
    path = state / 'raw' / (digest + '.json.gz')
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw:
            raise ValueError('existing raw evidence checksum mismatch')
    else:
        deliver(path, gzip.compress(raw, mtime=0))
    return {'source_url': url, 'captured_at': captured, 'sha256': digest,
            'path': path.relative_to(state).as_posix()}


def poll(batch, registration, state, *, clock=None, fetcher=_fetch):
    clock = clock or (lambda: datetime.now(timezone.utc))
    state, batch, registration = Path(state).resolve(), Path(batch), Path(registration)
    plan, fixtures, _ = read_predictions(batch)
    protocol = registration.read_bytes()
    if hashlib.sha256(protocol).hexdigest() != plan['payload']['binding']['registration_sha256']:
        raise ValueError('registration checksum differs from original plan')
    events = _registered_events(json.loads(protocol), plan, fixtures, state)
    report = {'registered': len(fixtures), 'due_missing': 0, 'requests': 0, 'accepted': [], 'pending': {}}
    # Serialize local pollers using the existing stable protocol inode. The normal
    # collector runs before this step in the shared workflow concurrency group.
    with exclusive_lock(registration):
        now = clock()
        eligible = {mid: f for mid, f in fixtures.items() if aware(f['kickoff_at']) + timedelta(hours=2) <= now}
        if not eligible:
            return report
        target = state / 'normalized-results.jsonl'
        previous, issues = read_results(state, eligible, now) if target.exists() else ({}, {})
        missing = {}
        for mid in eligible:
            if 'conflicting certified regulation scores' in issues.get(mid, []):
                report['pending'][mid] = 'existing certified results conflict'
            elif mid not in previous:
                missing[ESPN + 'bra.1/summary?event=' + mid[5:]] = mid
        report['due_missing'] = len(missing)
        if not missing:
            return report
        queue_dir = batch / 'result-polling'
        queue_dir.mkdir(exist_ok=True)
        queue = ScoreboardQueue(queue_dir, missing)
        for url in queue.order(missing)[:3]:
            mid = missing[url]
            queue.mark(url)
            report['requests'] += 1
            started = clock().isoformat()
            try:
                raw = fetcher(url)
            except (OSError, subprocess.SubprocessError) as exc:
                reason = type(exc).__name__
                if isinstance(exc, subprocess.CalledProcessError):
                    reason += ' exit ' + str(exc.returncode)
                report['pending'][mid] = reason
                append(state / 'requests.jsonl', {'source_url': url, 'started_at': started,
                       'captured_at': clock().isoformat(), 'status': 'FAILED', 'reason': reason})
                continue
            observed = clock()
            captured = observed.isoformat()
            ref = _retain(state, raw, captured, url)
            append(state / 'requests.jsonl', {'source_url': url, 'started_at': started,
                   'captured_at': captured, 'status': 'OK', 'raw': ref})
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError('expected ESPN summary object')
                row = regulation_row(SCOPE, events[mid], body, captured, ref)
                certify_result(row, fixtures[mid], state, observed)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                report['pending'][mid] = str(exc)
                continue
            append(target, row)
            report['accepted'].append(mid)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('batch', 'registration', 'state-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(poll(args.batch, args.registration, args.state_dir), sort_keys=True))
