"""Verify the pinned public GitHub archive against the original score-table freezes."""

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
REPO = 'kaka597000/kaka597000-Football-Analysis-Data'
COMMIT = 'ffe6332aac82ca9886d7cc975c0665eba5bff880'
ARCHIVE = 'workspace-updates/20261126-europe-first-display'
PROOFS = {
    'uecl': ('8e35292cbf95d2be-v000001', '323527b7ba98c727-v000001'),
    'uel': ('8e5d77aa065390d2-v000001', '56d1e48eafbc04d2-v000001'),
}
TABLE = 'publication/score-tables.md'
SCORECARD = 'publication/scorecard.json'
CHECKSUMS = 'SHA256SUMS'


def check(condition, message):
    if not condition:
        raise ValueError(message)


def time(value):
    stamp = datetime.fromisoformat(value)
    check(stamp.tzinfo is not None, 'time requires a zone offset')
    return stamp


def beijing(stamp):
    return stamp.astimezone(ZoneInfo('Asia/Shanghai')).isoformat()


def check_files(captures, folder):
    originals = {TABLE, SCORECARD, CHECKSUMS}
    for plan, display in PROOFS.values():
        originals.update((f'registration/{plan}.json', f'publication/{display}.json'))
    check(captures.keys() == originals, 'public capture inventory differs')
    expected_prefix = f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{ARCHIVE}/'
    original_checksums = (folder / 'commit-SHA256SUMS').read_text(encoding='utf-8')
    members = dict((path.removeprefix('./'), digest)
                   for digest, path in (line.split('  ', 1) for line in original_checksums.splitlines()))
    for relative, evidence in captures.items():
        path = folder / 'commit-SHA256SUMS' if relative == CHECKSUMS else folder.parent / relative
        digest = sha256(path.read_bytes()).hexdigest()
        check((evidence['url'], evidence['status'], evidence['sha256'], evidence['bytes'])
              == (expected_prefix + relative, 200, digest, path.stat().st_size),
              'public response differs from the pinned local archive: ' + relative)
        if relative != CHECKSUMS:
            check(members.get(relative) == digest, 'file differs from original PR checksum: ' + relative)


def audit(folder=HERE):
    observations = json.loads((folder / 'captures.json').read_bytes())
    check(observations['version'] == 'WCPP-EUROPE-PUBLIC-ARCHIVE-1', 'unexpected evidence version')
    pull, run, job = (observations['github'][key] for key in ('pull', 'run', 'job'))
    captures = observations['public_files']
    check_files(captures, folder)
    check(pull['number'] == 77 and pull['head']['sha'] == run['head_sha'] == job['head_sha'] == COMMIT
          and pull['base']['repository'] == run['repository']['full_name'] == REPO
          and pull['base']['private'] is False and run['repository']['private'] is False
          and run['event'] == 'pull_request' and run['head_branch'] == pull['head']['ref']
          and run['pull_requests'] == [{'number': pull['number'], 'head': pull['head']}]
          and run['id'] == job['run_id'] == 45776048930 and job['id'] == 139759841996
          and run['path'] == '.github/workflows/europe-first-display.yml'
          and (run['status'], run['conclusion'], job['status'], job['conclusion'])
          == ('completed', 'success', 'completed', 'success')
          and any(step == {'name': 'Verify both competition windows and their original score tables',
                           'status': 'completed', 'conclusion': 'success'} for step in job['steps']),
          'GitHub service did not attest the original public commit')
    creation, triggered, started, complete = [time(value) for value in (
        pull['created_at'], run['created_at'], job['started_at'], job['completed_at'])]
    check(creation <= triggered <= started <= complete, 'GitHub service times are out of order')
    scorecard = json.loads((folder.parent / SCORECARD).read_bytes())
    competitions = {}
    deadlines = []
    for short, (plan_id, publication_id) in PROOFS.items():
        registration = json.loads((folder.parent / f'registration/{plan_id}.json').read_bytes())
        published = json.loads((folder.parent / f'publication/{publication_id}.json').read_bytes())
        rows = scorecard[short]['rows']
        by_id = {row['fixture']['match_id']: row['fixture'] for row in rows}
        earliest = min(time(row['fixture']['kickoff_at']) for row in rows)
        deadlines.append(earliest)
        signed = published['payload']['identity']
        registered = registration['payload']['identity']['windows']['round1']['ids']
        seats = sorted((row['rank'], row['fixture']['match_id']) for row in rows if row['rank'] is not None)
        check(len(rows) == len(by_id) == len(registered) == 18 and set(registered) == by_id.keys()
              and published['payload']['fixtures'] == by_id
              and signed['window'] == registration['record_sha256'] == scorecard[short]['window']['sha256']
              and signed['scorecard_sha256'] == captures[SCORECARD]['sha256']
              and signed['displayed_table_sha256'] == captures[TABLE]['sha256']
              and [rank for rank, _ in seats] == [1, 2, 3] and signed['selected'] == [mid for _, mid in seats]
              and time(registration['recorded_at']) <= time(published['recorded_at']) <= creation <= complete < earliest,
              'public archive differs from the registered pregame population: ' + short)
        competitions[short] = dict(fixtures=len(by_id), scheduled_first_kickoff=beijing(earliest),
                                   registration_id=plan_id, publication_freeze_id=publication_id,
                                   selected_fixture_ids=signed['selected'])
    observed = [time(metadata['observed_at']) for metadata in captures.values()]
    check(complete <= min(observed) <= max(observed) < min(deadlines), 'readback is outside its recorded pregame window')
    return dict(scope='Pinned public GitHub pregame archive', original_commit=COMMIT, pull=pull['html_url'],
                run=run['html_url'], public_job_confirmed_at=beijing(complete),
                publicly_read_back_by=beijing(max(observed)), files_verified=len(captures),
                score_table_sha256=captures[TABLE]['sha256'], scorecard_sha256=captures[SCORECARD]['sha256'],
                independent_chat_first_delivery='UNVERIFIED', competitions=competitions)


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
