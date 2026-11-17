# 2026-11-17 fixtures and odds evidence

Compiled UTC: 2026-11-17T03:26:17.227894+00:00

## Fixture identities


### China vs Bahrain
- ESPN event `401930880`; competition label `International Friendly` (ESPN season slug `2026-international-friendly`); event status `Scheduled`.
- Kickoff 2026-11-17T12:00Z UTC / 2026-11-17 20:00 Beijing time.
- Teams: China team ID 658 (home); Bahrain team ID 4381 (away).
- ESPN header flag `neutralSite=false`; `summary.gameInfo.venue` is Zhaoqing New District Sports Center Stadium, Zhaoqing, China PR (home country).
- Competition label is International Friendly (`2026-international-friendly`); adult men inferred from ESPN national-team competition mapping; gender/age are not explicit in event fields.
- ESPN event-summary query time: 2026-11-17T03:22:56.893147+00:00 UTC. Quote time is unavailable; ESPN response contains undated `open` and `close` fields. Do not interpret `close` as a current quote or calculate movement from query time.
- ESPN displayed DraftKings prices (American odds; ESPN open → close):
  - 1X2: home  -105 → -105; draw  +225 → +230; away  +300 → +300
  - Point spread (not independently verified as Asian handicap): home  -0.5 -115 → -0.5 -110; away  +0.5 -125 → +0.5 -125
  - Totals: over  o2.5 +115 → o2.5 +120; under  u2.5 -160 → u2.5 -160
- Raw response SHA-256 `196e44f461c11c2f1f920ba8885480f662ac59baede49017ea1e5c383aae54a4`; source `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.friendly/summary?event=401930880`.

### Japan vs Paraguay
- ESPN event `401916336`; competition label `International Friendly` (ESPN season slug `2026-international-friendly`); event status `Scheduled`.
- Kickoff 2026-11-17T13:10Z UTC / 2026-11-17 21:10 Beijing time.
- Teams: Japan team ID 627 (home); Paraguay team ID 210 (away).
- ESPN header flag `neutralSite=false`; `summary.gameInfo.venue` is Singapore National Stadium, Singapore. Venue is outside Japan and Paraguay, so neutral is derived=true; preserve the contradiction with ESPN flag.
- Competition label is International Friendly (`2026-international-friendly`); adult men inferred from ESPN national-team competition mapping; gender/age are not explicit in event fields.
- ESPN event-summary query time: 2026-11-17T03:22:57.870226+00:00 UTC. Quote time is unavailable; ESPN response contains undated `open` and `close` fields. Do not interpret `close` as a current quote or calculate movement from query time.
- ESPN displayed DraftKings prices (American odds; ESPN open → close):
  - 1X2: home  -135 → -155; draw  +265 → +290; away  +360 → +400
  - Point spread (not independently verified as Asian handicap): home  -0.5 -150 → -0.5 -165; away  +0.5 +100 → +0.5 +120
  - Totals: over  o2.5 -105 → o2.5 -110; under  u2.5 -135 → u2.5 -120
- Raw response SHA-256 `8aacc4d34b5d95a1f9ec746b810ad5e463b7fa2ace1e23eecafd94a911cfcf1c`; source `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.friendly/summary?event=401916336`.

### Singapore vs Brazil
- ESPN event `401916335`; competition label `International Friendly` (ESPN season slug `2026-international-friendly`); event status `Scheduled`.
- Kickoff 2026-11-17T10:00Z UTC / 2026-11-17 18:00 Beijing time.
- Teams: Singapore team ID 4384 (home); Brazil team ID 205 (away).
- ESPN header flag `neutralSite=false`; `summary.gameInfo.venue` is Singapore National Stadium, Singapore (home country).
- Competition label is International Friendly (`2026-international-friendly`); adult men inferred from ESPN national-team competition mapping; gender/age are not explicit in event fields.
- ESPN event-summary query time: 2026-11-17T03:22:58.723310+00:00 UTC. Quote time is unavailable; ESPN response contains undated `open` and `close` fields. Do not interpret `close` as a current quote or calculate movement from query time.
- ESPN displayed DraftKings prices (American odds; ESPN open → close):
  - 1X2: home  +9000 → +3000; draw  +2800 → +2200; away  -6000 → -5000
  - Point spread (not independently verified as Asian handicap): home  +4.5 -130 → +4.5 -105; away  -4.5 -110 → -4.5 -130
  - Totals: over  o5.5 +115 → o5.5 -105; under  u5.5 -160 → u5.5 -130
- Raw response SHA-256 `ed0c805d8e7a51ea57491b0f6ff8f55b8014186a3de0a5491a86af486ad46409`; source `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.friendly/summary?event=401916335`.

## Provider attempts and limits

- The Odds API `/v4/sports?apiKey=…` used the official query parameter placement and returned HTTP 401, `INVALID_KEY` (“API key is not valid”). No quota headers were returned; the provider was stopped after this single request. Raw error body and credential-free metadata are retained.
- AsianOdds homepage returned HTTP 401; stopped after the response. Its body/metadata are retained.
- SofaScore scheduled-events API returned HTTP 403; stopped after the response. Its body/metadata are retained.
- Bing returned search pages, but top results were unrelated; they do not independently corroborate fixture identity.
- In the first collection pass, 5Dollar (`_5DOLLARS`) and InferSports (`infer_yapan_zhishu`) were not queried. A separate follow-up capture is stored in `../markets-fallback/`.
- Fixture identity and odds remain supported by ESPN. Independent official confirmation of start time and age/gender classification remains missing in this capture.

## Evidence files

- ESPN scoreboard response: `espn-fifa-friendly-20261117-raw.json` and metadata.
- ESPN event summaries: `espn-<event_id>-summary-raw.json` and metadata for each event.
- Failed provider responses: `theodds-sports-raw.json`, `asianodds-home-raw.html`, `sofascore-scheduled-raw.json` and accompanying metadata.
- Search pages: three `bing-search-*-raw.html` pages and metadata.
- Machine-readable extracted markets: `fixtures-markets-compiled.json`.