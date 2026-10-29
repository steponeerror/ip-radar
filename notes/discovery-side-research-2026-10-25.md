# 发现侧强化调研:发现轮管线化 + 笼内模型推理的 2026 实践对照

调研日:2026-10-25。触发:用户「运营侧能力很弱,没充分发挥模型能力,发现侧没描述」+「这个方向的强化需要调研一下」。
采集纪律:只采 2026 源(≤2025 仅背景标注)。三源:web/厂商/论文(scout 40644ab5,18 卡)、开源实作源码(scout bceced8c,10 项目卡,shallow clone 实读)、学术面(主会话 paper-search,有效命中 5)。
原始全文:`~/.pi/agent/sessions/--home-huxiao-dev-pi-ip-lookup-tool--/subagent-artifacts/outputs/40644ab5-*/context.md` 与 `bceced8c-*/context.md`(逐字保留,本件为合成层)。

---

## 一、五问总判定(三源合议)

| 问 | 判定 | 三源依据要点 |
|---|---|---|
| Q1 发现轮管线形状 | **支持;且在 SOC 域已是成熟形态** | web:planner/worker/observer 三角色+步间只传结论(卡1);LangChain 教科书步集=规划→并行采集→评估→综合(卡2)。OSS:研究 agent 侧主流是「自由循环+数字帽」(ODR/gpt-researcher/smolagents),步序级确定性管线是少数派(deep-searcher 最接近),**但 SOC 域 AiSOC/howler 全链确定性+LLM 侧挂已是生产成熟形态**;deer-flow 2.0 从研究框架重写为通用 harness,研究步集降级为 skill——与我们「步/门/工件分离」同向 |
| Q2 模型自由度边界(grounding/反编造) | **强支持;我们的设计高于开源现状** | web:span-grounded citation+外置代码验证=生产推荐/合规必选(卡7,三级方案 C);引用 URL 3–13% 纯幻觉实测(卡8,DRBench 53,090 URL)。OSS:gpt-researcher 仅追加 visited_urls 列表不校验正文对应;**逐字回引校验在全部检视项目中零实现**——最强同向件=AiSOC 确定性零-LLM groundedness 评分(IOC token 必须在证据中出现)+deer-flow citation envelope(引用带检索原文摘录) |
| Q3 配额/预算感知 | **支持;我们的面在样本中最严** | web:runcycles 三件套=attempt 前准入/结算后核销/超时 uncertainty hold(卡11);agentgateway 把余量暴露给调度方(卡10)。OSS:几乎全体缺席,预算=depth/breadth/concurrency 数字旋钮,ODR 把配额矛盾写进注释让用户自己调并发 |
| Q4 LLM 分诊人裁边界 | **强支持;与 2026 共识线精确重合** | web:Splunk ES 8.5 triage agent=disposition+rationale+留痕,人采纳(卡12);VDF AI 红线「不许关闭告警/不许阻断」(卡13);OpenAI 指南=草稿全自动、不可逆留人(卡14)。OSS:AiSOC verdict_gate=引用了证据外 IOC 的判决**降级人审而非自动关闭**+审批人≠发起人+三层 opt-in;howler=平台确定性+LLM 只挂只读 MCP 工具 |
| Q5 发现质量指标 | **支持;两条指标无先例(情报域特有)** | web:DeepResearch Bench=有效引用数×引用准确率(ICLR 2026,卡15);DREAM=Citation Integrity 调和平均+Domain Authoritativeness(ACL 2026,卡16);「何时调查够了」是开放难题(卡17)→硬门做停止条件获支持。**排他率与入队人裁两件无先例也无反驳** |

学术面补充:arXiv 2610.29346(2026-10-21)中间执行轨迹错误分类学(System-Level/Task-Level 两维+可操作设计指南)——对六步设计直接背书;Agentic Data Engineering(2026)读多诊断工具+写类工具显式人审门控——「只写不动作」跨域背书。

## 二、对撞零硬挑战,两条软补强(设计修订点)

**(a) 引文 span 匹配**(卡7/8):URL 核活不够——「URL 活但内容编造」漏网。G_SHORTLIST 的语义门应升级为:候选声明必须携带逐字引文 span,代码做字符串级匹配(卡7 方案 C);可参考 urlhealth 思路区分 link-rot(链接老死)vs fabricated(编造)。我们已有的逐字回引主张正好落在这条线上,门实现要对齐 span 级。
**(b) 超时成本 uncertainty hold**(卡11):超时请求 usage 未知,不得按零核销,应留 hold 挡住同预算域后续准入,防 retry storm 空转。budget.mjs 需检查现有超时路径的记账语义。

## 三、可借鉴的生产细节(AiSOC/howler 为主)

1. **门只拦「无人看就会关/会动作」的路径**:升级给人看的反而放行(少拦=少噪声)——我们 finding 出口已同型,分诊助理设计沿用。
2. **uncited 而非丢弃**:无引用声明标 *uncited* 保留在人审面,不静默删——「无证据≠清白」同型。
3. **审批人≠动作发起人 + 三层 opt-in(deployment/tenant/playbook 全默认关)**:分诊助理的启用面设计模板。
4. **howler MCP 工具面**:lucene_query+get_index_fields/get_field_values 发现式只读辅助——分诊助理工具面(判例检索/台账读)的现成模板;平台确定性+LLM 侧挂同构。
5. **deep-searcher 退出条件**:「反思→gap query→无新查询即停」显式退出,且停止规则本身进可复现评估——发现轮「还该不该再搜」的门形制。
6. **ODR 结构化输出重试帽**(max_structured_output_retries):我们该有的小门,防 schema 解析死循环。

## 四、对挂起七问的修订建议(grilling 待答)

- Q1 双轨并行:**维持**,研究背书补强(分诊助理=AiSOC copilot 模式+howler 侧挂形)。
- Q2 六步四门:**维持+两处升级**——G_SHORTLIST 语义门按补强(a)做 span 级;新增结构化输出重试帽小门。
- Q3 结构化候选+模型无权改入队判据:**维持**(AiSOC verdict_gate 同型)。
- Q4 OPS_DISCOVER_* 旋钮族+gh_search 配额一等公民:**维持+补强(b)** 超时 hold;quota 余量写工件供调度感知(已具 09-budget.json/breaker.json 面可比照)。
- Q5 北星两条零持门:**维持**;排他率=无先例自有指标,如实标注。
- Q6 GLOSSARY 铸词(发现轮/发现管线)+ADR 0010+STANDARD 挂点:**维持**。
- Q7 C1-C3 重构批先行:**维持**(工程卫生,研究不涉);名表是发现管线工件面的地基不变。

## 五、残余缺口

- Reddit/X 民间翻车面当日渠道故障未采(厂商文档+论文已覆盖五问,缺踩坑视角)。
- Perplexity/ORDR 原版等付费闭源竞品未覆盖。
- Tongyi DeepResearch(模型发布仓)未深读推理代码,按 README 定性,背景级。
