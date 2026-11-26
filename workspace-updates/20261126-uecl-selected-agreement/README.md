# 欧协联 R39 精选三场排序

原排序按 R13 第一比分的概率取全轮前三。R39 优先选原首选也得到 R9 和 R10 同时支持的比赛。两种方案逐场用同一首选和同样的三个比分。两项证据赛前历史充分且原市场一致时才提供排序优先级，组内仍按原概率、开球和比赛 ID 排序。无完整双路证据的场次保留原排序优先级。R9 与 R10 使用部分共同的基础数据。[运行前登记](protocol.json) · [逐场比较](comparison.json)

| 历史窗口 | 完整轮次 | 选中首选，原版 → 一致性 | 选中三选，原版 → 一致性 | 首选三中三批次，原版 → 一致性 |
|---|---:|---:|---:|---:|
| 2025/26 联赛阶段 | 6 | 2/18 → 2/18 | 8/18 → 5/18 | 0/6 → 0/6 |
| 2026/27 已完赛前 3 轮 | 3 | 3/9 → 3/9 | 3/9 → 3/9 | 0/3 → 0/3 |

旧赛季 108 场有 72 场可用双路历史证据，65 场同时支持原第一比分。后续 54 场对应 24 场和 20 场。新排序在两段分别换了 4 轮和 1 轮的精选成员。2025/26 第 2 轮多中一个首选，第 6 轮少中一个。两段均未满足预登记筛选条件。[同场比分及每轮市场覆盖](comparison.json)

上季 108 场均由欧足联核实官方赛轮、主客及 90 分钟赛果。原 36 队每轮各出现一次。源间名称写法经球队 ID 和完整赛程核对。里耶卡对布拉格斯巴达的 ESPN 存档日期对应下半场恢复，欧足联记录的是计划初开球。ESPN 的上半场和下半场分别于北京时间 10 月 24 日 00:45:54、22:00:16 开始，终场 1–0。比赛保留在第二轮，两种排序均未选择这场。历史 R13 的存档日期本身无法证明此场的预测在第一次开球前可用。[球队别名](club-aliases.json) · [欧足联采集](evidence/captures.json) · [恢复事件证据](evidence/resumption.json)

这些赛轮已有历史使用记录。今晚的正式三席按已锁定名单和首版预测等候 90 分钟赛果。第一阶段按原登记结算。[原首版和精选登记](../20261126-europe-first-display/README.md)

使用 Python 3.12.14、原源码依赖及 LightGBM 4.6.0 复算。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/2d7754822cc36e0387c61a140a4309be7d6e8ead)

```bash
folder=workspace-updates/20261126-uecl-selected-agreement
(cd "$folder" && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/Football-Analysis/runtime python -B "$folder/audit.py" > /tmp/uecl-selected-agreement.json
cmp "$folder/comparison.json" /tmp/uecl-selected-agreement.json
```
