# R48 日职联同样本 xG 与进球回放

在已留存的 FotMob 日职联详情中，51 场有双边 xG、总射门和射正，并与原 R5 的成年男子常规赛、主客、比赛日及 90 分钟比分一致。它们覆盖 2026 年 150 场面板的 51 场。44 场采集时点与原响应 SHA-256 一致，其余 7 场仅进入较早比赛日的历史对照。ESPN 401877581 的两源计划开球时间相差一小时，保留两个原值和同一天的比赛身份。[配对记录](evidence/observations.jsonl) · [原件索引](evidence/manifest.json)

每个目标日使用双方各自最近五个更早的日职联常规赛历名额。进球轨和 xG 轨取其中同一批有双边过程数据的比赛，并按历史进攻方去重。复用 R28 的八个先验观测和修正上限，底分布为签名 R7。150 场中 65 场有填入的较早比赛过程样本，32 场在目标比赛日北京时间 08:00 前已有相应的采集回执。[执行前登记](https://github.com/kaka597000/Football-Analysis/commit/471cb371a6509bc5f14d9bcdce202947558e5a21) · [逐场回放](replay/forecasts.jsonl.gz)

| 研究轨 | 前 86 场首选 / 三选 | 后 64 场首选 / 三选 | 全 150 场首选 / 三选 |
| --- | ---: | ---: | ---: |
| 原 R7 | 11 / 24 | 2 / 11 | 13 / 35 |
| 同样本进球 | 11 / 24 | 3 / 14 | 14 / 38 |
| 同样本 xG | 11 / 23 | 4 / 15 | 15 / 38 |
| 固定原总球的进球 | 11 / 23 | 3 / 13 | 14 / 36 |
| 固定原总球的 xG | 11 / 23 | 4 / 12 | 15 / 35 |
| 只用已有采集回执的进球 | 11 / 24 | 3 / 12 | 14 / 36 |
| 只用已有采集回执的 xG | 11 / 24 | 2 / 11 | 13 / 35 |

用全部同样本历史时，xG 比进球多中一个首选，全段三选改对 3 场、改错 3 场。用目标日前已留存采集回执的样本时，xG 的首选和三选各比进球少中一场。胜平负沿用原 80/150，市场同场可比 76 场，R7 命中 42 场、市场 40 场。可配对的比分市场和严格实盘大小球为 0/150。[配对差异、覆盖及区间](replay/metrics.json)

冈山对神户的早期原件为 1.10–1.97 xG，后版为 1.11–2.59。更换后，横滨水手对冈山的首选由 1–0 变为 2–0，神户对町田的两个备选换序。150 场的首选与三选命中数相同，固定总球下的有序比分也相同。[后版归档](evidence/alternate.jsonl)

本轮为历史开发。第一阶段沿用实际首次展示的正式首版。周末的真实 xG 前向证据来自已冻结的 R28 和 R46 对照。[周末 R46](../20261127-r46-j1-process-at-fixed-total/README.md)

两次来源复算和两次数值回放分别逐字节一致。来源复算读取 WCPP 恢复包中的原始 FotMob 文件和原采集清单。以下两步可在数据仓根目录运行。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/3a4945e4a6c131cc1f95c2f9bb2e5e84fcf2fa9a) · [校验清单](SHA256SUMS)

```bash
bundle=workspace-updates/20261127-r48-j1-matched-xg-history
python -B "$bundle/evidence/prepare.py" --wcpp /workspace/WCPP --out /tmp/j1-r48-source
cmp "$bundle/evidence/observations.jsonl" /tmp/j1-r48-source/observations.jsonl
cmp "$bundle/evidence/alternate.jsonl" /tmp/j1-r48-source/alternate.jsonl
PYTHONPATH=/path/to/Football-Analysis/runtime python -B -m research_program.j1_matched_xg_history \
  --data . --out /tmp/j1-r48-replay
diff -qr "$bundle/replay" /tmp/j1-r48-replay
```
