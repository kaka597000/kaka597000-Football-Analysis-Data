# R10 欧冠九场赛前证据补充

本包归档并复核 2026-11-25 欧冠九场的既有 R10 排名、首发与同价市场比较。它不生成赛果、预测或 TOP3，也不改动六场登记时的未发状态。不可变登记 SHA-256：`1823c3846b5e21c479cb57f1a2e426ceb590e35f71f53b9a20990f2cb02e6755`。

## 九场和首发

`registration.json` 固定九场、R10 原始同输入模型记录和原排名。原三席（Shakhtar–Fenerbahce、Atletico–Viking、Sporting–Man U）及其三个原 canonical、Current/Test 对和原始显示文本仍由本 PR 的 R10 原包提供；本补充校验其冻结 ID、记录 SHA、席位和排名完全不变。其余六场综合 FIRST canonical、原生 11 月 5 日记录、11 月 25 日 Current/Test 对、`six-firsts.json` 与真实文本 `message.txt` 均随 `canonical-records.tar.gz` 归档，并逐场核对签发 SHA、文本选项与开球时间。用户报告六份 FIRST 的文本曾在对话中逐字展示；独立平台 readback/receipt 未提供，本包明确记录该证据限制，不将对话展示表述成平台回执。

九场同盘市场 canonical 是独立的市场比较首签，不替换综合 FIRST 或原三席。它们逐场引用综合 FIRST 的同一 ESPN 市场原件及 DraftKings 价格；市场签发时间晚于综合 FIRST。原件没有 provider `quoted_at`，故只保留 ESPN `query_time`，不声称获得独立报价时间。`same-price-market-runtime.tar.gz` 与锁定脚本复算九场 `_full_market`/`pick` 输出，并对比 canonical payload。

## 输入时间与来源

六场综合 FIRST 所依据的 ESPN、FotMob 和近期比赛原件及逐响应 `.meta.json` 收在 `observed-inputs.tar.gz`。最早综合 FIRST 为 `2026-11-25T12:45:40.368501Z`；142 条实际响应均早于该时刻，其中 114 条晚于 12:30:35Z 初始登记、但早于综合 FIRST。`source-time-classification.csv` 的时间来自每个响应的 sidecar，不使用聚合清单占位时刻。校验器逐项检查原件 SHA、readback SHA、时间与分类，并验证六场目标 FotMob 伤停/可用性原件。

后取的俱乐部网页单独放在 `post-issue-club-pages.tar.gz`，索引为 `post-issue-club-pages.json`。十份 HTML 均在最早综合 FIRST 之后获取，只作为赛后补充资料，`pre_match_inputs_used=false`；每页时间取对应 HTML 的真实 `.meta.json`。另保留一条 Liverpool 页面孤立 meta：其匹配正文未留存，索引标明不可用于模型或赛前依据。不得用聚合清单顶层时间覆盖各页时间。

## 文件和复算

- `current-test-live-supplement.tar.gz`：六场真实 Current/Test 双模型、fixture、发布 receipt 和 ESPN 原始响应。
- `canonical-records.tar.gz`：六场综合 FIRST、六场 11 月 5 日 native canonical、六场 11 月 25 日 Current/Test canonical、九场同盘市场 canonical、六场原始 FIRST JSON 与展示文本。
- `observed-inputs.tar.gz`、`post-issue-club-pages.tar.gz`：赛前输入和后取网页分开保留。
- `nine-match-review.csv`、`nine-firsts-index.json`、`same-price-market-index.json`：逐场复核索引。
- `manifest.json`：本目录所有交付文件的 SHA-256。

在仓库根目录执行：

```sh
python -B workspace-updates/20261125-r10-ucl-nine-completion/verify.py
```

GitHub Actions 使用 Python 3.12，并安装固定的 NumPy 2.3.5、SciPy 1.17.0、LightGBM 4.6.0；设置 `NPY_DISABLE_CPU_FEATURES=AVX512F`、`OPENBLAS_CORETYPE=Haswell`、单线程 OpenBLAS/OMP 后运行同一校验器。校验器先运行 R10 原包校验，再核验登记、全部原件和签发回执、赛前时间、市场代码 pin 与九场复算结果。

验证输出区分登记时与当前状态：`at_registration_unissued=6`、`issued_now=9`、`pending_comprehensive_now=0`、`market_same_price=9`。登记中六个空位已由真实签发填入；原三席仍为原件。
