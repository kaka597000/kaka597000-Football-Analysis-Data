> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Market IDs

> Look up market IDs for prematch and live odds, including moneyline, spreads, totals and props. Check sport-specific market availability.

Markets represent the type of bet available for an event. Each market has a numeric `market_id` used throughout the API. Markets are split into prematch and live/in-play categories.

## Prematch Markets

| Market | ID | Description |
| - | - | - |
| Moneyline | 1 | Winner of the game |
| Point Spread | 2 | Handicap/spread betting |
| Total (Over/Under) | 3 | Combined score total |
| Player Points | 29 | Player points scored |
| Player Turnovers | 33 | Player turnovers |
| Player Rebounds | 35 | Player rebounds |
| Three Pointers | 38 | Player three-pointers made |
| Player Assists | 39 | Player assists |
| Double Double | 87 | Player double-double |
| Triple Double | 88 | Player triple-double |
| Player PRA | 93 | Points + Rebounds + Assists combo |
| Team Totals | 94 | Individual team total score |
| Player Blocks | 98 | Player blocks |
| 3-Way Result (Regulation) | 563 | NHL 60-minute regulation-time home/draw/away line |
| Player Points + Assists | 99 | PA combo |
| Player Points + Rebounds | 297 | PR combo |
| Player Rebounds + Assists | 298 | RA combo |
| Tennis Set 1 Moneyline | 1150 | Winner of Set 1 |
| Tennis Set 1 Spread | 1151 | Game handicap within Set 1 |
| Tennis Set 1 Total | 1152 | Total games played in Set 1 |
| Tennis Set 2 Moneyline | 1153 | Winner of Set 2 |

## Half & Period Markets

Halves and quarters have their own market IDs and, like full game, a **separate in-play ID**. Lines posted before kickoff use the prematch ID; once the game is under way, in-play updates (including lines posted at halftime) arrive under the in-play ID:

| Market | Prematch ID | In-play ID | Active window |
| - | - | - | - |
| First Half Moneyline | 4 | 1024 | Priced pregame; in-play through Q1–Q2, settles at halftime |
| First Half Spread | 5 | 1025 | Priced pregame; in-play through Q1–Q2, settles at halftime |
| First Half Total | 6 | 1026 | Priced pregame; in-play through Q1–Q2, settles at halftime |
| Second Half Moneyline | 1010 | 1028 | Pregame lines on 1010; at halftime and through Q3–Q4 on 1028 |
| Second Half Spread | 1009 | 1029 | Pregame lines on 1009; at halftime and through Q3–Q4 on 1029 |
| Second Half Total | 1008 | 1030 | Pregame lines on 1008; at halftime and through Q3–Q4 on 1030 |
| 3rd Quarter Moneyline | 1016 | 1040 | Pregame lines on 1016; at halftime and through Q3 on 1040 |
| 3rd Quarter Spread | 1015 | 1041 | Pregame lines on 1015; at halftime and through Q3 on 1041 |
| 3rd Quarter Total | 1014 | 1042 | Pregame lines on 1014; at halftime and through Q3 on 1042 |

There is no separate "halftime line" market — the lines books post at the half **are** the in-play second-half and third-quarter markets: second-half lines arrive on **1028/1029/1030** and third-quarter lines on **1040/1041/1042**.

Requesting a second-half prematch ID (`1008`, `1009`, `1010`) on the REST events endpoints or a WebSocket subscription automatically includes its in-play ID (`1030`, `1029`, `1028`). First-half (`4,5,6`) and third-quarter (`1014,1015,1016`) IDs are **not** expanded — request `1024,1025,1026` and `1040,1041,1042` explicitly. A WebSocket subscription can include these IDs before any book has posted them: prices stream as soon as they are published, without resubscribing.

## Live / In-Play Markets

Live markets are the in-play equivalents of prematch markets. They use separate IDs but map back to their prematch counterparts.

> [!WARNING]
>
> **Live rows arrive under the in-play IDs — make sure your client accepts them.** Once a game kicks off, the sportsbooks' full-game moneyline/spread/total updates flow under markets **41/42/43**, not the prematch `1,2,3`. Requesting `market_ids=1,2,3` on the REST events endpoints or a WebSocket subscription **automatically includes the live variants** (`1→41`, `2→42`, `3→43`, `94→96`, `1008→1030`, `1009→1029`, `1010→1028`, and the tennis set markets), so the data reaches you either way — but the rows come back tagged with the in-play IDs, **not relabeled** as `1/2/3`. A client that filters or keys strictly on the prematch IDs will silently discard almost the entire live stream and typically sees only the one or two books that still dual-write on `1/2/3` after kickoff. Treat each prematch/live pair as one logical market keyed on either ID. Half and quarter markets follow the same pattern with their own in-play IDs (see [Half & Period Markets](#half-%26-period-markets)): second half `1028,1029,1030` is auto-included with `1008,1009,1010`, but first half `1024,1025,1026` and third quarter `1040,1041,1042` must be requested explicitly. A complete live main-lines scope for a football game: `41,42,43` + `1024,1025,1026` + `1028,1029,1030` + `1040,1041,1042` (12 IDs, the per-request maximum). **Price history is the exception:** `GET /api/v2/events/{eventID}/markets/history` (and `/api/v2/markets/delta`) filter market IDs literally, so `market_ids=1,2,3` returns only prematch rows. Request `41,42,43,96` explicitly (for example `market_ids=1,2,3,41,42,43,96`) to get in-play history.

| Market | ID | Prematch Equivalent |
| - | - | - |
| Live Moneyline | 41 | 1 |
| Live Spread | 42 | 2 |
| Live Total | 43 | 3 |
| Live Player Points | 90 | 29 |
| Live Player Assists | 91 | 39 |
| Live Three Pointers | 92 | 38 |
| Live Team Totals | 96 | 94 |
| Live 1st Half Moneyline | 1024 | 4 |
| Live 1st Half Spread | 1025 | 5 |
| Live 1st Half Total | 1026 | 6 |
| Live 2nd Half Moneyline | 1028 | 1010 |
| Live 2nd Half Spread | 1029 | 1009 |
| Live 2nd Half Total | 1030 | 1008 |
| Live 3rd Quarter Moneyline | 1040 | 1016 |
| Live 3rd Quarter Spread | 1041 | 1015 |
| Live 3rd Quarter Total | 1042 | 1014 |
| Live 3-Way Result | 1105 | 563 |
| Live Player Rebounds | 982 | 35 |
| Live Player Blocks | 983 | 98 |
| Live Player Turnovers | 984 | 33 |
| Live Double Double | 985 | 87 |
| Live Triple Double | 986 | 88 |
| Live Player PRA | 987 | 93 |
| Live Player Points + Rebounds | 988 | 297 |
| Live Player Points + Assists | 989 | 99 |
| Live Player Rebounds + Assists | 990 | 298 |
| Live Tennis Set 1 Moneyline | 1154 | 1150 |
| Live Tennis Set 1 Spread | 1155 | 1151 |
| Live Tennis Set 1 Total | 1156 | 1152 |
| Live Tennis Set 2 Moneyline | 1157 | 1153 |

## Sport × Market Availability

Not every market is available for every sport. Core markets (moneyline, spread, total) are broadly available, but player props and sport-specific markets vary. Use the [sport/date market listing](https://docs.therundown.io/api-reference/generated/v2-markets/get-available-markets-for-a-sport-and-date.md) to check market definitions for a given day. Add `hide_closed_markets=1` to require at least one open price; without it, the listing can include markets whose matching prices are all closed.

| Market | NFL | NBA | MLB | NHL | NCAAF | NCAAB | WNBA | UFC | Soccer | Tennis |
| - | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Moneyline (1) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Spread (2) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ |
| Total (3) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Team Totals (94) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | ✓ |
| Player Props | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – |

> [!NOTE]
>
> The player prop market IDs listed above (29, 33, 35, 38, 39, etc.) are basketball-centric examples. Each sport has its own set of prop markets — for example, MLB has Player Strikeouts, Player Hits, and Player Home Runs. Use the [market catalog reference](https://docs.therundown.io/api-reference/generated/v2-markets/list-all-market-definitions.md) to discover IDs and filter definitions by `class`, `scope` or `sport_id`.

## Sport-Specific Notes

* **MLB**: Includes pitcher-specific markets. Starting pitcher information affects line availability — lines may show `0.0001` (off the board) until pitchers are confirmed. See [Sentinel Values](https://docs.therundown.io/reference/sentinel-values.md).
* **Soccer** (IDs 10-19, 33, and 34): The soccer 3-way moneyline (home/draw/away) is served on **Moneyline (1)** as three participants; the draw is a participant of the market, not a separate market. Soccer endpoints default `market_ids` to `1,2,3,563`.
* **NHL** (ID 6): The 60-minute regulation-time line — a genuinely different bet from the full-game moneyline, since regulation excludes overtime and shootouts — is served as **3-Way Result (563)**, with live variant `1105`. NHL endpoints default `market_ids` to `1,2,3,563`. Alternate puck lines appear as **alternate lines under Spread (2)** rather than a separate market.
* **Tennis** (IDs 38-39): Match markets use full-game periods (`0` prematch, `7` live). Set-specific markets use tennis-only market IDs such as `moneyline_first_set` (1150), `spread_first_set` (1151), and `totals_first_set` (1152) with set periods such as `3`, `4`, `15`, and `16`.
* **UFC/MMA**: Does not have spread markets. Moneyline and total rounds are the primary markets. Method-of-victory and round betting are available as prop markets.
* **CFL**: Supports core markets (moneyline, spread, total) but does **not** currently support player props.

> [!NOTE]
>
> For the API endpoints that return market data, see the [Markets API reference](https://docs.therundown.io/api-reference/v2/markets). For how markets fit into the overall data hierarchy, see the [Data Model](https://docs.therundown.io/reference/data-model.md).

## Participant-Shaped vs. Line-Valued Markets

Market definitions include `line_value_is_participant` to tell you where the meaningful selection detail lives.

When `line_value_is_participant: true`, the market is participant-shaped: the participant carries the selection, and the line `value` may be a placeholder or label. Moneylines and Yes/No-style result markets commonly work this way.

When `line_value_is_participant: false`, the line `value` is meaningful and should be displayed when present. This includes spreads, totals, player stat thresholds, and special markets where the detail is a method, round, or other outcome qualifier.

For example, UFC method-of-victory markets use the fighter as the `participant` and expose the method, such as decision or KO/TKO, as the line `value`.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.