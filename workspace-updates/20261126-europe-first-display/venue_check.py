"""Replay venue, lineup and recent-form evidence for the registered European rounds."""

from collections import Counter
import json
import re
from statistics import mean
from urllib.parse import urlsplit

from research.analysis_freeze import aware

import prepare
import result_intake


HERE = prepare.HERE
OPENING = 'espn:401915816'


def snapshot(root, meta):
    if meta['http_status'] != 200:
        raise ValueError('expected an HTTP 200 source capture')
    return result_intake.raw_result(root, meta['path'], meta['sha256'])


def source(meta):
    return {key: meta[key] for key in ('url', 'captured_at', 'sha256')}


def venue_fields(game):
    stadium = game['stadium']
    return dict(stadium_id=stadium['id'], stadium=stadium['translations']['name']['EN'],
                city=stadium['city']['translations']['name']['EN'], country=stadium['countryCode'])


def official_venues(scopes, bindings):
    recent = HERE / 'capture-plan/preflight'
    captures = prepare.read(recent / 'captures.json')
    if len(captures) != len(scopes):
        raise ValueError('incomplete first-round venue captures')
    venues = {}
    references = {}
    for short, scope in scopes.items():
        code = prepare.COMPETITIONS[short][0]
        meta, = (item for item in captures if result_intake.endpoint(item['url']) == ('uefa', code, None))
        new = json.loads(snapshot(recent, meta))
        original = prepare.read(HERE / 'calendar' / f'uefa-{short}-crosswalk.json')['meta']
        original = dict(original, captured_at=original['captured_at_utc'], path=f'uefa-{short}.json.gz')
        old = json.loads(snapshot(HERE / 'calendar', original))
        registered = {str(game['id']): game for game in old}
        if len(old) != len(registered) or registered.keys() != {bindings[mid]['id'] for mid in scope['today'] | scope['next_round']}:
            raise ValueError('official venues at registration differ from the two registered rounds')
        this_round = {str(game['id']): game for game in new}
        if len(new) != len(this_round) or this_round.keys() != {bindings[mid]['id'] for mid in scope['today']}:
            raise ValueError('latest official capture differs from the complete first round')
        references[short] = dict(round1_latest=source(meta), both_rounds_at_registration=source(original))
        for window, name in result_intake.WINDOWS.items():
            for mid, row in scope[name].items():
                binding = bindings[mid]
                registered_game = registered[binding['id']]
                is_first = window == 'round1'
                game = this_round[binding['id']] if is_first else registered_game
                observed = aware((meta if is_first else original)['captured_at'])
                fixture = row['fixture']
                status, _ = result_intake.uefa_score(game, fixture, binding, observed)
                if status != 'UPCOMING' or observed >= aware(fixture['kickoff_at']):
                    raise ValueError('venue audit requires a scheduled pregame fixture')
                ground = venue_fields(game)
                country = game['homeTeam']['countryCode']
                if not country or not all(ground.values()):
                    raise ValueError('official venue or home-country evidence is missing')
                venues[mid] = dict(window=window, competition=short, match_id=mid, uefa_id=binding['id'],
                                    scheduled=aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).isoformat(),
                                    teams=row['names'], home_club_country=country, **ground,
                                    outside_home_club_country=country != ground['country'],
                                    changed_since_registration=ground != venue_fields(registered_game) if is_first else None)
    return venues, references


def espn_pregame(root, meta, fixture):
    mid = fixture['match_id']
    if result_intake.endpoint(meta['url']) != ('espn', fixture['cohort'], mid):
        raise ValueError('ESPN summary belongs to a different fixture')
    document = json.loads(snapshot(root, meta))
    status, _ = result_intake.espn_score(document, fixture)
    if status != 'STATUS_SCHEDULED' or aware(meta['captured_at']) >= aware(fixture['kickoff_at']):
        raise ValueError('ESPN evidence is not an identified pregame capture')
    return document


def add_espn_venues(scopes, venues):
    for short, scope in scopes.items():
        root = HERE / 'prematch' / short
        captures = prepare.read(root / 'captures.json')
        if Counter(meta['match_id'] for meta in captures) != Counter(scope['today'].keys()):
            raise ValueError('incomplete ESPN summaries for the first round')
        for meta in captures:
            mid = meta['match_id']
            meta = dict(meta, path=meta['file'], sha256=meta['source_sha256'],
                        captured_at=meta['observed_at'], http_status=meta['status'])
            doc = espn_pregame(root, meta, scope['today'][mid]['fixture'])
            venue = doc['gameInfo']['venue']
            venues[mid]['espn'] = dict(stadium=venue['fullName'], **venue['address'],
                                      neutral_site=doc['header']['competitions'][0].get('neutralSite'))


def verify_uefa_match_page(body, meta, venue, binding):
    page = urlsplit(meta['url'])
    if (page.scheme, page.netloc) != ('https', 'www.uefa.com') or not page.path.startswith(
            f"/uefaconferenceleague/match/{binding['id']}--"):
        raise ValueError('unexpected UEFA match page')
    blocks = (json.loads(block) for block in re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>\s*(.*?)\s*</script>', body.decode(), re.S))
    event, = (item['mainEntity'] for item in blocks if item.get('mainEntity', {}).get('@type') == 'SportsEvent')
    location = event['location']
    if (event['url'] != meta['url'] or event['eventStatus'] != 'EventScheduled'
            or aware(event['startDate']) != aware(venue['scheduled'])
            or aware(meta['captured_at']) >= aware(venue['scheduled'])
            or location['name'] != venue['stadium']
            or location['address']['addressLocality'] != venue['city']
            or location['address']['addressCountry'] != venue['country']
            or any(f"/clubs/{binding[side]}--" not in event[side + 'Team']['sameAs'] for side in ('home', 'away'))):
        raise ValueError('official match page disagrees with the scheduled fixture or ground')


def recent_form(fixture, doc):
    root = HERE / 'prematch/uecl-process'
    captures = prepare.read(root / 'captures.json')
    original = prepare.read(root / 'recent-form.json')['teams']
    evidence = {}
    for side, fotmob_id in (('home', '8037'), ('away', '8127')):
        espn_id = fixture[side].removeprefix('espn:')
        kickoff = aware(fixture['kickoff_at'])
        team, = (row for row in original if row['team_id'] == fotmob_id)
        file = f'team-{fotmob_id}.json.gz'
        meta = dict(captures[file], path=file, captured_at=captures[file]['captured_at_utc'])
        club = json.loads(snapshot(root, meta))
        if str(club['details']['id']) != fotmob_id or aware(meta['captured_at']) >= kickoff:
            raise ValueError('FotMob club identity or time differs')
        flags = [dict(player=p['name'], expected_return=p['injury']['expectedReturn'])
                 for group in club['squad']['squad'] for p in group.get('members', []) if p.get('injury')]
        matches = []
        for match in team['recent_five']:
            file = f"match-{match['match_id']}.json.gz"
            detail = dict(captures[file], path=file, captured_at=captures[file]['captured_at_utc'])
            raw = json.loads(snapshot(root, detail))
            status = raw['header']['status']
            teams = raw['header']['teams']
            played = aware(status['utcTime'])
            if (str(raw['general']['matchId']) != match['match_id'] or not status['finished']
                    or status['reason']['short'] != 'FT' or status['awarded'] or status['cancelled']
                    or played != aware(match['date_utc']) or not played < aware(detail['captured_at']) < kickoff
                    or [(r['id'], r['score']) for r in teams] != [(match[s]['id'], match[s]['score']) for s in ('home', 'away')]):
                raise ValueError('recent match identity, regular-time score or cutoff differs')
            index, = (i for i, r in enumerate(teams) if str(r['id']) == fotmob_id)
            stats = (raw['content'].get('stats') or {}).get('Periods', {}).get('All', {}).get('stats', [])
            top = {r['key']: r['stats'] for group in stats if group['key'] == 'top_stats' for r in group['stats']}
            xg = top.get('expected_goals', [None, None])
            matches.append(dict(fotmob_id=match['match_id'], opponent=teams[1-index]['name'],
                                played=played.astimezone(prepare.BEIJING).isoformat(), competition=match['competition']['name'],
                                goals_for=teams[index]['score'], goals_against=teams[1-index]['score'],
                                xg=float(xg[index]) if xg[index] is not None else None,
                                xga=float(xg[1-index]) if xg[1-index] is not None else None, source=source(detail)))
        latest = max(matches, key=lambda row: aware(row['played']))
        group, = (row for row in doc['lastFiveGames'] if row['team']['id'] == espn_id)
        last_espn = max(group['events'], key=lambda row: aware(row['gameDate']))
        last_side = 'home' if last_espn['homeTeamId'] == espn_id else 'away'
        other_side = 'away' if last_side == 'home' else 'home'
        if (str(club['overview']['lastMatch']['id']) != latest['fotmob_id']
                or len(matches) != 5 or len({row['fotmob_id'] for row in matches}) != 5
                or aware(last_espn['gameDate']) != aware(latest['played'])
                or last_espn['opponent']['displayName'] != latest['opponent']
                or (int(last_espn[last_side + 'TeamScore']), int(last_espn[other_side + 'TeamScore']))
                != (latest['goals_for'], latest['goals_against'])):
            raise ValueError('latest competitive fixture was not reconciled')
        xg_rows = [item for item in matches if item['xg'] is not None and item['xga'] is not None]
        evidence[side] = dict(team=team['team'], fotmob_id=fotmob_id, espn_id=espn_id, club_source=source(meta),
                              team_injury_flags=flags, latest_reconciled_espn_event=last_espn['id'],
                              latest_scheduled_kickoff_interval_hours=(kickoff-aware(latest['played'])).total_seconds()/3600,
                              games_scored=sum(row['goals_for'] > 0 for row in matches),
                              games_conceded=sum(row['goals_against'] > 0 for row in matches),
                              xg_games=len(xg_rows), mean_xg=round(mean(r['xg'] for r in xg_rows), 2),
                              mean_xga=round(mean(r['xga'] for r in xg_rows), 2), matches=matches)
    return evidence


def build():
    scopes = prepare.register(False)
    fixtures = {mid: row['fixture'] for group in scopes.values() for key in result_intake.WINDOWS.values()
                for mid, row in group[key].items()}
    bindings = result_intake.official_bindings(fixtures)
    venues, references = official_venues(scopes, bindings)
    add_espn_venues(scopes, venues)
    opening = HERE / 'prematch/venue-opening'
    meta = prepare.read(opening / 'captures.json')
    doc = espn_pregame(opening, meta['espn'], fixtures[OPENING])
    verify_uefa_match_page(snapshot(opening, meta['uefa']), meta['uefa'], venues[OPENING], bindings[OPENING])
    pick, = (row for row in prepare.read(HERE / 'publication/scorecard.json')['uecl']['rows']
             if row['fixture'] == fixtures[OPENING])
    return dict(official_sources=references, fixtures=sorted(venues.values(), key=lambda row: (row['scheduled'], row['match_id'])),
                opening=dict(match_id=OPENING, sources={label: source(item) for label, item in meta.items()},
                             first_receipt=pick['first']['id'], original=pick['forecast'], same_cutoff_market=pick['market'],
                             original_total_provider_priced_at=pick['original_markets']['total']['quoted_at'],
                             original_domestic_history_counts=pick['domestic_history'],
                             espn_named_roster_teams=sum(bool(row.get('roster')) for row in doc.get('rosters', [])),
                             espn_injury_field_present='injuries' in doc, recent_form=recent_form(fixtures[OPENING], doc)))


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
