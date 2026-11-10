> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Coverage: 25+ Books

> Find sport IDs and coverage notes for TheRundown API. Query the sports catalog before selecting a league or assuming events are available.

Each sport supported by TheRundown API has a numeric `sport_id`. Use `GET /api/v2/sports` to discover the current catalog before building a selector or assuming a sport has events on a given date.

See the [Coverage Matrix](https://docs.therundown.io/reference/coverage-matrix.md) for which books price each league.

For a first request against one league, each league guide on therundown.io has a runnable Python example that requests that league by sport ID: [NFL](https://therundown.io/nfl-odds-api), [NBA](https://therundown.io/nba-odds-api), [MLB](https://therundown.io/mlb-odds-api), [NHL](https://therundown.io/nhl-odds-api), [NCAA football](https://therundown.io/college-football-odds-api), [NCAA men's basketball](https://therundown.io/college-basketball-odds-api), [WNBA](https://therundown.io/wnba-odds-api), [UFC/MMA](https://therundown.io/ufc-odds-api), [soccer](https://therundown.io/soccer-odds-api), [English Premier League](https://therundown.io/premier-league-odds-api), [tennis](https://therundown.io/tennis-odds-api) and [cricket](https://therundown.io/cricket-odds-api).

Cricket coverage is sparse and includes T20, IPL, and selected other competitions. Availability varies by source, event, and market; check the events and prices returned for your dates. Volleyball is not covered.

## Sport IDs

### Game Sports

| Sport | ID | Abbreviation |
| - | - | - |
| NCAA Football | 1 | NCAAF |
| NFL | 2 | NFL |
| MLB | 3 | MLB |
| NBA | 4 | NBA |
| NCAA Men's Basketball | 5 | NCAAB |
| NHL | 6 | NHL |
| UFC/MMA | 7 | UFC |
| WNBA | 8 | WNBA |
| IPL | 20 | IPL |
| T20 | 21 | T20 |

### Soccer Leagues

| League | ID | Abbreviation |
| - | - | - |
| MLS | 10 | MLS |
| English Premier League | 11 | EPL |
| Ligue 1 | 12 | FRA1 |
| Bundesliga | 13 | GER1 |
| La Liga | 14 | ESP1 |
| Serie A | 15 | ITA1 |
| UEFA Champions League | 16 | UEFA.CHAMP |
| UEFA Euro (currently carries UEFA Europa League matches) | 17 | UEFA.EURO |
| FIFA | 18 | FIFA |
| J-League | 19 | JPN1 |
| UEFA Europa League (no events; use `17`) | 33 | UEFA.EL |
| Liga MX | 34 | Liga MX |

> [!NOTE]
>
> UEFA Europa League matches, including qualifying rounds, are returned under sport ID `17`, which `GET /api/v2/sports` lists as `UEFAEURO`. Sport ID `33` (UEFA Europa League) is in the catalog but has not returned events. Request `17` for Europa League fixtures and prices.

### Politics

| Category | ID | Abbreviation |
| - | - | - |
| Politics | 22 | Politics |

### Season-Specific Sports

Preseason, spring-training, summer-league, and MLB playoff games have their own sport IDs. NBA, NFL, and NHL playoff games are returned under the regular-season IDs (`4`, `2`, and `6`): the 2026 NBA and NHL playoffs and the January 2026 NFL playoffs all used them. IDs `24`, `26`, and `28` are in the catalog but have not returned events.

| Sport | ID | Parent |
| - | - | - |
| NBA Preseason | 23 | NBA (4) |
| NBA Playoffs (no events; use `4`) | 24 | NBA (4) |
| NFL Preseason | 25 | NFL (2) |
| NFL Playoffs (no events; use `2`) | 26 | NFL (2) |
| NHL Preseason | 27 | NHL (6) |
| NHL Playoffs (no events; use `6`) | 28 | NHL (6) |
| MLB Spring Training | 30 | MLB (3) |
| MLB Playoffs | 31 | MLB (3) |
| NBA Summer League | 32 | NBA (4) |

> [!NOTE]
>
> Sport ID `27` is NHL Preseason. Sport IDs and sportsbook affiliate IDs are separate namespaces; use the affiliates endpoint to discover selectable sportsbooks.

> [!WARNING]
>
> **MLB Spring Training migration (February 2026):** MLB Spring Training games use sport ID `30`. Regular-season MLB games remain under sport ID `3`.

> [!WARNING]
>
> **MLB Playoffs migration (September 2026):** MLB Playoffs / postseason games use sport ID `31`. Regular-season MLB games remain under sport ID `3`. If you previously looked under sport ID `3` for playoff games, you must query `31`.

### Tennis Leagues

| Tour | ID | Abbreviation |
| - | - | - |
| ATP Tennis | 38 | TENNIS.ATP |
| WTA Tennis | 39 | TENNIS.WTA |

Tennis full-match markets use the dated-game core scope. Set-specific markets are opt-in and must be chosen from the [market catalog](https://docs.therundown.io/reference/markets.md): for example, request the selected prematch and in-play IDs for Set 1 or Set 2 together.

### Futures-Only Sports

| Sport | ID | Endpoint |
| - | - | - |
| PGA | 40 | [Futures](https://docs.therundown.io/api-reference/generated/v2-futures/get-futures-for-a-sport.md) |
| Formula 1 | 41 | [Futures](https://docs.therundown.io/api-reference/generated/v2-futures/get-futures-for-a-sport.md) |

PGA and Formula 1 competition markets use the futures endpoint, not dated-game core markets. Futures access requires an **Ultra plan or higher** for API keys. Discover the competition's market set before requesting it; `1141` is the common tournament-winner market, and golf competitions can offer additional markets.

## Recommended Core Market Scopes

Use an explicit `market_ids` scope in both the event snapshot and market-delta request. These are request scopes, not a promise that every event, sportsbook, plan, or date has every price. Check active availability with `GET /api/v2/sports/{sportID}/markets/{date}` and retain returned market IDs as-is.

| Sport family | Sport IDs | Explicit dated-game core scope |
| - | - | - |
| Ordinary dated game markets | 1–5, 7–8, 20–21, 23–26, 30–32 | `1,2,3,41,42,43` |
| Soccer and NHL regulation-time markets, when offered | 6, 10–19, 27–28, 33–34 | `1,2,3,41,42,43,563,1105` |
| ATP and WTA full-match markets | 38–39 | `1,2,3,41,42,43` |
| Politics | 22 | Discover active markets by date |

Politics is a separate catalog category. Use date-scoped active-market discovery before choosing its market IDs; do not apply a dated-game core scope by default.

`1`, `2`, and `3` are moneyline, handicap, and total. `41`, `42`, and `43` are their in-play IDs. `563` and `1105` are the prematch and in-play three-way result IDs. Include the three-way pair only for a sport, event, and source that offers it. This explicit scope avoids relying on endpoint defaults and keeps snapshots and literal delta filters aligned.

For tennis sets, add only the selected catalog pairs, such as `1150,1151,1152,1153,1154,1155,1156,1157`. For futures, use the dedicated futures endpoint and pass every selected futures market ID explicitly to market delta, such as `1141`; see the [Futures guide](https://docs.therundown.io/guides/futures.md).

## Feature Coverage

Coverage varies by sport, date, event, sportsbook, and plan. Use the current sport and market catalogs plus a date-scoped market read before presenting a market as available.

### Market Availability

Not every market is available for every sport, date, event, or sportsbook. UFC/MMA, for example, does not currently publish spread markets. Use the current sport and market catalogs plus a date-scoped market read to choose supported filters.

Soccer events do not use standard rotation numbers. Use the events-by-date endpoint or search by team ID rather than constructing an event ID from a rotation number.

## Approximate Season Windows

Use this as a rough guide for when regular seasons are active. Dates vary by year, and preseason and playoffs use their own sport IDs.

| Sport | Regular Season | Notes |
| - | - | - |
| NFL | Sep – Jan | 18-week regular season |
| NBA | Oct – Apr | Playoffs run Apr–Jun |
| MLB | Mar – Sep | Spring training starts Feb (sport ID 30); playoffs use sport ID 31 |
| NHL | Oct – Apr | Playoffs run Apr–Jun |
| NCAAF | Aug – Dec | Bowl games Dec–Jan |
| NCAAB | Nov – Mar | March Madness in Mar–Apr |
| WNBA | May – Sep | |
| UFC | Year-round | Events most weekends |
| MLS | Feb – Oct | |
| EPL | Aug – May | |
| Soccer (other) | Varies | See individual league schedules |
| ATP Tennis | Year-round | Tour calendar varies by tournament |
| WTA Tennis | Year-round | Tour calendar varies by tournament |


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.