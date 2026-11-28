// health-e2e.test.mjs — 健康轮链路 E2E(票 #228 修复⑥:「结构绿≠执行绿」的直接补丁)。
// 钉住本次三个 P0 的暴露面:MF1(path import——轮跑过 PROBE 后任意相位即触)/MF2(
// WAIT_MODEL join 契约——TRIAGE spawn 后 outcomes 只能在全 settle 后调)/MF3(transcript
// 工件面——DEEP 宿主回填与 G_SYNTH 闭合门都吃它)。链路=TRIAGE→WAIT_MODEL(settle)→
// DISPATCH→DEEP(带 evidence)→ITEMIZE→SYNTH→ANCHOR_SWEEP(降级旁路)→RETRO→CLOSE,
// fromPhase 缝起步 TRIAGE(旧 pipeline.mjs replay --from 同义;G_PROBE 需 ≥30 URL 真探测,
// 零网络红线),01/02 前置工件=旧 selftest-pipeline ⑫ p170 面同法种子。
// 罐装世界=旧 selftest R1 同契约:repo fixtures/pipeline(triage/deep×2/synth)+ 判例
// 2026-06-01-golden-aggregator.md(与 synth.json 引用配对)+ R1 抑制规则(dshield)。
// 环境面全 tmp:DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE;OPS_EVAL_PY=永败 stub(锚巡检走
// anchorSweepCli 失败信封→降级旁路,runFindingExits(sweepD=null)=skip 留痕零外发);
// OPS_SWEEP_DRY_RUN=1 双保险。faux provider 逐子任务分派(spawn 内注册),零网络零密钥。
// 第二测:①收口复查钉负例(OPS_PIPELINE_MAX_MODEL_CALLS=2 → 3 调用后 WAIT_MODEL 收口
// 终态 budget_exceeded——并行子任务 pre 只见基数,收口补全网的执法面)。
import "./.e2e-env.mjs"; // 首位:env 先行件(EVAL_PY=shared.mjs 加载期常量,晚设无效;详见该文件头注)
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb, spawn } from "node:child_process";
import { Harness } from "@earendil-works/pi-durable";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { createModels } from "@earendil-works/pi-ai";
import { OPS_HEALTH_ROUND, writeFaultedMirror } from "../tasks/health-round.mjs";
import { openHarness } from "../entry.mjs";
import { HealthRoundsDoc } from "../run-health.mjs";
import { fauxBundle } from "../run-discover.mjs"; // #445:openHarness opts.models 缝要 {models,resolve} 束(faux 罐装面,discover 测试同源)
import { buildRegistry } from "../registry.mjs";

const AGENT = path.resolve(import.meta.dirname, "..", "..", "pipeline-core"); // #412 前 ops/agent(旧真源)
const FIXTURES = path.join(AGENT, "fixtures", "pipeline");
const PREC = "2026-06-01-golden-aggregator.md"; // 与 fixtures/pipeline/synth.json 引用配对(旧 selftest 契约)
const CINS = "https://cinsscore.com/list/ci-badguys.txt";
const BDEF = "https://www.binarydefense.com/banlist.txt";
const CINS_SLUG = "https-cinsscore.com-list-ci-badguys.txt";
const BDEF_SLUG = "https-www.binarydefense.com-banlist.txt";

// 判例 fixture 文件(旧 selftest-pipeline.mjs PREC 逐字副本——synth.json 引用+锚域词表
// 检索词双命中面;动它须同步旧 selftest)。
const PREC_BODY = `---\nid: 2026-06-01-golden-aggregator\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`;

// 世界装配:tmp DOCS 树 + 前置工件(01/02)+ 判例/规则库 + env 面。返回恢复函数。
function seedWorld({ roundId, capCalls } = {}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-health-e2e-"));
  const docs = path.join(tmp, "docs");
  const ops = path.join(docs, "ops");
  const roundDir = path.join(ops, "rounds", roundId);
  fs.mkdirSync(path.join(ops, "precedents"), { recursive: true });
  fs.mkdirSync(path.join(ops, "rules"), { recursive: true });
  fs.mkdirSync(path.join(ops, "items"), { recursive: true });
  fs.mkdirSync(roundDir, { recursive: true });
  fs.writeFileSync(path.join(ops, "precedents", PREC), PREC_BODY);
  fs.writeFileSync(path.join(ops, "precedents", "_schema.md"), "schema 说明(注入排除面)。\n");
  fs.writeFileSync(path.join(ops, "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
    { id: "R1", adopted: "2026-10-24", adopted_via: "item-fixture", match: { bucket: "frozen", url_shape: "*dshield.org*" },
      action: "suppress", note: "fixture:dshield 冻结读数为已知探测伪迹", review_at: "2027-01-24" } ] }, null, 2) + "\n");
  // 01/02 前置工件(fromPhase=TRIAGE;形状=旧 PROBE/VERIFY 产物面):2 冻结幸存+1 抑制
  fs.writeFileSync(path.join(roundDir, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: roundId, urls_n: 3, attempted_n: 3,
    buckets: { fresh: 0, frozen: 3, unreachable: 0, token_required: 0, no_lm: 0 },
    flags: [
      { signal_id: CINS, url: CINS, bucket: "frozen", source: "cinsscore", age_days: 220, last_modified: "canned-220d" },
      { signal_id: BDEF, url: BDEF, bucket: "frozen", source: "binarydefense", age_days: 210, last_modified: "canned-210d" },
      { signal_id: "https://lists.dshield.org/block.txt", url: "https://lists.dshield.org/block.txt", bucket: "frozen", source: "dshield", age_days: 200, last_modified: "canned-200d" },
    ], matrix: { ok: true, exit_code: 0, violation_n: 0 } }, null, 2) + "\n");
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify({ survivors: [
    { signal_id: CINS, source: "cinsscore", bucket: "frozen", age_days: 220, url: CINS },
    { signal_id: BDEF, source: "binarydefense", bucket: "frozen", age_days: 210, url: BDEF },
  ], known_noise_digest: [{ id: "R1", action: "suppress", match: { bucket: "frozen", url_shape: "*dshield.org*" }, note: "fixture", review_at: "2027-01-24" }], rules_version: 1, in_flight_n: 0 }, null, 2) + "\n");
  fs.writeFileSync(path.join(roundDir, "02-verify-suppressed.json"), JSON.stringify({ suppressed: [
    { signal_id: "https://lists.dshield.org/block.txt", source: "dshield", bucket: "frozen", age_days: 200, url: "https://lists.dshield.org/block.txt", rule_id: "R1" },
  ], rules_version: 1 }, null, 2) + "\n");
  // 永败 py stub 由 ./.e2e-env.mjs 首位 import 提供(OPS_EVAL_PY 是 shared.mjs 加载期常量,
  // 测试体内设已晚);这里只设调用期读取面的 env
  const prev = { ...process.env };
  process.env.DOCS_ROOT = docs;
  process.env.PRECEDENTS_DIR = path.join(ops, "precedents");
  process.env.LEDGER_FILE = path.join(ops, "ledger.md");
  process.env.OPS_SWEEP_DRY_RUN = "1";
  process.env.IP_RADAR_EVAL_DIR = path.join(tmp, "eval-empty"); // #352:变异自检提醒面钉确定性(报告根指空 tmp→未见上次运行,不读真树)
  if (capCalls != null) process.env.OPS_PIPELINE_MAX_MODEL_CALLS = String(capCalls);
  return { tmp, docs, ops, roundDir, restore: () => {
    for (const k of ["DOCS_ROOT", "PRECEDENTS_DIR", "LEDGER_FILE", "OPS_SWEEP_DRY_RUN", "OPS_PIPELINE_MAX_MODEL_CALLS", "IP_RADAR_EVAL_DIR"])
      if (k in prev) process.env[k] = prev[k]; else delete process.env[k];
  } };
}

const jsonOf = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const jsonlOf = (p) => fs.readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));

// roundId 形状律:#403 起 CLOSE 写轮报告件(packages/<date>-health-<HHMM>.md,名字源
// reportNameOf 形状校验),测试轮 id 须同生产律 YYYY-MM-DD-HHMM-health(旧 -e2e- 字样
// 不合形状,随 #403 收正)。豁免:下方两处失败路径测试轮 id(2026-10-28-e2e-cap-health /
// 2026-11-15-e2e-mf-health)不走 CLOSE、不产报告件,不合形状属预期——若有人把终态改
// 成完成轮(会过 CLOSE),reportNameOf 掷 bad_round 即红,是本形状律的预期护栏。
test("健康轮链路 E2E:TRIAGE→WAIT_MODEL(join)→DEEP(evidence)→SYNTH→…→CLOSE 全绿(faux 零网络)", async () => {
  const roundId = "2026-10-28-0100-health";
  const w = seedWorld({ roundId });
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  const adm = { ok: true, projected: 0.06, month: "2026-10", spend: 0.01, counted: 1, skipped: 0, est: 0.05, cap: 30 }; // P1-5:admission 读数(submitter 链)
  try {
    // 空 Models(零真 provider 装载——faux 分派在 spawn 内注册;生产真面走 loadModels)
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES, monthlyAdmission: adm,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `健康轮未完成:${JSON.stringify(outcome)}`);
      // —— 信封(envelope=旧 composeEnvelope 逐字副本面)——
      const env = outcome.result.envelope;
      assert.equal(env.ok, true);
      assert.equal(env.round, "health");
      assert.equal(env.pipeline.round_id, roundId);
      const stageNames = env.pipeline.stages.map((s) => s.name);
      assert.deepEqual(stageNames, ["TRIAGE", "DISPATCH", "DEEP", "ITEMIZE", "SYNTH", "ANCHOR_SWEEP", "RETRO", "CLOSE"], "TRIAGE 起步→CLOSE 全相位留痕");
      assert.ok(env.pipeline.stages.every((s) => ["done", "skipped", "degraded"].includes(s.status)), `成功轮 stage 状态闭集:${JSON.stringify(env.pipeline.stages)}`);
      assert.equal(env.pipeline.stages.find((s) => s.name === "ANCHOR_SWEEP").status, "degraded", "锚巡检面死=降级旁路(零网络世界)");
      assert.ok(env.usage.totalTokens > 0, `轮 usage 数字回传(faux 估算面):${JSON.stringify(env.usage)}`);
      // P0-⑤ 求和律(旧 pipeline_ok 断言面):各步 usage 增量之和 == 信封 usage(脚本步 null 不计)
      const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
      for (const s of env.pipeline.stages) if (s.usage) for (const k of Object.keys(sum)) sum[k] += s.usage[k];
      assert.deepEqual(sum, env.usage, "各步求和==信封 usage(P0-⑤ 语义回旧律)");
      // —— MF3 transcript 面:TRIAGE 行型(faux 面无 model 字段/零 seed 行)——
      const tt = jsonlOf(path.join(w.roundDir, "03-triage-transcript.jsonl"));
      assert.deepEqual(tt.map((x) => x.type), ["input", "message"]);
      assert.equal(tt[0].model, undefined, "faux 面 input 行不带 model 字段(旧行型逐字节不变)");
      // —— DEEP:逐假设工件+transcript registry_seed 行(MF3)+宿主回填 evidence ——
      const cinsV = jsonOf(path.join(w.roundDir, `05-deep-${CINS_SLUG}.json`));
      assert.equal(cinsV.verdict, "confirmed");
      assert.deepEqual(cinsV.evidence, [{ call_id: "c-cins", field: "age_days", value: 220 }], "evidence 值=transcript registry_seed 宿主回填(A 一律;MF3 断链修复的直接暴露面)");
      const cinsT = jsonlOf(path.join(w.roundDir, `05-deep-${CINS_SLUG}-transcript.jsonl`));
      assert.deepEqual(cinsT.map((x) => x.type), ["input", "registry_seed", "message"], "DEEP transcript:input+seed(≤3/假设)+message");
      assert.equal(cinsT[1].call_id, "c-cins");
      assert.equal(cinsT[1].tool, "reprobe_get");
      assert.ok(fs.existsSync(path.join(w.roundDir, `05-deep-${BDEF_SLUG}-transcript.jsonl`)), "第二假设 transcript 落盘(并行子任务分派不串台)");
      const verdicts = jsonOf(path.join(w.roundDir, "05-deep-verdicts.json"));
      assert.equal(verdicts.verdicts.length, 2);
      assert.deepEqual(verdicts.verdicts.map((v) => v.verdict).sort(), ["confirmed", "refuted"], "两罐装判例:cinsscore confirmed/binarydefense refuted");
      // —— SYNTH:报告+transcript input 行 meta.injected(G_SYNTH closure 门的面)——
      const report = fs.readFileSync(path.join(w.roundDir, "07-synth-report.md"), "utf8");
      assert.ok(report.includes("## 注入判例") && report.includes(PREC), "canned 报告引 fixture 判例");
      const st = jsonlOf(path.join(w.roundDir, "07-synth-transcript.jsonl"));
      const stIn = st.find((l) => l.type === "input");
      assert.ok(stIn.meta?.injected?.includes(PREC), "input 行 meta.injected 含注入判例(旧 synthInput meta 面;G_SYNTH allowed 集同源)");
      // —— P1-5:09-budget.json monthly 维度对齐旧轮 ——
      const budget = jsonOf(path.join(w.roundDir, "09-budget.json"));
      assert.deepEqual(budget.readings.monthly, adm, "readings.monthly=admission 读数对象(旧轮=准入投影;断流修复)");
      assert.equal(budget.readings.model_calls, 4, "轮累计模型调用=TRIAGE+DEEP×2+SYNTH(P1-4 轮级口径)");
      assert.ok(budget.readings.usage.totalTokens > 0);
      // —— 门留痕:执行序全门 PASS(ANCHOR_SWEEP=降级旁路留痕)——
      const gates = jsonOf(path.join(w.roundDir, "gates.json")).records;
      const gateOf = (n) => gates.filter((r) => r.name === n);
      for (const g of ["G_TRIAGE", "G_DISPATCH", "G_DEEP", "G_ITEMIZE", "G_SYNTH", "G_RETRO", "G_CLOSE"])
        assert.ok(gateOf(g).some((r) => r.pass === true), `门 ${g} 应有 PASS 记录`);
      assert.ok(gateOf("G_ANCHOR_SWEEP").every((r) => r.reason.includes("门旁路")), "G_ANCHOR_SWEEP=降级旁路(求值面死不持门)");
      assert.ok(fs.existsSync(env.pkg), "pkg(07-synth-report.md)存在");
      assert.ok(fs.existsSync(path.join(w.ops, "retro", `${roundId}.json`)), "RETRO 工件落盘");
      // #352 票尾:RETRO 面变异自检月度到期提醒行(报告根=空 tmp → 未见上次运行,首跑即到期)
      const retro = jsonOf(path.join(w.ops, "retro", `${roundId}.json`));
      assert.equal(retro.mutation_check_due.due, true);
      assert.equal(retro.mutation_check_due.last_run, null);
      assert.match(retro.mutation_check_due.note, /未见上次运行/);
      // #403:轮报告件入 packages/(断供修复;命名=<date>-health-<HHMM>.md);#420 起结论
      // 先行+概览表——轮次/引擎折入标题/概览行,旧「轮次:/类型:/引擎:」行断言随之改向
      const repPath = path.join(w.ops, "packages", "2026-10-28-health-0100.md");
      assert.ok(fs.existsSync(repPath), "#403:报告件未落 packages/");
      const rep = fs.readFileSync(repPath, "utf8");
      assert.match(rep, /^# 运营轮报告 2026-10-28-0100-health$/m, "#420:标题含轮次 id");
      assert.match(rep, /^\*\*结论:/m, "#420:结论行置顶");
      assert.match(rep, /## 概览/);
      assert.match(rep, /\| 类型 \| health\(引擎 pipeline-v2/, "#420:概览类型行含引擎");
      assert.match(rep, /\| CLOSE \| done \|/, "相位表含 CLOSE 行");
      assert.match(rep, /## 信封/);
      const fenced = rep.split("```json\n")[1]?.split("\n```")[0];
      assert.equal(JSON.parse(fenced).pipeline.round_id, roundId, "信封 fenced JSON 可解析且 round_id 对上");
      // #408:CLOSE 终态回写——健康轮 v2 此前无 state.json(state 面=checkpoint,RUNBOOK 已知
      // 差异);现在 CLOSE 与报告件同点落终态镜像。终态词沿用 v1 status 流(done+stage 书挡
      // CLOSE;v1 selftest「state.json 终态 done/CLOSE」同断言面),B 票(#407 UI 徽章)读面即此字段。
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "done", "#408:CLOSE 后 state.json 终态 done");
      assert.equal(mirror.stage, "CLOSE", "#408:终态 stage 书挡 CLOSE(v1 finishClose 同对)");
      assert.equal(mirror.round_id, roundId);
      assert.equal(mirror.pipeline_mode, "pidurable");
      assert.deepEqual(mirror.stages.map((s) => s.name), stageNames, "#408:镜像 stages 全相位含 CLOSE");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// #408 失败面:报告件写败(#403 fail-loud 注入面:packages 被占为文件)→ runClose catch
// 镜像终态 failed/FAILED 书挡(v1 failStage 同对);轮 outcome 同终态 failed。
test("#408 健康轮 CLOSE 失败面终态:报告件写败 → state.json failed/FAILED", async () => {
  const roundId = "2026-10-28-0102-health";
  const w = seedWorld({ roundId });
  fs.writeFileSync(path.join(w.ops, "packages"), "占位文件(writeRoundReport mkdir 即败)");
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `应在 CLOSE 步败(报告件写败):${JSON.stringify(outcome)}`);
      assert.match(outcome.error.message, /CLOSE:.*轮报告件写败/);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed", "#408:close 相位失败出口镜像终态 failed");
      assert.equal(mirror.stage, "FAILED", "#408:失败书挡 FAILED(v1 failStage 同对)");
      const closeRec = mirror.stages.filter((s) => s.name === "CLOSE").at(-1);
      assert.equal(closeRec?.status, "failed", "已入镜像的 CLOSE 记录就地改判 failed(v1 failStage 同语义:轮终态败,记录不留 done)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// P0-③ attempt 即调用(旧律 budget.mjs:34「重试同计」):TRIAGE 首回合 stopReason=error
// (旧 runModelStep 失败面同判据)→ model_face 重试;重试 commit 同步 modelCalls+1,
// 成功面 ck.modelCalls+1 自动含失败回合 → 轮累计 5(TRIAGE 2 + DEEP×2 + SYNTH 1)。
// 修复前:重试不计数 → 4(失败回合丢账)。
test("P0-③ attempt 即调用:TRIAGE model_face 首败重试同计,轮累计=5 非 4", async () => {
  const roundId = "2026-10-28-0101-health";
  const w = seedWorld({ roundId });
  const fxDir = path.join(w.tmp, "fixtures-retry");
  fs.cpSync(FIXTURES, fxDir, { recursive: true }); // DEEP/SYNTH 面仍用原罐装回合
  const triage = jsonOf(path.join(fxDir, "triage.json"));
  fs.writeFileSync(path.join(fxDir, "triage.json"), JSON.stringify({ ...triage, turns: [{ role: "assistant", content: [], stopReason: "error" }, ...triage.turns] }));
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `重试后应全链完成:${JSON.stringify(outcome)}`);
      const budget = jsonOf(path.join(w.roundDir, "09-budget.json"));
      assert.equal(budget.readings.model_calls, 5, "失败 attempt 同计:TRIAGE 2+DEEP×2+SYNTH 1(旧律 budget.mjs:34)");
      // P0-⑤ 求和律在重试轮同样成立(增量口径与重试回合无关)
      const env = outcome.result.envelope;
      const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
      for (const s of env.pipeline.stages) if (s.usage) for (const k of Object.keys(sum)) sum[k] += s.usage[k];
      assert.deepEqual(sum, env.usage);
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
// P1-4 ①收口复查钉负例:调用帽 2 < 实际 3(TRIAGE+DEEP×2 各自 pre 只见基数全放行)→
// WAIT_MODEL 收口按轮累计终态 budget_exceeded(违界即停不降级;SYNTH 不再 spawn)。
test("P1-4 ①收口:并行子任务穿透基数后 WAIT_MODEL 按轮累计终态 budget_exceeded", async () => {
  const roundId = "2026-10-28-e2e-cap-health";
  const w = seedWorld({ roundId, capCalls: 2 });
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `应收口终态:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "budget_exceeded");
      assert.match(outcome.error.message, /预算四界①\(收口\):轮累计模型调用 3 > 2/);
      assert.ok(fs.existsSync(path.join(w.roundDir, `05-deep-${CINS_SLUG}.json`)), "已花工件保留(证据不灭失)");
      assert.equal(fs.existsSync(path.join(w.roundDir, "07-synth-report.md")), false, "SYNTH 未再 spawn(违界即停)");
      // #415:WAIT_MODEL 直落终态出口(②收口预算)同样写镜像——failed/FAILED 书挡;DEEP 未成不造名
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed", "#415:WAIT_MODEL 收口终态=轮失败,镜像同写(修前=无件)");
      assert.equal(mirror.stage, "FAILED", "#415:失败书挡 FAILED(v1 failStage 同对)");
      assert.deepEqual(mirror.stages.map((x) => x.name), ["TRIAGE", "DISPATCH"], "已提交相位留痕(TRIAGE 收编→DISPATCH 过门后才 spawn DEEP);DEEP 未成不造记录(宁少算)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── #355 DEEP 终答 JSON 后尾随散文:首个平衡 JSON 对象提取 + tail_note 留痕(4 起影子废轮回归;旧 consume 族已修,本测钉 v2 装配链)──
test("#355 DEEP 尾注容忍:带尾注终答不再 model_face 误杀,判决收编+tail_note 留痕可查", async () => {
  const roundId = "2026-11-15-0100-health";
  const w = seedWorld({ roundId });
  const fxDir = path.join(w.tmp, "fixtures-tail");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  // cinsscore deep 回合尾追散文(#355 真实废轮同形:合法 JSON 判决 + 「补记:」;尾注内嵌花括号不干扰首对象配平)
  const cinsFx = jsonOf(path.join(fxDir, "deep", `${CINS_SLUG}.json`));
  cinsFx.turns[0].content[0].text += "\n\n补记(transcript 留痕,不入 evidence):探针腿返回失败信封 {ok:false,code:too_large}——响应体超上限,端点在正常回传而非超时。";
  fs.writeFileSync(path.join(fxDir, "deep", `${CINS_SLUG}.json`), JSON.stringify(cinsFx));
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `尾注不得废轮(修前此处=failed model_face):${JSON.stringify(outcome)}`);
      const cinsV = jsonOf(path.join(w.roundDir, `05-deep-${CINS_SLUG}.json`));
      assert.equal(cinsV.verdict, "confirmed", "判决面无损(JSON 体内字段照旧收编)");
      assert.deepEqual(cinsV.evidence, [{ call_id: "c-cins", field: "age_days", value: 220 }], "evidence 宿主回填不受尾注影响");
      const cinsT = jsonlOf(path.join(w.roundDir, `05-deep-${CINS_SLUG}-transcript.jsonl`));
      assert.deepEqual(cinsT.slice(0, 3).map((x) => x.type), ["input", "registry_seed", "message"], "原 transcript 行型不动");
      const note = cinsT.at(-1);
      assert.equal(note.type, "tail_note", "尾注以 transcript 事件留痕(证据不灭失)");
      assert.equal(note.stage, "DEEP");
      assert.equal(note.hid, CINS);
      assert.ok(note.note.includes("{ok:false,code:too_large}"), "尾注原文整段在留痕(内嵌花括号原样)");
      // 其余假设(binarydefense 纯 JSON)零 tail_note 行——不发明噪音
      const bdefT = fs.readFileSync(path.join(w.roundDir, `05-deep-${BDEF_SLUG}-transcript.jsonl`), "utf8");
      assert.ok(!bdefT.includes("tail_note"), "纯 JSON 终答零留痕行");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── #355 失败轮台账:model_face 终态轮此前零台账行(RETRO 只记成功轮),补行带 error_code ──
test("#355 失败轮台账:TRIAGE 两 attempt 全坏→model_face 终态,ledger.md 补一行(带 error_code)", async () => {
  const roundId = "2026-11-15-e2e-mf-health";
  const w = seedWorld({ roundId });
  const fxDir = path.join(w.tmp, "fixtures-mf");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  fs.writeFileSync(path.join(fxDir, "triage.json"), JSON.stringify({ turns: [ // retry≤1:两 attempt 全非 JSON → 终态
    { role: "assistant", content: [{ type: "text", text: "不是 JSON(schema 违例负例)" }], stopReason: "stop" },
    { role: "assistant", content: [{ type: "text", text: "仍不是 JSON" }], stopReason: "stop" }] }));
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `应收口终态:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "model_face");
      const led = fs.readFileSync(path.join(w.ops, "ledger.md"), "utf8");
      assert.match(led, /pipeline-failed:2026-11-15-e2e-mf-health/, "失败轮台账行在场(标签:轮 id 可 grep)");
      assert.match(led, /error_code=model_face/, "行带 error_code");
      assert.equal(led.split("\n").filter((l) => l.includes("pipeline-failed:2026-11-15-e2e-mf-health")).length, 1, "恰一行");
      // #415:WAIT_MODEL 直落终态出口(单发子任务全败 model_face)同样写镜像;TRIAGE 未成=stages 空
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed", "#415:WAIT_MODEL 单发步终态=轮失败,镜像同写(修前=无件)");
      assert.equal(mirror.stage, "FAILED");
      assert.deepEqual(mirror.stages, [], "零相位提交:stages 空不造名");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── #415 终态镜像覆盖全部终态出口(#408 只接了 CLOSE;健康轮轮中失败此前无件)──────────
// mid-round 脚本相位失败 → FAILED 书挡 → runFailed:健康轮轮中失败的单一汇聚点。
// 注入面=真实调用链:ops/items 被普通文件占位 → ITEMIZE 步 createOpsItem 写条目即抛
// (定义表「条目写败=可重入终态」)→ failTerm → FAILED → runFailed 终态;零 mock。
test("#415 健康轮 mid-round 失败终态:ITEMIZE 条目写败 → FAILED 书挡 → state.json failed/FAILED,stages=[TRIAGE,DISPATCH,DEEP]", async () => {
  const roundId = "2026-10-28-0103-health";
  const w = seedWorld({ roundId });
  fs.rmSync(path.join(w.ops, "items"), { recursive: true });
  fs.writeFileSync(path.join(w.ops, "items"), "占位文件(createOpsItem 写条目即败)");
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `应在 ITEMIZE 步败:${JSON.stringify(outcome)}`);
      assert.match(outcome.error.message, /^ITEMIZE:/, "失败面须是 ITEMIZE 步本体(条目写败)");
      assert.equal(jsonOf(path.join(w.roundDir, "gates.json")).records.at(-1).name, "G_DEEP", "ITEMIZE 未到门(步抛在门前)");
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed", "#415:mid-round 失败终态=镜像 failed(修前=健康轮轮中无件/修后漏接=无件,轮已终态而无终态件)");
      assert.equal(mirror.stage, "FAILED", "#415:FAILED 书挡(v1 failStage 同对)");
      assert.deepEqual(mirror.stages.map((x) => x.name), ["TRIAGE", "DISPATCH", "DEEP"], "已提交相位全记录留痕;ITEMIZE 未成不造记录(宁少算)");
      assert.equal(mirror.round_id, roundId);
      assert.equal(mirror.pipeline_mode, "pidurable", "health 镜像全形起底(rebuildRoundCtx state 面)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// toPhase 停笔=completed 终态出口(旧 replay --to 同义;shadow 载具面):镜像同样落 done,
// stage 书挡=停笔相位(不走 CLOSE,不造 CLOSE 名)。
test("#415 健康轮 toPhase 停笔终态:completed 出口写镜像 done,stage=停笔相位,stages 止于停笔相位", async () => {
  const roundId = "2026-10-28-0104-health";
  const w = seedWorld({ roundId });
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", toPhase: "DISPATCH", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `停笔终态应 completed:${JSON.stringify(outcome)}`);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "done", "#415:toPhase 停笔=completed 终态出口,镜像 done(修前=无件)");
      assert.equal(mirror.stage, "DISPATCH", "stage 书挡=停笔相位(不造 CLOSE 名)");
      assert.deepEqual(mirror.stages.map((x) => x.name), ["TRIAGE", "DISPATCH"], "stages 全记录形,止于停笔相位");
      assert.equal(fs.existsSync(path.join(w.roundDir, "09-budget.json")), false, "停笔不入 CLOSE 书挡(前提:本测走的是停笔出口而非 CLOSE)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// #430 崩溃恢复重入成功出口的陈旧字段(P3-2):#415 失败出口把失败那刻的镜像落盘后,进程死在
// 终态 commit 之前 → 恢复重跑走到成功出口时,writeTerminalRoundState 以盘上件为底,只传
// status/stage 会把失败那刻的 stages 原样带回(终态件=done+CLOSE 但 stages 缺后段)。
// 修法=两个成功出口(CLOSE/停笔)显式传 stages;updated_at 仍保盘值(终态镜像写不读时钟,
// #408;写新时钟=重入重写字节漂移)。注入=直接落一份带失败 stages 的终态镜像(=崩溃窗口
// 留下的盘上状态),再走成功出口断言 stages 是新的。
const STALE_MIRROR_AT = "2026-10-27T00:00:00.000Z";
function seedStaleMirror(w, roundId) { // 前次失败出口已写的镜像形(#415 失败出口盘上形;终态 outcome 未落)
  fs.writeFileSync(path.join(w.roundDir, "state.json"), JSON.stringify({
    schema: 1, round_id: roundId, type: "health", pipeline_mode: "pidurable",
    status: "failed", stage: "FAILED",
    stages: [{ name: "TRIAGE", status: "done", attempts: 1, dur_ms: 0, usage: null }], // 失败那刻的已提交相位(陈旧)
    updated_at: STALE_MIRROR_AT,
  }, null, 2) + "\n");
}
test("#430 崩溃恢复重入 CLOSE 成功出口:残留的失败 stages 被本次 checkpoint 刷新(done+CLOSE,stages 全相位;updated_at 保盘值)", async () => {
  const roundId = "2026-10-28-0106-health";
  const w = seedWorld({ roundId });
  seedStaleMirror(w, roundId);
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      assert.equal(settled.state.outcome.status, "completed", `成功轮应 completed:${JSON.stringify(settled.state.outcome)}`);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "done");
      assert.equal(mirror.stage, "CLOSE");
      assert.deepEqual(mirror.stages.map((x) => x.name),
        ["TRIAGE", "DISPATCH", "DEEP", "ITEMIZE", "SYNTH", "ANCHOR_SWEEP", "RETRO", "CLOSE"],
        "#430:stages 以本次成功轮 checkpoint 为准(修前=盘上件为底,失败那刻的 [TRIAGE] 残留)");
      assert.equal(mirror.updated_at, STALE_MIRROR_AT, "updated_at 保盘值:终态镜像写不读时钟(#408;读新时钟=重入重写破字节级幂等)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
test("#430 崩溃恢复重入 toPhase 停笔成功出口:残留的失败 stages 被刷新(止于停笔相位)", async () => {
  const roundId = "2026-10-28-0107-health";
  const w = seedWorld({ roundId });
  seedStaleMirror(w, roundId);
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", toPhase: "DISPATCH", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      assert.equal(settled.state.outcome.status, "completed", `停笔终态应 completed:${JSON.stringify(settled.state.outcome)}`);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "done");
      assert.equal(mirror.stage, "DISPATCH");
      assert.deepEqual(mirror.stages.map((x) => x.name), ["TRIAGE", "DISPATCH"],
        "#430:停笔出口 stages 同样以本次 checkpoint 为准(修前=失败那刻的 [TRIAGE] 残留,缺停笔相位)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
test("#415 健康轮相位头预算墙:runScriptPhase 的 stepBoundary 拦截 → 终态 failed,镜像 failed/FAILED(零已提交相位)", async () => {
  const roundId = "2026-10-28-2347-health";
  const w = seedWorld({ roundId });
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  const priorWall = process.env.OPS_PIPELINE_WALL_CLOCK_S;
  try {
    process.env.OPS_PIPELINE_WALL_CLOCK_S = "0"; // 墙钟帽 0=恒超(overWallClock);轮始旋钮在 initial 冻结
    const harness = await Harness.open(storage, { models: createModels(), registry: buildRegistry() }, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      // 从脚本相位起步:相位头预算墙是它的第一个执法点(模型相位起步会先在子任务 pre 拦,走不到本出口)
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "DISPATCH", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `预算墙应终态失败:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "wall_clock_exceeded", "失败面=相位头 stepBoundary 的墙钟码(非模型 pre 的调用帽)");
      assert.match(outcome.error.message, /^DISPATCH:/, "失败面标相位名");
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.round_id, roundId);
      assert.equal(mirror.status, "failed", "#415:相位头预算墙=终态失败,镜像同写(修前=无件)");
      assert.equal(mirror.stage, "FAILED", "stage 书挡=FAILED(v1 failStage 对)");
      assert.deepEqual(mirror.stages.map((x) => x.name), [], "起步相位被拦=零已提交相位(宁少算)");
    } finally { await harness.close(context); }
  } finally {
    if (priorWall === undefined) delete process.env.OPS_PIPELINE_WALL_CLOCK_S; else process.env.OPS_PIPELINE_WALL_CLOCK_S = priorWall;
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#415 健康轮中止终态:在飞(已认领)轮被 abortTask → outcome aborted,镜像 aborted(stage=中止时所处相位,stages=已提交相位)", async () => {
  const roundId = "2026-10-28-2345-health"; // 合形状(子进程走 CLI=形状律先于准入)
  const w = seedWorld({ roundId });
  const db = path.join(w.tmp, "abort.sqlite");
  const context = BACKGROUND_CONTEXT;
  const stateFile = path.join(w.roundDir, "state.json");
  try {
    // 第一段:子进程 CLI 真跑;认领件=TRIAGE 相位头 claimGuard 在真实调用链上落的(写在首个
    // 模型调用之前),一可解析即 SIGKILL(=宿主骤死,任务停在在飞)。health 无 crashHook 缝,
    // 认领件是「轮已起步」的最早磁盘信号。
    const claimFile = path.join(w.roundDir, ".v2-claim.json");
    let child;
    const exited = new Promise((resolve) => {
      // spawn+detached(非 execFile):detached 只在 spawn 面 true 生效(新进程组;实锤
      // execFileCb 忽略之,组杀 ESRCH)——#579 锁代理链 SIGKILL 必须发整组(代理父→
      // flock→引擎子),只杀代理父会留孤儿引擎继续跑完(锁已释放,注入失效)。
      child = spawn(process.execPath, [
        path.resolve(import.meta.dirname, "..", "run-health.mjs"), roundId,
        "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", db,
      ], { env: { ...process.env }, detached: true });
      child.on("close", (code, signal) => resolve({ code, signal }));
    });
    let claimed = false;
    for (let i = 0; i < 5000 && !claimed; i++) { // 10s 帽
      try { claimed = typeof JSON.parse(fs.readFileSync(claimFile, "utf8")).token === "string"; } catch { claimed = false; }
      if (!claimed) await new Promise((r) => setTimeout(r, 2));
    }
    assert.equal(claimed, true, "认领件应在帽内落盘(轮已起步)");
    // #579 锁代理:SIGKILL 必须发整进程组(代理父→flock→引擎子链),只杀代理父会留
    // 孤儿引擎继续跑完(锁已释放,注入失效——首轮实测 state.json 照落)
    process.kill(-child.pid, "SIGKILL");
    assert.deepEqual(await exited, { code: null, signal: "SIGKILL" }, "SIGKILL 期望进程被信号杀(非自杀)");
    assert.equal(fs.existsSync(stateFile), false, "前提:在飞轮无终态镜像件(健康轮无进度镜像;若子进程已跑完=本测注入失效)");
    // 第二段:同库开 harness(不先 resume),对在飞任务下中止标记 → abort 相位(真框架路径,零 mock)
    const { harness } = await openHarness({ dbPath: db, env: { ...process.env } });
    try {
      const taskId = (await harness.snapshot(HealthRoundsDoc, context)).rounds[roundId].taskId;
      const before = await harness.getTask(taskId, context);
      assert.equal(["running", "waiting", "pending", "sleeping"].includes(before.state.status), true, `前提:任务在飞:${before.state.status}`);
      const ck = before.state.checkpoint;
      assert.equal(await harness.abortTask(taskId, context), "marked", "在飞任务应可下中止标记");
      const settled = await harness.waitForTask(taskId, context);
      assert.equal(settled.state.outcome?.status, "aborted", `中止终态应落:${JSON.stringify(settled.state.outcome)}`);
      const mirror = jsonOf(stateFile);
      assert.equal(mirror.round_id, roundId, "镜像落在本轮目录(认领件属主校验过)");
      assert.equal(mirror.status, "aborted", "#415:中止=任务终态,镜像同词 aborted(修前=无件)");
      assert.equal(mirror.stage, ck.phase, "stage=中止时所处相位(中止相位未成,不造书挡名)");
      assert.deepEqual(mirror.stages.map((x) => x.name), ck.state.stages.map((x) => x.name), "stages=中止时 checkpoint 已提交相位(全记录形;中止相位不造记录)");
    } finally { await harness.close(context); }
    // 反面(宁少算):轮目录被别任务认领(认领件 token 异于本任务 checkpoint)→ 中止不写镜像
    // (写了=改判别轮终态)。全新库、开 harness 后不先 resume 就下中止标记=任务零起步,
    // 不经 claimGuard(走的是中止出口自身的属主校验)。
    const roundId2 = "2026-10-28-2346-health";
    const dir2 = path.join(w.ops, "rounds", roundId2);
    fs.mkdirSync(dir2, { recursive: true });
    fs.writeFileSync(path.join(dir2, ".v2-claim.json"), JSON.stringify({ token: "foreign-task-token", taskId: 424242 }, null, 2) + "\n");
    const storage2 = await openNodeSqliteStorage(path.join(w.tmp, "foreign.sqlite"));
    const h2 = await Harness.open(storage2, { models: createModels(), registry: buildRegistry() }, context);
    try {
      const taskId2 = await (await h2.root(context)).commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId: roundId2, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      assert.equal(await h2.abortTask(taskId2, context), "marked", "在飞任务应可下中止标记");
      const settled2 = await h2.waitForTask(taskId2, context);
      assert.equal(settled2.state.outcome?.status, "aborted", `中止终态应落:${JSON.stringify(settled2.state.outcome)}`);
      assert.equal(fs.existsSync(path.join(dir2, "state.json")), false, "异主认领件:中止不写镜像");
    } finally { await h2.close(context); await storage2.close(context); }
  } finally {
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// #445:第四类终态出口——框架判 faulted(相位 handler 裸抛逃出 failTerm/stageDone 的
// checkpoint 面也写镜像 failed+error_code=faulted。接线位 entry.mjs openHarness onReport;
// 属主=认领件(claimGuard 真落盘);相位名单=entry Journal 的最后 checkpoint(终态记录被
// 框架去 checkpoint,withState 换 state)。
test("#445 健康轮框架判 faulted 出口:gates.json 被占为目录 → WAIT_MODEL 收口 G_DEEP 门留痕 EISDIR 裸抛 → 框架 faulted → 镜像 failed+error_code=faulted(stage=已提交 DISPatch)", async () => {
  const roundId = "2026-10-28-2347-health"; // 失败路径轮 id:不走 CLOSE 不产报告件(见上方形状律豁免注)
  const w = seedWorld({ roundId });
  const context = BACKGROUND_CONTEXT;
  const stateFile = path.join(w.roundDir, "state.json");
  try {
    // 注入点=真实调用链一环(#415 同律):DISPATCH skip(01/02 前置工件无 03/04)→ DEEP
    // spawn 子任务罐装完成 → WAIT_MODEL join 收口 def.forEach→finalize→G_DEEP 门评估→
    // appendGate 写 gates.json 落到目录=EISDIR 裸抛——waitModel 无 try/catch 包门留痕=
    // pi-durable 判 fault(onReport task_faulted),修前无 state.json(健康轮无进度镜像)。
    fs.mkdirSync(path.join(w.roundDir, "gates.json"), { recursive: true });
    const { harness } = await openHarness({ dbPath: path.join(w.tmp, "faulted.sqlite"), models: await fauxBundle(FIXTURES) });
    try {
      harness.resume();
      const taskId = await (await harness.root(context)).commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "DISPATCH", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      assert.equal(settled.state.outcome?.status, "faulted", `框架终态词=faulted:${JSON.stringify(settled.state.outcome)}`);
      assert.equal(fs.existsSync(path.join(w.roundDir, ".v2-claim.json")), true, "前提:认领件已在盘(claimGuard 相位头落)");
      // 上报面晚于 waitForTask 结算(waiter 先于上报续,entry.mjs #445 注记):镜像轮询等写落盘
      // (帽 5s;接线被去=永不落盘,轮询耗尽后下方断言转红=变异证据),认领件轮询(#415)同先例
      let mirror = null;
      for (let i = 0; i < 2500 && !mirror; i++) {
        try { mirror = JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch { mirror = null; }
        if (!mirror) await new Promise((r) => setTimeout(r, 2));
      }
      assert.ok(mirror, "#445:框架判 faulted 应写终态镜像(帽内未落=接线丢失)");
      assert.equal(mirror.status, "failed", "#445:框架判 faulted=轮终态,镜像写 failed(修前=无件/无终态)");
      assert.equal(mirror.error_code, "faulted", "错误码=框架自己的词 faulted(不造新码)");
      assert.equal(mirror.round_id, roundId, "镜像落在本轮目录(认领件属主校验过)");
      assert.equal(mirror.stage, "DISPATCH", "stage=已提交最后一个相位(DEEP/WAIT_MODEL faulted 未成不造名)");
      assert.deepEqual(mirror.stages.map((x) => x.name), ["DISPATCH"], "stages=Journal checkpoint 已提交相位(全记录形)");
      assert.equal(mirror.pipeline_mode, "pidurable", "health 镜像首写以 ctx.state 全形起底(rebuildRoundCtx 同底)");
    } finally { await harness.close(context); }
  } finally {
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// #445 属主负例(票面验收第二条直接证据;评审建议改 1):异主认领件 → 别人的轮目录不被写。
// 可达性注(实现负例时实测):链面上异主认领件在相位头就被 claimGuard 拦成 bad_round 域错
// (claimRoundDir :134),faulted 写口经链不可达此形——所以分两面钉:链面钉守卫拦截(任务
// 照常终态 failed),写口面直调 writeFaultedMirror 钉认领件 token 判据(claimOwnedByTask)。
test("#445 健康轮属主负例:异主认领件——链面守卫拦成 bad_round,写口面直调不写别人的轮目录", async () => {
  const roundId = "2026-10-28-2348-health";
  const w = seedWorld({ roundId });
  const context = BACKGROUND_CONTEXT;
  try {
    // 异主认领件(#415 中止负例 :620 同夹具形)+ fault 注入(gates.json 目录占位,#445 主用例同缝)
    fs.writeFileSync(path.join(w.roundDir, ".v2-claim.json"), JSON.stringify({ token: "foreign-task-token", taskId: 424242 }, null, 2) + "\n");
    fs.mkdirSync(path.join(w.roundDir, "gates.json"), { recursive: true });
    const { harness } = await openHarness({ dbPath: path.join(w.tmp, "faulted-foreign.sqlite"), models: await fauxBundle(FIXTURES) });
    try {
      harness.resume();
      const taskId = await (await harness.root(context)).commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "DISPATCH", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      // 链面:相位头 claimGuard 先拦(异主=bad_round 域错),fault 根本不发生=faulted 写口不可达
      assert.equal(settled.state.outcome?.status, "failed", `链面:异主认领件在相位头被 claimGuard 拦截:${JSON.stringify(settled.state.outcome)}`);
      assert.equal(settled.state.outcome?.error?.code, "bad_round", "拦截面=建轮守卫同律 bad_round(不是 faulted)");
      assert.equal(fs.existsSync(path.join(w.roundDir, "state.json")), false, "链面:无 fault 无镜像(本就不写)");
    } finally { await harness.close(context); }
    // 写口面(直调;链面被守卫拦后唯一可达此形的路):认领件 token ≠ ck.claimToken → 不写
    const ck = { phase: "DISPATCH", claimToken: "own-task-token", state: { stages: [] },
      budgetCny: 0.05, budgetKnobs: {}, breakerKnobs: {}, startedAtIso: "2026-11-26T00:00:00.000Z",
      usage: { input: 0, output: 0, totalTokens: 0 }, modelCalls: 0 };
    writeFaultedMirror({ roundId, fixturesDir: FIXTURES, modelFace: "faux" }, ck, "threw");
    assert.equal(fs.existsSync(path.join(w.roundDir, "state.json")), false, "写口面:异主认领件 faulted 上报不写别人的轮目录");
    assert.equal(fs.existsSync(path.join(w.roundDir, ".v2-claim.json")), true, "认领件本体不被动");
  } finally {
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── #490(第四轮评审卡 25)DEEP 并发闸 + 账户级限流分批面 ────────────────────────
// 共同面:Harness settings 关会话层自动重试(生产默认开;429 文本会被 pi-durable 会话层
// 先自动重试耗尽才到模型级分类——测试要直击模型级分类面,必须关掉保确定性)。
const ACC_ERR_429 = '429: {"code":"1302","message":"您的账户已达到速率限制，请您控制请求频率"}';

function healthHarness(storage, context) { // 与既有例同装配,仅 settings 关会话层自动重试
  return Harness.open(storage, {
    models: createModels(), registry: buildRegistry(),
    settings: { retry: { enabled: false }, compaction: { enabled: false } },
  }, context);
}

function trackModelConcurrency(harness) { // 任一提交时点在途(非 terminal)ops-model-round 任务数峰值
  const statuses = new Map();
  let max = 0;
  harness.subscribeCommits((publication) => {
    for (const ch of publication.changes)
      if (ch.type === "task" && ch.value?.kind === "ops-model-round")
        statuses.set(ch.value.id, ch.value.state?.status ?? "terminal");
    let n = 0;
    for (const s of statuses.values()) if (s !== "terminal") n += 1;
    max = Math.max(max, n);
  });
  return { get max() { return max; } };
}

function fixturesWithDeepError(tmp, slug, extraTurn) { // 复制罐装 fixture 树,把 DEEP 单假设回合换成 error
  const fxDir = path.join(tmp, "fixtures-490");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const f = jsonOf(path.join(fxDir, "deep", `${slug}.json`));
  fs.writeFileSync(path.join(fxDir, "deep", `${slug}.json`), JSON.stringify({ ...f, turns: [extraTurn] }));
  return fxDir;
}

function overrideSynth(fxDir, confirmed, refuted, unresolved, created = 2) { // 罐装 SYNTH 回合:深验三计数对齐降级世界
  // (G_SYNTH 深验抽检:报告数字=verdicts∪degraded∪truncated 回算;四计数 created 同对齐
  // 幸存面(3 假设罐装传 created=3)。判例引用只含 PREC,closureCheck 闭合面同源。)
  fs.writeFileSync(path.join(fxDir, "synth.json"), JSON.stringify({ turns: [
    { role: "assistant", content: [{ type: "text", text:
`## 注入判例
- 2026-06-01-golden-aggregator.md

## 异常清单
- (降级世界罐装清单;门检三节齐+四计数+深验三计数+判例闭合)

抑制 1 条(规则 R1×1——明细见工件 02-verify-suppressed.json)。

## 摘要
- 计数: created=${created} reopened=0 deduped=0 suppressed=1
- 深验: confirmed=${confirmed} refuted=${refuted} unresolved=${unresolved};探测桶 frozen=3
- P4 轮:DEEP 真开启(evidence=A 一律选择对,宿主回填;条目经 ops-items 桥落四键面)。` }], stopReason: "stop" },
  ] }));
}

test("#490 并发闸=1:DEEP 子任务串行分批(任一时点至多 1 个在途),轮照常全绿", async () => {
  const roundId = "2026-10-28-0110-health";
  const w = seedWorld({ roundId });
  const prev = process.env.OPS_MODEL_MAX_INFLIGHT;
  process.env.OPS_MODEL_MAX_INFLIGHT = "1";
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      const track = trackModelConcurrency(harness);
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `分批链应照常完成:${JSON.stringify(outcome)}`);
      assert.equal(track.max, 1, `任一时点至多 1 个模型子任务在途(实测峰值 ${track.max})`);
      const env = outcome.result.envelope;
      assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["TRIAGE", "DISPATCH", "DEEP", "ITEMIZE", "SYNTH", "ANCHOR_SWEEP", "RETRO", "CLOSE"], "分批不改相位面");
      const verdicts = jsonOf(path.join(w.roundDir, "05-deep-verdicts.json"));
      assert.deepEqual(verdicts.verdicts.map((v) => v.verdict).sort(), ["confirmed", "refuted"], "两批收编照常");
      assert.equal(jsonOf(path.join(w.roundDir, "09-budget.json")).readings.model_calls, 4, "轮累计不变(TRIAGE+DEEP×2+SYNTH)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prev === undefined) delete process.env.OPS_MODEL_MAX_INFLIGHT; else process.env.OPS_MODEL_MAX_INFLIGHT = prev;
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#490 缺省闸=2:两假设恰一批全放(任一时点 2 个在途),轮照常全绿", async () => {
  const roundId = "2026-10-28-0111-health";
  const w = seedWorld({ roundId });
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      const track = trackModelConcurrency(harness);
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: FIXTURES,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `缺省闸应照常完成:${JSON.stringify(outcome)}`);
      assert.equal(track.max, 2, `缺省闸 2=两子任务同时在途(实测峰值 ${track.max})`);
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// 缺省闸的判别力(评审建议2):2 假设世界峰值 2 与「不分批全放」不可区分(都是 2);
// 3 假设世界才咬得住分批——若去分批,峰值会到 3。另钉批间接续:第三假设的首个提交
// (pending)必须晚于首批两任务的终态。D dispatch 按 severity 排序,首批=cins(high)+bdef(medium)。
test("#490 缺省闸判别力:三假设 DEEP 分批 2+1(峰值 2,批间在首批终态后接续),轮全绿 modelCalls=5", async () => {
  const roundId = "2026-10-28-0114-health";
  const w = seedWorld({ roundId });
  const OPEN = "https://openphish.com/feed.txt";
  const OPEN_SLUG = "https-openphish.com-feed.txt";
  const fxDir = path.join(w.tmp, "fixtures-490-3hyp");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  try {
    // 1) TRIAGE:罐装 2 假设 + 第三假设(openphish low;闭集值 severity=low/cause_class=frozen_feed)
    const triage = jsonOf(path.join(fxDir, "triage.json"));
    const canned = JSON.parse(triage.turns[0].content[0].text);
    const hyp3 = { signal_id: OPEN, cause_class: "frozen_feed", hypothesis: "若 openphish feed 为批处理镜像,则 GET 复测 age_days 仍呈日级阶梯", need_deep: true, probe_hint: "reprobe_get", severity: "low", one_line: "openphish 停更 205 天,复测辨镜像" };
    fs.writeFileSync(path.join(fxDir, "triage.json"), JSON.stringify({ ...triage, turns: [
      { role: "assistant", content: [{ type: "text", text: JSON.stringify({ hypotheses: [...canned.hypotheses, hyp3], digest: "金轨迹回放:3 幸存信号(1 高危冻结 + 1 疑伪迹 + 1 疑镜像),深验子集 3 条。" }) }], stopReason: "stop" },
    ] }));
    // 2) 前置工件对齐:02 幸存集加第三条(G_TRIAGE 穷尽判据);01 探测旗标同步加行(计数面一致)
    const v02 = jsonOf(path.join(w.roundDir, "02-verify-survivors.json"));
    v02.survivors.push({ signal_id: OPEN, source: "openphish", bucket: "frozen", age_days: 205, url: OPEN });
    fs.writeFileSync(path.join(w.roundDir, "02-verify-survivors.json"), JSON.stringify(v02, null, 2) + "\n");
    const p01 = jsonOf(path.join(w.roundDir, "01-probe-summary.json"));
    p01.flags.push({ signal_id: OPEN, url: OPEN, bucket: "frozen", source: "openphish", age_days: 205, last_modified: "canned-205d" });
    fs.writeFileSync(path.join(w.roundDir, "01-probe-summary.json"), JSON.stringify(p01, null, 2) + "\n");
    // 3) 第三假设 DEEP 罐装:refuted(evidence 指向自带 seed;G_DEEP 解析面同罐装对)
    fs.writeFileSync(path.join(fxDir, "deep", `${OPEN_SLUG}.json`), JSON.stringify({
      seed: { id: "c-openphish", tool: "reprobe_get", sc: { ok: true, url: OPEN, method: "GET", status: 200, age_days: 205, last_modified: "canned-205d" } },
      turns: [{ role: "assistant", content: [{ type: "text", text: JSON.stringify({ hypothesis_id: OPEN, verdict: "refuted", evidence: [{ call_id: "c-openphish", field: "age_days" }], one_line: "GET 复测 age_days=205,镜像阶梯确证,非冻结" }) }], stopReason: "stop" }],
    }));
    // 4) SYNTH 罐装对齐:confirmed=1(cins)+ refuted=2(bdef/openphish);四计数 created=3
    overrideSynth(fxDir, 1, 2, 0, 3);
    const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
    const context = BACKGROUND_CONTEXT;
    try {
      const harness = await healthHarness(storage, context);
      try {
        const track = trackModelConcurrency(harness);
        const events = []; // DEEP 子任务提交轨迹(hid+status;批间接续判据)
        harness.subscribeCommits((publication) => {
          for (const ch of publication.changes)
            if (ch.type === "task" && ch.value?.kind === "ops-model-round")
              events.push({ hid: ch.value.input?.hid ?? null, status: ch.value.state?.status });
        });
        harness.resume();
        const root = await harness.root(context);
        const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
          roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
        }, { ownership: { kind: "conversation" } }), context);
        const settled = await harness.waitForTask(taskId, context);
        const outcome = settled.state.outcome;
        assert.equal(outcome.status, "completed", `三假设世界应照常完成:${JSON.stringify(outcome)}`);
        assert.equal(track.max, 2, `缺省闸 2=三假设也只 2 在途(去分批则峰值 3;实测 ${track.max})`);
        const deep = events.filter((e) => e.hid);
        const idx3 = deep.findIndex((e) => e.hid === OPEN);
        assert.ok(idx3 >= 0, `第三假设应有 DEEP 子任务提交(轨迹:${JSON.stringify(deep)})`);
        const firstBatchTerm = deep.filter((e) => e.hid !== OPEN && e.status === "terminal").length;
        assert.ok(firstBatchTerm >= 2, `首批两假设应先后到终态(实 ${firstBatchTerm};轨迹:${JSON.stringify(deep)})`);
        assert.ok(idx3 > deep.map((e, i) => (e.hid !== OPEN && e.status === "terminal") ? i : -1).reduce((a, b) => Math.max(a, b), -1),
          `批间接续:第三假设首个提交(pending)晚于首批全部终态(轨迹:${JSON.stringify(deep)})`);
        assert.equal(jsonOf(path.join(w.roundDir, "09-budget.json")).readings.model_calls, 5, "模型调用总账=5(TRIAGE 1+DEEP 3+SYNTH 1)");
        const dv = jsonOf(path.join(w.roundDir, "05-deep-verdicts.json"));
        assert.equal((dv.verdicts ?? []).length, 3, "三假设三判决全收编(cins 确证+bdef/openphish 反驳)");
        assert.equal(dv.verdicts.filter((v) => v.verdict === "refuted").length, 2, "refuted=2(bdef/openphish)");
      } finally { await harness.close(context); }
    } finally {
      await storage.close(context);
    }
  } finally {
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#490 批内账户级限流:败者记 unresolved(原因写明账户级),同批成功者照常收编,轮降级收口", async () => {
  const roundId = "2026-10-28-0112-health";
  const w = seedWorld({ roundId });
  const fxDir = fixturesWithDeepError(w.tmp, CINS_SLUG, { role: "assistant", content: [], stopReason: "error", errorMessage: ACC_ERR_429 });
  overrideSynth(fxDir, 0, 1, 1); // 深验计数对齐:1 refuted(bdef)+1 unresolved(cins)
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `批内单败应降级收口:${JSON.stringify(outcome)}`);
      const verdicts = jsonOf(path.join(w.roundDir, "05-deep-verdicts.json"));
      assert.equal(verdicts.verdicts.length, 1, "同批成功者照常收编");
      assert.equal(verdicts.verdicts[0].hid, BDEF);
      assert.equal(verdicts.degraded.length, 1, "败者记 unresolved");
      assert.equal(verdicts.degraded[0].hid, CINS);
      assert.equal(verdicts.degraded[0].verdict, "unresolved");
      assert.match(verdicts.degraded[0].one_line, /账户级限流/, `one_line 写明账户级限流:${verdicts.degraded[0].one_line}`);
      assert.equal(jsonOf(path.join(w.roundDir, "09-budget.json")).readings.model_calls, 4, "轮累计=TRIAGE+DEEP×2(败者也计)+SYNTH");
      const env = outcome.result.envelope;
      assert.equal(env.pipeline.stages.find((s) => s.name === "DEEP").status, "degraded", "DEEP 相位=degraded");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#490 账户级限流批间截断:余下假设不再放出(记 unresolved 未放出),轮正常收口", async () => {
  const roundId = "2026-10-28-0113-health";
  const w = seedWorld({ roundId });
  const fxDir = fixturesWithDeepError(w.tmp, CINS_SLUG, { role: "assistant", content: [], stopReason: "error", errorMessage: ACC_ERR_429 });
  overrideSynth(fxDir, 0, 0, 2); // 深验计数对齐:0 判决+2 unresolved(cins 败+ bdef 未放出)
  const prev = process.env.OPS_MODEL_MAX_INFLIGHT;
  process.env.OPS_MODEL_MAX_INFLIGHT = "1"; // 批=1:首假设撞限,第二假设永不放出
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "completed", `截断应按部分假设未解决正常收口:${JSON.stringify(outcome)}`);
      const verdicts = jsonOf(path.join(w.roundDir, "05-deep-verdicts.json"));
      assert.equal(verdicts.verdicts.length, 0, "零判决(第二假设没跑)");
      assert.equal(verdicts.degraded.length, 2, "两假设都记 unresolved");
      assert.deepEqual(verdicts.degraded.map((d) => d.hid).sort(), [BDEF, CINS].sort());
      assert.ok(verdicts.degraded.every((d) => /账户级限流/.test(d.one_line)), `全部注明账户级限流:${JSON.stringify(verdicts.degraded)}`);
      const bdefLine = verdicts.degraded.find((d) => d.hid === BDEF);
      assert.match(bdefLine.one_line, /未放出/, "未放出假设的 one_line 写明余下假设未放出");
      assert.ok(!fs.existsSync(path.join(w.roundDir, `05-deep-${BDEF_SLUG}.json`)) &&
        !fs.existsSync(path.join(w.roundDir, `05-deep-${BDEF_SLUG}-transcript.jsonl`)), "第二假设零工件零 transcript(批未放出)");
      assert.equal(jsonOf(path.join(w.roundDir, "09-budget.json")).readings.model_calls, 3, "轮累计=TRIAGE+DEEP×1+SYNTH(截断不空烧)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    if (prev === undefined) delete process.env.OPS_MODEL_MAX_INFLIGHT; else process.env.OPS_MODEL_MAX_INFLIGHT = prev;
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#490 TRIAGE 单发步账户级限流:不重试直落轮终态 failed code=account_rate_limited(state.json failed/FAILED)", async () => {
  const roundId = "2026-10-28-e2e-acct-health";
  const w = seedWorld({ roundId });
  const fxDir = path.join(w.tmp, "fixtures-490-triage");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const triage = jsonOf(path.join(fxDir, "triage.json"));
  fs.writeFileSync(path.join(fxDir, "triage.json"), JSON.stringify({ ...triage, turns: [
    { role: "assistant", content: [], stopReason: "error", errorMessage: ACC_ERR_429 },
  ] }));
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `单发步账户级应轮终态 failed:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "account_rate_limited", "轮终态错误码=诚实码");
      assert.match(outcome.error.message, /账户级限流/);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed", "#415:镜像与 outcome 同出口写 failed");
      assert.equal(mirror.stage, "FAILED", "#415:终态 stage 书挡 FAILED");
      assert.ok(!fs.existsSync(path.join(w.roundDir, "03-triage-transcript.jsonl")), "失败回合零 transcript(submission 层败在 writeTranscript 前)");
      // 评审必须改1:单发步账户级限流也写失败轮台账行(与 model_face 同权;仿 #355 深验败用例的写法)
      const led = fs.readFileSync(path.join(w.ops, "ledger.md"), "utf8");
      assert.match(led, /pipeline-failed:2026-10-28-e2e-acct-health error_code=account_rate_limited/, "单发步账户级失败台账行在场(标签:轮 id 可 grep)");
      assert.equal(led.split("\n").filter((l) => l.includes("pipeline-failed:2026-10-28-e2e-acct-health")).length, 1, "恰一行(幂等防双记)");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

test("#490 DEEP 全败皆账户级:轮终态 failed code=account_rate_limited(诚实码不冒充 model_face)", async () => {
  const roundId = "2026-10-28-e2e-acct2-health";
  const w = seedWorld({ roundId });
  const fxDir = path.join(w.tmp, "fixtures-490-deepall");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  for (const slug of [CINS_SLUG, BDEF_SLUG]) {
    const f = jsonOf(path.join(fxDir, "deep", `${slug}.json`));
    fs.writeFileSync(path.join(fxDir, "deep", `${slug}.json`), JSON.stringify({ ...f, turns: [
      { role: "assistant", content: [], stopReason: "error", errorMessage: ACC_ERR_429 },
    ] }));
  }
  const storage = await openNodeSqliteStorage(path.join(w.tmp, "t.sqlite"));
  const context = BACKGROUND_CONTEXT;
  try {
    const harness = await healthHarness(storage, context);
    try {
      harness.resume();
      const root = await harness.root(context);
      const taskId = await root.commit((tx) => tx.createTask(OPS_HEALTH_ROUND, {
        roundId, fromPhase: "TRIAGE", modelFace: "faux", fixturesDir: fxDir,
      }, { ownership: { kind: "conversation" } }), context);
      const settled = await harness.waitForTask(taskId, context);
      const outcome = settled.state.outcome;
      assert.equal(outcome.status, "failed", `全败应轮终态 failed:${JSON.stringify(outcome)}`);
      assert.equal(outcome.error.code, "account_rate_limited", `全败归因=账户级:${JSON.stringify(outcome.error)}`);
      assert.match(outcome.error.message, /全部 2 假设失败/);
      const mirror = jsonOf(path.join(w.roundDir, "state.json"));
      assert.equal(mirror.status, "failed");
      assert.equal(mirror.stage, "FAILED");
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
