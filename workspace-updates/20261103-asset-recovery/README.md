# 资产恢复验收 · 2026-11-03

恢复来源已实查，原先缺失的历史证据不需要重新采集替代。

## 固定来源

- 完整基线：`workspace-full-20261102-v1`，commit `466fd626a47481e70b176a9a69c58224d7d1bf63`，目录 `workspace-backup-20261102/`。
- 最终增量：`workspace-updates/final-20261102/`，原入口 `restore_latest.py`，组合清单验证258216个文件，包含16个SQLite一致性检查。
- 被基线有意去重排除的旧交接历史：`handoff/wcpp-20261102` 的固定commit `a0635b6551ba7a31c524ba3b25aee7e0ccbb8430`。`audit-history-parts/` 包含固定配方原始历史；`models-history-parts/` 包含incoming所引用的数据集manifest。只运行旧的一条主快照恢复命令会遗漏它们。

Git整包拉取等待过久后，按GitHub树API读取固定commit的完整文件清单，经同一平台认证下载raw文件。175个基线文件共2930109036字节，逐文件验证Git blob身份；历史包同样验证Git blob、分片SHA256、整包SHA256及CSV逐文件SHA256。没有使用本地907MB的校验失败残片。

## 当前资产路径

- 原工作区恢复：`/workspace/recovered-workspace-20261102/`。
- 默认运行路径：`/workspace/WCPP`，符号链接到上述目录的`WCPP`；保留原19路由注册表`WCPP-DUAL-4`，工件哈希无缺失或不匹配。
- incoming独立副本：`/workspace/recovered-workspace-20261102/incoming-20261102/WCPP/`，21队列、42工件、1650个core文件原始恢复验证通过；没有替换默认注册表。
- 旧审计历史：`/workspace/recovered-audit-history-20261102/`，16691文件验证通过。仅把原基线不存在的1456文件（410956184字节）追加到默认工作区，原文件零覆盖；10份冲突研究数据库留在独立历史目录。物理哈希不同不自动解释成逻辑数据不同。
- 旧模型历史：`/workspace/recovered-models-history-20261102/`，保留独立，不用旧历史覆盖活动模型。

固定配方目录`reports/auto-optimization-20261101/history/`内73条记录的原始比分证据均已找回，缺件数0。incoming的manifest补充及工件引用哈希核验结果见`incoming-manifest-recovery.json`。

## 本轮验证

源码身份：`a58595867e0bec71384b741d49c3e61387782228`，源码工作区无修改。

- 仓库静态检查：362个源文件，0项发现。
- 活动路由资产检查：19路由，0缺失/不匹配。
- 首轮严格检查暴露此前被资产缺失掩盖的环境依赖：缺少torch。按原备份安装CPU版`torch==2.14.1+cpu`，使用官方CPU wheel源，`pip check`通过。
- 最终`python scripts/run_tests.py --layer integration`：22组、469项，零失败、零跳过。该入口禁止把跳过算作集成通过。

这证明当前代码与恢复资产通过既有工程检查，不代表新增训练、历史as-of可用性已认证或未来命中率提升。Current/Test权重、旧冻结和永久参数未改；定时Actions未恢复，邮件未重新部署。

## 后续环境复用

先按`NEW-ENVIRONMENT.md`恢复基线加增量，再从上述固定旧交接commit取得审计/模型历史包。参考本目录`scripts/`：复制到`/workspace/recovery-tools/`，树清单分别放在脚本所用的固定本地路径后，执行`fetch_base.py`、`fetch_history.py`和`restore_history.py`；历史脚本默认审计组，参数`models-history`选择模型组。新目录恢复，不能覆盖现有目标。

恢复每一组后再按原清单比对，只追加缺失文件；已有不同哈希保留双份。必须单独核对incoming工件的`dataset_manifest_sha256`，不可制造一个新manifest替代原哈希。CPU torch并非当前源码requirements的完整必装项，具备真实私有训练资产时须显式补装后运行严格检查。

凭据仍通过安全环境绑定，本目录没有凭据值或原始聊天。恢复脚本与日志是工程证据，不是新的赛事预测。
