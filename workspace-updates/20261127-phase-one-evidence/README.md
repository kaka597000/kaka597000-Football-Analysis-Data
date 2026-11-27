# 第一阶段证据接入与 PR 收敛

本轮按建议优先核查正式首版、实盘时间和两仓依赖，并将日职联的结算与盘口采集单独提交到当前 main 的审核线上。第一阶段逐赛事使用原登记目标与覆盖门槛。[源码 PR](https://github.com/kaka597000/Football-Analysis/pull/131) · [四阶段目标](https://github.com/kaka597000/Football-Analysis/blob/baac2b8342f557ac7913e0c45ad3ea2ed4861e5b/project-goals.json)

## 赛果和首版

| 日职联窗口，北京时间 | 原场次 | 核实实际开球 | 核实常规时间赛果 |
| --- | ---: | ---: | ---: |
| 11 月 25 日原件重放 | 7 | 7 | 7 |
| 11 月 28–29 日 | 10 | 0 | 0 |
| 12 月 4–6 日 | 10 | 0 | 0 |
| 12 月 12–13 日 | 10 | 0 | 0 |

11 月 25 日的官方赛中、完场页面保留实际开球的分钟区间。常规时间终场比分与 ESPN 逐场一致。后三窗绑定了官方赛前原件，状态以 11 月 27 日 11:50 重放。周末同一结果目录可复盘原 Current、Test、市场对照、R28／R42／R46／R49 各自的首版，以及原综合比分与三席精选。正式综合展示分母仍待原渠道提供独立首送及原文回读。原合格市场须使用各自签发时冻结的报价。[复算](verified.json) · [结果入口](https://github.com/kaka597000/Football-Analysis/blob/357b3377593c6f1ced4ff891c7f3d1a12395cdda/docs/j1-official-kickoff-proof.md)

## 盘口时点

11 月 27 日 11:46 的匿名公开探测匹配周末 10/10 场。逐行时钟距实际接收不超过一小时的同机构胜平负与双边全场大小球覆盖 10/10 场，共 59 个机构与赛事配对。横滨水手对 FC 东京的两份响应共有 21 个市场键，21 个价格行均相同且 `as_of` 更新。接口说明把响应包的时钟定义为已应用的最近上游更新，逐行字段仅给出类型。机构原生报价发布时间仍待来源确认。[采集原件与时点](market-probe/captures.json) · [逐场盘口覆盖](market-probe/coverage.json) · [同场时钟对照](market-probe/baseline-comparison.json) · [InferSports 接口说明](https://api.infersports.dev/openapi.json)

T−24h、T−6h、T−60min、T−15min 按每场独立截止、独立留存。以各节点真实具名市场行复核来源和年龄。已签发的首版仍引用签发时的原证据，后续节点与首发信息按各自版本结算。[盘口采集入口](https://github.com/kaka597000/Football-Analysis/blob/357b3377593c6f1ced4ff891c7f3d1a12395cdda/docs/j1-infersports-market-evidence.md)

11 月 27 日 12:04 首采和 12:08 复采使用 13:00 的 T−24h 截止。两次均匹配京都不死鸟对大阪樱花、清水心跳对浦和红钻的原赛程。两场最新市场行均为 11:00:06，距节点截止 7,194 秒。本轮节点合格同机构配对为 0/2，另八场尚未进入各自节点的采集区间。[首采回执](market-t24/receipts.json) · [复采回执](market-t24-recheck/receipts.json)

## PR 审核

北京时间 11 月 27 日 11:45 审核时，源码 58 个开放 PR 中有 48 个以另一个开放 PR 为基底，最长链 39 个。数据仓 80 个开放 PR 中有 73 个以另一个开放 PR 为基底，最长链 58 个。清单逐项保留真实分支、基底尖端、提交、当时的检查、上游及下游依赖。[两仓清单](pr-audit/inventory.json) · [修改文件与 blob](pr-audit/changed-files.json)

1. 源码 #76 已纳入 main 的独立首版回读和结算。日职联窗口、官方开球及市场采集在源码 #131 独立审核。该 PR 在真实运行资产下通过 25 套 1,203 项本地测试。[已合并的 #76](https://github.com/kaka597000/Football-Analysis/pull/76) · [日职联 #131](https://github.com/kaka597000/Football-Analysis/pull/131)
2. #71 的四个改动文件已在 #74 第一提交以同名同 blob 出现，登记为可归档候选。#51 仍是 #74 的实际基底。数据仓 #45、#46、#50、#51 的文件已完整出现在 #61 中，四个 PR 仍有下游依赖。[逐文件比对](pr-audit/carry-71.tsv) · [源码 #74](https://github.com/kaka597000/Football-Analysis/pull/74) · [数据 #61](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/61)
3. R41、R45、R47、R48 的历史实验已保留协议、结果及代码引用。四项周末原研究以各自冻结结算。原 PR 状态仍在两仓供审核。[原 R49 与结果接口](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/120)

## 比分研究顺序

建议所列的 20 项赛事历史留出和近期复验汇总均已复算。历史首选 633/5,233，三选 1,635/5,233。近期首选 303/2,686，三选 830/2,686。R45 的首选多中一场、三选少中两场发生在 218 场选型样本。随后 312 场相较 R7 首选少一场、三选多两场，最近 150 场两项持平。[原逐赛事成绩](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/blob/87ef46859990a8760b4af361eef3186f5090d319/workspace-updates/20261123-all-scope-kpi/results/scorecard.csv) · [R45 配对](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/blob/87ef46859990a8760b4af361eef3186f5090d319/workspace-updates/20261127-r45-j1-four-goal-path/README.md)

| 原欧战窗口 | 原首选 | 原三选 | 原矩阵实际比分前五 | 原矩阵实际比分前十 |
| --- | ---: | ---: | ---: | ---: |
| 欧协联 | 1/18 | 6/18 | 8/18 | 12/18 |
| 欧联 | 0/18 | 7/18 | 10/18 | 12/18 |

两项欧战 36 场中，18 场的真比分落在原矩阵第七位或以后。该同场诊断用于优先复核总进球和主客进球分配。先用西甲、荷甲及日职联的独立时间窗验证已有分布方案。第一比分、固定首选下两个备选的额外覆盖，以及精选三场的首选可靠性各看原口径。精选排序复用 R16，等原周末三席结算后再比较。[两项欧战原结果](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/108) · [R16](https://github.com/kaka597000/Football-Analysis/pull/90)

## 复算

源码输入固定为 `357b3377593c6f1ced4ff891c7f3d1a12395cdda`，原数据输入固定为 `87ef46859990a8760b4af361eef3186f5090d319`。本地复算与 PR 检查使用相同两份输入。

```bash
(cd workspace-updates/20261127-phase-one-evidence && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/source/runtime python -B workspace-updates/20261127-phase-one-evidence/verify.py \
  --data-root /path/to/original-data
```
