# Europe 2026/27 window calendars

This package contains the independently reproducible calendar snapshot for La Liga (`esp.1`), Bundesliga (`ger.1`), Serie A (`ita.1`), and Ligue 1 (`fra.1`). It covers the two half-open Beijing windows:

- `[2026-11-27 00:00, 2026-12-04 00:00)`
- `[2026-12-04 00:00, 2026-12-11 00:00)`

Times are UTC+08:00 for window assignment. Source timestamps remain available in UTC. Collection used public ESPN scoreboard responses and FotMob's public league calendar API. The primary calendar snapshot consists of 12 compressed responses. `source-manifest.json` records each public URL, actual request start and response end clocks, body byte count and SHA-256, gzip object SHA-256, and a post-compression readback SHA check. Supplemental suspended-match status captures are separate under `supplemental-status-evidence/`.

## Rebuild and verification

Run from this directory with Python 3.10+:

```sh
python3 verify_calendars.py
```

The verifier uses only the Python standard library. It decompresses the source objects, verifies both compressed and original body hashes, rebuilds all tables in memory, and checks that the generated files match byte for byte. To regenerate the tables from the retained source objects:

```sh
python3 verify_calendars.py --write
```

`fixtures.json` has the four competition keys and exactly six fields per fixture: `match_id`, `cohort`, `stage`, `kickoff_at`, `home`, and `away`. Event and team IDs use ESPN IDs with the `espn:` prefix; `stage` is `regular`. Fixture arrays sort by kickoff then match ID.

`leagues/esp.1.csv`, `leagues/ger.1.csv`, `leagues/ita.1.csv`, and `leagues/fra.1.csv` contain the 79 window fixtures with source names, ESPN and FotMob event/team IDs, season, stage, UTC and Beijing kickoff, rounds, URLs, source hashes, and source observation clocks. `daily-coverage.csv` has all 56 competition-by-window-by-Beijing-date rows, including dates with zero fixtures. `window-status.csv` records both providers' status per fixture and the held suspended-match exception. `full-season-audit.json` records the full-season cross-source identity and timestamp audit and the window status summary.

## Results

| Competition | Nov 27–Dec 4 | Dec 4–Dec 11 | Total |
| --- | ---: | ---: | ---: |
| `esp.1` | 12 | 11 | 23 |
| `ger.1` | 9 | 9 | 18 |
| `ita.1` | 10 | 10 | 20 |
| `fra.1` | 9 | 9 | 18 |
| **Total** | **40** | **39** | **79** |

Across each complete 2026/27 season, ESPN and FotMob have the same ordered home/away pairings: 380 matches for `esp.1`, 306 for `ger.1`, 380 for `ita.1`, and 306 for `fra.1`. The identity join found no missing pairings and no duplicate home-away rows. All 79 matches fall in the same Beijing dates in both sources and have identical reported kickoff timestamps. No source-only, duplicated, or moved fixture was found inside either window. Empty dates are retained in `daily-coverage.csv`.

### Window status check

`window-status.csv` retains both source states for all 79 fixtures. Seventy-eight are not started: ESPN reports `STATUS_SCHEDULED` with `timeValid=true`, and FotMob reports `started=false`, `finished=false`, and `cancelled=false` at a non-placeholder kickoff.

Keep `espn:401882849` (Rayo Vallecano–Athletic Club, Dec 10 03:00 Beijing) in the La Liga second-window count of 11. Its ESPN event is `STATUS_SUSPENDED`, 0–0, first period at 33 minutes (`clock=1980` seconds), although FotMob lists the future fixture as not started. It is counted as a calendar fixture, but `prematch_first_issue_eligible_now=false`; do not backfill a first prematch issue from before an authoritative public continuation/restart confirmation.

An additional Athletic Club official homepage capture lists match `1_8579` as Athletic Club–Rayo Vallecano on Dec 9, 2026 at 20:00 local time, league matchday 8, `isMatchPlayed=false`, and `isPostponed=false`. This agrees with the listed future kickoff instant but does not document the prior 33-minute stoppage or establish that this is a restart announcement. The LaLiga calendar and Rayo official homepage captures did not expose a match-specific stoppage/restart record. Those raw captures, request clocks, and hashes are separate under `supplemental-status-evidence/`; the original 12 ESPN/FotMob captures and their manifest are unchanged.

Full-season timestamp differences occur outside the windows and are itemized in `full-season-audit.json`: 219 La Liga, 135 Bundesliga, 191 Serie A, and 141 Ligue 1 pairings have different raw timestamps. In 218, 135, 190, and 140 of those cases respectively, ESPN marks the time invalid (`timeValid=false`), so the difference is treated as unresolved provider precision/placeholder data rather than a confirmed schedule change. The remaining one timestamp difference in La Liga, Serie A, and Ligue 1 concerns an already finished match; Bundesliga has none. The audit found zero explicit conflicting scheduled kickoffs where both providers supplied a valid non-placeholder time. These differences are outside the requested windows; the window fixtures pass the exact timestamp check.

The ESPN `dates=2026` response also contains 2025/26 events; reconstruction retains events tagged by ESPN as the 2026 season and combines them with the 2027 board. FotMob team names are normalized only for matching source identities; original names and both providers' IDs are preserved in the league CSVs.

## Protocol reference

The protocol is the file at `research/20261125-europe-display-windows/protocol.json` in commit `9f102288aa0f838d5c6c97994a53acb50b48e7d6` (`9f10228` is its Git commit short ID). That committed file's SHA-256 is `5586c477082449beddc4c65d4929eeea8c7110dffdaf94d9b5d9eb0147c977da`. The protocol version and exact commit are recorded in `protocol-reference.json`; the content specifies the four competitions, 2026/27 season, regular stage, and both Beijing half-open windows.
