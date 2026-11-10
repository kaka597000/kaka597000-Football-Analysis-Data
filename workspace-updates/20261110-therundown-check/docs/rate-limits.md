> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Rate Limits by Plan

> Understand data-point costs, plan history windows, per-second throttles, usage headers, and error responses.

TheRundown API enforces usage controls **per API key**. There are two separate systems to understand:

* **Data-point billing** tracks how much data you consume across REST and WebSocket traffic.
* **Per-second throttling** protects the platform from bursty request patterns.

If you are building production workloads, you should monitor both. A key can stay under its requests-per-second ceiling and still run out of included data points, or vice versa.

## How Usage Is Enforced

### 1. Data points

Most API endpoints return an `X-Datapoints` header. That number represents how many billable data points the response consumed. Successful non-billable responses omit this header. These include the stats sample, catalog responses, and the V1 schedule endpoint (`GET /api/v1/sports/{sportID}/schedule`), which consumes zero data points on every successful response, including nonempty ones. Outside those documented non-billable endpoints, the header's absence does not prove that a request was free. Each request's recorded data points and billing category also appear in your dashboard's request log, which you can use to reconcile usage.

For event responses, each returned event costs **one `events` data point plus one `scores` data point**, plus **one `odds` data point per returned price**. A price is a market price at one sportsbook; count each returned price object. Events carrying `live_game_state` (available on Ultra and above) cost one additional `scores` point.

```text theme={null} theme={null}
data points = 2 × returned events + returned prices + events carrying live_game_state
```

Individual score fields, including per-period scores and overtime, never add a charge. Scores are included in event responses; there is no separate scores or results endpoint.

#### Results sweep example

Pass `hide_closed=true` to exclude closed prices while keeping events and scores:

```bash theme={null} theme={null}
curl --fail -H "X-TheRundown-Key: $THERUNDOWN_API_KEY" \
  "https://therundown.io/api/v2/sports/3/events/YYYY-MM-DD?hide_closed=true"
```

Replace `YYYY-MM-DD` with a completed date inside your [history window](#history-window). When all prices are closed and no `live_game_state` is returned, each game costs **two data points**, with status, final score, per-period scores, and overtime included. A completed baseball slate checked on September 8, 2026 returned eleven finals and zero price objects: `11 × 2 = 22` data points for events and scores. Verify the returned prices and `X-Datapoints` for your request, and add one point for each event carrying `live_game_state`.

For one completed game, `GET /api/v2/events/{eventID}?hide_closed=true` is two data points under the same conditions. See [Scores and Results](https://docs.therundown.io/guides/scores-and-results.md) for examples and checks before grading.

> [!NOTE]
>
> Omitting `market_ids` does not mean "no odds": the default is `1,2,3`, or `1,2,3,563` for soccer and NHL. While games are still open, `market_ids=1` with a single `affiliate_ids` value and `main_line=true` keeps a game to roughly four data points, depending on how many prices are returned. Add one more point if `live_game_state` is present, and use `X-Datapoints` to confirm the cost.

In practice:

* large snapshots across many sportsbooks and markets cost more than narrow, filtered responses
* delta endpoints are usually much cheaper than repeatedly fetching full event payloads
* WebSocket messages are also metered as data points, even though they do not increment the HTTP request counter

Free keys have two included caps: **20,000 data points per UTC day** and **200,000 per UTC calendar month**. The first cap reached pauses requests until that window resets. Paid plans have **monthly included data points** and, on self-serve tiers, optional overage pricing after the included amount. Plans billed weekly meter a proportional weekly share of the tier's allowance instead — see [Weekly Billing](#weekly-billing) below.

### 2. Burst throttling

Every key also has a per-second request ceiling. This is separate from billing and exists to prevent request storms.

If you exceed that burst limit, the API returns `429 Too Many Requests` with a short `Retry-After` value, usually `1`.

### 3. WebSocket behavior

WebSocket traffic does **not** increment your HTTP request counter, but it is still part of your metered usage. Treat subscriptions the same way you treat REST queries: filter aggressively and only subscribe to the sports, events, markets, and books you actually need. A `game_stats` frame costs one stats data point for each changed row across `team_stats[].stats` and `player_stats[].stats`; a zero-row terminal completion marker or invalidation fallback costs one stats data point. Heartbeats and in-band usage metadata are free.

## Current API Tier Defaults

| Tier | Included data points | Overage | Burst limit | Data delay | WebSocket |
| - | - | - | - | - | - |
| Free | `20,000/day` and `200,000/mo` | No overage | `1 req/sec` | `5 min` | No |
| Starter | `25,000,000/mo` | Opt-in at `$0.00001225/pt` | `2 req/sec` | `60 sec` | No |
| Pro | `125,000,000/mo` | Opt-in at `$0.00000745/pt` | `5 req/sec` | `30 sec` | No |
| Ultra | `500,000,000/mo` | Opt-in at `$0.00000499/pt` | `10 req/sec` | Real-time | Yes |
| Super | `1,250,000,000/mo` | Opt-in at `$0.00000325/pt` | `15 req/sec` | Real-time | Yes |
| Mega | `2,500,000,000/mo` | Opt-in at `$0.00000250/pt` | `20 req/sec` | Real-time | Yes |
| Max | `12,500,000,000/mo` | Opt-in at `$0.00000125/pt` | `50 req/sec` | Real-time | Yes |
| Enterprise | Custom | Custom | Custom | Real-time | Yes |

> [!NOTE]
>
> Sportsbook coverage, periods, history access, and other entitlements also vary by tier. Two to be aware of: **player prop markets require Starter or higher** (Free keys do not receive them), and **live game state, play-by-play, and live game-stat streams require Ultra or higher**. The live response headers are the best way to confirm what a specific API key can access right now. New-account stats access uses separate effective feature fields; see [Stats Access](https://docs.therundown.io/guides/stats-access.md).

## History window

Your plan's history window applies to **any request that names a date**, including `GET /api/v2/sports/{sportID}/events/{date}`.

| Plan | History window |
| - | - |
| Free | 7 days |
| Starter | 7 days |
| Pro | 30 days |
| Ultra | 90 days |
| Super | 6 months |
| Mega | 1 year |
| Max | Unlimited |

On Free, the 7-day window covers dated event and score requests only; odds-history endpoints start on Starter. See the [API pricing page](https://therundown.io/pricing/api) for plan details.

> [!WARNING]
>
> A dated request gates **events, scores, and odds together**. An odds-history allowance is not separate from results availability on those requests. **Lookups through `GET /api/v2/events/{eventID}` are not windowed**: use an event ID to retrieve a completed event and its period scores regardless of the plan's history window. The opening-line and closing-line routes for an event still apply an event-date gate.

The cutoff is floored to **midnight UTC**. The `offset` parameter does not shift it. A request outside the window returns `403 Forbidden` with this body shape:

```json theme={null} theme={null}
{
  "earliest_available_date": "2026-08-09",
  "error": "Your plan includes 30 days of history; 2026-01-18 is older than the earliest available date (2026-08-09)",
  "history_days_limit": 30,
  "upgrade_url": "/pricing/api"
}
```

Read `earliest_available_date` and `history_days_limit` from the response instead of calculating the boundary yourself. For older results, fetching by event ID is the supported path. Save the `event_id` values from event responses so you can use `GET /api/v2/events/{eventID}` later; see [Scores and Results](https://docs.therundown.io/guides/scores-and-results.md).

## Weekly Billing

Every paid API tier is also available on a **weekly billing cadence** for workloads that don't need a month-long commitment — for example, covering a single tournament or a few weeks of a season. Weekly plans are priced at a premium over the equivalent monthly plan (the commitment ladder is weekly > monthly > annual).

On a weekly plan, your included data points are a **proportional weekly share** of the tier's monthly allowance (monthly × 12 ÷ 52 — e.g. Starter weekly includes `5,769,231` data points per week), metered over your 7-day billing window. Overage beyond the weekly allowance is billed at the same per-data-point rates as the monthly tier.

The primary usage headers tell you which window applies to your key: `X-Datapoints-Period` reports `weekly` on weekly-billed plans (with `X-Datapoints-Reset` marking the end of the current 7-day window), `monthly` on monthly and annual plans, and `daily` on the Free tier. Free responses also include companion `X-Datapoints-Monthly-*` headers so you can monitor both enforced windows.

## Usage Headers

Metered responses include usage and entitlement headers you can surface in logs, dashboards, and upgrade prompts. Keys with an active plan also receive the `X-Datapoints-*` window headers and entitlement headers on non-billable responses; only `X-Datapoints` itself is omitted when a response costs zero.

| Header | Description |
| - | - |
| `X-Datapoints` | Data points consumed by this response |
| `X-Datapoints-Used` | Total data points used in the current billing window |
| `X-Datapoints-Remaining` | Included data points remaining before the next reset |
| `X-Datapoints-Limit` | Included data points for the current window |
| `X-Datapoints-Period` | Cadence of the quota window: `daily` (Free tier), `weekly` (weekly-billed plans), or `monthly` |
| `X-Datapoints-Reset` | ISO 8601 timestamp for the current usage window reset |
| `X-Datapoints-Monthly-Used` | Free-tier data points used in the current UTC calendar month |
| `X-Datapoints-Monthly-Remaining` | Free-tier monthly data points remaining before the next reset |
| `X-Datapoints-Monthly-Limit` | Free-tier UTC calendar-month cap (`200000`) |
| `X-Datapoints-Monthly-Reset` | Start of the next UTC calendar month; omitted on plans without a second monthly cap |
| `X-Datapoints-Credit-Balance` | Bonus data-point credits applied on top of the allowance, when present |
| `X-Datapoints-Credit-Expiry` | Expiry timestamp for the credit balance, when present |
| `X-Tier` | Current subscription tier |
| `X-Rate-Limit` | Allowed requests per second for this key |
| `X-Data-Delay-Seconds` | Delay applied to returned data for this key |
| `X-Bookmakers` | Sportsbook IDs this key can access, or `all` |
| `X-Periods` | Period IDs this key can access, or `all` |
| `X-History-Access` | Whether this key can access historical line data |
| `X-Live-Odds-Access` | Whether this key can access live odds |
| `X-Websocket-Access` | Whether this key can connect to WebSocket feeds |
| `X-Stats-Policy-Version` | Effective stats policy: `0` for legacy behavior or `1` for the new-account policy |
| `X-Stats-Game-Access` | Whether completed current-season event boxes are available |
| `X-Stats-Season-Access` | Whether current-season aggregates are available |
| `X-Stats-History-Access` | Whether this key can access available prior-season archives |
| `X-Stats-Live-Access` | Whether in-progress REST event boxes are available |
| `X-Stats-Evaluation-Active` | Whether a new Free account's stats evaluation is active, when present |
| `X-Stats-Evaluation-Expires-At` | New Free-account evaluation expiry as an ISO 8601 timestamp, when present |

```bash theme={null}
curl --fail -i -H "X-TheRundown-Key: YOUR_API_KEY" \
  "https://therundown.io/api/v2/sports/4/events/2026-02-26?market_ids=1,2,3&affiliate_ids=19,23&main_line=true&offset=300"
```

Example headers:

```text theme={null}
X-Datapoints: 452
X-Datapoints-Used: 120348
X-Datapoints-Remaining: 24879652
X-Datapoints-Limit: 25000000
X-Datapoints-Period: monthly
X-Datapoints-Reset: 2026-03-31T00:00:00Z
X-Tier: starter
X-Rate-Limit: 2
X-Data-Delay-Seconds: 60
X-Bookmakers: 19,22,23
X-Periods: all
X-History-Access: true
X-Live-Odds-Access: true
X-Websocket-Access: false
```

> [!NOTE]
>
> On `429` responses caused by billing caps, the billing headers remain useful. Read `Retry-After` and the `X-Datapoints-*` headers before deciding whether to retry or upgrade.

## Understanding `429 Too Many Requests`

Not every `429` means the same thing. There are three common cases.

### 1. Burst rate limit exceeded

You sent too many requests in a short interval for your tier.

```json theme={null}
{
  "error": "Rate limit exceeded",
  "limit": 2,
  "upgrade_url": "/pricing/api",
  "upgrade_message": "You've exceeded your plan's rate limit. Upgrade for a higher requests-per-second limit."
}
```

* Look at `Retry-After` before retrying.
* Queue or batch work instead of firing many concurrent requests.
* Switch recurring update loops to delta polling or WebSocket where appropriate.

### 2. Daily data-point cap reached

This is the free-tier hard cap.

```json theme={null}
{
  "error": "Daily data point limit reached",
  "limit": 20000,
  "used": 20000,
  "upgrade_url": "/pricing/api",
  "upgrade_message": "You've hit the free tier's daily limit. Upgrade to a paid plan for a higher monthly allowance and rate limits."
}
```

* `Retry-After` tells you how long until the next daily window begins.
* `X-Datapoints-Remaining` will be `0`.
* The fix is to wait for reset or move to a paid plan.

### 3. Monthly data-point cap reached

This appears when a Free key reaches its `200,000` UTC calendar-month cap, or when a paid account reaches a configured monthly hard cap.

```json theme={null}
{
  "error": "Monthly data point limit reached",
  "limit": 200000,
  "used": 200000,
  "period": "monthly",
  "upgrade_url": "/pricing/api",
  "upgrade_message": "You've reached your plan's monthly data-point limit. Upgrade for a higher allowance."
}
```

* Treat this as a billing-window issue, not a short retry.
* Read `Retry-After` and `X-Datapoints-Monthly-Reset` on Free keys; paid plans use `X-Datapoints-Reset`.
* If this is unexpected on a paid account, contact support with the response headers.

## Best Practices

### Filter aggressively

The biggest usage lever is almost always response shape. Start every integration by narrowing:

* `market_ids`
* `affiliate_ids`
* `event_ids`
* `main_line=true`
* `hide_closed_markets=1` where available

### Use delta endpoints for ongoing updates

Instead of fetching the full event list repeatedly, bootstrap once and poll:

* `GET /api/v2/delta` for changed event objects
* `GET /api/v2/markets/delta` for individual price changes

See the [Efficient Polling guide](https://docs.therundown.io/guides/efficient-polling.md) for the full pattern.

### Use WebSocket on real-time tiers

For live screens, line-movement monitoring, and live box scores, WebSocket is usually the best delivery model once your plan includes it. It avoids HTTP burst limits, but you should still keep subscriptions tight because pushed messages are metered.

### Cache reference data

Sports, affiliates, teams, and market definitions change far less often than live odds. Cache them locally and refresh on a longer interval.

### Alert before users run out

If you are building on behalf of end users or internal analysts, instrument alerts when usage reaches `70%`, `85%`, and `100%` of included data points. The headers above make this straightforward.

## Need More Throughput?

If your workload needs more data points, higher burst limits, or real-time access, contact support at **[support@therundown.io](mailto:support@therundown.io)** or use your dashboard. Include:

* Your API key (or the email associated with your account)
* Your current tier
* Approximate data-point volume per day or month
* Required requests-per-second ceiling
* Whether you need WebSocket, historical data, or broader sportsbook coverage
* A short description of your application or workload


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.