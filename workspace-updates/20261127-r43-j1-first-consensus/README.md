# R43 日职联原三选内的首选重排

R29 从结果类型内的总球分散度校准比分，R41 按赛前预期相近的旧比赛校准比分。两种方法都把同一个 R7 原备选排第一时，R43 将其提为首选，其余两个按原次序排列。两种单方法对照也仅在原三选内重排。逐场核对原 R7、市场、球队、日期、盘线和 90 分钟赛果，完整回放三个已使用的历史日期段。[跑数前登记](https://github.com/kaka597000/Football-Analysis/commit/d07416e6e72d803857db691bc5949c0b5572066a)

| 历史样本 | 原 R7 首选 | R43 首选 | 仅用 R29 的首选 | 仅用 R41 的首选 | 各轨三选 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025 年上半年 218 场 | 23 | 23 | 22 | 22 | 71 |
| 2025 年下半年 162 场 | 32 | 32 | 30 | 29 | 71 |
| 2026 年原面板 150 场 | 13 | 13 | 15 | 13 | 35 |
| 后两段合计 312 场 | 45 | 45 | 45 | 42 | 106 |

两段留出合计只有两场触发 R43，均未改变命中。京都对清水从 2–0 提为 1–0，赛果 0–1。川崎对福冈从 2–1 提为 2–0，赛果 1–0。单方法留出对照中，R29 改对 4 场、改错 4 场，R41 改对 7 场、改错 10 场。留出胜平负各轨 168/312，市场同场覆盖 192 场并各中 104 场，历史市场精确比分与实盘大小球覆盖均为 0/312。[逐段指标和同场区间](replay/summary.json) · [逐场留出](replay/history.jsonl.gz)

最新 150 场中，13 场命中首选，22 场只由备选覆盖，115 场落在原三选外。以同一组候选计算，即使知道赛果，重排能覆盖的首选上限也只有 35/150。距离历史样本上 20% 的首选线还差 17 场，需要从原备选的 22 场中找回 17 场并保住原 13 场。三选覆盖则由原名单固定为 35/150。[日期分段和覆盖诊断](replay/summary.json)

在周末原登记十场上，从已冻 R42 的 R7 和 R41 矩阵读取比分，再接入固定 R29 系数复算。十场均保留原 R7 首选。北京时间 11 月 27 日 09:49:40 冻结资格检查 `4b9a8a3137d2b23f-v000001`。周末独立前向比分检验已有 R42。第一阶段按原综合首版和原窗口结算。[十场检查](replay/forward-check.json) · [检查回执](forward-check-freeze.json) · [R42 首版](../20261127-r42-j1-fixed-first-backups/README.md)

两次本地复跑的四个工件逐字节一致。数据仓根目录用 Python 3.12.14 和固定源码复算即可验证。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/075bfccac2c8e252dad2a6144bb42db17d74a45c) · [校验清单](SHA256SUMS)

```bash
export PYTHONPATH=/path/to/Football-Analysis/runtime
python -B -m research_program.j1_first_consensus --data . --replay /tmp/r43-replay
diff -qr workspace-updates/20261127-r43-j1-first-consensus/replay /tmp/r43-replay
python -B workspace-updates/20261127-r43-j1-first-consensus/verify_check.py
```
