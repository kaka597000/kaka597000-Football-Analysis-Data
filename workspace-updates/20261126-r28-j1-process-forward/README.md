# R28 日职联前向比分对照

在原完整 11 月 28–29 日十场上，于北京时间 11 月 26 日 14:31 锁定独立研究首版，登记 `d7f7b90b447f4512-v000001`。首场为 11 月 28 日 13:00，十场留待实际赛果。登记绑定原赛程、原综合发布、两份原模型矩阵、真实近况及逐场预测。统计轨各保存三个有序比分、唯一首选及三席排名。[冻结登记](issued/d7f7b90b447f4512-v000001.json) · [逐场回执](issued/receipts.json) · [签发时状态](status-at-issue.json)

| xG 轨比较对象 | 首选变化 | 三选名单变化 |
|---|---:|---:|
| 两模型共同概率 | 2/10 | 5/10 |
| 完全同样本的进球数近况 | 0/10 | 1/10 |
| 原综合首版 | 5/10 | 5/10 |

三选名单变化按成员核算。每方使用 6–10 个去重进攻及对手防守观测。xG 与同样本进球数的首选逐场相同，未来这批两轨的首选命中数将相等。实验实盘结算覆盖为 0/10。正式第一阶段按其独立登记的 12 月两窗结算。[试验协议](protocol.json) · [12 月登记](../20261126-j1-december-windows/README.md)

11 月 25 日原综合在七场中首选命中一场，第三选中三场。水户–东京绿茵的 1–0 在 Current/Test 均排第 1，综合排第 3。浦和–大阪樱花的 2–2 在两模型排第 6/7，赛后总 xG 4.45。FC 东京–广岛的 2–2 在两模型排第 8/9，赛后总 xG 2.07。复盘中的赛后过程只解释当天实际表现，留作往后赛前的历史信息。[逐场原次序及过程](replay.json) · [原首版复盘](../20261125-forward-settlement/nov25/README.md)

只读复算运行 `python -B -m research_program.j1_process_forward --data . --verify workspace-updates/20261126-r28-j1-process-forward/issued`。令 `PYTHONPATH` 指向固定源码的 `runtime`。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/bc0ec1c11a33b073ccbd827266f686bc98c1f821) · [校验清单](SHA256SUMS)
