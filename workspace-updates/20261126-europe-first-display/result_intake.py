"""Normalize retained ESPN summaries and UEFA results for the original European rounds."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from publication import atomic_json, deliver
from research.analysis_freeze import aware
from v2_test.data_contract import public_url

import prepare


UEFA_IDS = {'14': 'uefa.europa', '2019': 'uefa.europa.conf'}
ESPN_TYPES = {entry[0]: entry[2] for entry in prepare.COMPETITIONS.values()}
WINDOWS = {'round1': 'today', 'round2': 'next_round'}
CROSSWALKS = {
    'uecl': '69f76f016296239ef34f5478ca4cae8a29debb650634fa00c9f1688ba309dff8',
    'uel': '73a7f90ef0ab485fd43d3c4eaa5adec761435db75309b64cdae1d098934c0b35',
}
IDENTITY = ('match_id', 'home', 'away', 'cohort', 'stage')
EVIDENCE_ERRORS = (OSError, EOFError, KeyError, ValueError, TypeError, AttributeError)


def endpoint(source):
    public_url(source)
    url = urlsplit(source)
    if url.port not in (None, 443):
        raise ValueError('unexpected public result service port')
    query = parse_qs(url.query)
    if url.hostname in {'site.api.espn.com', 'site.web.api.espn.com'}:
        code, = (code for code in ESPN_TYPES if url.path == f'/apis/site/v2/sports/soccer/{code}/summary')
        event, = query.get('event', ())
        if event.isascii() and event.isdecimal():
            return 'espn', code, 'espn:' + event
    if url.hostname == 'match.uefa.com' and url.path == '/v5/matches' and query.get('seasonYear') == ['2027']:
        competition, = query.get('competitionId', ())
        if competition in UEFA_IDS:
            return 'uefa', UEFA_IDS[competition], None
    raise ValueError('unsupported result source route')


def raw_result(root, relative, digest):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('result capture is outside its retained evidence directory')
    stored = path.read_bytes()
    body = gzip.decompress(stored) if stored.startswith(b'\x1f\x8b') else stored
    if sha256(body).hexdigest() != digest:
        raise ValueError('result capture checksum differs')
    return body


def registered_fixtures(window):
    return {mid: row['fixture'] for group in prepare.register(False).values() for mid, row in group[WINDOWS[window]].items()}


def official_bindings(fixtures):
    bindings = {}
    for short, digest in CROSSWALKS.items():
        code, _, _, _, first_matchday = prepare.COMPETITIONS[short]
        file = prepare.HERE/'calendar'/f'uefa-{short}-crosswalk.json'
        body = file.read_bytes()
        if sha256(body).hexdigest() != digest:
            raise ValueError('original UEFA identity crosswalk differs')
        for row in json.loads(body)['matches']:
            mid = 'espn:' + row['espn_event_id']
            if mid not in fixtures:
                continue
            kickoff = aware(row['kickoff_utc']).astimezone(timezone.utc)
            matchday = first_matchday + prepare.SLATES.index(kickoff.date().isoformat())
            if mid in bindings or code != fixtures[mid]['cohort'] or kickoff != aware(fixtures[mid]['kickoff_at']):
                raise ValueError('UEFA identity binding differs from the original window')
            bindings[mid] = dict(id=row['uefa_match_id'], home=row['home_uefa_id'], away=row['away_uefa_id'], matchday=matchday)
    if bindings.keys() != fixtures.keys():
        raise ValueError('incomplete UEFA identity bindings for the original round')
    return bindings


def uefa_score(game, fixture, binding, captured, *, season_year='2027'):
    meta = game['competition']
    code = UEFA_IDS.get(str(meta['id']))
    kickoff = aware(fixture['kickoff_at'])
    if (code != fixture['cohort'] or meta['age'] != 'ADULT' or meta['sex'] != 'MALE'
            or str(game['seasonYear']) != season_year or game['round']['metaData']['name'] != 'League Phase'
            or str(game['id']) != binding['id'] or str(game['homeTeam']['id']) != binding['home']
            or str(game['awayTeam']['id']) != binding['away']
            or str(game['matchday']['sequenceNumber']) != str(binding['matchday'])):
        raise ValueError('UEFA match, ordered teams or stage differs')
    status = game['status']
    if status in ('FINISHED', 'UPCOMING') and aware(game['kickOffTime']['dateTime']) != kickoff:
        raise ValueError('UEFA result response has a different scheduled kickoff')
    if status != 'FINISHED':
        return status, None
    score = game['score']
    regular = score['regular']
    values = tuple(regular[side] for side in ('home', 'away'))
    reason = game.get('winner', {}).get('match', {}).get('reason')
    fulltime = game.get('fullTimeAt')
    if (any(type(x) is not int or x < 0 for x in values) or score.get('total', regular) != regular
            or any(value is not None and any(part in key.casefold() for part in ('extra', 'penalt', 'shootout'))
                   for key, value in score.items())
            or reason not in (None, 'WIN_REGULAR', 'DRAW') or captured < kickoff + timedelta(minutes=90)
            or (fulltime and not kickoff + timedelta(minutes=90) <= aware(fulltime) <= captured)):
        raise ValueError('UEFA response does not establish a completed regulation score')
    return status, values


def espn_score(document, fixture):
    header = document['header']
    game, = header['competitions']
    mid = fixture['match_id'].removeprefix('espn:')
    code = fixture['cohort']
    teams = {row['homeAway']: row for row in game['competitors']}
    season = header['season']
    if (str(header['id']) != mid or str(game['id']) != mid or header['league']['slug'] != code
            or season['year'] != 2026 or season['type'] != ESPN_TYPES[code]
            or len(game['competitors']) != 2 or teams.keys() != {'home', 'away'}
            or any('espn:' + str(teams[side]['team']['id']) != fixture[side] for side in teams)):
        raise ValueError('ESPN match, ordered teams or stage differs')
    status = game['status']['type']
    if (status['name'] in ('STATUS_FULL_TIME', 'STATUS_SCHEDULED')
            and aware(game['date']) != aware(fixture['kickoff_at'])):
        raise ValueError('ESPN result response has a different scheduled kickoff')
    if status['name'] != 'STATUS_FULL_TIME' or status['completed'] is not True:
        return status['name'], None
    scores = [teams[side]['score'] for side in ('home', 'away')]
    values = tuple(int(score['displayValue'] if isinstance(score, dict) else score) for score in scores)
    return status['name'], values


def label(fixture, score, reference):
    return dict(fixture, home_goals=score[0], away_goals=score[1], event_status='FT', score_basis='regulation_90',
                source_url=reference['source_url'], known_at=reference['captured_at'], raw_reference=reference)


def certify_official(row, fixture, binding, root, at):
    ref = row['raw_reference']
    observed = aware(ref['captured_at'])
    if (endpoint(ref['source_url'])[:2] != ('uefa', fixture['cohort']) or observed > at
            or any(row[key] != fixture[key] for key in IDENTITY)
            or aware(row['kickoff_at']) != aware(fixture['kickoff_at'])
            or row['source_url'] != ref['source_url'] or aware(row['known_at']) != observed
            or row['event_status'] != 'FT' or row['score_basis'] != 'regulation_90'):
        raise ValueError('UEFA result label or capture does not match the original fixture')
    games = json.loads(raw_result(root, ref['path'], ref['sha256']))
    game, = (game for game in games if str(game['id']) == binding['id'])
    _, score = uefa_score(game, fixture, binding, observed)
    proposed = (row['home_goals'], row['away_goals'])
    if score is None or any(type(value) is not int for value in proposed) or score != proposed:
        raise ValueError('UEFA regulation score differs from the normalized row')
    return dict(home=score[0], away=score[1], source=ref, provider='uefa',
                actual_kickoff=None, kickoff_issue='UEFA_RESULT_HAS_NO_TYPED_ACTUAL_KICKOFF')


def assemble(manifest, out, fixtures, bindings, at):
    observations = {mid: [] for mid in fixtures}
    capture_errors, labels, raw = [], [], {}
    routes = {value['id']: mid for mid, value in bindings.items()}
    for index, capture in enumerate(prepare.read(manifest), 1):
        try:
            source = capture['url']
            provider, code, mid = endpoint(source)
            observed = aware(capture['captured_at'])
            if capture['http_status'] != 200 or observed > at:
                raise ValueError('unavailable or late capture')
            body = raw_result(manifest.parent, capture['path'], capture['sha256'])
            data = json.loads(body)
            if provider == 'espn':
                if mid not in fixtures or fixtures[mid]['cohort'] != code:
                    raise ValueError('ESPN capture outside the registered round')
                batch = {mid: espn_score(data, fixtures[mid])}
            else:
                batch = {}
                matched = [(routes[str(game['id'])], game) for game in data
                           if isinstance(game, dict) and str(game.get('id')) in routes]
                duplicate_counts = Counter(target for target, _ in matched)
                for target, game in matched:
                    try:
                        if duplicate_counts[target] != 1 or fixtures[target]['cohort'] != code:
                            raise ValueError('duplicate or wrong-competition UEFA result')
                        batch[target] = uefa_score(game, fixtures[target], bindings[target], observed)
                    except EVIDENCE_ERRORS as error:
                        capture_errors.append(dict(capture_index=index, match_id=target, reason=str(error)))
            path = 'raw/' + capture['sha256'] + '.json'
            raw[path] = body
            ref = dict(path=path, sha256=capture['sha256'], source_url=source, captured_at=capture['captured_at'])
            for target, (status, score) in batch.items():
                observations[target].append(dict(provider=provider, status=status, source=ref))
                if score is not None:
                    labels.append(label(fixtures[target], score, ref))
        except EVIDENCE_ERRORS as error:
            capture_errors.append(dict(capture_index=index, reason=str(error)))
    out.mkdir(parents=True, exist_ok=False)
    (out/'raw').mkdir()
    for path, body in raw.items():
        deliver(out/path, body)
    report = dict(as_of=at.astimezone(prepare.BEIJING).isoformat(), registered=len(fixtures),
                  captures_with_errors=capture_errors, candidate_regulation_rows=len(labels), matches=observations)
    atomic_json(out/'intake.json', report)
    deliver(out/'normalized-results.jsonl', ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in labels).encode())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--window', choices=WINDOWS, default='round1')
    args = parser.parse_args()
    fixtures = registered_fixtures(args.window)
    report = assemble(args.captures, args.out, fixtures, official_bindings(fixtures), datetime.now(timezone.utc))
    print(json.dumps({key: value for key, value in report.items() if key != 'matches'}, ensure_ascii=False))
