# WCPP旧云端向新云端交接

整理日期：北京时间2026年11月2日。交接包不等于已经迁移到新云端。

## 已在GitHub与仅在旧磁盘的内容

主项目 `/workspace/Football-Analysis` 为627838f1823087e7f3672ef2a121812b9ea6d05f，main与已核实的远端一致、无未提交修改。保留了原配方刷新、邮件准备、域外研究规则及远端Egidi研究分支合并。Git源码不等于完整可运行资产。

仅在旧磁盘或未核实远端副本的内容包括：约1GB统一SQLite、原始Canonical、21队列42活动工件、独立候选/历史模型、冻结台账、复盘/采集原始证据、WCPP约束与安装脚本。本包按实际文件盘点，不用旧聊天当恢复证据。

新云端截图说明源仓库存在35项本地变更。这些不在本交接工作区，无法从这里备份或认定内容。目标代理必须先保全这些改动；禁止git reset --hard、强推、checkout覆盖或用旧目录覆盖新源码。

## 包的分层

- core.tar.gz：一致性备份的统一库与Canonical、活动42工件、runtime登记/规则、全部冻结、恢复必需说明与脚本，以及11月1日四份最终原配方刷新候选。
- models-history.tar.gz：其余历史模型和研究工件，不表示活动晋级。
- audit-history.tar.gz：历史复盘、验证、研究库和来源证据。
- data-history.tar.gz：其余数据导出、原始数据和staging等。
- files.csv：每个纳入文件的实测SHA256/大小/所属包；各包另有*.manifest.json。
- excluded.json：未打包的可重新安装工具/缓存、旧交接包、MATLAB及凭据模式风险文件。排除不等于删除；原件留在旧工作区。凭据扫描是模式检查，不是安全性绝对保证。

不会复制环境变量中的密钥。setup旧脚本只装Python依赖，没有MATLAB要求。浏览器工具属于可重新安装组件，版本和测试说明在报告full-retest-20261102；浏览器安装成功不能证明雷速详情或盘口可取。

## 新云端恢复步骤

1. 先读取目标AGENTS并记录三个仓库分支、HEAD及未提交状态。保存截图提到的35项修改；不要替换它们。私有数据仓库在目标可能位于`/workspace/kaka597000-Football-Analysis-Data`，旧环境位置为`/workspace/Football-Analysis-Data`，须显式记录路径映射。
2. 获取归档、每包manifest及files.csv。禁止从公开仓库下载密钥。现Data仓库实测为public，本轮不向其上传运行资产；仓库名不能证明私密性。
3. 在全新暂存目录恢复，例如：

```bash
python restore.py --packages /path/to/packages --stage /workspace/wcpp-incoming-20261102 --groups core
```

需要完整历史时同时加入`models-history audit-history data-history`。脚本先核包SHA，再安全解压到新目录，逐文件核hash，检查42工件及两库quick_check；不改生产目录、不覆盖源码。
4. 若目标`/workspace/WCPP`确实不存在，可在核验成功后将暂存中的WCPP移动至该原路径；若已存在，停止自动替换，先对照/备份旧目录，保留两套。原模型与冻结引用使用/workspace/WCPP绝对路径；不能只改文件夹名后宣称可运行。
5. 复用目标源码支持的安装方式。旧`WCPP/setup/python/install.sh`依赖源码checkout已有runtime/research/requirements.txt，先确认目标代码存在及与原工件hash契约兼容；不要为了通过检查覆盖目标35项修改。当前/test保持各自工件和记录独立，不把候选当活动模型。
6. 核实环境秘密绑定名字和存在状态。旧环境当前仅football-data.org鉴权实测可用；5Dollar、API-Football、apifootball.com、TheOddsAPI、InferSports需要在目标安全设置确认个人绑定；不在聊天粘贴密钥，不从旧磁盘提取凭据。
7. 跑仓库静态检查/测试、活动42工件hash、真实未来赛程双模型和隔离冻结读写；赛前预测必须重新查询时间、首发及真实盘口，不发布本包旧预测作为新预测。

## 必须继承的研究状态

最高指标为未来首次冻结Primary精确比分；综合判断、当前、test分开。所有后续分析默认先保存冻结，赛前/滚球分开，修订不覆盖。

活动registry为WCPP-DUAL-5共21队列；当前MAIN1.2与test ML0.1等实际按registry读取，不是恢复出的Champion。MLS/日韩/澳超按独立EXPERIMENTAL/OOD研究，不借欧洲训练或宣称自动晋级。11月1日意甲/瑞典四个刷新候选已训练但PARTIAL_BLOCKED、inactive；其最终全量工件离线重放不算未见验证。

最近MLS批次`reports/mls-20261102-0853/`：LAFC—Minnesota综合2-1/主胜/小3.5；Portland—Houston精确比分待定/主胜倾向/大小观望；NE—Miami仅滚球观察。必须读取原冻结时间，不补追认。10月31日23场复盘已结算15场、仍有8场待更新，不能把旧阶段统计当全量最终赛果。

GitHub鉴权恢复；最近私有定时任务韩K采集在联赛身份核验处失败，邮件未部署、SMTP未绑定；不要称自动任务全部正常。09:00复盘没有成功部署，不追认完成。

原始数据库及旧环境不可删除。本次打包和暂存验证不是新云端实际恢复完成；只有在目标独立验收后才可确认交接成功。
