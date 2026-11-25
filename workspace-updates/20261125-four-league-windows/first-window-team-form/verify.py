"""Rebuild the prior-match statistics and current odds from all first-window source observations."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program.goal_state_forward import _read


ROOT = Path(__file__).resolve().parent


def verify():
    firsts = {}
    clubs = set()
    for code in ('esp.1', 'fra.1', 'ger.1', 'ita.1'):
        folder = ROOT.parent / code / 'registration'
        plan = _read(folder, json.loads((folder / 'plan.json').read_bytes()))['payload']
        for mid in plan['identity']['slates']['nov27_dec04']:
            fixture = plan['fixtures'][mid]
            firsts[mid] = fixture
            clubs.update((code, fixture[side]) for side in ('home', 'away'))
    with TemporaryDirectory() as temp:
        root = Path(temp)
        with tarfile.open(ROOT / 'sources.tar.gz') as archive:
            for member in archive.getmembers():
                if (not (member.isdir() or member.isfile()) or not Path(member.name).is_relative_to('europe-stage-team-intake-20261125')
                        or '..' in Path(member.name).parts):
                    raise ValueError('unexpected package member')
            archive.extractall(root, filter='data')
        package = root / 'europe-stage-team-intake-20261125'
        def inventory():
            return {p.relative_to(package).as_posix(): sha256(p.read_bytes()).hexdigest()
                    for p in package.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt'}
        checked = {}
        for line in (package / 'SHA256SUMS.txt').read_text().splitlines():
            value, name = line.split(maxsplit=1)
            checked[Path(name).as_posix()] = value
        if inventory() != checked:
            raise ValueError('raw response, time receipt or team evidence digest differs')
        targets = [json.loads(line) for line in (package / 'inputs/first-window-40.jsonl').read_text().splitlines()]
        if len(targets) != len(firsts) or {'espn:' + row['espn_source_match_id'] for row in targets} != set(firsts):
            raise ValueError('team form and registered window cover different fixtures')
        for target in targets:
            fixture = firsts['espn:' + target['espn_source_match_id']]
            if (target['competition'] != fixture['cohort'] or aware(target['kickoff_utc']) != aware(fixture['kickoff_at'])
                    or any('espn:' + target['espn_' + side + '_id'] != fixture[side] for side in ('home', 'away'))):
                raise ValueError('target team or kickoff differs from registration')
        subprocess.run([sys.executable, '-B', str(package / 'build_team_evidence.py')], cwd=package,
                       check=True, stdout=subprocess.DEVNULL)
        if inventory() != checked:
            raise ValueError('independent reconstruction differs from archived per-team statistics or odds')
        index = json.loads((package / 'derived/team-recent-match-index.json').read_bytes())
        if {(r['competition'], 'espn:' + str(r['espn_team_id'])) for r in index['rows']} != clubs:
            raise ValueError('latest-match selection misses registered teams')
        return json.loads((package / 'derived/coverage.json').read_bytes())


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False))
