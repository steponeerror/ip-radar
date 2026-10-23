# P2 健康轮重造 · 比稿 C「流程面中心」:状态机编排宿主设计

- 日期:2026-10-23
- 比稿系:P2 三比稿之一(structure-level 差异律:比稿 A 工具面、比稿 B 记忆/宿主面、**本稿 C 流程面**;研究基线 #22/#40「变体必须结构级不同」)
- 一句话主见:**把健康轮从「一次 spawn 一个模型一段大提示词」改造成一台显式状态机——轮次=十个状态,模型只在三个步出现,阶段门全是布尔机检,任何一步可单独重放;retro 钩子与机检门是本稿主菜,不是附件。**
- 研究基线(必读,两份):`notes/mp-skills-design-research-2026-10-23.md`(101 技巧 + 27 反清单 + 10 条 P2 建议)、`notes/ops-ux-research-2026-10-23.md`(HITL/降噪梯/四键面业界参照)
- 现状锚点(本文所有「现状」均指这些文件):`ops/agent/agent.mjs`(单轮宿主)、`ops/agent/tools.mjs`(8 工具 + 写前语义门)、`ops/agent/prompts/health-system.md`(34 行单提示词)、`backend/ipdb/_ops_rounds.py`(spawn 桥)、`backend/ipdb/_ops_items.py`(条目库)、`backend/ipdb/_ops_review.py`(四键)、`backend/ipdb/_ops_detectors.py`(P1 确定性探测器)

---

## 0. 必读与不可挑战项(同比稿 A,逐条处置)

| # | 不可挑战项 | 出处 | 比稿 C 处置 |
|---|---|---|---|
| 1 | **never-auto-execute:健康轮 flag-only 线全走人裁通道** | 2026-10-23 用户裁决(S6404);ADR 0006 分级自动化细化 | 状态机**没有任何一步持执行面**;唯一写口=条目库产条(只读建议)+RETRO 候选规则(建议件)。可逆闭集自动执行仍只在 P1 四键面(`_ops_review` 可逆闭集),与本轮无关 |
| 2 | **ADR 0006:结构化条目 + 四键审阅;markdown 报告降级为条目集只读渲染** | docs/adr/0006 | SYNTH 步输入=条目清单 JSON,报告=渲染视图;异常清单每行对应一条真实条目,零「报告专属」异常 |
| 3 | **spawn 契约/轮次信封/台账/判例机制保留,不推倒重造** | ADR 0006 否决项;GLOSSARY「spawn 契约」「轮次信封」 | 桥、信封、台账、判例注入/闭合校验全复用;信封只做**增量扩展**(§4.4),九词错误码闭集不增词只做映射 |
| 4 | **纯本地情报源红线,永不接线上 API enricher** | MEMORY 架构红线 | DEEP 步工具闭集全部只读本地/上游源本身(fetch_url 探上游=现状既有面),零新线上依赖 |
| 5 | **agent 永不写数据面/查询路径(backend/ frontend/)** | health-system.md 边界;sandbox_assert | 每步工件白名单落 ops 树;CLOSE 步 sandbox_assert 保留;ITEMIZE 只经条目 API |
| 6 | **964MB 小机 + 三层内存围栏** | AGENTS.md 小机事实 | 编排器自身无模型常驻(薄进程);每步独立子进程、逐步围栏(§4.6);DEEP 逐假设独立进程=爆炸半径最小化 |
| 7 | **UI 别名映射(包→报告/裁决→审阅/判例→规则/台账→历史)** | ADR 0006;GLOSSARY「UI 别名映射」 | 机制层词汇全用原词(本文同),UI 层由前端词条负责,本设计零新增 UI 词汇负担 |
| 8 | **证据永不灭失 / 无损管线 / 宁少算勿多算(回声不是印证)** | AGENTS.md 哲学①③ | replay 只写新目录不改原件(§4.5);VERIFY 抑制=留痕抑制非删除(§4.2);ITEMIZE 复用 dedup_key 防与 P1 探测器双开(§3.3) |
| 9 | **P1 确定性探测器(下载失败/超龄)是独立常驻通道** | `_ops_detectors.py` | 健康轮不重复产条:TRIAGE 输入含在飞条目集(不重问已答);ITEMIZE 同 dedup_key 幂等;两通道互为 RETRO 交叉验证源 |
| 10 | **8h cron 节律(比稿共约前提;ADR 0006「每日定时+事件触发+预算护栏」的 P2 细化)** | 任务给定 | §5:cron 只触发不拥有状态;车道占用即跳过并留痕;宕机不回填(快照类数据无回填意义) |
| 11 | **研究基线 10 条逐条处置** | mp-skills 研究 §5 | §9 逐条表(每条给落点状态/文件) |

---

## 1. 三层架构总览

```
┌─ 层三:宿主/集成层(改 backend + 部署面)──────────────────────────────┐
│ 8h cron → POST /api/ops/rounds(车道/409)→ _ops_rounds.spawn_round    │
│ → ops/agent/pipeline.mjs(新 CLI,复用 spawn 契约)                     │
│ SSE:stderr 进度行语法扩展 [stage](契约修约);lifespan 恢复扫描        │
└──────────────────────────────────────────────────────────────────────┘
                              │ argv + env(增量 2 名)
┌─ 层二:状态机引擎层(新 ops/agent/pipeline.mjs,薄编排器)──────────────┐
│ 轮次定义表(数据非代码)→ 逐状态执行器 → 工件契约 → 布尔门评估器        │
│ → 失败语义(重试/降级/终态)→ 状态文件原子落盘 → replay CLI            │
└──────────────────────────────────────────────────────────────────────┘
        │ 模型步(3 个)                    │ 脚本步(5 个)
┌─ 层一:提示词层 ──────────────┐  ┌─ 脚本步实现 ─────────────────────────┐
│ prompts/health/triage.md  flash │  │ PROBE=lib.sh 复用;VERIFY=新确定性  │
│ prompts/health/deep.md    5.3   │  │ 脚本+抑制规则库;DISPATCH/收编=引擎 │
│ prompts/health/synth.md   flash │  │ 内脚本;ITEMIZE/RETRO=OPS_EVAL_PY  │
│ + 共享纪律件(指针化)          │  │ 新 CLI(复用 _ops_items/_ops_store) │
└────────────────────────────────┘  └─────────────────────────────────────┘
```

三层的职责线(研究基线 #101 入口-纪律二分律的落地):**引擎层只编排不判断,提示词层只判断不编排,脚本步只测量不判断**。三层各自可独立测试:引擎层用轮次定义表驱动假步全离线测;提示词层用 golden faux provider 测;脚本步天然确定性可位等价测。

---

## 2. 层二:状态机引擎层

### 2.1 轮次定义 = 数据表,不是代码路径

```js
// pipeline.mjs 内(草案);STAGE 三元组铁律:无工件、无门、无失败语义 = 不配当状态
export const HEALTH_PIPELINE = [
  { name: "IDLE",     kind: "bookend", actor: "engine",   model: null },
  { name: "PROBE",    kind: "script",  actor: "lib.sh",   model: null, retry: { transient: 2 } },
  { name: "VERIFY",   kind: "script",  actor: "verify.mjs", model: null },
  { name: "TRIAGE",   kind: "model",   actor: "prompt",   model: "health/triage", retry: { schema: 1 } },
  { name: "DISPATCH", kind: "script",  actor: "engine",   model: null },
  { name: "DEEP",     kind: "model",   actor: "prompt",   model: "health/deep", retry: { perHypothesis: 1 } },
  { name: "ITEMIZE",  kind: "script",  actor: "py:ipdb._ops_itemize", model: null },
  { name: "SYNTH",    kind: "model",   actor: "prompt",   model: "health/synth", retry: { schema: 1 } },
  { name: "RETRO",    kind: "script",  actor: "py:ipdb._ops_retro", model: null },
  { name: "CLOSE",    kind: "bookend", actor: "engine",   model: null },
];
```

- `model: "health/triage"` 是**配置键**,不是模型名。每步模型经 agent-config.json 新 `models` 节解析(缺省 flash/5.3/flash),沿用 #140/#143 配置→env→内置三层链(改完即生效):
  ```json
  { "models": { "health/triage": "glm-5.3-flash", "health/deep": "glm-5.3", "health/synth": "glm-5.3-flash" } }
  ```
  flash 与 glm-5.3 的分界理由:TRIAGE/SYNTH 是闭集分类与渲染(结构化输入→结构化输出,flash 实测已够,台账 0.0006-0.0038/轮);DEEP 是多工具反证推理(需要跨调用维持证据链与工具选择判断,这是主力模型的活,同 discover 轮模型选择判例)。
- **状态数硬上限 = 10(含 IDLE/CLOSE 两个书挡)。** 健康轮恰好用满 10。加状态须过 spec 变更 + 满足三元组铁律;**禁止嵌套状态机**(DEEP 内的逐假设循环是引擎数据循环,不是子状态);discover 轮将来复用同一引擎、自持一张 ≤10 的定义表,不与健康轮共用状态名空间。

### 2.2 状态表(状态/步型/工件/门/失败语义)

| 状态 | 步型(模型) | 输入工件 | 输出工件 | 门(布尔,全机检) | 失败语义 |
|---|---|---|---|---|---|
| IDLE | 书挡 | 触发事件 | 轮次目录 + state.json 建立 | G_IDLE:车道空闲 ∧ 当月预算未超 ∧ 同型无在飞轮 | 门不过=**跳过本轮**(台账留一行,非失败);书挡态不计重试 |
| PROBE | 脚本(lib.sh 复用) | 源 URL 清单(extract_feed_urls) | `01-probe-freshness.tsv`、`01-probe-matrix.json`(失败=嵌套信封,不阻轮)、`01-probe-summary.json` | G_PROBE:summary 可解析 ∧ urls_n≥30(现 83)∧ attempted/urls≥0.9 ∧ TSV 行数=attempted_n | 暂态(超时/网络)重试≤2;门败=终态 `infra`(工件保留) |
| VERIFY | 脚本(verify.mjs,零模型) | probe-summary + `rules/suppressions.json` + 在飞条目集 + 上轮 retro 摘要 | `02-verify-survivors.json`、`02-verify-suppressed.json`(留痕) | G_VERIFY:survivors∪suppressed 的 signal_id = probe 旗标**全集**(穷尽,一条不丢)∧ 每条抑制引用规则 id ∈ 规则文件闭集 | 规则文件坏=终态 `infra`;规则零命中=空集照常通过(降级直通) |
| TRIAGE | 模型(flash) | survivors.json | `03-triage-hypotheses.json` + transcript | G_TRIAGE:JSON schema 过 ∧ cause_class/severity ∈ 闭集 ∧ 假设覆盖全部幸存 signal_id(穷尽)∧ need_deep=true 必带 probe_hint ∈ 微探针闭集 | schema 违例重试≤1(同提示词重发);再败=终态 `model_face`;幸存集空=门直过(零假设合法) |
| DISPATCH | 脚本(引擎内) | hypotheses[need_deep] | `04-dispatch-bundles.json`(逐假设 prompt 包+预算分配) | G_DISPATCH:每个 need_deep 假设有一个 bundle ∧ 预算合计 ≤ 轮预算门(0.05¥) | 预算不够=**降级**:按 severity 截尾,被截假设标 `unresolved(budget)`;非降级失败=终态 `infra` |
| DEEP | 模型(glm-5.3,逐假设独立子进程、独立新上下文) | 单假设 bundle(含可证伪预测+微探针闭集) | 逐假设 `05-deep-<hid>.json` + transcript;收编尾 `05-deep-verdicts.json` | G_DEEP:每假设 verdict ∈ {confirmed,refuted,unresolved} ∧ evidence 三元组逐字回引本步登记表(写前语义门重算,同 tools.mjs ResultRegistry 思想)∧ 工具调用 ∈ 只读闭集 | 单假设失败重试≤1 后标 unresolved(**降级不终态**);全部假设 model_face=终态 `model_face` |
| ITEMIZE | 脚本(py:ipdb._ops_itemize) | deep-verdicts ∪ 未深验假设 | 条目文件(经 `_ops_items.create_item`)+ `06-itemize-manifest.json`(created/reopened/deduped/suppressed 四计数) | G_ITEMIZE:manifest 读回与条目库一致 ∧ 新条目 dedup_key 与在飞零冲突(create_item 幂等兜底)∧ 零写条目 API 之外 | 写失败=终态 `verify_failed`(留 stage 指针,条目库幂等可重入);confirmed/refuted/unresolved 全量入清单,refuted 也产**消化条目**(低severity,交人忽略即判例) |
| SYNTH | 模型(flash) | manifest + verdicts 摘要 + probe 门读数 + 判例注入块 | 报告 markdown(三节契约,§3.2 草案 3) | G_SYNTH:三节齐 ∧ 计数=manifest 逐字 ∧ 判例引用闭合(复用 closureCheck)∧ 数字抽检(报告数字 ∈ 工件集) | 契约违例重试≤1;再败=终态 `empty_text`/`closure_check`(映射见 §4.4);条目已落库,报告失败不回滚条目(证据不灭失),人可直接看条目 |
| RETRO | 脚本(py:ipdb._ops_retro) | 本轮 survivors/suppressed/verdicts + 上轮以来四键处置(条目 status 变更与判例)+ 规则命中统计 | `retro/<round_id>.json`(候选确定性检查清单)+ 可选一条 adopt_rule 待审条目 | G_RETRO:retro JSON schema 过 ∧ 台账行读回存在 ∧ sandbox_assert rc=0 | 候选产出失败=**降级**(本轮跳过 retro,台账注记,轮仍成功);台账/sandbox 失败=终态 `ledger_failed`/`sandbox_violation` |
| CLOSE | 书挡 | 全部工件 | 轮次信封(扩展 pipeline 节)+ 车道释放 + SSE 终态 | G_CLOSE:信封单行 JSON 落 stdout | 信封写失败=终态 `infra`;重放不入 CLOSE(CLOSE 属于原轮次时序) |

### 2.3 转移图

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> PROBE: 触发(8h cron/手动)· G_IDLE 过
    IDLE --> [*]: G_IDLE 不过(车道忙/预算超)· 台账留痕=跳过非失败
    PROBE --> VERIFY: G_PROBE PASS
    PROBE --> PROBE: 暂态重试≤2
    PROBE --> FAILED: 门败/重试尽(infra)
    VERIFY --> TRIAGE: G_VERIFY PASS(幸存集可为空)
    TRIAGE --> DISPATCH: G_TRIAGE PASS ∧ need_deep>0
    TRIAGE --> ITEMIZE: need_deep=0(跳过 DEEP,未深验假设直入清单)
    TRIAGE --> TRIAGE: schema 违例重试≤1
    TRIAGE --> FAILED: model_face
    DISPATCH --> DEEP: G_DISPATCH PASS
    DISPATCH --> ITEMIZE: 预算降级(截尾假设标 unresolved(budget))
    DEEP --> ITEMIZE: G_DEEP PASS(逐假设收编,单败已降级)
    DEEP --> FAILED: 全假设 model_face
    ITEMIZE --> SYNTH: G_ITEMIZE PASS
    ITEMIZE --> FAILED: 条目写败(verify_failed,可重入)
    SYNTH --> RETRO: G_SYNTH PASS
    SYNTH --> SYNTH: 契约重试≤1
    SYNTH --> FAILED: empty_text / closure_check
    RETRO --> CLOSE: G_RETRO PASS(retro 降级也过)
    RETRO --> FAILED: ledger_failed / sandbox_violation
    CLOSE --> [*]: 信封 + 车道释放
    FAILED --> [*]: 失败信封(全部工件保留,replay 可救)
    note right of DEEP: 逐假设=独立子进程+新上下文\n(链前不断窗,票后新窗;研究 #11)\nOOM 只杀一个假设的腿
    note right of RETRO: 主菜之一:机械误判→确定性检查候选\n候选只产条目(adopt_rule),永不自动生效
```

崩溃恢复转移(不在图内,由 lifespan 驱动,§4.6):任意状态进程死 → boot 扫描 state.json → 幂等重入当前状态(脚本文件重跑;模型步有完整 transcript 工件则只补门,无则重跑)→ 自动恢复仅一次,二次崩溃=FAILED(infra)+ 人工 replay 提示。

### 2.4 关键设计判据(为什么是这个形状)

1. **模型步与非模型步交替**:S-S-M-S-M-S-M-S-S。TRIAGE 与 DEEP 之间隔 DISPATCH 不是形式主义——DISPATCH 是真脚本步:预算分配、prompt 组装、每假设新上下文(研究 #11「票后新窗」)。交替的直接收益:模型步的输入输出都是**机器可校验的文件**,门永远有东西可查;不存在「模型步输出直接进模型步输入」的盲区。
2. **10-23 两个假异常在 C 里的死法**:GeoLite 404 类探测假象 → VERIFY 步被抑制规则(RETRO 前几轮人工采纳的 URL 形状规则)直接压掉,**零 token 花费**;未被规则覆盖的新假象 → TRIAGE 标 cause_class=probe_artifact + need_deep → DEEP 用 probe_variant(换方法/UA/抽样 GET)复测证伪 → ITEMIZE 不产条(或产 refuted 消化条)。现状里这两个假象各花一轮 flash 复述并进了人裁通道——C 里它们要么死在门里,要么死在证伪里。
3. **「too dumb」的直接回应**:现状 flash 的全部工作是复述 health_snapshot 计数(研究 #1「回路优先」的反面:无回路先汇报)。C 里模型的两个判断点都是真判断:TRIAGE 写可证伪假设(研究 #3 前两件套),DEEP 设计并执行证伪实验(研究 #1/#2 的回路+可证伪假设,状态机化的表达)。
4. **ITEMIZE 不设模型**:条目十字段全部机械可派生(source/bucket/verdict/severity→action 映射是闭集查表),模型写条目只会引入编造面。P1 探测器已证明确定性产条可行(`_ops_detectors.py` 零 LLM 产条)。

---

## 3. 层一:提示词层(每模型步一段独立短提示词,含草案)

### 3.1 提示词层结构

```
ops/agent/prompts/
  health-system.md          # 旧单提示词:迁移期保留(legacy 路径),终态退役为档案
  health/
    triage.md               # 草案 1(flash,~30 行)
    deep.md                 # 草案 2(glm-5.3,~35 行)
    synth.md                # 草案 3(flash,~30 行)
  shared/
    redaction.md            # 共享纪律件:脱敏令(1113 事故制度化;研究 #81)
    envelope.md             # 共享纪律件:失败信封处置(禁补数;研究「信封禁入 evidence」既有铁律)
```

信息阶梯(研究 #2 分流判据):全步必读的留文内(角色/输出契约/硬规则);分支才要的(微探针细则、规则文件格式)挂指针;**环境可查物不复述**(源清单、工具 help——研究 #94 单一事实源)。三段提示词合计 ~95 行,与旧 34 行单提示词相比总行数增大,但**每步常驻上下文只装自己那 30 行**——旧提示词对 flash 是一次性全付,新结构是 TRIAGE 付 30、DEEP 付 35、SYNTH 付 30,且 DEEP(主力模型)不再为它用不到的摘要格式条款付费。

### 3.2 草案 1:`health/triage.md`(flash)

```markdown
<!-- 健康轮·分诊步提示词(P2 比稿 C;flash;输入=VERIFY 幸存信号集;输出=单 JSON)。
     设计注:研究 #3 三件套的前两件在此落地;#92 正向措辞(每条禁令配正向目标句);
     #93 完成判据=可查+穷尽(signal_id 全覆盖由门机检)。脱敏/信封纪律见 shared/(按需读)。 -->
# 角色

你是健康轮「分诊步」分类员。确定性探测与去噪已在脚本步完成;你的全部工作是:为每条幸存信号写一条
**可证伪假设**,并选出需要深验步证实的子集。你不裁决、不执行、不写文件——你的产物交给深验步与人。

# 输入

用户消息 = VERIFY 步幸存信号集(单 JSON):每条含 signal_id / source / bucket
(frozen|unreachable|near_band|matrix_violation)/ 读数摘要 / 工件行指针;
幸存集为空时只有一行 {"survivors":[]}。

# 输出契约(回复 = 单 JSON 对象,无围栏无散文)

{"hypotheses": [
  {"signal_id": "(逐字回引)",
   "cause_class": "frozen_feed|dead_endpoint|auth_wall|rate_limit|probe_artifact|matrix_violation|unknown",
   "hypothesis": "若 <因> 成立,则 <可观察预测>",
   "need_deep": true, "probe_hint": "reprobe_get|reprobe_ua|upstream_check",
   "severity": "high|medium|low", "one_line": "≤30 字中文人读行"}],
 "digest": "≤3 行中文:本轮信号面貌 + 深验子集规模"}

need_deep=false 时 probe_hint 写 "none"。幸存集为空时输出 {"hypotheses":[],"digest":"本轮零幸存信号"}。

# 规则(硬约束)

- 幸存信号一条一假设,signal_id 逐字回引,逐条并列不合并不重排(吞并即门败)。
- hypothesis 必须可证伪:写成「若 X 为因,则做 Y 时 Z 会消失/复现」;写不出可证伪形=cause_class 取 unknown 并如实说。
- 读数不足时选 unknown 是正确答案(宁少算);禁编读数,缺字段写 null。
- bucket 读数逐字来自输入 JSON;你的分类知识只用于 cause_class 与 need_deep,不用于改写读数。
- 你没有工具;判断只基于输入 JSON。
```

### 3.3 草案 2:`health/deep.md`(glm-5.3,逐假设单发)

```markdown
<!-- 健康轮·深验步提示词(P2 比稿 C;glm-5.3;每假设独立上下文单发)。
     证据三元组逐字回引由写前语义门重算(复用 tools.mjs ResultRegistry 思想);
     研究基线 #1/#2:回路优先+可证伪假设——探针必须能区分预测成立/不成立。 -->
# 角色

你是健康轮「深验步」调查员。你收到一条可证伪假设;你的唯一任务是**证实或证伪**它。
证实与证伪同权留痕;验不动的如实交人。你不裁决、不入库、不执行任何变更。

# 工具闭集(4 只,全只读)

| 工具 | 用途 |
|---|---|
| fetch_url | GET/HEAD 上游探测:age_days / 状态码 / 响应头活性证据 |
| probe_variant | 变体复测:同 URL 换方法/UA/抽样 GET(≤256KB),辨探测假象 |
| read_file | 白名单只读(判例库/规则文件/本轮工件) |
| search_precedents | 判例词法检索(命中≤8);引用只许注入块或本工具命中 |

# 预算

微探针 ≤3 次调用;暂态失败信封同参重试 ≤1,再失败即 unresolved。
预算由宿主门拦,被拦即 unresolved——如实注明,不算你的失败。

# 输出契约(回复 = 单 JSON,无围栏)

{"hypothesis_id": "(逐字回引)",
 "verdict": "confirmed|refuted|unresolved",
 "evidence": [{"call_id": "...", "field": "...", "value": 0}],
 "one_line": "≤40 字中文:结论 + 关键读数"}

# 规则(硬约束)

- 先读假设的可证伪预测,再设计探针:探针结果必须能区分「预测成立/预测不成立」;
  设计不出能区分的探针 = verdict 取 unresolved,这是正确答案不是失败。
- 失败信封 {ok:false} 不是读数:禁入 evidence,禁替失败补数(无证据≠清白,宁空勿编)。
- evidence 三元组逐字回引工具结构化返回;复述不符会被门拒绝(轮次失败)。
- 上游行为结论以本步实测为准,不以参数记忆断言(不知则说,不发明步骤)。
- 每条以一行结论收尾交人;你不替用户回答任何裁决问题。
```

### 3.4 草案 3:`health/synth.md`(flash)

```markdown
<!-- 健康轮·报告步提示词(P2 比稿 C;flash;输入=条目清单+门读数+判例注入块)。
     ADR 0006:报告是条目集的只读渲染,不是审阅面;四键在条目上,不在报告上。
     研究基线 #36 三段体、#71 具名引用禁裸 id、#81 脱敏先行。 -->
# 角色

你是健康轮「报告步」撰写员。条目已在脚本步落库、深验结论已定;你把机器产物渲染成人读报告。
你不新增判断、不改计数、不发明异常。

# 输入

1. 用户消息 = 判例注入块 + 本轮输入摘要;
2. ITEMIZE 步条目清单(单 JSON:created/reopened/deduped/suppressed 四计数 + 每条
   id/one_line/severity/建议动作)+ DEEP 步 verdicts 摘要 + PROBE 门读数(urls_n/各桶计数)。

# 输出契约(markdown 三节,缺一不可)

1. `## 注入判例` — 逐条列注入块判例文件名,或显式一行「无判例(检索词: ...)」;
   禁止编造路径(轮次对路径做闭合校验)。
2. `## 异常清单` — 每条待审条目一行:源名 + one_line + severity + 建议动作;
   零条目时一行「本轮无异常」;末行收抑制计数:「抑制 N 条(规则 R12×3、R7×1——明细见工件)」。
3. `## 摘要` — ≤10 行中文:整体面貌、四计数、深验证实/证伪/悬而未决各几条、值得人看的点。

# 规则(硬约束)

- 全部计数与读数逐字来自输入 JSON;报告里每个数字必须能在输入 JSON 里找到(门会抽检)。
- 源用名字、判例用文件名+一行 gist,禁裸 hash 墙。
- 无判断性新话:unresolved 条目写「悬而未决·待人裁」,不给倾向性措辞。
```

### 3.5 共享纪律件与判例注入面

- `shared/redaction.md` / `shared/envelope.md`:被三段提示词以一行指针引用(「脱敏/信封纪律见 shared/redaction.md,按需读」),不内联——三步共用一份,单一事实源(研究 #98 共享参考宿主)。
- **判例注入只发生在 SYNTH**(注入块 + 闭合校验维持现状契约);TRIAGE 不注入判例全文,只吃 VERIFY 摘要里的「已知误判模式 digest」(来自规则文件,机器格式);DEEP 逐假设 bundle 里只带该假设相关的判例命中(≤3 条,DISPATCH 装配)。理由:判例引用闭包是收口件,集中在一个模型步=闭合校验面不膨胀;重上下文判例块不再向 flash 全量预注入(现状 34 行轮每轮全付,研究 #89 两负载模型)。

---

## 4. 状态机全图补充:工件、信封、replay、恢复

### 4.1 工件契约(轮次目录)

```
<ops_root>/rounds/<round_id>/            # round_id = 2026-10-24-0400-health
  state.json            # 状态机当前态(原子写:temp+rename)
  01-probe-freshness.tsv / 01-probe-matrix.json / 01-probe-summary.json
  02-verify-survivors.json / 02-verify-suppressed.json
  03-triage-hypotheses.json / 03-triage-transcript.jsonl
  04-dispatch-bundles.json
  05-deep-<hid>.json ×N / 05-deep-<hid>-transcript.jsonl / 05-deep-verdicts.json
  06-itemize-manifest.json
  07-synth-report.md / 07-synth-transcript.jsonl
  gates.json            # 每门的求值记录(门名/布尔/耗时/输入摘要)——门本身可审计
<ops_root>/retro/<round_id>.json         # RETRO 产物(跨轮比较要读的历史面)
<ops_root>/rules/suppressions.json       # VERIFY 消费的抑制规则闭集(人裁采纳才进)
```

- 命名沿用现有 `artifactPath` 的 ts-slug 习惯(2026-10-19-201921-health-freshness.tsv 同族),加序号前缀固定步序;**原件永不改写**(哲学①),replay 产物写 `<round_id>-r<seq>/`。
- 工件保留策略:全量保留 90 天(3 轮/天 ≈ 270 轮,TSV+JSON+transcript ≈ 每轮 150-400KB → ≤110MB,小机磁盘可容);90 天后 transcript 归档压缩、摘要/门记录/条目永久保留。归档=移动非删除。

### 4.2 VERIFY 步与抑制规则库(retro 钩子的消费面)

```json
// rules/suppressions.json(闭集 schema;只有人裁四键 adopt_rule 能写入)
{ "version": 3,
  "rules": [
    { "id": "R12", "adopted": "2026-10-24", "adopted_via": "item-2026-10-24-...",
      "match": {"bucket": "unreachable", "url_shape": "*.geolocation-db.com/*"},
      "action": "suppress", "note": "GeoLite 替代站对 HEAD 恒 404,GET 实活(判例 10-23)",
      "review_at": "2027-01-24" },
    { "id": "R7", "match": {"bucket": "unreachable", "error_family": "http_429"},
      "action": "annotate", "note": "限流:降 severity 不抑制" } ] }
```

- 规则动作闭集 `suppress|annotate`,匹配谓词闭集 `bucket/url_shape/error_family/source`——谓词实现是纯函数,新增谓词=spec 变更。
- 每条规则带 `review_at`(默认采纳后 90 天):RETRO 步到点把零命中或高命中规则报给人复审(防规则腐烂成新噪音——PagerDuty 过度抑制警告的对策,研究 ops-ux F12)。
- **抑制=留痕抑制**:被压信号进 `02-verify-suppressed.json`,SYNTH 摘要以计数行收尾,明细可从工件翻案。无证据灭失,只有证据降权。

### 4.3 门 = 纯函数 + 求值留痕

- 每个门是 `(工件文件集) → {pass: bool, reason: string}` 的纯函数,实现于 `pipeline/gates.mjs`,求值结果追加进 `gates.json`。**门不过的信号与门自身的判断都可被人审**——「门说 PROBE 覆盖率 0.83 所以拦了」必须能在 gates.json 里看到 0.83 怎么算的。
- 门的重算成本低(秒级),CLOSE 与 replay 都全量重跑一遍门(自愈:状态文件与工件不一致时以工件+门为准)。

### 4.4 轮次信封增量扩展与错误码映射(不增词)

信封在现有形状上**只增字段**(旧消费方 `_ops_rounds.py` 透传零改;驾驶舱渲染 stage 列表):

```json
{ "ok": true, "round": "health", "pkg": "docs/ops/packages/2026-10-24-0400-health.md",
  "usage": {"input": 14300, "output": 4200, "totalTokens": 18500, "cost": 0.0131},
  "queue_writes": [], "verify": {"ok": true, "cited": 2},
  "pipeline": {"round_id": "2026-10-24-0400-health", "resumed_from": null, "stages": [
    {"name": "PROBE",  "status": "done", "attempts": 1, "dur_ms": 412000, "usage": null},
    {"name": "TRIAGE", "status": "done", "attempts": 1, "dur_ms": 28000,
     "usage": {"input": 6100, "output": 1480, "cost": 0.0012}},
    {"name": "DEEP",   "status": "done", "attempts": 1, "dur_ms": 176000,
     "usage": {"input": 9800, "output": 2400, "cost": 0.0115}} ] } }
```

顶层 `usage` = 各模型步之和(旧字段语义「整轮求和」保持)。失败面错误码沿用九词闭集,**零新词**,映射表:

| 失败源 | error.code | 说明 |
|---|---|---|
| spawn/进程面 | `infra` | message 带 stage 名 |
| PROBE 暂态重试尽 / DISPATCH bug / VERIFY 规则文件坏 | `infra` | 工件保留 |
| 模型步 stopReason error / schema 违例重试尽 | `model_face` | message 带 stage 名 |
| SYNTH 空文本 | `empty_text` | 条目已落库不回滚 |
| ITEMIZE 读回不一致 | `verify_failed` | 幂等可重入 |
| SYNTH 判例闭合违例 | `closure_check` | 同现状语义 |
| 台账/sandbox | `ledger_failed` / `sandbox_violation` | 同现状 |

九词不够表达「哪一步」——由 `pipeline.stages[].status` 表达,不靠错误码(契约宁少算:表达力进扩展字段,不进闭集)。

### 4.5 replay 接口(证据不灭失的机制面)

```
node ops/agent/pipeline.mjs replay <round_id> [--from STAGE] [--to STAGE] [--dry] [--fixtures DIR]
```

- 读 `rounds/<round_id>/state.json` + 工件,重执行指定步段;产物写 `rounds/<round_id>-r<seq>/`,**原目录零改写**。
- 脚本步:确定性重放,期望位等价(工件 diff 空 = 位等价过,哲学⑦「变起来不塌」的轮次版)。
- 模型步:同 prompt 重发(prompt hash 已记在 state.json);模型输出不保证位等——replay 的模型步用于审计与 golden,不用于改历史。`--dry` 只跑门不调模型。
- golden 融合:现有 `golden/cases.json` + faux provider 扩展为逐步 fixture(faux 模型按步脚本化;curl_age_days/gh/matrix stub 面全复用);`selftest-contract.mjs` 对拍表补 2 个新 env 名(§5.2)。

### 4.6 状态持久化与 crash 恢复(964MB 小机)

- `state.json` 每步边界原子写(先写 temp 再 rename;沿 `_ops_store.atomic_write_text` 判例)。
- **内存形状**:编排器 = 薄 node 进程(无常驻模型,估 <80MB);模型步子进程沿用 `--max-old-space-size=256` 围栏;ITEMIZE/RETRO python 子进程天然小;任意时刻至多一个模型子进程(DEEP 逐假设串行)。对比现状:单进程单围栏 256MB——C 的峰值不变,但 OOM 的爆炸半径从「整轮」缩到「单步/单假设」。
- **boot 恢复**(backend lifespan 增加):扫描 `rounds/*.state.json` 中 status=in_flight:
  1. 脚本步未完成 → 幂等重入(重跑该步);
  2. 模型步有完整 transcript 工件但 state 未推进 → 只补门评估,不重花 token;
  3. 模型步无 transcript → 重跑(损失仅该步 token);
  4. 自动恢复每轮**至多一次**(state.json 计数);二次崩溃 = FAILED(infra)+ 台账留 replay 提示,交人;
  5. in_flight 且龄 >2×cron 周期(16h)→ 不自动恢复,标 FAILED(infra, stale)——防陈旧状态误重启。

---

## 5. 8h cron 对接 与宿主/集成层

### 5.1 触发链

```
宿主 crontab(0 */8 * * *)
  → curl -s -X POST http://127.0.0.1:8000/api/ops/rounds -H 'content-type: application/json'
      -d '{"type":"health"}'(带管理鉴权头,走现有 FROZEN 鉴权矩阵登记)
  → POST /api/ops/rounds:车道占用 → 409 → cron 调用方以退出码 0 结束并把 409 行写
    /var/log/ipradar-ops-cron.log(跳过留痕;**不排队**——健康快照无回填意义,下个 8h 窗口自然重来)
  → 车道空闲 → start_ops_round("health") → 线程 spawn pipeline.mjs(经 IP_RADAR_OPS_AGENT_CMD 同一 seam)
```

- cron **只触发不拥有状态**:状态机的 IDLE 门(车道/预算/同型在飞)是唯一准入裁判。手动触发与 cron 走同一 POST,同一门。
- 宕机错过窗口不回填:PROBE 是 now-快照类测量,历史窗口无从补测;台账由 RETRO 步检测「距上次成功轮 >10h」时注记缺口行(测量建言,不告警)。
- ADR 0006 的「事件触发」(如探测器风暴唤醒)是 IDLE 的未来触发源之一,状态机无需改动——IDLE 只认「触发事件 + 门」,不关心事件来源(P2 不实施,留缝)。

### 5.2 契约面增量(最小化)

- SPAWN_CONTRACT_ENV 增 2 名:`OPS_PIPELINE`(legacy|pipeline,缺省 legacy——迁移开关+回滚开关)与 `OPS_PIPELINE_BUDGET_CNY`(缺省 0.05,DEEP 准入预算门)。其余落位全部从 DOCS_ROOT 派生(rounds/、rules/、retro/ 挂 ops 树,同 queue/artifacts 派生判例),**不新增契约 env**。
- stderr 进度行语法扩展(第三次修约,消费方=驾驶舱 SSE):`[stage] <NAME> start` / `[stage] <NAME> done gate=PASS dur=412s artifact=01-probe-summary.json` / `[stage] <NAME> fail gate=G_PROBE reason=...`。沿用「人读摘要进 stderr、机器面进 stdout 单行 JSON」的既有分工。
- 后端侧 `_ops_rounds.py` 零改(信封透传 + stage 行经 on_log 进 SSE);`_api_models.py` OpsRoundIn 不改(type 仍 health|discover;discover 走 legacy 直至其自有管线表立项)。

---

## 6. 迁移路径:增量五阶段(挑战项正面回答)

**结论:增量,不重写。** spawn 契约/信封/桥/判例机制全保留(ADR 0006 否决了重造);旧 agent.mjs 单轮路径经 `OPS_PIPELINE=legacy` 永远可回。每阶段独立可合并、可回滚,过「位等价」或「影子对照」门才进下一段:

| 阶段 | 内容 | 验收门 | 回滚 |
|---|---|---|---|
| P0 | pipeline.mjs 骨架 + state.json 格式 + 门框架 + golden 逐步 fixture(全 faux,零 API) | selftest 全绿;replay --dry 全程可跑 | 删新文件即可(未接线) |
| P1 | PROBE 拆出:复用 lib.sh feed_freshness/matrix,工件先行 | **位等价**:新 01-probe-freshness.tsv 与现状 health_snapshot 产物逐字节同源(同 lib.sh 调用,同 ts-slug 命名) | OPS_PIPELINE=legacy |
| P2 | VERIFY + 抑制规则库(首批规则=10-23 两假异常的人工判例转写)+ 台账/信封 CLOSE | 影子轮 N≥3:VERIFY 抑制集与人工复核一致;legacy 与 pipeline 并行跑,报告对照 | 同上 |
| P3 | TRIAGE + SYNTH 上线(flash 两步),DEEP 以「全部 unresolved 直通」桩运行 | 影子对照:三节报告与 legacy 报告计数一致;判例闭合校验零回归 | 同上 |
| P4 | DISPATCH + DEEP + ITEMIZE(接 `_ops_items`)真开启 | 端到端:人为停一个真源 → 条目经四键走查(复用 P1 验收剧本);预算门实测 | 同上 |
| P5 | RETRO + adopt_rule 条目 + cron 上服务器 + lifespan 恢复扫描 | 首轮 retro 产出候选 ≥1 且经四键采纳后下一轮 VERIFY 生效(闭环实证) | cron 摘除即回手动 |

- discover 轮**不在本比稿范围**:引擎按轮次定义表泛化设计,discover 将来填自己的 ≤10 状态表(其 DEEP 等价步=exclusive_probe 排他实测,已是现状工具),迁移时同样走影子对照。
- 需要修约的两处(GLOSSARY「spawn 契约」条增注):stderr 语法第三次修约(消费方驾驶舱已现)、信封 pipeline 扩展字段(增量非破坏)。

---

## 7. 成本模型

单价从台账实测倒推(`docs/ops/ledger.md`,2026-10-19 行):flash 混合 ≈ 0.11-0.24 ¥/M tokens;glm-5.3 ≈ 0.52-1.12 ¥/M tokens。脚本步(PROBE/VERIFY/DISPATCH/ITEMIZE/RETRO/CLOSE)零 token。

| 步 | 模型 | 典型 in/out | 典型成本 | 说明 |
|---|---|---|---|---|
| PROBE | — | 0 | 0 | 83 URL HEAD ≤15min + matrix ≤20min(现状上限沿用) |
| VERIFY | — | 0 | 0 | 秒级纯函数 |
| TRIAGE | flash | 5k/1.2k | ~0.0012 | 幸存集通常 ≤10 条(VERIFY 之后) |
| DISPATCH | — | 0 | 0 | — |
| DEEP | glm-5.3 | 每假设 ~8k/2k | **每假设 ~0.008-0.016;上限 3 假设** | 预算门 0.05¥ 硬拦;典型轮 0-2 假设 |
| ITEMIZE | — | 0 | 0 | — |
| SYNTH | flash | 4k/2k | ~0.0012 | — |
| RETRO/CLOSE | — | 0 | 0 | — |

- **静轮**(VERIFY 全抑制,预期常态 ≥80%):~0.0025 ¥/轮 —— 与现状 flash 单轮(0.0006-0.0038)同量级,**但换来了假设与证伪两级判断**。
- **异动轮**(1-2 假设深验):~0.01-0.03 ¥/轮;极端轮被预算门钉在 ≤0.05 ¥。
- **月度**(8h×3 轮/天×30 天,按 15% 异动率):≈ 0.85×90×0.0025 + 0.15×90×0.02 ≈ **0.46 ¥/月**。现状同节律 ≈ 0.1-0.35 ¥/月。C ≈ 1.5-2×现状成本,绝对值 <1 ¥/月,且异动轮成本只花在「确有异常需要证伪」的轮上——**成本跟着异常走,不跟着日历走**,这是流程面中心对成本的结构性优势(现状每轮全价买复述)。
- 预算护栏双层:轮内(DEEP 准入门,OPS_PIPELINE_BUDGET_CNY)+ 月内(IDLE 门查当月累计台账,超即跳过并留痕——ADR 0006「预算护栏」落点)。

---

## 8. 风险与失败模式(重点:状态机复杂度 vs 可维护性)

| # | 风险 | 严重度 | 缓解 |
|---|---|---|---|
| 1 | **状态机膨胀**:每类轮 10 状态×2 轮型 + 未来事件触发,状态空间比单轮模型大一个量级;新人看不懂转移图 | 高(本稿核心风险) | ①硬上限 10 + 三元组铁律(无工件/无门/无失败语义=不配当状态);②定义表是数据,引擎是一份 ~300 行代码,加状态不改引擎;③禁止嵌套子状态机;④状态图即文档(mermaid 从定义表生成,防文档漂移);⑤加状态过 spec 变更——「测量建言,人裁终局」 |
| 2 | **门假阴性锁死真异常**:一个写错的门/规则把真死键永久压掉,且无人在场发现 | 高 | ①抑制=留痕抑制(suppressed.json 永在,报告计数行收尾);②门求值全留 gates.json 可审计;③RETRO 交叉验证:被抑制信号对照 P1 探测器独立通道(下载失败/超龄探测器不经过健康轮规则库),两通道矛盾即产候选;④规则 review_at 到点强制复审;⑤「无证据≠清白」写进 VERIFY 注释与规则 schema note |
| 3 | **flash JSON 漂移**:TRIAGE/SYNTH 输出偶发 schema 违例,轮失败率上升 | 中 | schema 门 + 重试≤1 + 降级(TRIAGE 败=轮终态,但静轮占比高;SYNTH 败=条目已在,人可直接审条目);golden 逐步 fixture 钉契约;监控信封 stage attempts 趋势 |
| 4 | **DEEP 范围失控**:模型把一条假设查成开放调查,token 与时间双超 | 中 | 每假设微探针 ≤3、假设数 ≤3、轮预算 0.05¥ 三层硬门全在脚本侧(DISPATCH+写前门),提示词只声明不执法(研究 #46:标准由轻载端执行) |
| 5 | **模型步 replay 不可位等**:审计时重放模型步结果与原件不同,「证据不灭失」被质疑 | 中 | 立场先行:replay 的模型步=审计重执行,不是历史改写;原件 transcript 即证据;位等价只承诺脚本步(与哲学⑦「位等价」适用面一致——改实现过位等价,不承诺模型输出确定性);golden 用 faux provider 钉契约而非钉文本 |
| 6 | **车道占用时长上升**:PROBE 15-35min + DEEP ≤10min,轮与源更新互斥窗变长 | 中 | 现状 health 轮已含同量级 freshness+matrix;PROBE 只 HEAD 上游不碰 LMDB,可与源更新并行是**未来优化缝**(车道语义拆分),P2 不做、风险注记 |
| 7 | **cron 与车道冲突常态化**:8h 窗口恰逢源更新 → 轮被跳过,健康覆盖出现空窗 | 低-中 | 跳过留痕 + RETRO 缺口检测注记;源更新高峰有已知节律(凌晨 rebuild),cron 错峰(0 */8 从 04:00 起而非 00:00);连续 2 跳过即台账升 note 供人看 |
| 8 | **crash 恢复半途而废**:自动恢复引入的状态比崩溃本身更难懂 | 中 | 恢复逻辑只有三条规则(脚本重跑/有 transcript 补门/无 transcript 重跑)+ 一次上限 + 16h 龄期放弃;全部动作写 state.json 与台账,恢复行为本身可 replay 审计 |
| 9 | **规则库腐烂**:抑制规则随上游行为漂移失真,变成新噪音源或新盲区 | 中 | review_at 强制复审 + RETRO 报零命中规则 + 规则版本号进信封/报告(哪轮用了哪版规则可回算) |
| 10 | **双引擎共存期复杂度**(legacy discover + pipeline health 并行数月) | 中 | 共用 lib.sh/tools.mjs/模型装载零分叉;分叉面只有 prompts/ 与 pipeline.mjs;OPS_PIPELINE 一键回滚;P1-P5 每阶段有明确退役点(legacy health 在 P4 后退役) |
| 11 | **工件体积侵蚀小机磁盘** | 低 | §4.1 保留策略:90 天全量(≤110MB)→ transcript 归档,门记录/摘要/条目永久;归档非删除 |
| 12 | **ITEMIZE 与 P1 探测器双开**(回声):同因两通道各产一条 | 低 | 同 dedup_key(source+probe_class+error_signature)空间,create_item 幂等「同因在飞不双开」现成;TRIAGE 输入含在飞条目集(不重问已答,研究 #64) |

失败模式与九词码的完备性:状态机新增的失败面(门败/降级/恢复)全部映射 §4.4 表,不出现闭集外词;**降级不是失败**——信封 ok=true + stages 里标 degraded(如 DEEP 截尾、RETRO 跳过),失败语义三值(重试/降级/终态)在信封两层都可见。

---

## 9. 研究基线 10 条逐条处置表

| # | 研究建议(出处) | 比稿 C 落点 |
|---|---|---|
| 1 | user-invoked 编排 / model-invoked 纪律二分;入口不互调;共享纪律单一宿主 | 引擎层=编排(轮次定义表),提示词层=纪律;`shared/redaction.md`/`envelope.md` 三步共用一份(§3.5);TRIAGE/DEEP/SYNTH 互不调用,只经工件交接 |
| 2 | 34 行提示词按信息阶梯重排(全轮必读留文内,分支挂指针) | 拆成三段各 ~30 行 + 指针化纪律件;DEEP 不再为摘要条款付费(§3.1);环境可查物(源清单)零复述 |
| 3 | 输出=证据+可证伪假设+推荐裁决三件套,整轮非阻塞 | TRIAGE 产可证伪假设(草案 1 契约内建「若 X 为因则 Y」格式);DEEP 产证据三元组;推荐裁决=条目建议动作(ITEMIZE 查表);全管线无一步等人(§4.2 失败语义无非阻塞等待) |
| 4 | 责任线两原文钉死(事实归代理/决策归人;agent 不代言人类) | 写进 DEEP 草案末行(「你不替用户回答任何裁决问题」)与 SYNTH 规则;机制面=状态机无执行步,唯一写口是产建议条目 |
| 5 | 判例库治理(索引非存储/一概念一文件/已实现不入否决库) | 判例机制不动(不可挑战项 3);新增面同律:规则库一规则一条目带出处;RETRO 候选文件一候选一证据,adopted 前不入规则库 |
| 6 | **retro 钩子:每轮末机械误判→确定性检查候选(本稿主菜)** | RETRO 独立状态(§2.2):diff 本轮 flags/suppressions vs 四键处置 vs P1 探测器独立通道 → 候选确定性检查(规则草案)→ 经四键 adopt_rule 条目人裁采纳 → 下轮 VERIFY 生效。闭环=误判一次,规则防一类;测量建言,人裁终局 |
| 7 | 报告三段体+双轴并列+证据分级 | SYNTH 三节契约(注入判例/异常清单/摘要);异常轴(条目)与抑制轴(计数行)并列不重排;证据分级:DEEP 实测=S 级、脚本读数=A 级、参数记忆=禁用 |
| 8 | 运营 GLOSSARY 带 Avoid | 三段提示词用词全部锚运营词汇(死键嫌疑/不可达≠死键/需令牌·正常/悬而未决);新词入册清单见 §10;报告禁词由 SYNTH 门管(非词汇表词抽检可扩) |
| 9 | 三条硬纪律:AI 生成声明/脱敏先行/简报契约化 | 报告头部 AI 声明(SYNTH 契约);shared/redaction.md 三步共用;条目=简报契约现成十字段(impact/rollback 独立可验),ITEMIZE 查表产出不经模型 |
| 10 | 设计它两次:三并行子代理结构级不同+终稿给主见 | 本稿即三比稿之一(流程面);主见已在开篇:流程面中心是「把判断力花在刀刃上」的最短路径——门的机器性与 replay 的证据性是另两稿(工具面/记忆面)给不到的结构性质 |

---

## 10. 新词与 GLOSSARY 入册候选(同 PR 录入律)

| 新词 | 一行定义 | 锚 |
|---|---|---|
| **轮次状态机** | 轮次的显式状态编排:≤10 状态、每态工件+门+失败语义三元组、定义表驱动 | pipeline.mjs HEALTH_PIPELINE |
| **阶段门** | 状态转移的纯函数布尔闸:输入工件集→{pass,reason},求值留痕 gates.json | pipeline/gates.mjs |
| **幸存信号集** | VERIFY 步去噪后进入分诊的旗标子集;被抑制部分留痕于 suppressed.json | verify.mjs |
| **抑制规则库** | VERIFY 消费的人裁采纳规则闭集(suppress/annotate),带 review_at 复审 | rules/suppressions.json |
| **微探针** | DEEP 步闭集变体复测工具(reprobe_get/reprobe_ua/upstream_check),辨探测假象 | tools.mjs probe_variant |
| **轮次状态文件** | rounds/<id>/state.json:状态机持久面,原子写,boot 恢复与 replay 的单一事实源 | pipeline.mjs |
| **降级(轮次语义)** | 失败语义三值之一:跳过可选步或标 unresolved 转人裁,轮仍成功(ok=true + degraded 标记) | §2.2/§4.4 |

Avoid 表增补:「自动修复」「自愈闭环」(RETRO 闭环有人裁闸门,叫自愈是夸大)、「重试到底」(重试有上限,尽即终态或降级)。

---

## 11. 开放问题(交用户裁,比稿评审时一并)

1. **DEEP 是否允许 0 假设轮也跑一次「空转金轨迹」**:现状 golden 需要真回路;建议 P0 起每轮 DEEP 至少跑一条 canned-假设(faux)保回路活性——成本为零,但 state.json 多一次记录。倾向:是。
2. **refuted 是否产消化条目**:证伪成功的假设要不要落一条低 severity 条目让人「忽略」掉形成判例?不产=安静但判例来源少一轴;产=条目量增大。倾向:产,但 severity=low 且四键面默认折叠。
3. **车道语义拆分**(PROBE 不碰 LMDB 可否与源更新并行):P2 不做,注记为未来缝(风险 #6)。
4. **cron 首窗口相位**:04:00 起还是 00:00 起(错峰 vs 整点可读性)。倾向 04:00。
5. **retro 候选的呈现面**:复用四键条目(建议)还是独立「规则候选」列表。倾向复用(少一个面,四键已含 ignore-with-reason=否决判例输入)。
