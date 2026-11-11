// add-round.test.mjs — 加源轮 P1 骨架测试面(票 #332;设计真源 docs/superpowers/
// specs/2026-11-11-add-round-reimplementation-bench-design.md §架构 + §相位表 + 定案 7/8/9)。
// 面:①faux 全链冒烟(六相位/信封/工件/门全绿/台账行/沙箱真产物/分支指针)
// ②bench 形态 DOSSIER 跳过(开关位接口,P2b 基准接线消费)③未 APPROVE 卡=fail-closed
// 且轮零写 queue(写口仅人面)④相位头 SIGKILL 崩溃→同库 resume 续跑 ⑤CLI 冻结面
// (用法错 exit 2/真实轮零缺省模型/坏轮 id=bad_round 信封 exit 1)⑥旋钮族 OPS_ADD_*
// ⑦纯函数面(queue 行 evidence 解析/roster 撞卡/鲜活度/交接单与摘要形状/门命令集)。
// 沙箱世界:最小 repo 形树(git 单根提交 + ipdb 包骨架)——IMPLEMENT 工具真写真跑
// (run_pytest 红面=ModuleNotFoundError 正确理由),GATE 命令真执行,零网络。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb, execFileSync } from "node:child_process";
import { promisify } from "node:util";
import { runAddRound } from "../run-add.mjs";
import {
  ADD_PHASES,
  ADD_TASK_NAME,
  ADD_GATES,
  parseQueueRows,
  rosterCollisions,
  freshnessOf,
  dossierShape,
  implementSummaryShape,
  gateCommandsFor,
  slugify,
} from "../tasks/add-round.mjs";
import { roundKnobs, knobNames } from "../tasks/budget-guard.mjs";
import { addTools, addHosts, ADD_TOOL_NAMES } from "../tools/add-tools.mjs";

const execFile = promisify(execFileCb);
const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES = path.join(HERE, "fixtures", "add");
const ROUND = "2026-06-01-0400-add";
const SOURCE = "sampleblock";

// queue.md 表头(冻结件独立真源:backend/ipdb/_ops_store.py QUEUE_HEADER,不从被测模块导入)
const QUEUE_HEADER = (
  "# 源生命周期动作队列(三写口:ops 轮 queue_action · 发现轮 ENQUEUE 候选行 · 发现轮候选卡 appendCandidateCard;后两路 action=PROPOSE 一词一拼;行由 host 模板渲染,rationale 只落工件)\n\n" +
  "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n" +
  "|---|---|---|---|---|---|---|\n"
);

const DOSSIER = {
  name: "Sample Block List",
  url: "https://blocklist.example/raw.txt",
  samples: ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
  format: "plain-ip-list",
  auth: "none",
  cadence: "daily",
  field_routing: ["整行 IP → rebuild 键(cidr)"],
};

function seedWorld(prefix, { approve = true } = {}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const docsRoot = path.join(tmp, "docs");
  const opsRoot = path.join(docsRoot, "ops");
  fs.mkdirSync(opsRoot, { recursive: true });
  const rows = [
    `| 2026-06-01 | discover | PROPOSE | ${SOURCE} | — | candidate:name="Sample Block List";candidate:url="https://blocklist.example/raw.txt" | 是(否决=删除本行) |`,
  ];
  if (approve)
    rows.push(`| 2026-06-02 | human | APPROVE | ${SOURCE} | — | human:approved_by="测试" | 是(否决=删除本行) |`);
  fs.writeFileSync(path.join(opsRoot, "queue.md"), QUEUE_HEADER + rows.join("\n") + "\n");
  // 沙箱:最小 repo 形树(REPORT 分支指针走真 git 面;ipdb 包骨架让 python -m pytest
  // 的 cwd sys.path 面 importable——红面=ModuleNotFoundError 正确理由)
  const sandbox = path.join(tmp, "sandbox");
  fs.mkdirSync(path.join(sandbox, "backend", "ipdb"), { recursive: true });
  fs.writeFileSync(path.join(sandbox, "backend", "ipdb", "__init__.py"), "");
  const git = (...a) => execFileSync("git", ["-C", sandbox, ...a], { stdio: "ignore" });
  git("init", "-q");
  git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A");
  git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init");
  const sha0 = execFileSync("git", ["-C", sandbox, "rev-parse", "HEAD"]).toString().trim();
  return { tmp, docsRoot, opsRoot, sandbox, sha0 };
}

async function runRound(world, opts = {}) {
  const keys = ["DOCS_ROOT", "LEDGER_FILE"];
  const saved = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  process.env.DOCS_ROOT = world.docsRoot;
  process.env.LEDGER_FILE = path.join(world.opsRoot, "ledger.md");
  try {
    return await runAddRound({
      roundId: opts.roundId ?? ROUND,
      source: opts.source ?? SOURCE,
      sandboxRoot: opts.sandboxRoot ?? world.sandbox,
      fixturesDir: opts.fixturesDir ?? FIXTURES,
      dbPath: opts.dbPath ?? path.join(world.tmp, "v2.sqlite"),
      bench: opts.bench ?? false,
      dossier: opts.dossier ?? null,
      env: { ...process.env },
      stderr: { write: () => true },
    });
  } finally {
    for (const k of keys) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

// ── ① faux 全链冒烟 ────────────────────────────────────────────────────
test("faux 全链冒烟:六相位全绿;沙箱真产物+分支指针+台账行+09-budget OPS_ADD_* 面", async () => {
  const w = seedWorld("v2-add-full-");
  try {
    const r = await runRound(w);
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    const env = r.envelope;
    assert.equal(env.ok, true);
    assert.equal(env.round, "add");
    assert.equal(env.source, SOURCE);
    assert.deepEqual(Object.keys(env).sort(), ["ok", "pipeline", "pkg", "queue_writes", "round", "sandbox", "source", "usage", "verify"].sort(), "加源轮信封键闭集(ENVELOPE.md add 节)");
    assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["VERIFY", "DOSSIER", "IMPLEMENT", "GATE", "REPORT", "CLOSE"]);
    // usage 求和律(各步 usage 之和==信封 usage;脚本步 null 不回声)
    const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
    for (const s of env.pipeline.stages) if (s.usage) for (const k of Object.keys(sum)) sum[k] += s.usage[k];
    assert.deepEqual(sum, env.usage);
    // 工件闭集
    const dir = path.join(w.opsRoot, "rounds", ROUND);
    for (const f of ["a1-verify.json", "a2-dossier.json", "a2-dossier-transcript.jsonl", "a3-implement.json", "a3-implement-transcript.jsonl", "a4-gate.json", "a5-report.json", "09-budget.json", "gates.json", "state.json"])
      assert.ok(fs.existsSync(path.join(dir, f)), `工件缺:${f}`);
    // 门六记录全绿
    const gates = JSON.parse(fs.readFileSync(path.join(dir, "gates.json"), "utf8"));
    assert.equal(gates.records.length, 6, "六相位各一门留痕");
    for (const rec of gates.records) assert.equal(rec.pass, true, `${rec.stage} 门红:${rec.reason}`);
    // VERIFY 工件:卡+roster 对照+鲜活度
    const a1 = JSON.parse(fs.readFileSync(path.join(dir, "a1-verify.json"), "utf8"));
    assert.equal(a1.card.name, "Sample Block List");
    assert.deepEqual(a1.roster.collisions, []);
    assert.equal(a1.freshness.ok, true);
    // 沙箱真产物(TDD 硬序两文件;工具真执行非罐装)
    assert.ok(fs.existsSync(path.join(w.sandbox, "backend", "tests", "sources", "test_sample_block_list.py")), "测试文件应落沙箱");
    assert.ok(fs.existsSync(path.join(w.sandbox, "backend", "ipdb", "_sources", "sample_block_list.py")), "源文件应落沙箱");
    // GATE 工件:命令真执行 rc=0
    const a4 = JSON.parse(fs.readFileSync(path.join(dir, "a4-gate.json"), "utf8"));
    assert.equal(a4.passed, true);
    assert.equal(a4.results.length, 1);
    assert.equal(a4.results[0].rc, 0, `faux 门命令应绿:${JSON.stringify(a4.results[0].tail)}`);
    // REPORT:git 分支指针真路径(轮提交推进 sha)
    assert.notEqual(env.sandbox.sha, w.sha0, "REPORT 轮提交应推进沙箱 HEAD");
    assert.equal(env.sandbox.root, w.sandbox);
    assert.equal(env.sandbox.branch, "master");
    const a5 = JSON.parse(fs.readFileSync(path.join(dir, "a5-report.json"), "utf8"));
    assert.equal(a5.sandbox.sha, env.sandbox.sha);
    // IMPLEMENT transcript 行型:input + registry_seed(4 工具回合)+ message
    const tl = fs.readFileSync(path.join(dir, "a3-implement-transcript.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
    assert.deepEqual(tl.map((x) => x.type), ["input", "registry_seed", "registry_seed", "registry_seed", "registry_seed", ...Array.from({ length: 5 }, () => "message")], "实现转录=输入+四种子+五回合");
    // 台账行 + 09-budget env 面(OPS_ADD_* 族)
    const ledger = fs.readFileSync(path.join(w.opsRoot, "ledger.md"), "utf8");
    assert.match(ledger, /pipeline-add:2026-06-01-0400-add/, "台账轮次行缺失");
    const budget = JSON.parse(fs.readFileSync(path.join(dir, "09-budget.json"), "utf8"));
    assert.deepEqual(Object.keys(budget.env).sort(), ["OPS_ADD_MAX_MODEL_CALLS", "OPS_ADD_SPEND_CAP_CNY", "OPS_ADD_WALL_CLOCK_S", "OPS_PIPELINE_BUDGET_CNY", "OPS_PIPELINE_MONTHLY_CAP_CNY"].sort());
    assert.equal(budget.readings.model_calls, 6, "dossier 1 回合+implement 5 回合=6 次模型调用");
    // queue.md 零写(轮无写口改卡状态:PROPOSE/APPROVE 行原样)
    const q = fs.readFileSync(path.join(w.opsRoot, "queue.md"), "utf8");
    assert.equal((q.match(/\| 2026-/g) ?? []).length, 2, "轮不得写 queue.md");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ② bench 形态:DOSSIER 跳过(开关位接口,定案 2)──────────────────────
test("bench 形态:DOSSIER 相位跳过,交接单预填直入,零 dossier 模型回合", async () => {
  const w = seedWorld("v2-add-bench-");
  // bench 夹具=去 DOSSIER 首回合(轮会话顺序消费罐装回合;P2b 基准接线消费同一开关)
  const fxDir = path.join(w.tmp, "fixtures");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const turns = JSON.parse(fs.readFileSync(path.join(fxDir, "turns.json"), "utf8"));
  fs.writeFileSync(path.join(fxDir, "turns.json"), JSON.stringify({ turns: turns.turns.slice(1) }));
  try {
    const r = await runRound(w, { bench: true, dossier: DOSSIER, fixturesDir: fxDir });
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    assert.deepEqual(r.envelope.pipeline.stages.map((s) => s.name), ["VERIFY", "IMPLEMENT", "GATE", "REPORT", "CLOSE"], "bench 轮相位截断(卡已预填,DOSSIER 跳过)");
    const dir = path.join(w.opsRoot, "rounds", ROUND);
    const a2 = JSON.parse(fs.readFileSync(path.join(dir, "a2-dossier.json"), "utf8"));
    assert.equal(a2.bench, true);
    assert.equal(a2.dossier.url, DOSSIER.url);
    assert.equal(fs.existsSync(path.join(dir, "a2-dossier-transcript.jsonl")), false, "跳过相位零转录");
    const budget = JSON.parse(fs.readFileSync(path.join(dir, "09-budget.json"), "utf8"));
    assert.equal(budget.readings.model_calls, 5, "仅 implement 5 回合(dossier 零模型面)");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ③ 未 APPROVE 卡 = fail-closed(定案 9:只消费 status=approved)─────────
test("未 APPROVE 卡=fail-closed card_not_approved;轮零写 queue(写口仅人面)", async () => {
  const w = seedWorld("v2-add-noappr-", { approve: false });
  try {
    const r = await runRound(w);
    assert.equal(r.status, "failed");
    assert.equal(r.error.detail?.code, "card_not_approved", JSON.stringify(r.error));
    assert.match(r.error.message, /APPROVE/);
    const q = fs.readFileSync(path.join(w.opsRoot, "queue.md"), "utf8");
    assert.ok(!q.includes("APPROVE"), "轮不得写 APPROVE 行(写口仅人面)");
    assert.equal(fs.existsSync(path.join(w.opsRoot, "rounds", ROUND, "a1-verify.json")), false, "门红不落通过工件");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ④ 相位头 SIGKILL 崩溃 → 同库 resume(相位边界恢复点)──────────────────
test("相位头 SIGKILL 崩溃 → 同库 resume 续跑到 CLOSE", async () => {
  const w = seedWorld("v2-add-crash-");
  const db = path.join(w.tmp, "v2.sqlite");
  const env = { ...process.env, DOCS_ROOT: w.docsRoot, LEDGER_FILE: path.join(w.opsRoot, "ledger.md"), OPS_V2_CRASH_AFTER_PHASE: "dossier" }; // 崩钩语义=进入指定相位头自杀(discover 同律):crash 面在 DOSSIER 头=VERIFY checkpoint+a1 已落盘,验证「上一相位完整、恢复不重跑」
  const run = (e) => execFile(process.execPath, [path.join(HERE, "run-add.mjs"), ROUND, "--source", SOURCE, "--sandbox", w.sandbox, "--fixtures", FIXTURES, "--db", db], { env: e }).catch((er) => er.code);
  try {
    const kill = await run(env);
    assert.equal(kill, null, `SIGKILL 期望进程被杀(exit code ${kill} 非自杀)`);
    assert.ok(fs.existsSync(path.join(w.opsRoot, "rounds", ROUND, "a1-verify.json")), "verify 工件应先于崩溃落盘");
    delete env.OPS_V2_CRASH_AFTER_PHASE;
    const { stdout } = await run(env);
    const r = JSON.parse(stdout.trim().split("\n").filter((l) => l.startsWith("{")).pop());
    assert.equal(r.ok, true, JSON.stringify(r.error ?? r));
    assert.deepEqual(r.pipeline.stages.map((s) => s.name), ["VERIFY", "DOSSIER", "IMPLEMENT", "GATE", "REPORT", "CLOSE"], "恢复后每相位恰一次");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ⑤ CLI 冻结面(ENVELOPE.md 退出码表)─────────────────────────────────
test("CLI:缺 --source/--sandbox、坏 --model、真实面漏 --model = exit 2;坏轮 id = bad_round 信封 exit 1", async () => {
  const w = seedWorld("v2-add-cli-");
  const env = { ...process.env, DOCS_ROOT: w.docsRoot, LEDGER_FILE: path.join(w.opsRoot, "ledger.md") };
  const run = (args) => execFile(process.execPath, [path.join(HERE, "run-add.mjs"), ...args], { env }).catch((e) => e);
  const good = ["--sandbox", w.sandbox, "--fixtures", FIXTURES, "--db", path.join(w.tmp, "cli.sqlite")];
  try {
    for (const bad of [["2026-06-01-0400-add", "--sandbox", w.sandbox, "--fixtures", FIXTURES], [ROUND, "--source", SOURCE, "--fixtures", FIXTURES]]) {
      const r = await run(bad);
      assert.equal(r.code, 2, `缺必填 flag 应 exit 2:${bad.join(" ")}`);
      assert.equal(r.stdout.trim(), "", "用法错不发信封");
    }
    assert.equal((await run([ROUND, "--source", SOURCE, ...good, "--model", "noprovider"])).code, 2, "--model 缺斜杠=用法错");
    assert.equal((await run([ROUND, "--source", SOURCE, "--sandbox", w.sandbox, "--db", path.join(w.tmp, "x.sqlite")])).code, 2, "真实面(无 --fixtures)缺 --model=用法错不带病跑轮");
    const r = await run(["not-an-add-id", "--source", SOURCE, ...good]);
    assert.equal(r.code, 1);
    const e = JSON.parse(r.stdout.trim().split("\n").pop());
    assert.equal(e.ok, false);
    assert.equal(e.error.code, "bad_round");
    assert.match(e.error.message, /YYYY-MM-DD-HHMM-add/);
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ⑥ 旋钮族 OPS_ADD_*(spec §预算与执法:独立族,缺省沿发现轮形状缩放)─────
test("OPS_ADD_* 旋钮族:缺省=发现轮形状缩放(calls×2/wall×2/spend 同);env 覆盖;非法=用法错;旋钮名指认", () => {
  assert.deepEqual(roundKnobs({}, "add"), { maxModelCalls: 60, wallClockS: 7200, spendCapCny: 5, monthlyCapCny: 30, dupCallLimit: 3 });
  const k = roundKnobs({ OPS_ADD_MAX_MODEL_CALLS: "7", OPS_ADD_WALL_CLOCK_S: "99", OPS_ADD_SPEND_CAP_CNY: "1.5" }, "add");
  assert.equal(k.maxModelCalls, 7);
  assert.equal(k.wallClockS, 99);
  assert.equal(k.spendCapCny, 1.5);
  assert.deepEqual(knobNames("add"), { calls: "OPS_ADD_MAX_MODEL_CALLS", wall: "OPS_ADD_WALL_CLOCK_S", spend: "OPS_ADD_SPEND_CAP_CNY" });
  assert.throws(() => roundKnobs({ OPS_ADD_SPEND_CAP_CNY: "-1" }, "add"), (e) => e.usage === true, "非法旋钮=用法错不带病跑轮");
});

// ── ⑦ 纯函数面 ─────────────────────────────────────────────────────────
test("相位闭集与任务名", () => {
  assert.deepEqual(ADD_PHASES, ["verify", "dossier", "implement", "gate", "report", "close"]);
  assert.equal(ADD_TASK_NAME, "ops.add-round");
});

test("queue 行解析:三写口行形;evidence 引号内分号不裂(JSON 值面)", () => {
  const md = QUEUE_HEADER +
    '| 2026-06-01 | discover | PROPOSE | s1 | — | candidate:name="A;B";candidate:url="https://x/y;a=1" | 是(否决=删除本行) |\n' +
    "| 2026-06-02 | human | APPROVE | s1 | — | human:approved_by=\"owner\" | 是(否决=删除本行) |\n";
  const rows = parseQueueRows(md);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].action, "PROPOSE");
  assert.equal(rows[0].source, "s1");
  assert.equal(rows[0].evidence.get("candidate:name"), "A;B");
  assert.equal(rows[0].evidence.get("candidate:url"), "https://x/y;a=1");
  assert.equal(rows[1].action, "APPROVE");
  assert.equal(rows[1].evidence.get("human:approved_by"), "owner");
});

test("roster 撞卡:host 列与子列命中=重复出版方(skill Phase 1 律);大小写不敏感;去前导 www. 再比(#334 消化件①)", () => {
  const roster = [
    "dataplane | threat | dataplane.org | ip,asn | telnetlogin,rdns",
    "binarydefense | threat | www.binarydefense.com | ip",
  ];
  assert.deepEqual(rosterCollisions("dataplane.org", roster), ["dataplane.org"]);
  assert.deepEqual(rosterCollisions("DataPlane.ORG", roster), ["dataplane.org"], "host 大小写不敏感");
  assert.deepEqual(rosterCollisions("www.dataplane.org", roster), ["dataplane.org"], "候选带 www. 前缀→去 www 再比(www.dataplane.org vs dataplane.org 逐字比漏拦)");
  assert.deepEqual(rosterCollisions("binarydefense.com", roster), ["www.binarydefense.com"], "roster 侧带 www. → 去 www 后命中(报 roster 原文形)");
  assert.deepEqual(rosterCollisions("telnetlogin", roster), ["telnetlogin"], "子列信号撞卡(dataplane 前例)");
  assert.deepEqual(rosterCollisions("blocklist.example", roster), [], "零撞=过");
});

test("G_CLOSE queue.md 对拍:a1 记 sha,轮内被改写=红 sandbox_violation(轮零队列写防线,#334 消化件②)", async () => {
  const w = seedWorld("v2-add-qsha-");
  try {
    const r = await runRound(w);
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    const dir = path.join(w.opsRoot, "rounds", ROUND);
    const a1 = JSON.parse(fs.readFileSync(path.join(dir, "a1-verify.json"), "utf8"));
    assert.match(a1.queue_sha ?? "", /^[0-9a-f]{16}$/, "a1 须记 queue.md sha(镜像台账行读回防线同律)");
    const q0 = fs.readFileSync(path.join(w.opsRoot, "queue.md"), "utf8");
    // 轮后原样:同 ctx 重评 G_CLOSE 仍绿(信封/预算/台账工件均在)
    const ctx = { dir, queueFile: path.join(w.opsRoot, "queue.md"), envelope: { ok: true, round: "add" }, ledgerFile: path.join(w.opsRoot, "ledger.md"), roundId: ROUND, source: SOURCE };
    assert.equal(ADD_GATES.G_CLOSE(ctx).pass, true, JSON.stringify(ADD_GATES.G_CLOSE(ctx)));
    // 轮内改写模拟:queue.md 被(模型工具面/任何轮面)追加行 → sha 对拍红
    fs.appendFileSync(ctx.queueFile, `| 2026-06-03 | add | PROPOSE | ${SOURCE} | — | candidate:name="被改写" | 是(否决=删除本行) |\n`);
    assert.equal(q0.length > 0, true);
    const red = ADD_GATES.G_CLOSE(ctx);
    assert.equal(red.pass, false);
    assert.equal(red.code, "sandbox_violation");
    assert.match(red.reason, /queue\.md/);
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("鲜活度门:内部时间戳 ≤30d 过;>30d 或无证据=不过(响应≠活,file-mtime 不算)", () => {
  const now = new Date("2026-06-10T00:00:00Z").getTime();
  assert.equal(freshnessOf({ age_days: 2 }, now).ok, true);
  const stale = freshnessOf({ age_days: 45 }, now);
  assert.equal(stale.ok, false);
  assert.match(stale.reason, /45/);
  const none = freshnessOf({}, now);
  assert.equal(none.ok, false);
  assert.match(none.reason, /无内部时间戳/);
});

test("交接单形状:样本 3-5 行+必填面;缺面/越界=拒", () => {
  const r = dossierShape(DOSSIER);
  assert.equal(r.ok, true);
  for (const bad of [
    { ...DOSSIER, samples: ["1.2.3.4", "5.6.7.8"] }, // <3 行
    { ...DOSSIER, samples: ["a", "b", "c", "d", "e", "f"] }, // >5 行
    { ...DOSSIER, cadence: "" }, // 必填缺
    { ...DOSSIER, field_routing: [] }, // 路由草案空
    { ...DOSSIER, url: "not-a-url" },
  ]) {
    const x = dossierShape(bad);
    assert.equal(x.ok, false, `应拒:${JSON.stringify(bad).slice(0, 60)}`);
    assert.ok(typeof x.reason === "string" && x.reason);
  }
});

test("实现摘要形状:双文件+红绿双观察+stem 名;缺观察=拒(TDD 硬序机检面)", () => {
  const ok = implementSummaryShape({ name: "sample_block_list", test_file: "backend/tests/sources/test_sample_block_list.py", source_file: "backend/ipdb/_sources/sample_block_list.py", red_observed: true, green_observed: true });
  assert.equal(ok.ok, true);
  assert.equal(implementSummaryShape({ ...ok.summary, red_observed: false }).ok, false, "未看红=拒");
  assert.equal(implementSummaryShape({ ...ok.summary, green_observed: false }).ok, false, "未转绿=拒");
  assert.equal(implementSummaryShape({ ...ok.summary, source_file: "" }).ok, false);
});

test("门命令集:真实面=逐源测试+source_infra+目录源审计三连(定案 8 GATE 行);faux 面=罐装清单", () => {
  const real = gateCommandsFor({ stem: "sample_block_list", modelFace: "real", fixturesDir: null });
  assert.deepEqual(real.map((c) => c.args), [
    ["-m", "pytest", "tests/sources/test_sample_block_list.py", "-q"],
    ["-m", "pytest", "tests/source_infra/", "-q"],
    ["scripts/audit_lmdb_invariants.py"],
  ]);
  assert.deepEqual(real.map((c) => c.cwd), ["backend", "backend", ""]);
  const faux = gateCommandsFor({ stem: "x", modelFace: "faux", fixturesDir: FIXTURES });
  assert.deepEqual(faux, JSON.parse(fs.readFileSync(path.join(FIXTURES, "gate.json"), "utf8")).commands);
});

test("stem 派生:描述名→文件名 stem(house style [a-z0-9_])", () => {
  assert.equal(slugify("Sample Block List"), "sample_block_list");
  assert.equal(slugify("AbuseIPDB!"), "abuseipdb");
});

// ── ⑧ 编码工具面:沙箱遏制 + 未绑定宿主拒绝 ─────────────────────────────
test("编码工具闭集与沙箱遏制:write_file 逃逸拒绝;未绑定会话=拒绝信封", async () => {
  assert.deepEqual([...ADD_TOOL_NAMES].sort(), ["run_bash", "run_pytest", "write_file"]);
  const tools = addTools();
  const by = (n) => tools.find((t) => t.name === n);
  // 未绑定会话:拒绝信封(不执行任何面)
  const unbound = await by("write_file").execute({ path: "a.txt", content: "x" }, { conversationId: "conv-unbound-add", callId: "c0" });
  assert.equal(unbound.structuredOutput.ok, false);
  assert.equal(unbound.structuredOutput.code, "host_missing");
  // 沙箱逃逸:../ 前缀拒绝
  addHosts.set("conv-add-t", { sandboxRoot: fs.mkdtempSync(path.join(os.tmpdir(), "v2-add-host-")), python: process.execPath, seeds: [] });
  try {
    const esc = await by("write_file").execute({ path: "../escape.txt", content: "x" }, { conversationId: "conv-add-t", callId: "c1" });
    assert.equal(esc.structuredOutput.ok, false);
    assert.equal(esc.structuredOutput.code, "sandbox_escape");
    const ok = await by("write_file").execute({ path: "backend/nested/dir/a.txt", content: "x" }, { conversationId: "conv-add-t", callId: "c2" });
    assert.equal(ok.structuredOutput.ok, true);
    const host = addHosts.get("conv-add-t");
    assert.equal(host.seeds.length, 2, "种子登记(转录 registry_seed 面)");
  } finally { addHosts.delete("conv-add-t"); }
});
