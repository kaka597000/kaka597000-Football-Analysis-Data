# 2026/27 五大联赛季外重放及巴甲原工件核验

2026 年 11 月 18 日，按预先固定的配置重放此前 3,036 场训练之外的新赛季比赛。采集范围包括 Football-Data 五个联赛文件中比赛日期截至 11 月 17 日的全部已出赛果记录。五份快照最新一场均为 11 月 8 日。[额外比较设置](transfer-protocol.json) · [来源网址、时间与哈希](raw/source-metadata.json)

| 联赛 | 源文件已完场 | 具备近史和完整同机构报价 |
| --- | ---: | ---: |
| 英超 | 100 | 95 |
| 德甲 | 81 | 78 |
| 法甲 | 90 | 87 |
| 意甲 | 110 | 110 |
| 西甲 | 119 | 111 |
| 合计 | 500 | 481 |

19 场在原始进球强度模型中缺少至少一队的三场既往联赛记录。500 场都有当行 Bet365 胜平负和大小 2.5 的完整收盘报价。每个比赛日期先生成当日全部特征，之后加入该日赛果。使用存档的原估计器与系数，复算上季 1,737 场保存的主客进球强度，逐场最大绝对误差为 0。LightGBM、LSTM 和 Transformer 以 8 月 1 日为信息截止重新拟合，训练集为截至 5 月 24 日的 3,036 场。导出的参数、训练样本摘要与前向工件逐项相同。[拟合身份核验](refit-receipt.json)

| 模型 | 首选比分 | 胜平负 | 大小 2.5 全赢 | 比分对数损失 |
| --- | ---: | ---: | ---: | ---: |
| 进球模型＋同书盘口 | 57 | 273 | 290 | 2.99935 |
| LightGBM | 59 | 276 | 292 | 2.99624 |
| LSTM | 57 | 273 | 292 | 2.99561 |
| Transformer | 58 | 272 | 292 | 2.99655 |

Transformer 相对盘口基线，比分改对 1 场、改错 0 场，胜平负改对 0 场、改错 1 场，大小球改对 8 场、改错 6 场。按整日配对重采样的 95% 区间分别为 0.00 至 +0.68、−0.69 至 0.00、−1.12 至 +1.87 个百分点。相对 LightGBM，Transformer 少中 1 个比分、4 个胜平负，大小球相同。比赛在研究前已经结束，收盘价缺少可核实的逐笔时间，历史数据在事后下载。该赛季提供独立日期样本，真实赛前效果另由新冻结跟踪。[完整指标](europe-2627-validation.json) · [逐场四组预测与来源行](europe-2627-predictions.jsonl.gz)

另对 9 份留存的巴甲活动 Current 原冻结检查实际可用性，其中 2 场带有原截点双市场以及双方各 5 场既往记录。四组在这两场均获得比分 0/2、胜平负 1/2、大小球 1/2。两场属于同一比赛日。[巴甲配对结果与资格清单](brazil/report.json)

## 离线重放

在数据仓根目录运行以下命令，SOURCE 指向本次固定分析源码。第一条重放从头构建强度与球队状态，第二条重放原巴甲冻结。两者使用仓库保留的工件与响应，运行不访问赔率服务。权重拟合使用与原研究相同的 CPU PyTorch 和 LightGBM，见 refit.py。

```sh
STUDY=workspace-updates/20261118-transformer/transfer
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$STUDY/evaluate.py" --source "$SOURCE" --out /tmp/transformer-transfer-europe
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python "$STUDY/brazil/replay.py" --source "$SOURCE" --out /tmp/transformer-transfer-brazil
```
