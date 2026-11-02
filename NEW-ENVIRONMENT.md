# 新环境从这里恢复（最终增量版）

仓库须保持私有。固定恢复标签workspace-ready-20261102-v2；总清单latest-workspace-recovery.json。旧完整快照无需重传，脚本自动获取固定base并应用64文件增量与更新Git历史。请先读[最终交接说明](workspace-updates/final-20261102/FINAL-HANDOFF.md)。

```bash
git clone --single-branch --branch main https://github.com/kaka597000/kaka597000-Football-Analysis-Data.git /workspace/recovery-repository
cd /workspace/recovery-repository
git checkout workspace-ready-20261102-v2
python workspace-updates/final-20261102/restore_latest.py --stage /workspace/recovered-workspace-20261102
```

脚本仅恢复到全新目录，完整验证基线/增量/新交接冲突副本，不覆盖当前工作空间。恢复后按交接说明从更新Git bundle恢复main或独立V2分支、比对资产路径、复装依赖，并通过安全设置重新绑定密钥。BSD/OpenFoot旧进程未收到绑定，不把此问题误诊为密钥失效。活动权重和旧冻结保持。
