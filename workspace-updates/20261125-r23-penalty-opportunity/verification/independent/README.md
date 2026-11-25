# R23 独立复算

信号审计用 Understat 原始事件检查双方镜像差值和覆盖末日。比分审计重建 R7 概率矩阵，根据原始事件和已保存的历史球队 ID 独立计算 12 场暴露与四项特征，并核对历史评估、近期和 11 月追加共 2,300 场的 R7、R23、固定全强度三套首选、三选及概率。[信号结果](audit_signal.json) · [比分结果](expected.json)

完整流程由包根目录的 `verify.py` 执行。若已用锁定的源码和依赖准备好 `source/`、已导出的 `pinned-data/`、重建后的 `events.jsonl` 和一遍完整复训 `refit/`，可在数据仓库根目录单独执行以下命令。[数据与依赖锁](../../source-lock.json) · [完整验证器](../../verify.py)

```bash
R23_AUDIT=workspace-updates/20261125-r23-penalty-opportunity/verification/independent
python -B "$R23_AUDIT/audit_signal.py" events.jsonl | diff -u "$R23_AUDIT/audit_signal.json" -
PYTHONPATH=source/runtime python -B "$R23_AUDIT/independent_scores.py" \
  --data-root pinned-data --events events.jsonl --study refit \
  | diff -u "$R23_AUDIT/expected.json" -
```

独立前向复算读取 R22 原时点的 R7 整矩阵，重算 45 场的球队特征、三个有序比分和概率，并核对 15 席排序、44 条原盘线及原始 R7/R22 引用。以下命令从固定数据导出的 `pinned-data/` 重建矩阵，再对照随包归档的结果。`r22-forward-grids/` 是新的输出目录。[独立前向结果](independent_forward.json) · [R22 矩阵重建说明](../../../20261125-r22-draw-preserving/verification/rank-depth/README.md)

```bash
R23_PACKAGE=workspace-updates/20261125-r23-penalty-opportunity
R22_DIAGNOSTIC=workspace-updates/20261125-r22-draw-preserving/verification/rank-depth/rank_depth.py
PYTHONHASHSEED=0 python -B "$R22_DIAGNOSTIC" forward \
  --source source --data-root pinned-data --out-dir r22-forward-grids
PYTHONPATH=source/runtime python -B "$R23_PACKAGE/verification/independent/independent_forward.py" \
  --study refit --events events.jsonl --grids r22-forward-grids/r7-grids.jsonl.gz \
  --r22 pinned-data/workspace-updates/20261125-r22-draw-preserving/forward \
  --forward "$R23_PACKAGE/forward" --ranks "$R23_PACKAGE/ranked" \
  | diff -u "$R23_PACKAGE/verification/independent/independent_forward.json" -
```
