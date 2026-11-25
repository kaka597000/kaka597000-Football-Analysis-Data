# R18 日本 J1 七日信息截止敏感性

使用同一份 R15 权重和 R7 比分分布，分别读取严格早于比赛日、严格早于比赛日前七日的球队历史。两臂沿用 2024 验证期选定的三个剂量，比分、胜平负、大小球均为 0。530 场的特征有 380 场发生变化，两臂的首选、前三比分、胜平负和每日席位全部相同。[源码 PR #92](https://github.com/kaka597000/Football-Analysis/pull/92)

| UTC 窗口 | 场数 | 特征变化 | 首选比分命中 | 前三比分命中 | 胜平负命中 | 市场胜平负命中/有价 | 实际大小球线 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 测试 | 380 | 268 | 55/380 | 142/380 | 186/380 | 140/270 | 0/380 |
| 2026 近期 | 150 | 112 | 13/150 | 35/150 | 80/150 | 40/76 | 0/150 |

两窗各有 85、31 个比赛日，满三席日分别为 49、20。按日选出的 197、79 个席位，首选命中 25、7，前三比分命中 70、17，三席首选全中为 0/49、0/20。[席位与批次](tables/seat-and-batch.csv) · [配对 KPI 与日期聚类区间](tables/paired-kpis.csv)

逐场表按原 ESPN 赛事 ID 及主客顺序记录常规时间比分。current、lagged、R7 均含有序前三比分与胜平负。市场列按同场 R15 原件记录实际十进制胜平负赔率、方向、庄家和时间口径。市场没有精确比分选项，两窗均无实际大小球线，对应字段留空。空市场对象的场次仍计入窗口分母。[逐场表](tables/match-level.csv) · [窗口覆盖](tables/window-coverage.csv)

## 原件与重建

历史源码固定为 `102e4c5b4b9e3897c36686a227374d36a68c484b`，登记协议 SHA-256 为 `b639ff78f360e4f7ad458b3df285cb0253ee164ea8524cb6c9ee0c4a4755d915`。每次从 Git 导出这个提交，源码工作树可以继续前移。R18 final/repeat 各五个输出、R15 final/repeat 各八个输出均保留，两个来源各自逐字节相同。原名单 JSONL 以固定 gzip 保存，解压 SHA-256 为 `40599f252e115f57b98d6e1450a7eb4ea205a25908204083c7356bd6d99cf58e`。其余 R15 大文件引用同一数据仓库的已发布目录，按清单 SHA-256 `97a3cdc153035f4c1bea4f292cbb5a2cec7351deec2cbf4c92f199ec4f09f243` 逐文件核验。[R15 原始证据](../20261125-r15-j1-lineups/README.md) · [R18 文件清单](manifest.json)

在数据仓库根目录执行。使用 Python 3.12、NumPy 2.3.5、SciPy 1.17.0、LightGBM 4.6.0。构建和核验均在两个全新的单线程 Haswell Python 进程内运行，禁用 NumPy AVX512F。同机两次的五个文件须逐字节相同。构建器还要求五个文件与原归档逐字节相同。跨平台核验时，离散值逐项一致，浮点值使用绝对容差 1e-9、相对容差 1e-7。

```bash
PY=/workspace/football-venv/bin/python
R18=workspace-updates/20261125-r18-j1-cutoff
SOURCE=/workspace/scratch/r18-source
R5=workspace-updates/20261123-all-scope-kpi
R7=workspace-updates/20261123-prematch-literature
REBUILD=$(mktemp -d)

"$PY" -B "$R18/verify.py" --package "$R18" --source "$SOURCE" --r5 "$R5" --r7 "$R7"
"$PY" -B "$R18/build.py" --source "$SOURCE" --r5 "$R5" --r7 "$R7" --out "$REBUILD/package"
cmp "$R18/manifest.json" "$REBUILD/package/manifest.json"
"$PY" -B "$REBUILD/package/verify.py" --package "$REBUILD/package" --source "$SOURCE" --r5 "$R5" --r7 "$R7"
```

本包范围为两个已完赛历史窗口。周末研究发单使用单独的前向登记。
