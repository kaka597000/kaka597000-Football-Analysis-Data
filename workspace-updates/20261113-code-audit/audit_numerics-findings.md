# 数值、权重与评估逻辑审计

完成时间：2026-11-13 15:40（北京时间）。执行范围：源码 /workspace/Football-Analysis；审计文件保存在本目录。按 TEAM.md 先报告触发条件与拟改文件，root 确认优先处理两个确定的评估边界问题。

## 结论

修复两类可复现缺陷：矛盾完赛状态仍被结算；综合比分比较接受显式赛事身份冲突及换ID的重复物理赛事。仅修改研究评估层及其回归测试。活动参数、工件、注册表、旧冻结和真实数据库没有修改，没有训练或网络访问，也不宣称提高任何真实命中率。

## NUM-01：互补性评估忽略第二状态字段的冲突（已修复）

位置：runtime/research_program/complementarity.py:16。

触发：输入赛果 status=completed（或 FT），同时 event_status=LIVE、POSTPONED 或 CANCELLED。旧逻辑只检查 status，因此三场合成样本中含一场 LIVE 冲突时仍返回 settled=3，并累计该行的命中和配对指标。冻结和结果来源地址校验不能消除这一字段冲突。

修复：在结算前按现有 selection_review 的状态口径拒绝同时出现终场与非终场状态；一致的 completed/FT 组合保持可结算。未把有冲突记录静默丢掉以缩小分母，调用直接失败并要求修复来源。

回归：test_conflicting_result_status_cannot_settle，覆盖三种冲突及一致终场状态。

## NUM-02：综合比较未核对显式物理赛事身份（已修复）

位置：runtime/research_program/selection_review.py:29、:40、:58。

触发和修复前证据：

- 合法综合冻结引用合法 pair 的 freeze_id 和 SHA，但 pair.fixture 的主队、客队、competition 或 stage 与综合记录冲突，旧代码仍给出净命中；最小复现返回 comprehensive_hits=1。
- 赛果使用相同 match_id，却明确携带不同开球时间或球队/赛事/阶段，旧代码仍结算。
- 将同物理赛事复制为另一 match_id，并分别保持冻结校验正确，旧代码将同一场算两次。

修复：

- 保留既有 match_id、cohort、开球和冻结时间校验；补查双方实际提供的 competition、stage、home、away。
- 赛果明确提供开球时间时按时区感知时间比较；双方都提供身份字段时拒绝冲突。
- 有主客队字段时，以 cohort、stage、实际开球时间、home、away 检查物理赛事重复，拒绝不同ID重复计数。
- 合法 pair/综合的不同 cutoff、等价时区表达、同队不同开球场次继续通过。旧记录缺失的可选字段不补造、不据此认证身份完整；现有返回 schema 和 by_model_version 保持。

回归覆盖四种 pair 身份冲突、六种赛果身份冲突、不同ID同物理赛事、不同 cutoff/时区、同队不同开球及旧可选字段缺失。

## 验证

命令：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=runtime:runtime/research_program /workspace/football-venv/bin/python -m unittest research_program.test_selection_review research_program.test_complementarity -v
```

先添加失败回归：17个测试，14个失败子案例/测试，均是旧代码未拒绝上述输入；原有测试无回归。修复并补兼容用例后：19项测试全部通过，新增7个测试方法。完整日志见 audit_numerics-tests.log；机器记录见 audit_numerics-validation.json。以上都是合成的软件契约测试，不是历史/真实赛前效果验证。整仓集成由root统一执行，本代理不重复执行其它组。

只读核查历史综合/pair引用133条，125条这些身份字段相容；另外8条旧日联杯记录使用不同提供方队名命名空间，且综合记录本来就缺少此函数原本要求的 cohort，因此没有把它们当新增回归或自动映射。未改写历史冻结。

## 审查范围与未改项

已读取并审查：challengers、walk_forward、diagnostics、feature_ablation、elo_kelly_ablation、elo_kelly_shadow、mixture_selection_shadow、score_mixture_shadow、xg_native_scale、selection_review、complementarity，以及共享 v2_test.evaluation 与相关测试、文档。重点核对同日/月份训练边界、目标标签读取、均值/概率混合区别、Elo零和更新、外部凯利参考池、选权重/门控段、概率矩阵与独立覆盖分母。

在已读数值逻辑中没有另一个足够确定且可复现的高价值数值错误；不据此宣称完整正确性认证。未改挑战者或训练/推理核心源码，避免扰动训练/预登记源码哈希。

selection_review 的 role:version 是现有全批汇总维度；不同赛事混合成明确全批指标本身合法，不能仅凭它未按 cohort 细分就认定为bug。未改变 schema 或移除全批指标。若以后需要解释队列/工件差异，可以在保留全批总览的前提下新增独立分解；本次不作为已证缺陷处理。

