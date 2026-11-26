# 欧联和欧协联原始盘口时钟核查

北京时间 11 月 26 日，复核原冻结的 36 场比赛。将原 R5 冻结引用的 11 月 23 日 ESPN 比分板，和 11 月 26 日保存的 ESPN 比分板及逐场赛前摘要，按比赛 ID、主客、赛段、开球和 DraftKings 机构 ID 逐场对齐。三个来源各有 35/36 场同时提供完整三项胜平负、大小球盘线及两侧价格，均缺可核验机构报价时间。帕福斯对中日德兰保持报价缺项。查询时钟单列保存。[逐场回放](audit.json)

| DraftKings 报价观察 | 欧协联 18 场 | 欧联 18 场 |
| --- | ---: | ---: |
| 原比分板与 11 月 26 日比分板，大小球盘线不同 | 4 | 1 |
| 原价观察至 11 月 26 日比分板，大小球同线但价格不同 | 13 | 16 |
| 11 月 26 日比分板至同日逐场摘要，大小球盘线不同 | 1 | 0 |
| 11 月 26 日比分板至同日逐场摘要，大小球同线但价格不同 | 3 | 3 |

逐场摘要比当天比分板晚约 2 分 25 秒至 5 分 15 秒采集。索菲亚中央陆军对特拉布宗体育的同一机构，在比分板显示 3.5，逐场摘要显示 2.5。两项赛事各有一场的三项胜平负报价在这两份响应中也不同。以上仅记录这些响应的可见差异，价格在机构端发生变化的时刻仍缺证据。原首次预测引用的盘线由其原回执核实。[36 场比分首版及原始快照](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/77)

- ESPN Sports Core 的两场欧联抽样均返回 DraftKings 及 Bet365 完整胜平负和同机构全场大小球。四个机构对象以及单独的 DraftKings 对象均缺明确机构报价时间。下一轮的阿尔克马尔对格拉茨风暴样本返回 HTTP 200，报价集合为空。11 月 26 日保存的下一轮完整赛历中，两项赛事各 18 场的 DraftKings 对象均为空。[Core 获取清单](sources/espn-core.json) · [市场字段](sources/espn-bookmaker-fields.json)
- ESPN 链接指向的 DraftKings 公开赛事页收到 HTTP 403。澳客 `.com` 欧协联公开页列出平均初赔、指定机构的胜平负初赔和亚洲让球初盘选项，本次可见字段缺全场大小球及机构报价时间。[DraftKings 请求记录](sources/draftkings-direct-request.json) · [澳客可见字段](sources/okooo-selector.json)

北京时间 18:12，按澳客公开页面的选择器请求凯拉特对米亚尔比的 bet365 胜平负初赔。HTTP 200 响应的正文为验证码页，机构初赔和报价时点仍待取得。当前取证保留请求及响应哈希，时间是验证码页收到时刻。[澳客具名市场实测](sources/okooo-named-request.json)

当前已归档原首版的严格时钟盘口为欧协联 0/18、欧联 0/18。每个正式窗口的盘线覆盖要求沿用原登记。两项赛事的比分、三选与原精选席位已可在有真实赛果时复盘。[正式指标与赛程登记](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/77) · [首版复盘入口](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/78)

从数据仓库根目录使用 Python 3.12.14 及固定源码的运行依赖复算。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/01bf68219b3ff7d9108f1fd710078e43cd5e8ddc)

```bash
folder=workspace-updates/20261126-europe-market-source-clocks
(cd "$folder" && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/Football-Analysis/runtime python -B "$folder/audit.py" > /tmp/euro-market-audit.json
cmp "$folder/audit.json" /tmp/euro-market-audit.json
```
