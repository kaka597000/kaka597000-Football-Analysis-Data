"""Reconstruct the four first registrations from the source calendars, roadmap and original weights."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import domestic_window_registration as windows
from research_program import goal_state_forward as ledger
from research_program.display_window_review import review
from research_program.kpi_validation import _first
from research_program.r8_score_study import read


ROOT = Path(__file__).resolve().parent
SOURCE = Path(windows.__file__).resolve().parents[2]


def bound_weights(code, registry):
    expected = registry['models'][code]
    models = {}
    for label, prefix in (('Current', ''), ('Test', 'test_')):
        path = ROOT / 'model-evidence' / code / (label.lower() + '.json.gz')
        body = gzip.decompress(path.read_bytes())
        fingerprint = sha256(body).hexdigest()
        if fingerprint != expected[prefix + 'artifact_sha256']:
            raise ValueError('native weights differ for ' + code + ' ' + label)
        models[label] = dict(sha256=fingerprint, version=json.loads(body)['version'],
                             artifact_file=Path(expected[prefix + 'artifact_path']).name)
    return dict(registry_sha256=windows.sha(ROOT / 'model-evidence/registry.json'), native_models=models)


def bound_firsts(code, rows, registered_at, firsts):
    if set(firsts) != set(rows):
        raise ValueError('incomplete earlier-slot inventory')
    previous = 0
    for mid, tracks in firsts.items():
        if set(tracks) != set(windows.TRACKS):
            raise ValueError('incomplete earlier-track inventory')
        for track, ref in tracks.items():
            if ref is None:
                continue
            if ref['file'] != mid[5:] + '-' + track + '.json':
                raise ValueError('unexpected earlier receipt filename')
            rec = _first(read(ROOT / code / 'earlier' / ref['file']), track)
            f = rec['fixture']
            if (ref['sha256'] != rec['record_sha256'] or ref['recorded_at'] != rec['recorded_at']
                    or aware(rec['recorded_at']) > registered_at or aware(rec['recorded_at']) >= aware(f['kickoff_at'])
                    or aware(f['kickoff_at']) != aware(rows[mid]['kickoff_at'])
                    or any(f[k] != rows[mid][k] for k in ('match_id', 'cohort', 'stage', 'home', 'away'))):
                raise ValueError('original receipt, kickoff or match identity differs: ' + mid)
            previous += 1
    return previous


def verify():
    data = ROOT / 'data'
    subprocess.run([sys.executable, '-B', str(data / 'verify_calendars.py')], check=True)
    spec = read(windows.PROTOCOL)
    catalog, proof = data / 'fixtures.json', data / 'source-manifest.json'
    fixtures = read(catalog)
    registry = read(ROOT / 'model-evidence/registry.json')
    goals, scope = SOURCE / 'project-goals.json', SOURCE / 'configs/analysis-scope.json'
    observations = read(proof)['captures']
    last_read = max(aware(e['observed_response_end_utc']) for e in observations)
    if any(aware(e['observed_request_start_utc']) > aware(e['observed_response_end_utc']) for e in observations):
        raise ValueError('invalid calendar observation clock')
    if windows.sha(windows.PROTOCOL) != windows.PROTOCOL_SHA or set(fixtures) != set(spec['competitions']):
        raise ValueError('wrong prespecified protocol or competition population')
    result = {}
    for code in spec['competitions']:
        folder = ROOT / code / 'registration'
        ref = read(folder / 'plan.json')
        record = ledger._read(folder, ref)
        track = code.replace('.', '-') + '-comprehensive-windows-20261125'
        _first(record, track + '-registration')
        registered_at = aware(record['recorded_at'])
        rows = {f['match_id']: f for f in fixtures[code]}
        if not last_read <= registered_at < min(aware(f['kickoff_at']) for f in rows.values()):
            raise ValueError('registration must follow source observation and precede the window')
        batches, minima = windows.slates(code, fixtures[code], spec)
        exceptions = windows.prematch_exceptions(code, fixtures[code], proof)
        firsts = record['payload']['identity']['earlier_firsts']
        prior = bound_firsts(code, rows, registered_at, firsts)
        identity = dict(version=spec['version'], competitions=[code], protocol=spec, protocol_sha256=windows.PROTOCOL_SHA,
                        scope_sha256=windows.sha(scope), goals_sha256=windows.sha(goals),
                        roadmap=read(goals)['research_roadmap_20261124']['stages'], slates=batches, minima=minima,
                        model_inputs=bound_weights(code, registry), earlier_firsts=firsts, unavailable_new_firsts=exceptions,
                        calendar_sha256=windows.sha(catalog), calendar_proof_sha256=windows.sha(proof))
        if record['payload'] != dict(identity=identity, fixtures=rows, track=track):
            raise ValueError('signed calendar, models, coverage or goals differ for ' + code)
        with TemporaryDirectory() as temporary:
            state = Path(temporary)
            initial = review(record, ledger_root=folder.parent, batch_root=folder.parent, result_state=state,
                             evidence_root=state, at=ref['recorded_at'])
        if (initial['combined']['registered_n'] != len(rows) or initial['combined']['pending_n'] != len(rows)
                or len(initial['combined']['phases']) != 4 or initial['combined']['phase_pass']):
            raise ValueError('stage review at registration differs from the source calendar')
        result[code] = dict(windows={k: len(v) for k, v in batches.items()}, unavailable_new_firsts=exceptions,
                            bound_earlier_slots=prior, registered_at=ref['recorded_at'], sha256=ref['sha256'])
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
