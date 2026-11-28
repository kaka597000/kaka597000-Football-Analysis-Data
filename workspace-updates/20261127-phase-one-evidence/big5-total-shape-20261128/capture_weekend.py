"""Retain exact public ESPN and FotMob responses for the locked Big Five matches."""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from data_sources.clients import NoRedirect
from research.analysis_freeze import aware
from research_program.goal_state_study import write_new
from settlement import load_window, locked_bindings
from v2_test.data_contract import public_url, safe_content


BUSY = {401, 403, 429}
MAX_RESPONSE = 20_000_000
FOTMOB_LABEL_SCOPES = (
    ('content', 'stats', 'Periods'),
    ('content', 'playerStats'),
    ('content', 'matchFacts', 'playerOfTheMatch'),
    ('content', 'matchFacts', 'topPlayers'),
)


def plan(fixtures, matches, phase, now):
    if phase not in ('kickoff', 'full-time') or not matches or len(set(matches)) != len(matches):
        raise ValueError('supply a valid phase and unique matches from the registered slate')
    if set(matches) - fixtures.keys():
        raise ValueError('requested fixture outside the original weekend registration')
    providers = ('espn',) if phase == 'kickoff' else ('espn', 'fotmob')
    wait = timedelta(minutes=90) if phase == 'full-time' else timedelta()
    acts, skipped = [], {}
    for mid in matches:
        fixture = fixtures[mid]
        ready = aware(fixture['kickoff_at']) + wait
        if now < ready:
            skipped[mid] = {'reason': 'CHECKPOINT_AHEAD', 'first_query_at': ready.isoformat()}
            continue
        nid = mid.removeprefix('espn:')
        if mid != 'espn:' + nid or not nid.isascii() or not nid.isdecimal():
            raise ValueError('expected a registered ESPN match identity')
        code = fixture['cohort']
        for provider in providers:
            if provider == 'espn':
                url = f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={nid}'
            else:
                fm = str(fixture['fotmob']['match_id'])
                if not fm.isascii() or not fm.isdecimal():
                    raise ValueError('expected a registered FotMob match identity')
                url = f'https://www.fotmob.com/api/data/matchDetails?matchId={fm}'
            acts.append({'match_id': mid, 'provider': provider, 'source_url': url,
                         'filename': f'{nid}-{provider}.json'})
    return acts, skipped


def fotmob_validation_view(value, path=()):
    """Distinguish public stat labels from credential fields during validation."""
    if isinstance(value, list):
        return [fotmob_validation_view(row, path) for row in value]
    if isinstance(value, dict):
        translated = {}
        for name, item in value.items():
            is_stat_label = (name == 'key' and any(path[:len(scope)] == scope for scope in FOTMOB_LABEL_SCOPES)
                             and (item is None or isinstance(item, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', item)))
            if is_stat_label:
                safe_content(item)
                continue
            translated[name] = fotmob_validation_view(item, (*path, name))
        return translated
    return value


def fetch(act, path):
    url = act['source_url']
    public_url(url)
    started = datetime.now(timezone.utc)
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'WCPP-research'})
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        status = response.status
        if status != 200:
            raise ValueError('expected HTTP 200')
        body = response.read(MAX_RESPONSE + 1)
        received = datetime.now(timezone.utc)
    if len(body) > MAX_RESPONSE:
        raise ValueError('response exceeds the existing public-capture size limit')
    document = json.loads(body)
    if not isinstance(document, dict):
        raise ValueError('match summary must be a JSON object')
    safe_content(fotmob_validation_view(document) if url.startswith('https://www.fotmob.com/') else document)
    with path.open('xb') as stream:
        stream.write(body)
    return {'requested_at': started.isoformat(), 'captured_at': received.isoformat(),
            'sha256': sha256(body).hexdigest(), 'bytes': len(body), 'http_status': status}


def collect(fixtures, matches, phase, out, root, *, fetcher=fetch):
    """Keep successful per-request receipts even when later calls fail."""
    root, out = Path(root).resolve(), Path(out).resolve()
    prefix = out.relative_to(root)
    started = datetime.now(timezone.utc)
    calls, skipped = plan(fixtures, matches, phase, started)
    out.mkdir(parents=True, exist_ok=False)
    receipts, failures, denied, next_request = [], [], {}, {}
    for act in calls:
        provider = act['provider']
        target = {k: act[k] for k in ('match_id', 'provider', 'source_url')}
        if provider in denied:
            failures.append(dict(target, status='SKIPPED_AFTER_PROVIDER_REJECTION', http_status=denied[provider]))
            continue
        sleep(max(0., next_request.get(provider, 0.) - monotonic()))
        next_request[provider] = monotonic() + 1.
        raw = out / act['filename']
        try:
            observed = fetcher(act, raw)
        except HTTPError as error:
            failures.append(dict(target, status='HTTP_ERROR', http_status=error.code))
            if error.code in BUSY:
                denied[provider] = error.code
            continue
        except (URLError, TimeoutError, OSError, ValueError) as error:
            failures.append(dict(target, status=type(error).__name__))
            continue
        receipt = dict(target, **observed, path=(prefix / raw.name).as_posix())
        write_new(raw.with_suffix('.receipt.json'), receipt)
        receipts.append(receipt)
    write_new(out / 'receipts.json', receipts)
    report = {'phase': phase, 'started_at': started.isoformat(), 'selected': matches,
              'calls_eligible': len(calls), 'responses': len(receipts),
              'checkpoint_ahead': skipped, 'failures': failures}
    write_new(out / 'capture.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('kickoff', 'full-time'), required=True)
    parser.add_argument('--match-id', action='append', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    fixtures = load_window(bundle, locked_bindings(bundle))
    report = collect(fixtures, args.match_id, args.phase, args.out, args.evidence_root)
    print(json.dumps(report, ensure_ascii=False))
