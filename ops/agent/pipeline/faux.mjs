// pipeline/faux.mjs — 模型步执行器(#170 真接线):面选择 + 双面执行(faux 面 / 真 provider 面)。
// canned 回合 = fixtures/pipeline/ 逐步脚本化(TRIAGE/SYNTH 单发;DEEP 逐假设 deep/<slug>.json);
// 需网络的测量腿走 registrySeed 判例(预登记结构化返回,门从登记表真算——golden exclusive_probe 同型)。
// 面选择(selectModelFace 纯函数,零网络可单测;#170):
//   显式 fixtures(--fixtures / opts.fixturesDir:自测、golden、replay 零成本审计)→ faux 面;
//   运行面(生产/cron 轮,无 --fixtures)→ 真 provider = models.mjs loadModels(legacy 轮同装载路径);
//   replay 继承原件面(state.model_face;pre-#170 轮恒 faux),resume 直接复原 state.model_face。
//   步→模型映射 STEP_ROUND:TRIAGE/SYNTH=health(缺省 glm-5.3-flash)/DEEP=discover(缺省 glm-5.3)
//   ——复用 OPS_MODEL_HEALTH/OPS_MODEL_DISCOVER 既有 env 旋钮,models.mjs 零改动。
// 本文件仍是唯一替换点:引擎(pipeline.mjs)只在 mkCtx/runReplay/runResume 记录面选择(state.model_face),
// 工件契约(transcript 行型)与门零改动——真面 input 行仅增 model 字段(门不读该行;faux 面行型逐字节不变)。
// IO 全留痕(裁定「模型 I/O 全留痕可查看」):transcript 工件 = input 头(真面含 model 名;含 SYNTH
// 判例注入名,G_SYNTH 闭合校验面)+ registry_seed 行(微探针登记;faux 面=fx.seeds 脚本化,
// 真面=微探针工具实测登记 #173)+ 逐回合 assistant 消息。#173 起真面 DEEP 装三只只读微探针
// (pipeline/microprobes.mjs,deep.md 工具闭集):真工具调用发 registry_seed 行(同 faux 面行型),
// confirmed/refuted 证据腿在真面可产合法登记表——#170 的设计内缺口(真面 tools=[] 编造 call_id
// 被 G_DEEP 门败,2026-10-24 生产冒烟实证)已闭合;TRIAGE/SYNTH 提示词无工具面,恒 tools=[]。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { loadModels } from "../models.mjs";
import { mkMicroprobeHost } from "./microprobes.mjs";
import { hidSlug, modelIO } from "./steps.mjs";

const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

// 面选择纯函数(#170):显式 fixtures=faux(自测/golden 面);否则继承面优先(replay 保真);缺省=real(运行面)。
export function selectModelFace({ fixturesExplicit = false, inherited = null } = {}) {
  if (fixturesExplicit) return "faux";
  return inherited ?? "real";
}

// 步→models.mjs 轮键映射(#170):TRIAGE/SYNTH=health 轻模型(flash),DEEP=discover 重模型(glm-5.3);
// env 旋钮 OPS_MODEL_HEALTH/OPS_MODEL_DISCOVER 与 legacy 轮同一拼写(models.mjs resolve 闭集 health|discover)。
export const STEP_ROUND = { TRIAGE: "health", SYNTH: "health", DEEP: "discover" };

const transcriptName = (def, item) => def.name === "TRIAGE" ? "03-triage-transcript.jsonl"
  : def.name === "DEEP" ? `05-deep-${hidSlug(item.hid)}-transcript.jsonl`
  : def.name === "SYNTH" ? "07-synth-transcript.jsonl" : null;

function loadFixture(def, ctx, item) {
  // DEEP 逐假设 fixture(P4 #166 真开启):deep/<slug>.json,slug=hidSlug(hid);金轨迹轮=golden-track-canned。
  // 缺 fixture=配置面失败(infra;faux 面零网络,微探针=seed 登记表脚本化)。
  const p = def.name === "DEEP" ? path.join(ctx.fixturesDir, "deep", `${hidSlug(item.hid)}.json`)
    : path.join(ctx.fixturesDir, `${def.name.toLowerCase()}.json`);
  let fx;
  try { fx = JSON.parse(fs.readFileSync(p, "utf8")); } // 缺 fixture=配置面失败(infra;真轮走 real 面不读 fixtures)
  catch { throw Object.assign(new Error(`模型步 fixture 缺:${p}`), { code: "infra" }); }
  if (!Array.isArray(fx.turns)) throw Object.assign(new Error(`模型步 fixture 缺 turns:${p}`), { code: "infra" });
  return fx;
}

// 真面装载(#170):ctx.models 注入缝优先(agent.mjs opts.models 同型金轨迹缝——自测以 fake 传输层
// 驱动真面代码路径,零网络);缺省 loadModels(models.mjs 三层装载,legacy 同路径)轮内缓存(目录只装载一次)。
async function providerBundle(ctx) {
  if (ctx.models) return ctx.models;
  ctx._providerBundle ??= await loadModels();
  return ctx._providerBundle;
}

export async function runModelStep(def, ctx, item) {
  const face = ctx.modelFace ?? ctx.state?.model_face ?? "faux"; // 手搓 ctx/pre-#170 state 缺省 faux(零网络安全缺省)
  const input = await modelIO(def).input(ctx, item);
  return face === "real" ? runRealStep(def, ctx, item, input) : runFauxStep(def, ctx, item, input);
}

async function runFauxStep(def, ctx, item, input) {
  const fx = loadFixture(def, ctx, item);
  const { Agent } = await import("@earendil-works/pi-agent-core");
  const { fauxProvider, createModels } = await import("@earendil-works/pi-ai");
  const faux = fauxProvider({ models: [{ id: `faux-${def.model.replace(/\//g, "-")}` }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses(fx.turns);
  const agent = new Agent({ initialState: { systemPrompt: input.systemPrompt, model: faux.getModel(), tools: [] },
    streamFn: models.streamSimple.bind(models) });
  const rec = { usage: { input: 0, output: 0, totalTokens: 0, cost: 0 }, messages: [] };
  agent.subscribe((ev) => {
    if (ev.type === "message_end" && ev.message?.role === "assistant") {
      const u = ev.message.usage ?? {};
      rec.usage.input += u.input ?? 0; rec.usage.output += u.output ?? 0;
      rec.usage.totalTokens += u.totalTokens ?? 0; rec.usage.cost += u.cost?.total ?? 0;
      rec.messages.push({ role: "assistant", content: ev.message.content, stopReason: ev.message.stopReason ?? null });
    }
  });
  await agent.prompt(input.userMsg);
  const lines = [
    JSON.stringify({ type: "input", stage: def.name, system_sha: sha(input.systemPrompt), user_sha: sha(input.userMsg), meta: input.meta ?? null }),
    ...(fx.seeds ?? (fx.seed ? [fx.seed] : [])).map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.id, tool: sd.tool, sc: sd.sc })), // 微探针登记行(P4 ≤3/假设,G_DEEP 计数面;fx.seed 单腿向后兼容)
    ...rec.messages.map((m) => JSON.stringify({ type: "message", ...m })),
  ];
  fs.writeFileSync(path.join(ctx.dir, transcriptName(def, item)), lines.join("\n") + "\n"); // 留痕先于失败面判定
  const assistant = [...agent.state.messages].reverse().find((m) => m.role === "assistant");
  if (!assistant) throw Object.assign(new Error("事件流无 assistant 消息"), { code: "model_face" });
  if (assistant.stopReason === "error" || assistant.stopReason === "aborted")
    throw Object.assign(new Error(`模型失败面 stopReason=${assistant.stopReason}`), { code: "model_face" });
  const text = (assistant.content ?? []).filter((c) => c.type === "text").map((c) => c.text).join("\n").trim();
  return { text, usage: rec.usage, prompt_sha: sha(`${input.systemPrompt}\n${input.userMsg}`) };
}

async function runRealStep(def, ctx, item, input) {
  // 真 provider 路径(#170):经 pi-agent-core Agent 真调用(legacy agent.mjs 同型装配)。
  // DEEP 真面装微探针闭集三只(#173);ctx.probeFetch=自测注入缝(fake fetch 层,缺省 safeFetch 真网络)。
  const { Agent } = await import("@earendil-works/pi-agent-core");
  let bundle, model;
  try {
    bundle = await providerBundle(ctx);
    model = bundle.resolve(STEP_ROUND[def.name]); // 步→轮键映射;未装载模型=配置面失败
  } catch (e) { throw Object.assign(new Error(`真 provider 装载失败(${def.name}):${e.message}`), { code: "infra" }); }
  const probes = def.name === "DEEP"
    ? mkMicroprobeHost({ // #199 A4:registry/dupLimit 从 ctx 传导(轮次级累计;旋钮单源 budget.mjs)
        fetchImpl: ctx.probeFetch,
        dupRegistry: ctx.dupRegistry ?? new Map(),
        dupLimit: ctx.budgetKnobs?.dupCallLimit ?? 3 })
    : null;
  const agent = new Agent({ initialState: { systemPrompt: input.systemPrompt, model, tools: probes?.tools ?? [] },
    streamFn: bundle.models.streamSimple.bind(bundle.models) });
  const rec = { usage: { input: 0, output: 0, totalTokens: 0, cost: 0 }, messages: [] };
  agent.subscribe((ev) => {
    if (ev.type === "message_end" && ev.message?.role === "assistant") {
      const u = ev.message.usage ?? {};
      rec.usage.input += u.input ?? 0; rec.usage.output += u.output ?? 0;
      rec.usage.totalTokens += u.totalTokens ?? 0; rec.usage.cost += u.cost?.total ?? 0;
      rec.messages.push({ role: "assistant", content: ev.message.content, stopReason: ev.message.stopReason ?? null });
      ctx.log?.(`[model] ${def.name}${item ? `:${item.hid}` : ""} turn ${rec.messages.length} stopReason=${ev.message.stopReason ?? "?"} usage(in=${u.input ?? 0} out=${u.output ?? 0})`); // legacy [turn] 行同型观测面(仅真面;驾驶舱 SSE 透传不解析)
    }
  });
  await agent.prompt(input.userMsg);
  const lines = [
    JSON.stringify({ type: "input", stage: def.name, model: `${model.provider}/${model.id}`, system_sha: sha(input.systemPrompt), user_sha: sha(input.userMsg), meta: input.meta ?? null }), // 真面增 model 字段(门不读 input 行;faux 面行型不变)
    ...(probes?.seeds ?? []).map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.call_id, tool: sd.tool, sc: sd.sc })), // 真面微探针登记行(#173:行型与 faux 面同型;≤3 由工具面预算闸先拒,门重算双执法)
    ...rec.messages.map((m) => JSON.stringify({ type: "message", ...m })), // 零探针步(TRIAGE/SYNTH/无调用 DEEP)=零 seed 行
  ];
  fs.writeFileSync(path.join(ctx.dir, transcriptName(def, item)), lines.join("\n") + "\n"); // 留痕先于失败面判定(同 faux)
  const assistant = [...agent.state.messages].reverse().find((m) => m.role === "assistant");
  if (!assistant) throw Object.assign(new Error("事件流无 assistant 消息"), { code: "model_face" });
  if (assistant.stopReason === "error" || assistant.stopReason === "aborted")
    throw Object.assign(new Error(`模型失败面 stopReason=${assistant.stopReason}`), { code: "model_face" }); // 失败语义同 faux 路径(重试≤1/降级/终态归引擎,面无关)
  const text = (assistant.content ?? []).filter((c) => c.type === "text").map((c) => c.text).join("\n").trim();
  return { text, usage: rec.usage, prompt_sha: sha(`${input.systemPrompt}\n${input.userMsg}`) }; // 真 usage 数字经引擎入信封与台账(RETRO)
}
