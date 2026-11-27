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
import { BREAKER_CHANNELS, mkBreaker, readBreakerKnobs } from "../../pipeline-core/tools/breaker.mjs"; // 旧真源(对拍基准)
import { OPS_PROBE_TOOLS, bindProbeHost, unbindProbeHost } from "../tools/probes.mjs";
import { OPS_MODEL_ROUND, modelRequestId, MODEL_STAGES } from "../tasks/model-round.mjs";
import { OPS_HEALTH_ROUND, RUNNABLE, rebuildRoundCtx } from "../tasks/health-round.mjs";
import { buildRegistry } from "../registry.mjs";
import { HEALTH_PIPELINE } from "../../pipeline-core/pipeline.mjs";

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
  const fixturesDir = path.resolve(import.meta.dirname, "..", "..", "pipeline-core", "fixtures", "pipeline");
  const canned = JSON.parse(fs.readFileSync(path.join(fixturesDir, "triage.json"), "utf8"));
  const systemPrompt = fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "pipeline-core", "prompts", "health", "triage.md"), "utf8");

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
    // MF3 钉住:transcript 工件行型字节级一致(旧 faux.mjs:87-94——input 行无 model 字段/
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

// P1-5:admission 读数入链(submitter 链面——input.monthlyAdmission → initial →
// ck.state.monthly_admission → rebuildRoundCtx 透传 → CLOSE 09-budget.json readings.monthly)
test("P1-5:initial 接 monthlyAdmission 读数入 state.monthly_admission;缺席=不设(replay 面旧同形)", () => {
  const adm = { ok: true, projected: 0.06, month: "2026-10", spend: 0.01, counted: 1, skipped: 0, est: 0.05, cap: 30 }; // admitOrRefuse 返回 admission 读数对象(budget.mjs monthlyAdmission 同形)
  const ck = OPS_HEALTH_ROUND.definition.initial({ roundId: "r-p15-health", monthlyAdmission: adm });
  assert.deepEqual(ck.state.monthly_admission, adm, "读数对象原样入 checkpoint(旧 ctx.state.monthly_admission 同位)");
  assert.equal(OPS_HEALTH_ROUND.definition.initial({ roundId: "r2-health" }).state.monthly_admission, undefined, "缺席=不设键(09-budget readings.monthly=null,旧 replay 面同形)");
  // 重建面透传断言(rebuildRoundCtx:monthly_admission 有值才镜像)。rebuildRoundCtx 会 mkdir 轮目录
  // (tasks/health-round.mjs),DOCS_ROOT 未设时兜底到仓根 docs/——本文件 E2E 例的 finally 把
  // DOCS_ROOT 还原成进程初值(常规跑法=删净),这里跟着不设就会在仓里建出空目录
  // docs/ops/rounds/r-p15-health(#425),故指到本例自己的临时目录。
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-p15-admission-"));
  const prevDocs = process.env.DOCS_ROOT;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  try {
    const rebuilt = rebuildRoundCtx({ roundId: "r-p15-health", modelFace: "faux" }, ck);
    assert.deepEqual(rebuilt.state.monthly_admission, adm, "rebuildRoundCtx 透传(旧 state.json 全字段镜像面)");
    // 钉住上面那条 DOCS_ROOT 指向:轮目录必须落在本例的临时目录下,不许落回仓根 docs/(拆掉上面那行
    // 赋值即红;#425 评审前补钉——没有它,删掉修复套件照样绿)
    assert.ok(fs.existsSync(path.join(tmp, "docs", "ops", "rounds", "r-p15-health")), "轮目录落在本例临时目录的 DOCS_ROOT 下,不落仓根 docs/");
  } finally {
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

// ── #490(第四轮评审卡 25)模型失败面限流分类:账户级/单请求两级处置 ─────────────
// 共同面:faux fixture 注入 error 回合(errorMessage=pi-ai formatProviderError 形
// "<status>: <body>");Harness settings 关掉会话层自动重试保确定性(生产 retry 默认开,
// 429 文本会被 pi-durable 会话层先自动重试耗尽才到本分类——票面查证项,分类看到的是
// 耗尽后的最终错误,与生产链同形)。survivors 前置工件=上方 ③ 同罐装配对(G_TRIAGE
// 穷尽判据;B/C 成功面要过门)。
const ACC_ERR = '429: {"code":"1302","message":"您的账户已达到速率限制，请您控制请求频率"}';
const REQ_ERR = "429: too many requests, slow down";
const SURVIVORS = { survivors: [
  { signal_id: "https://cinsscore.com/list/ci-badguys.txt", source: "cinsscore", bucket: "frozen", age_days: 220, url: "https://cinsscore.com/list/ci-badguys.txt" },
  { signal_id: "https://www.binarydefense.com/banlist.txt", source: "binarydefense", bucket: "frozen", age_days: 210, url: "https://www.binarydefense.com/banlist.txt" },
], known_noise_digest: [] };

function fixtureDirWith(tmp, turns) { // 写罐装 TRIAGE fixture;返回 fixturesDir
  const fixturesDir = path.join(tmp, "fixtures");
  fs.mkdirSync(fixturesDir, { recursive: true });
  const canned = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "pipeline-core", "fixtures", "pipeline", "triage.json"), "utf8"));
  fs.writeFileSync(path.join(fixturesDir, "triage.json"), JSON.stringify({ ...canned, turns }));
  return fixturesDir;
}

function cannedTurnsWith(extraTurn) { // 罐装回合(可头部插一个 error 回合)——直建模型任务的 faux
  // 队列由测试显式 setResponses(health-round 才在 spawn 里读 fixture;与轮面同队列形状)
  const canned = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "pipeline-core", "fixtures", "pipeline", "triage.json"), "utf8"));
  return extraTurn ? [extraTurn, ...canned.turns] : canned.turns;
}

async function openModelRoundHarness(storage, context) { // 关会话层自动重试(测试面);关 compaction 同 HARNESS_SETTINGS
  const models = createModels();
  const faux = fauxProvider({ models: [{ id: "glm-5.3-flash" }] });
  models.setProvider(faux.provider);
  const harness = await Harness.open(storage, {
    models, registry: buildRegistry(),
    settings: { retry: { enabled: false }, compaction: { enabled: false } },
  }, context);
  const m = faux.getModel();
  const opsExt = buildRegistry().snapshot().installed().find((e) => e.name === "ops"); // AgentChange.extensions 要 Extension 对象
  return { harness, faux, agentOpts: { agent: { model: { provider: m.provider, modelId: m.id }, extensions: [opsExt], instructions: "t", modelTools: [] } } };
}

// 收集 ops-model-round 任务记录轨迹(status/attempt/lastErrorClass/backoffUntil;观察面 #445 同法)
function trackModelRoundCommits(harness) {
  const seen = [];
  harness.subscribeCommits((publication) => {
    for (const ch of publication.changes)
      if (ch.type === "task" && ch.value?.kind === "ops-model-round")
        seen.push({ status: ch.value.state?.status, attempt: ch.value.state?.checkpoint?.attempt ?? null,
          lastErrorClass: ch.value.state?.checkpoint?.lastErrorClass ?? null,
          backoffUntil: ch.value.state?.checkpoint?.backoffUntil ?? null });
  });
  return seen;
}

test("#490 账户级限流(429/1302):不重试直接终态 failed code=account_rate_limited(等待重试无效)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-acct-"));
  const prevDocs = process.env.DOCS_ROOT;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  const roundDir = path.join(process.env.DOCS_ROOT, "ops", "rounds", "2026-10-28-1300-health");
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify(SURVIVORS, null, 2) + "\n");
  const turns = cannedTurnsWith({ role: "assistant", content: [], stopReason: "error", errorMessage: ACC_ERR });
  const fixturesDir = fixtureDirWith(tmp, turns);
  const storage = await openNodeSqliteStorage(path.join(tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const { harness, faux, agentOpts } = await openModelRoundHarness(storage, context);
    try {
      faux.setResponses(turns); // 直建任务:faux 队列由测试显式装(health-round spawn 才读 fixture)
      const seen = trackModelRoundCommits(harness);
      harness.resume();
      const root = await harness.root(context, agentOpts);
      const taskId = await root.commit((tx) => tx.createTask(OPS_MODEL_ROUND, { roundId: "2026-10-28-1300-health", stage: "TRIAGE", modelFace: "faux", fixturesDir }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `账户级应终态 failed:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "account_rate_limited", "错误码=闭集新词(诚实码)");
      assert.match(outcome.error.message, /账户级限流/);
      assert.match(outcome.error.message, /1302/, "报文正文随消息出海(证据不灭失)");
      assert.ok(seen.every((s) => (s.attempt ?? 0) === 0), `无任何重试提交(attempt 恒 0):${JSON.stringify(seen)}`);
      assert.ok(seen.every((s) => s.status !== "sleeping"), "账户级不走 sleeping(等待重试无效)");
      assert.ok(!fs.existsSync(path.join(roundDir, "03-triage-transcript.jsonl")), "失败回合零 transcript 留痕(submission 层败在 writeTranscript 前)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("#490 单请求限流(429 非 1302):先 sleeping 退避(OPS_MODEL_RETRY_BACKOFF_S)再重试一次成功", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-backoff-"));
  const prevDocs = process.env.DOCS_ROOT, prevBackoff = process.env.OPS_MODEL_RETRY_BACKOFF_S;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  process.env.OPS_MODEL_RETRY_BACKOFF_S = "0.2"; // 200ms 退避(测试面小值;生产缺省 30)
  const roundDir = path.join(process.env.DOCS_ROOT, "ops", "rounds", "2026-10-28-1301-health");
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify(SURVIVORS, null, 2) + "\n");
  const turns = cannedTurnsWith({ role: "assistant", content: [], stopReason: "error", errorMessage: REQ_ERR });
  const fixturesDir = fixtureDirWith(tmp, turns);
  const storage = await openNodeSqliteStorage(path.join(tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const { harness, faux, agentOpts } = await openModelRoundHarness(storage, context);
    try {
      faux.setResponses(turns); // 直建任务:faux 队列由测试显式装(health-round spawn 才读 fixture)
      const seen = trackModelRoundCommits(harness);
      harness.resume();
      const root = await harness.root(context, agentOpts);
      const taskId = await root.commit((tx) => tx.createTask(OPS_MODEL_ROUND, { roundId: "2026-10-28-1301-health", stage: "TRIAGE", modelFace: "faux", fixturesDir }, { ownership: { kind: "conversation" } }), context);
      const t0 = Date.now();
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `退避后重试应成功:${JSON.stringify(outcome)}`);
      assert.equal(outcome.result.modelCalls, 2, "P0-③ 失败回合同计:modelCalls=2(1 败+1 成)");
      const sleep = seen.find((s) => s.status === "sleeping");
      assert.ok(sleep, `应有 sleeping 提交:${JSON.stringify(seen)}`);
      assert.equal(sleep.attempt, 1, "sleeping 提交同步 attempt+1(P0-③ attempt 即调用)");
      assert.equal(sleep.lastErrorClass, "rate_limited", "lastErrorClass 入 checkpoint(测试/排查读)");
      assert.ok(sleep.backoffUntil > 0, "backoffUntil 入 checkpoint(可取消等待的时间戳面)");
      assert.ok(Date.now() - t0 >= 150, `真等了退避窗(200ms 档,松下限 150ms):${Date.now() - t0}ms`);
      assert.equal(seen.filter((s) => s.status === "sleeping").length, 1, "恰一次退避(retry 预算仍 1)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    if (prevBackoff === undefined) delete process.env.OPS_MODEL_RETRY_BACKOFF_S; else process.env.OPS_MODEL_RETRY_BACKOFF_S = prevBackoff;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("#490 其他失败照旧立即重试:无 errorMessage 分类缺席,不 sleeping 不退避(行为面与改动前同)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-plainretry-"));
  const prevDocs = process.env.DOCS_ROOT;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  const roundDir = path.join(process.env.DOCS_ROOT, "ops", "rounds", "2026-10-28-1302-health");
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify(SURVIVORS, null, 2) + "\n");
  const turns = cannedTurnsWith({ role: "assistant", content: [], stopReason: "error" }); // 无 errorMessage(旧 P0-③ 同形)
  const fixturesDir = fixtureDirWith(tmp, turns);
  const storage = await openNodeSqliteStorage(path.join(tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const { harness, faux, agentOpts } = await openModelRoundHarness(storage, context);
    try {
      faux.setResponses(turns); // 直建任务:faux 队列由测试显式装(health-round spawn 才读 fixture)
      const seen = trackModelRoundCommits(harness);
      harness.resume();
      const root = await harness.root(context, agentOpts);
      const taskId = await root.commit((tx) => tx.createTask(OPS_MODEL_ROUND, { roundId: "2026-10-28-1302-health", stage: "TRIAGE", modelFace: "faux", fixturesDir }, { ownership: { kind: "conversation" } }), context);
      const t0 = Date.now();
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `普通失败应照旧重试成功:${JSON.stringify(outcome)}`);
      assert.equal(outcome.result.modelCalls, 2);
      assert.ok(Date.now() - t0 < 150, `零退避立即重试(${Date.now() - t0}ms;改动前行为)`);
      assert.ok(seen.every((s) => s.status !== "sleeping"), "非限流失败不走 sleeping");
      assert.ok(seen.every((s) => s.lastErrorClass === null), "分类缺席=lastErrorClass 恒 null");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("#490 单请求限流重试尽:终态 failed code=model_face,消息注明限流重试尽(重试预算仍 1)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-rlexhaust-"));
  const prevDocs = process.env.DOCS_ROOT, prevBackoff = process.env.OPS_MODEL_RETRY_BACKOFF_S;
  process.env.DOCS_ROOT = path.join(tmp, "docs");
  process.env.OPS_MODEL_RETRY_BACKOFF_S = "0"; // 关退避保快(退避本身由上一测钉)
  const roundDir = path.join(process.env.DOCS_ROOT, "ops", "rounds", "2026-10-28-1303-health");
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify(SURVIVORS, null, 2) + "\n");
  const turns = [
    { role: "assistant", content: [], stopReason: "error", errorMessage: REQ_ERR },
    { role: "assistant", content: [], stopReason: "error", errorMessage: REQ_ERR },
  ]; // 两发全限流:首败→退避重试→再败→终态(def.fail.retry=1;门不达,无收编面)
  const fixturesDir = fixtureDirWith(tmp, turns);
  const storage = await openNodeSqliteStorage(path.join(tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const { harness, faux, agentOpts } = await openModelRoundHarness(storage, context);
    try {
      faux.setResponses(turns); // 直建任务:faux 队列由测试显式装(health-round spawn 才读 fixture)
      const seen = trackModelRoundCommits(harness);
      harness.resume();
      const root = await harness.root(context, agentOpts);
      const taskId = await root.commit((tx) => tx.createTask(OPS_MODEL_ROUND, { roundId: "2026-10-28-1303-health", stage: "TRIAGE", modelFace: "faux", fixturesDir }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed");
      assert.equal(outcome.error.code, "model_face", "单请求限流非账户级=走原 model_face 终态");
      assert.match(outcome.error.message, /单请求限流重试尽/);
      assert.equal(seen.filter((s) => s.status === "sleeping").length, 1, "首败恰一次退避重试");
      assert.ok(seen.every((s) => (s.attempt ?? 0) <= 1), "attempt 上限=def.fail.retry(1),不无限重试");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prevDocs === undefined) delete process.env.DOCS_ROOT; else process.env.DOCS_ROOT = prevDocs;
    if (prevBackoff === undefined) delete process.env.OPS_MODEL_RETRY_BACKOFF_S; else process.env.OPS_MODEL_RETRY_BACKOFF_S = prevBackoff;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
