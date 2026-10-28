// tasks/health-round.mjs — 健康轮 v2 任务(票 #228 T4):pipeline.mjs HEALTH_PIPELINE 十态
// → defineTask 相位机,每态一相位;脚本步零复制调旧 steps.runStage/gates.evalStageGate(旧实现
// 单源,本文件只造 ctx 喂它们);模型步=创建 ops-model-round 子任务(逐假设一实例,票 Q1),
// WAIT_MODEL join 相位收口 usage → deepFinalize(零复制)+G_DEEP 聚合门。
// 失败三元组语义保留:retry≤def.fail.retry(handler 内圈,checkpoint.attempt 计数)→
// perItem 降级(RETRO/ANCHOR_SWEEP degrade 面在脚本步内返回)→ 终态=commit FAILED 相位
// 书挡 + outcome.failed(错误码闭集 ERROR_CODES)。G_CLOSE 回声哨逐字保留=零复制
// gates.evalStageGate(CLOSE def)(信封单行/往返解析/预算读数≤帽对拍——spec 谱系原则:环内
// 已执法,门只防工件漂移,非二次执法);CLOSE 步自身零复制 steps.runStage(09-budget.json
// 快照逐字节同旧:breaker snapshot 经 ops/agent-v2/breaker.mjs seam 同源旧 tools/breaker.mjs)。
// 预算双点接线(票 #226):entry 层 admitRound 不在本任务(宿主职责,旧 runPipeline 同位);
// 相位 handler 消费 budget-guard:步边界 stepBoundary(旧 runStages 检查点③同构,相位级
// startedAt 入 checkpoint——resume 沿原起算点续算,不重置)。requestId 幂等=子任务首 attempt 键。
// 旧管线零改动红线;tasks/index.mjs 冲突(T3 同面)预期内留给 merger。
import fs from "node:fs";
import { defineTask, configure } from "@earendil-works/pi-durable";
import { HEALTH_PIPELINE } from "../../agent/pipeline.mjs";
import * as steps from "../../agent/pipeline/steps.mjs";
import { evalStageGate, appendGate, appendGateBypass } from "../../agent/pipeline/gates.mjs";
import { STEP_ROUND } from "../../agent/pipeline/faux.mjs"; // 零复制:步→轮键映射(TRIAGE/SYNTH=health、DEEP=discover)
import { readBreakerKnobs } from "../../agent/tools/breaker.mjs"; // 零复制读面(轮始校验同旧 mkCtx)
import { ERROR_CODES } from "../../agent/error-codes.mjs";
import { loadModels } from "../models.mjs"; // 零复制 seam(定案 7:装载器不动)
import { buildRoundCtx, opsRootOf, composeEnvelope, skipWhenNoNeedDeep } from "../round-ctx.mjs";
import { roundKnobs, stepBoundary } from "./budget-guard.mjs";
import { OPS_MODEL_ROUND } from "./model-round.mjs";

const nowIso = () => new Date().toISOString();
const defOf = (n) => HEALTH_PIPELINE.find((d) => d.name === n);
export const RUNNABLE = HEALTH_PIPELINE.filter((d) => d.kind === "script" || d.kind === "model").map((d) => d.name); // PROBE…RETRO(旧 runnableOf 同推导)
const MODEL_PHASES = new Set(["TRIAGE", "DEEP", "SYNTH"]);

// ctx 重建:checkpoint.state 镜像旧 state.json 全字段(schema/round_id/stages/budget_knobs/
// fixtures_dir/model_face/prompt_hashes/started_at/replay_of/finding_exits/monthly_admission)。
export function rebuildRoundCtx(input, ck) {
  const env = process.env;
  const opsRoot = opsRootOf(env);
  fs.mkdirSync(path.join(opsRoot, "rounds", String(input.roundId)), { recursive: true }); // 旧 runPipeline 建轮目录对应位(工件面仍磁盘;state 面=SQLite checkpoint)
  const state = {
    schema: 1, round_id: input.roundId, type: "health", pipeline_mode: "pidurable",
    status: ck.failed ? "failed" : "in_flight", stage: ck.phase, stages: ck.state?.stages ?? [],
    budget_cny: ck.budgetCny, budget_knobs: ck.budgetKnobs, fixtures_dir: input.fixturesDir ?? null,
    model_face: input.modelFace ?? "faux", prompt_hashes: ck.state?.prompt_hashes ?? {},
    started_at: ck.startedAtIso, updated_at: nowIso(), resume_count: 0, replay_of: null,
    ...(ck.state?.monthly_admission != null ? { monthly_admission: ck.state.monthly_admission } : {}),
    ...(ck.state?.finding_exits != null ? { finding_exits: ck.state.finding_exits } : {}),
  };
  return buildRoundCtx({
    type: "health", roundId: input.roundId, opsRoot, env, log: (l) => process.stderr.write(`${l}\n`),
    fixturesDir: input.fixturesDir ?? null, modelFace: input.modelFace ?? "faux",
    budgetCny: ck.budgetCny, budgetKnobs: ck.budgetKnobs, breakerKnobs: ck.breakerKnobs,
    state, usage: ck.usage, modelCalls: ck.modelCalls,
  });
}

// —— 阶段记录/终态面(旧 failStage/writeState 同语义,载体=checkpoint 而非 state.json)——
const stageDone = (ck, rec, phase) => ({ ...ck, phase: nextPhase(phase ?? ck.phase), attempt: 0, children: null, spawnPhase: null, state: { ...ck.state, stages: [...(ck.state?.stages ?? []), rec], prompt_hashes: { ...(ck.state?.prompt_hashes ?? {}) }, stage: phase ?? ck.phase }, modelCalls: ck.modelCalls, usage: ck.usage });
function nextPhase(p) { const i = RUNNABLE.indexOf(p); return i >= 0 && i + 1 < RUNNABLE.length ? RUNNABLE[i + 1] : "CLOSE"; }
const failTerm = (ck, phase, code, message) => ({ ...ck, phase: "FAILED", failed: { code, message: `${phase}:${message}` } });

const mkAbort = (name) => async (_t, runtime, context) => {
  await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
};

// —— 模型相位共通:创建子任务(逐假设一实例)后转 WAIT_MODEL ——
let MODELS_BUNDLE = null; // 轮内缓存(旧 providerBundle 同型:目录只装载一次)
async function stepModelRef(def, input) {
  if (input.modelRef) return input.modelRef; // 显式覆盖(测试 faux 注入面)
  MODELS_BUNDLE ??= await loadModels();
  const m = MODELS_BUNDLE.resolve(STEP_ROUND[def.name]); // 步→轮键→模型(models.mjs 单源;缺省 flash/glm-5.3)
  if (!m) throw Object.assign(new Error(`模型未装载:${STEP_ROUND[def.name]}`), { code: "infra" });
  return { provider: m.provider, modelId: m.id };
}
async function spawnModelChildren(def, input, ck, runtime, context) {
  const ctx = rebuildRoundCtx(input, ck);
  const items = def.forEach ? steps.forEachItems(def, ctx) : [null]; // DEEP=bundles(零 bundle=金轨迹回退,旧 deepItems)
  const childIds = [];
  const modelRef = await stepModelRef(def, input); // 装载先于 commit(异步 IO 不入事务)
  await runtime.commit(async (tx, cur) => {
    for (const item of items) {
      // 每子任务一自有 conversation(api-map §3「子代理=自有 conversation」;并行 submit 不撞 busy)
      const conv = await tx.createConversation({ ownership: { kind: "task", taskId: cur.id } });
      const io = steps.modelIO(def);
      const minput = await io.input(rebuildRoundCtx(cur.input, cur.state.checkpoint), item); // 装配单源(与子任务内同函数)
      await configure(tx, conv.id, {
        model: modelRef,
        extensions: [runtime.registry.extension("ops")].filter(Boolean), // AgentChange 要 Extension 对象(applyChange names();存态才是字符串)
        instructions: minput.systemPrompt, // 旧提示词文件全文=会话 instructions(单源 prompts/health/*.md)
        ...(def.forEach ? { modelTools: ["reprobe_get", "reprobe_ua", "upstream_check"] } : { modelTools: [] }), // TRIAGE/SYNTH 无探针面=旧 tools=[]
      });
      const id = tx.createTask(OPS_MODEL_ROUND, {
        roundId: input.roundId, stage: def.name, ...(item ? { hid: item.hid } : {}),
        fixturesDir: input.fixturesDir ?? null, modelFace: input.modelFace ?? "faux",
      }, { ownership: { kind: "conversation" }, conversationId: conv.id });
      childIds.push(id);
    }
    return { status: "running", checkpoint: { ...cur.state.checkpoint, phase: "WAIT_MODEL", children: childIds, spawnPhase: def.name } };
  }, context);
}

// WAIT_MODEL:join 全部子任务 → usage/modelCalls/prompt_hashes 收编 → DEEP 收编尾 finalize+聚合门
async function waitModel(input, ck, runtime, context) {
  const ids = ck.children ?? [];
  const outcomes = await runtime.outcomes(ids, context); // 全 terminal 才返回(failFast 不用:逐假设败=降级面)
  const def = defOf(ck.spawnPhase);
  const ctx = rebuildRoundCtx(input, ck);
  const usage = { input: ck.usage?.input ?? 0, output: ck.usage?.output ?? 0, totalTokens: ck.usage?.totalTokens ?? 0, cost: ck.usage?.cost ?? 0 };
  let modelCalls = ck.modelCalls ?? 0;
  const promptHashes = { ...(ck.state?.prompt_hashes ?? {}) };
  const degradedItems = [];
  let failedN = 0;
  for (let i = 0; i < outcomes.length; i++) {
    const o = outcomes[i];
    const hid = def.forEach ? steps.forEachItems(def, ctx)[i]?.hid : null;
    const key = `${def.name}${hid ? `:${hid}` : ""}`;
    if (o.state.outcome.status === "completed") {
      const r = o.state.outcome.result;
      for (const k of ["input", "output", "totalTokens", "cost"]) usage[k] += r.usage?.[k] ?? 0;
      modelCalls += r.modelCalls ?? 1;
      promptHashes[key] = r.prompt_sha; // replay 审计面(旧 runModelStage prompt_hashes 同位)
    } else if (o.state.outcome.status === "failed") {
      failedN += 1;
      if (def.fail.perItem) degradedItems.push({ hid: hid ?? def.name, verdict: "unresolved", evidence: [], one_line: `重试尽降级 unresolved(${o.state.outcome.error?.message ?? "?"})` });
      else
        return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: o.state.outcome.error?.code ?? "model_face", message: `${def.name}:${o.state.outcome.error?.message ?? "?"}` } } }), context);
    }
  }
  if (def.fail.perItem && failedN === (def.forEach ? steps.forEachItems(def, ctx).length : 1) && failedN > 0) {
    const msg = `全部 ${failedN} 假设失败(model_face)`; // 旧 runModelStage 全败=终态(C稿 §2.2)
    return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: "model_face", message: msg } } }), context);
  }
  // DEEP 收编尾(零复制 deepFinalize:逐假设工件→05-deep-verdicts)+聚合门(G_DEEP,收编尾后一次)
  if (def.forEach) {
    steps.modelIO(def).finalize(ctx, { degradedItems });
    const gateRec = evalStageGate(def, ctx);
    appendGate(ctx.dir, ctx.roundId, gateRec);
    if (!gateRec.pass)
      return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: gateRec.code ?? def.fail.terminal, message: `门败 ${def.gate}:${gateRec.reason}` } } }), context);
  }
  const rec = { name: def.name, status: degradedItems.length ? "degraded" : "done", attempts: 1, dur_ms: 0, usage };
  await runtime.commit((tx, cur) => ({ status: "running", checkpoint: stageDone({ ...cur.state.checkpoint, usage, modelCalls, state: { ...cur.state.checkpoint.state, prompt_hashes: promptHashes } }, rec, cur.state.checkpoint.spawnPhase) }), context);
}

// —— 脚本相位执行体(零复制 steps.runStage + 门 + retry/degrade/终态;旧 runStages 同语义)——
async function runScriptPhase(def, input, ck, runtime, context) {
  const ctx = rebuildRoundCtx(input, ck);
  // 步边界查③(旧 runStages 检查点同构;resume 沿原 started_at 续算)
  const knobs = ck.budgetKnobs ?? roundKnobs(process.env, "health");
  const sb = stepBoundary({ roundType: "health", knobs, startedAtIso: ck.startedAtIso });
  if (!sb.ok)
    return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: sb.code, message: `${def.name}:${sb.message}` } } }), context);
  // DISPATCH skipWhen(旧 SKIP_WHEN.no_need_deep 零谓词重写,round-ctx 逐字副本)
  if (def.skipWhen === "no_need_deep" && skipWhenNoNeedDeep(ctx)) {
    const rec = { name: def.name, status: "skipped", attempts: 0, dur_ms: 0, usage: null };
    return void await runtime.commit((tx, cur) => ({ status: "running", checkpoint: stageDone(cur.state.checkpoint, rec) }), context);
  }
  const t0 = performance.now();
  let attempt = ck.attempt ?? 0, degraded = null;
  for (;;) {
    try { degraded = (await steps.runStage(def, ctx)) ?? null; break; } // 零复制:脚本步单源
    catch (e) {
      if (attempt < (def.fail.retry ?? 0)) { attempt += 1; continue; }
      const code = ERROR_CODES.includes(e?.code) ? e.code : "infra";
      return void await runtime.commit((tx, cur) => ({ status: "running", checkpoint: failTerm(cur.state.checkpoint, def.name, code, e?.message ?? String(e)) }), context);
    }
  }
  if (degraded?.skipGate) appendGateBypass(ctx.dir, ctx.roundId, def, degraded.degraded);
  else {
    const gateRec = evalStageGate(def, ctx); // 门单源(含 G_CLOSE 回声哨:信封单行/往返解析/预算读数≤帽)
    appendGate(ctx.dir, ctx.roundId, gateRec);
    if (!gateRec.pass) {
      const code = gateRec.code ?? def.fail.terminal;
      return void await runtime.commit((tx, cur) => ({ status: "running", checkpoint: failTerm(cur.state.checkpoint, def.name, code, `门败 ${def.gate}:${gateRec.reason}`) }), context);
    }
  }
  const rec = { name: def.name, status: degraded ? "degraded" : "done", attempts: attempt + 1, dur_ms: Math.round(performance.now() - t0), usage: null };
  // ANCHOR_SWEEP 写 finding_exits 入 state(旧步内 ctx.state 直写;v2 面同步回 checkpoint)
  const nextCk = stageDone(ck, rec);
  if (ctx.state.finding_exits != null) nextCk.state = { ...nextCk.state, finding_exits: ctx.state.finding_exits };
  await runtime.commit(() => ({ status: "running", checkpoint: nextCk }), context);
}

// —— CLOSE 书挡(旧 finishClose 同序:存在性校验→09-budget.json→信封→G_CLOSE→终态)——
async function runClose(input, ck, runtime, context) {
  const ctx = rebuildRoundCtx(input, ck);
  const def = defOf("CLOSE");
  const rec = { name: "CLOSE", status: "done", attempts: 1, dur_ms: 0, usage: null };
  try {
    await steps.runStage(def, ctx); // 零复制:09-budget.json(breaker 快照)+pkg 校验同字节
    ctx.state.stages.push(rec);
    ctx.state.status = "done"; ctx.state.stage = "CLOSE"; ctx.state.updated_at = nowIso();
    const envelope = composeEnvelope(ctx, { ok: true }); // round-ctx 逐字副本(旧 composeEnvelope 同形)
    ctx.envelope = envelope;
    const gr = evalStageGate(def, ctx); // G_CLOSE 回声哨:环内已执法,门只防工件漂移(spec 谱系原则)
    appendGate(ctx.dir, ctx.roundId, gr);
    if (!gr.pass) throw Object.assign(new Error(`门败 G_CLOSE:${gr.reason}`), { code: "infra" });
    await runtime.commit(() => ({
      status: "terminal",
      outcome: { status: "completed", result: { round_id: input.roundId, envelope, dir: ctx.dir, usage: ctx.usage } },
    }), context);
  } catch (e) {
    const code = ERROR_CODES.includes(e?.code) ? e.code : "infra";
    await runtime.commit(() => ({
      status: "terminal",
      outcome: { status: "failed", error: { code, message: `CLOSE:${e?.message ?? String(e)}` } },
    }), context);
  }
}

// FAILED 书挡(旧终态:工件全保留,replay 可救——v2 面=checkpoint 留全量 stageRecs)
async function runFailed(input, ck, runtime, context) {
  await runtime.commit(() => ({
    status: "terminal",
    outcome: { status: "failed", error: { code: ck.failed?.code ?? "infra", message: ck.failed?.message ?? "FAILED" } },
  }), context);
}

// —— 相位表:十态 + WAIT_MODEL join + FAILED 书挡 ——
const PHASES = { WAIT_MODEL: (t, r, c) => waitModel(t.input, t.state.checkpoint, r, c), FAILED: (t, r, c) => runFailed(t.input, t.state.checkpoint, r, c) };
for (const name of RUNNABLE) {
  const def = defOf(name);
  PHASES[name] = MODEL_PHASES.has(name)
    ? (t, r, c) => spawnModelChildren(def, t.input, t.state.checkpoint, r, c)
    : (t, r, c) => runScriptPhase(def, t.input, t.state.checkpoint, r, c);
}
PHASES.CLOSE = (t, r, c) => runClose(t.input, t.state.checkpoint, r, c);

export const OPS_HEALTH_ROUND = defineTask({
  name: "ops-health-round",
  version: 1,
  initial: (input) => ({
    phase: "PROBE", attempt: 0, children: null, spawnPhase: null, failed: null,
    startedAtIso: new Date().toISOString(),
    budgetCny: (() => { const raw = process.env.OPS_PIPELINE_BUDGET_CNY ?? "0.05"; const v = +raw; if (!Number.isFinite(v) || v < 0) throw Object.assign(new Error(`OPS_PIPELINE_BUDGET_CNY 须为非负数,得到:${raw}`), { usage: true }); return v; })(),
    budgetKnobs: roundKnobs(process.env, "health"), // 轮始校验(旧 mkCtx 同判例:非法 throw usage)
    breakerKnobs: readBreakerKnobs(process.env), // #199 B 同判例
    modelCalls: 0, usage: { input: 0, output: 0, totalTokens: 0, cost: 0 },
    state: { stages: [], prompt_hashes: {} },
  }),
  phases: PHASES,
  abort: mkAbort("ops-health-round"),
});
