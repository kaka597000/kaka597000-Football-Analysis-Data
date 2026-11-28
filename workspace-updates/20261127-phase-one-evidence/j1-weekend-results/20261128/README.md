# 日职联 11 月 28 日首版复盘

原登记十场已完成五场。北京时间 11 月 28 日 18:45 实采的五份 ESPN 摘要及五份 J.League 官方对阵页均为 HTTP 200。两源的 90 分钟比分逐场一致。J.League 的实际开球分钟与原计划分钟不同，按原证据保留一分钟区间。剩余五场和原三席精选均在 11 月 29 日。[原件与三波采集回执](captures/) · [逐场结算](review.json)

| 比赛 | 实际开球北京时间 | 90 分钟比分 | 原综合三选 |
| --- | --- | ---: | --- |
| 京都不死鸟–大阪樱花 | 13:03 | 4–1 | 1–0 / 1–1 / 2–1 |
| 清水心跳–浦和红钻 | 13:03 | 1–0 | 0–1 / 1–1 / 1–2 |
| 神户胜利船–千叶市原 | 14:03 | 3–1 | 2–1 / 2–0 / 1–1 |
| 鹿岛鹿角–冈山绿雉 | 14:04 | **1–1** | **1–1** / 2–1 / 1–0 |
| 柏太阳神–广岛三箭 | 15:03 | 3–1 | 1–1 / 1–2 / 2–1 |

| 赛前冻结轨道 | 第一推荐 | 三选 |
| --- | ---: | ---: |
| 原综合 | 1/5 | 1/5 |
| Current | 1/5 | 2/5 |
| Test | 1/5 | 2/5 |
| R28 同样本进球历史 / xG | 1/5 → 1/5 | 1/5 → 2/5 |
| R42 R7 / 固定首选备选，两档各自比较 | 1/5 → 1/5 | 1/5 → 1/5 |
| R46 固定总球进球历史 / xG | 1/5 → 1/5 | 1/5 → 1/5 |
| R49 90 分钟进球率 / 赛季 xG | 1/5 → 1/5 | 1/5 → 1/5 |

四组研究各保留十场原赛前首版，五场待定留在登记分母。R28 的 xG 将清水心跳 1–0 放入第三选，相对同样本进球历史改对一场、改错零场，相对原共同先验净增零。R46 固定总球的 xG 和同样本固定总球进球对照三选持平。相对 R46 的原 xG 历史轨，固定总球使同一场清水心跳 1–0 掉出三选。R49 在神户一场将首选从 1–0 改为 1–1，实际是 3–1，两条都失手。所有列出的对比首选净增为零。[版本、配对与原精选](first-window.json) · [四组研究完整同场明细](review.json)

原综合胜平负 2/5。三场实际出现 4 球或 5 球，三场原综合的三选都只覆盖至多 3 球。原文按发布留档 `3ef75900d3e06bb1-v000001` 的哈希和顺序复算。独立渠道首送回执仍缺，严格综合盘口覆盖 0/10，因此正式第一阶段尚未验收。另有三个原 T−24 小时的市场节点基准，按各自冻结另结首选 1/3、三选 1/3、胜平负 1/3，原大小球 2 全赢、1 全输。节点基准的供应商时钟不补计入综合原首版分母。[规范化赛果](normalized-results.jsonl) · [复盘冻结](review-freeze.json)

完成周日原五场结算后再对照十场净增和原三席。当前只用原预登记规则结算，继续保留原有活动路由。

## 复算

使用 [修复后的固定源码](https://github.com/kaka597000/Football-Analysis/commit/6a52804781d1530d0bdc1eaec29f57b48c5420cb) 和 [原登记输入数据](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/tree/87ef46859990a8760b4af361eef3186f5090d319/workspace-updates)。从本 PR 仓库根目录执行。

```bash
bundle=workspace-updates/20261127-phase-one-evidence
day="$bundle/j1-weekend-results/20261128"
out=/tmp/j1-weekend-20261128-check
PYTHONPATH=/path/to/source/runtime python -B "$day/replay.py" \
  --original-data /path/to/registered-inputs --wave-bundle "$day" \
  --checkpoint-bundle "$bundle" --out "$out" --at 2026-11-28T10:45:52+00:00
for file in review.json first-window.json normalized-results.jsonl; do
  cmp "$day/$file" "$out/$file"
done
```
