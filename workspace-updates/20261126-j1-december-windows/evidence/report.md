HELLO BOSS

# J1 2026-12-12/13 赛历核对

本轮仅发送2次指定的公开 ESPN GET，每个日期一次，未重试，也未访问其他网络来源。两份响应均为 HTTP 200；请求间隔超过1秒。所有时间以下均为北京时间。

## 查询与存档

| ESPN 查询 | 查询时间（北京时间） | HTTP | 响应 SHA-256 |
|---|---|---:|---|
| `https://site.api.espn.com/apis/site/v2/sports/soccer/jpn.1/scoreboard?dates=20261212` | 2026-11-26T13:36:50.760173+08:00 | 200 | `8c2862ac3d38d745ab7f0cbaaa9a9eb9c66f74ecc57c01a034e989eb8ab18ed7` |
| `https://site.api.espn.com/apis/site/v2/sports/soccer/jpn.1/scoreboard?dates=20261213` | 2026-11-26T13:36:54.280872+08:00 | 200 | `2081f37742258d97429db7a47426c7f5409cbe98f96f56808c7de2c9e942d61e` |

原年度赛历为原始归档中的 `raw/espn_calendar_2026.json`，SHA-256 `88ae1a444b952f521beda041b3c8cc4784421e88484032a3450e9075fb0c2fa4`。当前原始响应保存在 `raw/20261212.json`、`raw/20261213.json`。[原始归档](../../20261125-j1-stage-windows/evidence/prematch-07.tar.gz)

## 两日10场逐场核对

两个 ESPN 日期响应合计返回10场，10个event ID均存在年度赛历，双方球队ID、主客顺序、北京时间开球和 regular-season 阶段全部一致；每场当前赛前状态均为 `STATUS_SCHEDULED` / `pre`。10个开球时间均落在北京时间12月12日00:00至12月14日00:00区间，共覆盖20支唯一球队。未发现延期或赛程/身份变更。ESPN 的 `dates=20261212` 响应中含有一场北京时间12月13日12:00开球的事件（401877507）；按指定北京时间窗口合并两响应评估完整性，未按 `dates` 参数将其误归至北京时间12日。

| 北京时间 | Event ID | 主队 (ID) | 客队 (ID) | 阶段 | 当前状态 |
|---|---|---|---|---|---|
| 2026-12-12T13:00:00+08:00 | 401877495 | Cerezo Osaka (7109) | Machida Zelvia (22167) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-12T13:00:00+08:00 | 401877519 | Shimizu S-Pulse (7104) | Vissel Kobe (7477) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-12T15:00:00+08:00 | 401877496 | Gamba Osaka (7102) | Tokyo Verdy 1969 (3393) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T12:00:00+08:00 | 401877507 | Yokohama F. Marinos (7116) | V-Varen Nagasaki (19001) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T13:00:00+08:00 | 401877505 | Sanfrecce Hiroshima (7114) | Kashima Antlers (7115) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T13:00:00+08:00 | 401877506 | Fagiano Okayama (22522) | Kashiwa Reysol (7476) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T13:00:00+08:00 | 401877517 | Kyoto Sanga (21361) | JEF United Ichihara-Chiba (7111) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T14:00:00+08:00 | 401877504 | Avispa Fukuoka (7107) | FC Tokyo (3384) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T14:00:00+08:00 | 401877508 | Urawa Red Diamonds (3385) | Kawasaki Frontale (7112) | 14287 / regular-season | STATUS_SCHEDULED / pre |
| 2026-12-13T14:00:00+08:00 | 401877518 | Nagoya Grampus (7108) | Mito Hollyhock (131701) | 14287 / regular-season | STATUS_SCHEDULED / pre |

## 上一轮赛历核验

12 月 4–6 日的 10 场复用上一轮已存赛历，与原年度赛历逐场一致。上一轮逐场摘要已补核 401877522、401877514 的时刻、球队与常规赛阶段。[上一轮赛历](../../20261126-r26-j1-first-stage/evidence/full-window-calendar.json)

## 交付文件

- `request-manifest.json`：两次GET的URL、实际抓取时钟、状态、响应大小和SHA-256。
- `raw/`：两份原始JSON响应。
- `normalized-fixtures.json`：从当前赛历提取的规范化10场及匹配字段。
- `comparison.json`：与年度赛历逐场核对结果及完整性断言。
- 文件校验清单包含本目录全部证据的 SHA-256。[校验清单](../SHA256SUMS)
