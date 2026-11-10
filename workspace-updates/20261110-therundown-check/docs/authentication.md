> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Authenticate and Start Calling the API in Minutes

> Learn how to authenticate your requests to TheRundown API using API keys.

Authenticate server-side requests with your API key in the `X-TheRundown-Key`
header. Keep the key in a private environment variable; never place it in a URL,
prompt, browser bundle, mobile app bundle, or public repository. Once the key
works, the [odds API quickstart](https://therundown.io/odds-api) walks through a
first scoped request and its billed data points.

## Header authentication

Pass your API key in the `X-TheRundown-Key` request header from a server-side
application.

```
X-TheRundown-Key: $THERUNDOWN_API_KEY
```

## Code Examples

```bash curl theme={null}
curl --fail -H "X-TheRundown-Key: $THERUNDOWN_API_KEY" \
  "https://therundown.io/api/v2/markets"
```

```python Python theme={null}
import os
import requests

API_KEY = os.environ["THERUNDOWN_API_KEY"]
BASE_URL = "https://therundown.io/api/v2"

# Using header authentication (recommended)
headers = {
    "X-TheRundown-Key": API_KEY
}

response = requests.get(f"{BASE_URL}/markets", headers=headers)
response.raise_for_status()
data = response.json()

print(data)
```

```javascript JavaScript theme={null}
const API_KEY = process.env.THERUNDOWN_API_KEY;
if (!API_KEY) throw new Error("Set THERUNDOWN_API_KEY");
const BASE_URL = "https://therundown.io/api/v2";

// Using header authentication (recommended)
const response = await fetch(`${BASE_URL}/markets`, {
  headers: {
    "X-TheRundown-Key": API_KEY,
  },
});

if (!response.ok) throw new Error(`HTTP ${response.status}`);
const data = await response.json();
console.log(data);
```

## Compatibility

Use header authentication for new and updated integrations. The OpenAPI
contract retains query authentication for compatibility with existing clients,
including the legacy V1 reference.

## WebSocket authentication

V2 WebSocket clients authenticate the upgrade request with the same
`X-TheRundown-Key` header from a server-side environment variable. Native
browser `WebSocket` clients cannot set custom headers; connect browsers to an
authenticated backend relay, which keeps the key on your server. WebSocket
access requires an Ultra plan or higher.

## Public Endpoints

The following endpoints do **not** require authentication and can be called without an API key:

| Endpoint | Description |
| - | - |
| `GET /api/v2/sports` | Returns the list of available sports and their IDs. |
| `GET /api/v2/affiliates` | Returns the list of available sportsbook affiliates. |

These endpoints are useful for bootstrapping your application with reference data before making authenticated requests.

## Security Best Practices

> [accordion] Never expose keys in client-side code
>
> API keys embedded in frontend JavaScript, mobile app bundles, or public repositories can be extracted by anyone. Always route API calls through your own backend server.

> [accordion] Use environment variables
>
> Store your API key in an environment variable rather than hardcoding it in source files. This prevents accidental commits to version control and makes key rotation straightforward.
>
> ```bash theme={null}
> # .env file (never commit this)
> THERUNDOWN_API_KEY=YOUR_API_KEY
> ```
>
> ```python Python theme={null}
> import os
> api_key = os.environ["THERUNDOWN_API_KEY"]
> ```
>
> ```javascript Node.js theme={null}
> const apiKey = process.env.THERUNDOWN_API_KEY;
> ```

> [accordion] Rotate keys if compromised
>
> If you suspect your API key has been exposed, contact TheRundown support immediately to rotate your key. Update all services that reference the old key as part of the rotation.

> [accordion] Use separate keys per environment
>
> Maintain distinct API keys for development, staging, and production. This limits the blast radius if a non-production key is leaked and makes it easier to track usage per environment.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.