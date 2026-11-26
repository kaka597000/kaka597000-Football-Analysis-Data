# 欧协联与欧联连续两轮赛前登记

北京时间 11 月 26 日 15:20 锁定两项赛事各两个连续完整联赛阶段窗口。四份 ESPN 按日赛历各含 18 场，逐轮核对 36 家成年男子俱乐部均仅出赛一次。欧协联第 4、5 轮共 36 场，欧联第 5、6 轮共 36 场。UEFA 官方赛历与 ESPN 的 72 场主客、赛轮和开球时刻全部一致。今夜全部 36 场与更早已冻结的 R13 研究首版、R7 对照和 R5 盘口输入逐队、逐场、逐开球时间一致。[ESPN 赛历](calendar/captures.json) · [欧协联官方核对](calendar/uefa-uecl-crosswalk.json) · [欧联官方核对](calendar/uefa-uel-crosswalk.json)

| 赛事 | 第一窗口，北京时间 | 第二窗口，北京时间 | 登记回执 |
|---|---|---|---|
| 欧协联 | 11 月 26 日 23:30 至 27 日 04:00，18 场 | 12 月 10 日 23:30 至 11 日 04:00，18 场 | [8e35292cbf95d2be-v000001](registration/8e35292cbf95d2be-v000001.json) |
| 欧联 | 11 月 27 日 01:45 至 04:00，18 场 | 12 月 11 日 01:45 至 04:00，18 场 | [8e5d77aa065390d2-v000001](registration/8e5d77aa065390d2-v000001.json) |

今夜用 11 月 25 日 16:21 的 R13 原赛前研究首版做选分。逐场按原顺序保留唯一首选和两个不同备选、胜平负、已经给出的真实盘线方向和原三席。分别按各赛事排名锁定三席，以原作者排序为准。北京时间 11 月 26 日 15:21 冻结本次展示准备，欧协联 `323527b7ba98c727-v000001`，欧联 `56d1e48eafbc04d2-v000001`。Current/Test 实际路由查询 36/36 返回该赛事无已验证工件。R13 与 R7 相比，欧协联一场首选变化、三场三选成员变化；欧联首选逐场相同、三场三选成员变化。以后按同场 90 分钟赛果检验。[36 场比分表](publication/score-tables.md) · [逐场冻结回执、R7 和市场对照](publication/scorecard.json)

阿贾克斯对图恩是唯一首选有变化的比赛，R7 为 2–0，R13 为 3–0。图恩最近五场均有 xG，平均 1.73，给两轨共有的零封判断带来反证。两项赛事已另外归档 36 份赛前 ESPN 摘要，72 队各有五场比分近况。欧协联重点对阵中，古比斯、克拉约瓦大学和伊比利亚 1999 的 xG 各覆盖最近五场中的一场。欧联的雅盖隆最近五场中四场有 xG，均值 2.20；桑德兰五场平均 xGA 为 1.33，零封有反证。赛前补查用于评估候选风险，R13 分数来自原签发记录。[阿贾克斯与图恩](prematch/uecl-process/ajax-thun.json) · [欧协联重点球队](prematch/uecl-process/recent-form.json) · [欧联精选球队](prematch/uel-process/recent-form.json)

原 R13 盘线覆盖 35/36，帕福斯对中日德兰为待定。今夜保留的最新赛历盘口中有五场较早盘线不同，复盘按各自原冻结盘线记录。原输入和最新赛历的 DraftKings 报价对象均无可验证的机构更新时间，严格时钟盘线 0/36。两项赛事第一阶段分别验收，原指标为首选 20%、三选 40%、90 分钟胜平负 65%、严格实盘非走盘全赢 70%、三席原首选全中批次率 100%。每窗要求 18 场实际首版比分与胜平负、至少 15 场时钟合格实盘和至少 13 场已结算非走盘。实际展示独立回读、严格盘口及真实赛果仍待核实，后窗比分待届时赛前签发。

数据仓库根目录使用 Python 3.12 和源码 `71ba85c405c825d3fff10894de6b7dcf2eb3e5e3` 的依赖复跑。校验程序绑定原赛前回执、三比分顺序、原精选三席和展示表字节。

```bash
folder=workspace-updates/20261126-europe-first-display
(cd "$folder" && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/Football-Analysis/runtime python -B "$folder/prepare.py" verify
```

赛后复盘读取状态目录下的 `normalized-results.jsonl` 和其中各条 `raw_reference.path` 对应的 ESPN 比赛摘要或欧足联官方赛果原件。可保留多次采集。程序核对原始主客队和开球时间、成年男子联赛阶段、完整 90 分钟、采集时刻和原始响应哈希。赛果冲突或待完赛保留在原分母。输出含首选、三选命中顺位、同场 R7 与市场净得失、水位对应的五类原盘口结算和原三席结果。研究复盘输出保留严格盘口与独立展示证据的状态，正式阶段仍按原验收协议。

```bash
PYTHONPATH=/path/to/Football-Analysis/runtime \
  python -B "$folder/review.py" --result-state "$RESULT_STATE" > euro-review.json
```

未供应赛果时可省略 `--result-state` 重放完整赛前覆盖。带有上半场开球事件和 `wallclock` 的完场摘要同时输出实际开球、来源与哈希，逐赛事列可核实的场数。多份摘要的实际开球时点冲突时保留待核实状态，已核实的 90 分钟比分继续参与比分研究。11 月 6 日原档的 3 个欧联完赛摘要均可核实实际开球，分别比计划开球晚 83、169 和 187 秒。[赛前公开留档核验](public-archive/README.md)

## 原 R10 同场对照

两项赛事原 R10 均于北京时间 11 月 25 日 15:17 起冻结。北京时间 11 月 26 日 17:31 锁定 36 场原 R7、R10 和 R13 的同场复盘口径，绑定原 R5 盘线、原截止、两项比赛范围与精选记录。欧协联 13/18 场、欧联 18/18 场具备原 R10 的双方赛前射正历史。两套原精选三场的名单、次序及首选比分逐项一致。[欧协联对照回执](benchmarks/117beddf421c8b63-v000001.json) · [欧联对照回执](benchmarks/9f864f8278517c66-v000001.json) · [原 R10 逐场回执](benchmarks/scorecard.json)

| 首选有变化的比赛 | R10 首选 | R13 首选 |
|---|---:|---:|
| 阿贾克斯对图恩 | 2–0 | 3–0 |
| 比尔森胜利对本菲卡 | 0–2 | 1–2 |

两个 R10 首选均在 R13 的备选中。欧协联 5 场、欧联 4 场的三选成员有变化。复盘命令会列每场在各轨的命中顺位、最接近候选的双方进球数差、实际赛果方向是否在三选内，以及各原始模型同场的首选和三选净得失。第一阶段按原实际展示、盘口和真实赛果证据结算。

## 原始赛果接入与双来源核对

已留存的 ESPN 比赛摘要及欧足联官方赛果可统一接入。清单采用一个 JSON 数组，各项包含 `path`、`url`、`captured_at`、`sha256` 和 `http_status`。`path` 相对清单所在目录，`sha256` 为原响应的 SHA-256，压缩留档使用解压后的原响应哈希。脚本复用原欧足联比赛与球队对照，只纳入本次两项赛事各 18 场。`intake.json` 逐场保留来源状态和缺项，`normalized-results.jsonl` 提供待复盘认证的常规时间终场记录。[欧足联测试来源](result-intake-preflight/captures.json)

```bash
PYTHONPATH=/path/to/Football-Analysis/runtime \
  python -B "$folder/result_intake.py" --captures "$RESULT_CAPTURES" --out "$RESULT_STATE"
PYTHONPATH=/path/to/Football-Analysis/runtime \
  python -B "$folder/review.py" --result-state "$RESULT_STATE" > euro-review.json
```

欧足联以已验证赛事身份、`FINISHED` 状态及 `score.regular` 核实 90 分钟比分。ESPN 沿用原常规时间认证和开场事件取证。两个来源一致时，复盘保留两份原件及双来源计数。任一来源具备完整终场证据即可结算；已核实的比分冲突保留待核。延期和比赛尚未结束均留在原覆盖分母。两项赛事的官方历史快照含 35 场已完赛的联赛阶段比赛，其中米兰对费伦茨瓦罗斯 0–2、勒沃库森对马赛 0–1、水晶宫对霍芬海姆 1–1 已与 11 月 6 日留存的 ESPN 原件配对验证。[历史 ESPN 原件说明](../20261106-uel-review/README.md)
