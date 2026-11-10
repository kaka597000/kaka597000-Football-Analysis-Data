> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Sportsbook / Affiliate IDs

> Look up sportsbook and affiliate IDs in TheRundown API and use the affiliate_ids filter to request prices from specific sources.

Each source currently published by TheRundown API is identified by a numeric `affiliate_id`; these values are returned within odds/line objects and are used with the `affiliate_ids` filter parameter to request prices from specific books.

See the [Coverage Matrix](https://docs.therundown.io/reference/coverage-matrix.md) for which books price each league.

For a first request against one book, each book guide on therundown.io has a runnable Python example that passes that book's `affiliate_ids` value: [DraftKings](https://therundown.io/draftkings-odds-api), [FanDuel](https://therundown.io/fanduel-odds-api), [BetMGM](https://therundown.io/betmgm-odds-api), [Caesars Sportsbook](https://therundown.io/caesars-odds-api), [Pinnacle](https://therundown.io/pinnacle-odds-api), [Bovada](https://therundown.io/bovada-odds-api), [HardRock](https://therundown.io/hard-rock-odds-api), [theScore Bet](https://therundown.io/thescore-bet-odds-api), [Kalshi](https://therundown.io/kalshi-odds-api), [Polymarket](https://therundown.io/polymarket-odds-api), [Polymarket US](https://therundown.io/polymarket-us-odds-api) and [Novig](https://therundown.io/novig-odds-api).

| Sportsbook | Affiliate ID |
| - | - |
| Bovada | 2 |
| Pinnacle | 3 |
| SportsBetting | 4 |
| BetOnline | 6 |
| BookMaker | 7 |
| BetCRIS | 9 |
| LowVig | 11 |
| Intertops | 14 |
| Matchbook | 16 |
| YouWager | 18 |
| DraftKings | 19 |
| Unibet | 21 |
| BetMGM | 22 |
| FanDuel | 23 |
| theScore Bet | 24 |
| Kalshi | 25 |
| Polymarket | 26 |
| HardRock | 28 |
| ProphetX | 29 |
| Novig | 30 |
| Polymarket US | 31 |
| Circa Sports | 32 |
| Bet105 | 33 |
| Heritage Sports | 34 |
| Caesars Sportsbook | 35 |

> [!NOTE]
>
> These IDs are used in the `affiliate_ids` query parameter to filter which sportsbooks are included in the response. For example, `affiliate_ids=19,23` returns lines from DraftKings and FanDuel only.

> [!NOTE]
>
> Each affiliate's current integration health is returned by `GET /api/v2/affiliates` in the `status` field. Possible values include `healthy`, `unhealthy`, and `beta`. Treat the endpoint as authoritative and handle unrecognized values as unknown rather than hard-coding a status set on the client side. Availability varies by source, sport, and market.

## Source identifiers (mapping to a book's own data)

Two fields link TheRundown objects back to each sportsbook's *own* identifiers, so you can join our odds against a book's native dataset or deep-link into it:

| Field | Where | Meaning |
| - | - | - |
| `affiliate_source_ids` | Event object | Map of affiliate ID (string) → that book's own identifier for the **event** |
| `source_id` | Price object | That book's own identifier for the **specific selection/outcome** the price belongs to |

Both appear only where the book exposes an identifier — a missing field means that book doesn't publish one, not an error. The values are book-native and follow each book's own format.

### Polymarket (affiliate 26)

Polymarket identifiers are fully recoverable from our fields. The event-level `affiliate_source_ids["26"]` is Polymarket's **event slug**, and every price's `source_id` encodes three identifiers:

```
<event-slug>-<gamma-market-id>-<clob-token-id>
```

Parse it from the **right** — the event slug itself contains hyphens, but the two trailing fields are purely numeric: the last hyphen-separated field is the CLOB token ID, the second-to-last is the Gamma market ID, and everything before that is the event slug.

Worked example — an MLB game total (`Over 7.5`). Token IDs are long numeric strings (\~78 digits); the one below is truncated with `…` for readability:

```
source_id: mlb-nyy-bal-2026-08-18-3672567-4850008126…8000256102
           └───────┬────────────┘ └──┬──┘ └────────┬──────────┘
             event slug         Gamma market   CLOB token ID
                                    ID         (this outcome)
```

* **Gamma market ID → slug + conditionId**: `GET https://gamma-api.polymarket.com/markets/3672567` returns the market's `slug` (`mlb-nyy-bal-2026-08-18-total-7pt5`), `conditionId`, `question`, and `clobTokenIds`.
* **CLOB token ID → order book**: usable directly with Polymarket's CLOB API (e.g. `GET https://clob.polymarket.com/book?token_id=<id>`). Polymarket lists each outcome (Over / Under, each team) as its own token, so the token ID also tells you which *side* of the market our price row represents.
* **Event slug** groups all of a game's markets and matches Polymarket's own event slug.

So a single Gamma `/markets/{id}` call on the second-to-last field of `source_id` gives you the market's slug and `conditionId` — no name matching required.

### Other books

Formats for other books are their native identifiers as published (for example, DraftKings event IDs in `affiliate_source_ids["19"]` are DraftKings' own numeric event IDs). We don't transform them; consult the book's documentation for how to use its IDs.

## Current integration status

New books surface through the affiliates endpoint. Refresh your reference data regularly and use that response for the current roster and status. Use `?include=sports` for stored per-sport health or `?sport_id=12` for a sport-scoped `status` plus `status_scope: "sport"`. Without `status_scope`, `status` describes the book overall. Treat unrecognized status values as unknown. Availability varies by source, sport, and market.

Protected books (19, 22, 23) remain healthy in sport responses, except when an
explicit unhealthy whole-book restriction applies to BetMGM (22). Beta integrations remain beta.
That restriction also applies to `sports[]`; its `since` timestamp is the whole-book
status-change time in UTC, or null if unavailable.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.