"""Rebuild the original first-window teams, previous match XIs, xG and named bookmaker observations."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parent


def read(file):
    return json.loads(file.read_bytes())


def main():
    plan = ROOT.parent / 'registration'
    data = read(plan / read(plan / 'plan.json')['file'])['payload']
    first = data['identity']['slates']['nov27_dec01']
    expected = {mid.rsplit(':', 1)[1]: data['fixtures'][mid] for mid in first}
    with TemporaryDirectory() as tmp:
        dest = Path(tmp)
        with tarfile.open(ROOT / 'sources.tar.gz') as archive:
            archive.extractall(dest, filter='data')
        for line in (dest / 'SHA256SUMS.txt').read_text().splitlines():
            fingerprint, name = line.split(maxsplit=1)
            file = (dest / name).resolve()
            if not file.is_relative_to(dest) or sha256(file.read_bytes()).hexdigest() != fingerprint:
                raise ValueError('EPL source checksum differs: ' + name)
        tables = ['current-espn-odds.csv', 'current-espn-odds.json', 'source-index.csv', 'source-index.json']
        capture = {name: (dest / name).read_bytes() for name in tables}
        subprocess.run([sys.executable, '-B', str(dest / 'rebuild_index.py')], cwd=dest, check=True)
        if any((dest / name).read_bytes() != value for name, value in capture.items()):
            raise ValueError('EPL raw evidence does not reconstruct its original indexed values')
        teams = read(dest / 'source-index.json')
        if (set(expected) != {str(r['target_event_id']) for r in teams['rows']} or len(teams['rows']) != 20
                or any(r['team_espn_id'] != expected[str(r['target_event_id'])][r['target_side']] for r in teams['rows'])):
            raise ValueError('indexed prior teams or target population differs from registered EPL calendar')
        odds = read(dest / 'current-espn-odds.json')
        if len(odds['rows']) != 10 or len({str(r['event_id']) for r in odds['rows']} & expected.keys()) != 10:
            raise ValueError('observed bookmaker row does not cover each registered fixture')
        print(json.dumps({'team_coverage': teams['coverage'], 'observed_market_coverage': odds['coverage']}))


if __name__ == '__main__':
    main()
