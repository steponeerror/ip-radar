// tasks/model-round.mjs — 单个模型轮任务(票 #228 T4;主会话 Q1 裁决 A):
// 一个 defineTask(name="ops-model-round")覆盖健康轮全部模型步,input.stage∈{TRIAGE,DEEP,SYNTH};
// 实现零复制 import 旧 steps.modelIO(input/consume)/gates.evalStageGate——本文件不重写提示词装配、
// 不重写收编、不重写门,只造旧 ctx 形状(round-ctx.buildRoundCtx)喂它们。
// 实例粒度(票面):健康轮 TRIAGE/SYNTH 相位各建一实例;DEEP 逐假设一实例(input.hid)。
// requestId=round-<roundId>[-<stage>-<hidSlug>](entry.requestIdFor 同族;首 attempt 携带=
// 崩溃重启幂等:同键重放返回既有 submission 零新调用,T0 smoke 已证;门败重试 attempt+1 的
// 重发不带 requestId——旧语义「同提示词重发」要新调用,requestId 只保 attempt 0 的 exactly-once)。
// DEEP 的微探针:submit 前按 runtime.conversationId 绑定宿主(tools/probes.bindProbeHost;
// 预算 ≤3/假设+轮次级 dup registry,旧 faux.mjs runRealStep 同口径;TRIAGE/SYNTH 无探针面=
// 旧 tools=[] 同义,未绑定会话调用探针=拒绝信封)。G_DEEP 聚合门不在本任务:逐假设步门评收编尾
// 后一次(旧 runModelStage forEach 语义),归健康轮 DEEP 相位(deepFinalize+G_DEEP)。
// 预算执法(票 #226 双点之环内):每 attempt 前 preModelCall①③、结算后 postModelCall②④——
// 违界即停不重试(旧 fatalBudget 语义;宁少算)。相位级 startedAt 入 checkpoint(墙钟续算不重置)。
// 旧管线零改动红线:ops/agent/ 只 import 不改;本文件属 ops/agent-v2/(shadow 期共存)。
import fs from "node:fs";
import path from "node:path";
import { defineTask } from "@earendil-works/pi-durable";
import { HEALTH_PIPELINE } from "../../agent/pipeline.mjs"; // 零复制:定义表单源
import { modelIO, forEachItems } from "../../agent/pipeline/steps.mjs"; // 零复制:模型步装配/收编/逐假设枚举
import { evalStageGate, appendGate } from "../../agent/pipeline/gates.mjs"; // 零复制:单发步门(G_TRIAGE/G_SYNTH)
import { hidSlug } from "../../agent/pipeline/steps.mjs";
import { loadFauxFixture, fauxFixtureSeeds, transcriptFile } from "../faux-face.mjs"; // MF3:faux 面分派件(fixture/seeds/transcript 名,旧 faux.mjs 位等价副本)
import { ERROR_CODES } from "../../agent/error-codes.mjs";
import { buildRoundCtx, opsRootOf, sha16 } from "../round-ctx.mjs";
import { roundKnobs, preModelCall, postModelCall } from "./budget-guard.mjs"; // 票 #226 环内执法面
import { bindProbeHost, unbindProbeHost } from "../tools/probes.mjs";

export const MODEL_STAGES = ["TRIAGE", "DEEP", "SYNTH"]; // stage 闭集(票 #228 Q1)

// requestId 幂等键(entry.requestIdFor 同族扩展:DEEP 逐假设带 hid 后缀)。
export const modelRequestId = (roundId, stage, hid) =>
  hid != null ? `round-${roundId}-${stage}-${hidSlug(hid)}` : `round-${roundId}-${stage}`;

// 旧 def(HEALTH_PIPELINE 定义表项;fail 三元组 retry/terminal 语义单源)
const defOf = (stage) => HEALTH_PIPELINE.find((d) => d.name === stage);

const EMPTY_USAGE = { input: 0, output: 0, totalTokens: 0, cost: 0 };

// assistant 应答文本(entry.mjs lastAssistantText 同形:末条 pi.assistant 的首个 text 块)
const lastAssistantText = (view) => (view.entries.filter((e) => e.kind === "pi.assistant").at(-1)?.model ?? [])
  .flatMap((m) => m.content ?? []).find((b) => b.type === "text")?.text ?? "";
// 末条 pi.assistant 的 stopReason(旧 runModelStep 失败面判据;块级缺省 null=faux 面无此字段)
const lastStopReason = (view) => (view.entries.filter((e) => e.kind === "pi.assistant").at(-1)?.model ?? [])[0]?.stopReason ?? null;
// 本轮新增 assistant 条目的 usage 求和(pi-ai Usage:input/output/totalTokens/cost.total;旧 addUsage 同面)
const usageSince = (view, n0) => {
  const u = { ...EMPTY_USAGE };
  for (const e of view.entries.slice(n0)) {
    if (e.kind !== "pi.assistant") continue;
    for (const m of e.model ?? []) {
      const w = m.usage ?? {};
      u.input += w.input ?? 0; u.output += w.output ?? 0; u.totalTokens += w.totalTokens ?? 0; u.cost += w.cost?.total ?? 0;
    }
  }
  return u;
};

// transcript 工件留痕(MF3;旧 faux.mjs runFauxStep/runRealStep 的 transcript 写盘副作用面,
// 行型以旧源为准位等价:faux.mjs:87-94(faux 面)/faux.mjs:135-139(真面)——
//   input 行:{type:"input",stage,model(仅真面:provider/modelId),system_sha,user_sha,meta}
//   registry_seed 行:faux 面=fixture seeds(call_id=sd.id);真面=微探针宿主登记行(call_id=sd.call_id)
//   message 行:逐 assistant 消息 {type:"message",role,content,stopReason}
// 留痕先于失败面判定与 io.consume(旧同序:faux.mjs「留痕先于失败面判定」)。DEEP 的
// deepConsume 宿主回填与 G_DEEP/G_SYNTH 门读面(deepSeeds/07 input 行 meta)都吃本工件——
// 零复制链条的 transcript 半在此接回。v2 偏差(注明):重试同会话→message 行含全部 attempt
// 回合(旧=每 attempt 新 Agent 重写单回合文件);门读面不读 message 行,证据不灭失优先。
async function writeTranscript(def, input, item, modelInput, view, ctx, runtime, context) {
  const face = input.modelFace ?? "faux";
  const seeds = face === "faux"
    ? fauxFixtureSeeds(loadFauxFixture(def, input.fixturesDir, item)) // 缺 fixture=infra(旧 loadFixture 同判例)
    : (boundProbeHost(runtime.conversationId)?.seeds ?? []); // 真面=宿主登记行(seeds 必从宿主内存取,t1-notes 结论)
  let modelField = null;
  if (face !== "faux") {
    const am = (await runtime.agent(context))?.model ?? null; // 本会话 agent 面(configure 时模型真源)
    if (am) modelField = `${am.provider}/${am.modelId}`;
  }
  const tf = transcriptFile(def, item);
  if (!tf) throw Object.assign(new Error(`transcript 名未装配:${def.name}`), { code: "infra" });
  const lines = [
    JSON.stringify({ type: "input", stage: input.stage, ...(modelField ? { model: modelField } : {}),
      system_sha: sha16(modelInput.systemPrompt), user_sha: sha16(modelInput.userMsg), meta: modelInput.meta ?? null }),
    ...seeds.map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.call_id, tool: sd.tool, sc: sd.sc })),
    ...view.entries.filter((e) => e.kind === "pi.assistant").flatMap((e) => e.model ?? [])
      .map((m) => JSON.stringify({ type: "message", role: "assistant", content: m.content, stopReason: m.stopReason ?? null })),
  ];
  fs.writeFileSync(path.join(ctx.dir, tf), lines.join("\n") + "\n");
}

// ctx 重建(checkpoint 是唯一真源;旧 runResume ctxShape 同构面):modelFace 缺省 faux(零网络安全缺省,
// 旧 runModelStep 同缺省);工件面=opsRoot/rounds/<roundId>(旧同形)。
function rebuildCtx(input, ck) {
  const env = process.env;
  const opsRoot = opsRootOf(env);
  const state = {
    schema: 1, round_id: input.roundId, type: "health", status: "in_flight", stage: input.stage,
    stages: ck.stageRecs ?? [], budget_cny: ck.budgetCny ?? null,
    budget_knobs: ck.budgetKnobs ?? null, fixtures_dir: input.fixturesDir ?? null,
    model_face: input.modelFace ?? "faux", prompt_hashes: ck.promptHashes ?? {},
    started_at: ck.startedAtIso, updated_at: ck.startedAtIso, resume_count: 0, replay_of: null,
  };
  const roundDir = path.join(opsRoot, "rounds", String(input.roundId));
  fs.mkdirSync(roundDir, { recursive: true }); // v2 面:旧 runPipeline 建轮目录的对应位(checkpoint 在 SQLite,工件目录仍磁盘)
  return buildRoundCtx({
    type: "health", roundId: input.roundId, opsRoot, env, log: (l) => process.stderr.write(`${l}\n`),
    fixturesDir: input.fixturesDir ?? null, modelFace: input.modelFace ?? "faux",
    budgetKnobs: ck.budgetKnobs, breakerKnobs: ck.breakerKnobs, state,
    usage: ck.usage ?? { ...EMPTY_USAGE }, modelCalls: ck.modelCalls ?? 0,
  });
}

export const OPS_MODEL_ROUND = defineTask({
  name: "ops-model-round",
  version: 1,
  initial: (input) => ({
    phase: "run", stage: input.stage, hid: input.hid ?? null, attempt: 0,
    startedAtIso: new Date().toISOString(), modelCalls: 0, usage: { ...EMPTY_USAGE },
    promptHashes: {}, stageRecs: [], budgetKnobs: null, breakerKnobs: null, budgetCny: null,
  }),
  phases: {
    // 单相位状态机:重试圈在 handler 内(api-map §3:相位无内建 per-stage retry;checkpoint.attempt 持数)。
    run: async (task, runtime, context) => {
      const input = task.input;
      const ck = task.state.checkpoint;
      const def = defOf(input.stage);
      if (!def) throw Object.assign(new Error(`stage 须 ∈ {${MODEL_STAGES.join("|")}}:${input.stage}`), { code: "bad_round" });
      const ctx = rebuildCtx(input, ck);
      const knobs = ck.budgetKnobs ?? roundKnobs(process.env, "health"); // #199 A1 幂等:resume 重建面兑底同判例
      const io = modelIO(def);
      const item = def.forEach
        ? forEachItems(def, ctx).find((b) => b.hid === input.hid) ?? null
        : null;
      if (def.forEach && !item)
        return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: "bad_round", message: `hid=${input.hid} 不在 04-dispatch-bundles(或金轨迹回退)` } } }), context);
      const modelInput = await io.input(ctx, item); // 零复制:旧装配面(提示词/上下文判例注入单源)
      // —— attempt 前查①③(budget-guard 环内;旧 runModelStage 检查点同构,违界即停不重试;
      // P1-4:①③以轮累计为基——roundBase=健康轮 spawn 时点快照(轮调用数/轮 usage/轮
      // started_at;直建子任务缺省=自身起点)。并行兄弟各自只见基数,全网约東在健康轮
      // WAIT_MODEL 收口 ①②④复查(宁多算不漏记口径)——
      const base = input.roundBase ?? { modelCalls: 0, usage: null, startedAtIso: ck.startedAtIso };
      const pre = preModelCall({ roundType: "health", knobs, modelCalls: (base.modelCalls ?? 0) + ck.modelCalls, startedAtIso: base.startedAtIso ?? ck.startedAtIso });
      if (!pre.ok)
        return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: pre.code, message: `${input.stage}:${pre.message}` } } }), context);
      // —— 微探针绑定(仅 DEEP;旧 faux.mjs runRealStep 同口径:≤3/假设+轮次级 dup registry)——
      const conv = await runtime.conversation(runtime.conversationId, context); // 本任务会话句柄(handle 需显式 id)
      if (!conv) throw Object.assign(new Error(`会话句柄缺失(conv=${runtime.conversationId})`), { code: "infra" });
      if (input.stage === "DEEP")
        bindProbeHost(runtime.conversationId, { dupRegistry: ctx.dupRegistry, budget: 3, dupLimit: knobs.dupCallLimit ?? 3 });
      try {
        // requestId:仅 attempt 0 携带(崩溃幂等);重试重发不带(要新调用)
        const draft = { type: "input", content: modelInput.userMsg, ...(ck.attempt === 0 ? { requestId: modelRequestId(input.roundId, input.stage, input.hid) } : {}) };
        const base = 0; // 一次性会话前提(健康轮每模型步实例建新 conversation):基线恒 0;复用会话须换 entry 游标(票面注记)
        const sub = await conv.submit(draft, context);
        const settled = await sub.wait(context);
        if (settled.status !== "done")
          throw Object.assign(new Error(`submission ${settled.status}`), { code: "model_face" });
        const view = await runtime.context(runtime.conversationId, context); // ContextView.entries=已提交可见 transcript(旧 faux 读面同源)
        await writeTranscript(def, input, item, modelInput, view, ctx, runtime, context); // MF3:留痕先于失败面判定与 io.consume(旧同序)
        const stopReason = lastStopReason(view);
        if (stopReason === "error" || stopReason === "aborted")
          throw Object.assign(new Error(`模型失败面 stopReason=${stopReason}`), { code: "model_face" }); // 旧 runModelStep 同判据
        const text = lastAssistantText(view).trim();
        const usage = usageSince(view, base);
        ctx.modelCalls = ck.modelCalls + 1;
        await io.consume(ctx, item, { text }); // 零复制:收编落盘(03-triage-hypotheses/05-deep-<hid>/07-synth)
        // —— 结算后查②④(旧检查点同构;P1-4:轮内累计=轮基数+本会话累计——会话含重试
        // 回合全计(宁多算不漏记);旧=ctx.usage(轮)+步内累计,同口径面)——
        const totalTokens = (base.usage?.totalTokens ?? 0) + usage.totalTokens;
        const costCny = (base.usage?.cost ?? 0) + usage.cost;
        const post = postModelCall({ roundType: "health", knobs, totalTokens, costCny });
        if (!post.ok)
          return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code: post.code, message: `${input.stage}:${post.message}` } } }), context);
        const promptSha = sha16(`${modelInput.systemPrompt}\n${modelInput.userMsg}`); // 旧 transcript prompt_sha 同源算法
        // —— 单发步门入重试圈(旧 runModelStage:G_TRIAGE/G_SYNTH;DEEP 聚合门归健康轮)——
        if (!def.forEach) {
          const gateRec = evalStageGate(def, ctx);
          appendGate(ctx.dir, ctx.roundId, gateRec);
          if (!gateRec.pass) throw Object.assign(new Error(`门败 ${def.gate}:${gateRec.reason}`), { code: gateRec.code ?? def.fail.terminal });
        }
        return void await runtime.commit(() => ({
          status: "terminal",
          outcome: {
            status: "completed",
            result: { stage: input.stage, hid: input.hid ?? null, round_id: input.roundId, usage, modelCalls: ctx.modelCalls, prompt_sha: promptSha },
          },
        }), context);
      } catch (e) {
        if (input.stage === "DEEP") unbindProbeHost(runtime.conversationId); // 失败重绑定=宿主计数清零(宁少算口径)
        const code = ERROR_CODES.includes(e?.code) ? e.code : "model_face";
        // 旧 fail.retry≤1 同提示词重发;坏 fixture/缺轮目录等 infra 类不重试(旧 retry 圈同捕面,此处按 code 收窄)
        const retryable = code === "model_face" || code === "empty_text" || e?.gateRec;
        if (retryable && ck.attempt < def.fail.retry)
          return void await runtime.commit((tx, cur) => ({
            status: "running",
            checkpoint: { ...cur.state.checkpoint, attempt: cur.state.checkpoint.attempt + 1 },
          }), context);
        return void await runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error: { code, message: `${input.stage}:${e?.message ?? String(e)}` } } }), context);
      }
    },
  },
  abort: async (_task, runtime, context) => {
    await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
  },
});

// 会话读面入口在相位 handler 内直用 runtime.context(convId, ctx)(ContextView.entries);
// 本文件不再另设包装(单一读面,与 entry.mjs lastAssistantText 同形工具函数在上)。

// 会话 transcript 计量面(健康轮 WAIT_MODEL 收口消费;P1-4 failed 子任务花费留痕——
// 宁多算不漏记:result 缺席时从会话实计,重试回合全计;completed 子任务走 result.usage
// 权威面不经此)。
export const conversationUsage = (view) => usageSince(view, 0);
export const conversationModelCalls = (view) =>
  view.entries.filter((e) => e.kind === "pi.assistant").reduce((n, e) => n + (e.model ?? []).length, 0);

