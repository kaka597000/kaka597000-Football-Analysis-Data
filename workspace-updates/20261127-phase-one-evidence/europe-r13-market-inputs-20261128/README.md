# 欧联下一窗 R13 报价接入演练

下一窗 18 场沿用原主客队序、赛季和开球时间。36 个队名在固定 R7 工件的进球状态与 Pi 状态中均逐字匹配。ESPN 本次赛历的 18 场均缺显式中立场标记。贝尔谢巴工人对尤文图斯的原计划场地为罗马尼亚布加勒斯特，保留实际场地和主客队序，模型中立场字段留待确认。[原研究登记](../europe-market-fallback-study-20261128/round2-uel-research-cutoff-revision.json) · [名单与场地核查](verified-prices.json)

原件在输入截止时重新验哈希、赛事身份、主客、机构、盘线和行时钟。完整同机构报价用于两轨，两轨使用完全相同的 1X2，完整轨另外读取实盘双边大小球。只有合格 1X2 时，保留该轨，取最新市场行，同时间按机构名排序。两类输入均缺的比赛保留在 18 场原分母。InferSports 的 `as_of` 保留为供应商市场行时钟，独立的机构原生发布时间尚待核实。[报价适配](market_inputs.py)

欧联现有原件仅包含采列对奥林匹亚科斯的陈旧报价，完整轨与仅胜平负轨的支持数均为 **0/18**。以三份日职联真实原件核对共用报价格式，得到两份完整同机构配对、一份仅 1X2。用已完赛欧联首窗的原价和日期状态复算，**18/18** 场逐轨复现原 R13 和仅胜平负版本的第一比分、三选与独立方向。日职联原件只验证输入结构。本次演练未签发下一窗比分。[报价演练](verified-prices.json) · [模型复跑](verified-model.json)

使用 [采集源码](https://github.com/kaka597000/Football-Analysis/commit/f73b7e6fe9da7c542c46a69dd92fcf8739a79526) 和 [R13 源码](https://github.com/kaka597000/Football-Analysis/commit/f3f3f41673492b43b3d44770e4de76d8571fccb3)，固定原数据及原赛前报价。以下入口从采集输出生成报价输入清单，按实际 `cutoff` 复核已留存响应。首次签发仍需在实际开球前将两轨、原件与工件一起冻结。

```bash
PYTHONPATH=/path/to/collector-source/runtime python -B market_inputs.py \
  --registration /path/to/round2-uel-research-cutoff-revision.json \
  --registered-fixtures /path/to/fixtures-uel.json \
  --prepared-fixtures /path/to/live-capture/prepared-fixtures.json \
  --raw-root /path/to/live-capture --team-ids /path/to/team-ids.json \
  --cutoff "$captured_cutoff" --out /path/to/verified-price-inputs.json
```
