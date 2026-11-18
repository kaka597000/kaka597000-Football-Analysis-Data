# 球队状态、补充数据和战术图实验

本次比较优先评价唯一首选比分，另行评价胜平负、实盘大小球及概率质量。欧洲历史开发、巴甲赛前首版预测和传球接应任务分别计分。下面的前向预测均按 90 分钟结算。

## 最近五场能带来多少增量

在五大联赛 2024/25 的 1,299 场拟合，固定配方后评估 2025/26 的 1,737 场。每支球队只使用目标比赛日期之前的最近五场联赛比赛，两模型都看到相同的进失球、主客身份、有效场次掩码和基线期望进球。LightGBM 和单层 LSTM 分别预测主客进球率的修正，两组均在同一经过市场校准的比分矩阵上选唯一首选比分。历史基线取自先前的进球预测与 Bet365 收盘价，缺少逐笔报价时间，开发样本此前已被研究。

| 模型 | 第一比分 | 胜平负 | 大小 2.5 全赢 | 比分对数损失 |
| --- | ---: | ---: | ---: | ---: |
| 历史比分基线加盘口 | 225 | 923 | 1,011 | 2.87494 |
| LightGBM | 229 | 926 | 1,006 | 2.87357 |
| 轻量 LSTM | 226 | 924 | 1,006 | 2.87457 |

LightGBM 的第一比分改对 12 场、改错 8 场，净增 4 场，按日期做配对重采样的 95% 区间为 −0.32 至 +0.80 个百分点。训练完成后反转两队各自五场的顺序，在相同数据和盘口下重算，LightGBM 改选了 63 场首选比分，LSTM 只改选了 1 场。两组大小球都少中 5 场，保留候选身份。

[完整指标与分联赛结果](history/season-validation.json) · [逐场预测](history/season-holdout.jsonl.gz) · [次序敏感性](history/order-sensitivity.json) · [巴甲原冻结历史对照](history/brazil-transfer-validation.json)

## 六场独立前向验证

北京时间 2026 年 11 月 18 日 12:08 完成赛前冻结。基线从真实 Current 工件重新推断，再用当时的同机构胜平负与实际总进球盘校准。三组共享盘口、球队顺序和预测截点。LightGBM 仅将弗拉门戈–巴拉纳竞技从 2–1 改为 2–0。LSTM 同样改选这场，另把科林蒂安–博塔弗戈从 1–1 改为 1–0。其余四场首选比分一致。所有六场的胜平负及大小球方向三组均相同。独立核验重建了 18 份真实比分矩阵和选择。完赛后，已有采集任务会核查原始 90 分钟赛果，更新每场改对、改错与覆盖。

[事前登记](registration/protocol.json) · [逐场冻结](forward/summary.json) · [复算回执](forward/replay-validation.json) · [最新复盘](forward/review.json)

## 补数与战术研究

ESPN 提供主客身份、首发与已完场比赛射门，BSD 提供历史 xG，OpenFootball 的 CC0 公开文本用于交叉核对主客与日期。盘口使用 The Odds API 的机构报价时间。源数据缺失、来源状态和阵容窗口单独留存。各源按主客、日期与比赛身份对齐，保存观察时间和响应哈希。此次时序模型使用已登记的相同字段；新采到的 xG、射门和首发可供后续独立实验使用。

同一个巴西比赛日晚间另有定向采集。短任务在 UTC 11 月 18 日 21–23 时每小时的 11、41 分，以及 19 日 00:06 请求采样。若 GitHub 延迟调度，以实际观测时间判定能否作为赛前证据。最后一个预定窗口后，工作流会关闭该批专用定时入口。常规六小时采集继续复盘。

首轮真实取数覆盖 6/6 场的赛程校对、盘口和双方上一场的射门。去重后涉及 9 场已完赛历史。6/6 场能找到双方最近一场的供应商 xG 数值，其中 2/6 场的双边历史同时满足非估算标记条件。首轮确认首发 0/6，六场均处于临场窗口之前。

[当前字段覆盖](coverage/latest.json) · [逐次观测](coverage/runs)

战术原型使用公开的 StatsBomb 2024 欧洲杯事件。36 场小组赛拟合，15 场淘汰赛留出。强基线在 1,877 次可评价传球中识别接球人 434 次，增加有向图消息传递后为 428 次。该实验评价接球人识别，未估计终场比分收益。下一阶段保留可复用的图构建和输入数据定义。

[战术实验、数据署名和复算方法](tactics/README.md)

## 重放

在装有分析仓库 requirements.txt 依赖的数据仓库检出目录，运行以下命令。ANALYSIS 指向本轮分析源码。持久化文件包含原始数据索引、参数、预测及评估。

```sh
EXP=workspace-updates/20261118-sequence
OPENBLAS_NUM_THREADS=1 python "$EXP/verify.py" --source "$ANALYSIS"
PYTHONPATH="$ANALYSIS/runtime" python -m research_program.sequence_forward review --batch "$EXP/forward" --state-dir .
```

原始训练环境使用 CPU PyTorch 2.14.1 和 LightGBM 4.6.0。以下命令用临时目录重建历史样本、训练权重和逐场开发成绩。

```sh
REPLAY_OUT="$(mktemp -d)"
PYTHONPATH="$ANALYSIS/runtime" python -m research_program.sequence_history --data . --out "$REPLAY_OUT"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$EXP/history/run_models.py" --source "$ANALYSIS" --inputs "$REPLAY_OUT" --out "$REPLAY_OUT"
```
