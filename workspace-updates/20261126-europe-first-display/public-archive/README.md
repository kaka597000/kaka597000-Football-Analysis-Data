# 欧联与欧协联首版公开留档核验

GitHub 的原 PR 核验作业于北京时间 11 月 26 日 15:32:52 完成，服务端记录绑定原提交 `ffe6332aac82ca9886d7cc975c0665eba5bff880`。该提交的两项赛程登记、两份展示冻结、36 场比分表、逐场清单和校验清单均在开球前留档。比分和三席顺序与原登记逐项相符。北京时间 16:33 从公开原始文件端点直接取回七份文件，HTTP 均为 200，与原提交的字节完全一致。[原 PR](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/77) · [原核验作业](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/actions/runs/45776048930/job/139759841996) · [逐份来源与哈希](captures.json)

本记录归档 GitHub 服务事件和公开文件核验。按原协议，第一阶段还需核实原聊天正文及每场首发回执、实际开球和常规时间赛果。严格实盘报价时间沿用原盘口审计的状态。赛果复盘继续按欧联、欧协联各 18 场的原有首选、三选和精选顺序结算。[首发证据口径](https://github.com/kaka597000/Football-Analysis/blob/57c62db0681c8bdaae668c501f98a3b452781f15/docs/standalone-display-settlement.md) · [盘口审计](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/81)

在本目录运行 `python -B verify.py`，比对当前留档、原始提交的校验清单、两份正文哈希和 GitHub 服务时间。还可用 `captures.json` 中的不可变提交 URL 重新公开取回并核对 SHA-256。[核验输出](verified.json) · [本目录校验清单](SHA256SUMS)
