# 发布、冻结、复盘与未来验证审计

日期：2026-11-13（北京时间）。源码根：`/workspace/Football-Analysis`。本次仅使用本地文件与合成临时目录；没有调用赛事 API、网络来源或修改 Git。

## 审查范围与约束

已读 TEAM、源码及数据根 AGENTS、analysis-freeze-policy、score-distribution-adjustment、project-goals。审阅 predict_active/publication、analysis_freeze/prospective/review_events、future_validation/future_status、ucl_refresh_forward/ucl_refresh_review/promotion_review，并参照 paired_review 的独立分母、实际盘口五种结算及完赛规则。

本代理修改 `runtime/publication.py`、`runtime/research/prospective.py`、`runtime/research_program/future_status.py` 及对应测试，新增无写入/推理副作用的 `runtime/research_program/future_identity.py` 及测试。未修改活动 Current/Test 工件、注册表、数值模型、原始数据库或任何旧冻结；未重训、更新源码兼容哈希或追认历史预测。所有新写入和故障注入均位于 tempfile 目录。

## 已修复 5 项

### F1：同一 match_id 下的输入上下文冲突仍能取得首次发布资格

- 原触发：publication 只检查输出 match_id 和显式 cutoff/kickoff，没有检查主客队、赛事、阶段、回合、中立场或真实盘口。将 test.input.home 改为 OTHER，仍成功生成 FIRST_PREMATCH 并发布。
- 影响：两个模型事实上可能针对不同输入，却占用同场首次双模型冻结；会损害配对可比性与后续主评价身份。
- 修复：对已经提供的 model.input 核验完整字段集合及全部非时间值；两项顶层时点仍按实际同一时刻比较，允许等价时区偏移。缺省 input 的旧摘要维持原有兼容，不补造字段。实际 MAIN、weighted、ML、continental 和活动 adapter 均原样保存完整 fixture，已做静态调用链核查。
- 回归：逐项覆盖 home/away/competition/cohort/stage/leg/neutral/total_quote、输入缺字段及额外赛果字段；拒绝必须发生在 journal 和 freeze 写入前。旧摘要、中文回执恢复、等价时区和真实部分 Test 失败路径继续通过。

### F2：研究台账写入中断留下半文件，并可在等待或落盘后越过开球时点

- 原触发：prospective.save 对正式文件 open('x') 后直接 json.dump。合成 dump 在写入 `{"partial":` 后抛错，正式 .json 留下半内容且同场重试受 FileExistsError 阻断。原实现只在入口读取时间，等待/写入跨开球仍可发布。
- 修复：复用 storage_lock.exclusive_lock 串行化同场提交，并复用 publication.deliver 的完整临时文件、fsync、原子无覆盖链接与目录同步。deliver 增加默认关闭的 before_commit 回调；研究台账在锁内刷新记录时间，并在文件 fsync 后、链接前再次检查赛前边界。原 publication 调用默认行为不变。
- 回归：fsync 注入失败后无正式 JSON、无残留临时文件，后续保存成功；锁等待和提交时跨开球均拒绝；两线程同场并发仅一个成功、一个 FileExistsError，保留一个完整原始记录。既有冻结多进程追加链与发布中断回执恢复也继续通过。
- 边界：该独立研究台账维持原来的“同场禁止二次保存”语义，不新增相同请求自动恢复协议；异常若发生在原子链接成功之后，完整已提交记录仍保留，重试仍会拒绝覆盖。本轮没有做断电/内核崩溃或网络文件系统一致性实验。

### F3：LIVE/HT/中断观测被当作90分钟最终赛果结算

- 原触发：prospective.review 只检查 score_basis、数字比分和观测时间。给定赛后时点但 event_status=LIVE 的观测，仍返回 paired_settled=1，并增加两模型比分命中。
- 修复：与主配对复盘规则一致，要求明确 FT/completed；LIVE、HT、SUSPENDED、POSTPONED 等保留 pending。缺少状态或 final/non-final 状态互相冲突时拒绝。90分钟口径、来源与时间检查继续保留。
- 回归：四类非完赛状态不计分母、不补命中，显式 FT 可结算；缺状态及双字段冲突拒绝。

### F4：未来总体汇总不绑定计划回执，重复计划或身份别名可放大分母

- 原触发：future_status.run 未验证计划 receipt.sha256，也未拒绝重复计划。临时目录重复同一单场计划并填入错误 receipt 哈希，仍生成 population=2；跨计划重复 match_id 或同场不同ID/时区表示也被重复统计。
- 修复：先完整核验计划内容、回执哈希与manifest协议，再拒绝重复计划、跨计划match_id重叠、注册身份与eligible_ids不一致，以及同队列/阶段/真实开球时间/双方球队的重复比赛。全部计划通过预检后才开始逐队列复盘，不偷偷去重或删样本。
- 回归：错误回执、篡改记录、错误协议、重复计划、重复match_id、时区别名及身份总体缺失/重复均拒绝且不产生输出。同联赛不同批次的完整未捕获分母继续保留。

### F5：锁定复盘引擎外围缺少计划与实际冻结的完整身份绑定

- 原触发：future_validation.review 只把记录绑定到计划match_id/cohort/stage，没有核对计划fixtures_identity的主客队及开球时间。合成测试将计划home改为其他队并封装合法计划，仍接受为pending=1。
- 修复：按root追加范围在未锁定模块新增 `future_identity.validate_plan_packages(plan_record, packages)`，核验计划总体、包与计划哈希、两个回执及冻结内容，并将双方6项身份字段match_id/cohort/stage/kickoff_at/home/away绑定到注册总体。时区等价允许。future_status在调用锁定review前调用该helper，待完赛包也执行。该函数无模型、赛果或数值计算，不复制锁定引擎，不修改旧协议或冻结。
- 接口：packages内current_receipt/candidate_receipt路径须事先解析为可读取冻结文件；成功返回None，冲突抛出ValueError，缺必填字段抛KeyError。原引擎继续负责矩阵、工件、首版资格、时序和结算。
- 回归：每个角色6种身份字段冲突、同一kickoff时区等价、计划/包/回执/内容哈希冲突、顶层match_id、重复包与不完整总体；status集成测试确认拒绝发生在锁定review调用前。operations代理负责将同helper接入automation/prospective_cycle的两个fv.review调用点，本报告不代替其接入测试结论。

## 验证

修复前执行新增核心6项用例：6项均失败，合计20个失败子用例，确认问题可复现。另有独立 tempfile 脚本得到 `CONFLICTING_TEAMS_PUBLISHED OTHER`、`PARTIAL_LEDGER_REMAINS ... {"partial":`、`LIVE_RESULT_REVIEW 1`。

修复后必要回归命令：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=runtime:runtime/research /workspace/football-venv/bin/python -m unittest test_publication_recovery test_prospective test_analysis_freeze test_refactor_contracts.PublicationTests test_partial_prediction test_review_contracts.ReviewContracts.test_chinese_freeze_resume_and_append_under_cp1252_default
```

结果：42 tests，OK，耗时2.097秒，其中7项为新增用例。

追加未来总体修复前，4项核心安全用例出现8个失败子断言。追加修复与helper接入后执行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=runtime:runtime/research /workspace/football-venv/bin/python -m unittest research_program.test_future_status research_program.test_future_identity
```

结果：11 tests，OK，耗时0.012秒，其中10项为新增用例。两个必要回归批次共53项、17项新增。测试均为软件合成检查，不是未来真实赛前样本、历史模型效果实验或准确率提升证据。

## 遗留事项（未修改）

1. `future_validation.py` 直接CLI/API仍为原锁定实现；独立调用者必须先调用新helper或走future_status/已接入的automation外围。其源文件被协议 `source_files_sha256` 锁定，本轮没有绕过旧哈希。若要修改该入口本身，应发布新的协议/引擎版本。
2. 本次未对所有真实旧冻结、来源真伪与未来协议执行全库认证。90分钟来源核验及实盘五种结算代码已审阅；完整集成由 root 串行执行。旧锁定协议、活动矩阵和历史发布内容没有被本代理修改。
