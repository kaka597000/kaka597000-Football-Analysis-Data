"""Register the complete Europa and Conference league-phase slates and bind the R13 firsts."""

import argparse
from collections import Counter
from datetime import timezone
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from prediction_engine import predict_models
from publication import atomic_json
from research.analysis_freeze import aware, reject_credentials
from research_program import goal_state_forward as ledger
from research_program.display_window_review import _raw_market_clock
from research_program.goal_state_study import sha
from research_program.kpi_targets import ORIGINAL_SCHEMA, ORIGINAL_TARGETS
from research_program.paired_kpi_inference import _decisions


HERE = Path(__file__).resolve().parent
BEIJING = ZoneInfo('Asia/Shanghai')
SLATES = ('2026-11-26', '2026-12-10')
COMPETITIONS = {
    'uecl': ('uefa.europa.conf', 'UEFA Conference League, League Phase', 14546, '欧协联', 4),
    'uel': ('uefa.europa', 'UEFA Europa League, League Phase', 14540, '欧联', 5),
}
R13 = '20261125-r13-domestic-form/forward'
ARCHIVES = {
    'r13': (R13 + '/first-issues.tar.gz', '86808d14475d3584439af1571f9ece8a23b82ffc2801bb3e9a00078073f3fc08'),
    'ranked': (R13 + '/ranked.tar.gz', '9060b3c66d1dfb854f1f2043527258d20ca7055ddfb9b5d797a251f8ea4ecb76'),
    'r7': ('20261123-prematch-literature/first-issues.tar.gz', '52f1dd07d146a93ba9cec41ce9e1c9cdf75b3db43f8a65da7ffea222467f385d'),
    'r5': ('20261123-all-scope-kpi/forward-first-issues.tar.gz', '11eeb44fab0fd49602c8f9b04e00979318391d6242d483efc82034a3bdcf8d7a'),
}


def read(path):
    return json.loads(path.read_bytes())


def schedule(short, day, capture):
    code, stage, season_type, _, _ = COMPETITIONS[short]
    path = HERE / 'calendar' / f'{short}-{day}.json.gz'
    raw = gzip.decompress(path.read_bytes())
    board = json.loads(raw)
    url = urlsplit(capture['url'])
    if (sha(path) != capture['archive_sha256'] or hashlib.sha256(raw).hexdigest() != capture['source_sha256']
            or capture['status'] != 200 or url.scheme != 'https' or url.hostname != 'site.api.espn.com'
            or not url.path.endswith(f'/soccer/{code}/scoreboard')
            or parse_qs(url.query).get('dates') != [day.replace('-', '')]
            or [row['slug'] for row in board['leagues']] != [code]):
        raise ValueError('schedule archive or endpoint differs')
    rows = {}
    for event in board['events']:
        game, = event['competitions']
        kickoff = aware(event['date']).astimezone(timezone.utc)
        teams = {row['homeAway']: row['team'] for row in game['competitors']}
        mid = 'espn:' + str(event['id'])
        if (mid in rows or event['id'] != game['id'] or aware(game['date']) != kickoff
                or kickoff.date().isoformat() != day or aware(capture['observed_at']) >= kickoff
                or event['season'] != {'year': 2026, 'type': season_type, 'slug': 'league-phase'}
                or event['status']['type']['name'] != 'STATUS_SCHEDULED' or not game['timeValid']
                or len(game['competitors']) != 2 or teams.keys() != {'home', 'away'}):
            raise ValueError('schedule event differs from its league-phase round: ' + mid)
        fixture = dict(match_id=mid, cohort=code, stage=stage, kickoff_at=kickoff.isoformat(),
                       home='espn:' + str(teams['home']['id']), away='espn:' + str(teams['away']['id']))
        rows[mid] = dict(fixture=fixture, names=[teams['home']['displayName'], teams['away']['displayName']],
                         markets=game.get('odds', []))
    team_ids = Counter(row['fixture'][side] for row in rows.values() for side in ('home', 'away'))
    if len(rows) != 18 or len(team_ids) != 36 or max(team_ids.values()) != 1:
        raise ValueError('expected one scheduled fixture for each of 36 league-phase clubs')
    return rows, set(team_ids)


def registration_inputs():
    captures = read(HERE / 'calendar/captures.json')
    for short, (code, _, _, _, first_round) in COMPETITIONS.items():
        today, first_teams = schedule(short, SLATES[0], captures[short][SLATES[0]])
        next_round, next_teams = schedule(short, SLATES[1], captures[short][SLATES[1]])
        if today.keys() & next_round.keys() or first_teams != next_teams:
            raise ValueError('consecutive rounds differ in scope or overlap')
        boundary = '2026-12-10T00:00:00+08:00'
        windows = {
            'round1': dict(round=first_round, start='2026-11-26T00:00:00+08:00', until=boundary,
                           ids=sorted(today)),
            'round2': dict(round=first_round + 1, start=boundary, until='2026-12-12T00:00:00+08:00',
                           ids=sorted(next_round)),
        }
        identity = dict(version='EUROPE-R13-FIRST-DISPLAY-20261126-1', registry_schema=ORIGINAL_SCHEMA,
                        competitions=[code], windows=windows, targets=dict(ORIGINAL_TARGETS, selected_sweep=1.),
                        minimum=dict(first=18, three=18, wdl=18, timed_ou=15, non_push_ou=13, selected_seats=3),
                        method='R13-domestic-form-and-rest-1; signed first and ranking',
                        calendar=captures[short], first_archives={name: list(item) for name,item in ARCHIVES.items()},
                        market='Same R5 pregame odds cutoff; strict settlement requires named book and provider clock',
                        first_display='Original scoreboard fixture, first actual receipt, no later picks or substitutions',
                        result='Regulation 90 plus stoppage time from retained finished response', pairs={})
        yield short, today, next_round, identity


def register(issue):
    directory = HERE / 'registration'
    current = {}
    for short, today, next_round, identity in registration_inputs():
        fixtures = [row['fixture'] for row in (today | next_round).values()]
        track = short + '-r13-display-windows-20261126'
        manifest = directory / (short + '.json')
        if issue and not manifest.exists():
            ref = ledger.register(fixtures, identity, track, directory)
            atomic_json(manifest, ref)
        ref = read(manifest)
        plan = ledger._read(directory, ref)
        if (plan['payload']['identity'] != identity or plan['payload']['track'] != track
                or plan['payload']['fixtures'] != {f['match_id']: f for f in fixtures}
                or aware(plan['recorded_at']) >= min(aware(f['kickoff_at']) for f in fixtures)):
            raise ValueError('window registration differed or followed kickoff')
        current[short] = dict(plan=ref, today=today, next_round=next_round)
    return current


def verify_official():
    for short, today, next_round, _ in registration_inputs():
        fixtures = today | next_round
        path = HERE / 'calendar' / f'uefa-{short}-crosswalk.json'
        capture = read(path)
        meta = capture['meta']
        raw = gzip.decompress((path.parent / f'uefa-{short}.json.gz').read_bytes())
        url = urlsplit(meta['url'])
        competition = {'uecl': '2019', 'uel': '14'}[short]
        if (meta['http_status'] != 200 or hashlib.sha256(raw).hexdigest() != meta['sha256']
                or (url.scheme, url.hostname, url.path) != ('https', 'match.uefa.com', '/v5/matches')
                or parse_qs(url.query).get('competitionId') != [competition]):
            raise ValueError('independent UEFA schedule evidence differs')
        records = json.loads(raw)
        games = {r['id']: r for r in records}
        crosswalk = capture['matches']
        if (len(records) != 36 or len(games) != 36 or len(crosswalk) != 36
                or {r['uefa_match_id'] for r in crosswalk} != games.keys()
                or {'espn:' + r['espn_event_id'] for r in crosswalk} != fixtures.keys()):
            raise ValueError('incomplete UEFA and ESPN match concordance')
        clubs = {}
        for row in crosswalk:
            mid = 'espn:' + row['espn_event_id']
            raw_game = games[row['uefa_match_id']]
            fixture = fixtures[mid]['fixture']
            metadata = raw_game['competition']
            kickoff = aware(fixture['kickoff_at'])
            if (str(metadata['id']) != competition or metadata['age'] != 'ADULT' or metadata['sex'] != 'MALE'
                    or str(raw_game['seasonYear']) != '2027' or raw_game['status'] != 'UPCOMING'
                    or raw_game['round']['metaData']['name'] != 'League Phase'
                    or int(raw_game['matchday']['sequenceNumber']) != COMPETITIONS[short][4] + int(mid in next_round)
                    or not aware(row['kickoff_utc']) == aware(raw_game['kickOffTime']['dateTime']) == kickoff
                    or aware(meta['captured_at_utc']) >= kickoff):
                raise ValueError('official stage, round, status or kickoff differs: ' + mid)
            for side, name in zip(('home','away'), fixtures[mid]['names'], strict=True):
                provider_id = str(raw_game[side + 'Team']['id'])
                if (row[side + '_espn'] != name or row[side + '_uefa_id'] != provider_id
                        or clubs.setdefault(fixture[side], provider_id) != provider_id):
                    raise ValueError('inconsistent ordered club crosswalk: ' + mid)
        if len(clubs) != 36 or len(set(clubs.values())) != 36:
            raise ValueError('provider club crosswalk is not one-to-one')
        print(short, 'UEFA and ESPN concordance', len(crosswalk))


def original(folder, mid):
    index = read(folder / 'receipts.json')
    record = ledger._read(folder, index['matches'][mid])
    plan = ledger._read(folder, index['registration'])
    if (record['payload']['registration_sha256'] != plan['record_sha256']
            or record['track'] != plan['payload']['track']
            or not aware(plan['recorded_at']) <= aware(record['recorded_at']) < aware(record['fixture']['kickoff_at'])):
        raise ValueError('original first is outside its registered cohort or kickoff: ' + mid)
    return record, index['matches'][mid], plan


def scores(season):
    names = read(HERE / 'teams-zh.json')
    with TemporaryDirectory(prefix='euro-firsts-') as directory:
        sources = Path(directory)
        for key, (relative, expected) in ARCHIVES.items():
            path = HERE.parent / relative
            if sha(path) != expected:
                raise ValueError('original archive checksum differs: ' + key)
            with tarfile.open(path) as archive:
                archive.extractall(sources / key, filter='data')
        rankings = ledger._read(sources/'ranked', read(sources/'ranked/plan.json'))
        identity = rankings['payload']['identity']
        output = {}
        for short, prepared in season.items():
            code = COMPETITIONS[short][0]
            selected = identity['selected'][code]
            issued = []
            for mid, entry in sorted(prepared['today'].items(), key=lambda pair: (pair[1]['fixture']['kickoff_at'], pair[0])):
                record, ref, plan = original(sources/'r13', mid)
                r7, r7_ref, _ = original(sources/'r7', mid)
                odds, odds_ref, _ = original(sources/'r5/issued', mid)
                fixture = entry['fixture']
                p = record['payload']
                if (fixture != {key: record['fixture'][key] for key in fixture}
                        or fixture != {key: r7['fixture'][key] for key in fixture}
                        or aware(rankings['recorded_at']) < aware(record['recorded_at'])
                        or identity['source_registration'] != plan['record_sha256']
                        or p['forecasts']['r7'] != r7['payload']['forecasts']['candidate']
                        or p['forecasts']['market'] != r7['payload']['forecasts']['market']
                        or r7['payload']['input_sha256'] != odds['record_sha256']
                        or p['odds_source_first_issue'] != odds['record_sha256']
                        or p['odds_cutoff_at'] != odds['fixture']['cutoff_at']
                        or p['line'] != odds['payload']['line']
                        or fixture != {key: odds['fixture'][key] for key in fixture}):
                    raise ValueError('original fixture, ranking or comparison differs: ' + mid)
                forecast = p['forecasts']['candidate']
                _decisions(forecast, None, p['line'])
                if len(forecast['top3']) != 3 or not forecast['wdl']:
                    raise ValueError('each match requires its original three scores and WDL direction')
                books = [q for q in entry['markets'] if isinstance(q, dict)
                         and (q.get('provider') or {}).get('name') == 'DraftKings']
                if len(books) > 1:
                    raise ValueError('ambiguous named ESPN book')
                q = books[0] if books else {}
                current_line = q.get('overUnder')
                timestamp = _raw_market_clock(q)
                rank = next((i for i,s in enumerate(selected, 1) if s['match_id'] == mid), None)
                if rank:
                    seat = selected[rank - 1]
                    if (seat['first_issue'] != ref or seat['primary'] != forecast['primary']
                            or seat['top3'] != forecast['top3'] or seat['first_probability'] != p['quality']['p_first']):
                        raise ValueError('ranked seat differs from the original first issue: ' + mid)
                issued.append(dict(fixture=fixture, names=entry['names'], names_zh=[names[fixture[k]] for k in ('home','away')],
                                   first=ref, r7_first=r7_ref, forecast=forecast, r7=p['forecasts']['r7'],
                                   first_model_probability=p['quality']['p_first'], domestic_history=p['domestic_games'],
                                   market=p['forecasts']['market'], model_training_through=p['training_through'],
                                   source_odds_cutoff_at=p['odds_cutoff_at'], odds_source_first=odds_ref,
                                   original_markets=odds['payload']['market_evidence'],
                                   fresh_line=current_line, fresh_clock=timestamp, rank=rank))
            expected_ranking = sorted(issued, key=lambda r: (-r['first_model_probability'], r['fixture']['kickoff_at'],
                                                            r['fixture']['match_id']))[:3]
            if [item['fixture']['match_id'] for item in expected_ranking] != [item['match_id'] for item in selected]:
                raise ValueError('original seats do not reproduce over the entire round')
            output[short] = dict(window=prepared['plan'], original_ranking=rankings['record_sha256'], rows=issued)
    return output


def body(rounds):
    headings = ['| 北京时间 | 对阵 | 首选 | 备选一 | 备选二 | 胜平负 | 原盘线方向 |',
                '|---|---|---:|---:|---:|---|---|']
    direction = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
    side = {'under': '小', 'over': '大'}
    lines = []
    for short, data in rounds.items():
        lines.extend([f"## {COMPETITIONS[short][3]} 18 场", '', *headings])
        for row in data['rows']:
            kickoff = aware(row['fixture']['kickoff_at']).astimezone(BEIJING)
            choices = row['forecast']
            first, second, third = choices['top3']
            total = f"{side[choices['total_side']]} {choices['total_line']:g}" if choices['total_side'] else '待定'
            label = '–'.join(row['names_zh'])
            lines.append(f"| {kickoff:%m-%d %H:%M} | {label} | **{first}** | {second} | {third} | {direction[choices['wdl']]} | {total} |")
        lines.append('')
    return '\n'.join(lines)


def publication(rounds, issue):
    directory = HERE / 'publication'
    scorecard = directory / 'scorecard.json'
    message = directory / 'score-tables.md'
    table = body(rounds)
    if issue and not scorecard.exists():
        atomic_json(scorecard, rounds)
    if issue and not message.exists():
        message.write_text(table, encoding='utf-8')
    if read(scorecard) != rounds or message.read_text(encoding='utf-8') != table:
        raise ValueError('report changes an original first-selection table')
    verified = {}
    for short, section in rounds.items():
        fixtures = [r['fixture'] for r in section['rows']]
        selected = {r['rank']: r['fixture']['match_id'] for r in section['rows'] if r['rank']}
        identity = dict(window=section['window']['sha256'], ranking=section['original_ranking'],
                        selected=[selected[i] for i in range(1,4)], scorecard_sha256=sha(scorecard),
                        displayed_table_sha256=sha(message), verification='AWAITING_INDEPENDENT_CHANNEL_READBACK')
        track = short + '-r13-first-display-handoff-20261126'
        index = directory / (short + '.json')
        if issue and not index.exists():
            for f in fixtures:
                check = dict(f, competition=f['cohort'], identity_verified=True, stage_verified=True,
                             score_basis='regulation_90', phase='prematch')
                try:
                    predict_models(check)
                except ValueError as exc:
                    if str(exc) != 'no validated identity/history model for this cohort':
                        raise
                else:
                    raise ValueError('active route now exists; investigate before retiring the refusal')
            ref = ledger.register(fixtures, identity, track, directory)
            atomic_json(index, ref)
        ref = read(index)
        record = ledger._read(directory, ref)
        if (record['payload']['identity'] != identity or record['payload']['track'] != track
                or record['payload']['fixtures'] != {f['match_id']: f for f in fixtures}
                or not aware(section['window']['recorded_at']) <= aware(record['recorded_at'])
                < min(aware(f['kickoff_at']) for f in fixtures)):
            raise ValueError('publication freeze differs from its original window or table')
        verified[short] = ref
    return verified


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action', choices=('register', 'prepare-display', 'verify'))
    action = cli.parse_args().action
    if action == 'register':
        print({key: v['plan'] for key, v in register(True).items()})
    else:
        reject_credentials(read(HERE / 'calendar/captures.json'))
        rounds = scores(register(False))
        for short, ref in publication(rounds, action == 'prepare-display').items():
            print(short, len(rounds[short]['rows']), ref['id'], ref['recorded_at'])
        if action == 'verify':
            verify_official()
