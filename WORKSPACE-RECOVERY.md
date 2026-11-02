# 完整工作区恢复入口

仓库必须保持私有。完整备份固定提交见latest-workspace-backup.json，恢复标签workspace-full-20261102-v1，目录workspace-backup-20261102。

```bash
git clone --single-branch --branch workspace-full-20261102-v1 https://github.com/kaka597000/kaka597000-Football-Analysis-Data.git /workspace/recovery-repository
cd /workspace/recovery-repository/workspace-backup-20261102
python restore.py --stage /workspace/recovered-workspace-20261102
python incoming-core/restore_incoming.py --stage /workspace/recovered-incoming-20261102
```

先读该目录README.md。两套目标目录必须不存在；不会覆盖现有目录。主归档258154文件及16库验证通过，incoming交接1650文件、42活动工件和两库验证通过；7套Git历史另存bundle，最新源码提交与原本地检查点分别保留。不能将检查点旧源码当作main最新版。

密钥、授权许可、已安装依赖及活动进程需要独立恢复；依赖版本及安装脚本随包保存。数据库/注册表冲突副本均保留，接入前按说明比对。后续新增分析/训练必须另做增量备份，本次不是自动同步任务。

固定备份之后的源码及规则增量见latest-source.json和workspace-updates/。恢复固定快照后还须检查这些增量；旧快照保持不可变。
