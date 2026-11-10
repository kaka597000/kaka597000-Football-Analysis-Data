# 欧国联数据库交付（2026-11-10，北京时间）

Luna采集2018—2026年ESPN公开数据，9次年度清单请求、766次逐场摘要请求全部成功，共775次。实际独立SQLite保存824场、55支球队：756场普通完赛、4场加时、6场点球决胜、52场待赛、6场取消。

原文和阶段补证核验后，502场可作后续分级研究输入：A109、B139、C174、D80，均为联赛阶段。其余322场包括174场等级/阶段缺证据、10场加时或点球分段证据不足、80场摘要隔离、52场待赛及6场取消。隔离的是摘要观察，824场赛事清单仍完整保留。

80份隔离摘要中，30份与赛程阶段冲突、48份摘要内部阶段矛盾；另2份点球记录本场比分不平，属于两回合附加赛，需核对总比分。不能仅由本场比分不平断定来源错误。当前严格门槛未解析两回合总比分，因此保守隔离，尚不支持这两场的训练准入。

数据库包含teams、events、source_records、observations、import_runs、quarantine；当前1510条追加观察、695条已核验来源记录、2次导入。重复导入幂等，文件SHA保持一致。SQLite integrity_check=ok，外键无错误。所有502场导出再次通过正式训练入口的来源与阶段检查；这不代表已经训练模型。

原统一数据库、活动注册表和38个活动工件共40项SHA与操作前一致。欧国联已成为第19项正式范围，尚无通过验收的活动预测模型。未部署新定时刷新，未修改活动模型，未发布环境。

只完成ESPN同源清单与摘要核对，未取得独立UEFA清单认证；覆盖保持PARTIAL_UNTIL_INDEPENDENT_INVENTORY_VERIFICATION。历史first-known保持未知，本次抓取时间不追认为赛前可用，历史as-of未认证。

源码PR #25已合并，commit 641b7cb7b8ae5fae4fa5be0f7d7417f88369036a。本地673项测试、23组全部通过，无跳过；静态检查427个文件零发现。远端完整测试及Linux/Windows兼容性检查通过。

数据库文件：/workspace/WCPP/data/nations-league/uefa-nations-20261110.sqlite。来源、导出、测试日志、幂等记录和独立审计均在本目录。原始HTTP查询时间采用UTC保存，交付时间以北京时间登记。

## 下载与恢复

- [SQLite数据库](uefa-nations-20261110.sqlite)
- [完整原文及审计快照](nations-league-snapshot.tar.gz)（约23MB，806个文件）
- [文件清单与SHA256](manifest.json)
- [独立验收结果](independent-audit.json)
- [数据库统计](database-stats.json)
- [源码PR #25](https://github.com/kaka597000/Football-Analysis/pull/25)

先核对manifest中的压缩包SHA，再解压到独立目录核验逐文件SHA。压缩包保存workspace/nations-league-20261110及workspace/WCPP/data/nations-league目录结构；数据库中的原文路径指向/workspace/nations-league-20261110/staging，恢复后须保持对应路径，才能重新验证来源或导出。不要覆盖其他旧数据库或旧冻结文件。SQLite单文件可独立查询，但训练导出还需要原文快照。
