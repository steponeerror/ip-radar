// pipeline/faux.mjs — P0 模型步执行器:pi-ai fauxProvider + 真 Agent 循环(golden 同型;spec #161 P0)。
// canned 回合 = fixtures/pipeline/ 逐步脚本化(TRIAGE/SYNTH 单发;DEEP 逐假设 deep/<slug>.json);
// 需网络的测量腿走 registrySeed 判例(预登记结构化返回,门从登记表真算——golden exclusive_probe 同型)。
// P3/P4 换 loadModels 真 provider + 真工具时,本文件是唯一替换点;引擎/工件/门零改动。
// IO 全留痕(裁定「模型 I/O 全留痕可查看」):transcript 工件 = input 头(含 SYNTH 判例注入名,
// G_SYNTH 闭合校验面)+ registry_seed 行 + 逐回合 assistant 消息。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { hidSlug, modelIO } from "./steps.mjs";

const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

const transcriptName = (def, item) => def.name === "TRIAGE" ? "03-triage-transcript.jsonl"
  : def.name === "DEEP" ? `05-deep-${hidSlug(item.hid)}-transcript.jsonl`
  : def.name === "SYNTH" ? "07-synth-transcript.jsonl" : null;

function loadFixture(def, ctx, item) {
  // DEEP 逐假设 fixture(P4 #166 真开启):deep/<slug>.json,slug=hidSlug(hid);金轨迹轮=golden-track-canned。
  // 缺 fixture=配置面失败(infra;faux 面零网络,微探针=seed 登记表脚本化)。
  const p = def.name === "DEEP" ? path.join(ctx.fixturesDir, "deep", `${hidSlug(item.hid)}.json`)
    : path.join(ctx.fixturesDir, `${def.name.toLowerCase()}.json`);
  let fx;
  try { fx = JSON.parse(fs.readFileSync(p, "utf8")); } // 缺 fixture=配置面失败(infra;P0 未接真模型)
  catch { throw Object.assign(new Error(`模型步 fixture 缺:${p}`), { code: "infra" }); }
  if (!Array.isArray(fx.turns)) throw Object.assign(new Error(`模型步 fixture 缺 turns:${p}`), { code: "infra" });
  return fx;
}

export async function runModelStep(def, ctx, item) {
  const fx = loadFixture(def, ctx, item);
  const input = await modelIO(def).input(ctx, item);
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
