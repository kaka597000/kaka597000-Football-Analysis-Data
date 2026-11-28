"""Settle the original weekend with additional local Current/Test firsts."""

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha, write_new
from result_evidence import verify_results
from settlement import DIRECTIONS, first_opening, grade, load_window, locked_bindings, read


def added_firsts(bundle, fixtures):
    root = bundle / 'first-order'
    old = verify(read(bundle / 'weekend-freeze.json'))
    lock = verify(read(root / 'native-firsts-freeze.json'))
    source = root / 'native-firsts.json'
    spec = read(source)
    if (lock['stage'] != 'prematch' or lock['payload']['weekend_freeze_sha256'] != old['record_sha256']
            or lock['payload']['native_firsts_sha256'] != sha(source)
            or lock['payload']['first_pairs'] != len(spec) or spec.keys() - fixtures.keys()):
        raise ValueError('native first references differ from their registered addition')
    additions = first_opening(bundle, fixtures)
    for mid, data in spec.items():
        raw = bundle / data['raw_receipt']
        original = data['receipt']
        if sha(raw) != data['receipt_archive_sha256']:
            raise ValueError('retained pair archive checksum differs')
        record = verify(json.loads(gzip.decompress(raw.read_bytes())))
        fixture, expected = record['fixture'], fixtures[mid]
        if (mid in additions or record['record_sha256'] != original['sha256']
                or record['freeze_id'] != original['freeze_id'] or record['recorded_at'] != original['recorded_at']
                or record['stage'] != 'prematch' or record['track'] != 'current-test-pair' or record['revision'] != 1
                or record['evaluation_slot'] != 'FIRST_PREMATCH' or record['previous_sha256'] is not None
                or any(fixture[k] != expected[k] for k in ('match_id', 'cohort', 'home', 'away'))
                or aware(fixture['kickoff_at']) != aware(expected['kickoff_at'])
                or not aware(fixture['cutoff_at']) <= aware(record['recorded_at'])
                <= aware(lock['recorded_at']) < aware(expected['kickoff_at'])):
            raise ValueError('added Current/Test first differs from fixed fixture or chronology')
        stored_sources = {(item['source_url'], item['sha256'], item['captured_at']) for item in fixture['sources']}
        source_receipts = {(item['source_url'], item['sha256'], item['captured_at']) for item in data['sources']}
        if stored_sources != source_receipts or len(source_receipts) != 2:
            raise ValueError('additional pair source identities differ from its freeze')
        for item in data['sources']:
            path = bundle / item['file']
            if (sha(path) != item['archive_sha256']
                    or sha256(gzip.decompress(path.read_bytes())).hexdigest() != item['sha256']
                    or aware(item['captured_at']) > aware(fixture['cutoff_at'])):
                raise ValueError('additional pair source bytes or cutoff differ')
        arms = {}
        reference = {'freeze_id': record['freeze_id'], 'sha256': record['record_sha256'],
                     'recorded_at': record['recorded_at']}
        for arm, field in (('Current', 'current_model'), ('Test', 'test_model')):
            pick = record['payload'][field]
            frozen = pick['primary'], [item['score'] for item in pick['top3']]
            display = data['arms'][field]
            if ((display['primary'], display['top3']) != frozen or display['status'] != pick['recommendation_status']
                    or display['line_available'] != (pick['total'] is not None)):
                raise ValueError('display values differ from the added original model pair')
            arms[arm] = dict(reference, forecast={'primary': frozen[0], 'top3': frozen[1],
                                                 'wdl': DIRECTIONS.get(pick.get('wdl_direction'))})
        additions[mid] = arms
    return additions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence-root', 'receipts', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--at', required=True)
    args = parser.parse_args()
    at = aware(args.at)
    if at > datetime.now(timezone.utc):
        raise ValueError('review cutoff must be an actual time')
    bundle = Path(__file__).resolve().parent
    lock = verify(read(bundle / 'first-order/native-firsts-freeze.json'))
    if at < aware(lock['recorded_at']):
        raise ValueError('review cutoff predates the registered native first additions')
    fixtures = load_window(bundle, locked_bindings(bundle))
    verified = verify_results(fixtures, args.evidence_root, read(args.receipts), at)
    write_new(args.out, grade(fixtures, verified, added_firsts(bundle, fixtures)))
