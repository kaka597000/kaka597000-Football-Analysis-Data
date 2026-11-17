# 新环境从这里恢复（最终增量版）

**2026-11-17 xG补采：** [BSD欧国联xG字段与质量核查](workspace-updates/20261117-xg-availability/README.md)保存昨晚10场xG/逐射门原文、13次请求元数据、字段冲突及追加冻结。此为复盘后的来源补充，不能覆盖旧报告或回填赛前；数值接入与训练尚未执行。恢复时核验本增量manifest，基准身份仍使用下方复盘归档。

**2026-11-17复盘增量：** [欧国联10场复盘](workspace-updates/20261117-nations-review-0833/README.md)包含原预测引用、累计44场旧候选首版所需结果、10场双源赛果、29球事件核验、复盘及决定冻结。核对manifest后恢复到新目录，不覆盖不同冻结；现有 `future/nations-repair-state` 已追加至10已结/8待赛。活动参数与旧模型工件不变，不将结果结算当成新训练或晋级。

**2026-11-16赛前报告增量：** 恢复既有资产后，另核验 [欧国联赛前交付](workspace-updates/20261116-nations-prematch-2044/README.md) 的压缩包和逐文件SHA，再恢复本轮10场证据、原矩阵、综合推荐与完整冻结链；已有不同内容不可覆盖。此前模型恢复与18场研究首版仍使用 `workspace-updates/20261116-nations-repair/`，本次不切换活动模型。7个Secret测试结果另见 `api-probes/43863271589-1/README.zh-CN.md`，仓库不含密钥值。

**2026-11-10 四联赛刷新研究：** [最新独立刷新增量](workspace-updates/20261110-four-cohort-refresh/README.md)保存181条新增、102场时间留出、8份未晋级候选及冻结报告；活动模型保持。恢复时核验其独立归档与清单，不能将最终候选当作活动版本。

**2026-11-10补充：** 用户已接受公开数据仓库及赛事数据上传，覆盖下文旧私有要求；凭据仍不入库。本轮源码以 `latest-source.json` 为准，最新复盘/冻结/审计增量见 `workspace-updates/20261110-review-and-audit/`，须在旧快照恢复后另行核验应用。旧冻结字节不得覆盖修改。

**2026-11-03补充：** 主快照有意去重排除了旧交接历史。固定配方原始证据与incoming数据集manifest还需从固定旧交接commit的`audit-history-parts/`和`models-history-parts/`恢复。已在新环境找回并完成严格集成469项零跳过验证，具体来源、路径与步骤见[资产恢复验收](workspace-updates/20261103-asset-recovery/README.md)。

仓库须保持私有。固定恢复标签workspace-ready-20261102-v2；总清单latest-workspace-recovery.json。旧完整快照无需重传，脚本自动获取固定base并应用64文件增量与更新Git历史。请先读[最终交接说明](workspace-updates/final-20261102/FINAL-HANDOFF.md)。

```bash
git clone --single-branch --branch main https://github.com/kaka597000/kaka597000-Football-Analysis-Data.git /workspace/recovery-repository
cd /workspace/recovery-repository
git checkout workspace-ready-20261102-v2
python workspace-updates/final-20261102/restore_latest.py --stage /workspace/recovered-workspace-20261102
```

脚本仅恢复到全新目录，完整验证基线/增量/新交接冲突副本，不覆盖当前工作空间。恢复后按交接说明从更新Git bundle恢复main或独立V2分支、比对资产路径、复装依赖，并通过安全设置重新绑定密钥。BSD/OpenFoot旧进程未收到绑定，不把此问题误诊为密钥失效。活动权重和旧冻结保持。
