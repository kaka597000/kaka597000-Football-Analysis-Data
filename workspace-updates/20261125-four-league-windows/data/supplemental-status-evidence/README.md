# Supplemental suspended-fixture status evidence

These captures are separate from the immutable 12-response ESPN/FotMob calendar intake. No original calendar response bytes, SHA-256 values, or observation clocks were replaced or edited.

The single La Liga exception is `espn:401882849` (Rayo Vallecano–Athletic Club). Its retained ESPN season-board bytes report `STATUS_SUSPENDED`, score 0–0, period 1 at 33 minutes (`clock=1980` seconds). FotMob's independent full-season feed lists its future Dec 9 19:00 UTC fixture as not started, not finished, and not cancelled.

The public Athletic Club homepage response captured at `2026-11-25T12:00:03.600627Z` contains match `1_8579`: Athletic Club vs Rayo Vallecano, La Liga matchday 8, Dec 9 2026 20:00 local, not played, and not marked postponed. This supports the listed future kickoff but does not say it is a restart and does not establish when the reported 33-minute play began or was suspended. The public LaLiga calendar and Rayo Vallecano homepage were also captured, but no match-specific stoppage or restart notice was present. The public search response was an access interstitial and is not used as evidence.

Accordingly the fixture remains in the 11-match window denominator, while its first prematch issue is held pending public confirmation of continuation/restart status and time. `status-claim.json` contains each observation, URL, query clocks, and body SHA. `captures.jsonl` provides the response/readback hashes for the supplemental captures. The raw responses are gzip-compressed under `raw/`.
