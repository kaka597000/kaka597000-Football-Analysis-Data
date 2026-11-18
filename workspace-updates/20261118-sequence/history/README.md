# 比分序列研究的历史对照

五大联赛七季、35 份 Football-Data 赛果文件共覆盖 12,459 场。每个预测节点读取双方在同一联赛最近五场的进球、失球和主客身份，同一天的所有比赛均先生成特征，再更新当天赛果。逐步来源可在 samples-2425.jsonl.gz 和 samples-2526.jsonl.gz 的 sequence_sources 中定位到文件、行号和比赛日期。缺少的前序比赛在序列左端补零，valid 位同时记为 0。训练季有 1,291/1,299 场具备完整的两队十步，验证季为 1,727/1,737。

欧洲三组共用同一份比分分布。原始强度来自按时间生成的无盘口进球模型，接着按固定权重 1 投影到同一机构 Bet365 胜平负和 2.5 盘的去水约束。两个候选分别从最近五场序列及共同基线的上下文估计调整。2024/25 的 1,299 场用于拟合，2025/26 的 1,737 场只评估一次。此前项目已研究过这两个赛季，历史收盘没有逐笔时间戳。

| 同场验证 | 第一比分 | 胜平负 | 大小 2.5 全赢 | 比分对数损失 |
| --- | ---: | ---: | ---: | ---: |
| 共同盘口基线 | 225/1,737 | 923/1,737 | 1,011/1,737 | 2.87494 |
| LSTM | 226/1,737 | 924/1,737 | 1,006/1,737 | 2.87457 |
| LightGBM | 229/1,737 | 926/1,737 | 1,006/1,737 | 2.87357 |

季外配对比较使用比赛日作为抽样单位。两个候选的第一比分与胜平负净增区间均跨越零。两者大小球都净少 5 场，LightGBM 的区间跨越零，LSTM 的日期分组 95% 区间为 −0.61 至 −0.05 个百分点。season-validation.json 提供联赛分项、逐指标样本数、净增减、置信区间、对数损失和 Brier 分数。

巴甲迁移回放另以 2026-10-01 为训练截止，使用截至 5 月 24 日完结的欧洲 3,036 场和同一套配方拟合。巴甲 9 份既有 Current 首冻中，2 场同时保存了真实胜平负和亚洲大小球的报价及报价时间，两场均还原出原冻前两队各五场的联赛状态。其余 7 场保留在覆盖率清单中。另有 1 场状态缺最接近比赛的观测，逐场标记在 brazil/sequences.json。两场比较的三组都取得第一比分 0/2、胜平负 1/2、大小球全赢 1/2。同一比赛日无法估计日期分组区间。

## 复算

DATA 和 SOURCE 分别指向这次项目的数据与分析代码仓库。使用包含 NumPy、SciPy、PyTorch 和 LightGBM 的项目训练环境。

```sh
HISTORY="$DATA/workspace-updates/20261118-sequence/history"
cd "$SOURCE"
python -m runtime.research_program.sequence_history --data "$DATA" --out "$HISTORY"
python "$HISTORY/brazil/prepare.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$HISTORY/run_models.py" --source "$SOURCE" --inputs "$HISTORY" --out "$HISTORY"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$HISTORY/replay_brazil.py" --source "$SOURCE" --history "$HISTORY" --out "$HISTORY"
```

输入摘要保存在 sequence-inputs.json，巴甲回放报告为 brazil-transfer-validation.json。用于今后跟踪的候选独立保存在 artifact.json。
