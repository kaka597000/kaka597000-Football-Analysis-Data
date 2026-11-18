"""Read-only replay of the registered Brazil trial using permanently archived inputs."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from unittest.mock import patch

import numpy as np


EXPERIMENT = Path(__file__).resolve().parent
DATA = EXPERIMENT.parents[1]
REGISTRATION_SHA = 'dd2f84afe1d1dad2e2978ccbcd00f8074293f6a40e186d558e17d1f2c4685bc5'
BASELINE_ARCHIVE_SHA = '3f842a58a73eb453d354e8a770c934378785714189c2e73bf190f77596534e49'


def read(path):
    return json.loads(path.read_bytes())


def checked(path, expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('file digest mismatch: ' + str(path))
    return raw


def equal(actual, expected, field):
    """Selections and identifiers are exact; numeric portability allows BLAS roundoff."""
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError('fields differ: ' + field)
        for key in expected:
            equal(actual[key], expected[key], field + '.' + key)
    elif isinstance(expected, list) or type(expected) is float:
        np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-14, err_msg=field)
    elif actual != expected:
        raise ValueError('replay differs: ' + field)


def verify(source):
    sys.path[:0] = [str(source), str(source / 'runtime')]
    from prediction_engine import legacy
    from research.analysis_freeze import aware, digest, verify as verify_freeze
    from research_program import three_arm_forward as capture, three_arm_model as model, three_arm_review as review
    batch = EXPERIMENT / 'batch'
    protocol = json.loads(checked(EXPERIMENT / 'registration/protocol.json', REGISTRATION_SHA))
    plan, _, captures = review._predictions(batch)
    binding = plan['payload']['binding']
    if binding['registration_sha256'] != REGISTRATION_SHA or plan['payload']['registration_sha256'] != REGISTRATION_SHA:
        raise ValueError('freeze differs from the committed registration')
    checked(source / 'runtime/research_program/three_arm_forward.py', binding['capture_source_sha256'])
    checked(source / 'runtime/research_program/three_arm_model.py', binding['model_source_sha256'])
    checked(source / 'runtime/automation/market_snapshot.py', binding['market_builder_sha256'])
    artifact = json.loads(checked(EXPERIMENT / 'training/artifact.json', binding['artifact_sha256']))
    registry = json.loads(checked(DATA / 'future/bundle-v2/objects' / binding['registry_sha256'], binding['registry_sha256']))
    route = registry['models']['bra.1']
    if registry['status'] != 'ACTIVE_RESEARCH' or route.get('current_engine', 'legacy_weighted_anchor') != 'legacy_weighted_anchor':
        raise ValueError('unexpected original Current route')
    archive = DATA / 'workspace-updates/20261115-remaining-nations-brazil/remaining-evidence.tar.gz'
    checked(archive, BASELINE_ARCHIVE_SHA)
    member = 'WCPP/models/weighted-20261012/bra.1/artifact.json'
    with tarfile.open(archive) as tf:
        baseline = tf.extractfile(member).read()
    if route['artifact_sha256'] != hashlib.sha256(baseline).hexdigest() or not route['artifact_path'].endswith('/' + member):
        raise ValueError('baseline archive member differs from active routing')
    native_artifact = json.loads(baseline)['anchor']
    board = DATA / protocol['scoreboard_source']
    checked(board, protocol['scoreboard_sha256'])
    channel = board.parent
    checked(channel / 'market-channel.json', binding['channel_sha256'])
    cutoff = plan['fixture']['cutoff_at']
    fixtures, markets, sources = capture.batch_inputs(channel, EXPERIMENT / 'identity', binding['competition'], cutoff)
    capture.verify_registration(protocol, fixtures, cutoff)
    if (fixtures != plan['payload']['fixtures'] or markets != plan['payload']['markets']
            or sources != plan['payload']['sources'] or set(markets) != set(captures)):
        raise ValueError('frozen population or quotes differ from retained provider bytes')
    if len(fixtures) != 6 or not all(markets.values()):
        raise ValueError('expected six quoted Brazil fixtures')
    for fixture in fixtures:
        mid = fixture['match_id']
        freeze = captures[mid]
        payload = freeze['payload']
        if set(payload['arms']) != set(capture.ARMS) or payload['status'] != 'FROZEN_WITH_MARKET':
            raise ValueError('incomplete trial for ' + mid)
        native = payload['native_current']
        if native['artifact_sha256'] != route['artifact_sha256'] or native['matrix_sha256'] != payload['arms']['current']['matrix_sha256']:
            raise ValueError('Current model identity mismatch: ' + mid)
        checked(source / 'runtime/v5/weighted_model.py', native['engine_sha256'])
        quote = markets[mid]
        input_fixture = dict(fixture, total_quote=capture.total_quote(quote))
        # Reproduce the existing verified first issue offline, including the native
        # engine's prematch checks at its proven issuance time. No freeze is written.
        issue = aware(freeze['recorded_at'])
        class OriginalIssueClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return issue.astimezone(tz)
        with patch.object(legacy, 'datetime', OriginalIssueClock):
            original = legacy.predict(native_artifact, input_fixture)
        for field, source_field in (('version', 'version'), ('primary', 'primary'), ('wdl', 'wdl_reference'), ('total', 'total')):
            equal(original[source_field], native[field], mid + '.native.' + field)
        estimates = model.apply(artifact, original['matrix'], quote, cohort=fixture['cohort'], cutoff_at=cutoff)
        for arm in capture.ARMS:
            frozen = payload['arms'][arm]
            equal(estimates[arm], frozen['matrix'], mid + '.' + arm + '.matrix')
            selections = model.score_picks(estimates[arm], line=quote['total']['line'])
            equal(selections, {k: v for k, v in frozen.items() if k not in ('matrix', 'matrix_sha256')}, mid + '.' + arm)
    independent = verify_freeze(read(batch / 'comprehensive-decisions.json'))
    manual = independent['payload']
    blind = json.loads(checked(EXPERIMENT / 'registration/comprehensive-blind-picks.json',
                               manual['blind_preselection_file_sha256']))
    original_choices = {r['match_id']: r['selected_primary'] for r in blind['rows']}
    issued_choices = {r['match_id']: r['selected_primary'] for r in manual['rows']}
    if (manual['plan_sha256'] != plan['record_sha256'] or manual['formal_kpi_eligible'] is not False
            or blind['registration_sha256'] != REGISTRATION_SHA or aware(blind['recorded_at']) >= aware(cutoff)
            or blind['record_sha256'] != '40f77f9906094539a174ae5b2713b3b309ffa468609d72e4874ab469350c5e34'
            or digest({k: v for k, v in blind.items() if k != 'record_sha256'}) != blind['record_sha256']
            or set(original_choices) != set(captures) or issued_choices != original_choices
            or any(r['score_freeze_sha256'] != captures[r['match_id']]['record_sha256'] for r in manual['rows'])):
        raise ValueError('independent scores differ from the preselected scores or original model issues')
    return {'registered': len(fixtures), 'source_verified_markets': sum(bool(q) for q in markets.values()),
            'native_current_replays': len(captures), 'research_matrix_and_pick_replays': 3 * len(captures),
            'plan_sha256': plan['record_sha256'], 'artifact_sha256': binding['artifact_sha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.source.resolve()), indent=2))
