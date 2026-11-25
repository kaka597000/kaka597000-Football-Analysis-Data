# R20 日职 J1 半场状态研究数据

本包复原赛前模型的两次历史复训和 2026 年 11 月 28–29 日十场真实研究初签。半场比分仅用于历史参数估计，预测时对可能的半场比分积分。复算使用预登记 `bffa6a29e70fa8573cdc0f6f7e19cd2ec8bff71c` 和实际训练、签发时的源码 `4a70ba43df38750e14ddcb11a6b585064bd272ec`。后续 `5adcca645b0dea1f6765d32f105fb95255b71b1a` 仅修改 `test_halftime_state.py` 的导入，模型、历史回放、前向和协议的字节相同。

## 实际覆盖与结果

原 R5 登记的 2,822 场全部保留。核验器从现有 R15 的八个压缩分卷读回逐场 ESPN 原响应，用赛程和球队 ID 对齐原 R5、R7、R10，并按两段原始 `displayValue` 检查两队半场和与全场比分。2,818 场合格，四场排除原因见 `release/tables/ineligible.csv`。训练和验证各有两场缺失或冲突，评估与近期窗全部合格。另从原 R18 证据验证 11 月 25 日七场，单独保存排除记录。历史采集有真实回读时钟，可认证的逐场历史首次获知时刻缺失。

| 历史窗口 | 全部场次 | 有效半场 | 候选第一比分 | 候选前三比分 | 候选胜平负 | 实际大小球有效数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024 年前训练 | 1,912 | 1,910 | — | — | — | — |
| 2024 年选剂量 | 380 | 378 | — | — | — | — |
| 2025 年评估 | 380 | 380 | 55/380 | 142/380 | 186/380 | 0 |
| 后续 R5 近期窗 | 150 | 150 | 13/150 | 35/150 | 80/150 | 0 |

验证选出的比分、胜平负、总球剂量均为零。候选十场与签下的 R7 决策相同。全量状态调整单列，评估窗前三比分为 141/380，近期窗为 34/150。市场胜平负有真实同场决策的场次分别为 270 和 76。原盘口缺失保留为空，配对区间及每轨每项分母见 `release/tables/`。

全历史复拟合的主客半场进球份额分别为 0.416984 和 0.420853，半场领先、落后的后半场倍率分别为 1.019649 和 1.053983。评估窗有 49 个满三席日和 36 个短日，近期窗分别为 20 和 11 个。两个窗口满三席日的第一比分全中次数均为零。每席、逐日和 1–1、2–2 的完整统计在原始 `metrics.json` 和 `seats.jsonl.gz` 中。

## 周末研究首次

北京时间 20:48:12.873773 登记十场。十场的输入截止、逐场原签发时钟、价格、R7 原矩阵、两轮研究的原引用、排序和席位均从原件回读。十场原总球线均缺失。

| 席位 | ESPN ID | 对阵 | 第一比分 | 三个有序比分 |
| ---: | --- | --- | --- | --- |
| 1 | 401877524 | 町田泽维亚 – 东京绿茵 | 1–0 | 1–0 / 2–0 / 1–1 |
| 2 | 401877541 | 水户蜀葵 – 长崎成功丸 | 1–1 | 1–1 / 0–1 / 0–0 |
| 3 | 401877538 | 名古屋鲸八 – 福冈黄蜂 | 1–0 | 1–0 / 1–1 / 2–0 |

## 交付文件

| 路径 | 内容 |
| --- | --- |
| `release/halves-intake.tar.gz` | 采集方原清单、原脚本、说明、来源索引、2,822 行历史半场、四场异常及七场独立排除；同时保留原晚间采集索引 |
| `release/r18-reference.tar.gz` | 原 R18 登记、收据和十场首次，加上用于逐场验证七项排除的七份 ESPN summary |
| `release/study/` | 原始六文件，包括训练权重、验证剂量试验、完整历史预测、席位、配对净变化及日期聚类区间和全历史前向配方 |
| `release/ten-firsts.tar.gz` | R20 的登记、收据和十份真实首次，与签发人的导出及规范账本逐字节一致 |
| `release/tables/` | 可重建的各窗 KPI、配对区间、全部选中席位、拟合系数、四场排除明细 |
| `release/manifest.json` | 全部交付文件哈希、两次独立原复训各自的六文件清单、原登记和逐场 payload 哈希 |

上述数据文件共 1,000,807 字节。2,822 份历史 summary 和原始年度/日板沿用本数据分支已经收录的 R15 与 R5 档案。两个真实复训目录的六个文件逐字节相同，共享同一份已核验内容。七场晚间标签与历史输入分开保存。

## 从数据提交离线复算

使用已有的 Linux、Git 和 Python 3.12 环境，数值依赖为 NumPy 2.3.5、SciPy 1.17.0 和 LightGBM 4.6.0。将 `data` 与 `src` 指向本地数据和源码 Git 仓库。CI 在依赖准备后关闭网络，在临时目录重建来源、独立运行两次历史 CLI，再按原始截止复算整个前向登记和逐场初签。

```bash
data=/workspace/scratch/r20-data
src=/workspace/scratch/r20-source
pkg="$data/workspace-updates/20261125-r20-j1-halftime"
py=/workspace/football-venv/bin/python
rev=4a70ba43df38750e14ddcb11a6b585064bd272ec
reg=8b718c63b4620a34d8640d7df2fa7efa2849c3a24bea15cb058c470ce3614f65
receipts=f84db93bd24092db6d84dfd039996c5f738d2c6561c32642b5cc9ae69041195f
base=(--data-root "$data" --source "$src" --source-commit "$rev" --registration-sha256 "$reg" --receipts-sha256 "$receipts")
"$py" -B -m unittest discover -v -s "$pkg" -p 'test_*.py'
"$py" -B "$pkg/package.py" verify "${base[@]}"
```

从生产者的真实交接路径重建同一数据包可执行下列命令。重复打包核对已有文件。归档安装和恢复都使用独立目录，前向校验只调用源码的只读接口。

```bash
"$py" -B "$pkg/package.py" pack "${base[@]}" \
  --intake /workspace/scratch/r20-j1-halves-intake \
  --r18-bundle /workspace/scratch/r18-data/workspace-updates/20261125-r18-j1-cutoff-forward/release/firsts-and-evidence.tar.gz \
  --study /workspace/scratch/r20-historical --repeat /workspace/scratch/r20-historical-repeat \
  --firsts /workspace/scratch/r20-forward \
  --canonical /workspace/WCPP/forecasts/issued-analyses/research-r20-j1-latent-halftime-20261125
```

如需单独读取原始首次，在新的目录执行 `tar -xzf "$pkg/release/ten-firsts.tar.gz"`。训练行 SHA-256 为 `923dfda86ab85343a59a3b97f9cdeb816633fd47c29d450a3934b57ec7565839`，采集方原定版清单为 `46f4c05bc84081fcd8496da1848f93ab498098af7204d109a831cf8123a2a16a`。
