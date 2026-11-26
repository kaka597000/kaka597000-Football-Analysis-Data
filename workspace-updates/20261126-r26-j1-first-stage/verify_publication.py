"""Replay the original J1 second-window freeze using the inherited first-display contract."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from research.analysis_freeze import aware
from research_program import display_windows as windows, goal_state_forward as ledger
from research_program.display_window_review import _batch_text_audit, _quote_source
from research_program.future_validation import quote_audit


ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / '20261125-j1-stage-windows'
SCHEDULE = ROOT / 'next-window'
SECOND = ROOT / 'nov28_29'
EVIDENCE = ROOT / 'evidence'


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify_captures():
    groups = (('summary-manifest.json', ''), ('next-supplementary-manifest.json', 'extra-calendar/'))
    with tarfile.open(EVIDENCE / 'public-source-snapshots.tar.gz') as archive:
        for name, prefix in groups:
            for item in read(EVIDENCE / name):
                member = prefix + item['raw_file']
                content = archive.extractfile(member).read()
                if sha256(content).hexdigest() != item['sha256'] or len(content) != item['bytes']:
                    raise ValueError('raw response differs: ' + member)


def verify():
    verify_captures()
    entries = read(SECOND / 'entries.json')
    message = (SECOND / 'message.txt').read_text(encoding='utf-8')
    _, fixtures, expected = windows.prepared_batch(PRIOR / 'registration', 'nov28_29', entries, message, SECOND)
    batch = ledger._read(SECOND, read(SECOND / 'publication.json'))
    if (batch['payload']['identity'] != expected or len(fixtures) != 10 or len(expected['selected']) != 3
            or aware(batch['recorded_at']) >= min(aware(f['kickoff_at']) for f in fixtures)):
        raise ValueError('first-display freeze differs from the original full slate')
    cache, authors = {}, {}
    for mid, slot in entries.items():
        forecast = ledger._read(SECOND, slot['authored'])
        authors[mid] = forecast
        fixture, payload = forecast['fixture'], forecast['payload']
        quote = fixture['total_quote']
        for name, expected_hash in payload['evidence_files'].items():
            if digest(EVIDENCE / name) != expected_hash:
                raise ValueError('evidence input changed: ' + name)
        verified, reason, market_clock = _quote_source(quote, fixture, EVIDENCE, cache,
                                                       payload['market_snapshot']['h2h'])
        if (not verified or reason or market_clock is not None or quote_audit(fixture)['eligible']
                or payload['total_direction'] is not None or not forecast['selection_audit']['top3_ready']):
            raise ValueError('observed-only quote or analyst score comparison differs: ' + mid)
    if not _batch_text_audit(message, expected, authors)['original_blocks_present_once_in_order']:
        raise ValueError('unchanged chronological message is not bound to every first issue')

    next_plan = ledger._read(SCHEDULE, read(SCHEDULE / 'plan.json'))
    sources = next_plan['payload']['identity']
    if (sources['schedule_sha256'] != digest(EVIDENCE / 'full-window-calendar.json')
            or sources['current_calendar_capture_manifest_sha256'] != digest(EVIDENCE / 'calendar-manifest.json')
            or sources['supplementary_manifest_sha256'] != digest(EVIDENCE / 'next-supplementary-manifest.json')):
        raise ValueError('next window source digest differs')
    normalized = read(EVIDENCE / 'full-window-calendar.json')['events']
    checked = {'espn:' + r['event_id']: ('espn:' + r['home_id'], 'espn:' + r['away_id'], aware(r['kickoff_beijing']))
               for r in normalized}
    stored = {mid: (f['home'], f['away'], aware(f['kickoff_at']))
              for mid, f in next_plan['payload']['fixtures'].items()}
    if (len(stored) != 10 or stored != checked or aware(next_plan['recorded_at']) >= min(x[2] for x in stored.values())):
        raise ValueError('next calendar registration differs')
    print(json.dumps(dict(first_scores=len(entries), distinct_scores=3 * len(entries), selected=expected['selected'],
                          strict_total_quotes=0, next_window_fixtures=len(stored),
                          earliest_next_kickoff=min(x[2] for x in stored.values()).astimezone(timezone.utc).isoformat())))


if __name__ == '__main__':
    verify()
