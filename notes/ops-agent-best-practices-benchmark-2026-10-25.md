# 运营 agent 架构 × 2026 最佳实践对照(2026-10-25)

判定问题:ip-radar 运营 agent 架构(十面)是否符合 2026 agent 开发最佳实践。
方法:planning-queries 管线(三竞标计划+评委融合)→ 四渠道检索(web 博客/厂商一手/学术/社区)→ 十面逐条对照。源纪律:背书只采 2026;≤2025 只作背景并标注。

## 源清单(背书级,全部 2026)

| 源 | 类型 | 要点 |
|---|---|---|
| Anthropic《Harness design for long-running application development》2026-03-24 | 厂商一手 | harness 决定长任务性能;context reset+结构化 handoff 工件优于 compaction(context anxiety);生成者/评估者分离 |
| OpenAI《A Practical Guide to Building AI Agents》2026-01-15(更新版) | 厂商一手 | HITL 两触发器=失败阈值+高风险动作;升级机制 |
| OpenAI Agents SDK docs《Guardrails and human review》(现行) | 厂商一手 | 输入/输出/工具三guardrail;校验放副作用发生处;审批中断+可恢复 state;评审超时 fail closed |
| AWS Well-Architected Agentic AI Lens | 厂商一手 | bounded autonomy/guardrails AGENTSEC04/分层人监 AGENTREL02/日志留痕 AGENTOPS05/行为监控+评估框架(日期未核实,初版疑 2025-09,按规则降为背景级) |
| AgentHarness Engineering: A Survey(openreview eONq7FdiHa,2026) | 学术 | 「任务执行可靠性对 harness 的依赖大于对底层模型的依赖」——宿主层论点直配 |
| The Systems Architecture of LLM Multi-Agent Systems(10.21863/ijkbcs/2026.14.1.004) | 学术 | 静态顺序多体管线=通信开销/KV/3.28 倍 token 成本;动态路由/DAG 编排/成本感知分派 |
| AI Agents in Industry 4.0(10.3390/app16115428,2026-05-29) | 学术 | AAS+OPC UA+LLM+强制 HITL 密码学审批门;n=117 调查 47% 认为人监督不可替 |
| louisbouchard.ai《Multi-agent is the new overengineering》2026-01-28 | 社区/博客 | workflow(步已知)/单 agent(路径须变)/multi-agent(真并行/上下文过载/硬隔离);「大多数叫 agent 的其实仍是 workflow,步已知就 fine」 |
| decodingai《From 12 Agents to 1》2026-03-26 | 社区/博客 | always start with one agent;紧耦合顺序任务单 agent+工具最佳 |
| Mark Laursen《18 个月生产 agent 复盘》2026-05-06 | 社区/博客 | 23 起事后检五大破裂:silent compaction corruption/retry storm 成本爆炸/无策略门的工具调用级联/多体 handoff 漂移/信任校准失配 |
| SixDegree《agent postmortem checklist》2026-10-08 | 社区/博客 | 事后检第一步=冻结现场(prompt/工具调用/检索/输出全存) |
| Reddit r/aiagents 生产事故帖 2026-03-15 | 社区 | 「task 自报完成」事故:用量超限后零工作仍输出 TASK_COMPLETE——按工件验证完成,勿信自述 |
| Reddit r/AgentsOfAI 失败模式汇总帖 2026-05-17 | 社区 | 边界感缺失=头号事故源(PocketOS 数据毁灭/Cursor 删生产卷);无门工具调用;多体互吵 $2500 |

背景级(≤2025,不背书):Anthropic context engineering(2025-09-29)、writing tools for agents(2025-09-11)、OWASP AI Agent Security Cheat Sheet(持续更新,未核日期)。

## 十面对照

### 1. 编排形态:workflow+内嵌模型判断 —— 符合,且踩在 2026 共识正中
十步确定性管线+模型步(TRIAGE/SYNTH/RETRO)内嵌判断,正是 2026 年「workflow when steps known」共识形态(louisbouchard 2026-01;decodingai 2026-03)。MAS survey(2026)指出静态顺序多体管线通信开销/59.4% token 消耗于迭代段——我们单管线天然免疫多体 handoff 漂移(Laursen 五大破裂之一)。无动态路由需求(监控域路径已知),不需要 DAG 编排。

### 2. 门族(guardrails):领先主流实践
OpenAI guardrails 文档分类(输入/输出/工具门、校验放副作用处、fail closed)+ harness survey「可靠性系于 harness」+ Reddit 自报完成事故(按工件验证)。我方:十 G 门中七语义门、semanticGate 逐字回引防编造、G_SYNTH 计数逐字、G_ITEMIZE manifest↔树同签、gates.json 全留痕(门旁路也记)。**偏离子项**:G_ANCHOR_SWEEP 只验罐装自洽不对拍真 DB(gates.mjs:221-244)、fusion_replay_gate rc 死门(fusion_replay_gate.py:578 无条件 return 0)——典章自设的标准抓到了自己。

### 3. 工具面:符合
few, sharp tools(Anthropic 2025-09 背景+OpenAI 2026-01 实操指南延续):测量工具/发现通道分立、动作面 10 工具闭集、agent-reach 整只不入镜像(异构故障面)。偏离子项:tools.mjs 1345 行单体(评审C6 候选)。

### 4. 上下文工程:符合,且独立收敛到 2026 处方
Anthropic 2026-03-24:context reset+结构化 handoff 工件 > compaction(context anxiety)。我方:每轮全新进程=天然 context reset;resume 三规则(16h 窗/一次/模型步齐)+轮间 handoff 指针纪律(只指不复制)+digest 只喂机器摘要+precedent_hits≤3 只给文件名。与 2026 处方逐条同构,属独立收敛。

### 5. HITL:符合,升级机制在途
OpenAI 2026-01 两触发器=失败阈值+高风险动作;Industry 4.0(2026-05)密码学审批门。我方:出口只写不动作+needs-triage/ready-for-human 人裁面=高风险动作 HITL;verdict_conflict 留痕人裁(#188 生产已活)。**偏离子项**:失败阈值升级(跨轮熔断器)=PR3b 未落;needs-triage 无超时提醒(idle 无人清)。

### 6. 可观测:符合,尾部两洞
SixDegree 冻结现场+AWS AGENTOPS05 留痕。我方:transcript/台账/门记录/RETRO diff/cost ledger 全落盘,驾驶舱宁少算不伪造。**偏离子项**:SSE 终态丢失后驾驶舱永显进行中(评审C P2);生产 apprise webhook 未配置(设计降级但欠账未清)。

### 7. 评估轨:本地重于主流,自身接线三洞
AWS lens「行为监控+评估框架而非确定性测试」+Anthropic 2026-01-21 AI-resistant evaluations。我方:回放闸门/位等价/锚巡检/月轮北星 E-5/EDD 开发环/自检件——比多数 2026 生产实践重。**偏离子项**:replay 门 rc 死门(任何 FAIL 都不退出非零,全仓无 rc 消费方)、monthly_eval.sh 单腿红最长 35 天静默(F4 只修 anchors 腿)、罐装镜像漂移面(三处 10 门硬编码;#188 conflict 字段已实证一次)。

### 8. 安全:核心符合,一处真偏离
OWASP least privilege/per-tool scoping+OpenAI「校验放副作用处、fail closed」。我方:spawn 白名单(apprise/gh issue create)、GH_WRITE_SUBCOMMANDS 单写面、SSRF 逐跳、密钥遮蔽零回显。**真偏离**:`{**os.environ, **_round_env()}` 全量继承(spawn_round:221)——ADMIN_PASSWORD/JWT/webhook 密钥全传子进程,违 2026 least-privilege(评审C4 候选);next_epoch 无跨进程锁;auth.json 无 0600。

### 9. 预算:主要偏离面
Laursen retry storm 成本爆炸=真实破裂类;我方 G_DISPATCH 单点真门(¥0.05 缺省)+预算行 8/6/6+cost ledger。**DESIGN §6 承诺四界(每轮/月度/调用哈希/墙钟)只落 1/4**,PR3b 未实现,且 DESIGN 以既成口吻写未实现项(评审B P1-2 文档一真一虚)。

### 10. 物化/数据面:内部特有,外部无直接对照
LMDB 双族/纪元/sidecar→ptr→reader 提交序崩溃不变量是强项(评审C)。**系统性缺口**:mtime 谓词代理「内容+代码版本」→42 源 harvest 演进静默休眠(2026-10-10/#188 两起同形事故);根修=needs_convert 加 harvest 版本戳(评审C2 候选)。

## 总判定

**架构形态与 2026 最佳实践高度同频:十面中七面符合(其中门族/上下文工程/评估轨三面领先或独立收敛于 2026 处方),零面落后于 2026 共识,三面带真偏离子项。** 2026 源同时验证了我方最深的两注:harness > 模型选择(survey 主题句)、按工件验证完成 > 自报(Reddit 事故)。三处真偏离全部已在修复候选单上:预算四界=PR3b、spawn env 最小化=C4、评估轨接线三洞=C5/F8 推广。无一需要推翻既有架构方向。
