# 日职联历史双边射正

四份留存的 5Dollar 响应通过 SHA-256 校验。统一赛事库的 162 条证据去重为 136 场。每场按唯一 ESPN 赛事 ID 交叉核验 R5 日职联常规赛比赛日、主客和 90 分钟比分，同时核对原始响应的球队键、开球时间及双方射正、射偏。26 场涉及有已登记别名重定向的京都不死鸟或横滨水手，解析旧球队键后全部对齐。百年构想赛程在 R5 常规赛面板之外。[对照明细](paired-sot.jsonl) · [覆盖与来源哈希](coverage.json)

| 原面板区间 | 常规赛 | 有双边射正和射偏 |
| --- | ---: | ---: |
| 2025 年以前 | 2,291 | 0 |
| 2025 年上半年 | 218 | 0 |
| 2025 年下半年 | 162 | 50 |
| 2026 年截至 11 月 21 日 | 150 | 86 |

保留比赛时段为 2025 年 10 月 17 日至 12 月 6 日及 2026 年 8 月 7 日至 10 月 10 日。射正原件采集于北京时间 2026 年 10 月 10 日 20:58 至 20:59，136 场的源端首次可见时点均缺失。四份响应均无 xG 或直接总射门字段。可采用按原比赛日隔离的历史开发，或在 10 月 10 日之后按实际采集回执使用这些过程数据。第一阶段继续按正式首次展示、赛前冻结和核实赛果结算。[R10 射正对照](../../20261125-r10-shot-conversion/README.md) · [近期另存的 FotMob 资料](../../20261126-j1-recent-process/README.md)

读原工作区的 SQLite 和四份留存响应可以复算。公开表包含配对值、原场次 ID、回执时间及原件哈希。从数据仓根目录运行下列命令，两份输出可与本目录逐字节比较。[提取程序](extract.py)

```bash
python -B workspace-updates/20261127-r46-j1-process-at-fixed-total/history/extract.py \
  --panel workspace-updates/20261123-all-scope-kpi/models/jpn.1.tar.gz \
  --db /workspace/WCPP/data/unified/WCPP_统一赛事库.sqlite \
  --raw /workspace/WCPP/reports/5dollar-history-20261010 \
  --out /tmp/j1-shot-evidence
```
