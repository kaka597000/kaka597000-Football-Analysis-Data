# Buriram United vs Kashima Antlers: prematch evidence collection

Capture cutoff: 2026-11-04 11:56 UTC (19:56 Beijing), about 19 minutes before ESPN's listed 12:15 UTC kickoff. Match identity is ESPN event `401912613`, 2026-27 AFC Champions League Elite League Stage; senior men's clubs. ESPN summary explicitly reports `neutralSite=false`, venue Chang Arena, Buriram. Raw source files and hashes are indexed in `collection-index.json`; fixture identity is in `fixture.json`.

## Retrieved

- ESPN scoreboard and event summary confirm fixture ID, home/away IDs, kickoff, competition/stage, scheduled status, and non-neutral status. Raw JSON is retained.
- ESPN event summary has recent-score rows for both teams. The provider's generic `score` string can be ambiguous/inconsistent with the team ordering, so `espn-lastfive-id-audit.json` derives goals only from `homeTeamScore`/`awayTeamScore` and explicit team IDs. These are results, not xG.
- Buriram's latest listed ACL result: 1-1 away at Gamba (Oct 28); before that 0-1 home to Beijing (Oct 13), then 1-1 away at Johor (Sep 15). Kashima: 4-1 home over Cerezo (Oct 31, J1), 3-0 home over Pohang (Oct 28, ACL), 2-3 home loss to Kashiwa (Oct 24, J1), 2-2 away at Kyoto (Oct 21), 2-0 home over Nagasaki (Oct 17). Opponent strength not adjusted here.
- ESPN schedule API calls for both clubs' ACL fixtures captured separately, see `espn-buriram-elite-schedule.json` and `espn-kashima-elite-schedule.json`.

## Unavailable or unverified by cutoff

- xG/xGA: not returned by captured ESPN sources. FotMob `/api/data/matches?date=2026-11-04` returned JSON `null`; legacy `/api/matches` returned HTTP 404. No xG estimate is substituted.
- Injuries/suspensions: event roster objects are generic team rosters (20/23 entries), not confirmed matchday availability; no injury list or official absence notice was verified. ESPN event summary does not supply a usable injury report. Do not infer fit or absence from roster membership.
- Official starting XI: not present at capture time; no official lineup was verified.
- Odds: ESPN says `hasOdds=false` and has empty `pickcenter`. Attempted guessed OddsPortal and Oddschecker fixture URLs both returned 404. No bookmaker, market line, two-sided prices, quote timestamps, or movement history were verified. Therefore no market direction/line is available.
- Rest/travel: prior fixtures establish dates but do not establish full all-competition load or travel; no route/travel claim made.

Additional authorized API attempts at 2026-11-04 11:57:55 UTC:

- The Odds API `/v4/sports` returned HTTP 200 (authenticated; remaining quota 427, used 73). Its 49 active soccer sports did not include AFC Champions League/Elite, so it supplied no event key to query. Scrubbed response and audit are in `theodds-sports.json`; no event/market query was made.
- 5Dollar `/v1/fixtures?date=2026-11-04&types=jingcailottery` returned HTTP 400 (`HTTP_ERROR`); no fixture mapping or market was returned. Audit is in `5dollar-date-fixtures.json`.

No official club or AFC injury/suspension notice could be verified in the accessible captured data before cutoff; this remains unknown, not a clean bill of health.
