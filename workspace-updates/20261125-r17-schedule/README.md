# R17 同联赛赛程密度研究与核验包

数值源码固定为 `52afde502578686e79ff636ffbdab9d7b50d9aa4`。历史输入来自原 R5、R7、R10 数据包；R17 原始 R7 与同场市场基线按赛事、窗口逐场保留。主研究覆盖 20 项赛事。六个较早赛季按各自日历独立拟合和评估。前向研究回执与项目综合首签分轨保存。

## 历史结果

下列计数顺序均为 **R17 / 原始 R7**。完整主研究窗共 5,233 场：首选命中 `630/633`，三选命中 `1,711/1,721`，胜平负两组均为 2,737/5,233，有真实赛前总球线的结算全赢 `1,471/1,470`（该项分母 2,578，另列半赢、走盘、半输、全输）。近期窗首选 `310/317`；六个独立旧赛季合计首选 `270/272`。原 R7 和同场市场按赛事比较及可用覆盖都在逐赛事 CSV 与压缩逐场回放中。

全三场首选同时命中按完整比赛日批次计：主研究 `3/833`，近期 `0/416`，旧赛季 `0/369`。各赛事各窗口另列短批次、实际席位、每个有序席位的首选/三选命中、市场可用性及配对差异。四项 KPI 配对区间按比赛日期整组重采样；完整批次 sweep 比较使用独立的 2,000 次日期配对 bootstrap（种子 `20261125`）。

韩职原始 FotMob 赛季收据共核验 1,974 场；1 场行政判定保留为排除项：`2021-09-18 fotmob:3524653`，原因 `awarded`。剩余 1,973 场用于合规 FT 记录。九个不同赛季归档的原始 SHA-256 在 `evidence.json` 中各列一次，不按比赛重复罗列。亚冠首个训练折为 0 场时，注册岭目标唯一解是全零权重；验证、测试场次继续保留，候选逐场等于原始 R7。

## 前向签发

冻结时间为 **2026-11-25 18:58:20 北京时间**，原始回执 SHA-256：`7605a06287326419397da2cace477940fa23af7411d7ddb112dcd456e05dbc4b`。原注册 192 场中，赛前完整纳入 39 批、150 场；每条规则合计 85 个席位，114 场保留原始实盘总球线；12 个已开赛批次排除。最早纳入开球为 **2026-11-26 01:45 北京时间**。核验会从原签名 R5/R7 首发记录重新构造席位与赛事身份。

## 数值环境与复算

本机入口和 GitHub Actions 均固定 `NPY_DISABLE_CPU_FEATURES=AVX512F`、`OPENBLAS_CORETYPE=Haswell`、`OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`。包内记录 Python、NumPy、SciPy、LightGBM 版本。两次受控原始回放各 77 个文件，逐字节一致；CI 另做两次独立全量重训、离散字段精确核对和浮点 `atol=1e-9, rtol=1e-7` 比较。

从安装了源码依赖的 Python 3.12 环境运行：

```sh
./run_local.sh \
  --source /path/to/Football-Analysis \
  --source-commit 52afde502578686e79ff636ffbdab9d7b50d9aa4 \
  --r5 /path/to/20261123-all-scope-kpi \
  --r7 /path/to/20261123-prematch-literature \
  --r10 /path/to/20261125-r10-shot-conversion \
  --final /path/to/r17-replay \
  --repeat /path/to/r17-repeat \
  --forward /path/to/r17-forward
```

`r17-replay.tar.gz` 是保留逐场结果和逐赛事表格的确定性压缩档；`manifest.json` 校验包内文件。数据仓库根 `.github/workflows/r17-schedule-evidence.yml` 执行 CI，源码 checkout 使用包内 `source-commit.txt` 固定 SHA。
