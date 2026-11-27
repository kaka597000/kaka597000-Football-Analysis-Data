# R49 日职联赛季 xG 与比分分配

Football LAB 的 2026/27 日职联期望进球表于 11 月 26 日更新，北京时间 11 月 27 日 11:20:23 采集。两个表均有 20 支球队。累计范围与 157 场已核实的 90 分钟常规赛对应，14 队 16 场、6 队 15 场。足球实验室进球栏明确排除乌龙球。网页进球率和经核实的整场进球数各自保留，最新表全联赛的进球总数相差 6。[三份原件和采集回执](evidence/captures.json) · [逐队输入](evidence/snapshots.json)

每队用其均场进攻率与对手均场失球率的平均，按两队中较少的已完成场数及八场先验修正 R7。三条研究轨使用网页进球率、90 分钟全进球率和网页 xG。各轨保持 R7 的每个总球概率、胜平负判断和盘口结算方向。[执行前登记](https://github.com/kaka597000/Football-Analysis/commit/07228cae26addd1ba5dbb8800f260b73ea2847fd)

| 研究轨 | 用 2025 年表回放 140 场，首选 / 三选 | 用当时已有的 11 月表回放 10 场，首选 / 三选 |
| --- | ---: | ---: |
| 原 R7 | 13 / 34 | 0 / 1 |
| 网页进球率 | 13 / 33 | 0 / 2 |
| 90 分钟全进球率 | 13 / 32 | 0 / 2 |
| 网页 xG | 13 / 32 | 0 / 3 |

140 场中 100 场两队都有 2025 年表的记录，40 场使用冷启动回退。2025 年表在这些比赛之后采集，该段属于历史开发。第二段十场使用北京时间 11 月 20 日 15:46:43 采集的球队表，早于原十场所有计划开球。十场的比赛身份和比分通过签名 R7 复算，xG 比两种进球对照各多覆盖一个三选。两段的比分及实盘市场覆盖均为 0，原胜平负结算为 77/140 和 3/10。[逐场结果](replay/forecasts.jsonl.gz) · [配对和覆盖](replay/metrics.json)

## 11 月 28–29 日真实赛前对照

北京时间 11 月 27 日 11:27:44 冻结十场，登记回执 `31ea7f132acf6e2f-v000001`。固定总球后，与网页进球率相比，xG 有 1/10 场首选不同、4/10 场有序三选不同，其中 3/10 场变更了三选成员。网页进球率和全进球率的首选完全一致，有 1/10 场三选不同。[十场首选、三选和覆盖](prematch-comparison.json) · [登记及原件](issued/receipts.json)

北京时间 11 月 28 日 14:00 神户胜利船对千叶市原是两条进球对照和 xG 的唯一首选分歧。xG 轨为 **1–1／1–0／2–1**，两条进球对照均为 **1–0／1–1／2–0**。四轨研究前三席为町田–东京绿茵、水户–长崎、名古屋–福冈。正式精选沿用原综合首版。[原正式首版](../20261126-r26-j1-first-stage/README.md)

复算覆盖三份源页面、两段历史和十场赛前回执。用固定源码在数据仓根目录执行下列命令。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/f3f3f41673492b43b3d44770e4de76d8571fccb3) · [工件校验](SHA256SUMS)

```bash
bundle=workspace-updates/20261127-r49-j1-season-chance-rates
python -B "$bundle/evidence/prepare.py" --out /tmp/j1-r49-snapshots.json
cmp "$bundle/evidence/snapshots.json" /tmp/j1-r49-snapshots.json
export PYTHONPATH=/path/to/Football-Analysis/runtime
python -B -m research_program.j1_season_chance_rates --data . --replay /tmp/j1-r49-replay
diff -qr "$bundle/replay" /tmp/j1-r49-replay
python -B -m research_program.j1_season_chance_rates --data . --verify "$bundle/issued"
```
