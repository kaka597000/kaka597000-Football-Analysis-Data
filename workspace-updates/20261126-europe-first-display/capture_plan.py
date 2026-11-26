"""List the original European fixtures by kickoff for gathering result evidence."""

import argparse
from collections import defaultdict
from datetime import timezone
import json
from urllib.parse import urlencode

from research.analysis_freeze import aware

import prepare
import result_intake


def official_url(competition, day):
    query = urlencode(dict(competitionId=competition, seasonYear=2027, limit=100, offset=0,
                           fromDate=day, toDate=day))
    return 'https://match.uefa.com/v5/matches?' + query


def plan(window):
    scopes = prepare.register(False)
    calendar = {short: scope[result_intake.WINDOWS[window]] for short, scope in scopes.items()}
    fixtures = {mid: row['fixture'] for group in calendar.values() for mid, row in group.items()}
    official = result_intake.official_bindings(fixtures)
    groups = defaultdict(list)
    published = {}
    original = {}
    if window == 'round1':
        original = prepare.scores(scopes)
        published = prepare.publication(original, False)
    displays = {}
    bulk = {}
    competition_id = {code: ident for ident, code in result_intake.UEFA_IDS.items()}
    for short, scheduled in calendar.items():
        display = published.get(short)
        displays[short] = dict(window_registration=scopes[short]['plan']['id'],
                               score_display_freeze=display['id'] if display else None,
                               registered=len(scheduled))
        firsts = {row['fixture']['match_id']: row for row in original.get(short, {}).get('rows', ())}
        for mid, item in scheduled.items():
            fixture = item['fixture']
            kickoff = aware(fixture['kickoff_at']).astimezone(timezone.utc)
            event = mid.removeprefix('espn:')
            code = fixture['cohort']
            day = kickoff.date().isoformat()
            summary = f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary?event={event}'
            if result_intake.endpoint(summary) != ('espn', code, mid):
                raise ValueError('summary URL must match the original fixture')
            bulk[short, day] = official_url(competition_id[code], day)
            first = firsts.get(mid)
            groups[kickoff].append(dict(competition=short, match_id=mid, uefa_id=official[mid]['id'],
                                        official_matchday=official[mid]['matchday'], home=fixture['home'], away=fixture['away'],
                                        teams=item['names'],
                                        summary_url=summary, original_research_first=first['first']['id'] if first else None,
                                        selected_rank=first['rank'] if first else None))
    waves = [dict(scheduled=kickoff.astimezone(prepare.BEIJING).isoformat(),
                  fixtures=sorted(rows, key=lambda row: (row['competition'], row['match_id'])))
             for kickoff, rows in sorted(groups.items())]
    return dict(window=window, competitions=displays, waves=waves,
                official_result_sources=[dict(competition=short, utc_match_date=day, url=url)
                                         for (short, day), url in sorted(bulk.items())])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window', choices=result_intake.WINDOWS, default='round1')
    options = parser.parse_args()
    print(json.dumps(plan(options.window), ensure_ascii=False, indent=2))
