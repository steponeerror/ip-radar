# 情报运营 agent 开发黄金标准 — 外部研究底座(2026-10-24)

研究先行裁定(用户 2026-10-24):只采 2026 发表/发布;旧文只作背景不采信;学术+工业双轨。
方法:planning-queries 三竞标(glm-5.3-flash 独立)→ 评审(glm-5.3 四维锚点,C 骨架 8 分胜出)→ 融合执行。
用途:黄金标准条目的外部校验与补齐;冲突点带回 grill frontier 裁决。

## 学术腿(arXiv,已核 published_date 均为 2026)

### ④ 安全(最厚,5 源)

| id | 日期 | 主张 | 对撞点(→标准维度) |
|---|---|---|---|
| 2508.14925v2 (MCPTox, AAAI) | 首发2025-08, v2 2026-09 | 45 真实 MCP 服务器/353 工具/1348 毒例基准;o1-mini ASR 72.8%,**更能干的模型更易被投毒**(利用其指令遵循),拒绝率<3% | →安全:工具面投毒是 2026 实证基线;反直觉:模型能力≠安全 |
| 2607.14754 (FlowGuard) | 2026-07 | MCP 扫描器语义信号≠证据(疑似凭据可能只是占位符);运行时证据裁决,F1 0.879-0.942,五类漏洞 1880 例 | →安全+评估:与「无证据即无话」同构;检测结论须运行时证据落地 |
| 2603.22489 (STRIDE/DREAD) | 2026-03 | MCP 五组件威胁建模;tool poisoning=最普遍客户端漏洞;7 大客户端静态校验不足;多层防御=静态元数据分析+决策路径追踪+行为异常检测+用户透明 | →安全:威胁建模框架可引 |
| 2601.07395 (MCP-ITP) | 2026-01 | 隐式投毒:有毒工具不被调用,诱导 agent 调合法高权工具作恶;84.2% ASR / 0.3% 检出 | →安全:最小权工具面是实证必需,非锦上添花 |
| 2610.25372 (SEAL) | 2026-10 | 持久投毒跨多轮场景仍有效 | →安全:多轮运营轮场景的攻击面 |

### ① 评估与基准(4 源)

| id | 日期 | 主张 | 对撞点 |
|---|---|---|---|
| 2610.31650 (EpiSEM-Bench) | 2026-10-22 | 300 对安全/不安全任务;**工具响应省略关键事实→agent 执行被禁动作**(每句都真也可能不安全);恢复访问≠主动取证 | →评估:证据缺失下的安全评估范式;印证信封纪律 |
| 2605.18805 (RecoAtlas) | 2026-05 | 「有意义 agentic 基准」效度属性:性能随模型能力/测试算力扩展、随工具质量升降、语义合理性≠行为效用 | →评估:基准效度检查单(golden 基准设计依据) |
| 2610.31657 (Cost-Aware Abstention) | 2026-10-22 | 成本感知弃权:校准集选冻结策略再一次性测;正确性 AUROC 与 ECE 分开报 | →评估:弃权与校准分离度量 |
| 2610.31636 (Agentic Auditing) | 2026-10-22 | agent 当审计员:只读预算 API,$2-3/轮,**发现→编译成可执行测试→人验**;测试套件 0.7s 全量扫描 vs $12k-90k LLM 分类 | →运营:「发现必须固化为测试」实证(与「事故即金标」同构) |

### ③ AgentOps(2 源学术 + OTel 工业腿待采)

| id | 日期 | 主张 | 对撞点 |
|---|---|---|---|
| 2610.31662 (Selective Auditing) | 2026-10-22 | 在线监控 AI 决策流:最小化人审频率 + 未审错误率≤阈值的无假设保证(对抗/iid 双流最优) | →运营:人审预算化的数学框架 |
| (同上 Agentic Auditing) | — | 预算护栏内运行的审计 agent 实例 | →运营 |

### ⑤ 失效模式(2 源 2026 + Aegis 2025 背景)

| id | 日期 | 主张 | 对撞点 |
|---|---|---|---|
| 2610.01256 (DeFA) | 2026-10-01 | 依赖图失败归因:协议关系+语义依赖→事件依赖图→失败传播图→决定性错误/责任agent/错误类;分段处理长轨迹;诊断反馈喂回提升 6-15pp | →失效:多步误差分离定位方法论 |
| 2511.09710v3 (Echoing) | 2025-11 首发, v3 2026-03 | AxA 身份漂移:66 配置 2500+ 会话,echoing 最高 70%,推理模型仍 32.8%;**结构化响应协议降到 9%** | →失效+多agent反面:agent 间会话需协议级结构化 |
| (背景) 2508.19504 (Aegis) | 2025-08 | agent-环境交互失败 6 型分类;环境优化(可观测性/卸载/投机动作)提升成功率 6.7-12.5% 不改 agent | 背景:失败分类学参照 |

### 负向(被证伪/被挑战实践)

| id | 日期 | 主张 |
|---|---|---|
| 2601.13649 (Fairness or Fluency) | 2026-01 | pairwise LLM-as-judge 语言偏差持续:同语言判定欧语>非语,跨语言偏英;困惑度只解释部分 |
| MCPTox | 2026 | 「模型更强更安全」被证伪:更强模型 ASR 更高 |
| Echoing | 2026 | 「多agent对话自然收敛」被证伪:漂移是常态,结构化协议才压得住 |

### 缺口(按贫困程序如实记)

- ②开发过程:学术侧 2026 源贫(命中全为 2024-2025)→ 该角度主通道=工业文档,web 腿承重
- CTI 领域特化:2026 arXiv 源<3 → 按弃置条件放弃,记缺口
- LLMOps 学术综述:未命中独立 2026 源 → OTel GenAI 工业标准 + AgentOps 商业实践承重
- 部分基准横评类(contamination 2026 专文)未命中 → 若 web 腿也无,记标准缺口

## 工业腿(web/agent-reach,子代理 7504379f;已核日期,各角度≥3源)

### ① 评估(6)
- Anthropic Research 博客 2026-01-09|Demystifying evals for AI agents|**能力评测与回归评测分立**:capability 刻意低通过率起步爬坡;regression 要求≈100% 通过,回答「agent 是否还能做会的事」
- LangChain 官方 2026-06-23|Run/Trace/Thread 三级评测单位:单次调用/单轮执行/多轮会话,逐级对照 ground truth 分级断言
- OpenAI 官方(日期unknown不计)|EDD:每阶段 scoped 测试、早评常评;数值分必须与人工判断组合
- AWS Bedrock AgentCore 2026-10-16|生产评测四维:安全/质量/性能/运维控制,逐维独立打分
- Google Developers Blog 2026-10-15|Moving past the vibe check:vibe 抓不住死循环/烧token/「幻觉但看起来正常」;60分钟搭评测管线 playbook
- Braintrust 2026-02-26|终局结果+决策序列双面评测;step-level 判路径
### ② 开发过程(5)
- web.dev 官方 2026-01-29|EDD=TDD 的 AI 同构:可重复小步、抓回归
- Microsoft 官方 2026-06-10|Spec-Driven Development:requirements/design/implementation/validation 四层对齐,spec 是契约不是文档
- Braintrust 官方 2026-09-26|prompt CI/CD:候选与生产 prompt 在固定数据集按 quality/latency/cost 三指标对打,过 release-criteria 才上线
- Red Hat 2026-06-02|evalHub:红-绿-重构循环搬进 eval
- promptfoo+GitHub Actions 博客 2026-10-02|CI 五件套:golden 数据集+JSON Schema 输出校验+延迟成本断言+judge rubric,不达标 fail PR
### ③ AgentOps(6)
- **OTel GenAI semconv(必采)**|已迁独立仓 open-telemetry/semantic-conventions-genai(2026-05 建,推送至 2026-10-23):create_agent span(gen_ai.agent.id/version)、MCP 统一 execute_tool+mcp.method.name、tool 参数/结果 Opt-In
- Agent Internals 2026-09-23|经典三态熔断器原样适用 agent,按通道/工具粒度装
- Latentism 2026-10-05|**预算帽在调用前检查**:reserve-then-settle 预扣+花费熔断+kill switch;事后 dashboard 不构成预算控制
- IEEE Spectrum 2026-04-07|**安静失败**:监控全绿而行为已错,标准可观测性抓不出语义级退化
- ACM Queue 2026-10-15|LLM agent=「自己写调用图的分布式系统」,直接借用 40 年分布式可靠性工程
- Dynatrace 2026-08-25|2026 SRE 趋势:AI 系统纳入 SRE 实践基线
### ④ 安全(5+背景1)
- MCP Specification 2026-07-28|现行版,BCP14 语言,含 Authorization+Security Considerations
- NSA CSI 2026-06-02(17页)|MCP 安全设计考量,政府级威胁视角
- OWASP GenAI LLM Top 10 2026 v1.0(2026-08-03)|取代 2025 版
- OWASP Agent Control Standard(ACS)2026-09|agent 必须可检查/可追踪/可插桩,治理以透明为前提
- Docker Sandboxes 2026-01-30|microVM 隔离让编码 agent 可无人值守,least-privilege 工程样例
- (背景)OWASP Agentic Top 10 for 2026:首发 2025-12,按规则不计 2026 证据
### ⑤ 反面(6)
- Gartner 2026-10-07|When to Build a Multiagent System:默认最简架构,单 agent 优化穷尽前不建 MAS
- InfoWorld 2026-04-05|MAS=新的微服务复杂度故事;问「最小可行自主性」
- arXiv 2609.19759 2026-09|When More Is Less:协作边际收益随单 agent 能力递减
- swarm tax 博客 2026-05-17|引 Stanford(Tran & Kiela):**同 thinking-token 预算下多 agent 优势消失**——此前多 agent 优势是算力不对齐伪影
- Multigrid 2026-08-03|Anti-Pattern: Evaluating by Vibes:「看起来更好」只合法一周,无机制宣告结束就沿用一年
- Google Cloud 2026-02-27|From Vibe Checks to Continuous Evaluation:打地鼠改 prompt 必升持续评测管线

通道判例:r.jina.ai 对 github 匿名 403(AbuseAlleviation)→raw.githubusercontent+API;media.defense.gov HEAD 403→jina 全文;owasp 详情页 browser-check 空壳→采列表页;LangSmith 域无可采正文。

## 三向对撞(外部学术×工业×内部判例)

| 内部判例 | 外部印证 | 外部推翻 | 外部无对应(我们独有) |
|---|---|---|---|
| 锚门死件(条文漂亮零调用) | Google vibe批判+Google Cloud 持续评测+IEEE「安静失败」:面板绿≠行为对,须行为探针 | — | — |
| 事故即金标(8.8.8.8/114DNS) | promptfoo golden+Anthropic regression≈100%门+学术 Agentic Auditing(发现→可执行测试→人验) | — | — |
| 信封纪律(失败不编造) | EpiSEM-Bench(证据缺失→不安全动作)+FlowGuard(语义信号≠证据)+Cost-Aware Abstention(弃权单独校准) | — | — |
| 预算四界(¥3/¥30) | Latentism:**预算帽须调用前 reserve-then-settle**;熔断按工具粒度 | 若我们实现是事后记账则被推翻(待核) | — |
| C骨架状态机(模型只在3步) | Gartner/InfoWorld/swarm tax:最简架构默认;同预算下多agent无优势 | — | — |
| 谱系去重/假印证(回声不是印证) | swarm tax 方法论平行:混淆变量对齐后优势消失=伪影 | — | **源谱系混淆模型:工业 eval 框架均不建模,我们的独有条目** |
| 回放闸门/位等价 | Braintrust prompt CI/CD(候选vs生产对打)+promptfoo fail-PR | — | — |
| 三层职责线(宿主/提示词/脚本) | Microsoft spec-driven 四层对齐+ACM Queue 分布式视角 | — | — |
| 工具白名单+tool_keys 最小权 | MCP-ITP(借合法高权工具作恶 84.2% ASR)+MCP spec 2026-07-28+NSA CSI+Docker microVM | — | — |
| 北星指标(整体情报更准) | Anthropic:capability eval 与 regression eval **分立** | — | 北星=能力轨,锚=回归轨,阈值语义不同 |

外部新输入(内部无对应,待铸条):OTel GenAI semconv 词汇对齐(轮信封外发投影)、回归门≈100% 通过率语义、Run/Trace/Thread 三级评测单位、reserve-then-settle 预算模式、安静失败探针化。


## 判例(通道)

- paper-search search_arxiv:sort=submittedDate 会让查询词失效(返回全站当日新文,物理数学全进);
  必用 relevance+短语收紧+客户端筛 2026。本批判例 2026-10-24。
