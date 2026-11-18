"""Rebuild pre-cutoff Brazilian Serie A score sequences from preserved ESPN responses."""
import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[3]
DAILY = HERE.parents[1] / 'forward/history'
PREVIOUS = DATA / 'workspace-updates/20261118-three-arm'


def stamp(v):
    d = datetime.fromisoformat(v.replace('Z', '+00:00'))
    if not d.tzinfo:
        raise ValueError(v)
    return d.astimezone(timezone.utc)


def raw_bytes(p):
    b = p.read_bytes()
    return gzip.decompress(b) if p.suffix == '.gz' else b


def checked(path, digest):
    b = raw_bytes(path)
    if hashlib.sha256(b).hexdigest() != digest:
        raise ValueError('raw digest mismatch: ' + str(path))
    return json.loads(b)


def goal(x):
    value = x.get('value') if isinstance(x, dict) else x
    number = float(value)
    if not number.is_integer() or number < 0:
        raise ValueError('invalid score')
    return int(number)


def game(mid, ko, home, away, hg, ag):
    prefix = lambda x: 'espn:' + str(x)
    return dict(match_id=prefix(mid), kickoff_at=stamp(ko).isoformat(), home=prefix(home), away=prefix(away),
                home_goals=goal(hg), away_goals=goal(ag))


def league_finals(doc, receipt):
    if receipt.get('kind', '').startswith('fotmob_'):
        for x in receipt['identity_mappings'].values():
            if receipt['kind'] == 'fotmob_daily':
                m, = (m for league in doc['leagues'] if league.get('primaryId') == 268 and league['ccode'] == 'BRA'
                      for m in league['matches'] if str(m['id']) == x['fotmob_id'])
                ft = m['status']
                if not ft['finished'] or ft['reason']['shortKey'] != 'fulltime_short' or ft['periodLength'] != 45:
                    raise ValueError('FotMob daily record is not a regulation FT')
                ko, h, a = ft['utcTime'], m['home'], m['away']
                names, score = [h['name'], a['name']], [h['score'], a['score']]
            else:
                # The two Oct24 source HTTP bodies are missing from the restored staging tree.
                # This archived pre-freeze extraction preserves the provider IDs, timestamps,
                # oriented FT scores and original HTTP-body checksums for both.
                records = [r for match in doc['matches'] if match['competition']['espn_league_code'] == 'bra.1'
                           for side in match['recent_and_schedule'].values() for r in side['recent']
                           if str(r['match_id']) == x['fotmob_id']]
                m = records[0]
                source, = (v for v in doc['manifest'] if v['url'].endswith('?matchId='+x['fotmob_id']))
                if (source['status'] != 200 or len(source['sha256']) != 64 or m['match_detail_status'] != 'FT'
                        or m['extra_time_or_shootout_status'] or m['competition'] != 'Série A'
                        or stamp(source['captured_at']) > stamp(receipt['observed_at'])):
                    raise ValueError('retained match extraction receipt')
                names, ko = [m['home'], m['away']], m['utc']
                score = [m['gf'],m['ga']] if m['venue'] == 'home' else [m['ga'],m['gf']]
                if m['match_detail_scoreStr'] != f'{score[0]} - {score[1]}':
                    raise ValueError('retained FT score orientation')
            if names != [x['home_name'],x['away_name']] or stamp(ko) != stamp(x['kickoff_at']):
                raise ValueError('joint league, oriented name and kickoff mapping')
            yield game(x['match_id'][5:],ko,x['home'][5:],x['away'][5:],*score)
        return
    # Scoreboards cover a single league. Team schedules may mix competitions.
    for e in doc.get('events', []):
        league = e.get('league', {}).get('slug')
        if league is None and len(doc.get('leagues', [])) == 1:
            league = doc['leagues'][0].get('slug')
        if league != 'bra.1':
            continue
        c = e['competitions'][0]
        status = c['status']
        if status['type']['name'] != 'STATUS_FULL_TIME' or not status['type']['completed'] or status.get('period', 2) != 2:
            continue
        sides = {v['homeAway']: v for v in c['competitors']}
        if e['id'] != c['id'] or stamp(e['date']) != stamp(c['date']) or len(sides) != 2:
            raise ValueError('ESPN identity mismatch')
        h, a = sides['home'], sides['away']
        yield game(e['id'], c['date'], h['team']['id'], a['team']['id'], h['score'], a['score'])
    # ESPN last-five cards show the outcome in the card team's orientation.
    # Explicit side-labelled score fields recover the home/away orientation.
    for team in doc.get('lastFiveGames', []):
        for e in team['events']:
            if e.get('competitionName', '').strip() != '2026 Brasileiro Serie A' or e.get('gameResult') not in ('W','D','L'):
                continue
            yield game(e['id'], e['gameDate'], e['homeTeamId'], e['awayTeamId'], e['homeTeamScore'], e['awayTeamScore'])
    head = doc.get('header', {})
    if head.get('league', {}).get('slug') == 'bra.1':
        c = head['competitions'][0]
        if c['status']['type']['name'] == 'STATUS_FULL_TIME' and c['status']['type']['completed']:
            h, a = sorted(c['competitors'], key=lambda x: x['homeAway'] != 'home')
            yield game(c['id'], c['date'], h['team']['id'], a['team']['id'], h['score'], a['score'])


def team_reference(team):
    numeric = team.split(':')[1]
    f = DAILY / (numeric + '.json')
    if not f.exists():
        f = HERE / 'reference' / (numeric + '.json.gz')
    meta = json.loads((f.parent / (numeric + '.meta.json')).read_bytes())
    doc = checked(f, meta['sha256'])
    if doc['team']['id'] != numeric or doc['requestedSeason']['year'] != 2026 or 'bra.1/teams/' + numeric + '/' not in meta['url']:
        raise ValueError('reference team')
    return list(league_finals(doc, meta)), dict(raw_path=str(f.relative_to(DATA)), **meta)


def subsets():
    previous = {v['match_id']: v for v in json.loads((PREVIOUS / 'training/actual_current_sources.json').read_bytes())['rows']}
    with gzip.open(PREVIOUS / 'training/actual_current.jsonl.gz', 'rt') as fp:
        past = [dict(match_id=r['match_id'], home=previous[r['match_id']]['home'], away=previous[r['match_id']]['away'],
                     kickoff_at=r['kickoff_at'], cutoff_at=r['cutoff_at'], population='archived_current')
                for line in fp if (r := json.loads(line))['cohort'] == 'bra.1']
    return past


def build(index):
    options = defaultdict(list)
    for ref in index:
        p = Path(ref['path'])
        if not p.is_absolute():
            p = HERE / p
        doc = checked(p, ref['sha256'])
        if 'receipt_path' in ref:
            checked(HERE / ref['receipt_path'], ref['original_receipt_sha256'])
        for m in league_finals(doc, ref):
            if stamp(m['kickoff_at']) + timedelta(minutes=90) <= stamp(ref['observed_at']):
                options[m['match_id']].append((m, ref))
    out, used = {}, set()
    for f in subsets():
        sequence, lineage = [], {}
        for side in ('home','away'):
            team = f[side]
            entries, ref = team_reference(team)
            eligible = sorted((m for m in entries if stamp(m['kickoff_at']).date() < stamp(f['kickoff_at']).date()),
                              key=lambda m:(m['kickoff_at'],m['match_id']))
            if len({r['match_id'] for r in eligible}) != len(eligible):
                raise ValueError('duplicate historical event')
            slots = eligible[-5:]
            rows, missing = [], []
            for original in slots:
                mid = original['match_id']
                choices = [(m,r) for m,r in options[mid] if stamp(r['observed_at']) <= stamp(f['cutoff_at'])]
                if not choices:
                    rows.append(None)
                    missing.append(mid)
                    continue
                if any(m != original for m, _ in choices):
                    raise ValueError('conflicting prior scores/date/teams: '+mid)
                # Earliest retained observation of this completed league match.
                m, r = min(choices,key=lambda v:(v[1]['observed_at'],v[1]['sha256']))
                used.add(r['sha256'])
                evidence = dict(raw_sha256=r['sha256'], raw_path='historical_raw/'+r['sha256']+'.json.gz', observed_at=r['observed_at'])
                is_home = m['home'] == team
                if not is_home and m['away'] != team:
                    raise ValueError('team orientation')
                step = [m['home_goals'] if is_home else m['away_goals'], m['away_goals'] if is_home else m['home_goals'], int(is_home), 1]
                rows.append(dict(**m, **evidence, step=step))
            # Keep the contiguous most-recent run; do not substitute a non-adjacent older game.
            first = 1 + max((i for i,v in enumerate(rows) if v is None), default=-1)
            retained = rows[first:]
            sequence.append([[0,0,0,0]]*(5-len(retained)) + [r['step'] for r in retained])
            lineage[side] = dict(team=team, reference_path=ref['raw_path'], reference_sha256=ref['sha256'],
                                 reference_observed_at=ref['captured_at'], expected_ids=[m['match_id'] for m in slots],
                                 missing_pre_cutoff_ids=missing, matches=retained)
        out[f['match_id']] = dict(**f, sequence=sequence, lineage=lineage,
                                  complete=all(step[3] == 1 for s in sequence for step in s))
    return out, used


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-index', type=Path, default=HERE / 'historical_sources.json')
    parser.add_argument('--materialize', action='store_true', help='retain matched original ESPN response bytes')
    args=parser.parse_args()
    index=json.loads(args.source_index.read_bytes())
    out, used=build(index)
    if args.materialize:
        dest=HERE/'historical_raw'
        dest.mkdir(exist_ok=True)
        selected=[]
        for src in index:
            if src['sha256'] not in used:
                continue
            p=Path(src['path'])
            local='historical_raw/'+src['sha256']+'.json.gz'
            (HERE/local).write_bytes(gzip.compress(raw_bytes(p),mtime=0))
            selected.append(dict(**{k:v for k,v in src.items() if k!='path'},original_archive=str(p).split('/WCPP/')[-1],
                                 path=local))
        (HERE/'historical_sources.json').write_text(json.dumps(selected,indent=2,ensure_ascii=False)+'\n')
    (HERE/'sequences.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print([(mid,[sum(s[-1] for s in side) for side in v['sequence']]) for mid,v in out.items()])
