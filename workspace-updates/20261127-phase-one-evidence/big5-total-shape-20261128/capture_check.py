"""Check result-capture schedules and exact response-byte handling offline."""

from datetime import timedelta
import gzip
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from unittest.mock import patch

from capture_weekend import collect, fetch, fotmob_validation_view, plan
from research.analysis_freeze import aware
from result_evidence import retained
from settlement import load_window, locked_bindings, read
from settlement_additions import verified_window_results
from v2_test.data_contract import safe_content


def confirm(bundle):
    fixtures = load_window(bundle, locked_bindings(bundle))
    mid = 'espn:401882796'
    earliest = aware(fixtures[mid]['kickoff_at'])
    before, pending = plan(fixtures, [mid], 'kickoff', earliest - timedelta(seconds=1))
    opening, _ = plan(fixtures, [mid], 'kickoff', earliest)
    final, _ = plan(fixtures, [mid], 'full-time', earliest + timedelta(minutes=90))
    if before or not pending or [row['provider'] for row in opening] != ['espn'] or [
            row['provider'] for row in final] != ['espn', 'fotmob']:
        raise ValueError('capture planner changed the phase-specific endpoints or its dates')
    if plan(fixtures, [mid], 'full-time', earliest + timedelta(minutes=89))[0]:
        raise ValueError('result capture became eligible before 90 minutes')

    root = bundle / 'settlement-check'
    reference = read(root / 'morning-reference.json')
    morning = reference['fixtures']
    previous = read(root / 'morning-receipts.json')
    samples = {(row['match_id'], row['provider']): row for row in previous}
    sample = samples[('espn:401884720', 'espn')]
    raw = gzip.decompress((root / sample['path']).read_bytes())
    at = aware(reference['as_of'])
    only = verified_window_results(morning, root, [sample], at)[sample['match_id']]
    if only['actual'] is not None or not only['actual_kickoff_at'] or not only['final_receipts']:
        raise ValueError('a single score provider must remain pending while retaining its start and raw score')

    class Response(io.BytesIO):
        status = 200

    class ReplayOpener:
        def open(self, request, *, timeout):
            if request.full_url != sample['source_url'] or timeout <= 0:
                raise ValueError('test request changed the real archived URL')
            return Response(raw)

    with TemporaryDirectory(prefix='big5-capture-check-') as temp:
        output = Path(temp)
        with patch('capture_weekend.build_opener', return_value=ReplayOpener()):
            meta = fetch({'source_url': sample['source_url']}, output / 'exact.json')
        rebuilt, captured = retained(output, dict(meta, path='exact.json'), aware(meta['captured_at']))
        if rebuilt != raw or meta['sha256'] != sample['sha256'] or aware(meta['requested_at']) > captured:
            raise ValueError('public capture altered original bytes or data clocks')
        sample = samples[('espn:401884720', 'fotmob')]
        raw = gzip.decompress((root / sample['path']).read_bytes())
        with patch('capture_weekend.build_opener', return_value=ReplayOpener()):
            fotmob = fetch({'source_url': sample['source_url']}, output / 'fotmob.json')
        if fotmob['sha256'] != sample['sha256'] or (output / 'fotmob.json').read_bytes() != raw:
            raise ValueError('public stat labels changed the FotMob response bytes')
        # A sensitive field outside the explicitly documented stat descriptors still fails.
        try:
            safe_content(fotmob_validation_view({'content': {'stats': {'token': 'test'}}}))
        except ValueError:
            pass
        else:
            raise ValueError('credential field accepted while validating public stat labels')

        calls = []

        def provider_denied(act, file):
            provider, match = act['provider'], act['match_id']
            calls.append((provider, match))
            if provider == 'espn':
                raise HTTPError(act['source_url'], 429, 'mocked rate limit', None, None)
            earlier = samples[(match, provider)]
            file.write_bytes(gzip.decompress((root / earlier['path']).read_bytes()))
            return {key: earlier[key] for key in ('http_status', 'sha256', 'requested_at', 'captured_at')}

        old_matches = ['espn:401884720', 'espn:401875004']
        with patch('capture_weekend.sleep'):
            result = collect(morning, old_matches, 'full-time', output / 'rehearsal', output, fetcher=provider_denied)
        if calls != [('espn', old_matches[0]), ('fotmob', old_matches[0]), ('fotmob', old_matches[1])]:
            raise ValueError('a provider received another request after rejection')
        if result['responses'] != 2 or len(result['failures']) != 2:
            raise ValueError('the other provider lost successful responses')
        captured = output / 'rehearsal'
        receipts = read(captured / 'receipts.json')
        if any(not row['path'].startswith('rehearsal/') or not (output / row['path']).is_file()
               for row in receipts):
            raise ValueError('individually retained receipts escaped the shared evidence root')


if __name__ == '__main__':
    confirm(Path(__file__).resolve().parent)
