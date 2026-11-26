# 历史盘口时间与公开来源核验

11 月 23 日报告的 80 场和补充 6 场均已逐场重读。两场巴甲从 11 月 15 日独立旧包补回。86 场都能和原赛前冻结、Pinnacle 胜平负三项、同盘线大小球两侧以及原始 `last_update` 一一对应。时间字段来自 The Odds API 保存的具名市场对象。每场较新的市场更新时间比采集早约 0.5 至 29.4 秒，两项市场的更新时间均在原决策截止前一小时内。复算全程读取项目已有归档。[原 80 场报告](../20261123-kpi-optimization/README.md) · [巴甲旧包](../20261115-remaining-nations-brazil/README.md) · [逐场核验](history.json)

| 本轮公开来源 | 实测 | 同机构完整胜平负及大小球 |
| --- | --- | ---: |
| Oddschecker，桑德兰对雅盖隆 | 北京时间 16:58 取得 HTTP 200 和原始页面。胜平负有 24 家传统机构，另有 2 家交易所 | 0 家 |
| BetExplorer，欧协联赛事入口 | 北京时间 16:56 请求后转到站点根页并返回 HTTP 503 | 0 场确认 |

Oddschecker 每个胜平负报价对象带 UTC `betFeedTimestamp`，逐选项的值可不同。10bet 与 Unibet 的三个字段都落在采集前一小时内，字段的上游时间语义待核。该响应有 `Total Goals Over/Under` 和 `Asian Total` 两个市场目录项，实际赔率行均为 0。正常 Chromium 打开同页遇到证书校验错误，页面内的大小球数据待核。样本采集晚于已冻结的欧联首版。项目后续继续按原协议核对同一机构、真实盘线、双侧报价和各自的数据截止。[公开来源取回与逐项报价](public-probes.json) · [欧联首版](../20261126-europe-first-display/README.md)

北京时间 17:55 沿网站索引的公开链接复查贝西克塔斯对贝尔谢巴工人，赛事页返回 HTTP 200。原响应的 William Hill 与 bet365 均有三项胜平负及各自的时间字段。两个大小球目录的价格行均为 0，字段对应的机构报价时间仍待核。这次观察在欧联原首版冻结之后，原截止的严格盘口仍待核。[赛事身份、原响应哈希和逐项报价](oddschecker-besiktas-followup.json)

北京时间 18:39，OddsPortal 的欧联入口及同一场贝西克塔斯比赛的公开链接均返回 HTTP 200。原文可核开球时刻与格鲁吉亚巴统场地，本次响应的具名盘口、大小球两侧和报价时间仍缺。保留两份响应的采集时刻与哈希。[OddsPortal 原响应核验](oddsportal-besiktas-followup.json)

北京时间 20:29，SportyTrader 的公开赛事页实际显示贝西克塔斯对贝尔谢巴工人的全场胜平负和多条总球线。同机构两类市场在大小 2.5 有 8 家，在原首版引用的大小 3.5 有 11 家。以 Bet365 的 3.5 为例，大小两侧为 2.00 和 1.80，对应胜平负为 1.25、6.50、9.50。页面以比赛日期、赛事和双方名称连接官方赛程，准确开球和机构报价时钟在该页缺失。保存原始 HTML 响应的完整哈希和两条具名市场的结构化摘录。[公开页原文](https://www.sportytrader.com/en/odds/besiktas-jk-hapoel-beer-sheva-8787007/) · [市场字段与时钟核查](sources/sportytrader-besiktas.json)

北京时间 20:31，5Dollar 以既有 Community 权限取得鹿岛鹿角对冈山绿雉的单场 Bet365 报价。5Dollar 比赛编号 1866646530 与原日职联首版的主客和 11 月 28 日 14:00 开球对齐。胜平负开盘 `opened_at` 为前一天 21:19，收到响应时已约 23 小时 12 分钟。`closing` 的胜平负报价以及大小 2.5 的开盘和 `closing` 都缺报价时钟。此前存档的七个联赛每项一场也有同机构完整胜平负和大小球，七场所核对的市场对象均无明确报价时钟。[当前接口记录](sources/fivedollar/recent/03-odds-metadata.json) · [原日职联首版](../20261126-r26-j1-first-stage/README.md) · [早期和近期接口复算](recent-source-results.json)

两次当前报价观察均晚于对应原首版截止。正式盘线时间覆盖以原冻结及可核验机构时钟结算。[欧联首版](../20261126-europe-first-display/README.md)

在本目录运行 `python -B audit_history.py` 即可复算历史逐场来源与时间，固定输入为数据仓内的两份原始打包文件。公开网站的原响应留在本次采集目录。`python -B audit_public.py --probe-root /workspace/europe-20261126-intake/strict-market-probe` 可从本次取回的响应重建 `public-probes.json`。两份输出各经两次本地复跑逐字节比对。[校验清单](SHA256SUMS)

`python -B audit_recent_sources.py` 读取归档的原接口响应和核实过的公开表格，复算两类市场的同机构覆盖以及可用时间字段。5Dollar 当前响应采用采集端已脱敏的 JSON，分别保留采集时刻和脱敏文件哈希。[近期复算结果](recent-source-results.json)
