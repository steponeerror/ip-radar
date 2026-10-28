# ENVELOPE.md — 轮次信封契约(冻结面)

票 #229 T5 任务书②裁定。本文件冻结 cron 入口 stdout 的信封形状与 usage 口径;动此面前先过回放闸门(golden + shadow 对拍),否则视为破坏位等价红线。

## stdout 契约(cron 面,`run-health.mjs` / `run-discover.mjs` 同律)

- stdout **末行 = 单行 JSON 旧形信封**,是 stdout 上唯一 JSON;wrapper 进度信息一律走 stderr(`[v2-health]` / `[v2-discover]` / `[stage]` / `[tool]` / `[admission]` 行)。
- 旧形 = 与 `ops/agent/pipeline.mjs` 信封逐字段同族(composeEnvelope 单源),cron 消费方(脚本、看门狗)零改动。

| 面 | 成功 | 失败/拒跑 |
|---|---|---|
| 形状 | `{ok:true, round, pkg, usage, queue_writes, verify, pipeline}` | `{ok:false, round, error:{code,message}, pkg?}` |
| health | `round:"health"`,`pipeline:{round_id, resumed_from, replayed_of, stages, finding_exits?}` | 拒跑 `code:"budget_monthly"`;运行期失败码闭集同旧(ERROR_CODES) |
| discover | `round:"discover"`,六步 stages | 同上 |

- exit 码表(两 launcher 同律):`0`=completed;`1`=failed/refused/parked;`2`=用法错;`3`=运行期异常(launcher 自身崩溃,非轮内失败)。
- `--to-phase`(health 专属,旧 replay `--to` 镜像):停笔相位完成后终态 completed,信封 stages 止于该相位;默认 CLOSE 全链。

## usage 口径裁定(定案②)

**信封与台账的 usage = 轮累计事件流口径**(`harness.usage()` 差分,经 budget-guard `sumUsageState`):轮内全部模型事件(含子任务、缓存命中)累加,轮结束一次性结算。pi-durable 的 UsageDoc 仅作 harness 内部观察面,不进信封、不进台账。

已知计量边界差(与旧管线对拍时,见 SHADOW-RUNBOOK §已知差异):v2 的 `in` 含 cache_read 且 `total` 再计一次缓存面,故 faux 同轮 v2 数字 ≥ 旧面;**cost 细胞不受影响**(价目表按 token 类分别计价,faux 恒 0,真实轮 cost 独立求和),台账 usage 三计数(in/out/total)在 shadow 对拍中归一,cost 逐字比。

## 台账兼容行(月度准入消费面)

成功轮台账行由 RETRO 步写(与旧管线同点、同形):`| 日期 | 轮次 | model | in=N out=N total=N cost=0.00000000 | pipeline:<round_id> |`。月度准入(`monthSpendOfLedgerText`)与前端 `opsLedger.ts` 解析面零改动——v2 轮天然流出兼容行,`tests/cron-launchers.test.mjs` 与 `tests/shadow-health-parity.test.mjs` 双钉。
