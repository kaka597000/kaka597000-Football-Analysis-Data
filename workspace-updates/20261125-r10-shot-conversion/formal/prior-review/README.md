# R10 正式四指标前向分母核查（R9结果严格连接后更新）

核查截止：北京时间2026年11月25日14:30。只读本地赛事冻结、R9结果和原始证据；未联网、未改项目仓库。窗口为北京时间11月24日00:00至12月1日00:00，20个赛事队列。R9/R7在本报告中只提供90分钟赛果证据，研究预测绝不当作正式Primary或Current/Test预测。

## 结论

**完整正式综合 Primary 四指标分母仍未建立。** 但此前发现的7场登记后 Current/Test 首版，现已与 R9 `R7/results.json` 逐场严格连接并用原始 ESPN 响应校验：裸 ESPN ID、`espn:<ID>`、`afc.champions:<ID>`命名形式、原始主客ID、球队名、UTC开球、赛事、90分钟终场、原始响应SHA256均逐项核实，7/7通过。R9压缩包 `review/evidence.tar.gz` 内对应7个原始响应SHA256也逐一与结果清单和本地 `R7/evidence/`一致。

据 `runtime/v5/paired_review.py` 对 Current/Test 内部模型轨分轨结算：当前模型首选1/7、三选3/7、胜平负5/7；test模型首选2/7、三选3/7、胜平负5/7。大小球两轨均为0个可结算分母，原因是7场都没有正式冻结的大/小方向，也没有符合入口校验的真实盘口报价对象。以上数字只是既有 Current/Test 研究版首冻的模型轨复盘，**不是综合 Primary 业绩、不是本期20赛事的全量得分，也不是模型晋级证据**。

综合首版记录检查结果进一步明确：`analysis_freeze.py`规定的正式台账根目录为 `/workspace/WCPP/forecasts/issued-analyses`。按这7个确切事件ID扫描个人记录，只有7份 `track=current-test-pair` 首版，没有任何一条 `comprehensive`/综合 Primary 首版；唯一包含这些ID的批次级注册记录属于 `research-r8-conditional-score-20261125-registration`。所以综合轨是**没有对应首版回执**，不是“正式综合回执存在但只漏了展示字段”。

另有已交付的 `/workspace/WCPP/reports/afc-repository-model-20261124/README.md` 双模型报告，发布回执7/7为 `DELIVERED`，且报告本身标注两套输出为研究结果。报告展示的 Current/Test 首选比分与冻结内部首选7/7一致，没有展示差异；但它不是综合Primary台账。展示完整性为：有序三比分0/7、Current胜平负概率0/7、Test胜平负概率7/7、真实线及小球概率6/7、明确大/小选择方向0/7。Displayed与internal的对照单独保存，未把Test概率向量的最大项冒充冻结方向。

## 七场逐场结果与缺项

见 [逐场严格结果与内部模型计分](r9-strict-7-match-settlements.csv)。每行保留冻结内部首选/有序三比分/WDL、实际90分钟结果、各自命中字段、raw证据路径与SHA256、结果清单SHA256及完整身份检查JSON。空间不做跨队名模糊匹配；连接键来自赛事ID，并由主客ID、名称和开球时间复核。详细三个ID命名空间和结果证据见 [结果连接清单](verified-result-join.csv) 与 [严格身份校验](r9-strict-identity-checks.json)。

| 模型轨 | 首选 | 三选 | 胜平负 | 大小球可结算 |
|---|---:|---:|---:|---:|
| Current（内部统计轨） | 1/7 | 3/7 | 5/7 | 0/7 |
| Test（内部统计轨） | 2/7 | 3/7 | 5/7 | 0/7 |
| 综合 Primary | 无首版，不能计分 | 无首版 | 无首版 | 无首版 |

## 首选展示与内部值

| ID | Current 展示/内部 | Test 展示/内部 | 报告实际缺项 |
|---|---|---|---|
| `espn:401912587` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912588` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912585` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912586` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912599` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912598` | `1-1` / `1-1` | `1-1` / `1-1` | 有序三比分未展示；综合Primary无首冻 |
| `espn:401912584` | `1-1` / `1-1` | `2-1` / `2-1` | 有序三比分未展示；综合Primary无首冻 |

## 完整性边界和复现文件

- 这7场只更新已找到的亚冠精英分母，不补成20项赛事总体；其余赛事的完整赛程母体仍须独立核准。
- 小球概率来自已交付双模型报告；其数值可复核，但报告和首冻没有冻结一个大/小选择，且引用盘口的报价时钟为空，故大小球不记胜负。
- R9原始结果被用于赛果标签和identity/hash验证；未读取或计入R7/R8/R9研究模型首选与研究研究准确率。
- [综合台账track扫描](comprehensive-ledger-track-audit.json)列出正式根目录与精确ID搜索结果；[展示/内部拆分](displayed-vs-internal-current-test.csv)独立保留每场显示字段；[Current/Test复盘入口原始输出](runtime-v5-paired-review-r9-7.json)由现有配对复盘模块生成。
- 可重复脚本：[严格结果连接](reconcile_r9_current_test.py)、[综合台账与展示比对](audit_comprehensive_and_display.py)、[paired_review调用](run_paired_review_r9.py)、[更新汇总](update_reconciled_audit.py)。
- [更新汇总JSON](audit-summary.json)、[20队列覆盖表](by-competition.csv)、[来源清单](source-inventory.json)保留全批边界。
