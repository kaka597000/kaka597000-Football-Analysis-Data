# 私有完整工作区恢复备份 · 2026-11-02

本目录提供源文件、数据库、模型、报告、原始附件、交接资料和冻结记录的归档。必须保持所在数据仓库为 Private；不包含环境密钥。它是一次有截止点的备份，不是持续同步服务。

## 新环境恢复

使用平台提供的 GitHub 认证，检出本目录所在的固定提交；不要在聊天或命令参数中粘贴访问令牌。

```bash
git clone --single-branch --branch workspace-full-20261102-v1 https://github.com/kaka597000/kaka597000-Football-Analysis-Data.git /workspace/recovery-repository
cd /workspace/recovery-repository/workspace-backup-20261102
python restore.py --stage /workspace/recovered-workspace-20261102
```

脚本逐片验证SHA256及压缩归档整体哈希，安全解包到必须不存在的新目录，验证每个文件的大小/hash，并检查SQLite一致性。不会自动覆盖现有/workspace目录；若目标已存在，必须先比较并保全两套。

源代码的Git提交及分支见source-commits.json。归档中Football-Analysis是原本地代码的检查点，不是最新main。新环境另行克隆代码仓库并检出latest_source.commit；原检查点源码保持单独目录，不用旧源码覆盖main。数据库、模型注册表存在新旧冲突，详见transfer-audit/RESTORE-ACCEPTANCE.md；保留原件和incoming版本，默认活动库切换尚未完成。

恢复后的路径必须显式映射：归档根目录对应原/workspace，模型注册表可能引用/workspace/WCPP绝对路径。只有在确认新环境目标不存在时，才逐个移动恢复目录到其原路径。严禁把整个恢复目录盲目覆盖已有工作空间。

## 覆盖与限制

- inventory.csv为原盘点清单，files.json为实际归档文件清单，excluded.json说明逐文件排除项。必须检查排除项；不能把凭据排除解释为全部字节无损迁移。
- SQLite使用只读源连接和backup接口生成一致性副本，不用正在使用的数据库文件直接拷贝。数据库逻辑内容保留，备份文件物理哈希可能与原件不同。WAL/SHM为临时伴随文件，不单独恢复。
- 原始API响应、附件和源文件经过当前绑定值和凭据模式检查；检查不能证明不存在所有可能的敏感信息。仓库不得重新公开。
- Git历史另存git-bundles/，共7套仓库；路径映射见git-bundles.json。可用git clone /绝对路径/repository-N.bundle 恢复其分支和提交，源文件按files.json还原。GitHub上的固定提交也保留。
- 重复的transfer/incoming目录不二次打包；旧核心/历史交接包已在同一私有仓库handoff/wcpp-20261102分支固定提交a0635b6551ba7a31c524ba3b25aee7e0ccbb8430中保留。恢复审计和迁移测试记录保存在transfer-audit。
- node_modules、Python虚拟环境、缓存和编译字节码不打包。python-packages.json/runtime-versions.json登记版本；源码requirements和setup脚本用于复装。外部安装源将来可用性不保证。
- WCPP/tools中的MATLAB等工具未归档，原件不删除。MATLAB的许可与安装介质需通过官方授权方式提供；本项目默认纯Python。
- 云端秘密、.aws/.codex平台配置及活动进程不上传。新环境通过安全设置重新绑定密钥；邮件和定时任务也必须单独验收，不能从文件存在推断已运行。
- 新增分析或训练不会自动进入本次固定备份，需要另行提交增量备份。恢复验收时间及实际数量见RESTORE-VERIFICATION.json。

## 必须同时恢复的新交接资产副本

主归档保留原WCPP目录；最新交接中的数据库/注册表冲突副本额外放在incoming-core/，不要遗漏。恢复命令：

```bash
python incoming-core/restore_incoming.py --stage /workspace/recovered-incoming-20261102
```

此包为先前独立验收的1650文件、21队列42活动工件及两库，整包SHA256为8d6415a4d62a26edbe632620d76372e25eee61d038418ee96af3f155d8205e07。脚本验证分片和整体，解包并验证文件hash/工件hash及数据库，不覆盖原WCPP。两套一并保留供后续接入决策。除它以外的旧交接历史包仍在同一私有仓库原handoff分支中保留；完整旧工作区非工具资产已在本次主归档中覆盖。

固定恢复标签：workspace-full-20261102-v1。私有仓库main中的latest-workspace-backup.json登记最终完整commit。
