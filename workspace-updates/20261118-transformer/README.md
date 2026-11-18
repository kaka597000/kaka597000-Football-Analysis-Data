# 首选比分的 Transformer 对照

本次固定轻量 Transformer 的架构、比赛范围、输入及指标后训练。目标是检验在相同信息下，加入自注意力是否提高 90 分钟第一比分、胜平负与实际盘线大小球的命中率。首选比分按完整比分矩阵最大格取一个；胜平负按边际概率取方向；大小球按实际亚洲盘报告全赢、半赢、走盘、半输和全输。

## 按相同输入比较四组

Transformer 采用一层双头自注意力、16 维隐藏表示、32 维前馈层及位置编码，共 2,468 个可训练参数。最近五场进球、失球、主客与有效场次组成序列，盘口校准后的主客期望进球提供共同基线。训练目标和应用时的进球率修正范围与原 LightGBM、LSTM 一致。候选输出经过调整的完整比分概率。

| 2025/26 欧洲五大联赛，1,737 场 | 首选比分 | 胜平负 | 大小 2.5 全赢 |
| --- | ---: | ---: | ---: |
| 历史进球基线加盘口 | 225 | 923 | 1,011 |
| LightGBM | 229 | 926 | 1,006 |
| LSTM | 226 | 924 | 1,006 |
| Transformer | 226 | 927 | 1,010 |

此前季 1,299 场用于拟合，后季 1,737 场沿用既有开发比较。历史报价取自 Bet365 收盘资料，缺少原始逐笔时刻。Transformer 相对基线的比分改对 5 场、改错 4 场，净增 1 场，按比赛日划分的配对 95% 区间跨越零。反转两队最近五场的顺序，仅有 13 场改变比分首选。各模型的胜平负、大小球和概率质量另行计算。

[登记与固定配方](registration/protocol.json) · [跨季对照及复算方法](history/README.md) · [逐场预测](history/season-holdout.jsonl.gz) · [两次训练一致性](history/reproduction.json)

## 2026/27 赛季追加检验

登记范围为截至 11 月 17 日已结束的五大联赛比赛。在取得的 500 场中，19 场未达到同一上游进球模型的球队历史长度要求，481 场入评（96.2%）。各联赛文件最后的比赛日期以原始清单为准，最晚为 11 月 8 日。所有候选训练资料最晚的比赛是 5 月 24 日。季前截点重训后，权重与原最终工件一致。原 1,737 场上游进球强度逐场复现，最大差异为零。本段仍使用赛后下载的历史收盘价，无法认证每笔报价的原始时刻。

| 2026/27 赛季，481 场 | 第一比分 | 胜平负 | 大小 2.5 全赢 |
| --- | ---: | ---: | ---: |
| 同口径盘口基线 | 57 | 273 | 290 |
| LightGBM | 59 | 276 | 292 |
| LSTM | 57 | 273 | 292 |
| Transformer | 58 | 272 | 292 |

Transformer 相对基线改对一个首选比分、无改错，净增 0.21 个百分点。比赛日分组的 95% 区间为 0.00 至 +0.68 个百分点。481 场中，Transformer 有 12 场给出了与盘口基线不同的首选比分。与 LightGBM 相比，首选比分少中 1 场，大小球持平。两者有 4 场给出不同的胜平负选择，4 场均由 LightGBM 命中。另有 2 场真实巴甲历史 Current 首冻带有合格的双市场报价；四组在这 2 场的三项成绩均为 0/2、1/2、1/2。

[新赛季逐场来源、覆盖和配对区间](transfer/europe-2627-validation.json) · [新赛季逐场预测](transfer/europe-2627-predictions.jsonl.gz) · [追加验证登记](registration/transfer.json)

## 真实赛前与结算

北京时间 2026 年 11 月 18 日 13:11 对巴甲登记在册的 6 场另行首冻。四组选取同一时点、同一家机构的胜平负与实际大小球盘，并从活动 Current 工件重建比分基线。此次 Transformer 和盘口基线在 6 场的三个选择都相同。弗拉门戈对巴拉纳竞技的新盘为 3.0，Transformer 选大，LightGBM 选小。首冻时 6 场全部待结算。程序在有原始全场赛果后更新配对结果。各次实验保留各自的报价、比分矩阵、预测截止与结算口径。

[六场首版明细](forward/summary.json) · [完整概率](forward/freezes) · [24 份分布独立重放](forward/replay-receipt.json) · [最新复盘](forward/review.json)

使用分析仓库所锁定的源码与依赖，在数据仓库根目录可离线复核：

```sh
EXP=workspace-updates/20261118-transformer
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$EXP/verify.py" --source "$ANALYSIS"
PYTHONPATH="$ANALYSIS/runtime" python -m research_program.transformer_forward review --state-dir . --batch "$EXP/forward"
```

[严格集成测试](integration.json) · [完整离线复算](offline-replay.json) · [主分支实际运行与回滚记录](deployment.json)
