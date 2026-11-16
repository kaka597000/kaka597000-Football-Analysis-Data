# 11月16日欧国联复盘

[完整复盘](复盘报告_交付版.md) · [CSV展示](复盘展示.csv) · [Python指标](metrics.json) · [调整决定](review-decision.json) · [最新报告回执](report-delivery-receipt.json)

原8场已完赛，6场有效综合第一比分1/6、胜平负4/6；实际大小球4场为1全赢、1走盘、1半输、1全输。TOP3比分1/3、胜平负2/3。两场交付失败继续保留在覆盖分母。8场赛果经ESPN及赛前绑定The Odds provider_match_id交叉核对，32个进球事件完成身份/比分增量核验。

原候选首次与11月15日晚修订分列，两个等级本批比分均未中。累计34场首版研究候选按等级统计，不混成单一活动模型成绩。8场盘口可用，但数值候选没有赛前冻结大/小选向，因此模型OU命中率不补造；人工4场正常结算。没有改模型参数、注册表、旧冻结或发布环境。

08:33报告v1中把0-2误称为备选，08:34的v2已删除这一不准确描述。原实际推荐0-1、赛果0-2及全部指标/决定不变；两份报告和冻结链均保留，以交付版为准。

恢复：在本目录运行 `python verify_archive.py --stage /tmp/NEW-nations-review-restore`。核验新增归档、复用长期归档、文件字节与冻结链后，再按recovery-map.json恢复原路径和WCPP别名；源码另检出精确commit，依赖见inference-environment.json。复盘只读取原矩阵和预测，禁止将已结束比赛重新发布为赛前。

执行源码7a18cee715acb0633904af434b3f743d870c0951，PR #38仍开放、已有源码CI成功，main为1257fdde7b6746b7ba6d2aa919382214a2cfb589。本轮只有数据/报告提交，未新增源码PR；manifest中的data_parent_commit是本轮归档前的数据版本。
