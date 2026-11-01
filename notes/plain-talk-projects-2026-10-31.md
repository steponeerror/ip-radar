# 让 AI 说人话:项目调研 — 2026-10-31

调研问题:世上有哪些「让 AI 说人话/去 AI 味」的项目,与本项目 2026-10-30 立的「中文说人话」规则(全局 ~/.pi/agent/AGENTS.md)什么关系、有什么可偷。检索面:web(exa)/GitHub/paper-search(arXiv),2026-10-31 实查。

## 全景

生态分四层:英文通用「去 AI 味」层、编码 agent 专用层、中文专属层、学术基准层。共同手法:禁词表 + 句式禁令 + 先给答案;分化点:有没有评测、保不保证据、是否工具化。

## 英文通用层

- **astrofoundry/talk-normal** — 多 harness 写作 skill(Claude Code/Codex/Gemini CLI/Qwen/Kimi/**Pi**/Copilot/Zed/Cursor):答案先行、指令句 ≤20 词/描述 ≤25 词、动词替换表(use>utilize、show>surface)、规则传子代理、代码与引用逐字不动、破坏性操作豁免(先停再说)。<5000 字符可贴指令块。
- **hexiecs/talk-normal**(同名不同仓)— 单 system prompt,英/中双语;实测 GPT-4o-mini 缩短 73%、GPT-5.4 缩短 72% 且信息不丢。**规则回归迭代法**:线上漏出的规则进 regressions/ 记违规数与修复轮;「不是X,而是Y」句式四轮从每回复 6 次压到 0,**关键修复 = 移除规则里的负面例子——模型会把反例当模板逐字抄**。ChatGPT 版压进 1500 字符仍保留承重规则。
- **CoderSufiyan/plainspeak** — npm voice 层;三禁(禁词表/填充语/em dash)+ rules/voice.md 单真相,各 adapter 共读。
- **dead-developers/vibespeak** — Claude Code skill:省 token −61%(对照 caveman −67% 但保留术语解释);三档强度(short/normal/chatty);安全例外 = 删数据/危险 git/打钱时反而展开完整警告;代码/报错/路径/commit 逐字不动。
- **nicojan/humanize-text-prompt** — 改写 prompt,规则按同行评审研究分层(词汇/结构/语气/语篇/质地五层,如名词化、对偶反射、情感平坦)。
- **alessio-ds/no-clank** — 六族规则(对比句式/标点/~50 词禁表/hedge/宏大开头/结构习惯);实测输出短 ~60%、禁词 4-7→0。
- **tenkenco/declaude** — 服务化:Claude-English→plain English,MCP + Claude Code hook(渲染时重写、零 Claude token、跑自托管 Qwen2.5-14B,文本不进商业 API)。

## 编码 agent 专用层(技术解释)

- **Tradelord223/plain-english** — 「**简化解释,不简化证据**」:真值锚点(结果/证据/确定性/义务/范围/数字/风险/精确 token 压缩后必须原样存活);反盲替换表(serialize→说 JSON 仅当确知是 JSON;idempotent→解释实际的重试与重复副作用保证,不是「跑两遍安全」了事);压缩下限(短答案不许藏失败检查/不确定/风险);混合受众分层(先给结论层,专家机制沉后)。哲学与 ip-radar 哲学 2「无证据即无话」同构。
- astrofoundry/talk-normal 的进度更新规范(每轮一句进展、错误给位置+原因+修法、禁道歉)也属此层。

## 中文专属层

- **AmsonntagChow/shuo-ren-hua** — 名字就叫「说人话」,改编自 shreyashankar/plain-writing-skill(docwriter-org 上游,英文)。25 条规则四组(用词语气/句子段落/标点格式/避免套路),每条带改前改后例;中文特有反模式:互联网黑话、官腔、一逗到底、三连排比、量词悬空、「不只是X更是Y」;AI 写的和人写的都治。**评测方法最认真**:evals/behavior_cases.json 断言先定死不许迁就结果;发现性测试(提示不点名,看 agent 会不会自选 skill,近似任务测误触发)+ 提升测试(同输入带/不带规则双跑,剔两组都过的断言——没人失败的断言测不出差别)。
- **Raymondhou0917/speak-human-tw** — 繁体版:38 种 AI 写作痕迹,顺手校正中国用语与半形标点。
- **tomerose/stop-slop** — 41 种反模式的去 AI 味写作技能(Claude/Cursor/Copilot)。
- **yiancode/noai-flavor** — 开源指南库:开头「在当今社会…」、每段 emoji 装饰、永远「首先/其次/最后」。
- **chengzhi-c/natural-talk** — 首句直给、问 A 答 A、数量词严格(要 3 条就恰好 3 条)。
- **Moyouchi/humanizer-zh-pro** — 不止去痕,重建中文写作的节奏质地。
- **androidZzT/anti-ai-smell** — **零依赖中文 linter + 词表 + Claude skill**:确定性检出 AI 高频中文词并给「人会怎么说」的替换——把说人话从 prompt 纪律变成可测工具。
- hexiecs/talk-normal 自带中文版(见英文层)。

## 学术/基准面

- NIST **PLABA**(Plain Language Adaptation Benchmark,生物医学摘要→平实语言改写)是本任务的正经基准;arXiv 2609.17398(2026,NTU)用 GPT-4o-mini/Gemini-1.5-pro/LLaMA + MoA + QLoRA 做 PLA——「保义简化」有评测传统,不是民间新发明。文本简化(text simplification)是 NLP 老领域;这批项目的价值是把研究结论落成 agent 纪律与工具。

## 对照与可偷件(按 ADR 0015 三问预审)

现有规则已覆盖:禁英文行话/禁自造压缩词/术语首现一句解释/报告同律/说人话优先于简洁——**整包装任一 skill 都属重复装,拒**。生态增量三件值得吸收:

1. **shuo-ren-hua 的确定性评测法**(断言先定、双跑对照、剔无人失败的断言)→ 给自家规则配「说人话回归集」,规则改动过闸;与今日 ub-mode 裁决的「工具测量」思路同宗。
2. **Tradelord223/plain-english 的真值锚点 + 压缩下限** → 恰好补中文规则没写的「简化不许丢证据」条款(与哲学 2 呼应,落成写作纪律:数字/失败检查/不确定性/义务压缩后必须存活)。
3. **hexiecs/talk-normal 的负面例子判例**(模型会把规则里的反例当模板逐字抄)→ 自写规则时反例慎给:给结构不给原句,或反例后必须紧跟正例并标注「照抄即违规」。

## 星标排行(2026-10-31 实查,gh api)

| 星 | 项目 | 形态 |
|---|---|---|
| 1866 | hexiecs/talk-normal | 单 system prompt,英/中,回归迭代法 |
| 1100 | Raymondhou0917/speak-human-tw | 繁体中文去 AI 味 skill,38 痕迹 |
| 740 | shreyashankar/plain-writing-skill | 英文上游(shuo-ren-hua 改编源) |
| 99 | chengzhi-c/natural-talk | 中英规则(skill) |
| 18 | yiancode/noai-flavor | 指南库 |
| 15 | Tradelord223/plain-english | 编码 agent 真值锚点 skill |
| 12 | tomerose/stop-slop | 41 反模式 skill |
| ≤6 | 其余(humanize-text-prompt 6 / shuo-ren-hua 3 / anti-ai-smell 2 / plainspeak 2 / declaude 1 / no-clank 1 / vibespeak 0 / astrofoundry talk-normal 0) | |

要点:头三名里两个是中文项目(中文需求最痛);方法最认真的 shuo-ren-hua 仅 3 星(年轻);pi 插件形态的 astrofoundry/talk-normal 刚发布 0 星。相邻领域 anti-sycophancy(反油顺)最高 22 星(talhapythoneer/anti-sycophancy-prompt,42 篇文献声援),说明「反 AI 腔」整体仍是小生态,高星集中在头部两三个。

## 换框检索:「优化 AI 输出」的高星全景(2026-10-31,gh api 实查)

用户换框:从「去 AI 味」(后处理小生态)拉宽到「优化 AI 输出」——星量级完全不同:

| 星 | 项目 | 层 |
|---|---|---|
| 309,680 | obra/superpowers | ① agent 纪律/技能框架(用户体系曾用,2026-10-20 改指 MP) |
| 175,365 | f/awesome-chatgpt-prompts | ② 提示词库 |
| 79,691 | dair-ai/Prompt-Engineering-Guide | ② 提示工程知识库 |
| 56,959 | hesreallyhim/awesome-claude-code | ① agent 纪律/配置集合 |
| 38,949 | anthropics/prompt-eng-interactive-tutorial | ② 官方教程 |
| 38,864 | stanfordnlp/dspy | ③ 程序化提示优化(提示当参数,指标驱动) |
| 26,667 | promptfoo/promptfoo | ④ 提示/输出评测回归 |
| 23,917 | SuperClaude-Org/SuperClaude_Framework | ① agent 人格/纪律框架 |
| 21,812 | guidance-ai/guidance | ③ 结构化生成 |
| 19,212 | confident-ai/deepeval | ④ LLM 输出评测 |
| 15,987 | dottxt-ai/outlines | ③ 约束解码/结构化输出 |
| 14,084 | jxnl/instructor | ③ 结构化输出(Pydantic) |
| 9,587 | brexhq/prompt-engineering | ② 实战指南 |
| 4,223 | SylphAI-Inc/AdalFlow | ③ 提示优化框架 |
| 3,779 | zou-group/textgrad | ③ 文本梯度优化 |
| 1,985 | mlc-ai/xgrammar | ③ 高性能语法约束解码 |
| ~1.9k | hexiecs/talk-normal | ⑤ 后处理改写(原调研头部) |

结论:①用户已在层①(superpowers 血统→SDD+MP);②层⑤说人话是整个栈里最小的层;③对用户真正的新面孔是层④(promptfoo/deepeval——给提示/输出配评测回归,与回放闸门/评测文化同构)与层③的 DSPy 思路(提示当可优化参数、指标驱动,同「测量建言」哲学,但接入成本高,缓议)。

## 来源

GitHub/web 经 agent-reach(exa/gh 后端)2026-10-31 检索;各仓 README 原文摘录;上游谱系 plain-writing-skill → shuo-ren-hua 经两仓 README 互证;论文 arXiv 2609.17398 经 paper-search。
