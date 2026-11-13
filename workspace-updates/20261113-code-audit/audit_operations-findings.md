# 自动化与数据采集审计

审计日期：2026-11-13（北京时间）。执行代理：`audit_operations`。原3项采集修复后，按 root 追加授权接入共享计划身份校验，并修复2项训练输入证据缺口；最终定向回归共65项通过。全部使用合成数据或临时目录，不代表真实采集成功、历史效果改善或部署完成。

## 范围与边界

已阅读项目 AGENTS、TEAM、项目目标、无人值守说明，以及源码 `runtime/automation` 下 collector、trainer、prospective_cycle、result_queue、run、collection_status、export_seed、email_notify。数据仓库审查 `runtime/collect_kor1.py` 及其测试，修改已获 root 授权。market_snapshot / infer_market_snapshot / market_bridge 归其他代理，本组未修改。

修改源码 collector、prospective_cycle、trainer 输入核验及对应测试、数据仓库 collect_kor1 及其测试。Git仅按 root 追加授权读取固定 base 的 archive 到临时目录；未进行分支、提交或推送操作。未执行网络请求、邮件、真实采集/训练、数据库写入；未修改 workflow、执行 pin、定时状态、活动工件、注册表、模型参数或旧冻结。数据仓库既有自动采集提交由 root 保留，本组未改其状态数据。

## 已修复

### OPS-01：采集预算耗尽后，后排联赛与日期可持续饿死

- 位置：`/workspace/Football-Analysis/runtime/automation/collector.py:47`、`:212`、`:255`。
- 原行为：每轮按联赛字母序从最早日期重新开始；没有跨轮进度。预算持续偏小时，后面的赛事可能始终没被查询，滑出回看窗口后无法由该入口补回。
- 修复前证据：3联赛×2日期，每轮仅1次请求，连跑6轮只请求1个不同 URL（应为6）；首联赛超时的两轮也重复同一 URL。新增两项回归在修复前均失败。
- 修复：为每个明确的 `(competition, UTC date)` scoreboard URL 记录最后尝试序号；先未尝试、再最久未尝试。请求预算与时间预算通过后、传输前原子持久化；失败仍轮转，一次 HTTP 重试不额外改变公平顺序。摘要请求、100次上限、全局一次重试与25秒超时规则保持。
- 状态契约：数据目录根新增 `scoreboard-attempts.json`，含 `sequence` 和 `attempts`。状态只保留当前 scopes 和日期窗口中的 URL；每次实际请求前以临时文件、文件 fsync、原子替换和目录 fsync 写入。预算不足而没有请求时不建立状态文件。调用方仍负责已有的整轮串行化约束。
- 本地验证：不同轮预算1→2、次日窗口由2天缩到1天后，旧 URL 被裁掉，保留条目数为当前任务数；失败继续轮转；时间耗尽无请求无游标。响应缓存仍只在单轮内有效，没有跨轮 TTL 缓存。现有数据 workflow 使用 `git add -A`；本组未修改工作流。
- 限制：公平轮转不能证明每轮全覆盖，也不能在实际预算本身不足时保证每条赛果都能在回看期内取得；`coverage_complete=false` 保持。

### OPS-02：K League 1 去重丢弃赛程/身份/阶段更正

- 位置：`/workspace/kaka597000-Football-Analysis-Data/runtime/collect_kor1.py:203`。
- 原行为：签名仅包含 provider、match_id、status、goals、odds、statistics。已保存赛事的开赛时间、主客队身份、阶段、场地等更正会被识别为旧记录，静默丢失。
- 修复前证据：首次记录、仅更改 kickoff_at、仅更改 away_id 的新增数为 `[1,0,0]`。新增回归的7种字段更正（kickoff、home、away、stage、round、neutral、bookmaker）均失败。
- 修复：以完整行的业务字段去重，仅排除 `known_at` 和 `source_url`。语义更正追加为新观察，原观察保留；同事实的再次抓取或查询路径变化仍去重。不将候选数据放入训练库。
- 回归：7种更正都追加；只改变观察时间与查询 URL 不新增；原有完整 K League 1 合成采集测试保持通过。

### OPS-03：历史分页 completed 标记阻止跨年恢复

- 位置：`/workspace/kaka597000-Football-Analysis-Data/runtime/collect_kor1.py:338`。
- 原行为：2026年扫描到末页后保存 `{next_year:2027,page:1,completed:true}`。到2027年，`_history_url` 仍因 completed 无条件返回空，历史分页永久停止。
- 修复前证据：新增跨年回归在2027年3月仍得到 `url=None`，失败。
- 修复：`completed` 表示上一轮已追到当年的暂停状态；只有 `next_year > now.year` 时继续暂停。目标年份到达后恢复该年页码，并返回 `completed=false`；原游标对象不原地修改。
- 回归：同年暂停；次年恢复第1页，UTC年度起止时间正确。未改实际 history-cursor.json。

## 验证

1. 源码工作目录 `/workspace/Football-Analysis/runtime/automation`：
   `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/football-venv/bin/python -m unittest test_collector test_collection_status`
   最终18项通过，其中 collector 12项（新增3项），collection_status 6项。
2. 数据工作目录 `/workspace/kaka597000-Football-Analysis-Data`：
   `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/football-venv/bin/python -m unittest runtime.test_collect_kor1`
   14项通过，新增3项。该文件串行执行；既有固定测试目录由测试自行创建/清理，新回归使用唯一 TemporaryDirectory。
3. 修复前最小失败：源码2项测试均失败；数据3项新增测试包含8个失败子项、1项去重保留测试已通过。修复后全部通过。没有为此运行真实模型训练。

## 追加授权：共享前向计划身份校验

OPS-04：freeze_review 代理提供未锁定外围 helper `research_program.future_identity.validate_plan_packages`，本组在 `_recover_package` 和末端 `fv.review` 前接入。先 resolve 当前/候选回执，再把两份已验哈希冻结的 match_id、cohort、stage、home、away、kickoff 与预登记计划逐项绑定；锁定 future_validation.py 和协议不改。

新增两个自动化边界回归：内部一致但客队与登记不同的恢复包、开赛时间与登记不同的终端复盘包，在接入前均未抛错，在接入后拒绝进入 fv.review。既有测试的 forecast 回执由真实带 fixture 和内容哈希的合成记录构成，没有 mock 新 guard。`python -m unittest runtime.automation.test_prospective_cycle` 全20项通过。

部署需要新增 overlay 文件 future_identity.py。离线固定 base 加6项 overlay 已实际导入成功，8份协议锁定源码 SHA 前后保持。精确脚本、结果和 rollout 建议分别见 `audit_operations-overlay-smoke.py`、`audit_operations-overlay-validation.json`、`audit_operations-overlay-notes.md`。没有执行 hydrate 或真实捕获。

## 追加授权：训练输入证据缺口已修，部署待独立 rollout

`trainer._verify_raw_result`（`:122`附近）核验原始比分/身份，但未比对 `row.neutral` 与原文 `neutralSite`，也未要求 incremental 的 known_at 不早于 kickoff。临时目录里调用现有 RawEvidenceTests helper：原文 neutralSite=true 而 row.neutral=false，或者 known_at 早于开赛，均产生 accepted_rows=1、quarantined=0、`VERIFIED_RAW_REGULATION_90`。前者可把错误场地状态送入候选训练特征，后者是来源时间证据缺口；本次没有证明任何真实训练样本受影响，也不将其描述成已证明的历史前视泄漏。

后续只读核查确认 trainer 不在当前活动注册表或真实两bundle的源码锁中；自己的 code_fingerprint 是研究候选变更追踪/重拟合触发器。root 因此追加授权纯输入核验修复：OPS-05 仅在原文 neutralSite 与规范行 neutral 都是明确布尔且矛盾时隔离为 RAW_SOURCE_NEUTRAL_CONFLICT；OPS-06 仅对有原始证据的 incremental 行，known_at（或 first_known_at）早于已核验 kickoff 时隔离为 RAW_SOURCE_KNOWN_BEFORE_KICKOFF。任一方场地未知、无raw的legacy行、retrospective seed均保持旧语义。

新增4项回归覆盖上述拒绝条件及未知场地/legacy/seed兼容。修复前最小2项测试含3个失败子项；修复后 `python -m unittest test_trainer_raw_evidence` 全13项通过，只加载临时合成输入，没有调用 train。fit、数值参数、既有候选和活动工件不变。trainer 源码指纹随代码自然变化，未来授权训练可产生新候选，不回写旧候选，也不宣称效果提升。

训练任务继续执行固定 base 6639867，而 collector 使用独立 checkout；仅更新 collector pin 不会部署这两项 trainer 修复。本轮 base pin 保持，训练输入验证列为 PENDING_SEPARATE_ROLLOUT。此处没有评价模型命中率或宣称晋级。
