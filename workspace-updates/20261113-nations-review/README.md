# 欧国联8场冻结复盘｜2026年11月13日

[完整报告](review.md) · [Python统计结果](metrics.json) · [复盘冻结回执](delivery.json) · [独立核查](independent-verification.json) · [归档哈希清单](manifest.json)

综合首次／最新第一比分均4/7，胜平负7/7，各覆盖7/8。首版大小球1全赢、2半赢、1半输；最新2半赢。旧、新研究TOP3均比分1/3、胜平负3/3。活动欧国联Current/Test仍全部ABSTAIN，独立A/C候选分版核算，未晋级。

报告于北京时间2026年11月13日08:56:56追加冻结，ID `44fe9c25933523c8-v000001`，另含8条逐场review冻结。原66条赛前记录及38个活动工件校验不变。

本目录只追加证据和复盘。源码仍为 `ddfbc43197df8944072c70135e2a2831ae1a3ef5`；未重训、未切换活动模型、未更新训练库、未发布环境。回滚展示时改为引用上一份报告即可，保留本次及历史冻结，不删除记录。

## 长期恢复与复算

归档存放于Git数据仓库，未依赖临时Actions链接。先按`manifest.json`核验SHA256，再在空的恢复目录解包：

1. 复用[既有赛前证据归档](../20261113-nations-reanalysis/manifest.json)，其中已实际核验包含本轮所需的全部66条原始冻结；不重复上传旧矩阵与整套模型。
2. 解包本目录的`nations-review-evidence.tar.gz`，包含本轮原始赛果响应、采集元数据、冻结账户清单、计算脚本、独立核验、报告、9条review记录和原活动注册表快照。逐成员哈希在`manifest.json`，全部重新读取校验通过。
3. 将恢复的`WCPP`内容放到`/workspace/WCPP`；旧证据引用还使用`/workspace/recovered-workspace-20261102/WCPP`别名，按[原恢复说明](../../WORKSPACE-RECOVERY.md)保留兼容路径。若目标已有文件，先比较哈希，禁止覆盖不同内容的历史冻结。原候选工件可继续复用[11月10日模型归档](../20261110-nations-model/manifest.json)，无需重训。
4. 在独立源码检出中使用上述源码commit及项目Python依赖；把源码放在`/workspace/Football-Analysis`。仅复算不需要联网或API密钥，不调用`freeze_review.py`，也不重跑赛前预测。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
PYTHONPATH=/workspace/Football-Analysis/runtime:/workspace/Football-Analysis/runtime/optimization:/workspace/Football-Analysis/runtime/v5 \
/workspace/football-venv/bin/python \
/workspace/WCPP/reports/nations-review-20261113-0842/calculate_review.py
```

在副本目录运行可避免覆盖已经交付的派生文件。已在隔离副本实际重算，除`calculated_at`运行时间外，所有统计结果完全一致。首次冻结、候选及综合推荐均从原冻结读入，未重新预测。独立审查339项通过，既有结算测试10项通过；这里没有源码修改，也没有把本地检查称为新的远端CI运行。

## 来源限制

ESPN九次请求提供8场FT、两半场分数、进球／牌／点球事件；The Odds API单次scores请求独立核对8场比分一致。第二来源本身不标记90分钟，90分钟口径据已核实联赛阶段及ESPN两半场确认。赛后xG缺失，射门不是xG。

黑山比赛的比分供应商时间比原盘口晚1分钟，但provider event ID一致；差异保留。ESPN部分晋级附注的时间晚于采集时刻，该字段排除使用。原活动ABSTAIN外层发布截止与模型输入截止相差约1–2秒，复盘保留原始输入及外层时间，不改写旧冻结。
