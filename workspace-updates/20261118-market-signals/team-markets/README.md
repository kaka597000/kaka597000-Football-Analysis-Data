# 双方进球与球队进球盘口采集

| 赛前样本 | 已发现并确认 | 请求事件数 | BTTS 双边报价 | 主队 0.5 盘 | 客队 0.5 盘 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 已注册的巴甲比赛，11 月 18 日 | 6 | 6 | 6 场 | 0 场 | 0 场 |
| 英超独立采集，11 月 21 日 | 7 | 2 | 2 场 | 2 场 | 2 场 |

巴甲在北京时间 11 月 18 日 14:20 采集了 24 个双方进球的完整双边报价，每场各有四家机构。数据来源是 The Odds API 逐事件端点，使用欧区同一次请求检索 BTTS、球队进球与球队进球备用盘。科里蒂巴对桑托斯另查美国、英国、澳洲和美国第二区，也只返回 BTTS。备用 BSD 返回六场 BTTS 共识价格，其中弗拉门戈一场最后更新于 11 月 14 日。BSD 未返回具名机构的单队 0.5 赔率。API-Football 当次授权赛程请求返回 HTTP 403。[巴甲来源及覆盖](runs/20261118-first-eu/coverage.json) · [备用源和区域探测](diagnostics/index.json)

英超使用 ESPN 和供应方 20 个活动赛事的目录，在四天窗口内找到七个事件，逐一确认为 11 月 21 日比赛。按开球先后和主队名排序采集前两场。北京时间 14:28 存档 88 个 BTTS 或球队进球完整双边报价，包括主客队不同盘线。博彩公司同场同时提供 BTTS、主队 0.5、客队 0.5 的，曼城对富勒姆有 4 家，阿斯顿维拉对桑德兰有 5 家；每个市场拥有自己的真实报价时间。为供独立赛前候选复核，英超原始响应还同时包含同机构的全场胜平负及总进球盘。[英超赛程和身份](runs/20261118-epl-us-pilot/discovery-receipt.json) · [英超盘口和覆盖](runs/20261118-epl-us-pilot/coverage.json)

## 读取口径

每次采集的 `raw/` 保存未改变的成功供应商 JSON 字节。`requests.json` 登记来源 URL、SHA-256、请求与收到响应的时间、配额。`quotes.json` 中一个条目等于一场比赛、同一机构、同一市场、同一球队与盘线的一份完整双边报价。主客依据原始提供方球队名称匹配。报价时间来自供应商的市场级 `last_update`。返回相同赔率的普通盘与备用盘在同一时点合并，相互矛盾的同一时点报价单列。采集保留有效历史价格，使用时额外检查与分析截点的间隔。巴甲两队 0.5 的缺失按缺失登记；英超盘口独立归档。

## 运行和预算

在数据仓库根目录运行以下命令，`PYTHONPATH` 指向分析仓库的 `runtime`。实采从环境变量 `THE_ODDS` 读取凭据。离线复算只读取已归档输入。

```bash
EXPERIMENT=workspace-updates/20261118-market-signals/team-markets
python -m data_sources.team_market_quotes --data-root . --verify-run "$EXPERIMENT/runs/20261118-first-eu"
python -m data_sources.team_market_quotes --data-root . --verify-run "$EXPERIMENT/runs/20261118-epl-us-pilot"
python -m data_sources.team_market_quotes --data-root . --discover eng.1 --days 4 --regions us --max-events 1 --match-markets --out "$EXPERIMENT/runs/daily-$(date -u +%F)-eng1"
```

滚动采集选最近已挂牌的比赛日，用现有工作流的每日一次窗口采一场。优先选同赛区此前没有成功采集的比赛。当天重复使用相同输出路径时，采集器先从原始字节和赛程重放完整结果，再返回原记录。每日部署同时保留胜平负和全场总球，单个区域每场至多 5 个配额单位。只请求球队相关三种市场时至多 3 个。免费赛事目录及 ESPN 赛程独立登记。首批巴甲六场共用 6 个单位。英超试点额外使用 `--match-markets`，五种市场共用 10 个单位。上述数字为各自正式运行的供应商回执；探测请求另行计费。
