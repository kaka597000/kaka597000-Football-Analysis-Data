# 欧国联xG研究与未来真实冻结

2026年11月17日，按用户要求直接执行独立实验。源码[PR #40](https://github.com/kaka597000/Football-Analysis/pull/40)，执行代码 `7dc5d0f9a64185dd16e44e45b59385990d12f331`。

[研究报告](xG研究执行报告.md)与[全部13方案指标](metrics.csv)。758场真实历史、29场BSD xG，52工件、1,248条历史滚动预测；10月选方案，11月44场诊断比分5→6、胜平负30→31，10场真实盘口大小球无改善。结果属于已知历史统计研究，未证明未来准确率提升。

下一批8场×13方案已于10:25实际赛前冻结，真实总球线覆盖8/8，全部待结算，开球为北京时间11月18日03:45。计划 `0d33811468c62416-v000001`。原18场计划单独保留。

`nations-xg-evidence.tar.gz` SHA256 `1f5722db6e66467f3979c612817fa867fb0f9946e1fe36864c9f86566772d591`，8,840,011字节，226个文件。包含原文、输入、协议、工件、预测、完整新冻结及执行源码。`manifest.json`逐文件哈希与原路径可核查。旧758场赛果的原始ESPN证据复用manifest列出的既有长期归档，不依赖Actions临时artifact。

先在空目录验证和解包：

```bash
python workspace-updates/20261117-nations-xg-research/verify_archive.py --out /tmp/nations-xg-restore
```

数值离线重跑（检出源码 `7dc5d0f9a64185dd16e44e45b59385990d12f331` 并安装其Python依赖）：

```bash
PYTHONPATH=runtime python workspace-updates/20261117-nations-xg-research/verify_archive.py --out /tmp/nations-xg-replay --replay
```

恢复至WCPP时将 `research/nations-xg-20261117` 放到 `/workspace/WCPP/research/`，新增冻结按manifest恢复到 `/workspace/WCPP/forecasts/issued-analyses/`。已有相同哈希可复用；已有不同内容保留另查，不覆盖旧记录。`runtime-AGENTS.md`保存本次研究偏好，恢复时合并这条偏好，保留新环境已有更新。

`xg_research.review_forward(恢复后的forward目录, 已核验赛果列表)`可按首版冻结结算，未完赛保持pending。已有旧18场定时流程不自动纳入本8场新实验；本轮已执行训练与冻结，未另建定时任务。

代码审查后修正了盘口附加时的中立场上下文与计算依赖身份；`review-fix-evidence.tar.gz`另存修复后的52工件和1,248条逐场结果，107文件，SHA256 `8b593ca79ac40052f33526f52a97b3c1e22279f0ea2066019c6560a382d44daf`。重算与首轮指标和逐场预测完全一致；原8场104份冻结继续绑定原执行源码，未重发或改写。验证修复包可追加 `--manifest review-fix-manifest.json --out /tmp/nations-xg-review-fix`。

时间口径：历史10月/11月诊断实际能用的是较早9月的19条xG；11月16日新增10条只进入随后拟合和未来8场预测，没有进入该10场自身的预测。未来8场按等级为A两场、B六场，C/D暂没有本批未来样本。

后续源码同步保留了并行合入main的芬超移除配置（不影响欧国联），并修复Windows并发冻结的锁文件初始化竞争。最终源码与CI身份见 `delivery.json`；首版预测仍按其原始执行代码及工件评价。

最终补充核验：赛前历史大小球排除开赛后捕获的盘口，保留比赛的比分/胜平负与原报价审计；本批10场盘口全部合格，1,248条数值重算仍完全相同。最终严格集成执行25组、973次、零失败/零跳过，见 `test-summary-release.json`。

源码PR #40与数据PR #14已合并。最新源码main为 `29c9701821367034b46fb6d86683e57e31f02262`；原10:25首版使用 `7dc5d0f9a64185dd16e44e45b59385990d12f331`，两者身份单列。最新修复头 `2970cc808bacad85e1f1a3c51fade7318b2ecf57` 的push/PR CI均通过，数据主分支归档CI通过，实际回执见 `source-pr-ci.json`、`source-push-ci.json`、`data-main-ci.json`。
