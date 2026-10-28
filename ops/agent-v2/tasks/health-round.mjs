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
import path from "node:path"; // MF1:rebuildRoundCtx 建轮目录用 path.join(漏 import 首相位即 ReferenceError;旧遗漏修复)
import { defineTask, configure } from "@earendil-works/pi-durable";
import { HEALTH_PIPELINE } from "../../agent/pipeline.mjs";
import * as steps from "../../agent/pipeline/steps.mjs";
import { evalStageGate, appendGate, appendGateBypass } from "../../agent/pipeline/gates.mjs";
import { STEP_ROUND } from "../../agent/pipeline/faux.mjs"; // 零复制:步→轮键映射(TRIAGE/SYNTH=health、DEEP=discover)
import { readBreakerKnobs } from "../../agent/tools/breaker.mjs"; // 零复制读面(轮始校验同旧 mkCtx)
import { ERROR_CODES } from "../../agent/error-codes.mjs";
import { loadModels } from "../models.mjs"; // 零复制 seam(定案 7:装载器不动)
import { buildRoundCtx, opsRootOf, composeEnvelope, skipWhenNoNeedDeep } from "../round-ctx.mjs";
import { roundKnobs, stepBoundary, postModelCall, knobNames } from "./budget-guard.mjs"; // P1-4:收口复查①②④ 面
import { OPS_MODEL_ROUND, conversationUsage, conversationModelCalls } from "./model-round.mjs"; // P1-4:failed 子任务留痕计量面
import { mkFauxFace, loadFauxFixture } from "../faux-face.mjs"; // 修复⑥:faux 面分派件(旧 faux.mjs 位等价副本)
import { OPS_PROBE_TOOLS } from "../tools/probes.mjs"; // DEEP 真面探针闭集(AgentChange.modelTools 要 ToolRegistration 对象非名字串——applyChange names() 映射 .name)

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
const stageDone = (ck, rec, phase) => ({ ...ck, phase: nextPhase(phase ?? ck.phase), attempt: 0, children: null, childConvs: null, spawnPhase: null, state: { ...ck.state, stages: [...(ck.state?.stages ?? []), rec], prompt_hashes: { ...(ck.state?.prompt_hashes ?? {}) }, stage: phase ?? ck.phase }, modelCalls: ck.modelCalls, usage: ck.usage });
function nextPhase(p) { const i = RUNNABLE.indexOf(p); return i >= 0 && i + 1 < RUNNABLE.length ? RUNNABLE[i + 1] : "CLOSE"; }
const failTerm = (ck, phase, code, message) => ({ ...ck, phase: "FAILED", failed: { code, message: `${phase}:${message}` } });

const mkAbort = () => async (_t, runtime, context) => { // 终审小项:无参名(name 未用)
  await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
};

// 起步相位缝(修复⑥ E2E 面;旧 pipeline.mjs replay --from STAGE 同义语义):生产 cron
// 不传(缺省 PROBE 全十态);测试/faux 审计用前置工件面从指定相位起步(零网络红线下
// PROBE 的真探测/矩阵面不可入测试)。闭集=RUNNABLE+CLOSE(WAIT_MODEL=join 态/FAILED=终态
// 书挡,不可起步);非法=bad_round(闭集成员)。
const startPhaseOf = (p, input) => {
  if (p == null) return "PROBE";
  if (![...RUNNABLE, "CLOSE"].includes(p))
    throw Object.assign(new Error(`fromPhase 须 ∈ {${[...RUNNABLE, "CLOSE"].join("|")}}:${p}`), { code: "bad_round" });
  // toPhase(旧 pipeline.mjs replay --to 镜像;shadow 载具用):停在 toPhase 完成后(含其门+台账),
  // 不入 CLOSE 书挡。默认 CLOSE=全链。合法性:toPhase 须晚于 fromPhase(否则零相位空转)。
  const tp = input?.toPhase ?? "CLOSE";
  if (![...RUNNABLE, "CLOSE"].includes(tp))
    throw Object.assign(new Error(`toPhase 须 ∈ {${[...RUNNABLE, "CLOSE"].join("|")}}:${tp}`), { code: "bad_round" });
  if (RUNNABLE.includes(tp) && RUNNABLE.indexOf(tp) <= RUNNABLE.indexOf(p))
    throw Object.assign(new Error(`toPhase(${tp}) 须晚于 fromPhase(${p})`), { code: "bad_round" });
  return p;
};
// 停笔点统一书挡(相位完成、门已过后):终态 completed + 信封(旧 replay --to 同义:
// 不落 09-budget/G_CLOSE,信封 stages 止于停笔相位)。P2-4:与 stageDone 同一 commit
// 原子落(两笔问隔窗崩溃会越 toPhase 直入 CLOSE,违冻结口径)——故本函数只出 commit
// 载荷,由调用方合入唯一一笔 commit。
function stopOutcome(input, ck, def) {
  const fin = rebuildRoundCtx(input, ck);
  fin.state.status = "done";
  fin.state.stage = def.name;
  fin.state.updated_at = nowIso();
  const envelope = composeEnvelope(fin, { ok: true });
  return {
    status: "terminal",
    outcome: { status: "completed", result: { round_id: input.roundId, envelope, dir: fin.dir, usage: fin.usage } },
  };
}

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
  const childConvs = {}; // taskId → convId(P1-4:WAIT_MODEL 收口读 failed 子任务会话留痕计量)
  // faux 面分派(修复⑥/审查 P2-4 最小接面,只接分派不动 T5 台账兼容面):显式 modelRef
  // (测试注入面)优先;否则 modelFace 缺省 faux(零网络安全缺省,rebuildCtx 同口径;生产
  // cron 须显式传 real)→ 逐子任务一 fauxProvider 罐装回合(旧 runFauxStep 每步 new
  // Agent 同义;provider 唯一名防并行串台,见 faux-face.mjs 头注),注册进 harness
  // Models(runtime.models 面);真面路径不变(loadModels 真装载)。进程内注册=崩溃重启
  // 后在飞子任务 provider 不可复现(faux 面限制:测试/审计面,生产不走;宁少算不静默切真面)。
  const explicitRef = input.modelRef ?? null;
  const fauxFace = !explicitRef && (input.modelFace ?? "faux") === "faux";
  const modelRef = explicitRef ?? (fauxFace ? null : await stepModelRef(def, input)); // 装载先于 commit(异步 IO 不入事务)
  const fauxRefs = new Map(); // items 索引 → modelRef(faux 面逐子任务)
  if (fauxFace) {
    items.forEach((item, i) => {
      const { faux, modelRef: ref } = mkFauxFace(def, { roundId: input.roundId, stage: def.name, hid: item?.hid });
      faux.setResponses(loadFauxFixture(def, input.fixturesDir, item).turns); // 缺 fixture=infra(旧 loadFixture 同判例,提交前抛)
      runtime.models.setProvider(faux.provider);
      fauxRefs.set(i, ref);
    });
  }
  // P1-4:轮级基数快照(spawn 时点轮累计)随 input 入子任务——子任务 pre①③/post②④
  // 以轮为基(旧 runModelStage 轮累计执法同口径;并行兄弟各自只见基数,全网收口在本轮
  // WAIT_MODEL ①②④复查)
  const roundBase = { modelCalls: ck.modelCalls ?? 0, usage: ck.usage ?? null, startedAtIso: ck.startedAtIso };
  await runtime.commit(async (tx, cur) => {
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      // 每子任务一自有 conversation(api-map §3「子代理=自有 conversation」;并行 submit 不撞 busy)
      const conv = await tx.createConversation({ ownership: { kind: "task", taskId: cur.id } });
      const io = steps.modelIO(def);
      const minput = await io.input(rebuildRoundCtx(cur.input, cur.state.checkpoint), item); // 装配单源(与子任务内同函数)
      await configure(tx, conv.id, {
        model: fauxRefs.get(i) ?? modelRef,
        extensions: [runtime.registry.extension("ops")].filter(Boolean), // AgentChange 要 Extension 对象(applyChange names();存态才是字符串)
        instructions: minput.systemPrompt, // 旧提示词文件全文=会话 instructions(单源 prompts/health/*.md)
        // 真 DEEP=微探针闭集三只(旧 runRealStep 同面;modelTools 传 ToolRegistration 对象,
        // 框架 applyChange 存名字串——旧代码传名字串会 map 出 undefined 存储炸 strict JSON,
        // 执行面暴露的第四处暗病,随 E2E 一并修复);faux 面恒 [](旧 runFauxStep tools=[] 同义:
        // 罐装回合无工具面,种子=fixture registry_seed 行由 model-round 落盘)
        ...(def.forEach && !fauxFace ? { modelTools: OPS_PROBE_TOOLS } : { modelTools: [] }),
      });
      const id = await tx.createTask(OPS_MODEL_ROUND, {
        roundId: input.roundId, stage: def.name, ...(item ? { hid: item.hid } : {}),
        fixturesDir: input.fixturesDir ?? null, modelFace: input.modelFace ?? "faux",
        roundBase,
      }, { ownership: { kind: "conversation" }, conversationId: conv.id });
      childIds.push(id);
      childConvs[String(id)] = conv.id;
    }
    // MF2:spawn 与 wait 同一 commit(框架 README §Child Tasks Canonical 模式;types.d.ts
    // outcomes「rejects when one is missing or not terminal. Used after a wait」)——提交
    // waiting+on+policy,子任务全 settle 后才恢复 WAIT_MODEL 相位;逐假设败=降级面,故
    // allSettled 非 failFast(旧 runModelStage perItem 语义对应)。
    return { status: "waiting", checkpoint: { ...cur.state.checkpoint, phase: "WAIT_MODEL", children: childIds, childConvs, spawnPhase: def.name }, on: childIds, policy: "allSettled" };
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
    if (o.status === "completed") { // TaskOutcome 面值即 {status,result|error,reason}(types.d.ts:510;无 .state 包裹)
      const r = o.result;
      for (const k of ["input", "output", "totalTokens", "cost"]) usage[k] += r.usage?.[k] ?? 0;
      modelCalls += r.modelCalls ?? 1;
      promptHashes[key] = r.prompt_sha; // replay 审计面(旧 runModelStage prompt_hashes 同位)
    } else if (o.status === "failed") {
      failedN += 1;
      // P1-4 failed 子任务花费留痕(哨面宁多算不漏记):result 缺席 → 从其会话 transcript
      // 实计(pi.assistant usage 求和/调用数=assistant 消息数;重试回合全计)——失败重试
      // 已花的钱不从轮账面消失(09-budget.json 读数与真实花费不背离)。读败只 stderr 注记
      // 不阻轮(缺口显式可见,不静默归零)。
      const convId = ck.childConvs?.[String(ids[i])];
      if (convId != null) {
        try {
          const view = await runtime.context(convId, context);
          const cu = conversationUsage(view);
          for (const k of ["input", "output", "totalTokens", "cost"]) usage[k] += cu[k];
          modelCalls += conversationModelCalls(view);
        } catch (e) { process.stderr.write(`[waitModel] failed 子任务留痕读败(conv=${convId}):${e?.message ?? e}\n`); }
      }
      if (def.fail.perItem) degradedItems.push({ hid: hid ?? def.name, verdict: "unresolved", evidence: [], one_line: `重试尽降级 unresolved(${o.error?.message ?? "?"})` });
      else
        return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: o.error?.code ?? "model_face", message: `${def.name}:${o.error?.message ?? "?"}` } } }), context); // 终审修复:TaskOutcome 无 .state 包裹(类型面同注),原 o.state.outcome 会 TypeError→框架 fault
    }
  }
  // —— P1-4 WAIT_MODEL 收口复查①②④(轮级累计口径;并行子任务 pre/post 各自只见基数,
  // 收口补全网;违界即停不降级——旧 fatalBudget 同语义。①口径=已计>帽,不预支 +1
  // (overCallsCap 的 attempt-前查口径归子任务;帽内恰满的轮不误杀)——
  const knobs4 = ck.budgetKnobs ?? roundKnobs(process.env, "health");
  if (modelCalls > knobs4.maxModelCalls)
    return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: "budget_exceeded", message: `预算四界①(收口):轮累计模型调用 ${modelCalls} > ${knobs4.maxModelCalls}(${knobNames("health").calls})` } } }), context);
  const post = postModelCall({ roundType: "health", knobs: knobs4, totalTokens: usage.totalTokens, costCny: usage.cost });
  if (!post.ok)
    return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: post.code, message: `${def.name}:${post.message}` } } }), context);
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
  const finCk = stageDone({ ...ck, usage, modelCalls, state: { ...ck.state, prompt_hashes: promptHashes } }, rec, ck.spawnPhase);
  // toPhase 停笔(模型相位版;与 stageDone 同 commit 原子落——P2-4)
  if (input.toPhase && input.toPhase === def.name)
    return void await runtime.commit(() => stopOutcome(input, finCk, def), context);
  await runtime.commit(() => ({ status: "running", checkpoint: finCk }), context);
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
  // toPhase 停笔(脚本相位版;与 stageDone 同 commit 原子落——P2-4:停在门后,不丢台账/工件)
  if (input.toPhase && input.toPhase === def.name)
    return void await runtime.commit(() => stopOutcome(input, nextCk, def), context);
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
    phase: startPhaseOf(input.fromPhase, input), attempt: 0, children: null, childConvs: null, spawnPhase: null, failed: null,
    startedAtIso: new Date().toISOString(),
    budgetCny: (() => { const raw = process.env.OPS_PIPELINE_BUDGET_CNY ?? "0.05"; const v = +raw; if (!Number.isFinite(v) || v < 0) throw Object.assign(new Error(`OPS_PIPELINE_BUDGET_CNY 须为非负数,得到:${raw}`), { usage: true }); return v; })(),
    budgetKnobs: roundKnobs(process.env, "health"), // 轮始校验(旧 mkCtx 同判例:非法 throw usage)
    breakerKnobs: readBreakerKnobs(process.env), // #199 B 同判例
    modelCalls: 0, usage: { input: 0, output: 0, totalTokens: 0, cost: 0 },
    // P1-5:admission 读数入链——submitter(Entry/T5)把 admitRound 的 admission 读数对象
    // 入任务 input.monthlyAdmission → initial → ck.state.monthly_admission(rebuildRoundCtx
    // 已透传)→ CLOSE 09-budget.json readings.monthly(旧轮=月度准入投影对象;缺席=null
    // =replay 面旧同形)。旧 pipeline.mjs:396 ctx.state.monthly_admission 同位。
    state: { stages: [], prompt_hashes: {}, ...(input.monthlyAdmission != null ? { monthly_admission: input.monthlyAdmission } : {}) },
  }),
  phases: PHASES,
  abort: mkAbort("ops-health-round"),
});
