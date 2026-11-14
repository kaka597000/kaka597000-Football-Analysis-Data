# 剩余欧国联与巴西甲｜2026年11月15日

[完整报告](report.md) · [CSV](比赛分析展示.csv) · [冻结回执](delivery.json) · [来源审计](source-audit.json) · [代码与CI回执](ci-summary.json)

03:07北京时间完成本轮5场欧国联、2场巴甲赛前冻结。比分/胜平负各7场，实际大小球4场给方向、3场观望。优先三场：葡萄牙2-1丹麦、北爱尔兰1-0乌克兰、瑞典1-1波黑。欧国联候选未晋级；巴甲现有双模型实际加载，训练只到10月9日。原活动参数、注册表和旧冻结不变。

雷速首页核实五场赛程并看到葡萄牙首发新闻标题，但详情和正文受滑动验证阻断；没有取得完整11人名单。ESPN/FotMob/SofaScore缺项与失败均保留。七场盘口身份、来源哈希及真实报价时间均已核验；不使用错误的奥地利—冰岛事件。巴甲采集原日志存在请求前/抓取完成时间重复，保留原记录及time-audit.json，以落盘时间作为保守可用上界，不伪造HTTP完成时间。

源代码commit与PR见delivery.json，分支为analysis/remaining-nations-brazil-20261115。该版本已用于本轮人工运行，main和后台采集工作流未切换。回滚代码到1257fdde7b6746b7ba6d2aa919382214a2cfb589即可恢复原范围/映射；旧模型不需要回滚。数据父commit见manifest.json，不能删除本轮冻结链。

长期恢复：先运行 `python verify_archive.py --stage /tmp/NEW-remaining-restore`，验证原文字节、所有引用的旧归档和冻结链，再按recovery-map.json协调原始路径与WCPP符号链接。源码另checkout精确commit，Python/numpy/scipy/LightGBM等版本见inference-environment.json。候选模型、训练数据/协议、巴甲两份原工件及原运行输入均已保留；其余旧文件复用长期归档，不依赖Actions短期下载链接。比赛过期后不能绕过未来时点检查重新冒称赛前运行，只读取已冻结矩阵或使用独立历史研究入口。

prepare.py保存了最初的60秒窗口拒绝与sources字段名失败；finish_predictions.py只修正本轮输入证据字段名后完成真正predict_active运行。失败诊断保留，不修改模型或哈希检查。冻结receipt为规范化记录哈希，不等同于JSON文件字节哈希。全部尚待比赛结果结算；恢复校验、CI与代码完整性不等于预测准确率已通过验收。
