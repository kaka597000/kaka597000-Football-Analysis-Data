# 欧国联与日联杯代码审计（2026-11-13，北京时间）

审查范围：`runtime/nations_league/*`、`runtime/jleague_cup/*`、赛事文档；读取共享比分矩阵/阶段校验逻辑。未联网、未操作Git、未训练或晋级真实候选、未改真实数据库或冻结。

## 已复现与修复

1. **P1：未核验库存阻挡真实欧国联记录升级。** `nations_league/database.py` 的 `_projection_conflict` 曾把 `raw_verified=0` 的 `STATUS_FULL_TIME` 与日期当作已证实结果；先导入缺原文、声称2025-01-02完赛的库存，再导入原文明示2025-01-01的summary，得到 `quarantined=1`，事件仍 `summary_verified=0/training_eligible=0`。较晚的库存query时间或缺原文summary类别也会压过真实scoreboard。现按原文核验可信度优先投影；只有已核验完赛来源参与结果矛盾/时点保护。新增两项回归，仍保留已核验比分冲突隔离、旧响应不能回退、追加观察及事务回滚保障。该数据库源码未被16份候选锁定。

2. **P1：日联杯互相矛盾的结果来源可进入训练。** 旧 `evidence.verify_row` 接受列表 `2:1 AfE` 与同场详情 `3:1 After Extra Time`（分段 `1:0,0:1,2:0`），旧数据库导出一条合格90分钟历史；列表延期/未知标志也可借用完赛详情。新 `safe_evidence.verify_row` 在复用旧90分钟重算后，要求列表明确AfE/AET/AfP，展示总分与详情一致、完赛类型一致。新的safe_cli建库在临时库完整重验后独占发布；训练入口在创建输出或调用原训练前严格检查所有合格历史；QF预测严格检查首回合历史证据。旧锁定证据/数值源码不改。

3. **P1：欧国联未来事件ID与标签契约不完整。** 旧 `validate_future` 接受 `match_id=espn:999/source_event_id=101` 且带 `home_90=3`，可能以错误事件ID冻结并携带目标赛果。新 `safe_cli` 对应真实源事件ID，拒绝90分钟、总分、加时、点球、常见比分/结果别名，复核competition/级别/阶段/current-test角色、实际执行的旧核心及训练截止。日联杯未来入口同样拒绝标签别名并保留历史首回合标签的合法位置。

## 兼容方式与完整批次

root确认使用新增安全入口保留旧工件。新增运行文件仅 `nations_league/safe_cli.py`、`jleague_cup/safe_evidence.py`、`jleague_cup/safe_cli.py`；数值直接调用既有函数，未复制或调整拟合/比分公式。三篇赛事模型文档已将未来训练、预测、冻结命令切换为真实可运行的safe_cli；旧入口仅用于历史复现。新输出记录执行校验层版本/SHA、旧核心/依赖SHA及共享数值源SHA，训练另留execution-guard.json。

两种未来冻结入口均在首个save之前校验完整名单、索引/角色/阶段身份并计算所有可发场次两边结果，结束再检查源与时点，以及严格JSON可发布性和原冻结凭据字段禁入规则。后场业务错误不会留下前场冻结；未核验首回合的日联杯次回合先完成身份验证，再单列deferred。跨文件磁盘故障/并发开球期间的整体事务回滚不在本轮保证内。

## 只读实际资产核查

- 16份旧候选：欧国联8、日联杯edition4、八强4；全部工件字节和已登记依赖SHA保持匹配。
- 对16份实际core进行160个已见/未见球队与允许场地状态数值重载分支检查；非负、有限、归一化、胜平负合计及矩阵均值通过，最大误差4.44e-16。未见球队使用拟合总体先验；欧国联64次missing检查通过。日联杯edition安全输出补充缺失球队元数据，不改概率。
- 只读日联杯扩展数据库233条合格历史，40个需ET/点球详情的案例，列表总分及状态均与详情一致；未发现该漏洞已经污染当前数据库。欧国联当前数据库不存在raw_verified=0的事件，本轮修复是可复现边界缺陷，不将合成失败冒称现有数据事故。
- 本轮仅软件与参数重载验证，不是赛前as-of回测、预测效果提升或活动模型验收。原历史first-known未知、小样本、真实盘口缺失等验收限制维持。

## 锁定源码（全部保持原SHA）

|文件|SHA256|受影响旧候选|
|---|---|---|
|nations_league/model.py|ae412b2120605bc702b2836b727568289cb637a1f89426b343661749ca7141e5|8份欧国联|
|jleague_cup/model.py|041815a70a4e475544a079b2e1fa0b6589ce083ca9875616f9f025f03aad11f7|4份edition+4份QF|
|jleague_cup/evidence.py|39b5a13ddde27680fbd096a136b47417669866dbe93d09e53af30f2e9f0e7556|4份QF|
|jleague_cup/database.py|0a3cf0fb96a1b9e654a452ad12f51164e6b34d994afad529a14a230e7c2d7736|4份QF|
|jleague_cup/quarterfinals.py|218a071ec639d5bc2ded0570a69e68718cde4d59ba85b39ae0dec3573e276fb9|4份QF|

最终测试命令、数量及逐工件SHA复核见 `audit_league_models-validation.json`；160分支明细见 `verify_league_artifacts-validation.json`。
