"""Validate the actual pregame eligibility snapshot for the ten locked J1 matches."""

import json
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha


ROOT = Path(__file__).resolve().parent
CHECK = ROOT / 'replay/forward-check.json'
TRACK = 'research-r43-j1-first-eligibility'


if __name__ == '__main__':
    record = verify(json.loads((ROOT / 'forward-check-freeze.json').read_bytes()))
    check = json.loads(CHECK.read_bytes())
    identity = 'r43-j1-first-eligibility:' + check['identities_sha256']
    deadline = min(aware(row['kickoff_at']) for row in check['matches'])
    fixture = record['fixture']
    if (record['track'] != TRACK or record['stage'] != 'prematch' or record['revision'] != 1
            or record['evaluation_slot'] != 'FIRST_PREMATCH' or record['previous_sha256'] is not None
            or record['match_id'] != identity or aware(fixture['kickoff_at']) != deadline
            or not aware(check['source_cutoff_at']) <= aware(fixture['cutoff_at']) <= aware(record['recorded_at']) < deadline):
        raise ValueError('eligibility check is outside its registered pregame chronology')
    protocol = ROOT / 'protocol.json'
    payload = dict(version=json.loads(protocol.read_bytes())['version'], registered=10, changed_first=0,
                   protocol_sha256=sha(protocol), forward_check_sha256=sha(CHECK),
                   prospective_eligibility='NO_CHANGED_FIRST', source_cutoff_at=check['source_cutoff_at'])
    rows = check['matches']
    if (record['payload'] != payload or (check['registered'], check['changed_first']) != (10, 0)
            or len(rows) != 10 or len({row['match_id'] for row in rows}) != 10
            or any(row['changed'] or row['r7'] != row['consensus'] for row in rows)):
        raise ValueError('eligibility snapshot differs from the replayed ten frozen source fixtures')
    print(record['freeze_id'])
