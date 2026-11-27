# R46 日职联固定总进球下的 xG 比分分配

北京时间 11 月 27 日 10:18:14，周末原登记的十场完成独立 R46 赛前冻结。登记回执 `0723a2a73788af3e-v000001`。复现原 Current/Test 共同分布、R28 原比分和逐场过程证据，再把 xG 与进球数两条轨的结果分别投影回同一总球分布。每个可能总球的最大概率差为 5.56×10⁻¹⁷。每个得分方向使用 6 至 10 个去重后的赛前可用历史观测，两条轨使用同一组样本。[预登记](https://github.com/kaka597000/Football-Analysis/commit/a276b0b441aea9ebfdee58a7a1c9d72f98bbd2ef) · [登记及逐场回执](issued/receipts.json) · [原过程证据](../20261126-j1-recent-process/README.md)

| 固定总球后的 xG 比较对象 | 首选变化 | 三选成员变化 |
| --- | ---: | ---: |
| 原 Current/Test 共同概率 | 2/10 | 4/10 |
| 同样本进球数，固定总球 | 1/10 | 1/10 |
| 原 R28 xG 候选 | 0/10 | 2/10 |

同样本、同总球口径下唯一首选和三选均有分歧的是北京时间 11 月 29 日 14:00 川崎前锋对大阪钢巴。xG 轨为 **1–1／2–1／1–0**，进球数轨为 **2–1／1–1／2–0**。两条研究轨的胜平负均为主胜。这一场可在核实赛果后直接检验两种比分分配。[十场研究比分和观测数](prematch-comparison.json)

三席研究排序均为名古屋–福冈、横滨水手–FC 东京、清水–浦和，三场的两轨首选均为 1–1。实盘严格报价覆盖为 0/10。完整十场按照实际 90 分钟赛果比较首选、三选及原候选已覆盖总球的比分，原综合推荐按其首版和原冻结的三席计算第一阶段成绩。[原综合首版](../20261126-r26-j1-first-stage/README.md) · [周末开球证据](../20261127-j1-official-kickoff/README.md)

两次本地检查逐字节一致。从数据仓根目录运行以下命令，读取固定源码、原赛前证据和十份冻结回执即可复算。实际结果复盘沿用 `research_program.goal_state_forward` 的已核赛果入口。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/f016e8931d6a40ec1b622010a5116d21ab69399c) · [校验清单](SHA256SUMS)

```bash
export PYTHONPATH=/path/to/Football-Analysis/runtime
python -B -m research_program.j1_process_at_fixed_total --data . \
  --verify workspace-updates/20261127-r46-j1-process-at-fixed-total/issued
```
