> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Your Free API Key and Make Your First Call

> Make your first authenticated sports odds API request, read usage headers, and choose REST or Ultra+ WebSocket. Free uses delayed pre-match data.

## 1. Get your API key

Sign up at [therundown.io/api](https://therundown.io/api) to get your API key,
then store it in the private `THERUNDOWN_API_KEY` environment variable of your
server-side application.

## 2. Make your first request

```bash cURL theme={null}
curl --fail -H "X-TheRundown-Key: $THERUNDOWN_API_KEY" \
  "https://therundown.io/api/v2/sports"
```

```python Python theme={null}
import requests
import os

response = requests.get(
    "https://therundown.io/api/v2/sports",
    headers={"X-TheRundown-Key": os.environ["THERUNDOWN_API_KEY"]},
)
response.raise_for_status()
print(response.json())
```

```javascript Node.js 22+ (ESM) theme={null}
const apiKey = process.env.THERUNDOWN_API_KEY;
if (!apiKey) throw Error('Set THERUNDOWN_API_KEY');

const response = await fetch(
  "https://therundown.io/api/v2/sports",
  {
    headers: { "X-TheRundown-Key": apiKey },
  }
);
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const data = await response.json();
console.log(data);
```

```go Go theme={null}
package main

import (
    "fmt"
    "io"
    "log"
    "net/http"
    "os"
)

func main() {
    if err := run(); err != nil {
        log.Fatal(err)
    }
}

func run() error {
    apiKey := os.Getenv("THERUNDOWN_API_KEY")
    if apiKey == "" {
        return fmt.Errorf("Set THERUNDOWN_API_KEY")
    }

    req, err := http.NewRequest(http.MethodGet, "https://therundown.io/api/v2/sports", nil)
    if err != nil {
        return err
    }
    req.Header.Set("X-TheRundown-Key", apiKey)

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return err
    }
    _, err = fmt.Println(string(body))
    return err
}
```

```ruby Ruby theme={null}
require 'net/http'
require 'json'

uri = URI("https://therundown.io/api/v2/sports")
req = Net::HTTP::Get.new(uri)
req["X-TheRundown-Key"] = ENV.fetch("THERUNDOWN_API_KEY")

response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) do |http|
  http.request(req)
end

puts JSON.parse(response.body)
```

> [!NOTE]
>
> Some reference endpoints are public, but authenticating from the start lets you see the same headers and behavior your production integration will use.

You'll receive a list of available sports with their IDs. A shortened example:

```json theme={null}
{
  "sports": [
    { "sport_id": 1, "sport_name": "NCAA Football" },
    { "sport_id": 2, "sport_name": "NFL" },
    { "sport_id": 3, "sport_name": "MLB" },
    { "sport_id": 4, "sport_name": "NBA" },
    { "sport_id": 5, "sport_name": "NCAA Men's Basketball" },
    { "sport_id": 6, "sport_name": "NHL" },
    { "sport_id": 38, "sport_name": "ATP" },
    { "sport_id": 39, "sport_name": "WTA" }
  ]
}
```

## 3. Get today's MLB odds

> [!NOTE]
>
> These examples use the current UTC date. The `offset` parameter shifts the date boundary so a "day" aligns with the timezone you care about instead of midnight UTC. When you use an offset, choose the date for that same market-day boundary. A date with no events can simply be outside the season or schedule; check [available dates](https://docs.therundown.io/api-reference/generated/v2-sports/get-available-dates-for-a-sport.md) before treating it as a coverage gap.

```bash cURL theme={null}
TODAY_UTC=$(date -u +%F)

curl --fail -H "X-TheRundown-Key: $THERUNDOWN_API_KEY" \
  "https://therundown.io/api/v2/sports/3/events/$TODAY_UTC?market_ids=1,2,3,41,42,43&affiliate_ids=19,23&main_line=true"
```

```python Python theme={null}
import requests
from datetime import datetime, timezone
import os

today_utc = datetime.now(timezone.utc).date().isoformat()

response = requests.get(
    f"https://therundown.io/api/v2/sports/3/events/{today_utc}",
    headers={"X-TheRundown-Key": os.environ["THERUNDOWN_API_KEY"]},
    params={
        "market_ids": "1,2,3,41,42,43",  # Full-game prematch and in-play core
        "affiliate_ids": "19,23",
        "main_line": "true",
    }
)

response.raise_for_status()

for event in response.json()["events"]:
    teams = event["teams"]
    print(f"{teams[0]['name']} @ {teams[1]['name']}")
    for market in event.get("markets", []):
        print(f"  {market['name']}")
        for participant in market["participants"]:
            for line in participant["lines"]:
                for aff_id, price in line["prices"].items():
                    print(f"    {participant['name']}: {price['price']}")
```

```javascript Node.js 22+ (ESM) theme={null}
const today = new Date().toISOString().split("T")[0];
const apiKey = process.env.THERUNDOWN_API_KEY;
if (!apiKey) throw Error('Set THERUNDOWN_API_KEY');

const response = await fetch(
  `https://therundown.io/api/v2/sports/3/events/${today}?market_ids=1,2,3,41,42,43&affiliate_ids=19,23&main_line=true`,
  {
    headers: { "X-TheRundown-Key": apiKey },
  }
);
if (!response.ok) throw new Error(`HTTP ${response.status}`);
const data = await response.json();

for (const event of data.events) {
  console.log(`${event.teams[0].name} @ ${event.teams[1].name}`);
  for (const market of event.markets || []) {
    console.log(`  ${market.name}`);
  }
}
```

> [!NOTE]
>
> This MLB example uses the explicit full-game core scope. For soccer, NHL regulation-time, tennis, futures, and every current sport ID, see the [recommended core market scopes](https://docs.therundown.io/reference/sports.md#recommended-core-market-scopes). In production, `market_ids`, `affiliate_ids`, and `main_line=true` are your biggest levers for controlling payload size and data-point usage.

Fetch `GET /api/v2/affiliates` instead of hard-coding the source roster. Current IDs include BookMaker (`7`), BetCRIS (`9`), Circa Sports (`32`), Bet105 (`33`), and Heritage Sports (`34`). Availability varies by source, sport, and market; see [Sportsbook IDs](https://docs.therundown.io/reference/sportsbooks.md) for the complete current mapping.

## Opening and closing snapshots

Historical snapshots require a plan with historical access. Opening snapshots return the earliest recorded price for each available line and sportsbook. Closing snapshots return the latest recorded price at or before scheduled event start; a closing snapshot queried before start is provisional. Both are returned in an `events` array, even for one event.

Use `https://therundown.io` with the full `/api/v2/events/{eventID}/closing` path. If your client already uses `https://therundown.io/api/v2` as its base URL, append only `/events/{eventID}/closing`. The final URL contains `/api` exactly once.

```bash theme={null}
curl --fail -H "X-TheRundown-Key: $THERUNDOWN_API_KEY" \
  "https://therundown.io/api/v2/events/ebb2dc1a9b7c2e32c4468da5ba60a526/closing?market_ids=11,12&affiliate_ids=19,23"
```

Replace the event ID with one within your plan's history window. For all parameters and response shapes, see the [event opening reference](https://docs.therundown.io/api-reference/generated/v2-events/get-opening-prices-for-an-event.md), [event closing reference](https://docs.therundown.io/api-reference/generated/v2-events/get-closing-prices-for-an-event.md), and [historical odds guide](https://docs.therundown.io/guides/historical-odds.md).

## 4. Choose your update path

For a plan with explicitly confirmed zero data delay, bootstrap with a narrow event snapshot and reuse its valid `meta.delta_last_id` cursor for market-delta polling. Do not start with `last_id=0`; see [Efficient Polling](https://docs.therundown.io/guides/efficient-polling.md) for the bounded bootstrap and recovery flow. Delayed plans use repeated narrow snapshots instead.

If your server-side key has `X-Websocket-Access: true`, you can connect to the
WebSocket feed for real-time updates. WebSocket access requires an Ultra plan
or higher. Run this in Node.js 22+ ESM (`.mjs` or `"type": "module"`) and
install [`ws`](https://www.npmjs.com/package/ws) with `npm install ws` on your
server; browser `WebSocket` clients cannot set this authentication header and
should connect to your authenticated backend relay instead.

```javascript Node.js 22+ (ESM) theme={null}
import WebSocket from "ws";
const apiKey = process.env.THERUNDOWN_API_KEY;
if (!apiKey) throw Error('Set THERUNDOWN_API_KEY');

const ws = new WebSocket(
  "wss://therundown.io/api/v2/ws/markets?sport_ids=4",
  { headers: { "X-TheRundown-Key": apiKey } }
);

ws.on("message", (raw) => {
  const msg = JSON.parse(raw.toString());
  if (msg.meta?.type === "heartbeat") return;
  const d = msg.data;
  console.log(`Price update: event=${d.event_id} market=${d.market_id} price=${d.price}`);
});
```

> [!NOTE]
>
> If your key does not have WebSocket access, use market delta polling instead.

## Next steps

Choose an integration guide for [sports data](https://therundown.io/sports-data-api), [sports odds](https://therundown.io/sports-odds-api), [live odds](https://therundown.io/live-odds-api), [betting tools](https://therundown.io/sports-betting-api), [scores](https://therundown.io/sports-scores-api) or [free sports data](https://therundown.io/free-sports-data-api), or follow the [odds API quickstart](https://therundown.io/odds-api) to a first measured request. Review [API pricing and licensed use](https://therundown.io/pricing/api) before publishing customer-facing data.

> [card] [Authentication](https://docs.therundown.io/authentication.md)
>
> Learn about all auth methods

> [card] [Rate Limits](https://docs.therundown.io/rate-limits.md)
>
> Understand data points and `429` responses

> [card] [Building an Odds Screen](https://docs.therundown.io/guides/building-odds-screen.md)
>
> Step-by-step guide

> [card] [Efficient Polling](https://docs.therundown.io/guides/efficient-polling.md)
>
> Delta, caching, and cost control

> [card] [Market IDs Reference](https://docs.therundown.io/reference/markets.md)
>
> All market types and their IDs

> [card] [WebSocket Streaming](https://docs.therundown.io/guides/websocket-streaming.md)
>
> Real-time data guide


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.