# MP skills 全量设计研究 — IP Radar 运营 agent 重设计(P2)参照系

- 研究日期:2026-10-23
- 主源:本地全量 clone `/home/huxiao/.pi/agent/git/github.com/mattpocock/skills/`,快照 commit `5beb35b`(2026-10-19,与 `~/.pi` 装载版本一致),只读未改
- 范围:engineering 20 只 + productivity **7 只**(任务口径写 8,实际目录只有 7:grill-me/grilling/handoff/teach/to-questionnaire/wait-what/writing-for-agents;README 引用清单亦为 7,README.md:247-258)。总覆盖 **27 只**,非 28。
- 已读:27 只全部 SKILL.md(含 frontmatter)+ 全部 references(tdd/tests.md、mocking.md、codebase-design/DEEPENING.md、DESIGN-IT-TWICE.md、domain-modeling/ADR-FORMAT.md、GLOSSARY-FORMAT.md、ask-matt/PHASE-BOUNDARIES.md、prototype/LOGIC.md、UI.md、triage/AGENT-BRIEF.md、OUT-OF-SCOPE.md、improve-codebase-architecture/HTML-REPORT.md、setup 4 件、teach 4 件、writing-for-agents/SKILL-MECHANICS.md、wizard/template.sh)+ 根级 README/AGENTS/CLAUDE/GLOSSARY/SCOPE + `.agents/invocation.md`
- 主会话已细读 4 样本(tdd/implement/diagnosing-bugs/grilling+domain-modeling+handoff+retro)提取 8 条技巧,本文以「已提取」标注并补行号锚点;其余为「新」

---

## 1. 技巧总库存表

表内缩写:**健康**=健康轮(每日探针/异常/裁决面)、**发现**=发现轮(月度 intel 源普查)、**审阅**=审阅面(P1 四键 agree/modify/snooze/ignore 与报告体)、**判例**=判例库、**装配**=P2 提示词/agent 结构本身。引文均为英文原文,≤2 行。

### 1.1 已提取 8 条(主会话 4 样本产出,此处补精确行号)

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 1 | **回路优先**(已提取) | skills/engineering/diagnosing-bugs/SKILL.md:20 | "**This is the skill.** Everything else is mechanical." | 健康:探针先于判断——先证明「这条异常能被一条命令复现/证伪」,再谈根因 |
| 2 | **可证伪假设**(已提取) | diagnosing-bugs/SKILL.md:90-96 | "Each hypothesis must be **falsifiable**: state the prediction it makes." | 健康:每条 flag 附「若 X 为因,则改 Y 会消失」格式的假设+预测 |
| 3 | **阶段门**(已提取) | diagnosing-bugs/SKILL.md:66;improve-codebase-architecture/SKILL.md:60 | "No red-capable command, no Phase 2." / "Do NOT propose interfaces yet." | 审阅:四键出现前必须先过证据门;健康:无探针不进假设段 |
| 4 | **反模式+tell**(已提取) | tdd/SKILL.md:30-31;tdd/tests.md:63-77 | "The tell: the test breaks when you refactor but behavior hasn't changed." | 发现/审阅:运营产物模板配反例+识别征候(如「探针假红的 tell=URL 形状未带资产名」) |
| 5 | **点名失败模式**(已提取) | diagnosing-bugs/SKILL.md:66 | "jumping straight to a hypothesis is the exact failure this skill prevents" | 装配:每条运营规则写明它防的是哪个具体失败(如「不展示原始输出=汇报漂移」) |
| 6 | **小入口按需深读**(已提取) | tdd/SKILL.md:16;codebase-design/SKILL.md:111-115 | "See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines." | 装配:健康轮 system prompt 保持小入口,判例格式/探针手册挂 references 按需读 |
| 7 | **亮工作过程**(已提取) | diagnosing-bugs/SKILL.md:59 | "you have **already run at least once** (show the invocation and its output, redacted)" | 健康:异常行必须带已跑过的探针命令+原始输出,不许只给结论 |
| 8 | **非阻塞检查点**(已提取) | diagnosing-bugs/SKILL.md:98 | "Don't block on it; proceed with your ranking if the user is AFK." | 健康:整轮问题打包+推荐裁决,用户不在场也不卡管线 |

### 1.2 新发现(按 skill 目录序;共 93 条)

**ask-matt(路由器,97 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 9 | **路由器技能+防说谎纪律**(新) | skills/engineering/ask-matt/SKILL.md:3;AGENTS.md:21 | "A router over the skills in this repo" / "a new skill it never mentions… is a router that lies" | 装配:运营域建一个「何时用哪条流程」的单一入口文档;流程增删必须同步改它 |
| 10 | **主流程/on-ramp/standalone 三层地图**(新) | ask-matt/SKILL.md:13-15 | "Most paths run along one **main flow**, and two **on-ramps** merge onto it. Everything else is standalone" | 装配:运营域分主流程(健康轮)、汇入道(异常→发现轮立项)、独立件(CHANGELOG 等) |
| 11 | **上下文卫生:链前不断窗,票后新窗**(新) | ask-matt/SKILL.md:38 | "Keep steps 1–3 in **one unbroken context window**… Each `/implement` then starts fresh" | 装配:同链轮次共用推理主源;每票(每异常/每源)独立执行上下文,防交叉污染 |
| 12 | **smart zone 预算+相位边界五选项树+主/副源代价**(新) | ask-matt/SKILL.md:40;ask-matt/PHASE-BOUNDARIES.md:19,44-51 | "the window (~150k tokens…) within which the model still reasons sharply… don't push on degraded" / "Work top to bottom at the boundary. The first **yes** wins" / "Every move except **Continue** turns a **primary source** into a **secondary source**" | 装配:健康轮单轮上下文要有预算;轮间交接(判例/报告)按 continue→clear→handoff→subagent→compact 代价序选 |

**code-review(双轴评审,89 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 13 | **双轴并行子代理防污染**(新) | skills/engineering/code-review/SKILL.md:11 | "Both axes run as **parallel sub-agents** so they don't pollute each other's context" | 审阅:标准轴/spec 轴分跑(P1 已用);健康轮「探针事实轴」与「裁决建议轴」同理分列 |
| 14 | **固定点先校验,失败前置**(新) | code-review/SKILL.md:23 | "A bad ref or empty diff should fail here, not inside two parallel sub-agents." | 健康:进模型前先做确定性校验(ref 解析、快照非空),省下模型预算给真判断 |
| 15 | **恒定底线+仓优先+判断项标签**(新) | code-review/SKILL.md:38-41 | "a fixed set of Fowler code smells… that applies even when a repo documents nothing" / "**The repo overrides.**" / "always a judgement call" | 健康:内置一条「探针假红 smells 基线」(URL 形状/时区/阈值漂移),用户判例永远压过基线;基线命中只标「疑似」 |
| 16 | **并列不重排不选冠+子代理字数预算**(新) | code-review/SKILL.md:78-80;:66 | "Do **not** merge or rerank findings… Don't pick a single winner across axes" / "Under 400 words." | 审阅:两轴报告并列呈现;子代理简报硬字数上限;健康:异常列表不许重排成「最严重一条」吞掉其余 |

**codebase-design(深模块词汇,114 行+2 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 17 | **固定词汇+_Avoid_ 禁词表**(新) | skills/engineering/codebase-design/SKILL.md:12-14 | "Use these terms exactly: don't substitute 'component,' 'service,' 'API,' or 'boundary.'" | 装配:运营 GLOSSARY(异常/裁决/判例/轮次…)带 Avoid 列,报告用词出表才许用 |
| 18 | **删除测试+接口即测试面**(新) | codebase-design/SKILL.md:63-64 | "**The deletion test.** Imagine deleting the module… **The interface is the test surface.**" | 发现:每条源接入前问「删掉它异常会否集中重现」;运营工具只从对外接口验证,不刺探内部 |
| 19 | **两适配器才真缝**(新) | codebase-design/SKILL.md:65;DEEPENING.md:29 | "One adapter means a hypothetical seam. Two adapters means a real one." | 装配:agent 工具层不设抽象层,除非已有第二实现(如探针的 prod/test 双跑)证明缝为真 |
| 20 | **Rejected framings 显式节**(新) | codebase-design/SKILL.md:105-109 | "## Rejected framings" | 判例:被否口径(如「回声不算印证」)在词汇表/DESIGN 里立专节,防反复重提 |
| 21 | **依赖四分类+换不叠**(新) | codebase-design/DEEPENING.md:9-25;:34 | in-process / local-substitutable / remote-but-owned / true external; "Old unit tests… become waste… delete them" | 发现:新源按依赖类别定验证策略;替代旧检查时删旧的,不叠两层门 |
| 22 | **设计它两次:3+ 并行子代理激进不同+有主见**(新) | codebase-design/DESIGN-IT-TWICE.md:21;:43 | "Each must produce a **radically different** interface" / "Be opinionated: the user wants a strong read, not a menu." | 装配:P2 重设计可派 3 个并行子代理出激进不同的健康轮架构,终稿给主见推荐而非选项堆 |

**domain-modeling(主动建模,74 行+2 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 23 | **主动建模 vs 被动读词之辨**(新) | skills/engineering/domain-modeling/SKILL.md:8 | "Merely *reading* `GLOSSARY.md` for vocabulary is not this skill" | 装配:健康轮只消费词汇=被动;改判例/裁决枚举那一刻才触发建模流程 |
| 24 | **冲突即刻点名+代码交叉验证**(新) | domain-modeling/SKILL.md:46;:58 | "call it out immediately… check whether the code agrees. If you find a contradiction, surface it" | 健康:用户口径与判例库/探针实现冲突时当场点名,不许静默选边 |
| 25 | **情景压力测试+惰性创建**(新) | domain-modeling/SKILL.md:54;:40 | "stress-test them with specific scenarios" / "Create files lazily: only when you have something to write" | 判例:新裁决入库前拿边界情景压测;判例文件只在真有裁决时建,不预铺骨架 |
| 26 | **ADR 三门槛**(新) | domain-modeling/SKILL.md:68-72;ADR-FORMAT.md:37 | "**Hard to reverse**… **Surprising without context**… **The result of a real trade-off**. If any of the three is missing, skip" | 判例:入库门槛同构——难逆+无上下文会奇怪+真有权衡,缺一不入 |

**grill-with-docs(纯链式装配,7 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 27 | **纯链式装配:7 行技能=两次 Skill 调用**(新) | skills/engineering/grill-with-docs/SKILL.md:7 | "Call the Skill tool twice, for 'grilling' and 'domain-modeling'." | 装配:运营流程层可以薄到只做「调用哪几个纪律原语」;原语不复制进流程 |

**implement(17 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 28 | **约定缝上驱动子技能**(新) | skills/engineering/implement/SKILL.md:11 | "Call the Skill tool with 'tdd' where possible, **at pre-agreed seams**." | 审阅:改判例只在预先约定的写回点(裁决 API)落笔,不许旁路改库 |
| 29 | **分级反馈节奏**(新) | implement/SKILL.md:13 | "typechecking regularly, single test files regularly, and the full test suite once at the end" | 健康:轻检查每异常跑、单源检查高频跑、全量门每轮末一次——反馈粒度分档 |

**implement-spec(40 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 30 | **上下文指针稀疏通信+后台并发**(新) | skills/engineering/implement-spec/SKILL.md:15;:17 | "Communicate primarily through **context pointers**… Don't duplicate information already available via pointers" / "run in the background where possible" | 健康:轮报告只放指针(判例 id/快照路径),重活派后台代理,主窗不复制内容 |
| 31 | **任务图+前沿工作法+探索代理仓外共享笔记**(新) | implement-spec/SKILL.md:13;:23;:34 | "a **task graph**… always a **frontier** of tickets which are ready" / "save its markdown notes in a directory outside the repo, accessible by all future subagents" | 发现:源普查按阻塞边排图,取「就绪前沿」并发;探索产物存共享目录供后续轮引用 |

**improve-codebase-architecture(71 行+HTML ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 32 | **热点定界:YAGNI+git log 热点**(新) | skills/engineering/improve-codebase-architecture/SKILL.md:20;:23 | "Scope before you scan: YAGNI… put extra weight on the parts… that have recently changed" / "walk back a good stretch of the commit history to find the codebase's hot spots" | 发现:月轮先定界再扫(近期变更源优先),不做全域均匀普查;审阅面异常同理 |
| 33 | **产物出仓:写临时目录,仓库零落地**(新) | improve-codebase-architecture/SKILL.md:39 | "Write a self-contained HTML file to the OS temp directory so nothing lands in the repo." | 健康:中间产物(HTML 报告/草稿)出仓,只有终态工件入判例库/notes |
| 34 | **推荐强度三档徽章+ADR 翻案门**(新) | improve-codebase-architecture/SKILL.md:50;:56 | "one of `Strong`, `Worth exploring`, `Speculative`, rendered as a badge" / "only surface it when the friction is real enough to warrant revisiting the ADR" | 健康:异常/建议带置信三档;翻既有判例须真摩擦,不例行重审 |
| 35 | **候选菜单→用户选→才进深挖**(新) | improve-codebase-architecture/SKILL.md:60-64 | "ask the user: 'Which of these would you like to explore?'… call the Skill tool with 'grilling'" | 发现:普查先出候选清单,人选定后才深读该源——同 P1「发现→条目→四键」链 |

**pr(170 行,体量大半是代码围栏)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 36 | **三段体+最小视觉+禁前言**(新) | skills/engineering/pr/SKILL.md:14-33;:37 | "## Summary / ## Evidence / ## Merge Danger" / "Pick the smallest view that makes the key point clear" / "Skip all preambles and keep prose brief" | 审阅:运营报告三段体(摘要最小视图/前后证据/风险判);禁开场白 |
| 37 | **证据分级 S/A+单向/双向门+爆炸半径**(新) | pr/SKILL.md:162-170 | "Screenshots are S-tier… Execution-based evidence is A-tier" / "**Door:** one-way or two-way" / "**Blast Radius:**" | 审阅:裁决行附证据等级;每条运营改动标单向/双向门+波及面,供四键决断 |

**prototype(26 行+2 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 38 | **一次性答一问+问题写顶**(新) | skills/engineering/prototype/SKILL.md:8;prototype/LOGIC.md:20 | "throwaway code that answers a question. The question decides the shape" / "Before writing code, write down what… question you're prototyping" | 发现:对新源的探查脚本按「回答一个问题」设计,问题写在产物顶部,防答非所问 |
| 39 | **状态全显+非开发者语言**(新) | prototype/SKILL.md:25;prototype/LOGIC.md:5 | "print or render the full relevant state so the user can see what changed" / "hand it to a non-developer… it speaks their language, not the code's" | 健康:面向用户的健康面板用运营词汇全量显状态,变化可点见 |
| 40 | **纯模块可迁移+变体必须结构级不同**(新) | prototype/LOGIC.md:22-24;prototype/UI.md:54 | "a single `<script>` block… could be lifted out" / "Variants must be **structurally different**… it's wallpaper" | 装配:P2 方案对比须结构级差异(工具面/模型面/流程面),禁换皮三稿 |
| 41 | **原型留档为主源**(新) | prototype/SKILL.md:26 | "capture the prototype itself as a **primary source**: commit it to a throwaway branch" | 判例:被否方案也留档可回算——呼应「证据永不灭失」哲学 |

**research(12 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 42 | **背景代理读、主线不停**(新) | skills/engineering/research/SKILL.md:6 | "Spin up a **background agent** to do the research, so you keep working while it reads." | 发现:源背景调查派后台,健康轮主线不被读文档阻塞 |
| 43 | **主源追责+逐条引用**(新) | research/SKILL.md:10-12 | "Investigate the question against **primary sources**… Follow every claim back to the source that owns it." | 健康/发现:每条主张挂一手源(探针输出/上游文档),禁转述链 |

**retro(44 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 44 | **环境改进回路:机械→确定性检查,判断→标准**(新) | skills/engineering/retro/SKILL.md:7;:19;ask-matt/SKILL.md:34 | "improvements to the coding agent's **environment**, not the code" / "a mechanical one… gets a deterministic check, full stop" / "Mechanical mistakes become deterministic checks; judgement calls become coding standards" | 健康:每轮后跑 retro——GeoLite 404 这类探针假红应收编为确定性 URL 形状检查,不靠模型每轮重判 |
| 45 | **七类改进候选清单+no-ops 排查**(新) | retro/SKILL.md:17-23 | "Navigation… Automated checks… Coding standards… Tool economy… **No-ops**… Information access" | 装配:运营 prompt 的定期体检清单;专查不改行为的死指令 |
| 46 | **上下文压力不对称:标准由审阅面执行**(新) | retro/SKILL.md:31-35 | "The implementation agent has the most **context pressure**… the review agent should be responsible for imposing coding standards" | 装配:运营规则检查放轻载的审阅端,重载的执行端 prompt 只留必要纪律 |
| 47 | **AGENTS/CLAUDE 极简+导航指针化**(新) | retro/SKILL.md:41-42 | "they should be used incredibly sparingly, usually only for **navigation pointers**" | 装配:运营 system prompt(现 34 行)再瘦身,只剩指针+不可省判例 |

**setup-matt-pocock-skills(118 行+4 seed)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 48 | **探索→呈现→确认→写,一次配置**(新) | skills/engineering/setup-matt-pocock-skills/SKILL.md:15 | "This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write." | 装配:运营域初始化(判例库/词汇表/裁决枚举)同此四步,写前必确认 |
| 49 | **推荐答案领场,一词可接受**(新) | setup-matt-pocock-skills/SKILL.md:36 | "Lead each section with the recommended answer so the user can accept it in a word." | 健康:裁决问句全部带推荐选项;审阅四键的默认键即推荐 |
| 50 | **规范角色→实际标签映射表**(新) | setup-matt-pocock-skills/triage-labels.md:5-13 | "The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings" | 审阅:运营状态的规范名(裁决/挂起/忽略)与存储枚举分表映射,提示词只说规范名 |

**tdd(38 行+2 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 51 | **pre-agreed seams:未确认缝不写测试**(新) | skills/engineering/tdd/SKILL.md:22 | "**Test only at pre-agreed seams.**… No test is written at an unconfirmed seam." | 审阅:回放/等价检查只落在与用户约定过的面上,不自选观测点 |
| 52 | **mock 只在系统边界**(新) | tdd/mocking.md:3-14 | "Mock at **system boundaries** only… Don't mock: Your own classes/modules, Internal collaborators" | 健康:探针可替身只限外部世界(HTTP 时钟),自家判定逻辑不许 mock |

**to-spec(75 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 53 | **不访谈只综合**(新) | skills/engineering/to-spec/SKILL.md:7 | "Do NOT interview the user; just synthesize what you already know." | 健康:快照→报告轮禁再问用户已知项,只综合;要问走 grilling 通道 |
| 54 | **缝先行+理想数为一+用户确认**(新) | to-spec/SKILL.md:15-17 | "The fewer seams across the codebase, the better - the ideal number is one. Check with the user" | 装配:运营写回面收敛到单一裁决 API(ADR 0006 同向);扩面前先过用户 |
| 55 | **spec 无路径无码**(新) | to-spec/SKILL.md:55 | "Do NOT include specific file paths or code snippets. They may end up being outdated very quickly." | 判例:判例正文禁文件路径/行号引用,写行为契约;防漂移 |

**to-tickets(105 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 56 | **垂直切片+单上下文窗尺寸**(新) | skills/engineering/to-tickets/SKILL.md:29-36 | "Each slice cuts a narrow but COMPLETE path through every layer… sized to fit in a single fresh context window" | 发现:每源工单纵切到底(探查→接入→验证),不按层横切 |
| 57 | **阻塞边显式+前沿工作法**(新) | to-tickets/SKILL.md:38;:65 | "Give each ticket its **blocking edges**… Work the **frontier**" | 发现:源工单间依赖显式化,可并行取就绪票 |
| 58 | **宽改造 expand–contract 例外**(新) | to-tickets/SKILL.md:40 | "sequence it as **expand–contract**… keeping CI green batch to batch" | 发现:全库级口径变更(如源数统计)用扩缩法分批,不硬切 |
| 59 | **粒度问卷+prefactor**(新) | to-tickets/SKILL.md:44-56;:23 | "Does the granularity feel right?… Should any tickets be merged or split further?" / "'Make the change easy, then make the easy change.'" | 发现:批次立项前问粒度/依赖/拆合三问;先易后难排 prefactor 票 |

**triage(112 行+2 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 60 | **AI 生成声明头部**(新) | skills/engineering/triage/SKILL.md:13-17 | "Every comment or issue posted… **must** start with: *This was generated by AI during triage.*" | 审阅:所有入判例库/入 issue 的运营产物顶部带 AI 生成声明 |
| 61 | **双检查:冗余+先例**(新) | triage/SKILL.md:70 | "(a) **redundancy**: search for an existing implementation… (b) **prior rejection**: read `.out-of-scope/*.md`" | 判例:新裁决先查「已实现」与「已否」双库,报告查过哪里 |
| 62 | **先验证再 grill**(新) | triage/SKILL.md:74 | "Before any grilling, check that the claim holds up… A confirmed verification makes a much stronger agent brief." | 健康:flag 先复现(探针重跑)再进裁决问;审阅:改判请求先验证现判例成立否 |
| 63 | **概念级去重 KB+已实现不入库**(新) | triage/OUT-OF-SCOPE.md:17;:88 | "One file per **concept**, not per issue" / "recording it would poison the dedup checks with false rejections" | 判例:一概念一判例文件(防同源重复/谱系派生双计);已实现≠已拒绝,不入否决库 |
| 64 | **不重问已答+维护者直通信任**(新) | triage/SKILL.md:112;:90 | "check whether the reporter has answered… Don't re-ask resolved questions" / "If the maintainer says… trust them and apply the role directly. Skip grilling." | 健康:轮间衔接先读上轮判例;用户直接给裁决时走快速通道免问 |
| 65 | **简报=契约:耐久>精确、行为式、验收可独立验、出界显式**(新) | triage/AGENT-BRIEF.md:3-38 | "the agent brief is the contract" / "**Durability over precision**… Don't reference file paths" / "independently verifiable" / "State what is out of scope" | 审阅:四键面产出的「待办简报」按此四性写;防 agent 自行脑补邻域 |

**wayfinder(128 行,最重)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 66 | **地图=索引非存储+低分辨率装载+按需缩放**(新) | skills/engineering/wayfinder/SKILL.md:23;:29 | "The map is an **index**, not a store… a decision lives in exactly one place" / "The whole map at low resolution, loaded once per session… found by query" | 装配:运营状态文档(NEEDS/判例索引)只存指针+一行 gist,明细在原判例;上下文只装低清版 |
| 67 | **产出决策非交付物**(新) | wayfinder/SKILL.md:13 | "produce decisions, not deliverables" | 健康:裁决轮的输出是决定(裁决+判例),不是执行;与 never-auto-execute 裁决同构 |
| 68 | **雾战图:可陈述才开票;出界永不毕业**(新) | wayfinder/SKILL.md:88;:99 | "whether you can state the question precisely now, _not_ whether you can answer it now" / "Out-of-scope work never graduates" | 发现:NEEDS.md 记「想问而无槽」=雾;能精确陈述才立项;明确出界的永不复活除非重画目的 |
| 69 | **先认领后干活+单会话单票**(新) | wayfinder/SKILL.md:67;:105 | "A session **claims** a ticket… **first**, before any work, so concurrent sessions skip it" / "never resolve more than one ticket per session" | 发现:并发轮次先认领防双干;一轮专注一源一事 |
| 70 | **HITL/AFK 二分+agent 不代言人类**(新) | wayfinder/SKILL.md:75 | "HITL (human in the loop…) the agent never stands in for the human's side of it" | 健康:flag-only 线=HITL 票;运营 agent 永不替用户答裁决问——0db23018 判例的形式化依据 |
| 71 | **具名引用,禁裸 id**(新) | wayfinder/SKILL.md:17 | "refer to it by that name, never by a bare id, number, or slug… A wall of `#42, #43` is illegible" | 健康:报告引用判例/源用名+链接,不许只丢 hash |

**wizard(44 行+template.sh)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 72 | **向导化人类专用步骤+库固定不可改**(新) | skills/engineering/wizard/SKILL.md:8;:10 | "walks a human, step by step, through a manual procedure that's tedious to re-explain to an AI every time" / "the library… is identical in every wizard; that consistency is the point: never hand-edit it" | 装配:需要人手工的运营步骤(key 续费/上游迁移三选一)生成向导脚本而非每次重讲;共享库段冻结 |
| 73 | **不知则说+不发明步骤+静态追踪验证**(新) | wizard/SKILL.md:29;:43 | "Where you don't actually know… say so and ask… never invent steps" / "Don't run it end-to-end yourself… Trace it statically instead" | 健康:探针知识盲区显式说,不编上游行为;agent 不亲手跑需人值守的流程,静态核对代替 |
| 74 | **负触发写进 description**(新) | wizard/SKILL.md:3 | "Don't invoke this for steps the agent can perform itself." | 装配:工具/技能描述写清「何时不该触发」,防误用(注意与 negation 失效原则的张力,见 §4-9) |

**grill-me(7 行)/ grilling(30 行,可复用访谈原语)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 75 | **设计树+前沿轮问**(新) | skills/productivity/grilling/SKILL.md:6-8 | "Map this as a **design tree**… The **frontier** is every decision whose prerequisites are already settled" | 健康:裁决问按依赖分层,一轮只问前沿(先决已定的),不问悬空问题 |
| 76 | **每问带推荐答案+yes 措辞**(新) | grilling/SKILL.md:13-15;:24 | "➡️ <your recommended answer>" / "Word each question so 'yes' accepts your recommended answer." | 健康:轮问格式 Q+➡️推荐;四键默认键=推荐答案 |
| 77 | **事实归代理,决策归人**(新) | grilling/SKILL.md:28 | "Finding _facts_ is your job, never the user's… The _decisions_ are the user's: put each to them and wait." | 健康:探针/翻文档归 agent,裁决归用户——P2 责任线的原始表述 |
| 78 | **不确认不动手**(新) | grilling/SKILL.md:30 | "Do not act on it until the user confirms you have reached a shared understanding." | 健康:裁决写回前置共享确认,呼应 never-auto-execute |

**handoff(16 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 79 | **指针不复制+建议技能节**(新) | skills/productivity/handoff/SKILL.md:12;:10 | "Do not duplicate content already captured in other artifacts… Reference them by path or URL instead" / "Include a 'suggested skills' section" | 健康:轮间交接文档只引判例/快照路径;附「下轮该读哪些纪律文件」节 |
| 80 | **用途先行裁剪交接**(新) | handoff/SKILL.md:16 | "treat them as a description of what the next session will focus on and tailor the doc accordingly" | 健康:健康轮→发现轮的交接按下一轮用途裁剪,不做万能摘要 |
| 81 | **脱敏先行**(新) | handoff/SKILL.md:14;diagnosing-bugs/SKILL.md:14 | "Redact any sensitive information" / "write `<REDACTED>` in its place" | 健康:进报告/判例的探针输出先脱密钥(1113 事故教训的制度化) |

**teach(140 行+4 ref)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 82 | **使命先行+含糊即追问**(新) | skills/productivity/teach/SKILL.md:75;teach/MISSION-FORMAT.md:29 | "your first job should be to question the user on why" / "A bad mission is worse than no mission." | 发现:轮的目的(为什么查这批源)写明并先行;含糊先问再动手 |
| 83 | **学习记录=ADR 同构+覆盖≠学会**(新) | teach/LEARNING-RECORD-FORMAT.md:5;:40 | "the teaching equivalent of ADRs" / "Coverage is not learning. Wait for evidence." | 判例:运营「已核实事实」须有证据才记;跑过≠结论成立 |
| 84 | **流畅 vs 存储强度+最近发展区+永不信参数知识**(新) | teach/SKILL.md:41;:81;:30 | "Fluency can give the user an illusory sense of mastery" / "zone of proximal development" / "Never trust your parametric knowledge." | 健康:报告别把「看起来顺」当已验证;agent 对上游源的事实一律探针/文档取证,禁参数记忆断言 |

**to-questionnaire(54 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 85 | **问发送不问主题,问题打向缺口**(新) | skills/productivity/to-questionnaire/SKILL.md:9 | "**Grill the send, not the subject.**… The questions in the document then target the **gap**" | 健康:向用户发问只问用户独有信息(偏好/预算/裁决),环境事实自查 |
| 86 | **「不知道」也是有效答案+一问一事**(新) | to-questionnaire/SKILL.md:36;:40 | "Partial answers and 'I don't know' are useful: flag anything you're unsure of" / "Every question is one idea, never compound" | 健康:裁决问允许「不知道」并降级为 needs-info;禁复合问句 |

**wait-what(7 行)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 87 | **重讲协议:受控英语+词汇表语言**(新) | skills/productivity/wait-what/SKILL.md:7 | "Re-pitch that: give me a little bit of context, talk in ASD-STE100 Simplified Technical English" | 健康:用户看不懂报告时的标准降级重讲动作;报告语言锚运营 GLOSSARY |

**writing-for-agents(81 行)+SKILL-MECHANICS(22 行)+`.agents/invocation.md`**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 88 | **上下文指针学**(新) | skills/productivity/writing-for-agents/SKILL.md:12 | "the pointer's _wording_, not its target, decides when the agent reaches the material" | 装配:判例/工具描述的措辞即触发器;指针弱=方差 bug,先改词再考虑内联 |
| 89 | **两负载模型(context/cognitive)**(新) | writing-for-agents/SKILL.md:22-27 | "**Context load**… spending tokens and attention whether or not it fires… **Cognitive load** is the cost on the human" | 装配:运营文件每加一段先问付的是哪种负载;人的索引成本花在裁决点,别处自动化 |
| 90 | **信息阶梯+渐进披露(分支判据)**(新) | writing-for-agents/SKILL.md:31-39 | "inline what every branch needs, and push behind a pointer what only some branches reach" | 装配:34 行 prompt 重排为阶梯——全轮要的留文内,分支才要的(如 snooze 规则)挂指针 |
| 91 | **领头词(leading word)**(新) | writing-for-agents/SKILL.md:63 | "a compact concept already living in the model's pretraining… reach for an existing word first" | 装配:运营提示词用预训练里已有的强词(回路/前沿/判例/红线)压缩指令;自造词须先定义 |
| 92 | **否定失效→正向措辞**(新) | writing-for-agents/SKILL.md:74 | "steering by prohibition drags the forbidden behaviour into context and makes it _more_ available" | 装配:「不要自动执行」类禁令配正向目标句(「每条以轮问收尾交人」);纯禁令半失效 |
| 93 | **完成判据=可查+穷尽**(新) | writing-for-agents/SKILL.md:47-52 | "The strongest criteria are both checkable and exhaustive." / premature completion | 健康:每步终态给可查判据(「每条 flag 均附探针输出」),防提前收工 |
| 94 | **环境即事实源+单一事实源**(新) | writing-for-agents/SKILL.md:78-79 | "The **environment** is a source of truth too… a document that restates it is a **cache**" | 装配:prompt 不复述环境可查之物(源清单/工具 --help);一词一义一处定义 |
| 95 | **no-op 靠跑检验+沉积修剪**(新) | writing-for-agents/SKILL.md:80 | "settle it by running the document, not by debate" / "the default fate is **sediment**" | 装配:运营 prompt 改版须跑对照判无效句;定期修剪防沉积 |
| 96 | **触发分支写法+二分负载权衡**(新) | .agents/invocation.md:5-6;SKILL-MECHANICS.md:9-12 | "The test…: _could the model usefully reach for this autonomously?_" | 装配:运营纪律文件按「模型能否自主取用」决定常驻(带触发 description)还是人唤(禁触发) |
| 97 | **显式 Skill 工具调用+一调一技能**(新) | .agents/invocation.md:16;:20 | "expressed as an explicit instruction to **call the Skill tool**… Naming the tool is what gets it fired" / "two calls, not one" | 装配:运营流程间依赖写「调用 X」而非散文提及;两依赖=两次显式调用 |
| 98 | **共享参考宿主=可被调用的技能**(新) | SKILL-MECHANICS.md:9;:14 | "reference needed by several skills lives in one place" / "Push it to a plain file outside the skill system" | 装配:多条运营轮共用的纪律(如判例格式)做成可被各轮调用的单一 model-invoked 参考 |

**仓库级文件(README/SCOPE/AGENTS)**

| # | 技巧 | 出处 | 关键原文 | 运营映射 |
|---|------|------|----------|----------|
| 99 | **双部件准入 bar:观察失败+合哲学**(新) | SCOPE.md:7-10 | "**Observed failure.**… A hypothetical improvement ('it would be better if...') does not clear this part." | 发现:新源/新规则立项须有「真实会话中观察到的失败」,假想改进不立项 |
| 100 | **四失败模式总纲**(新) | README.md:113-207 | "#1 The Agent Didn't Do What I Want… #2 Way Too Verbose… #3 The Code Doesn't Work… #4 Ball Of Mud" | 装配:运营域四问——没对齐?词汇冗?无回路?已成泥?每条运营痛先归因四型再开方 |
| 101 | **user-invoked 编排 / model-invoked 纪律二分**(新) | README.md:211;invocation.md:8 | "user-invoked skills… their job is to orchestrate… hold the reusable discipline. A user-invoked skill may invoke model-invoked skills, but never another user-invoked one" | 装配:P2 的核心分层律:轮入口(人唤)只编排,纪律(模型可唤)可复用;入口不得互调 |

**技巧总数:101(已提取 8 + 新 93)。** 主会话 4 样本(tdd/implement/diagnosing-bugs/grilling+domain-modeling+handoff+retro,计 7 只)贡献了已提取 8 条与 §1.2 中 #27-29、#51-52、#75-81 等;其余 20 只贡献其余新条目。

---

## 2. 仓库级结构模式

### 2.1 frontmatter 字段语义

| 字段 | 语义 | 证据 |
|------|------|------|
| `name` | 目录同名 kebab-case;跨 harness 中性(invocation.md:16「Dropping the leading `/` keeps this harness-neutral」) | 全部 27 只目录名=frontmatter name |
| `description` | **双面性**:model-invoked=模型面向,须带触发分支;user-invoked=人类面向一行摘要,「Strip trigger lists」 | invocation.md:5-6 原文 |
| `disable-model-invocation: true` | 锁死为人类专属;配套 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false`,「a skill is user-invoked in both harnesses or neither」 | AGENTS.md:19;invocation.md:5,10 |
| `argument-hint` | 提示用户该传什么(仅 2 只用:handoff「What will the next session be used for?」、teach「What would you like to learn about?」)——两例都把参数当「用途裁剪」入口 | handoff/SKILL.md:4;teach/SKILL.md:5 |
| `metadata.credits` | 外来技巧署名(pr 技能标 Dex Horthy/show-me 源),配套 CREDITS.md 说明为何内联不依赖 | pr/SKILL.md:4-9;pr/CREDITS.md:3 |

### 2.2 description 的 when-to/when-not 写法

- 正触发句式:「Use when the user wants…, mentions 'grill' trigger phrases」(grilling/SKILL.md:3)、「Use when the user says 'diagnose'/'debug this', or reports something broken/throwing/failing/slow」(diagnosing-bugs/SKILL.md:3)——把用户原话词汇直接编进触发面。
- 负触发句式:wizard「Don't invoke this for steps the agent can perform itself.」(wizard/SKILL.md:3)。这是全仓唯一 description 负触发;与 writing-for-agents:74 的否定失效原则有张力——说明 MP 把负触发只用在「防误调用」这一硬闸门,不作日常指令。
- 触发分支规则:writing-for-agents/SKILL.md:14「One trigger per branch. Synonyms that rename a single branch are one branch written twice; collapse them」;:17「Front-load the leading word」。
- 实测长度:model-invoked description 中位 ~25 词,最长 code-review 68 词(全触发场景列举);user-invoked 中位 ~16 词,最短 retro/pr 7 词。description 是常驻 context 负载(invocation.md 视角,writing-for-agents/SKILL.md:24),按分支数付账。

### 2.3 skill 间链式调用

- 标准句式:「Call the Skill tool with "tdd"」(implement/SKILL.md:11)、「Call the Skill tool twice, for "grilling" and "domain-modeling"」(grill-with-docs/SKILL.md:7、triage/SKILL.md:76、wayfinder/SKILL.md:79)——显式点名工具、点名次数,「two calls, not one」(invocation.md:20)。
- 链式合法性仅限下行(user→model,README.md:211);user-invoked 的前置条件写成人话让 agent 转告:「tell the user to run `/setup-matt-pocock-skills`」(invocation.md:22;implement-spec/SKILL.md:9;code-review/SKILL.md:13)。
- 共享原语:grilling 是「the reusable interview primitive behind grill-me, grill-with-docs, triage, wayfinder and improve-codebase-architecture」(README.md:257);codebase-design 是被 tdd/ICA 引用的词汇层(tdd/SKILL.md:26「a reference to consult, not a session to run」)。
- 路由器 ask-matt 单向枚举所有 user-invoked 流程;「a router that lies」即失职(AGENTS.md:21)。

### 2.4 文件组织(SKILL.md + 平级 references,渐进披露)

- 结构 = `SKILL.md`(入口)+ **平级**参考文件(非 references/ 子目录:tdd/tests.md、mocking.md;codebase-design/DEEPENING.md、DESIGN-IT-TWICE.md;triage/AGENT-BRIEF.md、OUT-OF-SCOPE.md…)+ `agents/openai.yaml`(每技能一份)+ 可选 `scripts/`(wizard/template.sh、diagnosing-bugs/hitl-loop.template.sh)。
- 命名分层:技能内强参考多用全大写(AGENT-BRIEF.md、LOGIC.md、UI.md、PHASE-BOUNDARIES.md、SKILL-MECHANICS.md、*-FORMAT.md);setup 的配置种子用小写(domain.md、triage-labels.md、issue-tracker-*.md)。大写=load-bearing 纪律文档的视觉信号(观察,MP 未明文规定——不确定处明说)。
- 披露判据:「inline what every branch needs, and push behind a pointer what only some branches reach」(writing-for-agents/SKILL.md:39);入口文件以「See [X](X)」一行挂指针(tdd/SKILL.md:16;codebase-design/SKILL.md:113-114)。
- 跨技能**不**允许文件级互链:共享内容靠 Skill 调用,「not deep `../other-skill/FILE.md` cross-references」(invocation.md:16);两个 user-invoked 共享的参考必须推到技能系统外的普通文件(SKILL-MECHANICS.md:14)。
- 产物面同样分层:GLOSSARY.md(词汇)+docs/adr/(决策)惰性创建(domain-modeling/SKILL.md:40);报告类产物出仓入临时目录(improve-codebase-architecture/SKILL.md:39)。

### 2.5 命名与大小纪律(实测统计)

- 命名:全 kebab-case;单词优先(tdd、pr、research、retro、triage、wayfinder、wizard);同族前缀共享(grill-me/grill-with-docs/grilling)。
- 体量(本机实测 wc):SKILL.md 主体 7~170 行,中位 ~54 行,均值 ~62 行;最薄三只 grill-me(7 行/22 词)、grill-with-docs(7 行/35 词)、wait-what(7 行/60 词)全是「薄入口/纯链式/单协议」;最厚 wayfinder(128 行/2075 词)、ask-matt(97 行/1958 词)、writing-for-agents(81 行/1777 词)都是**地图/参考**类——编排与纪律可以厚,执行面技能(implement 17 行/research 12 行)保持薄。
- 仓级硬纪律:禁 em-dash,「never do a blind character substitution」(AGENTS.md:25);promoted 桶必须三处同步(README+plugin.json+bucket README,AGENTS.md:9-17);docs 页四节模板 What it does/When to reach for it/Common questions/It's working if(AGENTS.md:17)。

---

## 3. 装配层与宿主层专用模式(上下文怎么进模型/宿主怎么管模型)

1. **入口-纪律二分是装配第一律**:user-invoked 编排、model-invoked 持纪律、入口不互调(README.md:211;invocation.md:8)。7 行的 grill-with-docs 证明编排层可以薄到一句链式调用(grill-with-docs/SKILL.md:7)。
2. **上下文指针是装配的基本单位**:措辞决定触达,「A must-have target behind a weakly worded pointer is a variance bug」;常驻指针每词每轮付费(writing-for-agents/SKILL.md:12,14)。运营映射:34 行健康 system prompt 里每行都是常驻指针,按此定价。
3. **信息阶梯+渐进披露保护注意力**:三档(文内步骤/文内参考/披露参考),披露判据=分支;过挤 bury 步骤会变「coin-flip」方差(writing-for-agents/SKILL.md:31-39)。
4. **两负载预算**:context load(常驻,机器付)vs cognitive load(人类索引,人付);「Not a cost to minimise: it is the price of human agency」(writing-for-agents/SKILL.md:22-27)。运营四键面是人类裁决点,值得付 cognitive load;其余应下沉为自动检查。
5. **主/副源经济学**:除 Continue 外每个相位边界动作都把主源降为副源;Continue 先排除(「costs nothing and loses nothing」),compact 是底不是首选(PHASE-BOUNDARIES.md:21,44-51,40)。运营映射:判例=决策的主源,报告里只准 gist+指针(wayfinder/SKILL.md:23 同律)。
6. **smart zone 预算与不硬撑**:~150k 内模型才锐;接近时「don't push on degraded」,在相位边界 compact(ask-matt/SKILL.md:40)。glm-5.3-flash 小窗下更要按阶段切轮。
7. **链前不断窗、票后新窗**:grill→spec→tickets 一条不compact 的窗;每票 fresh(ask-matt/SKILL.md:38)。运营映射:裁决问+证据生成同窗(实现要推理主源 verbatim,PHASE-BOUNDARIES.md:21),执行写回每判例新上下文。
8. **稀疏通信+指针传递**:implement-spec 子代理间「communicate primarily through context pointers… Don't duplicate」(implement-spec/SKILL.md:15);handoff 同律「Reference them by path or URL instead」(handoff/SKILL.md:12)+「suggested skills」节(:10)+按用途裁剪(:16)。
9. **后台化与并发**:research 背景代理「keep working while it reads」(research/SKILL.md:6);implement-spec 后台 implementer+merger 子代理(implement-spec/SKILL.md:17,32);任务图 frontier 并发(:34)。运营映射:发现轮背景查源,健康轮主线不等。
10. **上下文压力不对称决定职责落位**:实现重载(探索+写+调)、审阅轻载(只收 diff);标准执行权放审阅端(retro/SKILL.md:31-35)。运营映射:规则核查放审阅面轻载轮,健康轮重载端只留最小纪律。
11. **AGENTS/CLAUDE 极简指针化**:「incredibly sparingly, usually only for navigation pointers」;CODING_STANDARDS 超 1000 行才加导航指针(retro/SKILL.md:41-42)。
12. **环境改进回路(retro)**:机械错→确定性检查、判断类→标准,分类先行(「Default to building the check over writing the rule」,retro/SKILL.md:19);环境而非代码(ask-matt/SKILL.md:34)。这是把运营每轮教训制度化的模板。
13. **词汇表是宿主层省 token 器**:「the agent also **spends fewer tokens on thinking**, because it has access to a more concise language」(README.md:165);固定词汇+Avoid(codebase-design/SKILL.md:12)。运营 GLOSSARY 同功。
14. **领头词+正向措辞+no-op 检验**:预训练强词压缩行为(writing-for-agents/SKILL.md:63);禁令半失效须配正向目标(:74);no-op 句删整句、靠跑判(:80)。
15. **宿主双 harness 同步**:Claude(`disable-model-invocation`)与 Codex(`openai.yaml policy`)必须同开关(invocation.md:10)。IP Radar 运营模块若换执行引擎(pi spawn),同律:触发语义要逐宿主对齐。

---

## 4. 反清单(MP 明确反对的写法 → 运营等价物)

| # | MP 反模式 | 出处原文 | 运营等价物(要防的) |
|---|-----------|----------|---------------------|
| 1 | Tautological test(同义反复断言) | tdd/SKILL.md:31 "it passes by construction and can never disagree with the code" | 健康轮「探针显示正常所以正常」式自证;验收值须来自独立已知好源(tdd/tests.md:74-76 字面量例) |
| 2 | Horizontal slicing(先写全部测试再写全部实现) | tdd/SKILL.md:32 "Bulk tests verify _imagined_ behavior" | 发现轮先铺全套检查表再接源;应纵切:一源到底再下一源 |
| 3 | Implementation-coupled(测内部协作) | tdd/SKILL.md:30 "mocks internal collaborators, tests private methods" | 健康轮检查写死实现细节(探针内部状态),实现一改即假红 |
| 4 | Mock 自家模块 | tdd/mocking.md:10-14 "Don't mock: Your own classes/modules… Anything you control" | 运营回放里替身自家裁决逻辑,只该替身外部世界 |
| 5 | "log everything and grep" | diagnosing-bugs/SKILL.md:108 | 健康轮无差别全量抓日志再人肉筛;探针必须映射到具体假设 |
| 6 | 未打标 debug 日志 | diagnosing-bugs/SKILL.md:110 "Untagged logs survive; tagged logs die." | 运营临时插桩无 `[DEBUG-xx]` 前缀,事后清不掉 |
| 7 | 无回路先立假说 | diagnosing-bugs/SKILL.md:66 | 健康:flag 未复现就写根因——正是 10-23 两假异常差点成的错 |
| 8 | no-ops 指令 | retro/SKILL.md:22;writing-for-agents/SKILL.md:80 "pays load to say nothing" | 运营 prompt 里模型默认就会做的客套句、恒真句 |
| 9 | 否定式导向(未配正向) | writing-for-agents/SKILL.md:74 "_Don't think of an elephant_" | 「不要慌报/不要啰嗦」类裸禁令;改成正向目标句 |
| 10 | 复义散布+无价值缓存 | writing-for-agents/SKILL.md:41,79 "scattering fragments one meaning";"a document that restates it is a **cache**" | 判例口径散在多文件;prompt 复述源清单/工具输出等环境可查物 |
| 11 | 沉积不修剪 | writing-for-agents/SKILL.md:80 "adding feels safe and removing feels risky" | 运营 prompt 只增不删,半年后没人知道哪行还活 |
| 12 | 模糊完成界(premature completion) | writing-for-agents/SKILL.md:49 "invites **premature completion**" | 健康轮「已生成报告」即宣告完成,判据不可查 |
| 13 | 路由器说谎 | AGENTS.md:21 "is a router that lies" | 运营入口文档列了已废流程/漏了新流程 |
| 14 | agent 代言人类(HITL 票) | wayfinder/SKILL.md:75 "the agent never stands in for the human's side" | 健康:agent 自答裁决问再替用户确认——never-auto-execute 判例的违例形态 |
| 15 | 未确认即行动 | grilling/SKILL.md:30 "Do not act on it until the user confirms" | 轮结论未共享确认就写回判例库 |
| 16 | 问用户可自查的事实 | grilling/SKILL.md:28 "don't ask the user for anything you could look up yourself" | 健康轮问「源多久没更新了」(探针可答) |
| 17 | 重问已答问题 | triage/SKILL.md:112 "Don't re-ask resolved questions" | 轮间衔接不读上轮判例,重复问已裁决项 |
| 18 | 已实现入否决库 | triage/OUT-OF-SCOPE.md:88 "would poison the dedup checks" | 判例库把「已存在功能」记成「已否决」,污染后续去重 |
| 19 | 简报带路径行号 | triage/AGENT-BRIEF.md:15-16;to-spec/SKILL.md:55 "Don't reference file paths: they go stale" | 审阅面待办写死 file:line,仓库一动全废 |
| 20 | 前言/ throat-clearing/客套 | pr/SKILL.md:37;HTML-REPORT.md:123 "No hedging, no throat-clearing" | 运营报告开场白、对冲语;wins 写「更易维护」等非词汇表词(HTML-REPORT.md:121) |
| 21 | 合并重排双轴/选总冠军 | code-review/SKILL.md:78-80 | 审阅面把标准/spec 两轴发现揉成一个 Top1,一轴掩另一轴 |
| 22 | 假设性改进立项 | SCOPE.md:9 "A hypothetical improvement… does not clear this part" | 运营新规则无观察失败支撑即上马 |
| 23 | 换皮变体/墙纸 | prototype/UI.md:54,109 "it's wallpaper" | P2 方案三稿只差措辞;源探查脚本三份只改 URL |
| 24 | 原型接真库/求通用 | prototype/LOGIC.md:63-64 "Don't wire it to the real database… Don't generalise" | 探查脚本直写生产库、顺手做成通用框架 |
| 25 | 发明不存在的步骤 | wizard/SKILL.md:29 "never invent steps that may not exist" | 健康:对上游 dashboard 行为不确定时编路径让用户跑 |
| 26 | 参数知识断言 | teach/SKILL.md:30 "Never trust your parametric knowledge." | 运营对上游 API 行为、源格式凭记忆下结论 |
| 27 | 复制他 artifact 已有内容 | handoff/SKILL.md:12 | 交接文档复述判例正文而非引用 |

---

## 5. 对 P2 设计的直接建议(10 条,每条挂证据)

1. **按「user-invoked 编排 / model-invoked 纪律」重切运营层**:健康轮/发现轮入口由人(或 cron 以人名义)触发、只做编排;判例格式、探针纪律、裁决枚举做成可被任一轮调用的共享纪律件。依据:README.md:211 二分律 + invocation.md:8 单向不变量 + SKILL-MECHANICS.md:9「reference needed by several skills lives in one place」。
2. **把 34 行 system prompt 按信息阶梯重排**:全轮必读的留文内(词汇表指针、终态判据、脱敏令),分支才要的(snooze 规范化、STIX 导出规则)挂指针文件;判据=「inline what every branch needs, push behind a pointer what only some branches reach」(writing-for-agents/SKILL.md:39)。这与主会话已提取的「小入口按需深读」(tdd/SKILL.md:16)同源,但给了**分流判据**。
3. **健康轮输出改为「证据+可证伪假设+推荐裁决」三件套,整轮非阻塞**:每条 flag 附已跑探针命令+原始输出(diagnosing-bugs/SKILL.md:59)+假设预测(:90-96)+➡️推荐答案措辞(grilling/SKILL.md:13-15,24),用户 AFK 不卡轮(diagnosing-bugs/SKILL.md:98)。直接消解「too dumb」抱怨:模型的工作从复述变成有据判断。
4. **裁决责任线用两条 MP 原文钉死**:「Finding facts is your job… The decisions are the user's」(grilling/SKILL.md:28)+「the agent never stands in for the human's side」(wayfinder/SKILL.md:75)。写进 DESIGN.md 作为 never-auto-execute(判例 0db23018)的形式化表达:flag-only 线=HITL 票。
5. **判例库按「索引非存储+概念级一文件+已实现不入否决库」治理**:决策只住一处、索引只留一行 gist(wayfinder/SKILL.md:23);一概念一文件防同源重复/谱系派生双计(triage/OUT-OF-SCOPE.md:17);入库三门槛=难逆+无上下文会奇怪+真权衡(domain-modeling/SKILL.md:68-72)——与 glossary「宁少算勿多算」哲学直接对齐。
6. **每轮闭环跑 retro,把机械误判固化为确定性检查**:探针 URL 形状校验(GeoLite 404 案例)、snooze 时区规范化等归「deterministic check, full stop」,判断类才进判例标准(retro/SKILL.md:19;ask-matt/SKILL.md:34)。这是运营模块自愈回路,替代人工逐轮纠偏。
7. **报告体统一三段+双轴并列**:摘要=最小视觉、证据=前后对照带 S/A 级(pr/SKILL.md:36-37,162-164)、风险=单向/双向门+爆炸半径(:168-170);异常轴与裁决轴并列不重排不选冠(code-review/SKILL.md:78-80)。四键面即 Merge Danger 判的运营版。
8. **建运营 GLOSSARY(带 _Avoid_),报告用词出表才许用**:收口「异常/假红/裁决/判例/轮次/谱系」等自造词,并让模型省 token(README.md:165;codebase-design/SKILL.md:12;HTML-REPORT.md:121「Don't write 'easier to maintain'… terms aren't in the glossary」)。与主仓 GLOSSARY.md 机制同构,MP 证明该机制本身可迁移到运营域。
9. **所有运营产物三条硬纪律**:AI 生成声明头部(triage/SKILL.md:13)、脱敏先行(diagnosing-bugs/SKILL.md:14)、简报契约化——耐久>精确、行为式、验收可独立验、出界显式(triage/AGENT-BRIEF.md:9-38)。1113 key 事故与 CHANGELOG 口径问题的制度化预防。
10. **P2 方案比稿用「设计它两次」**:派 3 个并行子代理出结构级不同的健康轮架构(工具面/记忆面/流程面),用户读问题域说明时代理同时跑,终稿给主见推荐(DESIGN-IT-TWICE.md:17,21,43「the user wants a strong read, not a menu」);候选先呈现、人选定才深挖(improve-codebase-architecture/SKILL.md:60-64)。

---

## 6. 不确定与未覆盖

- 任务口径「productivity 8 只」与实际 7 只的差异未能在仓内找到解释(README/AGENTS 均列 7);不排除把 in-progress/ 中的某只(如 loop-me)误计入。已按 27 只全量覆盖。
- `misc/`、`in-progress/`、`deprecated/` 三桶与 `.out-of-scope/` 八篇、`.agents/writing-docs.md`、docs/ 人读页未细读(非任务范围);若 P2 需要「被拒概念全集」可补读 .out-of-scope/。
- 「大写文件名=强纪律参考」是本人观察推断,MP 无明文;引用时按此置信度对待。
- 描述词数/行数为本机 wc 实测(快照 5beb35b),上游演进后数字会漂。
