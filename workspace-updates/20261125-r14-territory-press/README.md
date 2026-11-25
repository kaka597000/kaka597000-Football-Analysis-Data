# R14 五联赛 xG、区域进攻与压迫研究复算

英超、西甲、德甲、意甲和法甲各自拟合主客共用的进球概率与正比分分布。每个联赛都保留六列全模型和前两列 xG 模型，以及各自按验证期选出的比分、胜平负和大小球剂量。历史主面板、原面板近期窗口和十一月扩展分别结算。独立旧窗口的启用状态来自回放的 `inputs.json`。每个窗口的逐场记录、训练权重、验证试验和前向权重保存在回放包中。[登记协议](protocol.json) · [回放原件](replay/forecasts.tar.gz)

## 数据来源

| 输入 | 在数据仓库中的位置 | 用途 |
| --- | --- | --- |
| R5 | `workspace-updates/20261123-all-scope-kpi` | 五联赛的 `models/<code>.tar.gz` 提供原始面板，前向首次赔率来自 `forward-first-issues.tar.gz` |
| R7 | `workspace-updates/20261123-prematch-literature` | 同名逐联赛包内的 `main/fit.json` 和 `main/forward.json` 提供原日历、控制及前向配方，已发行对照来自 `first-issues.tar.gz` |
| R10 | `workspace-updates/20261125-r10-shot-conversion` | `replay/main.tar.gz` 提供逐场原对照，前向来源为 `forward/first-issues.tar.gz`。启用独立面板时另读 `inputs/independent.tar.gz` 和 `replay/independent.tar.gz` |
| R11 | 本包 `inputs/r11/` | 数据 PR #48 的原始 manifest 和 extension 包，保存 CSV 原始响应、物理行号、非收盘 Bet365 价格和常规时间比分 |
| Understat | 本包 `inputs/understat.tar.gz` | 五联赛直接归档的原始 getLeagueData 响应、采集记录、离线提取器、事件表和覆盖诊断 |

Understat 的原始比赛日期时间字符串没有时区。特征按来源日历日截断，同日比赛整体排除。抓取时钟单独保留。直接原始归档覆盖 2020/21 至 2026/27，五联赛最近快照采于 2026 年 10 月 15 日。各字段的覆盖及缺项以包内 `reports/coverage.json` 为准。

R11 原始 manifest 的 SHA-256 为 `d76cdbc338407c9962122f70aa69a071c0df51203fc2cb6e74d9a722054543bb`，extension 的 SHA-256 为 `d5d39eb5ad1cab389ad2bcf9414e6168c23a7d1a682ca037000b0f46ea2889cc`。包内嵌入这两份原件，使复算可独立于 PR #48 的合并历史执行。[原始 manifest](inputs/r11/manifest.json) · [原始 extension](inputs/r11/extension.tar.gz)

## 指标与权重

四项指标按逐场可结算条件各自计分。大小球以原实际盘线拆分四分之一盘口，全赢计中，走盘退出分母，五类结算各自保留。配对表给出同场命中、分母、分歧数和净变化。日期整组区间来自已登记的抽样程序，在完整重训时复算。特征诊断包含实际使用的历史日期、球队匹配方式、来源比赛核对状态及进攻和压迫信号覆盖。[四项计数](replay/competition-metrics.csv) · [配对结果](replay/comparisons.csv) · [覆盖与改判](replay/diagnostics.csv) · [各阶段两组系数](replay/weights.csv) · [完整指标](replay/metrics.json)

## 从数据仓库验证

使用 Python 3.12、源码提交的 `requirements.txt` 和 LightGBM 4.6.0。将清单中 `source_commit` 对应的源码检出到 `source`。在数据仓库根目录运行以下命令。

```bash
python -B workspace-updates/20261125-r14-territory-press/verify.py --source source --data-root .
```

核验器在临时目录中从原始响应重建 Understat 事件、来源清单和覆盖报告，逐字节核对，并将 R11 目标连接到归档 CSV 的物理行。它从逐场预测独立重算四项计数、五类大小球结算、配对计数及特征诊断，并核对已发布的权重表。随后使用重建的事件、五联赛 R5/R7/R10 基准及内嵌 R11 扩展连续运行两次 `research_program.territory_study`。同环境两次输出的文件集合及所有字节必须一致。与归档跨环境比较时，选择、计数、覆盖、身份和策略逐项精确匹配，浮点量允许相对误差 `1e-7`、绝对误差 `1e-9`。每次训练的前向文件须引用自身训练文件的实际 SHA。追加 `--quick` 仅执行原始数据与归档核验。

含前向首冻的包在 manifest 中记录 `forward_included=true`。核验器校对 R5、R7 和 R10 原始首冻、签发先后、比赛身份、原始价格、模型绑定和有序比分；每联赛按首选概率、开球时刻、比赛 ID 重排最多三个席位。原件位置为 `forward/first-issues.tar.gz`、`forward/ranked.tar.gz`，汇总为 `forward/first-issues.csv`。

## 从共享 scratch 生成数据 PR

在 `R14_SOURCE_SHA` 中设置整合完成的源码提交。下面的命令先用独立目录构建和核验，再把数据包和工作流写入指定工作树。相同输入的重复运行复用字节一致的文件。

```bash
/workspace/football-venv/bin/python -B /workspace/scratch/r14-evidence-tools/package.py \
  --replay /workspace/scratch/r14-final --source-commit "$R14_SOURCE_SHA" \
  --stage-root /workspace/scratch/r14-data
git -C /workspace/scratch/r14-data add -- workspace-updates/20261125-r14-territory-press .github/workflows/r14-territory-press.yml
```

打包器默认读取 `r14-understat-complete`、`r14-forward`、`r14-ranked` 和 `r11-data/workspace-updates/20261125-r11-asian-handicap`。可用 `--verify-training` 在写入前完成两次重训。本地源码整合期间可将 `--stage-root` 指向临时目录，用 `--working-source` 保留精确文件散列，源码提交栏为空。前向产物待生成时，显式传入 `--replay-only` 可生成标明历史范围的预览。数据 PR 工作流按 manifest 的完整源码提交复算。
