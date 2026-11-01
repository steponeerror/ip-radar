# 业界如何解决「agent 优化文档/词汇表致人类主事人失读失审」(2026-10-31)

调研问题:AI 辅助开发项目中,面向 agent 优化的文档与领域词汇表让人类主事人失去阅读与审计能力——业界与学界如何解决?
我方背景:GLOSSARY 曾为 agent 优化积累 60+ 自造中文行话;2026-10-31 已落地四层闸门(改名批 / 命名纪律:先查现成通用词→路人测试→人裁点头才入表 / 出处格式守卫测试 / ADR 0016 受众改判)。
检索方法:planning-queries 三投标者+裁判融合计划(出处见文末);执行 = agent-reach web/github(22 查询,14 页直读)+ paper-search(9 查询);原料存 .worktrees/research-industry-worker-output.md。

## 一句话答案

**业界没有单一解法,是一套分工:受众分离(README 给人、AGENTS.md 给 agent)+ 术语审批工作流(提案→评审→发布→归档,人握批准权)+ 标准背书(ISO 704 明写术语工作为"人与人无歧义交流")+ 机检只管格式、真人管语义(cloze/读者实测)+ 旧词拒用列表进 CI。** 我们的四层闸门与这套分工同构,且在出处死链守卫、改名对照表、判例存档三处走在前面;主要缺口是旧词拒用列表还没进 CI。

## 七面发现(每条带来源与日期)

### 1. 受众分离是官方规范立场,不是工程猜测

- AGENTS.md 官方规范:"README.md files are for humans… AGENTS.md complements this by containing the extra, sometimes detailed context coding agents need"(agents.md,自称 60k+ 开源项目使用)。业界主流是**按读者分文件**,不是一份文档服务两读者。
- OpenAI Codex:AGENTS.md 发现链(全局→逐目录→就近覆盖)+ 32KiB 默认上限(learn.chatgpt.com)。GitHub Copilot 2025-08-28 起支持同一文件——多工具收敛(github.blog changelog)。
- 工程实践指认漂移根源:"it has no required structure, which is both its strength and the reason it drifts";解法主张="one source that the files are generated from, and a check that runs on every change"(docs.groundrule.dev,2026-10)。
- DevRel Almanac 双受众论:"Pick a canonical name for each concept and use it consistently… Models may reproduce whichever terminology they retrieve"(chabot.dev)——agent 会复述它检索到的任一版本,所以概念命名必须钉死二选一。
- **对照**:我方「主人直读优先,agent 可读免费」比业界"分文件"更严格(单受众裁决);业界"agent 会复述检索词"解释了为什么行话会自我强化。

### 2. 术语审批工作流是成熟产业(数据治理平台标配)

- Macquarie 大学《Glossary Policy》:一词一定义;「什么词必须定义」判定清单(易混淆/跨部门不同义/用于法规/比标准英语更精确);生命周期五阶段 Proposed→Assigned→In Development→Reviewed→Approved;**Steward(批准权)与 Custodian(起草权)分权**;废词归档不删除;年度复审(policies.mq.edu.au)。
- OpenMetadata(开源数据治理平台):指定 Reviewer 后新词强制 Draft 态,只有 Reviewer 能改状态(docs.open-metadata.org);OneTrust 四态 Proposed/Under Review/Approved/Archived(2026-10-15 更新);Microsoft Purview 术语创建即 draft,须显式 publish 全员可见(learn.microsoft.com)。
- Prolyz:"The trail is the point. Six months later 'who decided that active means twelve months' has an answer with a name and a date";反模式判例=自己批自己的草稿、无 owner 的词必漂移(2026-10-04)。
- **对照**:我方「人裁点头才入表」=无工具化的同构;留痕我方靠 git blame + ADR 承担(单仓场景够用,不必加状态机字段——宁少算)。

### 3. 开源基金会旗舰:CNCF/K8s 的词汇表治理

- CNCF Glossary 准入条款:"Not every term will be admitted. To be included in the Glossary, they should be **established and widely-used** cloud native concepts"(glossary.cncf.io/contribute,2025-05-27)——与「先查现成通用词」同款准入闸。
- CNCF 双通道审批:技术批准后必须有 editor 复核;"If a term is heavily edited, the editor must request a technical approver to review it again **to ensure the meaning wasn't altered**"(contributor-ladder,2025-03-31)——防「改文改义」,与我方 SDD 审查+人裁同构。
- CNCF 风格指南第一条:"Use simple, accessible language, avoiding technical jargon and buzzwords";建议草稿冷却几天再回看(glossary.cncf.io/style-guide)。
- Kubernetes:风格指南由 SIG Docs 集体决议修改;专设 "Avoid jargon and idioms" 节(理由:英语二语读者);每词一文件 + shortcode 全站复用同一份定义(kubernetes.io,2026-04-28)。
- **对照**:K8s shortcode = 单一真相源思想的工程化;我方 GLOSSARY+守卫测试同构。

### 4. 标准层:ISO/法规把「人」写在条文里

- **ISO 704:2022 术语工作原则**:"The goal of terminology work… is, thus, a clarification and standardization of terminology for **communication between humans**"(BSI 预览正文)——术语学的百年根基就是为人类交流;「为 agent 优化」从根上偏离学科目标。造词七原则:透明性/语言经济/一致性/得体性/可派生/语言正确/母语优先(ATA Chronicle 2020 转述 2009 版,附实践判例:常用「长透明形+短经济形」并存)。
- **ISO 24495-1:2023 平实语言**:四原则(读者得所需/易找到/易理解/能使用);"Plain language focuses on how successfully readers can use the document **rather than on mechanical measures such as readability formulas**"(iteh.ai FDIS 直读)——我方「机检判不出人话,归人裁」的标准级背书;原则 4 要求用真实读者评估(5.4 节)。
- **ASD-STE100 Issue 9**(航空受控英语):写作规则 53 条 + 受控词典 ~900 词一词一义一词性;"Rule 1.10 Do not use regional, slang, or jargon words as technical nouns";"Rule 1.11 Do not use different technical nouns for the same item"(asd-ste100.org 官方 PDF)——「受限词汇+人可审计」的最强既有行业标准。
- **EU AI Act 第 14 条**:高风险 AI 监督者须"properly understand the relevant capacities and limitations"、须警觉"automation bias"(自动化依赖)、须能"disregard, override or reverse the output"(ai-act-service-desk.ec.europa.eu)——「主事人必须读得懂、且能推翻」的法规级表述;automation bias 正是「失审」的风险机制命名。
- **对照**:ISO 704 目标条款直接支持我方受众改判;EU AI Act 14 条给「为什么必须主人可读」提供法规级理由。

### 5. 大厂风格指南:词表管制 + 造词前置检查

- Microsoft Writing Style Guide:"If you mean the same thing, use the same word";"Aim for one term, one concept";"**Don't create a new term if an existing one serves your purpose. If you must create a new term, verify that it isn't already being used to mean something else**";查证顺序=A–Z 词表→Merriam-Webster→行业权威词典(learn.microsoft.com)——我方「先查现成通用词」的逐字大厂版。
- Google 风格指南:word list 分级(Use with caution/Don't use);jargon 处置四问决策树(能否绕开?能否更具体?一次→括号解释;贯穿→首现括号或链接可信定义);技术写作课程:"If the term already exists, link to a good existing explanation. (**Don't reinvent the wheel.**)";"if you rename a term in the middle of a document, your ideas won't compile (in your users' heads)";疑似同义词会让读者怀疑有隐含区分(developers.google.com)。
- **对照**:我方命名纪律与大厂指南同构;大厂「查证顺序」值得抄进 GLOSSARY 表头(中文侧=全国科技名词委规范名词库)。

### 6. 机检守卫:Vale 生态(词面合规)+ cloze(真人验证)

- Vale(开源 prose linter)Vocab 机制:每词库两纯文本文件 accept.txt/reject.txt;accept 条目自动生成 substitution 规则强制精确拼写;consistency 检查=同文两形只许其一(docs.vale.sh)。工程样例:发布管线跑术语 substitution+existence 规则(docs-as-code.com,2025-07-21)。版本化约定实践:musher-dev/engineering-conventions(2026-09,requirement 永久 ID+Rego/JSON Schema/Vale 三检,各仓 pin 版本)。
- NN/g cloze 测试:挖空每第 6 词,目标受众真人填,≥60% 判可懂;"Readability is a property of the text itself… Comprehension is a combined property of the text and a specific user segment"(nngroup.com,2011;Sandia 国家实验室 2018 双测佐证 doi:10.2172/1489628)。
- **对照——这是主要缺口**:我方守卫测试只查「出处存在性」(test_glossary_anchors),不查「词面合规」(旧词拒用)。**可采纳:把 GLOSSARY 改名对照表的旧词列做成 CI 拒用列表**(等价 Vale reject.txt),防旧词回流——与 #259 延后批同票或单开。cloze 真人测试我方不采纳(单主人场景,人裁即真测试;AI 模拟路人是伪测试)。

### 7. 中文现场:全国科学技术名词审定委员会(国家级「人裁点头」)

- 章程:国务院授权,审定公布的名词「具有权威性和约束力」;委员会 ≤150 人,分学科委员会 15–35 人;**会议 2/3 出席方可开、决议须出席 3/4 通过**;审定公布七步程序(确定任务→编订→专业委员会审定→公开征求意见→组织审核→主任委员批准→公布)(cnterm.cn)。
- 《科学技术名词审定原则及方法》(2016 施行):单义性=「一个概念仅确定一个与之相对应的规范的中文名称」;多名分五档(正名/全称简称/又称/俗称/曾称);科学性=「对不科学的,易引起概念混乱的名词应予以纠正」;**民族性=「意译为主,适当采用音译,尽量不造新字」**;**新词两步快轨=「发布试用」→「审定公布」**;预公布 1 年(cnctst.cn)。
- 工作手册(2012):三审同行专家「一般应不少于 10 人」;换届保留 1/3 委员保连续;跨学科「副科服从主科」。
- **对照**:名词委是「人裁点头」的国家级行业形态;「意译为主、尽量不造新字」正是我方「先查现成通用词」的中文规范背书;「发布试用→审定公布」两步=我方 crystallise(稳定复现)条件的制度版。中文侧查证源可引规范名词库(termonline.cn)。

## 学术面(2026 年新研究;全部 paper-search 直检)

| 论文 | 日期 | 要点 |
|---|---|---|
| Context Rot(Treude & Baltes, arXiv 2606.09090) | 2026-06 | CLAUDE.md/AGENTS.md/.cursorrules 会腐化;356 仓抽样 23.0% 有陈旧代码引用;建议复用文档-代码一致性检查器——我方出处守卫的学术同类与定量佐证 |
| Harness Engineering(Galster et al., arXiv 2602.14690v5) | 2026-02/06 | 2853 仓实证:Context Files 主导配置,AGENTS.md 成互操作标准 |
| Human-Centered AI-Assisted Terminology Work(San Martin, arXiv 2512.18859v4) | 2025-12,更新 2026-10-15 | 术语学界立场:LLM 不可靠(错误/幻觉/偏见),terminologist 不可替代;"meaningful human control"与高自动化兼容——人裁的学科级印证 |
| What GenAI Means for Terminological Definitions(San Martín, arXiv 2402.16139) | 2024-02 | post-editing terminography:机器起草定义、术语学家修订——「命名裁决件」的行业原型 |
| The year of silent failures(Korolev, 2025-12) | 2025-12 | 提出 verification debt/knowledge rot;组织逐渐失去验证、解释、复现决策的能力——「失审」的问题类命名;Human Verification Rate 等度量 |
| SAT 透明度模型(Chen et al., 2018,339 引) | 2017-18(理论) | agent 从工具变队友,透明度支撑校准信任且不增负担——GLOSSARY/ADR 作为透明度工件的理论定位 |
| AIRA(Parris, arXiv 2604.17587) | 2026-04 | AI 代码「安静失败」模式(表面能跑、保证被腐蚀);AI 文件高危问题 0.435/文件 vs 人类 0.242(1.8×)——失审侧实证 |
| Security Degradation in Iterative AI Code Gen(Shukla et al., arXiv 2506.11022) | 2025-05 | LLM 迭代「改进」5 轮后严重漏洞 +37.6%;结论=人类验证环节不可省 |

## 负面证据(为什么不能只靠公式/为什么行话真的贵)

- Redish & Selzer 1985(IEEE Trans. Prof. Comm.,全文直读):可读性公式对成人技术文档"INADEQUATE… focus the writer's attention on words and sentences and draw attention away from important sources of readers' problems";至多当旧文档初筛。Redish 2000/Schriver 2000(ACM JCD):公式为儿童课本开发;同文本不同公式分差达 3 个年级。→ 我方拒绝伪机检的学术背书。
- Martínez, Mollica & Gibson(Cognition 2022):合同语言难懂主因是「写得差」(长距离句法依赖)而非概念专业化——n≈1000 万词 + N=184 实验。
- Kickresume 实验(2025-04,50 人):行话版 vs 平实版——理解 5/10 vs 8/10、信任 2.8 vs 4.5、敢行动 60% vs 90%、**一小时后回忆 12 要点 vs 34 要点且行话组有失真**;85% 入门级员工对行话持负面态度(非同行评审,量级参考)。
- CHI 2026:行话自动解释需个性化过滤,定义轰炸伤参与。

## 对照总表:业界做法 vs 我方四层闸门

| 维度 | 业界主流 | 我方现状 | 判定 |
|---|---|---|---|
| 受众 | README(人)/AGENTS.md(agent)分文件 | 主人直读优先,agent 可读免费 | 我方更严,兼容 |
| 新词准入 | Microsoft「别造新词」/CNCF「established」/名词委「意译为主」 | 先查现成通用词→路人测试→人裁 | 同构 ✓ |
| 稳定复现条件 | 名词委「发布试用→审定公布」;CNCF 冷却几天 | crystallise(概念稳定复现才命名) | 同构 ✓ |
| 审批人 | Steward/Custodian 分权;双通道(技术+文字);名词委 3/4 决议 | 人裁点头 + SDD 审查环 | 同构 ✓ |
| 留痕 | Prolyz「审批即留痕」;OneTrust 状态机 | git blame + ADR 0016 | 单仓够用 ✓ |
| 机检 | Vale accept/reject + consistency(CI 强制) | test_glossary_anchors 只查出处存在性 | **缺口:旧词拒用列表未进 CI** |
| 真人验证 | cloze ≥60%;ISO 24495 原则 4;Mintlify 混合验证 | 人裁(用户本人) | 单主人场景 ✓ |
| 判例存档 | (该子领域少见) | ADR 0016 + 改名对照表(grep 可达) | **我方在前** |
| 死链守卫 | Context Rot 建议复用(研究前沿) | 出处守卫测试已运行(4 绿) | **我方在前** |

## 可采纳清单(按性价比排序)

1. **旧词拒用列表进 CI**(等价 Vale reject.txt):把 GLOSSARY 改名对照表旧词列(θ 简写除外——代码面)做成守卫测试第二断言,活文档零旧词从「一次性批」变「永久闸」。可与 #259 同批或单开票。
2. **查证顺序写进 GLOSSARY 表头**:中文新词先查全国科技名词委规范名词库(termonline.cn)与统计界通行译名,再查工程界——Microsoft 查证顺序的中文版,一行成本。
3. (缓办)对上游反馈:Groundrule/Vale 生态无「中文 GLOSSARY+出处守卫」公开样例,我方实践可作为回馈素材;MP domain-modelk 上游提「prefer established vocabulary」建议仍挂缓办。

## 新鲜度声明

agent 文档子领域为 2026 年才成型的新领域:所引最热论文两篇在 **2026-10-15 / 10-13** 仍在改版,其余集中在 2026-02~06;标准与法规面(ISO 704:2022、ISO 24495-1:2023、ASD-STE100 Issue 9、EU AI Act)为现行版;中文现场为现行章程与 2016 施行规范。arXiv 纯日期排序会丢关键词(实测),故新鲜度以相关性排序论文的版本日期为准。负面面两篇基石文献(1985/2000)为方法论经典,不构成过期。

## 检索出处(planning-queries 六块之⑥)

3 投标者(glm-5.3-flash,独立盲拟)+ 裁判(glm-5.3,评分 8/7/8,零否决);融合=逐维取冠+裁判三盲区补位(中文现场/ASD-STE100/cloze 验证,三者全部命中成为本笔记第 4/6/7 节)。贫瘠记录:「术语漂移」「linguistic antipatterns」在 semantic/arxiv 两轮零命中(该库检索不到,由 Context Rot 引用面兜底);github 词表配置面单薄(低星仓),由 Vale 官方文档补齐;ISO/ANSI 站 Cloudflare 拦截 4 处,均有替代一手通道(快照/iteh.ai FDIS)。
