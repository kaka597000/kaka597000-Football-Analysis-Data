"""Rebuild the German first-window quote times and intervening games from the team's source calendars."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tarfile
from urllib.parse import parse_qs, urlsplit


HERE = Path(__file__).resolve().parent
BEIJING = timezone(timedelta(hours=8))
WINDOW = 'nov27_dec04'


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('timezone required for the calendar or source clock')
    return result


def csv_bytes(rows):
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def rebuild():
    registration = HERE.parent/'registration'
    receipt = json.loads((registration/'plan.json').read_bytes())
    plan = json.loads((registration/receipt['file']).read_bytes())
    digest = plan.pop('record_sha256')
    encoded = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if sha256(encoded).hexdigest() != digest or digest != receipt['sha256']:
        raise ValueError('original Bundesliga window registration differs')
    identity = plan['payload']['identity']
    ids = identity['slates'][WINDOW]
    with (HERE.parents[1]/'data/leagues/ger.1.csv').open(encoding='utf-8', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['match_id'] in ids]
    catalog = {r['match_id']: r for r in rows}
    if set(catalog) != set(ids) or len(rows) != len(ids):
        raise ValueError('original ESPN/FotMob mapping does not cover the window')
    checks, before = [], []
    with tarfile.open(HERE/'team-calendars.tar.gz') as archive:
        expected = set()
        for mid in ids:
            fx = plan['payload']['fixtures'][mid]
            row = catalog[mid]
            ko = stamp(fx['kickoff_at'])
            if (ko != stamp(row['kickoff_at']) or fx['cohort'] != 'ger.1' or fx['stage'] != 'regular'
                    or any(fx[side] != row[side+'_espn_id'] for side in ('home','away'))):
                raise ValueError('different registered fixture ' + mid)
            at_start = len(before)
            for side in ('home', 'away'):
                team = row[side+'_fotmob_id'].split(':')[-1]
                meta_path = 'sources/fotmob-team-' + team + '.json'
                meta = json.load(archive.extractfile(meta_path))
                raw_path = 'raw/' + meta['sha256'] + '.gz'
                expected.update((meta_path, raw_path))
                raw = gzip.decompress(archive.extractfile(raw_path).read())
                url = urlsplit(meta['url'])
                seen = stamp(meta['received_utc'])
                if (meta['http_status'] != 200 or meta['raw_path'] != raw_path or meta['bytes'] != len(raw)
                        or sha256(raw).hexdigest() != meta['sha256'] or url.hostname != 'www.fotmob.com'
                        or parse_qs(url.query).get('id') != [team] or not stamp(meta['requested_utc']) <= seen < ko):
                    raise ValueError('different team source, timestamp or payload')
                source = json.loads(raw)
                if str(source['details']['id']) != team or source['details']['primaryLeagueId'] != 54:
                    raise ValueError('calendar belongs to another team or domestic league')
                events = source['fixtures']['allFixtures']['fixtures']
                target, = [e for e in events if str(e['id']) == row['fotmob_match_id'].split(':')[-1]]
                if (stamp(target['status']['utcTime']) != ko or str(target[side]['id']) != team
                        or target['tournament']['leagueId'] != 54 or target['status'].get('started')):
                    raise ValueError('target did not match the original calendar')
                if len({e['id'] for e in events}) != len(events):
                    raise ValueError('duplicate event on a team calendar')
                for e in events:
                    status = e['status']
                    kickoff = stamp(status['utcTime'])
                    if (not seen < kickoff < ko or 'friendl' in e['tournament']['name'].lower()
                            or any(status.get(k) for k in ('finished', 'awarded', 'cancelled'))):
                        continue
                    if team not in (str(e['home']['id']),str(e['away']['id'])):
                        raise ValueError('intervening fixture belongs to another club')
                    before.append(dict(target=mid, club=target[side]['name'], event='fotmob:'+str(e['id']),
                        competition=e['tournament']['name'], home=e['home']['name'], away=e['away']['name'],
                        kickoff_bjt=kickoff.astimezone(BEIJING).isoformat(), observed_utc=meta['received_utc'],
                        calendar_sha256=meta['sha256']))
            checks.append(dict(match_id=mid, home=row['home_name'], away=row['away_name'],
                kickoff_bjt=ko.astimezone(BEIJING).isoformat(), quote_24h_bjt=(ko-timedelta(hours=24)).astimezone(BEIJING).isoformat(),
                quote_1h_bjt=(ko-timedelta(hours=1)).astimezone(BEIJING).isoformat(), intervening_club_events=len(before)-at_start))
        if len(archive.getnames()) != len(expected) or set(archive.getnames()) != expected:
            raise ValueError('unexpected or missing calendar evidence')
    return {'quote-times.csv': csv_bytes(checks), 'intervening-competitions.csv': csv_bytes(before)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-new', action='store_true')
    args = parser.parse_args()
    for name, content in rebuild().items():
        path = HERE/name
        if args.write_new and not path.exists():
            with path.open('xb') as file:
                file.write(content)
        if path.read_bytes() != content:
            raise ValueError('recomputed calendar table differs: ' + name)
    print('Verified German first-window quote dates and intervening club fixtures.')
