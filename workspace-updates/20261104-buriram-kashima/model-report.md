# 单场赛事完整模块分析

赛事ID：espn:401912613；截止时间：2026-11-04T11:55:28.860384+00:00

模块有输出不代表数据齐全、五名外部代理已执行、状态模拟已训练或准确率提高

## 历史进失球、球队攻防、主客场

补充证据状态：unknown
缺少该模块的本场可核查证据

- current：WCPP-AFC-ELITE-CURRENT-CONSTANT-0.1；训练比赛截止 2026-10-12
  - home：均值 1.700483091786754；P0 0.18259529245626724；P≥2 0.5069045000818677；P≥3 0.24290432368917095；区间 {'lower': 0, 'upper': 3, 'nominal_coverage': 0.8, 'width': 3, 'lower_quantile': 0.09999999999999998, 'upper_quantile': 0.9, 'matrix_coverage': 0.9067382883723899, 'method': 'EQUAL_TAIL_INTEGER_INVERSE_CDF_INCLUSIVE'}
  - away：均值 1.2125603864734282；P0 0.29743475574345296；P≥2 0.34190764188163536；P≥3 0.1232480810214836；区间 {'lower': 0, 'upper': 3, 'nominal_coverage': 0.8, 'width': 3, 'lower_quantile': 0.09999999999999998, 'upper_quantile': 0.9, 'matrix_coverage': 0.9651312261860818, 'method': 'EQUAL_TAIL_INTEGER_INVERSE_CDF_INCLUSIVE'}
- test：WCPP-AFC-ELITE-TEST-POISSON-0.1；训练比赛截止 2026-10-12
  - home：均值 1.6473144493420964；P0 0.19256636154898382；P≥2 0.4902162886140648；P≥3 0.22893792662979368；区间 {'lower': 0, 'upper': 3, 'nominal_coverage': 0.8, 'width': 3, 'lower_quantile': 0.09999999999999998, 'upper_quantile': 0.9, 'matrix_coverage': 0.9145312803692822, 'method': 'EQUAL_TAIL_INTEGER_INVERSE_CDF_INCLUSIVE'}
  - away：均值 1.4758148533485052；P0 0.228592381865718；P≥2 0.43404758561452866；P≥3 0.18510711215512546；区间 {'lower': 0, 'upper': 3, 'nominal_coverage': 0.8, 'width': 3, 'lower_quantile': 0.09999999999999998, 'upper_quantile': 0.9, 'matrix_coverage': 0.9373562372885448, 'method': 'EQUAL_TAIL_INTEGER_INVERSE_CDF_INCLUSIVE'}
数值权重：未在本报告另行指定；数据缺失不填零。

## 近期状态与比赛间隔

补充证据状态：unknown
缺少该模块的本场可核查证据

数值权重：未在本报告另行指定；数据缺失不填零。

## 射门、射正、控球

补充证据状态：unknown
缺少该模块的本场可核查证据

工件记录的训练覆盖行数：{"current": null, "test": null}；工件未登记的覆盖保持未知；0表示本工件无登记合格训练行，不表示未采集任何资料
数值权重：未在本报告另行指定；数据缺失不填零。

## xG / xGA

补充证据状态：unknown
缺少该模块的本场可核查证据

工件记录的训练覆盖行数：{"current": null, "test": null}；工件未登记的覆盖保持未知；0表示本工件无登记合格训练行，不表示未采集任何资料
数值权重：未在本报告另行指定；数据缺失不填零。

## 阵容、伤停、停赛

补充证据状态：unknown
缺少该模块的本场可核查证据

数值权重：未在本报告另行指定；数据缺失不填零。

## 战意、旅行、完整赛程负荷

补充证据状态：unknown
缺少该模块的本场可核查证据

数值权重：未在本报告另行指定；数据缺失不填零。

## 盘口、赔率与水位变化

补充证据状态：unknown
缺少该模块的本场可核查证据

同机构同盘口价格比较：{"status": "NO_SNAPSHOTS", "comparisons": [], "rejected_snapshots": 0, "prediction_modified": false, "money_flow_inferred": false}
数值权重：未在本报告另行指定；数据缺失不填零。

## 五角色审查、分钟模拟、冷门旁路

补充证据状态：unknown
缺少该模块的本场可核查证据

- five_role_review：fail_closed_no_random_or_default_agent_probability
  外部调用次数：0；独立代理次数：0
- upset_classifier：ABSTAIN_NO_TRAINED_COHORT
- upset_candidate：ABSTAIN_NO_TRAINED_COHORT
- selection_experiment：EXPERIMENTAL
- minute_simulation：NOT_CONFIGURED
数值权重：未在本报告另行指定；数据缺失不填零。

## 综合选分检查

- 逐队比较0/1/2+进球路径
- 比较至少两个比分候选及反证
- 重点核查同机构同盘口水位变化与升降盘
- 胜平负、第一比分和实际大小球分别判断
- 引用双模型冻结，综合判断独立追加；缺数据如实标记

本报告是证据与执行状态报告，不自动将统计比分改名为综合第一推荐；综合结论须独立保存冻结。
