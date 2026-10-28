// rounds.test.mjs — T4(票 #228)任务面测试:①breaker seam 五通道闭集+快照只读不造文件
// (Q3③);②微探针三件套闭集+replay unsafe+未绑定拒绝/绑定派发(stub 传输层零网络);
// ③ops-model-round E2E(fauxProvider 注入,零网络零密钥):TRIAGE 一发→工件落盘→G_TRIAGE
// 过→任务 terminal completed;④健康轮相位结构面:相位闭集=旧 runnableOf+CLOS+WAIT_MODEL+
// FAILED 书挡,轮始旋钮非法=usage 错(旧 mkCtx 同判例);⑤requestId 形状(Q1)。
// 真 GLM:本文件零调用(预算 ¥0;provider 路径由 tests/smoke-glm.test.mjs 既有 18 例覆盖,
// 真轮对拍=T5 shadow harness 票面)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Harness } from "@earendil-works/pi-durable";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { fauxProvider, createModels } from "@earendil-works/pi-ai";
import * as v2breaker from "../breaker.mjs"; // 零复制 re-export seam(被测面)
import { BREAKER_CHANNELS, mkBreaker, readBreakerKnobs } from "../../agent/tools/breaker.mjs"; // 旧真源(对拍基准)
import { OPS_PROBE_TOOLS, bindProbeHost, unbindProbeHost } from "../tools/probes.mjs";
import { OPS_MODEL_ROUND, modelRequestId, MODEL_STAGES } from "../tasks/model-round.mjs";
import { OPS_HEALTH_ROUND, RUNNABLE } from "../tasks/health-round.mjs";
import { buildRegistry } from "../registry.mjs";
import { HEALTH_PIPELINE } from "../../agent/pipeline.mjs";

// ── ① breaker seam:五通道闭集 + 快照只读不造文件(Q3③;旧 CLOSE 步同面)──────────
test("breaker seam:五通道闭集逐名;snapshot() 只读零写(回声律:不造文件)", async () => {
  assert.deepEqual(v2breaker.BREAKER_CHANNELS, ["fetch_url", "gh_search", "rss_parse", "web_read", "web_search"]);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-breaker-"));
  try {
    const file = path.join(tmp, "breaker.json");
    const knobs = { threshold: 1, cooldownS: 60 }; // 阈值 1:单败即 open(旧语义;写侧转移才 persist)
    const face = mkBreaker({ file, env: {}, round: "t", ledgerFile: path.join(tmp, "ledger.md"), knobs, log: () => {} }); // ledger 指 tmp:台账留痕不落生产面
    const snap = face.snapshot();
    assert.ok(snap && typeof snap === "object", "快照非对象");
    assert.equal(fs.existsSync(file), false, "CLOSE 观察面 snapshot() 不得创建 breaker.json(回声律)");
    // 写侧(=T3 通道工具面,票面注记):闭集内名结算 → 状态转移才 persist(状态文件才出现)——与 CLOSE 只读面互锁
    const t1 = face.record("fetch_url", { ok: false, code: "channel_auth" }); // counted code 才计入 consec(BREAKER_COUNTED_CODES 闭集)
    assert.equal(t1, "opened", "阈值 1:单败即 opened 转移(旧转移词 opened)");
    assert.equal(fs.existsSync(file), true, "转移后状态文件应在(写侧与 CLOSE 只读面互锁)");
    assert.equal(face.verdict("not_a_channel").action, "allow", "通道外名=fail-判读面 allow 零写(旧语义)");
    assert.equal(face.verdict("fetch_url").action, "block", "open 态闭集内名=block(冷却未到)");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── ② 微探针三件套(Q2:只迁三只,全 replay unsafe)────────────────────────────
test("微探针闭集=三只全 replay:unsafe;未绑定会话=拒绝信封;绑定后派发旧宿主(stub 零网络)", async () => {
  assert.deepEqual(OPS_PROBE_TOOLS.map((t) => t.name).sort(), ["reprobe_get", "reprobe_ua", "upstream_check"]);
  assert.ok(OPS_PROBE_TOOLS.every((t) => t.replay === "unsafe"), "三只全 unsafe(真网络探测,重放=出网)");
  const byName = (n) => OPS_PROBE_TOOLS.find((t) => t.name === n);
  // 未绑定会话(TRIAGE/SYNTH 无探针面同义):拒绝信封,不执行任何网络
  const refused = await byName("reprobe_get").execute({ url: "https://example.test/x" }, { conversationId: "conv-unbound", callId: "c1" });
  assert.equal(refused.isError, true);
  assert.equal(refused.structuredOutput.ok, false);
  // 绑定会话:stub 传输层派发进旧宿主(读数结构化面同源;零真网络)
  bindProbeHost("conv-bound", { fetchImpl: async () => ({ status: 200, headers: { "last-modified": "Tue, 01 Jan 2026 00:00:00 GMT" }, finalUrl: "https://example.test/f", bytes: 4 }) });
  try {
    const r = await byName("reprobe_get").execute({ url: "https://example.test/x" }, { conversationId: "conv-bound", callId: "c2" });
    assert.equal(r.isError, undefined, "绑定后成功读数非 isError");
    assert.equal(r.structuredOutput.ok, true);
    assert.equal(r.structuredOutput.status, 200);
    assert.equal(typeof r.structuredOutput.age_days, "number", "age_days 由旧宿主回填(值由宿主回填 A 一律)");
  } finally { unbindProbeHost("conv-bound"); }
});

// ── ③ ops-model-round E2E(fauxProvider;零网络零密钥)─────────────────────────
test("ops-model-round E2E:TRIAGE 一发→03-triage-hypotheses.json 落盘→G_TRIAGE PASS→terminal completed", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-modelround-"));
  const prevDocs = process.env.DOCS_ROOT, prevDb = process.env.OPS_V2_DB;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  const roundId = "2026-10-28-1234-health";
  const roundDir = path.join(process.env.DOCS_ROOT, "ops", "rounds", roundId);
  fs.mkdirSync(roundDir, { recursive: true });
  // 前置工件:02-verify-survivors.json(幸存集=canned 假设两 signal_id,G_TRIAGE 穷尽判据)
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify({
    survivors: [
      { signal_id: "https://cinsscore.com/list/ci-badguys.txt", source: "cinsscore", bucket: "frozen", age_days: 220, url: "https://cinsscore.com/list/ci-badguys.txt" },
      { signal_id: "https://www.binarydefense.com/banlist.txt", source: "binarydefense", bucket: "frozen", age_days: 210, url: "https://www.binarydefense.com/banlist.txt" },
    ], known_noise_digest: [] }, null, 2) + "\n");
  // canned 回合=旧 fixtures/pipeline/triage.json 同型(G_TRIAGE 闭集值全过);fixturesDir=同源
  // (MF3 后 faux 面 transcript 种子/fixture 必件——旧 loadFixture 同判例)
  const fixturesDir = path.resolve(import.meta.dirname, "..", "..", "agent", "fixtures", "pipeline");
  const canned = JSON.parse(fs.readFileSync(path.join(fixturesDir, "triage.json"), "utf8"));
  const systemPrompt = fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "agent", "prompts", "health", "triage.md"), "utf8");

  const { fauxProvider: fp, createModels: cm } = { fauxProvider, createModels };
  const faux = fp({ models: [{ id: "glm-5.3-flash" }] });
  const models = cm();
  models.setProvider(faux.provider);
  faux.setResponses(canned.turns);
  const storage = await openNodeSqliteStorage(path.join(tmp, "t.sqlite"));
  const harness = await Harness.open(storage, { models, registry: buildRegistry() }, BACKGROUND_CONTEXT);
  const context = BACKGROUND_CONTEXT;
  try {
    harness.resume();
    const m = faux.getModel();
    const opsExt = buildRegistry().snapshot().installed().find((e) => e.name === "ops"); // AgentChange.extensions 要 Extension 对象(applyChange names() 读 .name;存态才是字符串)
    const root = await harness.root(context, { agent: { model: { provider: m.provider, modelId: m.id }, extensions: [opsExt], instructions: systemPrompt, modelTools: [] } });
    const taskId = await root.commit((tx) => tx.createTask(OPS_MODEL_ROUND, { roundId, stage: "TRIAGE", modelFace: "faux", fixturesDir }, { ownership: { kind: "conversation" } }), context);
    const settled = await harness.waitForTask(taskId, context);
    const outcome = settled.state.outcome;
    assert.equal(outcome.status, "completed", `任务未完成:${JSON.stringify(outcome)}`);
    assert.equal(outcome.result.stage, "TRIAGE");
    assert.match(outcome.result.prompt_sha, /^[0-9a-f]{16}$/);
    const h = JSON.parse(fs.readFileSync(path.join(roundDir, "03-triage-hypotheses.json"), "utf8"));
    assert.equal(h.hypotheses.length, 2, "收编工件(零复制 triageConsume)落盘");
    // MF3 钉住:transcript 工件行型位等价(旧 faux.mjs:87-94——input 行无 model 字段/
    // 零 registry_seed/assistant message 行;门与 DEEP 宿主回填的读面)
    const tl = fs.readFileSync(path.join(roundDir, "03-triage-transcript.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
    assert.deepEqual(tl.map((x) => x.type), ["input", "message"], "TRIAGE transcript 行型:input+message(单发步零 seed 行)");
    assert.equal(tl[0].model, undefined, "faux 面 input 行不带 model 字段(旧行型逐字节不变)");
    assert.equal(tl[0].stage, "TRIAGE");
    assert.match(tl[0].system_sha, /^[0-9a-f]{16}$/);
    assert.equal(tl[0].meta, null, "TRIAGE 无判例注入面 meta=null(旧 input.meta ?? null 同形)");
    assert.equal(tl[1].role, "assistant");
    assert.equal(tl[1].stopReason, "stop");
    const gatesLog = JSON.parse(fs.readFileSync(path.join(roundDir, "gates.json"), "utf8"));
    const g = (Array.isArray(gatesLog) ? gatesLog : gatesLog.records ?? []).find((r) => r.gate === "G_TRIAGE" || r.name === "G_TRIAGE");
    assert.ok(g, "gates.json 落 G_TRIAGE 记录");
  } finally {
    await harness.close(context);
    await storage.close(context);
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    if (prevDb === undefined) delete process.env.OPS_V2_DB;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

// ── ④ 健康轮结构面:相位闭集 + 轮始旋钮判例 ──────────────────────────────────
test("健康轮相位闭集=旧 runnableOf(PROBE…RETRO)+CLOSE+WAIT_MODEL+FAILED;stage 闭集;requestId 形状", () => {
  const oldRunnable = HEALTH_PIPELINE.filter((d) => d.kind === "script" || d.kind === "model").map((d) => d.name);
  assert.deepEqual(RUNNABLE, oldRunnable, "v2 相位序=旧 runnableOf 单源推导");
  assert.equal(RUNNABLE[RUNNABLE.length - 1], "RETRO");
  const phases = Object.keys(OPS_HEALTH_ROUND.definition.phases).sort();
  assert.deepEqual(phases, [...oldRunnable, "CLOSE", "WAIT_MODEL", "FAILED"].sort(), "相位闭集=十态+join+书挡");
  assert.deepEqual(MODEL_STAGES.sort(), ["DEEP", "SYNTH", "TRIAGE"]);
  assert.equal(modelRequestId("r1", "TRIAGE"), "round-r1-TRIAGE");
  assert.equal(modelRequestId("r1", "DEEP", "hyp 2"), "round-r1-DEEP-hyp-2", "hid 经 hidSlug(hyp 2→hyp-2)");
});

test("轮始旋钮非法=usage 错不带病跑轮(旧 mkCtx 同判例;OPS_PIPELINE_BUDGET_CNY 面)", () => {
  const prev = process.env.OPS_PIPELINE_BUDGET_CNY;
  process.env.OPS_PIPELINE_BUDGET_CNY = "not-a-number";
  try {
    assert.throws(() => OPS_HEALTH_ROUND.definition.initial({ roundId: "x-health" }), (e) => e.usage === true);
  } finally {
    if (prev === undefined) delete process.env.OPS_PIPELINE_BUDGET_CNY; else process.env.OPS_PIPELINE_BUDGET_CNY = prev;
  }
});
