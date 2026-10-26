# DP-T3-REPORT — 发现管线化批 T3(#209)交卷

工位:`.worktrees/dp-t3`(分支 `feature/dp-t3`,基 b8825774 = 集成分支 feature/discover-pipeline-v0 顶)。commit:46ea92cc(占位)→ 0a810184(交付物 ①②④)→ 5169dc38(交付物 ③⑤)。未 push;未动主仓/其他 worktree。

## 交付清单(票 #209 五项)

### ① 结构化候选 schema+手写校验器(零新 npm 依赖)
`ops/agent/pipeline/discover-candidate.mjs`(新文件,165 行):
- `CANDIDATE_FIELDS`(7 键)/`SOURCE_CHANNELS = ['registry','needs','web']`(SCAN 三来源闭集,与 T1 d1-scan.json 协议面同集,合流时同批扩)/`CANDIDATE_MAX` 长度帽(name 200/url 500/quote 1000/notes 2000/evidence_ptr 600)。
- `validateCandidate(c)` → `{ok:true,candidate}`|`{ok:false,code:'shape',reason}`:六键必填(name/url/source_channel/quote/evidence_ptr/exclusivity_estimate),notes 可缺省(备注非证据),未知键=拒,source_channel 闭集,exclusivity_estimate∈[0,1] 数字。**排他率≥0.25 硬门裁决不在此**(属 T1 ENQUEUE 判据,模型无权改判据,ADR 0010 §3)。
- `validateCandidates(list)` → `{valid, dropped:[{index,name,url,reason}]}` 留痕清单。
- 供 T1 SHORTLIST 消费(候选形状=模型输出契约)。

### ② 证据存在性校验(纯函数,宁少算)
同文件:`evidencePtrForm(ptr)` 判两形——`<工件名>#<json指针>`(RFC6901-lite,~0/~1 转义;拒空指针=整工件指认无法对账)或 http(s) URL(工件集合内 `containsExactString` 深度逐字搜,不规范化——**半真 URL 不算在场**);`resolveEvidencePtr` / `filterCandidatesByEvidence(candidates, artifacts)` → `{kept, dropped:[{index,name,url,evidence_ptr,reason}]}`——缺=候选丢弃+留痕,不静默。

### ③ 发现轮工具宿主(microprobes 同形制注入面)
`ops/agent/pipeline/discovery-host.mjs`(新文件,150 行):`mkDiscoveryHost({dupRegistry, dupLimit, budgets, breaker, methods})` → `{tools, seeds, channelCounts, call}`。
- 工具=web_read/web_search/rss_parse(`DISCOVERY_TOOLS` 冻结闭集;**gh_search 留 legacy 面**,spec T3 节)。实现零复制:`discoveryMethods`(#179)经 `Object.assign` 挂适配器,`this.finish(callId,name,structured,contentText)` 收口——真网络/解析/信封面单源(tools/discovery.mjs)。
- 守卫链 **dup→breaker→cap**,与 tools.mjs `ToolHost.beforeToolCall` 同序同义(自决已录判例);被拒=零执行零 seed,入 blocked 观察面。breaker 回写仅 `BREAKER_CHANNELS∩布尔 ok` 面(信封码单源)。
- `call(name,args)`:MEASURE 侧确定性直调,补发 `measure-N` call-id(与运行时模型 id 不撞),同样过守卫链+登记。
- AgentTool 面(name/label/description/annotations/parameters/outputSchema)= initialState.tools 直装形(microprobes 同);seeds=chronological `{call_id,tool,sc}`(registry_seed 行型,G_* 门对账面)。

### ④ 入队行:候选卡(ENQUEUE 只写不动作,#0006 人裁交互律不动)
同 discover-candidate.mjs:`CANDIDATE_ACTION='PROPOSE'`;`candidateSourceSlug(url)` = host slug+md5(url)[:6](同候选跨轮幂等判重键 action+source,同 host 异 url 不互撞);`candidateCardEvidence` = 五字段指针卡(name/url/source_channel/exclusivity_estimate/evidence_ptr;**quote 不入行**——全文在 shortlist 工件);`appendCandidateCard(candidate,{round,queueFile})` 走 `appendQueueRowLocked`(#139 flock 路径单源;坏候选/缺 round=拒写零文件)。7 列冻结表头不动(status 列语义=proposal)。

**action 词裁决:PROPOSE(新词)非 ENQUEUE**——ENQUEUE/REJECT 闭集(python `_ops_store.QUEUE_ACTIONS`+registry.mjs queueAction schema)是运营轮**已测量源**动作词(语义门独占 exclusive_probe 实测);候选卡=发现轮 pre-验证提案,语义不同层。queue.md 无程序解析行消费方(grep 证实:py 侧只写不读行;contract 测试只对拍锁路径),7 列形状保住即可。**改词须 python 侧同批**(若合流裁决改用 ENQUEUE)——留合流批。

### ⑤ 配额一等公民(通道分列调用计数)
同 discovery-host.mjs:host 内建 `channelCounts`(executed/ok/failed/blocked 分列);`aggregateChannelCalls(rows)` 纯聚合(种子行/扁平行两形;坏行掷错不静默吞——对账面要响);`discoverChannelReadings(channelCounts)` 构造器→`{channels:{tool:{calls,ok,failed,blocked}}, calls_total, blocked_total}`(frozen;不变量 ok+failed=calls 违者/非非负整数=构造期掷错)。**breaker 态快照沿用 steps.mjs 既有 readings.breaker 面,不重造**(票面明示)。缺省帽=tools/shared.mjs `B` 常量单源(与 legacy discover 轮 ToolHost budgets 同源)。

## 与 T1 的接线协议(合流面)

T1(SHORTLIST/MEASURE/CLOSE 步)按此接,不新增 T3 侧改动:

1. **SHORTLIST(模型步)**:`mkDiscoveryHost({dupRegistry: ctx.dupRegistry, dupLimit: ctx.budgetKnobs?.dupCallLimit, breaker: <轮级 mkBreaker()>, budgets: <OPS_DISCOVER_* 旋钮面或缺省>})`,`host.tools` 直装 initialState.tools(仿 faux.mjs DEEP 真面 mkMicroprobeHost 装配);`host.seeds` 逐条发 registry_seed transcript 行(形制同 microprobes)。
2. **dupRegistry 传 ctx 级 Map**(与模型调用同 registry,dup 判据 #199 A4 同律);breaker 传**轮级** mkBreaker() 实例(熔断态跨步共享)。
3. **MEASURE(零模型)**:`host.call(name, args)` 宿主直调,call-id=measure-N。
4. **CLOSE**:09-budget.json readings 增 `discover_channels = discoverChannelReadings(host.channelCounts)`(键名 T1 定;构造器只出值);breaker 快照仍走既有 readings.breaker。
5. **候选流**:模型 SHORTLIST 输出候选(①schema)→`filterCandidatesByEvidence(candidates, scanArtifacts)`(②)→T1 排他率硬门(≥0.25,代码常量)→`appendCandidateCard`(④)。全文候选+quote 落 shortlist 工件(名从 T1 扩的 ARTIFACTS.DISCOVER_* 取);queue.md 卡行=指针卡。

## 红证(TDD)

- **①②④**:红 81/3(模块缺,discover-candidate.mjs 未落盘)→绿 84/0。负例:缺键/错型/未知键/闭集外通道/exclusivity 越界/空指针/半真 URL 各拒。
- **③⑤**:红 84/4(模块缺,discovery-host.mjs 未落盘)→绿 88/0;**反证红 87/1**(临时破坏 blocked 计数 `+=0` → 宿主例「被拒入 blocked 观察面」即败,验毕还原)——断言咬行为,非只咬模块存在。

## 验收门(2026-10-26 实跑)

| 门 | 结果 |
|---|---|
| selftest-pipeline | **PASS=88 FAIL=0**(基线 81 不降+7 新例绿) |
| selftest-t4 | PASS=63 FAIL=0 |
| selftest-contract | PASS=18 FAIL=0 |
| standard-check | OK=47 FAIL=0(不降) |
| node --check | discover-candidate.mjs / discovery-host.mjs / selftest-pipeline.mjs 全过 |

## 余项/风险(合流批裁决)

1. **queue.md 表头注释陈旧**:「queue_action 唯一写口」自本写入器起过时(PROPOSE 走 appendQueueRowLocked);表头本身不动(跨语言双源对拍哨)。改词须 python 同批。
2. **readings 键名 discover_channels 为建议**,T1 CLOSE 落地时定名。
3. **OPS_DISCOVER_* 旋钮族**未 env 化(ADR 0010 §4):宿主经 opts.budgets 注入即可,旋钮读取器属 T1 宿主装配面。
4. **dupe-seeds 面注意**:被拒调用不入 seeds=不计聚合(宁少算);若 T1 需要被拒观察面,用 host.channelCounts.blocked(readings 构造器已含 blocked_total)。
5. 测试对真实现面零网络装载断言(AgentTool 面齐);真网络路径继承 #179 既有测试,不在本票重测。
