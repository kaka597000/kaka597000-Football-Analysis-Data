"""Bind the next three registered J1 slates to the public result endpoints."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware
from research_program import goal_state_forward as ledger
from research_program import nov25_first_review as historical
from research_program.display_window_review import _registered, summary_kickoff
from research_program.goal_state_study import sha
from research_program.three_arm_review import _results


PACKAGES = Path(__file__).resolve().parents[1]
BEIJING = ZoneInfo('Asia/Shanghai')
NOVEMBER = PACKAGES / '20261126-r26-j1-first-stage'
DECEMBER = PACKAGES / '20261126-j1-december-windows'
NOVEMBER_REGISTRATION = PACKAGES / '20261125-j1-stage-windows'
NOV25_ARCHIVE = '2ad0d42fa60f2ddde28a2cf4a161f1ac8cae1c2afef27dcf8083b53a466ace38'


def read(path):
    return json.loads(path.read_bytes())


def registration(root):
    path = root / 'registration'
    ref = read(path / 'plan.json')
    return _registered(ledger._read(path, ref))


def slates(root, names, official_path, official, display=None):
    plan, fixtures, windows, specs = registration(root)
    if ({mid for name in names for mid in windows[name]} != set(official['fixtures'])
            or {name: specs[name]['expected'] for name in names} != official['confirmed_per_window']):
        raise ValueError('J.League confirmation does not cover the original windows')
    for name in names:
        waves = defaultdict(list)
        for mid in windows[name]:
            fixture = fixtures[mid]
            source = official['fixtures'][mid]
            scheduled = aware(fixture['kickoff_at']).astimezone(BEIJING)
            event = mid.removeprefix('espn:')
            page = urlsplit(source['url'])
            if (not mid.startswith('espn:') or not event.isascii() or not event.isdecimal()
                    or (page.scheme, page.netloc) != ('https', 'www.jleague.jp')
                    or not page.path.startswith('/match/j1/2026/') or scheduled != aware(source['kickoff_beijing'])):
                raise ValueError('J1 official and ESPN fixture binding differs: ' + mid)
            waves[scheduled].append(dict(match_id=mid, home_id=fixture['home'], away_id=fixture['away'],
                official_home=source['home'], official_away=source['away'], official_match_url=source['url'],
                espn_summary_url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/jpn.1/summary?event={event}'))
        yield name, dict(registration=plan['freeze_id'], registered=len(windows[name]), score_display_freeze=display,
                         official_crosswalk=str(official_path.relative_to(PACKAGES)), official_crosswalk_sha256=sha(official_path),
                         waves=[dict(scheduled=kickoff.isoformat(), fixtures=sorted(rows, key=lambda r: r['match_id']))
                                for kickoff, rows in sorted(waves.items())])


def kickoff_rehearsal():
    _, universe, windows, _ = registration(NOVEMBER_REGISTRATION)
    fixtures = {mid: universe[mid] for mid in windows['nov25']}
    state = (PACKAGES / '20261126-j1-forward-result-review/nov25-state').resolve()
    cutoff = max(aware(json.loads(line)['known_at'])
                 for line in (state / 'normalized-results.jsonl').read_text().splitlines())
    results, issues = _results(state, fixtures, cutoff)
    if issues or results.keys() != fixtures.keys():
        raise ValueError('previous J1 regular-season scores did not replay')
    archive_path = PACKAGES / '20261125-forward-settlement/nov25/evidence.tar.gz'
    if sha(archive_path) != NOV25_ARCHIVE:
        raise ValueError('previous J.League evidence archive differs')
    pages = defaultdict(list)
    with tarfile.open(archive_path) as archive:
        manifest = archive.extractfile('snapshot/jleague-live-captures.jsonl').read()
        for line in manifest.splitlines():
            capture = json.loads(line)
            if capture['http_status'] != 200:
                continue
            code = capture.get('jleague_match_code') or capture['match_code']
            mid = 'espn:' + historical.J1_CARDS[code][0]
            body = archive.extractfile('intake/' + capture['path']).read()
            if sha256(body).hexdigest() != capture['sha256'] or len(body) != capture['bytes']:
                raise ValueError('original J.League page changes: ' + mid)
            pages[mid].append(historical.official_card(body, dict(capture, code=code), fixtures[mid]))
    proof = {}
    for mid, fixture in sorted(fixtures.items()):
        result = results[mid]
        source = result['source']
        try:
            kickoff = summary_kickoff((state / source['path']).read_bytes(), source['source_url'],
                                      dict(fixture, competition='jpn.1'), aware(source['captured_at']))
        except (ValueError, KeyError, TypeError, AttributeError):
            kickoff = None
        observations = sorted(pages[mid], key=lambda row: aware(row['source']['captured_at_utc']))
        outcome = dict(home_goals=result['home'], away_goals=result['away'], observed_at=source['captured_at'])
        starting = dict(at=kickoff.isoformat()) if kickoff else None
        official = historical.official_crosscheck(observations, dict(kickoff=starting), outcome)
        interval = official['kickoff_interval']
        proof[mid] = dict(verified_score=[result['home'], result['away']],
                          espn_kickoff=kickoff.astimezone(BEIJING).isoformat() if kickoff else None,
                          scheduled=aware(fixture['kickoff_at']).astimezone(BEIJING).isoformat(),
                          official_interval={key: aware(interval[key]).astimezone(BEIJING).isoformat()
                                             for key in ('start_inclusive', 'end_exclusive')} if interval else None,
                          official_kickoff_source=official['kickoff_source'], verdict=official['verdict'],
                          issues=official['issues'])
    return dict(fixtures=len(proof), espn_actual_starts=sum(row['espn_kickoff'] is not None for row in proof.values()),
                official_actual_minutes=sum(row['official_interval'] is not None for row in proof.values()),
                archive_sha256=NOV25_ARCHIVE, matches=proof)


def plan():
    nov_path = NOVEMBER / 'public-archive/verified.json'
    dec_path = DECEMBER / 'evidence/jleague-december-comparison.json'
    november = read(nov_path)
    publication = ledger._read(NOVEMBER / 'nov28_29', read(NOVEMBER / 'nov28_29/publication.json'))
    if november['publication_freeze'] != publication['freeze_id']:
        raise ValueError('J1 independent calendar refers to a different first display')
    scopes = dict(slates(NOVEMBER_REGISTRATION, ('nov28_29',), nov_path,
                         november['official_calendar'], publication['freeze_id']))
    scopes.update(slates(DECEMBER, ('dec04_06', 'dec12_13'), dec_path, read(dec_path)))
    return dict(competition='jpn.1', windows=scopes,
                actual_kickoff_basis='ESPN typed first-period clock and J.League reported KO minute when validated',
                regulation_result_basis='Verify the ESPN regular-season result and cross-check the J.League final',
                november_25_start_rehearsal=kickoff_rehearsal())


if __name__ == '__main__':
    print(json.dumps(plan(), ensure_ascii=False, indent=2))
