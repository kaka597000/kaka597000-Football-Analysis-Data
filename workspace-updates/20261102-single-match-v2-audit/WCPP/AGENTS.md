**2026-10-15最新用户授权：后续所有分析默认冻结。** 发布前保存；当前/test独立并行，综合判断另轨，更新追加不覆盖，赛前/滚球分开。首次赛前版本为默认逐轨主评价版本，后续版本单列；不追认历史、不择优。完整规则见 /workspace/Football-Analysis/docs/analysis-freeze-policy.md。此条优先于下文旧的研究不冻结表述；冻结不等于模型晋级。

# WCPP 分析约定

- **2026-10-19输出要求**：每批分析结尾列最推荐TOP3赛事，含胜平负、实际盘口大小球及唯一综合第一比分、排序理由；当前/test继续独立，名单和排序随分析赛前冻结，复盘单列且不替代全批统计。不足三场不强凑。完整规范以 `/workspace/Football-Analysis/docs/user-primary-score-requirements.md` 的TOP3条款为准。

- **首要需求（2026-10-13重新确认）**：先读docs/user-primary-score-requirements.md。必须通过多方证据、比赛路径及候选比较选择唯一综合第一推荐比分；统计矩阵最大格子或市场最高选取率不能直接替代。统计基准、综合研究、正式推荐分开；缺关键证据写待定，人工选择另留方法版本/依据/反证且不伪造概率或改原矩阵。目标是未来真实命中率Top1≥70%、胜平负及实盘大小球≥80%，不是单场赋予相同概率。

- 中文，用户回应首句 HELLO BOSS，日期时间使用北京时间 UTC+8。
- 后续赛事分析必须读取 runtime/active-model.json，使用 /workspace/Football-Analysis/runtime/predict_active.py 输出同场两份独立结果：当前模型、test模型。
- 当前模型保留 WCPP-MAIN-1.2 基线与证据审查；test模型活动版本读注册表：当前WCPP-ML-0.1为DC＋LightGBM机器学习研究候选，旧WCPP-WEIGHTED-0.1版本及原预测保留。两者都不是恢复出的 Champion V21.5 源码。
- 预测及复盘分别标注模型名称、版本、数据截止时间、第一比分、胜平负和实际大小球线；不得赛后择优组合两个模型命中率。
- 两边同一场使用相同数据和盘口；真实未训练的xG、伤停、战意、体能模块保持未训练标记，不造权重或概率。正式冻结必须满足既有条件；时间冲突与已开场比赛不能冒充赛前。
- 复盘使用 runtime/v5/paired_review.py 分别统计并作同场对照，不同test版本不得混算命中率，保留各模型完整分母及待完赛场次；全赢、半赢、走盘、半输、全输分开。
- Champion V21.5、Selector4.1-RP1、Regime-MT-KL Shadow、永久λ不变，原500+200未重新预注册。
- 中国体育彩票官网及镜像禁止访问；澳客允许。五大联赛/J1/J2按用户要求实际调用5Dollar并记录失败和备用来源；密钥只读环境变量，禁止进入日志和文件。

- 新数据源客户端在 /workspace/Football-Analysis/runtime/data_sources/clients.py，football-data.org 使用 WCPP_FOOTBALL_DATA_API_KEY，API-Football直连使用 WCPP_API_FOOTBALL_KEY。状态及权限必须实际验证；无绑定不请求、不冒充已接通。实际优先读取新变量football_data、_apifootball，保留旧别名兼容；禁止将聊天密钥写进工具参数或文件。
- 活动ML-0.1已学习状态、主客、攻防和同联赛间隔特征；英超360场、西甲369场历史过程数据已匹配。xG、阵容、伤停、数学战意和完整体能数据仍无合格历史训练覆盖，不能声称这些权重已经学成。

- test输出附带WCPP-FIVE-REVIEW-0.1五角色证据资料，目前未调用五个外部LLM，不改概率。不得把W-5宣传的筛选/二分类准确率当第一比分命中率，不采用随机兜底或倒推回测。

- 2026-10-12继续训练ML-0.2：8451条历史、2370条xG，14组20组合时间选择；同段1238场仍150次Top1，未通过替换，保持ML-0.1活动。新候选仅在runtime/training-candidates.json，未来不得称为已切换。
- 较早API检查：Football_data_api和Apifootballcom_APIKEY已存在，旧允许域名不符并出现400/403；此为历史诊断。后续API-Football域名已经修正，不重复要求用户修改同一域名或填写密钥。

- 历史API实测（2026-10-12 15:22，北京时间）：football_data与dashboard_api_football均HTTP200。football-data.org当前2026英超赛程和五大积分榜已取得。API-Football为Free 100次/天；2026 fixtures拒绝并提示2022–2024，2024五大/J1/J2历史及首发/xG/伤停/事件样本已取得；赔率样本为空，未验证可用。此为当时结果。

- 历史API重测（2026-10-12 15:40–15:43，北京时间）：Apifootballcom_APIKEY允许域名已正确，但此绑定及dashboard_api_football请求/status均403，错误页为Cloudflare HTML，标准客户端重试仍403。当前连接BLOCKED，不能称当前已鉴权，也不推断密钥失效或订阅变化。记录：reports/openfootball-api-retest-20261012-154008/summary.json。
- 用户指定Open Football是https://open-football.org/zh（ZOXEXIVO/open-football），HTTP200的足球世界模拟器，含生成数据；与openfootball/football.json不同。仅作模拟研究参考，模拟赛果与生成球员资料禁止进入真实赛事Canonical和训练标签，按用户确认直接访问公开网页，无需API调用或密钥；不以未接API作为网页使用障碍。真实数据是否可用按具体页面内容与独立来源核验。

- 历史API-Football重测（2026-10-12 16:01，北京时间，运行配置35）：两种现有绑定/status均HTTP403，HTML含Cloudflare及Attention Required标记，server头为envoy。域名配置正确，当前仍BLOCKED；未验证最新订阅与赛事权限。记录：reports/api-football-retest-20261012-160112/summary.json。

- 历史API-Football重测（2026-10-12 16:07，北京时间）：环境重启完成，配置37凭证ready且网络enforced；两个绑定/status仍HTTP403，HTML含Cloudflare/Attention Required。远端连接仍BLOCKED，无法验证最新权限；记录reports/api-football-retest-20261012-160744/summary.json。

- API-Football原因排查（2026-10-12 16:10–16:11）：现有凭证/status为Cloudflare HTML403；无鉴权与单次合成无效密钥则为API JSON的Missing/Invalid key，football-data对照200。不得声称整个网络不通、出口IP整体被封或密钥必定无效；精确规则待服务方按CF-Ray查询。报告reports/api-football-diagnosis-20261012-161049/原因排查报告.md；支持说明草稿未发送。

- API-Football官方接入文档已读（2026-10-12 16:16）：api-sports.io/public/documentations/football-v3.yaml确认profile?access可限制调用方域名/IP，区别于云环境API目的域名；限速/突发可触发防火墙封禁。用户Access实际设置未读取（登录页挑战）。最小GET鉴权头仍Cloudflare403。解决方案reports/api-football-solution-20261012-161613/接入解决方案.md；Free恢复后建议全任务合计串行保守6次/分钟，HTML403停止继续请求，/status不计日配额不等于不受限速。不得把观测出口IP当完整固定范围。

- 历史API-Football重测（2026-10-12 19:46，北京时间）：现有dashboard_api_football单次/status仍Cloudflare HTML403，Ray a495dd08bbbee7fd-ORD；连接BLOCKED，未继续查赛事。记录reports/api-football-retest-20261012-194619/summary.json。

- 历史API-Football重测（2026-10-12 19:51，北京时间）：用户更新密钥后运行配置41，两绑定ready且网络enforced；串行间隔10秒分别/status均Cloudflare HTML403。未检查密钥内容以证明轮换，不称密钥无效；连接仍BLOCKED。记录reports/api-football-key-change-20261012-195119/summary.json。

- 历史API-Football重测（2026-10-12 19:55，北京时间）：运行配置42，Apifootballcom_APIKEY单次/status仍Cloudflare HTML403，Ray a495e9f3bbe09675-ORD；连接BLOCKED，未继续查赛事。记录reports/api-football-retest-20261012-195508/summary.json。

- 最新API-Football重测（2026-10-12 20:06–20:07，北京时间）：运行配置45，_apifootball变量/status鉴权HTTP200恢复，Free每日100次/分钟10次；2024曼联–富勒姆历史fixture可查，2026赛季HTTP200但plan错误明确拒绝并提示2022–2024。客户端默认兼容优先_apifootball，数据源10项测试通过，来源AVAILABLE_WITH_SCOPE_LIMITS。secret apifootball仍绑定dashboard域名，未验证该secret；不要求重复填密钥。记录reports/api-football-retest-20261012-200625/summary.json；未改模型或入库。

- 亚冠历史补充（2026-10-13）：统一库afc.champions共2383条/2189条90分钟合格，afc.cup594条/460合格；净新增2484条含赛程。分类表afc_source_classification及afc_training_90按competition/era/phase隔离旧亚冠、精英、旧杯、二级；不可混合训练。只有110条核实场地和双边过程，未知场地不能默认false。afc.cup由runtime/afc独立适配器目录加载，未修改会影响现有模型hash的registry.py。2015/早期档案有覆盖缺口，非全量完整认证；AFC独立双模型尚未训练注册，不声称历史扩库等于预测可用。报告reports/afc-history-20261013/亚冠历史补充报告_2026-10-13.md。冷门只有分歧/异常审查，未有独立验证分类器。

- 用户工作分工授权（2026-10-13）：以后数据收集、采集、查询由主代理自行安排gpt-6-luna子代理执行，无需逐次询问。委派时使用明确的来源范围、日期和共享配额，提供本文件路径及任务上下文；fork_turns=none时补齐中文/UTC+8、禁止中国体育彩票及镜像、允许澳客、只读环境密钥、继承代理与TLS等约束。Luna保存来源与时间证据到独立staging，主代理核验球队身份、90分钟口径、阶段/年代、盘口及重复记录后接入模型或批准统一库写入；模型训练、选择和最终结论由主代理负责。模型可用性或来源阻断照实报告。

- 独立冷门分类器（2026-10-13）：WCPP-UPSET-0.1已以ACTIVE_SHADOW_RESEARCH登记在runtime/upset-classifier.json，默认predict_active.py独立upset_classifier字段。九国内联赛分别训练，全部未通过市场基准门槛；只能展示未验证研究概率，禁止可信行动警报或主比分重排。亚冠未训练、无核实1X2报价时ABSTAIN。独立复盘热门输球与不胜，不并入Primary，不追认旧预测。报告models/upset-20261013/冷门分类器初版报告.md。

- MATLAB（2026-10-13）：R2026a Update5＋Statistics and Machine Learning Toolbox已安装tools/MATLAB/R2026a，Engine26.1在tools/matlab-python导入通过。实际批处理启动退出1，License-1.2；Engine启动同样License Error。尚不能训练，禁止声称授权已完成。setup/matlab/install.sh可复用且重复验证，smoke_train.m待授权执行；环境配置草稿已保存未发布。不得自行申请试用/购买/登录或输出许可内容。

- Python主架构（2026-10-13）：默认纯Python，不再要求MATLAB或许可证；MATLAB可选安装保留。setup/python/install.sh和环境草稿install_script/start_skill已更新未发布；CPU PyTorch2.14.1+cpu、XGBoostCPU3.4.1、CatBoost1.2.10、Optuna5.0等依赖已安装并实际检查。CUDA不可用；PPO只完成CartPole能力测试，不称足球RL训练。
- 冷门0.2候选（2026-10-13）：九队列分别训练86项特征，20077原病例不变，过程20076覆盖；过去射门/射正/角球/牌数、同主客、对手Elo、同联赛赛程密度等均严格先前日期。fit区未见当前CSV xG特征被屏蔽；最后核查补1900旧英超research_xg，提供方混合尺度/first_known_at缺失，独立字段纳入候选训练但英超最终仍选市场基准，不声称统一xG权重已验证；阵容伤停战意完整体能仍缺快照。0.2登记runtime/upset-candidates.json，predict_active.py独立upset_candidate；0.1与当前/test登记哈希不变。西甲只有小开发改善，所有误差差值CI包含零；全样本Brier0.12743仍弱于市场0.12615。禁止晋级或可信报警。29项测试通过，报告reports/python-upset-20261013/Python架构与冷门模型优化报告.md；最终工件models/upset-0.2-20261013-r4，不用前三个开发工件。
- 后续分析采集及验证：Luna按可用T-24h及首发发布窗口保存来源时间到独立staging/snapshots；主代理核验，不声称已部署定时爬虫。runtime/research/snapshots.py拒绝赛后/未来来源和凭证字段。真实双模型预测有实际矩阵与同输入后用runtime/research/prospective.py record保存独立研究台账，review保留待完赛和冷门拒绝项、版本/工件分组；不冒充正式Primary冻结、不改500+200。旧测试只开发诊断，未来未见样本才验证，最高指标仍Primary Top1。

- 欧冠队列（2026-10-13）：活动登记WCPP-DUAL-3共15条，原14路由及工件哈希不改；新cohort=uefa.champions:NEW_FORMAT:league_phase，competition=uefa.champions，stage=NEW_FORMAT:league_phase。306场（24/25 144、25/26 144、26/27已完18）90分钟/场地逐summary核实。当前MAIN1.2 anchor，test=WCPP-ML-UCL-0.1独立分派；新版本保留真实射正/控球、射偏缺失，不改原ML0.1。81病例开发Top1当前4/81=4.94%、test8/81=9.88%，仅研究非前瞻；绝不称达到70%。实际Arsenal-Lille未来事件401915417默认入口两份51×51矩阵验证，OBSERVE，无完整综合赛前分析或正式冻结；报价hasOdds=false矛盾未施加total_quote。26检查通过（6欧冠/11默认与旁路/9台账）。资格旧组赛/淘汰按era phase leg分离，未训练状态见runtime/ucl-queues.json，不借新GL概率。冷门无UCL队列ABSTAIN。报告reports/ucl-onboarding-20261013/欧冠队列接入报告_2026-10-13.md。
- 欧冠今晚日期（2026-10-13查询）：ESPN/football-data.org UTC10/13九场为北京时间10/14凌晨00:45/03:00；UTC10/14另九场为10/15凌晨。官方UEFAwidget未读到逐场行，澳客“未开售”overlay语义和列表时间未独立核实，销售状态UNKNOWN。后续分析由Luna重新查实际竞彩名单、首发与真实盘口，不把源字段矛盾或字面HTML当确认；队列注册不等于盘口/首发已齐全。统一库与原Canonical本次不改。研究台账MAIN1.2缺可选input_hash时计算独立保存，矩阵及同输入校验仍保留。

- 新赔率源实测（2026-10-13，配置56）：The Odds API变量manyzhishu_theodds_sports，官方https://the-odds-api.com/liveapi/guides/v4/，base https://api.the-odds-api.com/v4；实际目录欧冠key soccer_uefa_champs_league（soccer_uefa_champs=404无扣额）。eu+h2h,totals,spreads一次200返回18场，耗3units，余497；核实机构/赔率/总球线/时间，spreads不直接冒称亚盘。InferSports变量yapan_infersports，官方base https://api.infersports.dev Bearer，正确markets=1x2,asian_handicap,totals（total会400）。修复后实际赔率200、亚洲让球和总球字段可读，但stale=true，价格仍10/02，health degraded/feed_live=false，不得用于当前赛前盘口，只存staging。两者history权限未测试。报告reports/odds-connectivity-20261013/官方接入核查.md，状态runtime/odds-sources.json；未改模型参数或概率、未写赛事库。未来盘口采集可由Luna调用已验证TheOdds官方端点按batch复用，每次保存实际bookmaker/market/same-event两边line/source query及quote时间/额度；不得把API查询密钥或Bearer写入日志、URL证据、报告。

- 亚洲盘口公开网页来源（2026-10-13用户指定并核查）：https://www.asianodds.org/ 提供BetInAsia单来源1X2/亚洲让球/大小球开盘与当前价格；https://odds.directory/en/football/markets/asian-handicap/ 有实际聚合盘口，赛事页含1X2/大小球及开盘/当前/高低点，但机构未知；https://www.oddsportal.com/ 页面可达，本轮报价表未核实。上述公开网页用途无需用户APIKey，不代表所有功能免费或已自动接入；每次由Luna重查比赛身份、机构、盘口、报价时间与可访问性。开盘与当前差值不等于完整逐时历史，赔率变化不等于资金流量或卖分证据；三站均未核实成交量/投注额/投注比例。仅作市场末端校验与有界重排，不改Primary、模型参数或冻结规则。证据reports/market-flow-reference-20261013/官网参考核查.md；引用旧对话全文未读，不声称旧资金模型已审阅或部署。

- OFM引用总结已完整读取用户粘贴版本（2026-10-13）：保存reports/market-flow-reference-20261013/用户提供_OFM引用对话总结.txt及OFM引用方案评估.md。可借鉴独立盘口旁路、真实时间快照、前推验证；尚未构建/训练/启用OFM，不视为第三个活动模型。赔率变化只作代理，成交量模块无数据则不可用；InferSports陈旧不可主源，API-Football当前季盘口权限未证实，TheOdds spreads不冒称亚盘、历史权限未测。原对话外链全文仍未读，不与已读粘贴内容混淆。接入主比分选择器必须未来同样本证明Primary Top1增益，不改原模型及冻结规则。

- 综合重新分析留档（2026-10-13）：reports/comprehensive-reanalysis-20261013/综合第一比分重新分析.md已保存9场，原数值模型9对矩阵和人工研究0.1分别留档；人工当前/test每侧8初稿、斯托克1待定，非正式Primary。人工首选不等于原primary，未来复盘不得混算原MAIN/ML、人工方法或首发前后版本。初稿升级需新记录，保留此次完整分母与未知字段；不称人工权重已训练或概率已校准。

- 2026-10-14昨日复盘：reports/review-20261014/昨日赛事完整复盘.md，12场90分钟完赛；8欧冠双源，其余4场ESPN单源。22:18人工综合两侧Top1均0/8，WDL当前4/8/test3/8，OU均2全赢1走盘5全输；原欧冠统计基准Top1也0/8，WDL5/8、4/8。01:16两场子集单独留档，AFC两版独立，Stoke待定保留；无人工改善证明，不可包装为70%或自动升比分/追认冻结。失误候选标签与未来验证要求见报告，原参数未改，结果尚未写训练库。

- **2026-10-15来源使用要求**：后续分析必须实际核查近期xG/xGA及最新伤停/停赛；按覆盖使用Understat、Transfermarkt、StatsBomb开放数据及已授权备用源。逐场保存来源/时间/窗口/缺项及是否进入判断或数值模型，禁止仅登记网站就称已使用。执行细则见docs/user-primary-score-requirements.md的2026-10-15补充。

- **2026-10-20执行约束**：分析前读 `/workspace/Football-Analysis/docs/score-distribution-adjustment.md`。默认入口已附单队/总球审计；综合冻结必须引用实际双模型冻结并填写比分候选、零球vs一球反证及实盘大小球独立理由。缺比较不进入新TOP3，但全批仍如实冻结；不强制加球。校准C1/C2未过门槛，仅M2独立研究，当前/test未晋级。

- **2026-10-21复盘约定**：比分、胜平负与大小球分母独立；比分待定但已明确方向仍结算方向，观望和候选不得补命中。test欧冠/英冠版本分列。乌龙球员队与受益队使用 `runtime/research/review_events.py` 校验分数变化及shotmap球队ID，不能直接取isHome；新增8测试及真实42球验证通过。复盘证据见 `/workspace/WCPP/reports/review-20261021-0813/赛事复盘与调整决定.md`；本次数值参数不变，未宣称训练或晋级。

- **2026-11-02用户最新规则**：分析重点关注同机构同盘口、有真实报价时间的水位变化，降低对官方首发的依赖。首发未公布时用可靠伤停和轮换情景继续分析，明确未知；重大未解决人员风险仍待定。不得编造水位历史、百分比权重或资金流。新版规则及实现见已推送源码docs/market-and-lineup-policy.md，保留原模型数值及旧冻结。

- **2026-11-02单场完整模块/V2阶段一**：后续分析按新版默认入口match_analysis覆盖八类模块，数据/训练/执行状态分别列，缺项不造数。源码主分支05b0b44已修复哈希兼容并统一模块；独立V2 Test分支v2-test/audit-20261102已完成阶段一审计，动态融合/球员影响与新校准尚未训练，活动权重不变。优先补历史时点与来源身份映射，再做同场嵌套时间验证；见docs/v2-roadmap.md。
