# 欧联与欧协联的历史精选三场复盘

核对 2026/27 已归档的欧联前四轮、欧协联前三轮。每轮 18 场，始终以欧足联轮次为准，核实同一赛季成年男子联赛阶段的 36 家俱乐部及主客开球。欧联第一轮和第四轮各跨两个比赛日。以原 R13 逐场第一比分概率排序，同概率沿用开球、比赛 ID 排序。首选、备选和市场对照读自同一已归档 R13 回放。[逐轮及逐场核验](history.json) · [原 R13](../20261125-r13-domestic-form/README.md)

| 赛事 | 完整历史赛轮 | 精选第一比分 | 精选三选 | 三个首选全中批次 | 全轮至少有三个首选命中的轮次 |
|---|---:|---:|---:|---:|---:|
| 欧联 | 4 | 0/12 | 2/12 | 0/4 | 0/4 |
| 欧协联 | 3 | 3/9 | 3/9 | 0/3 | 3/3 |

欧联四轮的全轮首选命中数依次为 0、1、1、2。即使赛后重挑这四轮的精选席位，原全轮首选也凑不出三中三。欧协联全轮首选命中数依次为 6、3、5，实际排序每轮各挑中一场。欧联市场同席首选 1/11，对应 R13 为 0/11。欧协联市场与 R13 同席首选各 3/9。市场比分来自原历史盘口推导。[逐席查核](history.json)

126 场都可按 90 分钟比分核实。欧足联三个原条目的 `score.regular` 与 `score.total` 互相冲突。以 ESPN 完场状态、上下半场加总和无加时或点球大战的证据核实亚特兰大 3–1 帕福斯、塞尔塔 1–2 尤文图斯、伯恩茅斯 3–0 格拉茨风暴，三个结果都与欧足联 `score.total` 一致。原流程隔离了冲突记录，保留两个字段和 ESPN 原件。欧联首次采集时本地记录时钟失败，保留原文并低频重取，最终归档的响应与第一次哈希一致。[留档与时钟](evidence/captures.json) · [冲突明细](history.json)

这些是历史回放结果。首阶段精选三场仍按原赛程登记、赛前锁定名单、首次实际展示和可靠终场核验。今夜欧联和欧协联各有一批原精选三席待赛。11 月 25 日已复盘的日职联原七场批次，原精选三席首选 0/3、整批全中 0/1，独立首次送达证据继续待核。[今夜原登记](../20261126-europe-first-display/README.md) · [日职联原七场](../20261125-forward-settlement/nov25/README.md)

使用 Python 3.12.14、原源码依赖及 LightGBM 4.6.0 复算。归档保留五份公开原件和逐项哈希。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/2d7754822cc36e0387c61a140a4309be7d6e8ead)

```bash
folder=workspace-updates/20261126-europe-selected-history
(cd "$folder" && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/Football-Analysis/runtime python -B "$folder/audit.py" > /tmp/europe-selected-history.json
cmp "$folder/history.json" /tmp/europe-selected-history.json
```
