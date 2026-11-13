# 当前20项赛事的8 API实测

核查日期：北京时间2026年11月13日。

- [完整报告](report.md)
- [20赛事 × 8接口覆盖表（CSV）](competition-matrix.csv)
- [逐字段能力与证据（CSV）](field-capabilities.csv)
- [机器可读结论](audit-summary.json)
- [独立审查](independent-audit.json)与[校验回执](verification.json)
- [冻结回执](delivery.json)与[归档清单／哈希](manifest.json)

6个接口返回数据。API-Football和TheRundown接口均403，Luna使用已有Chromium＋Playwright正常浏览器导航也均403；不能据此认定密钥无效。The Odds有实取机构盘口；InferSports本轮恢复200，但所测47条报价仅2条让球符合60分钟鲜度，大小球0条符合。日联杯未验证到API数据覆盖；目录列出、实际样本、访问受阻和权限不足已分开。

冻结：`34c39469fa74707a-v000001`，北京时间09:50:09，stage=review。原模型、注册表和数据库不变，未发布环境。

本归档不依赖临时Actions链接。核验manifest中的压缩包SHA256后，解包到空目录，逐成员校验哈希；全部77成员已重读校验。包含8服务各自计划、脱敏响应、字段与赛事清单、浏览器访问证据、冲突与时区修正、报告生成脚本和原冻结记录。结构化响应与原始字节哈希分别标注；没有原字节的响应不能冒称可复算原字节哈希。

只读复算报告使用归档内`build_report.py`，无需联网、密钥或重新采集；在副本中运行，避免修改已冻结派生文件。不要重复运行`freeze_and_archive.py`，也不需要重训模型。源码版本固定为`ddfbc43197df8944072c70135e2a2831ae1a3ef5`。

限制保留：football-data实际12次请求超出内部10次计划，末次间隔不足6秒，且欧冠响应被覆盖丢失，故该项未验证；The Odds／Infer存在赛事身份或分级冲突；OpenFoot派生xG不能当原生数据；部分报价陈旧。完整回执不把这些缺口包装为通过。此次仅数据报告提交，无源码变更或新增远端CI运行。
