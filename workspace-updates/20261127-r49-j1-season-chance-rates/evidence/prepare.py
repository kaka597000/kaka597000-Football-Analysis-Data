"""Verify the three Football LAB J1 team tables and their regulation-score scopes."""

import argparse
from collections import defaultdict
from csv import DictReader
from datetime import date, datetime
import gzip
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import tarfile
from unicodedata import normalize


HERE = Path(__file__).resolve().parent
ARCHIVES = HERE.parents[1]
PANEL_SHA256 = 'b9c883ee9055b0e562e8ad5b482a26dab219d1c0d6bd76ae0c16f74a42f23edb'
NOV25_SHA256 = '7b6c00e87ebff4b27ff8e1083cadec566d503d86d3f925757aefe0868f7a286a'
IDENTITY_SHA256 = '885adf5aeae53271c527272edfdbc7399b85435fc5a62ef331350ae1cc5d0341'
TEAMS_SHA256 = '73d93c317001a4695dc17ff357b33f37ac93e2ce0d91a531bf24c96ae80b8d24'
SIDES = ('home', 'away')
TABLE_NAMES = ('ゴール期待値', '被ゴール期待値')


def checked(path, digest):
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError('the retained source differs: ' + path.name)
    return body


def japanese(name):
    return normalize('NFKC', name).strip()


def identities():
    official = ARCHIVES / '20261127-j1-december-evidence/kickoff-packet.json'
    provider = ARCHIVES / '20261127-j1-december-readiness/prepared/team-ids.json'
    bindings = json.loads(checked(official, IDENTITY_SHA256))['binding_record']['payload']['bindings']
    teams = json.loads(checked(provider, TEAMS_SHA256))['jpn.1']
    known = {japanese(row['identity']['names'][side]): teams[row['identity']['fixture'][side]]['espn_name']
             for row in bindings.values() for side in SIDES}
    if len(known) != 20 or len(set(known.values())) != 20:
        raise ValueError('the verified 2026/27 roster must contain twenty teams')
    known.update({japanese('アルビレックス新潟'): 'Albirex Niigata', japanese('湘南ベルマーレ'): 'Shonan Bellmare',
                  japanese('横浜ＦＣ'): 'Yokohama FC'})
    return known


def games():
    file = ARCHIVES / '20261123-all-scope-kpi/models/jpn.1.tar.gz'
    checked(file, PANEL_SHA256)
    with tarfile.open(file) as packed:
        rows = [json.loads(line) for line in packed.extractfile('panel.jsonl')]
    original = [r for r in rows if r['stage'] == 'regular' and r['score_basis'] == 'regulation_90'
                and r['season'] in ('2025', '2026-27')]
    raw = ARCHIVES / '20261125-forward-settlement/nov25/fixtures.csv'
    seven = [r for r in DictReader(checked(raw, NOV25_SHA256).decode().splitlines()) if r['competition'] == 'J1']
    if len(seven) != 7 or any(row['crosscheck'] != 'official_and_espn_ft_agree' for row in seven):
        raise ValueError('the full set of verified November 25 regulation labels is required')
    for row in seven:
        home, away = map(int, row['regulation_score'].split('-'))
        original.append(dict(id=row['id'], date=row['kickoff'][:10], season='2026-27',
                             home=row['home'], away=row['away'], home_goals=home, away_goals=away))
    if len(original) != len({row['id'] for row in original}):
        raise ValueError('duplicate regulation match in the aggregate inputs')
    return original


def read_tables(html, label, updated, roster):
    title = f'<title>リーグサマリー：{label} J1 ゴール期待値 |'
    updated_text, = re.findall(r'<em class="uiDate">(\d{4}\.\d{1,2}\.\d{1,2}) update</em>', html)
    page_day = date(*map(int, updated_text.split('.')))
    if (title not in html or page_day.isoformat() != updated
            or 'ゴール数、被ゴール数はオウンゴールを含んでおりません。' not in html):
        raise ValueError('season, update date or goal attribution note differs')
    tables = []
    for name in TABLE_NAMES:
        _, fragment = html.split(f'<span>{name}</span></h3>', 1)
        table = fragment.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
        entries = {}
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', table, re.S):
            club, = re.findall(r'<span class="dsktp">(.*?)</span>', row)
            xg, goals, *_ = (float(z) for z in re.findall(r'<td class="c">(.*?)</td>', row))
            team = roster[japanese(unescape(club))]
            if team in entries or not 0 <= xg <= 10 or not 0 <= goals <= 10:
                raise ValueError('invalid team expectation or goal table')
            entries[team] = (xg, goals)
        if len(entries) != 20:
            raise ValueError('expected twenty J1 teams in both tables')
        tables.append(entries)
    return tables


def season_snapshot(receipt, all_games, identities_):
    meta = receipt['capture']
    raw = gzip.decompress((HERE / receipt['file']).read_bytes())
    observed = datetime.fromisoformat(meta['received_at_utc'])
    if (meta['http_status'] != 200 or len(raw) != meta['bytes'] or sha256(raw).hexdigest() != meta['sha256']
            or observed.tzinfo is None or date.fromisoformat(receipt['updated']) > observed.date()):
        raise ValueError('source response or collection clock differs')
    created, allowed = read_tables(raw.decode(), receipt['label'], receipt['updated'], identities_)
    selected = [g for g in all_games if g['season'] == receipt['season'] and g['date'] < receipt['before']]
    totals = defaultdict(lambda: [0, 0, 0])
    for game in selected:
        for own, other in (('home', 'away'), ('away', 'home')):
            count = totals[game[own]]
            count[0] += 1
            count[1] += game[own + '_goals']
            count[2] += game[other + '_goals']
    if len(selected) != receipt['fixtures'] or set(totals) != set(created) or set(created) != set(allowed):
        raise ValueError('table does not match the registered season population')
    clubs = {}
    for name, (played, gf, ga) in totals.items():
        xg, source_gf = created[name]
        xga, source_ga = allowed[name]
        source_total = [round(rate * played) for rate in (source_gf, source_ga)]
        if any(abs(count / played - rate) > .00501 or count > actual
               for count, rate, actual in zip(source_total, (source_gf, source_ga), (gf, ga), strict=True)):
            raise ValueError('reported no-own-goal rate is incompatible with the team schedule: ' + name)
        clubs[name] = dict(played=played, xg=[xg, xga], source_goals=[source_gf, source_ga],
                           regulation_goals=[gf, ga], source_goals_recovered=source_total)
    if sum(r['source_goals_recovered'][0] for r in clubs.values()) != sum(
            r['source_goals_recovered'][1] for r in clubs.values()):
        raise ValueError('source league goal counts do not balance')
    return dict(season=receipt['season'], before=receipt['before'], updated=receipt['updated'], fixtures=len(selected),
                captured_at=meta['received_at_utc'], source_url=meta['url'], source_sha256=meta['sha256'], teams=clubs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    receipts = json.loads((HERE / 'captures.json').read_bytes())
    matches, roster = games(), identities()
    snapshots = {key: season_snapshot(ref, matches, roster) for key, ref in receipts.items()}
    with args.out.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(snapshots, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
