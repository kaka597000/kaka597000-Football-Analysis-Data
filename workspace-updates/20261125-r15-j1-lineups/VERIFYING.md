# R15 日本 J1 历史首发证据包

这套工具复核 R15 登记的回顾性实验。基准日历含 2,822 个原始 R5 ESPN 赛事 ID。每场都保留主客队的独立证据、缺失原因和前序比赛槽位。最终回放由 `--replay` 决定，训练输入由回放的 `inputs.json` 中两项散列决定。采集继续期间可使用 Maxwell 留存的同 SHA 检查点，或用 `--snapshot DIR` 指定含原版 `events.jsonl`、`snapshot-manifest.json` 和 `coverage-audit.json` 的冻结目录。

## 生成全历史包

R15 的最终源码提交是 `993686077a360705fb02c0667de96fc32b590e3b`。打包器默认使用该提交，核验器核对清单中的同一 SHA。最终训练完成后，先运行以下命令生成全历史包并暂存工作流。保存打包器输出的 `manifest_sha256`。重复执行会校验已有包是否相同。

```bash
/workspace/football-venv/bin/python -B /workspace/scratch/r15-evidence-tools/package.py \
  --intake /workspace/scratch/j1-lineups-history-intake \
  --snapshot /workspace/scratch/j1-lineups-history-intake/checkpoints/final-checkpoint \
  --replay /workspace/scratch/r15-final \
  --source /workspace/scratch/r15-source \
  --source-commit 993686077a360705fb02c0667de96fc32b590e3b \
  --stage-root /workspace/scratch/r15-data
git -C /workspace/scratch/r15-data add -- workspace-updates/20261125-r15-j1-lineups .github/workflows/r15-j1-lineups.yml
```

## 独立核验

在包含 R5、R7 和 R10 的数据仓库根目录执行。轻量核验使用 Python 3.12 标准库。完整核验使用源码仓库的 Python 依赖、LightGBM 4.6.0 和 threadpoolctl 3.7.0。CI 先对原件与清单执行轻量核验，再取出清单中的源码提交进行两次独立训练。

打包器、历史两次复训、前向回算和 CI 都显式设置 `NPY_DISABLE_CPU_FEATURES=AVX512F`、`OPENBLAS_CORETYPE=Haswell`，并将 OpenBLAS、OpenMP、MKL、NumExpr 的线程数设为 1。数值进程在导入 NumPy 前接收这些设置。核验器用相同环境启动独立探针，检查 NumPy 的 AVX512F 分派已关闭，且 NumPy 与 SciPy 实际加载的 OpenBLAS 都使用单线程 Haswell。本地 x86-64 VENV 的两个 OpenBLAS 库版本均为 0.3.30。CI 在作业级设置 `TMPDIR=/tmp`。

```bash
R15=workspace-updates/20261125-r15-j1-lineups
/workspace/football-venv/bin/python -B "$R15/verify.py" --light --data-root .
/workspace/football-venv/bin/python -B "$R15/verify.py" --full --data-root . --source /workspace/scratch/r15-source
```

## 与 Maxwell 的采集接口

- `source_match_id` 是 ESPN 原始事件 ID。`source_sha256` 是 HTTP 正文解压后的 SHA-256。`source_url`、`source_query_time_utc` 与实际摘要请求逐行匹配。`identity_source_sha256`、`identity_source_url`、`identity_source_query_time_utc` 绑定年度赛程原件。采集时钟用带时区的时间表示。回放截止日按原始 R5 比赛日计算。
- 常规请求收据的 `date` 和复查收据的 `event_date` 都绑定已核实赛程的开球时间。复查收据中的日期、赛事 ID、主客队 ID、比分和完赛状态另以原始摘要逐项核对。
- `intake.tar.gz` 保存采集格式说明、精确 ID 清单、目标表、年度表和 249 个额外赛事、两种来源收据、快照清单和覆盖审计、提取器散列、原始正文目录及有序训练行散列。最终快照使用归档的 `observed-extract.py`，SHA-256 为 `945982d5fd4adbc02bcb9941aaf7c7125d132575c690e33a59e24a2d45ecd933`，从全部压缩原件按赛事、身份核验和实际采集时钟重新选择记录。早期快照使用固定的 `extract_v1.py`。采集日志截取到该快照记录的行数，相同正文的多次请求保留全部收据。摘要只能在严格更早的比赛日供后续球队使用。
- `raw/part-*.tar` 每卷约 8 MiB。每个唯一正文只存一个 gzip 成员，成员名为解压正文的 SHA。索引同时绑定 gzip 散列、正文长度和所属卷。年度赛程、试采赛程、摘要和有正文的失败请求采用相同的去重方式。`normalized-starters.jsonl.gz` 有 2,822 行，包含赛程队 ID、各队合格球员 ID/位置或 null、各队状态、请求清单及训练快照收录状态。
- 轻量核验直接从压缩正文读取原始赛事、联赛、开球时间、主客队和完场比分，交叉核对年度赛程、R5 原件与常规时间标识。它按原始首发旗标、11 个唯一 ID 和 G/D/M/F 位置独立重建双方名单，再用冻结的采集器复建训练 JSONL，逐行核对字节散列。
- `replay/` 保存规范训练的八个输出。`weights.csv` 对应初训与全量重拟合，均含六列和两列模型中进球概率、正进球数分布的逐列系数，以及训练场数、边界和选定剂量。`metric-counts.csv`、`paired-counts.csv` 和 `day-counts.csv` 分别记录各臂指标、成对变化和按席位的日批次统计。
- 登记日历按顺序含 1,912、380、380、150 场。2025 年测试窗有 85 个比赛日，其中 49 日够三场。近期窗有 31 个比赛日，其中 20 日够三场。两窗实测大小球线均为 0 条，可结算命中率为空。固定总体分母保留 380 和 150。市场胜平负按当场实际出价单独计数。
- 完整核验从同一份逐行重建的训练输入启动两个新的训练进程。两次都重新构建球队历史、拟合两个模型、选择剂量、计算指标和日期聚类区间，并生成前向权重。同一环境两次运行的全部文件须逐字节相同。与发布回放跨环境比对时，仅浮点数允许相对 1e-7、绝对 1e-9 的误差。赛事、计数、排名、选项、身份以及其他离散值逐项相等，每次前向配方还须绑定各自的拟合文件散列。

## 可选前向补包的执行顺序

1. **先生成全历史包。** 按首节单独运行 `package.py`。确认历史包中已有完整 2,822 场训练的 `replay/forward.json` 及其绑定的 `fit.json` 和 `inputs.json`，记录历史清单 SHA 后再签发。
2. **人工签发。** 在签发 shell 中先执行下方的环境设置，再沿用固定源码的 `research_program.lineup_forward --issue`、原冻结库和真实签发时钟。`--study` 指向全历史包的 `replay/`，`--rosters` 指向与包内散列相符且旁有原 `snapshot-manifest.json` 的训练 JSONL。签发后运行 `sha256sum "$R15_ISSUES/receipts.json"`，在补包之外独立留存该散列。它绑定原登记与十场首签。
3. **最后补前向。** 使用下方 `prospective.py pack`，将已签原件写入单独的 `BUNDLE`，再执行 `verify` 和 `recalc`。`R15_ISSUES` 和 `R15_FIRST_STORE` 分别指向第二步的原签发目录和冻结库，`R15_RECEIPTS_SHA256` 使用第二步留存的散列。若使用已有的两个暂存选项，也在这一步向同一版本的历史打包命令追加 `--forward-issues "$R15_ISSUES" --forward-freeze-root "$R15_FIRST_STORE"`，它会先核对已有历史包再写补包。

第二步在启动原签发进程前设置环境。

```bash
export NPY_DISABLE_CPU_FEATURES=AVX512F OPENBLAS_CORETYPE=Haswell
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
```

第三步在历史包和首签目录都已就绪后执行。

```bash
PY=/workspace/football-venv/bin/python
TOOL=/workspace/scratch/r15-evidence-tools/prospective.py
DATA=/workspace/scratch/r15-data
STUDY="$DATA/workspace-updates/20261125-r15-j1-lineups"
BUNDLE="$DATA/workspace-updates/20261125-r15-j1-lineups-forward/first-issues.tar.gz"

"$PY" -B "$TOOL" pack --study-package "$STUDY" --data-root "$DATA" \
  --issues "${R15_ISSUES:?set the actual first-issue directory}" \
  --freeze-root "${R15_FIRST_STORE:?set the issuing freeze root}" --out "$BUNDLE"

"$PY" -B "$TOOL" verify --study-package "$STUDY" --data-root "$DATA" \
  --bundle "$BUNDLE" --freeze-root "$R15_FIRST_STORE"

"$PY" -B "$TOOL" recalc --study-package "$STUDY" --data-root "$DATA" \
  --bundle "$BUNDLE" --source /workspace/scratch/r15-source \
  --receipts-sha256 "${R15_RECEIPTS_SHA256:?set the independently retained receipts.json SHA}"
```

`verify` 和 `recalc` 均可使用独立首签库或外部留存的首签索引 SHA，也可额外给出 `--registration-sha256`。原 J1 展示登记默认取自数据仓库的 `workspace-updates/20261125-j1-stage-windows`，`--display-windows` 可指定同一登记的原件目录。

- `pack` 检查 R15 专属轨道的登记与十条 `FIRST_PREMATCH` 首签，逐个比对冻结库对应作用域的 `000001.json`，也查验七个排除槽位的首签路径。包内每条研究首签只存一份。目标文件仅创建一次，相同内容可重复打包。正式展示目录、基线和首签库只读。
- `verify` 从原 R5/R7/R10 登记恢复日历，按已签 `inputs_cutoff_at` 逐场划分。原 17 场中，开球时间小于或等于截止时间的 7 场占据原槽位，研究登记恰含其余 10 场。每场核对赛事、主客、开球时间及三条原首签。十场的市场覆盖分别统计胜平负、实际大小球线、双边大小球价格和配对盘口，分母均为 10。研究席位按首选比分概率降序、原赛事 ID 升序复算。
- `audit.json` 留存 17 场的三套原预测、十场研究首签及盘口覆盖、三个研究席位和先前公开的三个原推荐。包内 `display/` 保存截止时间前的原展示登记、已发布消息、作者首签及 Current/Test 对照首签。两套席位各自绑定签发记录。
- `recalc` 从历史包中的压缩原件重建训练输入，从固定提交 `993686077a360705fb02c0667de96fc32b590e3b` 导出模型，按历史复训的 NumPy 与 OpenBLAS 设置调用只读的 `lineup_forward._prepare`。回算从首签记录中只取原登记轨道与时钟，逐场比对预测载荷的完整 SHA，再比对包含席位的整个登记载荷。终端回报覆盖计数、散列和实际使用的 BLAS 版本与内核。

模拟测试命令如下。

```bash
cd /workspace/scratch/r15-evidence-tools
/workspace/football-venv/bin/python -B -m unittest -v test_prospective
```
