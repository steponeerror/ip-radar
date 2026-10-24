# STANDARD.md — 情报运营 agent 开发典章 v0(四层)

裁定:ADR 0008(2026-10-24 用户确认,嵌套 docs 仓);研究底座:notes/ops-agent-golden-standard-research-2026-10-24.md(40 卡,只采 2026 学术+工业源);spec:#180(总纲)/#181(本文件 v0)。

**总律:挂不上验证手段的条目只能称建议,不得称标准**——反面教材=锚门死件(anchors.py 明文「must stay clean」却零生产调用面,2026-10-24 事故复盘)。本文件的机检面=ops/agent/standard-check.mjs(零依赖纯 node;挂 selftest 链 §13):每条条文的门挂点指向的文件/测试必须真实存在,死锚/空挂点/伪条目=非零退出;无门挂点条目必须以「类:建议」显式标类落建议区(§五)。

条文编号:E=评估回归维,D=开发过程维,G=金标层条目;条文五件套=编号+主张+原语组成+门挂点+判例链;原语组成必须是 §一 表内词(组合不出原语=伪条目)。

## 一、原语层(22 词)

状态语义:**已有**=机制在场且接线活;**半缺**=部分在场;**缺**=无。半缺 9+缺 3 即补课清单(ADR 0008 后果节),逐项落 §五建议区。22=v0 冻结闭集——增删原语=STANDARD 版本变更(词汇表律:铸词同 PR 录入 GLOSSARY)。

| # | 原语 | 2026 出处(研究底座) | 内部状态 | 内部锚 / 补课 |
|---|---|---|---|---|
| P1 | 信封纪律 | FlowGuard 2026-07;EpiSEM-Bench 2026-10 | 已有 | ops/agent/tools.mjs(classifyChannelError 四码) |
| P2 | 状态机骨架 | Gartner 2026-10;swarm tax 2026-05 | 已有 | ops/agent/pipeline.mjs(HEALTH_PIPELINE,模型只在三步) |
| P3 | 谱系去重 | swarm tax 2026-05(算力对齐同构);对撞表独有列 | 已有 | backend/ipdb/_logodds.py(dedup_lineage) |
| P4 | 回放闸门 | Braintrust 2026-09;promptfoo 2026-10 | 已有 | ops/agent/golden(字节等价)+PROBE 位等价判例(#169) |
| P5 | 三层职责线 | Microsoft 2026-06;ACM Queue 2026-10 | 已有 | ops/agent/DESIGN.md(ADR 0007) |
| P6 | 工具白名单 | MCP-ITP 2026-01;NSA CSI 2026-06;MCP spec 2026-07 | 已有 | ops/agent/tools.mjs(MEASUREMENT_TOOLS 闭集) |
| P7 | 轮内预算步前检查 | Latentism 2026-10(调用前检查印证) | 已有 | ops/agent/pipeline.mjs(budget_truncate) |
| P8 | 阶段门 | promptfoo 2026-10(CI fail-PR) | 已有 | ops/agent/pipeline/gates.mjs(gates.json 留痕) |
| P9 | 判例升格通道 | Agentic Auditing 2026-10(人验签核平行;外部无直接对应) | 已有 | ops/agent/promote-detect.mjs |
| P10 | 金标集 | Anthropic 2026-01(回归语义);promptfoo 2026-10(golden 数据集) | 已有 | ops/agent/golden/cases.json(faux 零花费) |
| P11 | 回归门≈100% | Anthropic 2026-01-09(回归/能力分立) | 半缺 | 锚集+ops 轮巡检已接线(#182 ANCHOR_SWEEP/G_ANCHOR_SWEEP);补课=生产 cron 灰度开启+223.5.5.5 残留(#188) |
| P12 | 安静失败探针 | IEEE Spectrum 2026-04 | 半缺 | 判例=8.8.8.8 门不响;接线已落(#182);补课=生产 cron 灰度开启 |
| P13 | 发现固化 | Agentic Auditing 2026-10-22 | 半缺 | 首批金标=§四;当天固化+人验签核流程门未建制 |
| P14 | 能力轨北星 | Anthropic 2026-01;Braintrust 2026-02(双面评测) | 半缺 | 定稿已落=E-5+月轮 northstar 观测件(#185);剩余=跨月趋势基线累积(首环比待第二轮月轮) |
| P15 | 预扣结算 | Latentism 2026-10-05(reserve-then-settle) | 半缺 | 轮内步前在;补课=月度 kill switch |
| P16 | 跨轮熔断 | Agent Internals 2026-09(通道/工具粒度) | 半缺 | 轮内 transient≤1 在;跨轮态缺 |
| P17 | 对照对打 | Braintrust 2026-09-26(quality/latency/cost) | 半缺 | 字节等价对拍在;三轴数值门缺 |
| P18 | EDD开发环 | web.dev 2026-01-29(OpenAI EDD 日期 unknown 不计) | 半缺 | selftest/TDD 在;灰度影子轮 N≥3 门待验收 |
| P19 | 弃权校准 | Cost-Aware Abstention 2026-10(AUROC/ECE 分立) | 半缺 | 弃权语义在(无证据即无话);校准度量缺 |
| P20 | OTel投影 | OTel GenAI semconv 2026-05→10(独立仓) | 缺 | 轮信封外发投影;另票(ADR 0008 决策5) |
| P21 | 跨轮级评测 | LangChain 2026-06-23(Run/Trace/Thread) | 缺 | 跨轮 Trace/Thread 评测缺 |
| P22 | 失败归因图 | DeFA 2026-10-01(依赖图归因) | 缺 | 失败传播图缺 |

## 二、条文层(首批两维)

首批两维自研究底座三向对撞表提炼(内部判例×外部印证,无一条内部判例被推翻)。

### 评估回归维(E)

#### E-1 EDD 开发环(头条)
- 主张:先写失败评测,再动 agent——环=失败评测先行→spec 对齐→实现→对照对打(quality/latency/cost 三轴)→回归门≈100%→灰度影子轮 N≥3→发现固化人验;已挂面=回归门(golden)+伞面(selftest)+CI,三轴对打与影子轮门=在建腿(P17/P18,影子轮判例 #176-178),挂上门即转正
- 原语组成:EDD开发环;金标集;对照对打;回归门≈100%;发现固化
- 门挂点:ops/agent/golden/run-golden.mjs;ops/agent/selftest.sh;.github/workflows/ci.yml;backend/ipdb/_eval/anchors.py
- 判例链:web.dev 2026-01-29(EDD=TDD 的 AI 同构);Braintrust 2026-09-26(prompt CI/CD);Anthropic 2026-01-09(回归≈100%);2026-10-24 8.8.8.8/114DNS 事故(ADR 0008);#176-178 三轮影子复验判例

#### E-2 双轨分立
- 主张:回归轨(已知答案金标+行为探针,≈100% 通过才放行,持 CI+运营轮巡检)与能力轨(北星=整体情报更准,爬坡观测,不持门)阈值语义不同,不得互相原谅
- 原语组成:回归门≈100%;能力轨北星;金标集
- 门挂点:ops/agent/golden/cases.json;backend/ipdb/_eval/anchors.py
- 判例链:Anthropic 2026-01-09(能力评测刻意低通过率起步爬坡 vs 回归要求≈100%);对撞表「北星=能力轨,锚=回归轨,阈值语义不同」

#### E-3 安静失败探针
- 主张:监控面板全绿不构成行为正确的证据——活路径已知答案查询(行为探针)必须挂生产查询路径巡检,失败=finding 不持门、自动开 issue 人裁;接线已落(#182:ops 轮 ANCHOR_SWEEP 步+G_ANCHOR_SWEEP 门在案,生产查询路径逐锚读数);启用语义=生产 cron 随 OPS_PIPELINE 灰度(接线≠已启用,部署后首个巡检轮起运行面转正)
- 原语组成:安静失败探针;回归门≈100%
- 门挂点:backend/ipdb/_eval/anchors.py;ops/agent/pipeline/steps.mjs#ANCHOR_SWEEP;ops/agent/pipeline/gates.mjs#G_ANCHOR_SWEEP;notes/ops-agent-golden-standard-research-2026-10-24.md
- 判例链:IEEE Spectrum 2026-04(安静失败=标准可观测性抓不住语义级退化);2026-10-24 锚门死件复盘(ADR 0008:零生产调用面)

#### E-4 发现固化
- 主张:生产事故与运营 finding 当天固化为回归轨金标,agent 提名、人验签核(人裁终局);金标增补落锚集/金标集并过本核对器,禁「就事论事修个案」
- 原语组成:发现固化;金标集;回归门≈100%
- 门挂点:ops/agent/golden/cases.json;backend/ipdb/_eval/anchors.py
- 判例链:Agentic Auditing 2026-10-22(发现→可执行测试→人验,$2-3/轮);ADR 0008 决策3;首批金标=§四 G-1/G-2

#### E-5 能力轨北星(只观测不持门)
- 主张:北星=「整体情报更准」的方向性指标,v0 可计算代理两腿=锚集全绿率(19 锚金标投影,读月轮 anchors-*.json 工件)+谱系去重后 corroborated 精度(OK 层 k≥2 命中剔除派生簇独证,114DNS 假印证面折减)月环比;代理可换(换代理≠本典章版本变更),记录落 eval 月轮 readout 腿工件(northstar-*.json+monthly-*.md 北星行)——只观测不持门:零阈值、零 CI 面、不拦月轮退出码,与回归轨(E-2)阈值语义分立不得互相原谅
- 原语组成:能力轨北星;谱系去重;金标集
- 门挂点:backend/ipdb/_eval/monthly.py#render_northstar;backend/tests/eval/test_eval_northstar.py;scripts/monthly_eval.sh
- 判例链:Anthropic 2026-01-09(能力评测低通过率起步爬坡 vs 回归≈100%);Braintrust 2026-02(双面评测);ADR 0008 决策2(双轨分立);#185

### 开发过程维(D)

#### D-1 对照对打门
- 主张:候选与生产变更在固定数据集上对照对打,过 release criteria 才放行;字节等价是下限不是上限——评分实现改动必过回放闸门(融合层位等价对照)
- 原语组成:回放闸门;对照对打
- 门挂点:ops/agent/golden/run-golden.mjs;ops/agent/selftest-t4.mjs#golden
- 判例链:Braintrust 2026-09-26;promptfoo 2026-10-02(golden 数据集+断言不达标 fail PR);PROBE 位等价判例(PR #169)

#### D-2 最简架构默认
- 主张:单 agent 优化穷尽前不建多 agent;宿主=状态机骨架,模型只在 TRIAGE/DEEP/SYNTH 三步,门全机检、步可 replay、职责线三层(宿主只编排/提示词只判断/脚本只测量)
- 原语组成:状态机骨架;三层职责线
- 门挂点:ops/agent/pipeline.mjs#HEALTH_PIPELINE;ops/agent/DESIGN.md
- 判例链:Gartner 2026-10-07(When to Build a Multiagent System);swarm tax 2026-05-17(同 thinking-token 预算下多 agent 优势消失);arXiv 2609.19759 2026-09(When More Is Less);ADR 0007(C 骨架终裁)

#### D-3 工具白名单+证据最小权
- 主张:测量面=闭集白名单,发现产物不进谓词硬门数字(evidence 语义门不因发现通道放宽);模型可调工具最小权——借道合法高权工具作恶是实证攻击面(MCP-ITP 84.2% ASR/0.3% 检出)
- 原语组成:工具白名单
- 门挂点:ops/agent/tools.mjs#MEASUREMENT_TOOLS
- 判例链:MCP-ITP 2026-01(隐式投毒);NSA CSI 2026-06;MCP Specification 2026-07-28;PR #179 判例(发现通道三件不入 MEASUREMENT_TOOLS)

#### D-4 谱系去重
- 主张:回声不是印证——同源重复与谱系派生不得计两次;聚合器自述 derived 入谱系簇,评分变更过回放闸门(corroborated 语义复核),巡检披露「印证对聚合器占比」
- 原语组成:谱系去重
- 门挂点:backend/ipdb/_logodds.py#dedup_lineage
- 判例链:swarm tax 2026-05(变量不对齐的优势=伪影);114DNS 事故(cps_collected_iocs+ziyadnz 聚合器假印证,ADR 0008);对撞表独有列(工业 eval 框架均不建模源谱系)

#### D-5 预扣结算
- 主张:预算在动作前检查(reserve 后动作、settle 对账),事后 dashboard 不构成预算控制;轮内=步前检查实报累计,跨轮熔断与月度 kill switch=补课腿(P15/P16)
- 原语组成:轮内预算步前检查;预扣结算;跨轮熔断
- 门挂点:ops/agent/pipeline.mjs#budget_truncate
- 判例链:Latentism 2026-10-05(预算帽调用前检查);对撞表「若实现是事后记账则被推翻(待核)→ 轮内已核=步前检查实报」(2026-10-24 预算核验判例)

#### D-6 信封纪律
- 主张:失败不编造——通道失败走四码结构化分类(每码自带下一步合法动作),无证据≠清白,弃权/缺口不冒充零命中;wire 漂移哨钉语法面
- 原语组成:信封纪律;弃权校准
- 门挂点:ops/agent/tools.mjs#classifyChannelError;ops/agent/error-codes.mjs
- 判例链:FlowGuard 2026-07(语义信号≠证据);EpiSEM-Bench 2026-10(每句都真也可能不安全);判例 2026-10-24-discover-dual-channel-dead;PR #179 wire 漂移哨(非空无标记文本归 io_error 不冒充零命中)

## 三、门挂点层

挂口族注册表(条文门挂点必须落在族内载体上;挂点路径一律主仓相对,嵌套 docs 仓文件禁作挂点——CI checkout 无 docs/;`#锚词` fragment 须在文件文本内;空挂点/死锚=核对器非零退出):

| 挂口族 | 载体 | 核对方式 |
|---|---|---|
| CI 腿 | .github/workflows/ci.yml(frontend job:golden+selftest 步) | CI 三腿绿(paths-ignore **.md 不触发,故标准变更必伴代码面) |
| selftest 伞 | ops/agent/selftest.sh(§13=本核对器+单测) | bash selftest.sh 全绿 |
| golden 回归 | ops/agent/golden/run-golden.mjs + golden/cases.json | faux 全绿零 API 花费 |
| ops 轮门 | backend/ipdb/_eval/anchors.py + ops/agent/pipeline/steps.mjs#ANCHOR_SWEEP(接线已落=#182) | 每轮全锚巡检(G_ANCHOR_SWEEP 门);启用=生产 cron 随 OPS_PIPELINE 灰度 |

## 四、金标层(首批)

回归语料=已知答案金标;期望全对≈100% 才放行(哲学:证据永不灭失——金标判例可回算)。

#### G-1 公共解析器 clean 锚
- 主张:8.8.8.8/8.8.4.4/1.1.1.1/1.0.0.1/9.9.9.9/208.67.222.222 判 clean——任何指控显形=回归门红,回滚
- 原语组成:回归门≈100%;金标集;安静失败探针
- 门挂点:backend/ipdb/_eval/anchors.py
- 判例链:2026-10-24 8.8.8.8 事故(myip_ms 单源 rel 0.55 打惡意55;ADR 0008);anchors.py「must stay clean, any failure = rollback」

#### G-2 114.114.114.114 clean(判例已固化,ops 轮巡检已接线)
- 主张:114DNS 公共解析器判 clean;验证面=判例固化在场核+anchors.py 扩行已落(#182:19 员含 114.114.114.114/223.5.5.5/9.9.9.4)+ops 轮 ANCHOR_SWEEP 巡检在案;启用语义=生产 cron 随 OPS_PIPELINE 灰度
- 原语组成:发现固化;回归门≈100%
- 门挂点:backend/ipdb/_eval/anchors.py#ANCHORS;ops/agent/pipeline/steps.mjs#ANCHOR_SWEEP;notes/ops-agent-golden-standard-research-2026-10-24.md
- 判例链:2026-10-24 114DNS 事故(cps_collected_iocs+ziyadnz 聚合器假印证打黑名單;ADR 0008);#182 接线(锚集扩公共解析器 16→19)

#### G-3 既有 reserved/tor/hosting 锚
- 主张:保留段短路(10.0.0.1/127.0.0.1/192.168.1.1/172.16.0.1)、tor 出口 is_tor=true(季度刷新留痕)、云边缘 is_hosting=true(52.95.116.115/20.36.253.52/34.64.121.1)
- 原语组成:回归门≈100%;金标集
- 门挂点:backend/ipdb/_eval/anchors.py
- 判例链:anchors.py 锚集(spec §5.2);2026-10-14 tor 季度刷新判例(96.44.159.202→185.220.101.34,双源口径一致)

## 五、建议区(无门挂点,显式标类)

建议=挂不上验证手段的条目形态;显式标「类:建议」,永不称条文;挂上门挂点即升格(升格=改本文件并过核对器)。

- 类:建议 三轴数值对打门(quality/latency/cost release criteria;P17)——E-1 在建腿,建制后转正
- 类:建议 灰度影子轮 N≥3 门(P18)——#176-178 影子轮判例在案,灰度验收门三件待做
- 类:建议 月度预算 kill switch(P15 缺面)——跨月熔断另票
- 类:建议 跨轮熔断器(P16)——按通道/工具粒度装
- 类:建议 跨轮级评测 Run/Trace/Thread 三级补全(P21)
- 类:建议 弃权单独校准 AUROC/ECE 分立(P19)
- 类:建议 失败归因图 DeFA 式(P22)——多步误差分离定位
- 类:建议 OTel GenAI semconv 轮信封外发投影(P20)——内部契约不动
- 类:建议 人审预算化(Selective Auditing 2026-10-22:最小化人审频率+未审错误率≤阈值)
- 类:建议 基准效度检查单(RecoAtlas 2026-05:性能随模型能力/算力/工具质量扩展)——golden 基准设计依据
- 类:建议 结构化响应协议压漂移(Echoing 2026-03:身份漂移 70%→9%)——多 agent 会话面扩展时启用
- 类:建议 锚巡检生产启用(#182 已接线:ops 轮 ANCHOR_SWEEP 跑 anchors 全集,失败=finding 自动开 issue needs-triage,E-3/G-2 运行面已转正)——剩余=部署后生产 cron 随 OPS_PIPELINE 灰度开启
