# P2 健康轮重造 · 比稿 A「工具面中心」设计文档

- 日期:2026-10-23
- 落仓目标路径:`notes/p2-design-a-toolfirst-2026-10-23.md`(本比稿 A 全文;比稿 B/C 另文)
- 比稿语境:本稿是「设计它两次」三比稿之一(研究 L364,DESIGN-IT-TWICE.md:21「radically different interface」),结构级差异锚在**能力面落在哪**:A=工具面(模型=验尸官,结论只出自亲手探针);B/C 假定走记忆面/流程面,本文不预设其结论。
- 研究基线:`notes/mp-skills-design-research-2026-10-23.md`(下引「研究 L<n>」= 该文档行号,「研究 §1.2 #<n>」= 技巧条目号);现状文件引「文件:行」。

## 0. 问题陈述与不可挑战面

### 0.1 要解决的问题

用户 2026-10-23 裁定健康轮「too dumb、看不到 AI 能力」(S6404 观测),同轮证明当日两条异常均为**探针假象**(探测面产物,非源真实劣化)。根因在现状结构,不在模型:

1. 现状把模型钉死为**摘要员**:「你调用 `health_snapshot` 取实测读数,只做汇总与标异常」(ops/agent/prompts/health-system.md:6),且「一次 `health_snapshot` 调用即可,不要反复调用」(同文件:28)。模型唯一的工具是零参快照(tools.mjs:236-240,health 轮工具面仅 `health_snapshot`、预算 2)。
2. 全部结论在模型进课前已由本地脚本预派生:`freshness_flags` 直接产「死键嫌疑/不可达·建议复核」行(lib.sh:209-217),模型做的是**复读**(研究 §4-12「premature completion」与 §4-1「自证式断言」的运营等价物)。
3. 假象与真实在快照层不可分辨:GeoLite「releases/latest/download」HEAD-404 型假红与 abuse.ch 410 真死键在 `freshness_flags` 输出里同形(均为「不可达·建议复核」),只有**再探一次**(换方法、看历史、读上游)才能分开——这正是现状模型没有的动作面。

### 0.2 不可挑战项在本设计中的落点(全部保持,零重设计)

| 裁定项 | 本设计的兑现方式 |
|---|---|
| 四键条目面(P1 已交付) | 诊断条目经 `create_item` 十字段冻结面入库(_ops_items.py:54-58),四键 agree/modify/ignore/snooze 与可逆闭集(_ops_review.py:46-50)一字不动;本设计只做**条目的生产者**,不做条目的消费者 |
| 永不自动执行(仅人裁) | 健康轮工具面全只读探针 + `emit_diagnosis` 仅产**待审条目**(status=active,等四键);测量全自动沿三层权限既有语义(discover-system.md 边界节) |
| 模型 I/O 全留痕 | 每轮新增 transcript.jsonl 工件(§2.1.4)+ 查看视图扩展;现有包脚注/台账留痕面全保留 |
| amend 问句闭环 | investigation 类诊断条目带 `amend_question`,modify 答问即闭环,复开走 T1 supersedes 链指(_ops_items.py 头注「复开链指」) |
| retro 钩子 | 双接线:轮内「探针假象→确定性检查候选」+ 轮后「人裁 ignore 惯性→抑制候选」(§2.1.5) |
| 三节模板降级 | 三节(注入判例/异常清单/摘要)是**降级地板**:任何阶段门翻红或预算尽,宿主零 LLM 渲染三节包,轮次永不变暗(§3.GD) |
| 8h 节奏+预算卡 | 8h tick 走既有串行车道;深查单发≤$0.01、月≤$0.5 由工具预算+回合帽+月累计守门三闸执行(§4) |
| 判例/台账/旧包永不改写 | 本设计只新增文件(transcript/、retro-candidates.md、新包),不改写任何既有件;锚判例集是装配面索引,不是判例改写 |
| 964MB 服务器 | 健康轮工具面**不含** exclusive_probe(256MB 下载面是 discover 专属,tools.mjs B.probeBytes);探针全走 fetch_url 既有 512KB 围栏+SSRF 逐跳(tools.mjs safeFetch);node 256MB 堆围栏沿 spawn argv(_ops_rounds.py:23);深查与例行轮共用串行车道互斥(main.py:1518-1526 一轮一车道) |

## 1. 设计主张(比稿 A 的结构差异)

**一句话:把健康轮从「读报告的摘要员」改成「验尸官」——尸体(旗标)由确定性快照提供,但死因结论只能出自验尸官亲手跑过的探针;宿主用机检布尔行当阶段门,模型过不了门就降级,不糊弄。**

三条结构律(每条对应一个现状缺陷):

1. **能力面=可消耗的探针回路。** 模型得到的是 6 个带预算的工具(§2.1.2),不是一份预消化的报告。回路优先于判断:先证明「这条旗标能被一条探针复现/证伪」,再谈根因(研究 §1.1 #1,diagnosing-bugs/SKILL.md:20「This is the skill. Everything else is mechanical.」)。
2. **阶段门=机检工件布尔行。** 每阶段在包内产固定格式布尔行(`GATE-2 falsify covered=true ...`),宿主对照结构化返回登记表(ResultRegistry,tools.mjs:340-345 既有件)逐字机检;门行缺失/为假 = 该阶段未完成(研究 §1.2 #93,writing-for-agents/SKILL.md:47-52「checkable and exhaustive」)。**不信模型自报,只信登记表可回算的布尔。**
3. **模型选探针,宿主填数字。** `emit_diagnosis` 的 evidence 只收 `call_id+field` 选择对,值由宿主从 structuredContent 解析回填;分类一致性由宿主规则机检(§3.G5)。这结构性消灭 discover 语义门已知的复述漂移失败面(tools.mjs:268-283 逐字比对所需的前置:模型抄对值——flash 上这是方差源)。

责任线钉死两条 MP 原文(研究 L358):「Finding facts is your job… The decisions are the user's」(grilling/SKILL.md:28)+「the agent never stands in for the human's side of it」(wayfinder/SKILL.md:75)→ 写进提示词边界节,作为 never-auto-execute(判例 0db23018)的形式化表达:旗标线=HITL 票,验尸官产报告,四键面执刀。

## 2. 三层完整架构

```
┌─ 宿主层(host:agent.mjs + _ops_rounds.py + lib.sh,既有骨架上扩)─────────────┐
│ 8h tick → 串行车道 → spawn 契约(argv/env/轮次信封,零改) → 工具白名单+预算  │
│ → 阶段门机检 → transcript.jsonl 工件 → 桥侧条目物化(create_item) → 收口四件   │
│ → retro 双钩子 → 预算卡三闸 → 降级渲染                                        │
├─ 装配层(assembly:进模型上下文的构造)───────────────────────────────────┤
│ 预注入=锚判例闭集 + 动态检索=read_precedents(闭集=预注入∪命中,铁律④)        │
│ + handoff 指针纪律(下轮指针节,只指不copy) + 输入派生(在飞条目/上轮假设摘要)  │
├─ 提示词层(prompt:重写版 health-system.md,§2.3 全文草案)──────────────────┤
│ 验尸官角色 / 6 工具面 / 五阶段回路 / 布尔门行格式 / 信封处置 / 边界 / 降级      │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 宿主层

#### 2.1.1 轮次派生(8h 节奏 + 深查单发)

- **例行轮**:进程内 8h tick(_scheduler 挂一个 ops tick 槽;备选=服务器 cron 打 POST /api/ops/rounds,二者择一,P2 立项时定,倾向进程内——单一拼写,免新 auth 面)。tick 走 `start_ops_round` 既有串行车道与 409 面斥(main.py:1518-1526),输入非空校验、SSE 进度、取消面全部复用,零契约改动。
- **输入派生**(新增小件 `_ops_input.py`,桥侧):例行输入 = 上轮包的「下轮指针」节(§2.2.3)+ 在飞条目摘要(≤20 行:source/probe_class/severity)+ 上轮 top 假设 id;深查输入 = `DEEP <hyp-id>:<问句> + 证据指针`。
- **深查派发**:例行轮信封新增 `deep_hint` 字段(top 假设 needs_deep=true 时携带)。桥侧判定三闸全过才派发:①月累计<$0.42(§4);②车道空闲;③同假设 7 天内未深查过(host 记最近深查集,内存态即可,判例幂等由条目库兜)。深查=同 `health` 轮型、输入带 `DEEP` 前缀,提示词按模式分支(§2.3),**不开新轮型**——spawn 契约 argv/env/信封九词闭集(agent.mjs ERROR_CODES)零改。
- 测量全自动边界:tick 与深查派发均为测量轮,不触碰源状态,符合三层权限「测量全自动」;永不自动执行约束的对象是**对源的动作**,条目物化属旗标通道(P1 确定性探测器已零 LLM 自动产条,_ops_detectors.py:99-162 同律)。

#### 2.1.2 工具白名单与预算(轮次能力面,闭集)

健康轮工具面从 1 个扩到 6 个(tools.mjs `round === "health"` 分支改写;discover 面零触碰):

| 工具 | 复用/新增 | 每轮预算 | 关键围栏 |
|---|---|---|---|
| `health_snapshot` | 复用(tools.mjs healthSnapshot(),零参) | 1 | 现状快照:URL 全量冻结检测+matrix;TSV/JSON 落工件 |
| `probe_url` | 复用 fetch_url 实现改名注册(同 safeFetch) | ≤8 | SSRF 逐跳+512KB+15s;HEAD/GET;`age_days`/`status`/样本≤5 行 |
| `read_artifact` | 新增(薄件) | ≤6 | 白名单=本轮工件目录+docs/ops/artifacts+docs/ops/packages;≤50KB/2000 行;pattern 过滤;复用 checkReadablePath 判定 |
| `read_precedents` | 复用 search_precedents | ≤4 | rg 词法,命中≤8(铁律⑦,hitCap=8 tools.mjs:43);命中进闭集 |
| `task_history` | 新增(薄件) | ≤4 | 只读桥侧预派生的近 7 天任务终态 JSON 工件(§2.1.1 输入派生时落盘),Node 零 Python 耦合 |
| `emit_diagnosis` | 新增(唯一写) | ≤5 | 见 §3.G5;不直接写盘——结构化提案入信封,Python 桥物化 |

结构性红线不变:零内建工具、agent 无 bash/write/edit(tools.mjs:4 铁律⑥);`emit_diagnosis` 不是文件写,是**提案返回**(宿主登记 itemProposals,信封携带,桥侧 `create_item` 落库);越界工具调用仍=轮次失败 foreign_tool(agent.mjs 零内建工具证明)。外沿探针礼貌:probe_url 同 host 每轮≤2(host 计数),串行执行;深查禁连续轮询同 host(abuse.ch 5 分钟节奏礼节,观测 29947)。

#### 2.1.3 沙箱断言

`sandbox_assert` 原样复用(lib.sh:120-134):轮末跑,backend/frontend 有改动即轮次失败。本设计下模型连写文件的工具都没有(唯一写是提案),沙箱断言从「拦模型乱写」降格为「拦宿主/工具实现缺陷」,仍保留为不变形防线(哲学:测量建言,防线不撤)。

#### 2.1.4 transcript 工件(模型 I/O 全留痕)

- 每轮新增 `docs/ops/transcripts/<包名>.transcript.jsonl`,逐事件追加(不整缓存,964MB 友好):每条 = `{seq, role, content|toolCall{name,args}|toolResult{callId,structuredContent,artifact}|stopReason, usage, ts}`。数据源=agent.mjs 既有 subscribe 事件流([turn]/[tool] 行的同源事件,agent.mjs:196-215),只加落盘不改契约。
- 查看视图:P1 包查看面(`/api/ops/packages/{name}`,main.py:1545)扩展并列 tab「轮内记录」:新增只读端点 `/api/ops/transcripts/{name}` 渲染 JSONL 为时间线(工具调用可折叠、structuredContent 摘要+原文切换);前端仅加 tab,不动四键面。
- 旧包/台账/判例零改写;transcript 只增不删,90 天滚动归档(磁盘策略,P2 部署件)。

#### 2.1.5 retro 钩子接线(机械误判→确定性检查候选)

- **轮内钩(假象收编)**:模型每判一条 `verdict=探针假象`,包内「retro 候选」节必须给出候选确定性检查的**可执行描述**(例:「`raw.githubusercontent.com/*` 与 `github.com/*/releases/latest/download/*` 的 HEAD-404:候选=lib.sh `_ff_probe_once` 对该两形状直接降 GET,跳过 HEAD」)。宿主把该节 append 到 `docs/ops/retro-candidates.md`(新文件,append-only,永不改写)。人另裁是否真收编进 lib.sh——候选≠执行(永不自动执行对代码面同理生效)。
- **轮后钩(人裁惯性)**:四键 ignore 落判例时(_ops_review.py 写回面),桥侧检测同 `cause_group` 连续 ignore≥2 → 追加「抑制候选」行到 retro-candidates.md(例:某探针形状假红已两轮被人 ignore→候选=snapshot 层预过滤)。判例本身仍走四键判例落盘,不改写。
- retro 三原则按研究 §1.2 #44(retro/SKILL.md:19「mechanical one gets a deterministic check, full stop」):机械误判→确定性检查候选;判断类→判例标准(经四键裁决面自然沉淀)。

#### 2.1.6 收口顺序(扩既有四件为六件)

包落盘 → 台账(九裁决 9:实测入账)→ 判例闭合校验(closureCheck,agent.mjs:224,闭集=预注入∪read_precedents 命中)→ 阶段门机检(§3,新增)→ 桥侧条目物化(新增:create_item 幂等,失败=infra 台账行+JSONL spool 兜底,下轮重放安全)→ sandbox_assert。任一失败=轮次失败非零退出,工件不灭失(规格 §3 既有语义)。

### 2.2 装配层(进模型上下文的构造)

#### 2.2.1 预注入锚判例(闭集,恒注入)

- 现状:静态关键词检索注入(agent.mjs:39-40 `health: ["冻结","死键","不可达","违例"]`),命中随库漂移。
- 改为**两段式**:①**锚判例**=显式闭集文件 `ops/agent/anchors-health.txt`(一行一判例文件名,≤6 条),每轮无条件注入——首版锚:threatview-sunset(sunset 门线判例,lib.sh:136 出处)、firehol-webserver-unsubscribe(已裁退订史)、2026-10-23 两假象判例(GeoLite-404 型假红、abuse.ch-410 真死键——**P2 上线前置件:把 10-23 两次验证写成两条判例入库**,判例库 append 不违「永不改写」);②**动态注入**=静态基础词 + 上轮包旗标 host 域名派生词,仍走 `inject_precedents`(lib.sh:42),命中并入闭集。
- 上限沿铁律⑦:总注入≤8(锚+动态合计截前 8)。
- 锚集治理:锚集是**装配面索引**不是判例(研究 §1.2 #66「map is an index, not a store」),换成员不动判例;每季度人审一次。

#### 2.2.2 按需检索(轮内)

`read_precedents`(=search_precedents)给模型轮内自查:证伪阶段按旗标域名/形状检索(「abuse.ch」「410」「releases/latest」),深查阶段按假设检索同型判例。引用闭集=预注入∪本会话命中,闭合校验拦编造(既有 closureCheck,零改)。判例库=唯一跨轮记忆、无界不删(_schema.md),P2 不动其 schema。

#### 2.2.3 handoff 指针纪律

- 每个完整轮的包尾新增「## 下轮指针」节:未决假设(hyp-id+一行 gist+探针工件路径)、在飞待裁条目(item-id)、retro 候选指针。**只放指针不放内容**(研究 §1.2 #79,handoff/SKILL.md:12「Reference them by path or URL instead」);旧包永不改写,指针指向的包/工件只读。
- 下轮输入派生(§2.1.1)读上轮指针节拼输入——「按下一轮用途裁剪」(研究 §1.2 #80):例行轮只带假设/条目指针,深查轮带单假设全量证据指针。
- 具名引用纪律(研究 §1.2 #71):指针写「<source 名>:<判例/条目 id>」并附路径,禁裸 hash 墙。

### 2.3 提示词层:重写版 health-system.md 全文草案

> 设计注:草案按信息阶梯排布——全轮必读内联,分支规则挂指针(研究 L356,writing-for-agents/SKILL.md:39 分流判据);禁令配正向目标句(研究 §1.2 #92 否定失效);每条硬规则点名它防的失败(研究 §1.1 #5)。目标 ≤90 行。

```markdown
<!-- 健康轮系统提示(P2 比稿 A「工具面中心」草案,取代 T3/T4 摘要员版 2026-10-23;
     历史:T3 定稿摘要员→T4 health_snapshot 结构化→P2 验尸官。旧版见 git 历史,不改写。) -->
# 角色

你是 IP Radar 源生命周期「健康轮」验尸官。确定性快照送来尸体(旗标),
死因结论只能出自你本会话亲手跑过的探针:没探过的旗标,你的措辞只能是「未验」。
事实归你(探针/翻判例/读历史),裁决归人(四键面);你从不执行任何对源的动作。

# 动作面(6 工具;零内建工具——没有 bash/read/edit/write)

| 工具 | 用途 | 每轮预算 |
|---|---|---|
| `health_snapshot` | 零参快照:全量源冻结检测计数+旗标+matrix 读数(原始读数落工件) | 1 |
| `probe_url` | HEAD/GET 探测(SSRF 逐跳拒;返回 status/last_modified/age_days/样本≤5 行) | ≤8 |
| `read_artifact` | 读工件原始读数(本轮 TSV/matrix JSON/任务史),pattern 过滤 | ≤6 |
| `read_precedents` | 判例库词法检索(命中≤8;引用只许引注入块或本工具命中) | ≤4 |
| `task_history` | 近 7 天源更新任务终态史(连败/成功/取消,按源过滤) | ≤4 |
| `emit_diagnosis` | **唯一写**:产诊断条目提案(宿主门+人裁四键,见阶段五) | ≤5 |

# 五阶段回路(阶段门=布尔门行,宿主对照登记表机检;门不过=重跑该阶段或降级)

**阶段一 取数**:调 `health_snapshot` 一次。产门行:
`GATE-1 snapshot ok=<true|false> flags_n=<旗标总数>`
(matrix 失败信封照实写 ok=false,不许替失败补数。)

**阶段二 逐条证伪**:对快照每条旗标跑 ≥1 条**可分辨探针**,给三态裁决:
- `真实` — 复探同型失败成立且换法仍成立(如 HEAD 与 GET 均 4xx,或 age_days 复测仍≥180);
- `探针假象` — 换法探针推翻快照读数(如 HEAD-404 而 GET-200;URL 形状陷阱)。此裁决**必须**引用一条 ok=true 且与快照矛盾的同 URL 探针;
- `存疑` — 探针失败信封/证据不足。存疑是合法结论,编造不是。
产门行(逐旗标一行):
`GATE-2 <url或cell> verdict=<真实|探针假象|存疑|未验> probe=<call_id>`
未验旗标不许在诊断清单里消失——宁列「未验」,勿吞旗标。

**阶段三 排序假设**:对 verdict∈{真实,存疑} 的旗标立假设,每条带**可证伪预测**
(「若 X 为因,则改 Y 会消失」;例:若 abuse.ch 停发匿名导出,则其 v2 API 带
token 可达且 4xx 消失)。排序并列呈现,不选冠军、不吞尾部(评审纪律:并列不重排)。
产门行:`GATE-3 rank emitted=<true|false> top=<hyp-id> needs_deep=<true|false>`

**阶段四 深查(仅 DEEP 模式)**:输入以 `DEEP <hyp-id>` 起头时,只跑本阶段+阶段五。
一次深查只答一个假设(单会话单票)。探针族按假设选,手册见 deep-playbooks:
死键嫌疑 = probe_url GET 取样本对照历史工件 + 打上游状态页/备用主机;
上游变更 = 新旧探针对照(同 URL 两次读数或对照 read_artifact 旄件);
回归 = task_history 查拉取史 + read_precedents 找同型判例。
每个硬数字挂 call_id。
产门行:`GATE-4 deep answered=<true|false> cost_probes=<n>`

**阶段五 产诊断条目**:`emit_diagnosis` 逐条提案(字段见工具描述)。evidence 只给
`call_id+field` 选择对——**值由宿主从结构化返回回填,你只选探针不抄数字**
(抄错即门拒)。investigation 类条目必带 `amend_question`(一句可答问句,
人裁 modify 答问即闭环)。
产门行:`GATE-5 items emitted=<n> gate_blocked=<n>`

# 信封处置指令(硬约束)

- 工具返回 `{ok:false,code,reason}` = 失败信封:不是读数,禁止入 evidence,
  禁止替失败补数(无证据≠清白——宁空勿编)。同参数可重试 ≤1 次,再败即记「存疑」。
- `health_snapshot` 的 matrix 子信封 = 测量故障:如实注明「matrix 测量故障:<code>」交人裁。

# 边界(硬约束)

- 只测量、只产条目、只留人裁:发现真死键/假象/回归 = 产诊断条目+推荐四键,
  **不退订、不改源、不自动执行**——每条以「待四键人裁」收尾,这就是你的正向终点。
- 每条「探针假象」同时是 retro 候选:在「retro 候选」节写一句可执行的确定性检查
  描述(防:同一假象月月重判、人月月重看)。
- 不可达≠死键;NO-LM/TOKEN_REQUIRED 不是异常,摘要如实提及计数(沿 P1 T2 口径)。
- 探针输出进报告前脱敏:任何 key/token 形样写 `<REDACTED>`(防 1113 型事故入档)。
- 硬门数字只出自本会话探针的结构化返回;读数缺项写「待实测」。

# 降级(硬约束)

预算尽、门行翻红两次、或你无法完成任一阶段:停止回路,按三节模板输出——
`## 注入判例` / `## 异常清单`(旗标原样列出,逐条标「未验」)/ `## 摘要`。
降级是诚实的地板,不是失败;编造才是失败。

# 输出契约(健康包 markdown;节序固定;降级=仅 1/2/3)

1. `## 注入判例` — 逐条列注入块判例文件名,或显式「无判例(检索词: ...)」;禁止编造路径(闭合校验)。
2. `## 异常清单` — 证伪结果表:旗标 | verdict | probe call_id | 一行依据(每行可点回工件)。
3. `## 诊断条目` — emit_diagnosis 逐条摘要(条目 id、severity、建议四键、amend 问句);无则「无」。
4. `## 摘要` — 中文 ≤10 行:真实/假象/存疑计数、值得人看的点、待裁积压。
5. `## 下轮指针` — 未决假设/在飞条目/工件路径,只放指针。
6. `## retro 候选` — 本轮探针假象的确定性检查候选,一行一条;无则「无」。

<!-- 指针(分支规则,按需让宿主注入,不常驻上下文):
     ops/agent/prompts/refs/probe-patterns.md — 探针形状手册(已知假象族与分辨探针)
     ops/agent/prompts/refs/deep-playbooks.md — 深查剧本(死键/回归/上游变更三型)
     ops/agent/prompts/refs/item-vocab.md — probe_class/签名/cause_group 词汇表 -->
```

装配层注:三份 refs 文件是**模型可按需要的分支参考**(宿主在输入派生时按模式附带对应一份,DEEP 模式带 deep-playbooks);不常驻 system prompt,省 flash 上下文(研究 §1.2 #6/#90 信息阶梯)。

## 3. 五阶段回路在工具面中心的落地

每阶段 = 工具消耗模式 + 机检门行。**门行是工件布尔行:宿主从登记表回算真值,与模型写的行逐字比对;不符=门翻红。** 模型写不出真门行 = 没做过该阶段的活(研究 §1.2 #7 亮工作过程的机检化)。

| 门 | 布尔行(包内) | 宿主机检算法(全部可从 transcript+registry 回算) | 翻红处置 |
|---|---|---|---|
| G1 | `GATE-1 snapshot ok=… flags_n=…` | 与 health_snapshot structuredContent 的 ok/旗标计数逐字段相等 | 快照失败信封→直接降级三节(现状行为保留) |
| G2 | 每旗标一行 `GATE-2 <id> verdict=… probe=<call_id>` | ①旗标集=snapshot 旗标集(不许丢旗标);②probe call_id ∈ registry 且工具∈{probe_url,task_history,read_artifact,read_precedents};③verdict=探针假象 → 该 call_id 结构化返回须 ok=true 且同 URL 与快照旗标矛盾(status 翻转/age_days 归零);④verdict=真实 → 引用探针须支撑(4xx 复现或 age_days≥180);⑤verdict∈{存疑,未验} → 引用探针须存在(含失败信封) | 翻红一次:宿主回报差异,允许重跑该旗标;两次:该旗标强制改「未验」,轮继续 |
| G3 | `GATE-3 rank emitted=… top=… needs_deep=…` | top ∈ G2 真实/存疑集;needs_deep=true 要求 top 有≥2 条独立探针支撑 | 翻红:排序降为「全列不排序」,needs_deep 强制 false |
| G4 | `GATE-4 deep answered=… cost_probes=…` | answered=true → 结论段每个硬数字挂 call_id 且值=registry 回算值;cost_probes=实际探针计数(预算≤8) | answered=false → 条目降级 investigation+amend 问句 |
| G5 | `GATE-5 items emitted=… gate_blocked=…` | 逐条:emit_diagnosis 提案过了语义门(§下);gate_blocked=宿主拦截数如实 | 拦截条目不物化,包内如实计数 |

**emit_diagnosis 语义门(宿主规则,复用 discover 门骨架 tools.mjs:253-302 改写)**:

- 字段闭集:source ∈ registry 源名形(`^[a-z0-9_]{1,32}$`);probe_class ∈ P2 词汇表(新增 `frozen_feed|unreachable_real|matrix_violation|upstream_change|regression`,经 spec 变更扩 _ops_detectors.py:62 CAUSE_GROUPS 词表——**唯一 spec 依赖,见 §7**);severity ∈ {high,medium,low}(_ops_items.py 闭集);action 建议句**不得**以 ENQUEUE/REJECT 起头(自然落 P1「仅立项」语义,_ops_review.py:189-191 proposal_only)。
- evidence:`[{call_id, field}]`——宿主 resolveField 回填值(tools.mjs 既有解析件),再按 probe_class 规则验证一致性(frozen_feed→age_days≥180;unreachable_real→status≥400 复现;upstream_change→新旧探针对照)。
- 幂等预检:同 source+probe_class 已有在飞条目(输入派生的条目摘要面)→ 拦截并回报既有 item-id(T1 幂等语义在宿主面前提前执行,防双通道双开:确定性探测器已产 download_failure/staleness 条,_ops_detectors.py:99-162,LLM 条与 detector 条的 error_signature 由宿主同一生成器渲染,保 dedup_key 同源)。
- 桥侧物化:信封 item_writes[] → `_ops_items.create_item`(十字段/幂等/supersedes 全复用,_ops_items.py:198),物化失败=infra 台账行;itemProposals 同步落 JSONL spool 工件,下轮重放幂等安全。

**降级路径(GD)**:任一环节(预算尽/门两翻/G0 模型面失败)→ 宿主**零 LLM** 用 snapshot structuredContent 渲染三节包(异常清单=旗标原样+「未验」),包标 `degraded: true`,台账记因。地板=现状行为,轮次永不变暗。

## 4. 成本模型(轮均 token 估算)

计价基准=台账实测(docs/ops/ledger.md 2026-10-19 行):flash 混合约 $0.24/1M tok(15,616 tok→$0.0038;6,043 tok→$0.0007 区间),glm-5.3 混合约 $0.58/1M(26,072 tok→$0.015)。估算仅用于预算规划;**记账以每轮 provider 实报为准**(九裁决 9,agent.mjs usage 累计既有件)。

| 轮型 | 构成 | token 估算 | 成本估算 |
|---|---|---|---|
| 例行轮(flash) | system ~1.3k + 锚判例注入 ~1.0k + 输入派生(指针+条目摘要)~0.6k + 快照读数 ~1.2k + 回路 6-10 探针回合(累计输入膨胀)~10k + 输出(门行+清单+摘要)~2k | 总 ~16-20k | **~$0.004/轮** |
| 深查轮(flash) | DEEP 输入(假设+证据指针)~1.5k + 剧本 ref ~0.8k + 8 探针回合 ~14k + 结论文本 ~2.5k | 总 ~20-25k | **~$0.005-0.006/发** |
| 深查轮(glm-5.3 兜底) | 仅当 retro 连续两月显示 flash 深查 answered=false 率>30% 才经 OPS_MODEL_HEALTH 切换;输入裁到门行+探针摘要(禁原始读数全文)≤12k | ≤17k | **≤$0.0098<单发 $0.01 帽** |
| 降级轮 | 零 LLM(宿主渲染) | 0 | $0 |

**月度推演(8h 节奏)**:例行 3 发/日 × 30 = 90 发 × $0.004 ≈ **$0.36**;深查 ≤1 发/3 日 ≈ ≤10 发 × ≤$0.01 = ≤**$0.10**;合计 ≈ **$0.46 ≤ $0.5** ✓。

**预算卡三闸(宿主执行,防估算漂移)**:
1. 工具预算+回合帽:例行 ≤16 回合、深查 ≤12 回合,到帽即降级(预算计数走 beforeToolCall 既有面,tools.mjs:247-253);
2. 派发前月闸:桥侧解析台账当月 health 行合计,≥$0.42 停派深查(条目降 investigation+amend 问句),≥$0.48 例行轮也降为零 LLM 渲染至月末;
3. 事后追认:单发深查实测>$0.01 → 台账标注 + retro 候选(「深查剧本超支」=机械误判面)。

## 5. 风险与失败模式

| # | 失败模式 | 征候 | 缓解(结构位) |
|---|---|---|---|
| R1 | flash 跑不动五阶段回路,门翻红成灾 | 降级率>30%、G2 未验占比高 | 降级地板保底;retro 监控降级率,连续两月超标才切 glm-5.3(成本重算过 §4 帽);比稿 A 的回路本身按 flash 注意力预算裁剪(探针≤8、清单行短) |
| R2 | 探针对上游不礼貌(限流/封禁) | 同 host 连续 4xx、abuse.ch 429 | 同 host 每轮≤2、串行、UA 标识;深查 7 天不重查同假设;探针形状手册收编已知敏感 host 礼节 |
| R3 | 双通道双开条目(detector+LLM 同因) | 条目面同源两 active | error_signature 宿主同源渲染 + emit 前在飞条目预检(§3 G5);残余靠 T1 dedup_key 幂等兜底 |
| R4 | 分类判断造假(把真实说成假象) | 人裁 agree 率与 verdict=探针假象 冲突 | 假象裁决须引用矛盾探针(机检);四键人裁终局;轮后 retro 钩把惯错类收编候选 |
| R5 | 复述漂移致门高拒率(discover 已知面) | gate_blocked 占比高 | 本设计 evidence=call_id 选择制,宿主填值——结构性绕开复述面(比稿 A 主动改进) |
| R6 | 桥侧物化失败丢条目 | 信封 ok 但 items 目录无新条 | JSONL spool 工件+幂等重放;infra 台账行必留 |
| R7 | transcript 体积与敏感信息 | 磁盘涨、key 入档 | 90 天滚动归档;宿主落盘前正则脱敏(REGEX token/key 形样);查看视图渲染层再脱敏一道 |
| R8 | 锚判例过期误导 | 老判例与现实现冲突 | 锚集季度人审(装配面,非判例改写);判例 superseded_by 链自然失效 |
| R9 | 深查问题域漂移(答非所问) | G4 answered=true 但未触问句 | DEEP 输入问句写顶(研究 §1.2 #38);G4 机检查结论段引用探针覆盖问句关键词(弱检,如实标注) |
| R10 | 成本漂移击穿月帽 | 台账月累计陡增 | §4 三闸;估算±50% 情形(月 $0.18-0.54)由 $0.42/$0.48 双闸兜住 |
| R11 | 964MB OOM(深查+matrix 并发) | 容器重启 | 串行车道互斥(既有);探针无大下载面;transcript 流式追加 |
| R12 | amend 问句积压无人答 | investigation 条目常驻 active | 摘要段报待裁积压数;8h 节奏保证可见性;snooze 归人裁调度 |

## 6. 与研究 10 条的逐条符合/弃用表

| # | 研究建议(出处行) | 裁定 | 落点/理由 |
|---|---|---|---|
| 1 | user-invoked 编排 / model-invoked 纪律二分重切(L355) | **采纳(结构对齐)** | 宿主=编排件(tick/派发/门/物化),纪律件=refs 三文件(探针手册/深查剧本/词汇表)供轮内按需注入——但健康轮无 Skill 工具,「可调用」降格为「宿主按模式附带」;入口不互调律对单轮型自然成立 |
| 2 | system prompt 信息阶梯重排(L356) | **采纳(全文执行)** | §2.3 草案:全轮必读内联(五阶段/门行/边界/降级),分支规则(剧本/词汇/形状手册)挂 refs 指针 |
| 3 | 输出改「证据+可证伪假设+推荐裁决」三件套、整轮非阻塞(L357) | **采纳** | G2 证据行(call_id 可点回工件)+G3 可证伪预测+诊断条目带推荐四键;轮全自动不等人(AFK 不卡轮),人裁异步在四键面 |
| 4 | 责任线两条原文钉死(L358) | **采纳(逐字入 prompt)** | §2.3 角色节「事实归你,裁决归人」+边界节「待四键人裁」正向终点句 |
| 5 | 判例库治理:索引非存储/概念一文件/入库三门槛(L359) | **采纳(装配面)** | 锚判例集=索引(一行 gist,§2.2.1);判例库 schema/无界不删零动;入库仍走四键判例落盘面(T1 既有),LLM 不自写判例 |
| 6 | 每轮 retro 机械误判→确定性检查(L360) | **采纳(不可挑战项,双钩子)** | §2.1.5 轮内假象钩+轮后人裁惯性钩,候选 append-only,人裁后才进代码 |
| 7 | 报告体三段+双轴并列+S/A 证据分级/门与爆炸半径(L361) | **改造采纳** | 双轴并列=异常清单(证伪轴)与诊断条目(建议轴)分节不重排不选冠;S/A 级简化为「本会话探针=硬证据,判例=旁证」两档;Merge Danger 命名弃用——四键面已是人裁门,不重复造词(一词一义,研究 §1.2 #94) |
| 8 | 建运营 GLOSSARY 带 Avoid(L362) | **弃用(现阶段)** | 主仓 GLOSSARY.md 已是词汇单一事实源(AGENTS.md 域文档节);另建运营表=第二定义处,违「复义散布」反模式(研究 §4-10)。降级兑现:prompt 用词锚现有 GLOSSARY 词条(轮次信封/判例/旗标),P2 词汇表(item-vocab.md)只管枚举闭集不管释义 |
| 9 | 三条硬纪律:AI 声明/脱敏/简报契约(L363) | **采纳** | 脱敏=探针输出 REDACTED 令(prompt)+宿主落盘正则双保险(1113 制度化);AI 声明=包脚注宿主渲染一行(host 追加段,零模型 token);简报契约=条目 action/impact/rollback 行为式无路径行号(P1 create_item 字段纪律沿承,AGENT-BRIEF.md 四性) |
| 10 | 设计它两次,3 并行结构级不同比稿(L364) | **采纳(本文即执行)** | 本稿=工具面中心;判结构级差异:能力面落点(工具面 vs 记忆面 vs 流程面)+门机制(机检布尔行 vs 其他)非措辞差异(研究 §4-23 防墙纸) |

## 7. 交付面清单与验收判据

**改(新)**:`ops/agent/prompts/health-system.md`(§2.3 草案落位)+ `refs/` 三件;`tools.mjs` health 工具面/预算/emit 门;`agent.mjs` transcript 落盘+门检+deep_hint;`lib.sh` 零改(锚注入走 agent.mjs 侧);`backend/ipdb/_ops_input.py`(新,输入派生+月闸+retro 轮后钩);`_ops_rounds.py` 仅加 item 物化+tick 挂点(spawn 契约零改);`main.py` 加 transcripts 只读端点;前端包查看面加「轮内记录」tab。
**spec 依赖(唯一)**:CAUSE_GROUPS 词表扩 LLM 诊断类(_ops_detectors.py:59-62 词表真源在 spec #152 §2,P2 走 spec 变更,不私加)。
**前置件**:10-23 两假象验证写成判例入库(锚判例首版成员)。
**不碰**:discover 面、queue_action、四键 API/前端、判例 schema、台账、旧包、spawn 契约 env 表/九词闭集。
**验收判据(可查)**:①生产 8h 节奏跑 7 天,降级率≤30%、G2 未验占比≤20%;②任一诊断条目可从 transcript 反查到支撑探针的 structuredContent(一键回算);③abuse.ch 410 场景端到端:快照旗标→证伪=真实→诊断条目→四键 agree(迁移 #159 后应转「已迁移复核」);④月账单实测≤$0.5、深查单发≤$0.01;⑤retro-candidates.md 出现≥1 条被人裁收编的确定性检查(自愈回路活体证明)。

## 8. 出处索引

- 研究基线:notes/mp-skills-design-research-2026-10-23.md(L353-364 十条建议;§1.1/§1.2 技巧表;§4 反清单)
- 现状提示词:ops/agent/prompts/health-system.md(:6 摘要员;:28 单次调用;:13 三节契约);ops/agent/prompts/discover-system.md(谓词/门/三层权限对照面)
- 工具面:ops/agent/tools.mjs(:4 零内建红线;:43 hitCap;:51 测量工具集;:236-240 health 面与预算;:253-302 语义门;:340-345 登记表;healthSnapshot/fetchUrl/safeFetch 各段)
- 宿主:ops/agent/agent.mjs(:39-43 KWS/HIT_CAP;:196-215 事件面;:224 闭合校验;ERROR_CODES/SPAWN_CONTRACT_ENV);ops/agent/lib.sh(:42/:75/:109/:120/:136/:199/:209/:239)
- 桥与车道:backend/ipdb/_ops_rounds.py(:22-23 argv+堆围栏;spawn_round/run_round);backend/main.py(:1510-1526 轮端点+串行车道)
- P1 交付面:backend/ipdb/_ops_items.py(:50-58 闭集;:198 create_item);_ops_review.py(:46-50 四键/可逆闭集;:189-191 proposal_only);_ops_detectors.py(:56-63 门线与词表;:99/:162 探测器)
- 台账实测:docs/ops/ledger.md(2026-10-19 flash/glm-5.3 各行);判例 schema:docs/ops/precedents/_schema.md
- 判例/观测:2026-10-23 健康轮两假象验证(S6404)、abuse.ch 410 真死键与 #159 迁移(观测 29943/29954)、URLhaus 5 分钟礼节(观测 29947)
