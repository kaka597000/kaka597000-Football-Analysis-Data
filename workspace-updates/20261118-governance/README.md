# 模块治理、接口收敛与冻结验证

本次整理保留全部原始数据、训练工件、冻结与源码锁定点。源码仓新增机器可读模块/路由清单、有限候选检查和公开复盘 API；数据仓把复盘轮询中的跨仓私有调用集中到 `runtime/source_review_api.py` 兼容层。现有固定版本没有公开 API 时仍执行相同旧函数；后续迁移源码 pin 后使用 v1。工作流未迁移、未部署。

## 实际验证

[验证清单](validation.json) 记录完整基线提交与证据哈希。严格集成 25 组、1,039 测试通过、0 跳过；另有公开接口恒等检查 1 项。数据轮询在公开接口和原 `3fd411a…` 版本各通过 4 项测试，覆盖 90 分钟结果认证、原始响应、失败轮换和幂等性。

原三臂、sequence、Transformer 的 18、18、24 份矩阵及选择全部重放一致。校验包括原来源/工件哈希、六场首次冻结及赛前市场。重放没有发布新预测或覆盖旧冻结。三组各六场仍按各自原登记复盘；LSTM 和 Transformer 未中止。

`config/source-contract.json` 记录无人值守工作流的五组版本及 32 份受保护文件哈希，包含三组登记、首冻、工件、国内联赛/欧冠协议和 overlay 安装器。源码 `module_governance.py --data` 检查这些身份。原定时流程的最新已观察运行 [44250121199](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/actions/runs/44250121199) 成功；这不是本次代码的部署回执。

## 收敛依据

[consolidation.json](consolidation.json) 可由源码 `research_program.consolidation_audit` 离线重建。481 场历史记录重算如下：

| 既有模型 | 第一比分 | 相对盘口基线改对/改错 | WDL Brier | 比分 log loss |
|---|---:|---:|---:|---:|
| 盘口基线 | 57/481 | 0/0 | 0.556816 | 2.999347 |
| LightGBM | 59/481 | 3/1 | 0.555550 | 2.996238 |
| LSTM | 57/481 | 1/1 | 0.555673 | 2.995613 |
| Transformer | 58/481 | 1/0 | 0.555721 | 2.996553 |

第一比分和 WDL Brier 从逐场预测及真实比分重新计算；log loss 为原逐场值的平均，另由 Transformer 原验证器完成数值重放。这批样本已经用于研究比较，且历史收盘价缺原始逐笔时刻，不能当作未来验收。LightGBM 只列为优先整合组件；没有声称新候选改善。联赛校准默认关闭，作为下一轮可选组件而非新增长期对照。

三组巴甲首冻截止分别是北京时间 11 月 18 日 11:12、12:08、13:11。盘口和输入不同，不跨组池化成绩。下一阶段复用既有 Current → 盘口 → LightGBM 组件，每赛事阶段最多一项整合候选；先完成原冻结验证，再决定是否需要新配方。

## 复现与回滚

```sh
ANALYSIS=/path/to/Football-Analysis
python "$ANALYSIS/runtime/module_governance.py" --data .
PYTHONPATH="$ANALYSIS/runtime" python -m unittest discover -s runtime -p test_poll_three_arm_results.py -v
PYTHONPATH="$ANALYSIS/runtime" python -m research_program.consolidation_audit --data . > /tmp/consolidation.json
diff -u workspace-updates/20261118-governance/consolidation.json /tmp/consolidation.json
```

使用原三组 `verify.py --source "$ANALYSIS"` 可重放全部冻结。没有删除数据或改活动工件；revert 对应整理提交即可回滚。保留 legacy 兼容层和 overlay，直到分别完成运行 pin 迁移及冻结协议兼容验证。本次不合并、不部署、不自动晋级。
