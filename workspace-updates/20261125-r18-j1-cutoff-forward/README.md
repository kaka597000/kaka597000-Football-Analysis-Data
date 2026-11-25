# R18 J1 周末十场研究初签的离线复算

`forward_bundle.py` 从 R5、R7、R10、R15 完整训练归档、已签 R15 十场和 11 月 25 日两家提供方的采集原件复算 R18。源码固定在 `source-commit.txt`，当前为 `16fc96be434d231aa41df7c86f10bf24ac884e9a`。每次运行都从本地 Git 对象导出该提交，在新的临时目录调用源码的只读准备与校验函数。R18 初签以签发人导出的原字节交付。

## 本次交付

2026-11-25 七场 FT90 均获双确认后，签发人于北京时间 20:28:48.878425 登记，输入截止为 20:28:40.319007。浦和的双确认时刻为 20:27:41.369198。完整 R15 历史为 2,822/2,822 行。七场的十四侧都读到 11 名明确首发，按原 R15 四大位置口径，十四侧的位置均为 `unknown_or_ambiguous_position`。开球证据为 J.LEAGUE 的七个 JST 分钟区间，此次 ESPN summary 均无可核的实际开球时刻。

十场双方特征复算后，每场都有特征变化。正式 full 的比分、胜平负、总球剂量均为零，两臂的十场决策、排序和三席相同。三席依次为 `espn:401877524`（1–0）、`espn:401877541`（1–1）、`espn:401877538`（1–0）。十场原市场均缺价格和总球线。

| 独立标识 | SHA-256 |
| --- | --- |
| 原 R18 登记 | `9ba2b89ecb7e504ce9eef40701cbf002082c7548df3f06bce458b286852249be` |
| 原 `receipts.json` | `0a9de0ba4f2e2b1a4ad63821b1ea335cbbdbecc73a4dd47f1d88d8552132a30a` |
| `release/firsts-and-evidence.tar.gz`（2,374,805 字节） | `16fbb7bd3ee55d01b4f5713237cd0fd909fde61af8fe2fdee6b85b4a51f76201` |

本包从九场采集目录的真实截止截面剪裁了 25 次回读，压缩入包 23 份唯一正文，另按 #51 引用年度日历。

## 本机路径与环境

以下命令使用 Bash、Linux、Git 和既有的 Python 3.12 环境。数值依赖为 NumPy 2.3.5、SciPy 1.17.0、LightGBM 4.6.0。复算器在导入模型前固定数值线程及 CPU 配置。CI 单独安装依赖，随后在隔离网络命名空间中运行。常规本机复算读取本地文件。

```bash
data=/workspace/scratch/r18-data
src=/workspace/scratch/r18-source
pkg="$data/workspace-updates/20261125-r18-j1-cutoff-forward"
tool="$pkg/forward_bundle.py"
py=/workspace/football-venv/bin/python
intake=/workspace/scratch/live-j1-afc-20261125
canonical=/workspace/WCPP/forecasts/issued-analyses/research-r18-j1-prior-fixture-information-20261125
firsts=/workspace/scratch/r18-forward
base=(--data-root "$data" --source "$src")
```

| 输入 | 数据仓库中相对于 `workspace-updates/` 的位置 |
| --- | --- |
| 原始盘口、R7 矩阵、R10 首次 | `20261123-all-scope-kpi`、`20261123-prematch-literature`、`20261125-r10-shot-conversion` |
| R15 权重、训练输入、采集分卷 | `20261125-r15-j1-lineups/` |
| 原 R15 周末十场及选中三席 | `20261125-r15-j1-lineups-forward/first-issues.tar.gz` |
| #51 登记、展示引用、年度 ESPN 原件 | `20261125-j1-stage-windows/`，年度原件是 `evidence/prematch-07.tar.gz` 的 `raw/espn_calendar_2026.json` |
| 七场 J1 赛后证据和四天日板 | 本机 `$intake`，支持九场最终复盘包和已搬迁的日历原件 |

默认从 R15 历史原始采集分卷重建全部 2,822 行。可另外传入 `--study /workspace/scratch/r15-final`、`--r15-firsts /workspace/scratch/r15-forward` 和 `--rosters /workspace/scratch/j1-lineups-history-intake/checkpoints/final-checkpoint/events.jsonl`。快速路径仍比对正式配方、输入、历史 JSONL 和相邻 snapshot-manifest 的 SHA。R18 历史研究包由单独的流程维护。

## 只读检查

```bash
"$py" -B "$tool" inputs "${base[@]}"
"$py" -B "$tool" probe "${base[@]}" --intake "$intake" \
  --as-of 2026-11-25T12:12:30+00:00
R18_SOURCE="$src" R18_TEST_INTAKE="$intake" \
  "$py" -B -m unittest discover -v -s "$pkg" -p 'test_*.py'
```

固定的 20:12:30 北京截面有六场通过双源 FT90，浦和 `espn:401877547` 待定。该复算保留十个周末目标，输出零份新预测。它从完整采集和剪裁副本分别读回六场，并检查比分、球员、参考时间、全部证据字段和日历。省略 `--as-of` 可用当前观察时点检查输入。

## 从已签发目录打包

签发人提供 R18 原始登记和 `receipts.json` 两个独立 SHA 后，可直接传给 `pack`。下列同机命令从独立的规范账本读取这两个值，检查所有 scope、真实签发时间和首版记录，再与签发人导出的十二个文件逐字节核对。若要比对交接值，可先查看 `pins` 输出。

```bash
original_pins=$("$py" -B "$tool" pins --source "$src" --canonical "$canonical")
reg=$(jq -er .registration_sha256 <<<"$original_pins")
receipts=$(jq -er .receipts_sha256 <<<"$original_pins")
"$py" -B "$tool" pack "${base[@]}" --canonical "$canonical" --firsts "$firsts" \
  --intake "$intake" --registration-sha256 "$reg" --receipts-sha256 "$receipts" \
  --out "$pkg/release"
```

已有九场最终复盘归档时，给 `pack` 增加 `--review-bundle /实际路径/九场最终包.tar.gz`，其 `snapshot/ft-review.json` 须有九场 FT90。工具从该包恢复 R18 截止时的 J1 原始采集，并从 `--intake` 取四张日板和日历审计。原件需与 R18 已签完整日志的哈希一致。若该九场包已在可分发的数据仓库中，另加 `--share-review /数据仓库内实际路径/九场最终包.tar.gz`，相同正文将按包 SHA 和成员名引用。独立分发仅需携带一份共享归档。

单次打包先用完整采集重读所有截止内 J1 状态，检查冲突、撤回及七场双确认，再从剪裁结果重建整批并核对规范初签。两个步骤均成功后以原子方式安装整包。同一内容重复运行保持已有文件，遇到不同内容会报错并保全原件。

## 在另一台离线机器恢复原件

仅需数据仓库、含指定 Git 对象的源码仓库和以上环境。默认复算仅使用前向包及其归档依赖。下面的 `--restore` 在独立目录中还原 `receipts.json`、一份登记和十份原始比赛首次，各自保留 UTC、冻结 ID、记录 SHA 及原始 JSON 字节。

```bash
reg=9ba2b89ecb7e504ce9eef40701cbf002082c7548df3f06bce458b286852249be
receipts=0a9de0ba4f2e2b1a4ad63821b1ea335cbbdbecc73a4dd47f1d88d8552132a30a
restored=$(mktemp -d)/firsts
"$py" -B "$tool" verify "${base[@]}" --release "$pkg/release" --restore "$restored" \
  --registration-sha256 "$reg" --receipts-sha256 "$receipts"
```

本次还用北京时间 20:27:41.369198 截面的九场最终包独立验证了所有 J1 原始回读，得到同一登记和十份预测。下面的命令可在共享主机复现这一步。

```bash
review=/workspace/scratch/nov25-live-review-tools/packages/20261125T122741369198Z-nov25-first-review-jleague.tar.gz
echo "2ad0d42fa60f2ddde28a2cf4a161f1ac8cae1c2afef27dcf8083b53a466ace38  $review" | sha256sum --check
"$py" -B "$tool" verify "${base[@]}" --review-bundle "$review" \
  --registration-sha256 "$reg" --receipts-sha256 "$receipts"
```

在只读交付环境中，可省略两个命令行 SHA，以已审阅数据提交内的 `release/pins.json` 为锚。追加 `--full-intake "$intake"` 或 `--review-bundle /实际路径/九场最终包.tar.gz` 可对当时所有 J1 回读再做完整冲突检查。原已签截止时间直接取自登记。重算须精确匹配所有十份 payload SHA 和登记摘要，包括双方特征前值、后值、差值、七次历史更新、盘口、来源、R7 原矩阵、R15 原席与 R18 新三席。即使正式 full 剂量三项为零，也会逐项核验两臂决策。单场详情在恢复的原始 payload；命令输出另列比赛 ID、特征 SHA、原席和新席。

## 分发文件与证据界限

- `release/pins.json` 记录源码、原登记、原收据索引、十二份原件字节、归档和来源索引的 SHA，并给出共享包引用。
- `release/sources.json` 将采用的每个回读关联到赛程或查询日期、用途、原路径、公共 URL、请求及回读时间、字节数、SHA、提供方标识和原始日志。年度 ESPN 日历只有原回读时刻，其请求时间保留为 `null`。
- `release/firsts-and-evidence.tar.gz` 含十二份原件、日历审计、完整截止日志元数据和按 SHA 去重的正文。正文覆盖实际采用的官方 FT 与 KO、ESPN 开球和所有用于终场及首发核验的 ESPN summary，以及 22–25 日四张日板。年度日历和 R15/基线档案沿用上表原位置。
- R18 登记绑定了三份完整采集日志的字节 SHA。其中混有 AFC 和早期状态行，保留这些元数据才能复核登记。独立剪裁复算从完整日志抽取被引用的行，验证模型实际读取的行哈希，再从完整日志原字节重算登记的三项日志 SHA。逐场结果、历史和预测均由源码从保留的原件重算。重新检查被剪去正文中是否有冲突，需要上面的完整采集或九场包。
- 官方三个采集种类的准入、URL、队序、时钟、字节、页面状态和比分校验全部走所钉源码，包含 `postgame-state-check`。JST 开球分钟保留原半开区间。缺失首发按侧原样记录并保留比赛槽。研究输出沿用 R18 的 R15 原位置口径。
