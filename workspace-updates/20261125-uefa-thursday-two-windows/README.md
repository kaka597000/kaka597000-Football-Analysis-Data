# 欧联杯、欧协联两轮窗口登记与首单证据

本目录保存 2026 年 11 月 26 日至 12 月 12 日的两个连续北京时间窗口，覆盖 UEFA Europa League / League Phase 与 UEFA Conference League / League Phase。每项赛事每窗 18 场，共 72 场。四个窗口逐场使用稳定 UEFA 赛事 ID，赛历、比赛日、开球及球队身份由 UEFA、ESPN、FotMob 原始响应相互核对。原始响应时刻、URL、SHA-256 和源内 ID 均保留在 `evidence/fixtures.jsonl` 与 `archives/uefa-thursday-20261125-5c03f3517796c580.tar.gz`。

## 冻结范围

登记要求每窗 18/18 首选比分、三选、WDL，三席均须选出且整批三席首选比分全中率为 100%；同一场真实市场专属报价时钟和总球线至少 15/18（80%）；实际结算后须至少有 13/18 场可核的非走盘总球（70%覆盖），并要求该非走盘样本中的总球全赢率至少 70%。市场专属上游时钟与直接博彩公司签发时钟分列。这只是预先登记，不代表达标。没有结算，也没有综合预测、席位选择或模型晋级。注册表缺少这两项赛事的原生 Current/Test 配对事实，因此本包不声称已运行该阶段。

每个窗口目标覆盖 18/18 唯一首选比分、三选、WDL，并选出三席且要求整批三席首选比分 sweep 达到 18/18。现存研究首单只作原始发行记录对照：第一轮 36 场各有 R7 和 R13 已发行首单；第二轮两条轨迹均没有已发行首单，全部留空。逐场 R7/R13 原始记录 member、SHA、发行时间和模型/配方标识见 [研究首单引用索引](evidence/research-reference-index.csv)，记录本体及原注册回执在研究归档中。原先的预测、冻结 ID、发行时间、记录哈希、模型或配方哈希以及 R13 实际剂量均按原件保存。后续市场观察没有合并进这些首单，也没有重评首选或成绩。

## 盘口时钟口径

ESPN 首轮摘要原始快照显示 DraftKings 同店 1X2 和双边 OU/线 35/36 场，机构自己的报价时钟为 0/36；这项原始结果保持不变。

另一个首轮采集来自 InferSports。`odds[i].as_of` 是 InferSports 文档定义的“应用于该机构×市场线的最近上游更新时间”，而非经博彩公司直接签发认证的时刻。逐场原始响应和 HTTP/采集 sidecar 已另行打包到 `archives/first-round-upstream-market-raw.tar.gz`。可复核出 36/36 场至少存在同店 1X2 与 totals 报价，且两条市场时钟均在各自真实响应收齐时刻前一小时内；其中 20 场有至少一对同刻盘口，共 35 对。`evidence/upstream-market-matched-pairs.csv` 保存这 35 对及其原行号、原行 SHA 和逐市场时钟，`evidence/upstream-market-fixture-coverage.json` 保存 36 场的响应 SHA 与采集时刻。第一轮欧联、欧协联分别为 18/18；第二轮目前为 0/18，报价目标尚未满足。目标按各赛事、各窗口分别核验。

这 36 份原始响应由 Euclid（本任务的 Codex 驱动子代理）在一次上游采集中取得；验证器对同一批归档响应和采集 sidecar 独立复算，不代表第二次采集。逐项时钟属于 InferSports 文档定义的上游市场更新时间，不能记成博彩公司直接签发时间，也不能替代 ESPN/DraftKings 首次快照或 R7/R13 首单。

## 复核

从仓库根目录或本目录运行：

```sh
python3 -B workspace-updates/20261125-uefa-thursday-two-windows/verify.py
```

验证器只用 Python 标准库，检查登记窗口、72 个官方 fixture crosswalk、来源 response 时刻和 SHA、R7/R13 原首单引用、未选择席位及未结算状态。它从原始盘口行逐条复核 491 个同店市场组合，再计算 36 场报价双钟均在一小时内、20 场含相同上游时钟、35 对同刻盘口。文件 SHA 清单为本目录 `manifest.json`。

## 注册封存与研究引用

四窗口的 72 个稳定赛程 ID、指标门槛、逐窗当前观测状态及原 R7/R13 首单引用已由 canonical `research-uefa-thursday-two-windows-20261125-registration` 登记。实际注册时间为 2026-11-25 13:57:39 UTC；freeze ID `3908ff15e2181192-v000001`，canonical record SHA-256 `ab5753d3c6484449182fe8d4cc23e71955b7d53f03faa9c786445efd1cc0e397`。登记原件、freeze 根目录路径与现场回读校验见 [canonical registration seal](evidence/canonical-registration-seal.json) 和 [sealed record](evidence/canonical-registration-record.json)。封存后新增一份独立补充：完整团队采集归档和其中原字节的 180 行 `prior-first-prematch-records.csv`。逐条解析得 R7、R8、R9、R10、R13 各 36 条；源文件 SHA-256 为 `fa69b8ad3245de83f3cad8c3c01e5262d950f391b43f2f933ad867572151e265`，归档 SHA-256 为 `ab32734d0e5d8025338bc0a26cc261ba715ea5cff31d2d4dc29c594efa96bd92`。`evidence/prior-first-prematch-reference-index.csv` 把 180 行各自解析到归档内的原始发行文件，并核对字节 SHA、记录 SHA、freeze ID、发行时间、registration SHA 和首选。补充团队包记录赛程 36 场、球队 72 支、既往 FT 70/72、xG 47、SOT 62；其来源清单生成时间为 2026-11-25 13:35:15.333913 UTC，逐项请求/响应时刻保存在原 sidecar。它是在 canonical R7/R13-only registration seal 之后单独附加的材料，不属于或改变已封存的登记身份；正式首单比较仍由逐场 R7/R13 原件与原评分表承担。
