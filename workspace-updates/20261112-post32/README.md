# PR #32 后续归档与恢复

原源码 main：`c47ee5b8910f8e54f7587348fedc97ea67c1a07e`（PR #32 已合并）。
此目录保留 PR #32 的真实验收、Elo/Kelly 研究和 xG 数值输出，哈希及 Actions 来源见 `archive-index.json`。Actions 附件过期不影响恢复。

`recovery-catalog.json` 复用已有长期 core 归档，只新增约 2.5 MB 的日职兼容依赖、球队身份凭据和当前 19 路注册表。恢复脚本逐段、整包、逐文件验哈希，拒绝覆盖不同文件。不要把旧 core 内的 21 路注册表替换到当前环境。兼容 manifest 含机器路径，应在新环境重新生成；不更改原工件哈希。

源码中的 `.github/workflows/pr32-validation.yml` 给出全新 runner 的恢复命令。已有严格集成结果（24 组、769 次执行、零跳过）属于原验收版本，新的持久恢复 CI 专门验证恢复与日职真实工件，不冒充新的全套生产验收。

运行版本分别记录：源码最新提交、采集任务固定源码、训练/前向任务固定源码、活动注册表/工件。候选和新源码不自动晋级模型。`latest-source.json` 与后续执行报告记录这些身份。

盘口任务沿用现有每六小时采集调度，最多两次请求、一个地区的 h2h/totals，不重试；需要既有 GitHub Secret `WCPP_ODDS_API_KEY` 或 `THE_ODDS`，缺失会保存 `MISSING_CREDENTIAL`。从云端成功采集不推断 GitHub 的密钥可用，绝不复制云端凭据。模型可用报价要求来源市场时间、完整同线价格及 ESPN 主客/开球匹配，60 秒窗口不随结果放宽。

PR #7 已合并；main 实际部署运行 `43223434033` 成功，盘口业务状态仍为 `MISSING_CREDENTIAL`。原前向队列在该次运行中为 24/80 已核验完赛、56 待定；欧冠独立 36 场尚无已通过核验的完赛结果。

补充 `elo-independent-temporal.tar.gz` / `elo-supplement-index.json`：盘口缺失没有阻断独立 goals/Elo 对照，固定旧系数在 2526 的 1,737 场合格目标均命中 208 次、净增 0，不晋级。`elo-independent-report.json` 可直接查看分联赛和不确定性。它仍不是活动 Current/Test 同场增量或历史 as-of 认证。前一执行包零覆盖专指五臂共同盘口面板，保留原版本，不覆盖旧结果。
