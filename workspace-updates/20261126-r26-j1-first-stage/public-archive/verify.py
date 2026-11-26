"""Match the published November J1 evidence to the original registered firsts."""

from csv import DictReader
import gzip
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware
from research.display_delivery import delivery_request
from research_program import display_windows, goal_state_forward as ledger


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = HERE.parent
STAGE = PACKAGE/'nov28_29'
REGISTRATION = PACKAGE.parent/'20261125-j1-stage-windows/registration'
REPO = 'kaka597000/kaka597000-Football-Analysis-Data'
COMMIT = 'aba9784cd0c0d47c13ba20fa7ffdd8f40de97618'
RUN_ID = 45762416257
JOB_ID = 139715257933
STAGE_ID = '3ef75900d3e06bb1-v000001'
PLAN_ID = '99791e2c015d1473-v000001'
STEP = 'Verify the original ten first scores, selected seats, and next schedule'
BEIJING = ZoneInfo('Asia/Shanghai')
JLEAGUE = 'https://www.jleague.jp/j1/match/search-list/?startdate=2026-11-28&enddate=2026-11-29&period=custom&sort_desc=true'
JLEAGUE_TITLE = '【公式】明治安田Ｊ１リーグ 2026年11月28日〜2026年11月29日の日程・結果 | Ｊリーグ公式サイト'


def read(path):
    return json.loads(path.read_bytes())


def github_times(service):
    pull, run, job = (service[key] for key in ('pull', 'run', 'job'))
    head = {'sha': COMMIT, 'ref': 'research/r26-j1-total-pace-evidence-20261126'}
    if (pull['number'] != 68 or pull['head'] != dict(head, repository=REPO, private=False)
            or pull['base'] != dict(repository=REPO, private=False)
            or run['repository'] != dict(full_name=REPO, private=False)
            or run['pull_requests'] != [dict(number=68, head=head)] or run['head_branch'] != head['ref']
            or run['path'] != '.github/workflows/r26-j1-first-stage.yml' or run['event'] != 'pull_request'
            or run['id'] != RUN_ID or job['run_id'] != RUN_ID or job['id'] != JOB_ID or job['name'] != 'verify'
            or run['head_sha'] != COMMIT or job['head_sha'] != COMMIT
            or any(item['status'] != 'completed' or item['conclusion'] != 'success' for item in (run, job))
            or pull['html_url'] != f'https://github.com/{REPO}/pull/68'
            or job['html_url'] != f'https://github.com/{REPO}/actions/runs/{RUN_ID}/job/{JOB_ID}'):
        raise ValueError('original GitHub public service, commit or workflow differs')
    step, = (item for item in job['steps'] if item['name'] == STEP)
    if (step['status'], step['conclusion']) != ('completed', 'success'):
        raise ValueError('GitHub did not certify the original ten-fixture evidence')
    created, triggered, running, started, checked, finished = map(aware, (
        pull['created_at'], run['created_at'], job['started_at'], step['started_at'],
        step['completed_at'], job['completed_at']))
    if not created <= triggered <= running <= started <= checked <= finished:
        raise ValueError('GitHub chronological service events do not agree')
    return created, checked, finished


def readback(captures, entries, finished, earliest):
    fixed = [STAGE/name for name in ('message.txt', 'frozen-scorecard.csv', 'entries.json',
                                     'publication.json', STAGE_ID+'.json')]
    linked = [STAGE/ref['file'] for row in entries.values() for ref in row.values()]
    sides = [PACKAGE/'SHA256SUMS', PACKAGE/'verify_publication.py',
             REGISTRATION/'plan.json', REGISTRATION/(PLAN_ID+'.json')]
    expected = {path.relative_to(ROOT).as_posix(): path for path in fixed + linked + sides}
    if len(captures) != 29 or captures.keys() != expected.keys():
        raise ValueError('public readback must cover all original references')
    prefix = f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/'
    checksums = dict((name.removeprefix('./'), digest) for digest, name in (
        line.split('  ', 1) for line in (PACKAGE/'SHA256SUMS').read_text().splitlines()))
    times = []
    for relative, path in expected.items():
        meta = captures[relative]
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        if (meta['url'], meta['status'], meta['sha256'], meta['bytes']) != (prefix+relative, 200, digest, len(raw)):
            raise ValueError('retained file differs from the original GitHub response: ' + relative)
        if (path.is_relative_to(PACKAGE) and path.name != 'SHA256SUMS'
                and checksums.get(path.relative_to(PACKAGE).as_posix()) != digest):
            raise ValueError('the original package did not seal this record: ' + relative)
        times.append(aware(meta['observed_at']))
    if not finished <= min(times) <= max(times) < earliest:
        raise ValueError('the public readback observation must precede the original scheduled start')
    return max(times)


def scorecard(body, identity, entries, display_at):
    selected = identity['selected']
    with (STAGE/'frozen-scorecard.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(DictReader(handle))
    if len(rows) != 10 or {row['match_id'] for row in rows} != entries.keys() or len(selected) != 3:
        raise ValueError('public scorecard has incomplete or duplicated fixtures or seats')
    positions = []
    for row in rows:
        mid = row['match_id']
        signed = identity['rows'][mid]
        ref = ledger._read(STAGE, entries[mid]['authored'])
        payload = ref['payload']
        first = [row[key] for key in ('first', 'alt1', 'alt2')]
        kickoff = aware(signed['kickoff_at']).astimezone(BEIJING).strftime('%m-%d %H:%M')
        seat = str(selected.index(mid)+1) if mid in selected else ''
        if (first != signed['displayed_scores'] or len(set(first)) != 3 or row['wdl'] != signed['wdl']
                or row['kickoff_bjt'] != kickoff or row['selected_seat'] != seat
                or [row['home'], row['away']] != payload['team_names_zh']
                or float(row['observed_total_line']) != signed['total_line']
                or row['eligible_strict_total'] != str(payload['strict_quote_eligible'])
                or not aware(ref['recorded_at']) <= display_at < aware(signed['kickoff_at'])):
            raise ValueError('public scorecard differs from the original authored row: ' + mid)
        positions.append(body.index(delivery_request(ref)['text']))
    if positions != sorted(positions) or len(set(positions)) != len(rows):
        raise ValueError('public scorecard order differs from original first-display message')


def official_schedule(fixtures):
    module_path = PACKAGE.parent/'20261126-j1-december-windows/official.py'
    spec = spec_from_file_location('jleague_official_schedule', module_path)
    parser = module_from_spec(spec)
    spec.loader.exec_module(parser)
    capture = read(HERE/'jleague-capture.json')
    raw = gzip.decompress((HERE/'jleague-calendar.html.gz').read_bytes())
    return parser.check_schedule(capture, raw, fixtures, {'nov28_29': [f['match_id'] for f in fixtures]},
                                 expected_url=JLEAGUE, expected_title=JLEAGUE_TITLE)


def verify():
    capture = read(HERE/'captures.json')
    if capture['version'] != 'WCPP-J1-PUBLIC-FIRST-ARCHIVE-1':
        raise ValueError('unexpected public capture version')
    created, checked, finished = github_times(capture['github'])
    entries = read(STAGE/'entries.json')
    message = (STAGE/'message.txt').read_text(encoding='utf-8')
    plan, fixtures, identity = display_windows.prepared_batch(REGISTRATION, 'nov28_29', entries, message, STAGE)
    batch = ledger._read(STAGE, read(STAGE/'publication.json'))
    display_at = aware(batch['recorded_at'])
    first = min(aware(fixture['kickoff_at']) for fixture in fixtures)
    if (plan['freeze_id'] != PLAN_ID or batch['freeze_id'] != STAGE_ID
            or batch['payload']['identity'] != identity
            or batch['payload']['fixtures'] != {fixture['match_id']: fixture for fixture in fixtures}
            or not aware(plan['recorded_at']) <= display_at <= created <= checked <= finished < first):
        raise ValueError('the public proof does not bind the full original pregame freeze')
    observed = readback(capture['public_files'], entries, finished, first)
    scorecard(message, identity, entries, display_at)
    return dict(scope='Original J1 public GitHub pregame archive', original_commit=COMMIT,
                publication_freeze=batch['freeze_id'], published_job=capture['github']['job']['html_url'],
                verified_on_service_at=checked.astimezone(BEIJING).isoformat(),
                public_readback_at=observed.astimezone(BEIJING).isoformat(),
                first_scheduled_kickoff=first.astimezone(BEIJING).isoformat(), files_verified=len(capture['public_files']),
                fixtures=len(fixtures), ordered_score_count=3*len(fixtures), selected=identity['selected'],
                original_body_sha256=identity['body_sha256'], independent_chat_first_delivery='UNVERIFIED',
                official_calendar=official_schedule(fixtures))


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
