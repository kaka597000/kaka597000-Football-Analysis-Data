# R19 J1 站位名称复核

本包唯一改动是按已登记的 ESPN 原始站位名称与缩写表恢复球员位置组。固定源码 `f17c40be7a611998db3b755c65c1d2ebb1f39dc8`，R19 协议 SHA-256 `79c475cc0311ddc605071bd579103c91c6e41e9fc89f773e7f30a6248adfe3ef`。包内原样保存 R15 62MB 原始数据包、原 530 场预测、原名单快照、R15 原有十场首签 archive、R19 原始九文件 final/repeat 和 19:41:38 +08:00 的 R19 十场首签收据。

## 历史窗口

| 窗口 | 场数 | 实际大小球线 | R15 双方已核实 XI | R19 双方已核实 XI | R19 当前两侧 XI |
|---|---:|---:|---:|---:|---:|
| 2025 evaluation | 380 | 0 | 0 | 380 | 主客各 380 |
| 2026 recent | 150 | 0 | 0 | 148 | 主客各 149；各有 1 场不足 11 名明确首发 |

每窗逐队 XI、先前阵容覆盖、R15 / R7 / R10 / 市场与新模型对照均在 `tables/`。`window-kpis.csv` 留存四项 KPI 与全部分母；`paired-comparisons.csv` 保留 R15 原首选、新选项及固定剂量 personnel 敏感性配对区间；`same-fixture-market.csv` 明列市场覆盖和大小球结算。两窗实际大小球线均为 0，五类大小球结果都保留为零覆盖。每个选席和整批首选结果在 `selected-seats.csv` 与原 `selected-days.jsonl.gz` 中。

R19 只按登记的角色映射修正首发资料，再用固定算法从 R15 原始 roster 重新拟合 full 与 form 模型，并在原验证期重新选择剂量。R15 与 R19 的验证选择中 full 的 score、WDL、total 剂量都为 0；R19 系数以本包 `replay/fit.json` 的实际拟合输出为准，不把 R15 系数描述为直接复用。固定强度 full/form 敏感性比较单列，不代表正式剂量或阶段通过。完整逐场旧 / 新预测及两窗原九文件在 `replay/` 与 `reference/r19/`。

## 原始 R15 十场与 R19 首签

`reference/r15/first-issues.tar.gz` 是原始 R15 prospective archive，SHA-256 固定为 `f56f8308cb3741e17340ecb6802579d401b6280b98feb24773f506fdf1bad7f7`，内部原始 `firsts/receipts.json` SHA 为 `6ee26b469e23febecde863caf0f4f07bcf96b5e42362a4ed66a7e3400e86bb52`。包验证先用 R15 官方 prospective verifier 验证 archive，再从它恢复十场原始 R15 首签供 R19 对照。

R19 forward 的原登记为 `5b57e12c31bd8634-v000001`，SHA-256 `1eeebfe6c0e0e11d4144500919fe570fafaa4fb80fba8ce4daa57a0342217ce1`，记录时间 `2026-11-25T19:41:38.627109+08:00`。验证器在隔离临时目录直接调用 `lineup_position_forward.prepare(..., retry=原登记)`，比较十场 picks、输入绑定和首签载荷；这一步不调用 issue/save，也不回写冻结库。

## 本机验证

用 Python 3.12、NumPy 2.3.5、SciPy 1.17.0、LightGBM 4.6.0；设置单线程 Haswell OpenBLAS，并关闭 AVX512F。R15 原包通过原 intake、原响应和冻结快照重建 2,822 行名单；R19 两次新的 position-role 训练必须同机逐字节相同。打包结果跨机器比较离散字段严格一致，浮点容差为绝对 `1e-9`、相对 `1e-7`。

```bash
export NPY_DISABLE_CPU_FEATURES=AVX512F OPENBLAS_CORETYPE=Haswell
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mpl-r19
R19=workspace-updates/20261125-r19-j1-position-roles
/workspace/football-venv/bin/python -B "$R19/verify.py" \
  --package "$R19" --data-root . --source /workspace/scratch/r19-source
```

CI 在 `.github/workflows/r19-j1-position-roles.yml` 使用同一入口与 pinned source commit。R5、R7、R10 包和原 J1 展示归档从 data worktree 读取；R15 完整原包及两套首签 archive 已嵌入 R19 包中。

本 R19 包不重新签发任何结果，不更改 R15/R18 首签、正式模型或阶段。R19 forward 之后的 FT / 结算由父代理补充。
