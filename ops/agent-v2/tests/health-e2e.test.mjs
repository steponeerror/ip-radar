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
import { Harness } from "@earendil-works/pi-durable";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { createModels } from "@earendil-works/pi-ai";
import { OPS_HEALTH_ROUND } from "../tasks/health-round.mjs";
import { buildRegistry } from "../registry.mjs";

const AGENT = path.resolve(import.meta.dirname, "..", "..", "agent"); // ops/agent(旧真源)
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

test("健康轮链路 E2E:TRIAGE→WAIT_MODEL(join)→DEEP(evidence)→SYNTH→…→CLOSE 全绿(faux 零网络)", async () => {
  const roundId = "2026-10-28-e2e-health";
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
  const roundId = "2026-10-28-e2e-retry-health";
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
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── #355 DEEP 终答 JSON 后尾随散文:首个平衡 JSON 对象提取 + tail_note 留痕(4 起影子废轮回归;旧 consume 族已修,本测钉 v2 装配链)──
test("#355 DEEP 尾注容忍:带尾注终答不再 model_face 误杀,判决收编+tail_note 留痕可查", async () => {
  const roundId = "2026-11-15-e2e-tail-health";
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
    } finally { await harness.close(context); }
  } finally {
    await storage.close(context);
    w.restore();
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
