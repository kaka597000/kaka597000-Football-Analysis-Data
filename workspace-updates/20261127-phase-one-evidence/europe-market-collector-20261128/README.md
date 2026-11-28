# 欧联、欧协联第二窗口盘口采集

已用两个原赛程冻结、原 ESPN 比分板和上一轮已核身份生成盘口采集输入。欧联和欧协联各 18 场，72 个比赛侧的球队身份分别绑定 ESPN 与 InferSports 的名称、编号。每场还保留原联赛阶段、赛季标识、计划开球和已核实的供应商赛事编号。[欧联输入](fixtures-uel.json) · [欧协联输入](fixtures-uecl.json) · [球队对照](team-ids.json)

扩展沿用日职联现有公共采集器。赛历状态须可证实为待赛，盘口必须逐场复核主客、机构、全场范围、实际双边价格和供应商市场行时钟。每场应用其自己的采集截止。欧战差异基于独立审核的日职联取证分支提交。[欧战源码 PR #132](https://github.com/kaka597000/Football-Analysis/pull/132) · [基础取证 PR #131](https://github.com/kaka597000/Football-Analysis/pull/131)

用正常采集入口离线复跑两场共六份真实响应。采列–奥林匹亚科斯的全场报价在取样时已陈旧，特拉布宗体育–亚布洛内茨的原件为空。合格总球为 **0/2**，因此这些样本的后续采集仍在相应节点取最新原件。这里只核盘口数据入口，原比赛范围、首版签发和正式验收以各自登记为准。[入口复跑](replay.json) · [真实原件](../market-readiness-20261128/europe-infer-catalog/http-log.json)

## 调用

每项赛事独立调用，使用当时的独立输出目录。需要按比赛对应节点验证时，可传 `--checkpoint T-24h`、`T-6h`、`T-60m` 或 `T-15m`。现有入口按每场计划开球计算采集时段。下一窗的正式首版仍绑定实际签发截止。

```bash
bundle=workspace-updates/20261127-phase-one-evidence/europe-market-collector-20261128
python /path/to/source/scripts/capture_public_club_markets.py \
  --fixtures "$bundle/fixtures-uel.json" --team-ids "$bundle/team-ids.json" --out /path/to/uel-capture
```

欧协联使用 `fixtures-uecl.json`。从固定的原登记数据重建输入，并复跑已保存的取样，使用下列命令。[固定采集源码](https://github.com/kaka597000/Football-Analysis/commit/f73b7e6fe9da7c542c46a69dd92fcf8739a79526)

```bash
PYTHONPATH=/path/to/source/runtime python -B "$bundle/prepare.py" \
  --original-data /path/to/registered-inputs --source /path/to/source --out /tmp/europe-market-replay
for file in fixtures-uel.json fixtures-uecl.json team-ids.json replay.json; do
  cmp "$bundle/$file" "/tmp/europe-market-replay/$file"
done
```
