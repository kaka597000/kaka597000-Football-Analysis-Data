"""Reproduce the paired J1 chance-creation rows from their original local responses."""

import argparse
from datetime import datetime, timedelta
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import tarfile


HERE = Path(__file__).resolve().parent
R5 = HERE.parents[1] / '20261123-all-scope-kpi'
PANEL_SHA = 'b9c883ee9055b0e562e8ad5b482a26dab219d1c0d6bd76ae0c16f74a42f23edb'
ESPN_SHA = 'c986c90b61ed364a403ebf2ead6fee34ab9e0a45e626ef0de7fd3633a4003d80'
STAT_KEYS = ('expected_goals', 'total_shots', 'ShotsOnTarget')
SIDES = ('home', 'away')
ALIASES = {
    'JEF United Chiba': 'JEF United Ichihara-Chiba',
    'Yokohama F.Marinos': 'Yokohama F. Marinos',
    'Yokohama F Marinos': 'Yokohama F. Marinos',
    'Tokyo Verdy': 'Tokyo Verdy 1969',
    'Fagiano Okayama FC': 'Fagiano Okayama',
    'Kyoto Sanga FC': 'Kyoto Sanga',
}


def digest(body):
    return sha256(body).hexdigest()


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError('timezone required for retained evidence')
    return stamp


def original_results():
    path = R5 / 'models/jpn.1.tar.gz'
    if digest(path.read_bytes()) != PANEL_SHA:
        raise ValueError('the registered J1 panel changed')
    with tarfile.open(path) as packed:
        result = {row['id']: row for line in packed.extractfile('panel.jsonl') if (row := json.loads(line))['season']
                  == '2026-27' and row['stage'] == 'regular' and row['score_basis'] == 'regulation_90'}
    archive = R5 / 'evidence'
    ref = json.loads((archive / 'source-index.json').read_bytes())[ESPN_SHA]
    with tarfile.open(archive / ref['archive']) as packed:
        body = gzip.decompress(packed.extractfile(ref['member']).read())
    if digest(body) != ESPN_SHA:
        raise ValueError('the registered ESPN result evidence changed')
    board = json.loads(body)
    if [row['slug'] for row in board['leagues']] != ['jpn.1'] or len(result) != 150:
        raise ValueError('the original J1 calendar or population changed')
    return result, {'espn:' + event['id']: event for event in board['events']}


def metadata_objects(value):
    if isinstance(value, dict):
        yield value
        for field in value.values():
            yield from metadata_objects(field)
    elif isinstance(value, list):
        for field in value:
            yield from metadata_objects(field)


def verify_capture(wcpp, receipt):
    path = (wcpp / receipt['manifest_file']).resolve()
    if not path.is_relative_to(wcpp):
        raise ValueError('capture receipt outside the WCPP archive')
    raw = path.read_bytes()
    if digest(raw) != receipt['manifest_sha256']:
        raise ValueError('retained collection manifest differs')
    for item in metadata_objects(json.loads(raw)):
        if (item.get('sha256') == receipt['sha256']
                and (item.get('url') or item.get('final_url')) == receipt['url']
                and receipt['observed_at'] in item.values()):
            return
    raise ValueError('no original collection entry binds this timestamp and response')


def verified_pairs(raw):
    sections = raw['content']['stats']['Periods']['All']['stats']
    pairs = []
    for key in STAT_KEYS:
        candidates = [row.get('rawStats') or [] for section in sections for row in section['stats']
                      if row['key'] == key and row.get('type') != 'title']
        values, = {tuple(stat['value'] for stat in pair) for pair in candidates
                   if len(pair) == 2 and all(isinstance(stat, dict) for stat in pair)}
        if len(values) != 2 or any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in values):
            raise ValueError('invalid bilateral FotMob values')
        pairs.append(values)
    if any(int(shots) != shots or int(on) != on or on > shots for shots, on in zip(*pairs[1:], strict=True)):
        raise ValueError('invalid official shot counts')
    return pairs


def observation(wcpp, reference, result, event):
    path = (wcpp / reference['archive_file']).resolve()
    if not path.is_relative_to(wcpp):
        raise ValueError('source path must stay in the restored WCPP archive')
    body = path.read_bytes()
    if digest(body) != reference['sha256']:
        raise ValueError('FotMob raw response differs')
    raw = json.loads(body)
    general, header = raw['general'], raw['header']
    id_, status = reference['fotmob_id'], header['status']
    scheduled = timestamp(event['date'])
    kickoff = timestamp(general['matchTimeUTCDate'])
    fotmob = [general[side + 'Team'] for side in SIDES]
    names = [ALIASES.get(team['name'], team['name']) for team in fotmob]
    goals = [result[side + '_goals'] for side in SIDES]
    espn_teams = {row['homeAway']: row for row in event['competitions'][0]['competitors']}
    if (str(general['matchId']) != id_ or general['leagueId'] != 937875 or general['parentLeagueId'] != 223
            or general['countryCode'] != 'JPN' or general['gender'] != 'male'
            or event['season']['slug'] != 'regular-season'
            or event['status']['type']['name'] != 'STATUS_FULL_TIME'
            or result['source_sha256'] != ESPN_SHA
            or names != [result[side] for side in SIDES]
            or [espn_teams[side]['team']['displayName'] for side in SIDES] != names
            or [int(espn_teams[side]['score']) for side in SIDES] != goals
            or not general['finished'] or not status['finished'] or status['reason']['short'] != 'FT'
            or status['cancelled'] or status['awarded'] or status['whoLostOnPenalties'] is not None
            or not status['halfs']['gameEnded'] or any(status['halfs'][k] for k in
                ('firstExtraHalfStarted', 'secondExtraHalfStarted'))
            or [team['id'] for team in header['teams']] != [team['id'] for team in fotmob]
            or [team['score'] for team in header['teams']] != goals
            or timestamp(status['utcTime']) != kickoff
            or kickoff.date().isoformat() != result['date'] or scheduled.date() != kickoff.date()):
        raise ValueError('fixture, goals or stage differs for ' + result['id'])
    stamp = None
    if capture := reference['capture']:
        if (capture['sha256'] != reference['sha256'] or capture['url'] != reference['url']
                or timestamp(capture['observed_at']) < max(kickoff, scheduled) + timedelta(minutes=90)):
            raise ValueError('capture time is not bound to the archived final response for ' + result['id'])
        verify_capture(wcpp, capture)
        stamp = capture['observed_at']
    xg, shots, sot = verified_pairs(raw)
    return dict({k: result[k] for k in ('id', 'competition', 'stage', 'date', 'home', 'away',
                                      'home_goals', 'away_goals', 'score_basis')},
                fotmob_id=id_, xg=xg, shots=shots, shots_on_target=sot, observed_at=stamp,
                source_sha256=reference['sha256'], source_url=reference['url'], result_source_sha256=ESPN_SHA,
                fotmob_kickoff_at=kickoff.isoformat(), espn_kickoff_at=scheduled.isoformat())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wcpp', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    panel, espn = original_results()
    references = json.loads((HERE / 'manifest.json').read_bytes())
    outputs = {'observations.jsonl': [], 'alternate.jsonl': []}
    for ref in references:
        outputs[ref['output']].append(observation(args.wcpp.resolve(), ref, panel[ref['id']], espn[ref['id']]))
    args.out.mkdir(parents=True, exist_ok=False)
    for name, rows in outputs.items():
        if len({r['id'] for r in rows}) != len(rows) or len({r['fotmob_id'] for r in rows}) != len(rows):
            raise ValueError('each R5 and FotMob fixture may appear only once per variant')
        with (args.out / name).open('x', encoding='utf-8') as stream:
            for row in sorted(rows, key=lambda r: (r['date'], r['id'])):
                stream.write(json.dumps(row, sort_keys=True) + '\n')
