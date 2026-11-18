# 2026年11月18日仓库检查

本轮修复盘口采集的分页、欧国联B级过滤、三组国家队别名和覆盖分母；增加同矩阵、同盘口的独立大小球目标实验。原冻结和38份活动工件均核验不变。源码PR：[Football-Analysis #43](https://github.com/kaka597000/Football-Analysis/pull/43)，固定执行版本 `3e4412b853bfa258f6b8a121d35cc76d3e9965b5`。

- 严格集成：25组、982次测试执行，0失败、0跳过。
- 真实存档重放：旧代码0/8，新分页+B级5/8，本日别名审核后8/8、51条有效总球报价。本日别名和旧query_time代理明确标为诊断重放，未新增赛前预测。
- 大小球：18场唯一比赛、26个原冻结比赛节点、194组模型矩阵/盘口，四种政策776行。固定Test按严格全赢目标从7/16到8/16；2场走盘保留覆盖。结果已经见过，属于开发诊断，未来效果仍待验证。
- D级：两次合法有界查询均200空数组，尚无可核验InferSports D级映射。不能把空响应说成支持或不支持D级。
- 状态：旧18场、xG8场都已完成复盘，更新过期pending。原云端TheOdds响应成功，但赛事已开赛，不能继续标为密钥缺失。

永久证据在 `repository-audit-evidence.tar.gz`；`manifest.json` 保存每个成员的字节数和SHA256。`infer-evidence/alias-review-candidates.json` 的原字节与源码配置中引用的审核哈希一致。实际部署和CI见随后追加的 `delivery-receipt.json`，源码就绪不代表新任务已实际运行。

恢复并检查：

```bash
python workspace-updates/20261118-repository-audit/verify_archive.py --out /tmp/repository-audit-restore
```

`input-dependencies.json` 指向仍长期保存的旧修复计划、xG工件和复盘原文，避免重复上传整套模型。重跑数值实验先恢复这些依赖，在独立工作树签出上述源码提交；解包的 `scripts/compare_total_objectives.py`、`scripts/replay_infer.py` 保留实际执行步骤。脚本中 `/workspace` 路径为本项目恢复布局；更换位置时明确重定位，禁止改原工件哈希。重跑输出使用新目录。

回滚只需在现有无人值守工作流将采集版本恢复 `3eca355a9e801c15d21c9b9b87e84592be15cee9` 并停用新增InferSports步骤；训练/锁定推理仍为 `6639867d502a2dfe53a9a235c8761f8ee6b91533`，无需改动模型、冻结或历史复盘。

北京时间11月18日08:58–08:59已完成主分支真实部署运行 [44212218194](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/actions/runs/44212218194)，所有步骤成功并自动提交 `3dab247275faab7e7a1d0d771468f618802318c5`。Nations无未开赛目标，Infer只查ESPN一次、未消耗供应商额度，因此不声称本轮已做云端Infer鉴权或盘口覆盖验收。巴西甲通道取得208条有效报价、覆盖5/6，另1场身份未匹配；18场旧计划复盘仍完整，新增复盘版本未改旧冻结。详见 `delivery-receipt.json`。
