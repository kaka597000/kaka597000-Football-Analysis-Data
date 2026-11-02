# 新云端最终交接（增量版）

原完整快照workspace-full-20261102-v1保持不变，本次仅新增64文件（2修改、62新增）与2套更新的Git历史，未删除原数据。manifest.json给出逐文件hash，changed archive包含一致性读取后的文件；未变化数据库不重复上传。

## 新环境一条恢复命令

选择同一GitHub账户，确保新环境可访问私有数据仓库。只克隆main即可，脚本按固定提交获取旧完整快照，不用全分支下载旧归档。

```bash
git clone --single-branch --branch main https://github.com/kaka597000/kaka597000-Football-Analysis-Data.git /workspace/recovery-repository
cd /workspace/recovery-repository
# 检出latest-workspace-recovery.json指定的final_tag，避免后续main变化。
git checkout workspace-ready-20261102-v2
python workspace-updates/final-20261102/restore_latest.py --stage /workspace/recovered-workspace-20261102
```

目标目录必须不存在。脚本验证固定基线及文件hash，恢复258154基线文件，再仅对匹配旧hash的文件应用增量，验证组合目录的258216文件；另外恢复incoming-20261102/WCPP里的1650文件、42工件和两库副本。不会自动替换现有/workspace/WCPP或源码。若目标已有内容，先比对并保全两套。

## 接续时务必读取

1. source-commits.json：源码主分支已含八模块单场分析、市场水位优先、阵容情景和哈希兼容修复；V2 Test独立。最新主分支及V2的Git历史均在本增量git-bundles.json中映射到bundle文件，不依赖旧云端存活。原本地107文件检查点也在旧完整快照中，不能用其旧源码覆盖main。
2. 恢复Git历史：读取本增量git-bundles.json；对原路径wcpp-transfer-20261102/source-627838f对应bundle执行git clone <bundle> <新的源码目录>，再按source-commits.json检出main commit或V2 commit。bundle保存所有分支；检查点源码单独保留。
3. /workspace/WCPP默认资产仍19队列，incoming是21队列；二者注册表和统一库有冲突，均保留。先明确选用路径，不盲目覆盖。需要沿用绝对路径时，仅在目标为空且保全之后搬入，不修改原工件哈希。
4. 恢复后的WCPP/reports/v2-audit-20261102/阶段一审计与决定.md和用户授权V2方案原文.txt：阶段一完成；动态融合、球员级影响模型、新校准、完整滚动回测尚未完成。训练历史as-of时点缺失是重点，不能冒称无泄漏或命中率提升。
5. WCPP/reports/portland-lineup-20261102-1006/：今天波特兰—休斯敦首发后综合2-1/主胜/大小观望，与早先待定版本分别冻结；最新赛果未在本轮交接更新，勿把功能验收报告当新赛事分析。
6. 密钥不在仓库；secret-requirements.json只记录名称。BSD/OpenFoot已适配客户端，但旧进程未收到两项绑定，尚未真实鉴权，不要误称密钥无效。通过新环境安全设置提供值，不读取旧聊天原文写文件。环境配置发布失败不影响Git备份；新环境须独立验证权限。
7. 浏览器按源码setup/ai-browser/install.sh重装，依赖参照旧快照python-packages.json及源码requirements。不要恢复缓存/活动进程或MATLAB许可。邮件及自动任务未在本轮部署/复验，不追认成功。

先完成还原验收、读取约束并确认资产路径，再继续用户授权V2计划。不要重训或替换活动模型来让检查通过。固定快照+本增量已做组合文件哈希验证，当前环境仍保留，不删除原工作成果。
