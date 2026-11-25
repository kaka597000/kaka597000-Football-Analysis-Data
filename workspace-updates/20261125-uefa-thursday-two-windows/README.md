# 欧联杯、欧协联两轮窗口登记与首单证据

本目录保存 2026 年 11 月 26 日至 12 月 12 日的两个连续北京时间窗口，覆盖 UEFA Europa League / League Phase 与 UEFA Conference League / League Phase。每项赛事每窗 18 场，共 72 场。四个窗口逐场使用稳定 UEFA 赛事 ID，赛历、比赛日、开球及球队身份由 UEFA、ESPN、FotMob 原始响应相互核对。原始响应时刻、URL、SHA-256 和源内 ID 均保留在 `evidence/fixtures.jsonl` 与 `archives/uefa-thursday-20261125-5c03f3517796c580.tar.gz`。

## 冻结范围

登记要求每窗 18/18 首选比分、三选、WDL，三席均须选出且整批三席首选比分全中率为 100%；同一场真实博彩公司报价须具备报价时钟和总球线，覆盖率至少 80%；非走盘大小球全赢率至少 70%。这只是预先登记，不代表达标。没有结算，也没有综合预测、席位选择或模型晋级。注册表缺少这两项赛事的原生 Current/Test 配对事实，因此本包不声称已运行该阶段。

现存研究首单只作原始发行记录对照：第一轮 36 场各有 R7 和 R13 已发行首单；第二轮两条轨迹均没有已发行首单，全部留空。原先的预测、冻结 ID、发行时间、记录哈希、模型或配方哈希以及 R13 实际剂量均按原件保存。后续市场观察没有合并进这些首单，也没有重评首选或成绩。

## 盘口时钟口径

ESPN 首轮摘要原始快照显示 DraftKings 同店 1X2 和双边 OU/线 35/36 场，机构自己的报价时钟为 0/36；这项原始结果保持不变。

另一个首轮采集来自 InferSports。`odds[i].as_of` 是 InferSports 文档定义的“应用于该机构×市场线的最近上游更新时间”，而非经博彩公司直接签发认证的时刻。逐场原始响应和 HTTP/采集 sidecar 已另行打包到 `archives/first-round-upstream-market-raw.tar.gz`。可复核出 36/36 场至少存在同店 1X2 与 totals 报价，且两条市场时钟均在各自真实响应收齐时刻前一小时内；其中 20 场有至少一对同刻盘口，共 35 对。`evidence/upstream-market-matched-pairs.csv` 保存这 35 对及其原行号、原行 SHA 和逐市场时钟，`evidence/upstream-market-fixture-coverage.json` 保存 36 场的响应 SHA 与采集时刻。

用户报告 Euclid 独立得出上述 36/36、20 场、35 对统计。本工作区未发现单独由 Euclid 产生的原始响应或执行回执；故 verifier 直接对包内 InferSports 上游原件独立复算这些相同计数，并明确保留该来源与执行来源区别。不得把这些上游时钟记作直接博彩公司时钟，也不得用它们替代原 ESPN/DraftKings 首次快照或 R7/R13 首单。

## 复核

从仓库根目录或本目录运行：

```sh
python3 -B workspace-updates/20261125-uefa-thursday-two-windows/verify.py
```

验证器只用 Python 标准库，检查登记窗口、72 个官方 fixture crosswalk、来源 response 时刻和 SHA、R7/R13 原首单引用、未选择席位及未结算状态。它从原始盘口行逐条复核 491 个同店市场组合，再计算 36 场报价双钟均在一小时内、20 场含相同上游时钟、35 对同刻盘口。文件 SHA 清单为本目录 `manifest.json`。
