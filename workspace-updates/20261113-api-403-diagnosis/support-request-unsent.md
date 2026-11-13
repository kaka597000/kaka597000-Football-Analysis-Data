# 服务商支持材料（草稿，未发送）

请分别通过 API-Sports 和 TheRundown 的官方支持渠道提交本服务对应部分。下列时间均为北京时间 UTC+8；不包含密钥、账户标识或访客 IP。

## API-Football / API-Sports

Our authorized server-side Python request to `https://v3.football.api-sports.io/status` on 2026-11-13 at 10:08:05 (UTC+8) returned HTTP 403, `text/html; charset=UTF-8`, with the title `Attention Required! | Cloudflare` and Cloudflare Ray ID `a59a3a02986e2cc8-DFW`.

We used the documented GET method and `x-apisports-key` header. TLS verification remained enabled, the managed environment's normal proxy was retained, and redirects were disabled. No API JSON authentication, plan or quota error was obtained. Our environment reports the credential binding ready and the official API host permitted, but that does not verify the request as received by your infrastructure. Additional probes stopped when the challenge detector triggered.

Please investigate the Ray ID and time, identify the actual security feature/rule causing the denial, and confirm the supported server-to-server access requirements for this account. If an account-specific source restriction is relevant, please specify its supported configuration and verification procedure. We have not confirmed a stable egress IP and do not want to configure a guessed range. Please advise the service-side correction needed before we run one further protected-endpoint verification. No request to disable TLS or bypass your access controls is being made.

## TheRundown

Three bounded Python GET requests to the documented protected endpoint `https://therundown.io/api/v2/markets` on 2026-11-13 all returned HTTP 403, HTML, with `Attention Required! | Cloudflare`:

| Control | Request time (UTC+8) | Cloudflare Ray ID |
|---|---|---|
| Current authorized credential via `X-TheRundown-Key` | 10:02:43 | a59a32243e0e1c16-DFW |
| No credential | 10:02:48 | a59a32455f661c16-DFW |
| Deliberately invalid diagnostic value | 10:02:53 | a59a326689f81c16-DFW |

The requests were serial, at least five seconds apart, with TLS verification enabled, the normal managed proxy retained, and redirects disabled. No further event requests or retries were made. No JSON error, Retry-After or API usage fields were returned, so we cannot determine account authentication or entitlements from these responses.

Please investigate these Ray IDs and times, confirm the precise edge security rule and the supported remedy for an authorized server-to-server client, and advise whether any account-side configuration is required. We verified the host/header/endpoint against your current authentication guide and official Python SDK. We have not sent the key to an alternate host or relay. Please confirm when a single protected-endpoint verification is appropriate.
