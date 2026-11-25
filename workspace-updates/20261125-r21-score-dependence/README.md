# R21 五联赛比分相关性原始证据与复算包

本包固定 R21 登记协议、Understat 原始历史、四类基准输入、历史重训结果和真时钟前向首发/排序记录。所有复算限定在该数据包与锁定源码上；研究产物不具备正式 KPI 资格，也不触发模型晋升或新签发。

## 来源与锁定

| 输入 | 来源及用途 | SHA-256 / 版本 |
| --- | --- | --- |
| R21 源码 | `https://github.com/kaka597000/Football-Analysis`，R21 完整数值、历史和前向实现 | `828f7a68daff347dfef4e69185e7761965954582` |
| R21 协议 | 源码提交中的 `research/20261125-r21-score-dependence/protocol.json` | `a4eb968e0965882c0844235fb0e9448a25a172f4a4ea8f16ec6d5e490439ed52` |
| Understat | R14 数据 PR #51 的 `workspace-updates/20261125-r14-territory-press/inputs/understat.tar.gz`，保留原始 `getLeagueData` 响应及离线提取器 | `c83b75b247ad86e1fa8b52fa7063e666837be02016386188e250a128a73225c2` |
| R5 | `workspace-updates/20261123-all-scope-kpi`：原面板、R5 市场与来源原档 | manifest `f3b6fa64903e97a6c74966362894c3378dfe5bca03a4a84709d4c694946ed3d8` |
| R7 | `workspace-updates/20261123-prematch-literature`：比分边际、已登记控制与历史首发 | manifest `e2ed191e29150ba59bf9623ce2a44b265e8b71c9e777d9197ec869975a957df3` |
| R10 | `workspace-updates/20261125-r10-shot-conversion`：逐场市场/模型对照与前向首发 | manifest `f136707b0d5cbbac883f74cc9ce8dc85e9bc434ece591a2ba8c72c327faaf8cb` |
| R11 | 本包 `inputs/r11/`：真实来源扩展及来源 manifest | manifest `d76cdbc338407c9962122f70aa69a071c0df51203fc2cb6e74d9a722054543bb` |

R5、R7、R10 的原件直接复用此数据分支现存文件，并由上游 manifest 逐文件校验；R11 的 manifest 与扩展原档在本包内保留。详细路径和各文件散列列于 [source-inputs.json](inputs/source-inputs.json) 与 [source-lock.json](source-lock.json)。重训环境固定 Python 3.12、LightGBM 4.6.0，并使用锁定源码的 `requirements.txt`。

## 包内结构

```text
inputs/
  understat.tar.gz                R14 #51 原 Understat 包的逐字节副本
  r11/manifest.json
  r11/extension.tar.gz
  source-inputs.json              R5/R7/R10/R11 输入路径和原 SHA
verification/understat/          独立原始核验脚本、逐响应审计与覆盖表
forward/                          原 R21 登记和 45 份首发记录
ranked/                           原 15 席排序计划
replay/reference/                 Dalton 首次完整历史重训输出（27 文件）
replay/repeat/                    Dalton 独立重复输出（27 文件）
reports/                          逐赛事/窗口覆盖、权重、剂量、配对增益表
verify_understat.py               标准库离线原始审计
verify_freezes.py                 冻结 SHA、身份、时序和席位核验；不签发
verify.py                         CI 全流程复算包装
tables.py                         从已复算 metrics.json 生成报告表
source-lock.json                  完整源码及运行时锁
manifest.json                     本包全部文件的 SHA-256 清单
```

## Understat 计数修正与核验

`verification/understat/reports/verification.json` 的赛事计数与 npx 指标现在均按联赛统计，并有独立的联赛合计/全局总计断言。五联赛事件数为英超 2,340、西甲 2,358、德甲 1,881、意甲 2,340、法甲 2,112；对应双方 npxG 和 npxGA 侧值分别是赛事数的两倍，两个镜像方向分别逐场核对，无冲突。全局为 11,031 场、22,062 个 npxG 侧值、22,062 个 npxGA 侧值、每个镜像方向 11,031 次。历史赛事 ID、日期、主客队名/ID、比分和各项源响应 SHA 均从 gzip JSON 独立复算。

npxG 与 npxGA 原始值来自 Understat 每队 history，并存于固定事件的 `source_history_sides.home/away`。顶层 `home_xg/away_xg` 与 `home_xga/away_xga` 是普通全射门 xG/xGA，不是 npx 指标。R14 原始归档有 35 份响应，覆盖 2020/21 至 2026/27；原始捕获时间为 2026-10-15，最近完成日期因赛事而异，未声称覆盖到 2026-11-24。逐赛事原文件 SHA、来源 URL、时钟和赛季日期覆盖见 `verification/understat/reports/`。

## 历史结果与覆盖

Dalton 提供的 `replay/reference/` 与 `replay/repeat/` 各有 27 个文件，文件集合、每个字节以及目录树散列相同。该证据包重训所有五联赛，CI 将再次训练两次并与这两套原件逐字节比较。

固定 2025/26 评估样本为 1,752 场。候选与 R7 的四项命中计数依次为：比分首选 234/235、三选覆盖 597/609、胜平负 933/933、实际大小球全赢非走盘 1,019/1,018。研究报告保留逐赛事、evaluation/recent/November extension 三窗的分母、双边 prior-history 暴露、每联赛拟合系数与选定剂量，以及 R21 对 R7、同场市场、截距模型和匹配剂量截距消融的净增/净损及日期聚类 95% 区间。数值表为 [competition-window-coverage.csv](reports/competition-window-coverage.csv)、[fitted-weights-and-doses.csv](reports/fitted-weights-and-doses.csv) 与 [paired-gains.csv](reports/paired-gains.csv)。

## 真时钟首发与排序

保留的 R21 登记 SHA 为 `03fbf89faf84312015532a3d935824bfe6e5eb0560c609a2f3654cc873aea33c`，记录时钟为 `2026-11-25T21:17:21.555419+08:00`；排序计划 SHA 为 `2b8e50f9248f21685b19f5236c10c6a02fe6926bd52ac3b4da1d4c4b7936cf35`。原 R7 五联赛 48 场中 3 场已开赛，登记其余 45 场。独立核验确认实盘双边 44/45，双方各有近期历史 42/45；相对 R7 首选变更 1 场、三选顺序变更 6 场。按原首选概率、开球时间、稳定 ID 重建的每联赛前三席与原排序逐字段一致。所有首发仍是 2026-11-25 原记录；验证程序只计算并比较 payload，不调用登记或 issue 写入器。

## 本地复现

在数据仓库根目录使用锁定源码检出到 `source/` 后运行：

```bash
python3.12 -m pip install -r source/requirements.txt lightgbm==4.6.0
PYTHONPATH=source/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3.12 -B workspace-updates/20261125-r21-score-dependence/verify.py \
  --source source --data-root .
```

CI 使用相同命令和完整源码 SHA。它先从 R14 #51 Understat 压缩档恢复原件并运行独立核验，再离线重建 `events.jsonl`；然后对五联赛完整训练/历史重放两次，验证逐字节确定性、27 文件参考结果、权重和报告表，并在原登记时钟对 45 份冻结 forecast payload 做纯函数重算、重新排序 15 席。运行期间不会写入共享冻结库、不会重新签发，也不会修改两个历史输入目录。

本次归档由 Codex 工作区代理整理和独立复算；历史参考与重复输出由 Dalton 提供；Understat/R5/R7/R10/R11 来源及提交号保留在锁文件和输入审计中。GitHub Actions CI 的训练执行记录将作为后续 PR 检查结果。
