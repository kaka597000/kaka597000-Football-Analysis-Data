# 2026-11-16 欧国联修复交付

源码 PR：https://github.com/kaka597000/Football-Analysis/pull/39

最终实验 `experiment-v4`，数据库 `database-v2`，前向冻结 `forward-v2`。说明和完整数值见[修复验收报告](修复验收报告.md)、[逐级指标](历史逐级实验指标.csv)、[实验摘要](experiment-summary.json)。四个候选均未过晋级门槛；旧模型、旧库与注册表不变。前序比分偏差诊断也已保存。

`archive-index.json` 按原路径、SHA256和归档内成员定位内容；本次仅新增新内容，复用 20261110-nations-league 与 20261110-nations-model 两个既有长期归档，不依赖 Actions 临时下载链接。

## 校验和恢复

在本数据仓库根目录执行：

```bash
python runtime/restore_nations_repair.py
python runtime/restore_nations_repair.py --dest /tmp/nations-recovery
```

第一条只核对全部归档和成员；第二条把原绝对路径映射到指定新目录。若目标已存在但哈希不一致，拒绝覆盖。全新机器原路径恢复可用 `--dest /`，仅还原索引中 `/workspace/` 下的路径。

重新计算矩阵需要固定源码 commit `4c6061dd5eb2e4af77f18e64bd908a2847f039d0`，放置于 `/workspace/Football-Analysis-nations-repair-20261116`，安装该版本 requirements.txt，再恢复全部资产后运行：

```bash
python runtime/verify_nations_repair.py --index workspace-updates/20261116-nations-repair/archive-index.json --out replay.json
```

此命令校验新12个/旧8个工件、全部748条训练来源并重算90份冻结矩阵，只是历史数值复算，不生成新的赛前预测。`cloud-validation/` 保存真正全新 GitHub runner 的结果。

## 前向运行

`future/nations-repair-bundle/` 是已冻结的完整18场五轨；`future/nations-repair-state/` 是无人值守复盘追加的原始赛果、结果队列、复盘冻结和运行回执。没有真实90分钟终场证据就保持待结算，不能把有盘口的18场称为已结算18场。

本次沿用已有 cron，collector-only 与新复盘步骤固定到上述源码；原训练和已锁定推理保持 `6639867d502a2dfe53a9a235c8761f8ee6b91533`。实际部署运行号、源码CI与恢复验收见 `delivery-receipt.json`，未生成此回执前不得宣称部署完成。

回滚：撤销新增 Nations 复盘步骤并将 collector-only ref 回退 `1257fdde7b6746b7ba6d2aa919382214a2cfb589`；保留全部研究资产及冻结。不修改活动模型、不发布聊天环境。
