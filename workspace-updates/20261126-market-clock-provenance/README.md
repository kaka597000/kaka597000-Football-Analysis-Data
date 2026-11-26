# 历史盘口时间与公开来源核验

11 月 23 日报告的 80 场和补充 6 场均已逐场重读。两场巴甲从 11 月 15 日独立旧包补回。86 场都能和原赛前冻结、Pinnacle 胜平负三项、同盘线大小球两侧以及原始 `last_update` 一一对应。时间字段来自 The Odds API 保存的具名市场对象。每场较新的市场更新时间比采集早约 0.5 至 29.4 秒，两项市场的更新时间均在原决策截止前一小时内。复算全程读取项目已有归档。[原 80 场报告](../20261123-kpi-optimization/README.md) · [巴甲旧包](../20261115-remaining-nations-brazil/README.md) · [逐场核验](history.json)

| 本轮公开来源 | 实测 | 同机构完整胜平负及大小球 |
| --- | --- | ---: |
| Oddschecker，桑德兰对雅盖隆 | 北京时间 16:58 取得 HTTP 200 和原始页面。胜平负有 24 家传统机构，另有 2 家交易所 | 0 家 |
| BetExplorer，欧协联赛事入口 | 北京时间 16:56 请求后转到站点根页并返回 HTTP 503 | 0 场确认 |

Oddschecker 每个胜平负报价对象带 UTC `betFeedTimestamp`，逐选项的值可不同。10bet 与 Unibet 的三个字段都落在采集前一小时内，字段的上游时间语义待核。该响应有 `Total Goals Over/Under` 和 `Asian Total` 两个市场目录项，实际赔率行均为 0。正常 Chromium 打开同页遇到证书校验错误，页面内的大小球数据待核。样本采集晚于已冻结的欧联首版。项目后续继续按原协议核对同一机构、真实盘线、双侧报价和各自的数据截止。[公开来源取回与逐项报价](public-probes.json) · [欧联首版](../20261126-europe-first-display/README.md)

北京时间 17:55 沿网站索引的公开链接复查贝西克塔斯对贝尔谢巴工人，赛事页返回 HTTP 200。原响应的 William Hill 与 bet365 均有三项胜平负及各自的时间字段。两个大小球目录的价格行均为 0，字段对应的机构报价时间仍待核。这次观察在欧联原首版冻结之后，原截止的严格盘口仍待核。[赛事身份、原响应哈希和逐项报价](oddschecker-besiktas-followup.json)

在本目录运行 `python -B audit_history.py` 即可复算历史逐场来源与时间，固定输入为数据仓内的两份原始打包文件。公开网站的原响应留在本次采集目录。`python -B audit_public.py --probe-root /workspace/europe-20261126-intake/strict-market-probe` 可从本次取回的响应重建 `public-probes.json`。两份输出各经两次本地复跑逐字节比对。[校验清单](SHA256SUMS)
