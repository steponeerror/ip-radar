# ENVELOPE.md — 轮次结果单契约(冻结面)

票 #229 T5 任务书②裁定。本文件冻结 cron 入口 stdout 的结果单形状与 usage 口径；动此面前先过同数据重跑比对(golden + shadow 对拍)，否则视为破坏字节级一致红线。

> 术语注（#259）：本契约面已改称「轮次结果单」；代码注释/输出字符串面（如 composeEnvelope、probes/discovery-tools 输出）因与 agent v1 字节级一致冻结暂存旧称，切流退役时一并清理。

## stdout 契约(cron 面,`run-health.mjs` / `run-discover.mjs` / `run-add.mjs` 同律)

- stdout **末行 = 单行 JSON 旧形结果单**,是 stdout 上唯一 JSON;wrapper 进度信息一律走 stderr(`[v2-health]` / `[v2-discover]` / `[stage]` / `[tool]` / `[admission]` 行)。
- 旧形 = 与 `ops/agent/pipeline.mjs` 结果单逐字段同族;形状由对拍测试钉死(round-ctx `composeEnvelope` 逐字副本 + discover 第二副本,golden/shadow 双闸),cron 消费方(脚本、看门狗)零改动。

| 面 | 成功 | 失败/拒跑 |
|---|---|---|
| 形状 | `{ok:true, round, pkg, usage, queue_writes, verify, pipeline}` | `{ok:false, round, error:{code,message}, pkg?}` |
| health | `round:"health"`,`pipeline:{round_id, resumed_from, replayed_of, stages, finding_exits?}` | 拒跑 `code:"budget_monthly"`;运行期失败码闭集同旧(ERROR_CODES) |
| discover | `round:"discover"`,六步 stages | 同上 |
| add | `round:"add"`,六相位 stages(VERIFY→DOSSIER→IMPLEMENT→GATE→REPORT→CLOSE;bench 形态五相位,DOSSIER 跳过不记 stage);域键 `source`+`sandbox:{root,branch,sha}`,`pkg` 恒 null,`queue_writes` 恒空(轮零队列写口,spec 2026-11-11-add-round 定案 9) | 拒跑 `code:"budget_monthly"`;运行期失败码闭集九词 + add 域词 `card_missing` / `card_not_approved` / `duplicate_publisher` / `freshness_gate` / `gate_failed` |

失败结果单差异注:旧 pipeline 轮失败结果单含 `pipeline` 字段(composeEnvelope 失败分支),v2 失败结果单无——已声明差异面(见 SHADOW-RUNBOOK §已知差异);`error.code` 语义同闭集九词。

- exit 码表(三 launcher 同律):`0`=completed;`1`=failed/refused/parked;`2`=用法错;`3`=运行期异常(launcher 自身崩溃,非轮内失败)。
- `--to-phase`(health 专属,旧 replay `--to` 镜像):停笔相位完成后终态 completed,结果单 stages 止于该相位;默认 CLOSE 全链。

## usage 口径裁定(定案②)

**结果单与台账的 usage = 轮累计事件流口径**:轮内全部模型事件(含子任务、缓存命中)累加,轮结束一次性结算。取数机制按入口分面:发现轮 = 会话 UsageDoc 快照求和(`discover-round.mjs roundUsage`);健康轮 = 逐子任务 result 求和(`health-round.mjs` WAIT_MODEL 收口);entry 骨架 = `harness.usage()` 差分。三面共同点 = 轮累计事件流口径(与旧管线同义);pi-durable 的 UsageDoc 对 entry 面仅作 harness 内部观察面。加源轮同发现轮面(会话 UsageDoc 求和,`add-round.mjs roundUsage`);差异:结果单 `pipeline.stages[].usage` 为**相位增量**(会话累计差分)——发现轮单模型步恒等,加源轮两个模型步,增量记法保 stages usage 求和 == 结果单 usage 的求和律。

已知计量边界差(与旧管线对拍时,见 SHADOW-RUNBOOK §已知差异):v2 的 `in` 含 cache_read 且 `total` 再计一次缓存面,故 faux 同轮 v2 数字 ≥ 旧面;**cost 细胞不受影响**(价目表按 token 类分别计价,faux 恒 0,真实轮 cost 独立求和),台账 usage 三计数(in/out/total)在 shadow 对拍中归一,cost 逐字比。

## 台账兼容行(月度准入消费面)

成功轮台账行由 RETRO 步写(与旧管线同点、同形):`| 日期 | 轮次 | model | in=N out=N total=N cost=0.00000000 | pipeline:<round_id> |`。月度准入(`monthSpendOfLedgerText`)与前端 `opsLedger.ts` 解析面零改动——v2 轮天然流出兼容行,`tests/cron-launchers.test.mjs` 与 `tests/shadow-health-parity.test.mjs` 双钉。加源轮 CLOSE 步经 lib.sh `ledger_append` 写同形行,标签 `pipeline-add:<round_id>`(轮次列=real/faux-pipeline);旧 `LEDGER_TAGS` 闭集零改动(属主红线),消费面只读 cost 列不受标签词影响。

## queue.md 兼容面(发现轮;终审补声明)

spec 定案 4 裁「ledger/queue 不再自维护,对下游兼容输出由 T5 保证」:v2 发现轮 ENQUEUE 步零复制 `steps.runStage` 仍写 `queue.md` PROPOSE 行(同点同形,golden 对拍硬断言钉住)——与台账同属对下游兼容输出面,消费方(人工审阅队列)零改动。健康轮不写 queue(旧同律)。
