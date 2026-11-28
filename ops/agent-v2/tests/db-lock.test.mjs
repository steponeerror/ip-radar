// db-lock.test.mjs — 引擎开库独占锁(票 #579;守卫=事实包 §2.3 候选1+2:锁为主、
// 查库只作拒跑诊断)。面:①A 持锁跑 faux 轮 → B 起另一入口立刻拒跑(exit 16+消息含
// A 的任务信息;变异①共享锁/变异③诊断漏状态靶)②A 被 SIGKILL → 锁随进程死释放,
// B 立刻能拿锁跑完 ③同 requestId 双提交框架层幂等(admission 事务内查重,现状已安全
// 钉防回归)④cron 侧等待语义(旋钮 OPS_V2_DB_LOCK_WAIT_S:持锁方限时释放 → 等到跑完;
// 永不释放 → 上限到即拒)+ 入口闭集静态覆盖(变异②靶)。
// 载具=shadow-diff seedWorld faux 面,零网络零花费(cron-launchers.test.mjs 同判例)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { seedWorld } from "../shadow-diff.mjs";
import {
  dbLockPath, dbPathFromArgv, EXIT_DB_LOCKED, DB_LOCK_WAIT_ENV,
} from "../db-lock.mjs";

const execFileP = promisify(execFile);

const HERE = import.meta.dirname;
const AGENT = path.resolve(HERE, "..", "..", "pipeline-core");
const FIXTURES = path.join(AGENT, "fixtures", "pipeline");
const RUN_HEALTH = path.join(HERE, "..", "run-health.mjs");
const RUN_DISCOVER = path.join(HERE, "..", "run-discover.mjs");
const today = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; })(); // 本地日期=台账行日期源(cron-launchers 同律,UTC 分叉防 flake)
const rid = (n = 0) => { const d = new Date(); return `${today}-${String(d.getHours()).padStart(2, "0")}${String((d.getMinutes() + n) % 100).padStart(2, "0")}-health`; }; // 分钟位+n(mod 100),保形状律

// 子进程 CLI(cron-launchers cli 同构):真 spawn node run-health.mjs,收 exit code/stdout/stderr
function cli(args, env) {
  return new Promise((resolve) => {
    const p = spawn("node", [RUN_HEALTH, ...args], { env: { ...env }, cwd: path.resolve(HERE, "..", "..") });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    const done = new Promise((res) => p.on("close", (code, signal) => res({ code, signal, out, err })));
    return resolve({ child: p, done });
  });
}
const awaitClose = (c) => c.done;

// ── 入口闭集静态覆盖(变异②靶:留一个口不加锁 → 此测红)──
test("入口闭集:run-health/run-discover/run-add/entry 四口都调 withDbLock(#579 任务书入口清单)", () => {
  for (const f of ["run-health.mjs", "run-discover.mjs", "run-add.mjs", "entry.mjs"]) {
    const src = fs.readFileSync(path.join(HERE, "..", f), "utf8");
    assert.match(src, /withDbLock\(/, `${f} 缺 withDbLock 调用——入口闭集破口(撞窗重开)`);
  }
});

test("锁目标库落位:argv --db 优先,否则 resolveDbPath 同源(OPS_V2_DB;锁和库不许漂)", () => {
  assert.equal(dbPathFromArgv(["node", "run-health.mjs", "--db", "/tmp/a.sqlite"], {}), "/tmp/a.sqlite");
  assert.equal(dbPathFromArgv(["node", "run-health.mjs"], { OPS_V2_DB: "/tmp/b.sqlite" }), "/tmp/b.sqlite");
  assert.equal(dbLockPath("/x/agent-v2.sqlite"), "/x/agent-v2.sqlite.lock");
});

// ── ①锁冲突拒跑(变异① flock -s / 变异③ 漏状态 靶)。确定性载具:真 faux 轮落库
//    → 轮任务行置回 running 态(SQL 直改,record.state 口径与框架同)→ 裸 flock 持锁
//    → B 另一入口。不用「A 真跑轮时 B 挤」真时序:A 全链 ≈3s 与 B 进程启动同量级,
//    撞窗窗口太窄必 flake(首轮实测 B 常在 A 收尾后才到);真时序面由 ②④ 覆盖。
test("①锁冲突拒跑:库有在飞任务+锁被人持,B 另一入口 exit 16,消息含任务 kind/round/startedAt", async () => {
  const id = rid(10);
  const w = seedWorld(id);
  const db = path.join(w.tmp, "s.sqlite");
  let holder;
  try {
    // 第一步:真 faux 轮跑完 → 库里有真 schema/真任务行
    const a = await awaitClose(await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", db], w.env));
    assert.equal(a.code, 0, `faux 轮应跑完:\n${a.err}`);
    const ro = new DatabaseSync(db, { readOnly: true });
    const rows = ro.prepare("SELECT id, kind, record FROM tasks").all();
    ro.close();
    const task = rows.map((r) => ({ r, rec: JSON.parse(r.record) }))
      .find(({ r, rec }) => rec?.input?.roundId === id && JSON.parse(r.kind) === "ops-health-round");
    assert.ok(task, `应找到本轮轮任务行(rows=${rows.length})`);
    // 第二步:轮任务行置回 running 态(在飞语义;startedAt 口径=transaction.js:730-742 首转 running 时写)
    const rw = new DatabaseSync(db);
    const startedAt = "2026-06-01T04:00:00.000Z";
    rw.prepare("UPDATE tasks SET status = 'running', record = ? WHERE id = ?").run(
      JSON.stringify({ ...task.rec, state: { ...task.rec.state, status: "running", startedAt } }), task.r.id);
    rw.close();
    // 第三步:裸 flock 持锁(模拟另一引擎在跑;锁文件 flock O_CREAT 自建)
    holder = spawn("flock", [dbLockPath(db), "sleep", "30"]);
    await new Promise((r) => setTimeout(r, 400)); // 持锁人拿稳
    // B:同库另一入口(无 roundId——锁面先于用法校验,拒跑必 16 非用法 2;--db 对准同一把锁)
    const b = await awaitClose(await cli(["--db", db], w.env));
    assert.equal(b.code, EXIT_DB_LOCKED, `B 应被锁拒(stdout=${b.out} stderr=${b.err})`);
    assert.equal(b.out.trim(), "", "拒跑 stdout 零信封(ENVELOPE.md 码表 16 行)");
    assert.match(b.err, /\[v2-db-lock\] 拒绝跑轮/);
    assert.match(b.err, /另一引擎进程持有库锁/);
    assert.match(b.err, /kind=ops-health-round/, "消息含在飞任务类型(kind 列 JSON 编码解码)");
    assert.match(b.err, new RegExp(`round=${id}`), "消息含在飞轮号(record.input.roundId)");
    assert.ok(b.err.includes(`startedAt=${startedAt}`), "消息含 startedAt(record.state.startedAt)");
    assert.ok(b.err.includes(`id=${task.r.id}`), "消息含在飞任务 id");
  } finally {
    if (holder) holder.kill("SIGKILL");
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});

// ── ②A 被 SIGKILL(--crash-after-phase 缝,票面指定;相位头自杀面)= 锁随进程死释放,
//    B 立刻拿锁 resume 跑完。信号透传链:任务内自 SIGKILL → flock 对信号死子进程重拉
//    同信号(实测 rc=137 判例)→ 外层见 SIGKILL → 锁已随 flock 死释放。载具=discover
//    crash 面(discover-round.test.mjs「相位头 SIGKILL」同款世界;health 面任意点硬杀
//    的 resume 不在框架保证内,首轮实测会 model_face 废轮——孤儿轮另案 #558)──
test("②SIGKILL 释锁:A 崩在相位头 → B 立刻拿锁 resume 跑完全链", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-dblock-crash-"));
  const docsRoot = path.join(tmp, "docs");
  const db = path.join(tmp, "v2.sqlite");
  const ROUND = "2026-06-01-0400-discover"; // discover-round.test.mjs crash 用例同轮 id
  const crashEnv = { ...process.env, DOCS_ROOT: docsRoot, LEDGER_FILE: path.join(docsRoot, "ops", "ledger.md"), OPS_V2_CRASH_AFTER_PHASE: "shortlist" };
  try {
    const a = await execFileP(process.execPath, [RUN_DISCOVER, ROUND, "--fixtures", FIXTURES, "--db", db], { env: crashEnv, cwd: path.resolve(HERE, "..") }).then(() => null, (e) => e);
    // 信号穿锁代理的两种形(util-linux 版本差):flock 对信号死子进程重拉同信号(外层见
    // signal=SIGKILL)或 exit 128+9(2.41 实测形态,rc=137)——两者都证明链上进程死于 SIGKILL
    assert.ok(a?.signal === "SIGKILL" || a?.code === 137,
      `A 应死于 SIGKILL(实得 code=${a?.code} signal=${a?.signal})`);
    // B:锁已随死释放 → 立刻拿锁 resume 跑完(exit 0)
    const resumeEnv = { ...crashEnv };
    delete resumeEnv.OPS_V2_CRASH_AFTER_PHASE;
    const { stdout, stderr: berr } = await execFileP(process.execPath, [RUN_DISCOVER, ROUND, "--fixtures", FIXTURES, "--db", db], { env: resumeEnv, cwd: path.resolve(HERE, ".."), maxBuffer: 4 * 1024 * 1024 });
    const r = JSON.parse(stdout.trimEnd().split("\n").at(-1));
    assert.equal(r.ok, true, `B 应拿锁 resume 跑完:\n${berr}`);
    assert.deepEqual(r.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"], "恢复后每步恰一次");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── ③同 requestId 双提交:框架层 admission 幂等(submissions.js:150-157 同一 commit
//    事务内查重,现状已安全;钉防回归。串行化面=BEGIN IMMEDIATE 写锁,并发双进程被
//    SQLite 排队后看到的都是先到者已提交的行)──
test("③同 requestId 双提交:同 submission id,库里该 request 恰一行,任务不重复建", async () => {
  const { fauxProvider, fauxAssistantMessage, fauxText, createModels } = await import("@earendil-works/pi-ai");
  const { openHarness } = await import("../entry.mjs");
  const { BACKGROUND_CONTEXT } = await import("@earendil-works/chord/context");
  const tmp = fs.mkdtempSync(path.join(path.sep, "tmp", "v2-dblock-dedup-"));
  const dbPath = path.join(tmp, "s.sqlite");
  try {
    const faux = fauxProvider({ models: [{ id: "faux-dedup" }] });
    faux.setResponses([fauxAssistantMessage([fauxText("dedup-pin")])]);
    const models = createModels();
    models.setProvider(faux.provider);
    const { harness } = await openHarness({ dbPath, models: { models, resolve: () => faux.getModel() } });
    const context = BACKGROUND_CONTEXT;
    try {
      const model = faux.getModel();
      const root = await harness.root(context, { agent: { model: { provider: model.provider, modelId: model.id }, extensions: [] } });
      const req = "round-dblock-dedup-pin";
      const [s1, s2] = await Promise.all([
        root.submit({ type: "input", content: "x", requestId: req }, context),
        root.submit({ type: "input", content: "x", requestId: req }, context),
      ]);
      assert.equal(s1.id, s2.id, "双提交同 requestId 返回同 submission(不重复建)");
      const ro = new DatabaseSync(dbPath, { readOnly: true });
      // request_id 列=encodeIndexedString 存形(JSON.stringify,storage.js:10、598)——同形对参
      const rows = ro.prepare("SELECT id FROM submissions WHERE request_id = ?").all(JSON.stringify(req));
      ro.close();
      assert.equal(rows.length, 1, `该 request 恰一行 submission(实得 ${rows.length})`);
    } finally { await harness.close(context); }
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── ④cron 侧等待语义(旋钮调小;票面 900s 生产值由 deploy/ops-cron-v2*.sh 出口,
//    ops-cron-v2*.test.mjs 钉)──
test("④cron 侧等待:持锁方限时释放 → 等到跑完;永不释放 → 上限到即拒 16", async () => {
  const id = rid(12);
  const w = seedWorld(id);
  const db1 = path.join(w.tmp, "s1.sqlite");
  const db2 = path.join(w.tmp, "s2.sqlite");
  const holders = [];
  try {
    // 持锁人 = 裸 flock(1)(模拟另一引擎在跑;锁文件 flock O_CREAT 自建)
    holders.push(spawn("flock", [dbLockPath(db1), "sleep", "2"]));
    await new Promise((r) => setTimeout(r, 400)); // 持锁人拿稳
    const b = await awaitClose(await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", db1],
      { ...w.env, [DB_LOCK_WAIT_ENV]: "15" }));
    assert.equal(b.code, 0, `限时释放后应等到锁跑完:\n${b.err}`);

    holders.push(spawn("flock", [dbLockPath(db2), "sleep", "60"]));
    await new Promise((r) => setTimeout(r, 400));
    const t0 = Date.now();
    const c = await awaitClose(await cli(["--db", db2], { ...w.env, [DB_LOCK_WAIT_ENV]: "2" }));
    const wallS = (Date.now() - t0) / 1000;
    assert.equal(c.code, EXIT_DB_LOCKED, `上限到应拒(stdout=${c.out} stderr=${c.err})`);
    assert.ok(wallS < 10, `应在旋钮上限附近拒(实耗 ${wallS.toFixed(1)}s,不得挂满 sleep 60)`);
    assert.match(c.err, /等了 2 秒没等到/, "拒跑消息报出等待上限");
    assert.match(c.err, /在飞任务:查不到/, "db2 无库:诊断如实写查不到,不猜");
  } finally {
    for (const h of holders) h.kill("SIGKILL");
    fs.rmSync(w.tmp, { recursive: true, force: true });
  }
});
