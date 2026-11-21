# 全赛事共享采集与实际展示比分结算：隔离交付

## 停止与范围纠正

用户将范围从单巴甲纠正为项目全部正式赛事后，已停止单巴甲执行。纠正前仅读取Actions、代码和数据，fetch并建立隔离worktree/分支；没有触发采集、GitHub workflow、赛果写入、提交或推送。此后仅实施本报告的共享模块与隔离测试。没有广域真实请求、付费请求、训练、推理发布、部署、权限变更、日常优化恢复、旧PR合并或RSI改动。

源码从main d5645f13de63658af79289bfd118d530e2b4f0f2隔离开发；数据从main a5ecf0d0f1148a7acdb5675d45c347c0d5fb9d12核查，原normalized-results.jsonl git blob为8c133ebaf7aa0c4b89675c13b6871954f3a397c1。它在本轮没有变化。

## 覆盖不能混用分母

权威analysis-scope为20项（芬超已排除）；持久collection scopes为17项。正式范围内15项有活动注册表路由登记，欧联、欧协、世界杯、欧国联、日联杯缺活动路由。17个持久scope缺巴甲、欧国联、日联杯；巴甲在现有workflow运行时临时加入，然后恢复训练范围，不能说长期训练scope含巴甲。墨超、葡超、沙特、英冠四条保留路由位于当前正式范围之外，不删除也不混入正式分母。

逐赛事、阶段限制及根normalized-results观察数见[coverage-table.md](coverage-table.md)；机器清单和输入指纹见coverage.json。表内0条只表示根normalized-results文件没有观察，不能推断独立研究/专用目录没有数据。可公开查询、已有路由、采集scope、已存观察、当前批次推荐五个口径独立；本轮没有发布赛事批次，推荐分母为null，不把20项范围当成20场推荐。

具体缺口：

- 韩K1被主workflow从ESPN请求移除，用独立collect_kor1路径；不能把ESPN覆盖称为韩K1可用。
- 欧冠持久scope阶段是NEW_FORMAT:league_phase，而通用collector识别league_phase；需用保留原响应和原路由做阶段契约修复测试，不能简单删前缀混合时代。本轮只报告，未改正式采集配置。
- 欧国联与日联杯缺持久scope，通用ESPN标准化也缺对应阶段适配；应先分别建立分级/杯赛90分钟契约和拒绝混期测试，再考虑正式接入，不因独立研究能查到数据就宣称共享链已通。
- 欧联/欧协/世界杯已有采集scope不代表有活动预测路由。未来实际推荐缺路由时仍应保留弃权记录，不从别联赛借模型。

## 共享修复（未部署）

1. 正常automation.run collect新增显式 `--results-only`，collector新增include_market开关。仅此选择时不发任何盘口快照请求；默认保持兼容，不能与train并用。仍遵循当前scope白名单，不扩大范围或权限。
2. `research.display_review.attach_display`把**实际将显示的第一比分、两个去重备选及同版显示文本**放入已有payload的displayed_scores字段，返回同一实际文本。它不负责选比分，路径依据仍由原分析保留。现有冻结入口可保存该payload；当前生产入口尚未接入，不声称已改变线上展示。
3. 共用certify_retained从保留的ESPN summary或football-data.org v4 match原始字节提取90分钟结果，核验原SHA、实际捕获时间、主客ID、比赛ID、赛事/阶段与原开球。未支持来源拒绝，不能把调用方手填比分当认证结果。
4. settle只接受原轨道、第一版、真实赛前保存的记录，严格比对原provider赛事/阶段。无新display契约的旧记录标MISSING；不借primary、compared_scores、矩阵前三或其他轨。Top1和展示Top3分别统计已发布覆盖、已结算分母、命中率、缺失、弃权与待结算。首选命中必然计入完整展示Top3；只命中备选不算Top1。旧三元组不完整时可保留可证Top1，而Top3分母不增加。
5. 核心需求文档补充：每场三个比分与每批精选三场并存；矩阵Top3统计继续单列。原文不能否定用户新要求，也不反向修改历史。

## 隔离验收与可复现入口

测试覆盖巴甲/MLS的ESPN格式，以及英超football-data.org格式：至少三赛事、两来源共用同一结算器。共用端到端测试真实执行本地collector函数→标准化JSONL→保留原响应认证→已首冻显示结算→幂等重跑，网络返回全部为显式合成响应，临时目录销毁。**这不是对三赛事真实在线可用性的验收，也没有新的真实赛果落库。**

测试还覆盖首选兼Top3命中、仅备选命中、空/不完整/重复字段、拒绝赛后补填、跨轨/跨版本/赛事阶段隔离、篡改、非90分钟、缺失分母与禁止results-only训练。精确命令、最终代码commit、运行时间、测试数和保护哈希见validation.json；首次验证的日志另保留initial-check，不冒称最终代码验证。

```sh
cd /workspace/shared-results-source
/workspace/football-venv/bin/python -m unittest discover -s runtime/research -p test_display_review.py -v
/workspace/football-venv/bin/python scripts/run_tests.py --layer integration
```

将来经单独部署决定后，正常入口支持如下仅赛果模式；**本轮未执行该真实采集命令**：

```sh
python -m runtime.automation.run collect --state-dir /absolute/authorized-state --results-only
```

共享发布接入示意（只演示字段契约，不代表产生推荐）：

```python
from research.display_review import attach_display
payload, actual_text = attach_display(original_payload, selected_first, selected_two_alternatives)
# 原调用方须显示actual_text，并在发布前通过既有save冻结同一个payload。
# 未完成路径证据时使用abstain=True；旧已冻payload不得补写。
```

## 历史巴甲仅作回归资料

尚未找到与用户截图完全匹配、可证同版赛前实际展示三元组的机器发布物。已检查的comprehensive-decisions明确是独立研究且没有实际显示三元组；competing_scores只用于思考。模型矩阵不是展示证据。

用户提供的截图人工口径为Top1 0/6、展示Top3 4/6；这里仅注明用户提供的人工复算，未独立认证截图原件。独立研究综合3/4属于另一轨，不合并。旧六场的自动实际展示证据目前0/6可证，不能把缺失记作0/6命中；本轮没有采集其新赛果或生成结算记录。

## 定时执行观察及后续

observed-actions.json保存平台可见的常规workflow运行记录：最近一次为44391584574，2026-11-18 20:29:37 UTC，仍在该批赛前。44444802998首发窗口所有采集步骤跳过；44473265901是关闭窗口任务，不能冒充常规collect回执。workflow仍active，但缺少后续run记录的具体平台原因无法仅凭这些事实判定；不把“看不到运行”改称“采集代码已修复”。本轮没有任何手动dispatch。

下一步应独立评审共享模块接入、对应来源适配与缺失阶段路由，再决定部署；定时真实成功必须等待实际schedule回执、真实原响应及规范化持久化提交。旧两个草稿PR、本轮之前RSI十场原冻结及正式模型均保持原状。回滚只需放弃本隔离分支，无线上状态需回滚。

最终本地验证：源码 `5f1cf31b5e72177d79f433d1457f9e604e06ae2d` 完整严格资产集成1,070项通过、零跳过；8项针对测试另跑通过（已包含在完整套件，不重复累计）。静态扫描通过。95份旧资产及RSI文件哈希不变。源仓草稿PR：https://github.com/kaka597000/Football-Analysis/pull/51 。最终源提交基于main，与旧治理草稿的测试总数不直接比较；未包含旧草稿未合并模块。
