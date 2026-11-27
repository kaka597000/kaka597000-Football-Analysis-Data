# 11 月 28–29 日日职联官方实际开球证据准备

北京时间 11 月 27 日 08:55:58，日职联原登记第二窗口的 10 场官方身份已另行冻结，回执 `27defe5fb1c3dc6e-v000001`。逐场绑定 ESPN 比赛 ID、主客顺序、J.League 官方对阵页、主客球队 ID、日文名和原计划时间。十场均为日职联第 17 节，采集时均处于赛前。最早的两场按原计划于 11 月 28 日 13:00 开球。[赛前冻结绑定](kickoff-packet.json) · [十份原件及哈希](captures.json) · [原比分和精选首版](../20261126-r26-j1-first-stage/README.md)

正式复盘从保留的赛中或赛后官方页面核查 `KO` 分钟。通过核验的官方时间保留完整分钟区间，首次实际送达早于整个区间才满足开球时序。若独立来源出现冲突，该场开球留待核实。原计划时间与官方报时分钟相同时，需要补充独立秒级开球证据。实际首送、赛果和盘口覆盖分别按原登记核实。[正式复盘口径](https://github.com/kaka597000/Football-Analysis/blob/bfed38d5591e31577c96b2ca16ad683d98335cf3/docs/j1-official-kickoff-proof.md)

用新入口重放 11 月 25 日的真实赛中和终场原件，7/7 场均取得官方分钟区间，官方与 ESPN 的 90 分钟终场比分 7/7 一致。周末窗口的赛前入口已复跑，10 场待赛，实际开球证据等待赛中或赛后采集。[复跑结果](verified.json) · [既有七场证据和对应的周末采集入口](../20261127-europe-round1-review/j1-capture-plan.json)

数据仓库根目录可用固定源码的 `runtime` 复跑。校验将比对原登记、十份赛前官方页、原绑定冻结和真实旧轮的七场开球原件。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/bfed38d5591e31577c96b2ca16ad683d98335cf3)

```bash
PYTHONPATH=/path/to/Football-Analysis/runtime \
  python -B workspace-updates/20261127-j1-official-kickoff/bind.py
```
