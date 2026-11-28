// db-lock.test.mjs — 引擎开库独占锁(票 #579;守卫=事实包 §2.3 候选1+2:锁为主、
// 查库只作拒跑诊断)。面:①A 持锁跑 faux 轮 → B 起另一入口立刻拒跑(exit 16+消息含
// A 的任务信息;变异①共享锁/变异③诊断漏状态靶)②A 被 SIGKILL → 锁随进程死释放,
// B 立刻能拿锁跑完 ③同 requestId 双提交框架层幂等(admission 事务内查重,现状已安全
// 钉防回归)④cron 侧等待语义(旋钮 OPS_V2_DB_LOCK_WAIT_S:持锁方限时释放 → 等到跑完;
// 永不释放 → 上限到即拒)+ 入口闭集静态覆盖(变异②靶)。返工新增(2026-11-28 评审后):
// ⑤两真引擎进程真时序;⑥held 标记不传孙子(变异③新靶);⑦flock 缺席退出 3 非锁冲突
// (变异①新靶;原变异①靶=共享锁仍在第①测)。
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

// ── 入口闭集静态覆盖(变异②靶:留一个口不加锁 → 此测红;返工第4条收紧:清单不写死,
//    扫顶层文件;匹配前去 // 注释行,正则钉真调用面而非 import/注释字样)──
// 扫描集判定(返工裁决 B 2026-11-28):带「直接执行才跑」判断(process.argv[1] 共有形状)
// 且自己开 agent-v2 库(信号=文件内 import openHarness 或 resolveDbPath)的顶层 .mjs。
// 边界(评审指认后裁决):add-lift.mjs 不开此库(#375 封存的手动 lift 工具链,全文件无
// openHarness/resolveDbPath);shadow-diff.mjs 自己也不开——两侧子进程各 spawn run-health
// 且各带自己的 --db 临时库,锁面在子进程已覆盖。两者都不入扫描集(不要求上锁)。
test("入口闭集:顶层直接执行且开 agent-v2 库的 .mjs 都有 await withDbLock( 调用", () => {
  const dir = path.resolve(HERE, "..");
  const required = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!e.isFile() || !e.name.endsWith(".mjs")) continue; // 只扫顶层文件(tests/、bench/ 是目录,天然不在)
    const src = fs.readFileSync(path.join(dir, e.name), "utf8");
    if (/process\.argv\[1\]/.test(src) && /openHarness|resolveDbPath/.test(src)) required.push(e.name);
  }
  assert.ok(["entry.mjs", "run-health.mjs", "run-discover.mjs", "run-add.mjs"].every((f) => required.includes(f)),
    `四入口应都在扫描集内(实得 ${required.join(",")})——开库信号判定漂了`);
  assert.ok(!required.includes("add-lift.mjs") && !required.includes("shadow-diff.mjs"),
    `不开 agent-v2 库的 CLI 不应被要求上锁(实得 ${required.join(",")})`);
  for (const f of required) {
    const code = fs.readFileSync(path.join(dir, f), "utf8")
      .split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n"); // 去 // 注释行:注释里的字样不作数
    assert.match(code, /^\s*await withDbLock\(/m, `${f} 缺 await withDbLock( 调用——入口闭集破口(撞窗重开)`);
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
    // 第三步:裸 flock -s 持锁(变异①靶:持锁人也拿共享——若引擎侧也被改成共享锁,
    // B 与持锁人共存,B 就不会拒跑,本测必红;独占引擎对共享持锁人照撞冲突)
    holder = spawn("flock", ["-s", dbLockPath(db), "sleep", "30"]);
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

// ── ⑤两个真引擎进程(返工第5条):A 真跑轮(带 --db),锁在场且在飞行可见后立刻起
//    B(同 --db 无轮号——锁面先于用法校验)→ B 拒 16 且报出 A 的在飞轮号(真时序下
//    的诊断消息面,与①的确定性载具互补),A 不受影响跑完 0。确定性两件:①触发信号
//    不用认领件(.v2-claim.json)——返工实测它落在 A 收尾前 ~0.3s,晚于 B 的启动耗时,
//    拿它触发必 flake;改扫 /proc 等 A 的 flock 进程在场(锁面信号,A 起步即成立);
//    ②A 的 TRIAGE 头部插两个 429 error 回合(rounds.test.mjs #490 同形;生产会话层
//    自动重试吃掉它们,每次重试带 2s/4s 指数退避)把 A 拉长 ~6s,给 B 的拒跑窗口——
//    否则「在飞行可见 → A 释放」只有 ~0.3s,B 的启动追不上(返工实测)──
test("⑤两个真引擎进程:A 跑轮中 B 同库另入口 → B 拒 16 报 A 轮号,A 跑完 0", async () => {
  const { liveTasksReport } = await import("../db-lock.mjs");
  const id = rid(14);
  const w = seedWorld(id);
  const db = path.join(w.tmp, "s.sqlite");
  const ERR_TURN = { role: "assistant", content: [], stopReason: "error", errorMessage: "429: too many requests, slow down" }; // 单请求限流说法(model-errors RATE_LIMIT_RE 面;非 1302 不触账户级终态)
  try {
    const fx = path.join(w.tmp, "fixtures429");
    fs.cpSync(FIXTURES, fx, { recursive: true }); // 全量拷贝(TRIAGE 之外的 DEEP 等 Phase 还要各自 fixture 件,缺件=infra 失败,返工实测)
    const canned = JSON.parse(fs.readFileSync(path.join(FIXTURES, "triage.json"), "utf8"));
    fs.writeFileSync(path.join(fx, "triage.json"), JSON.stringify({ ...canned, turns: [ERR_TURN, ERR_TURN, ...canned.turns] }));
    const a = await cli([id, "--from-phase", "TRIAGE", "--fixtures", fx, "--db", db], w.env);
    let flockSeen = false;
    for (let i = 0; i < 2000 && !flockSeen; i++) { // 10s 帽:A 的代理 spawn 的 flock 进程(锁文件路径只在它的 argv 里)
      flockSeen = fs.readdirSync("/proc").some((n) => /^\d+$/.test(n) && (() => { try { return fs.readFileSync(`/proc/${n}/cmdline`, "utf8").includes(dbLockPath(db)); } catch { return false; } })());
      if (!flockSeen) await new Promise((r) => setTimeout(r, 5));
    }
    assert.equal(flockSeen, true, "A 的锁应在帽内被探到在场(锁已被人持)");
    let live = null;
    for (let i = 0; i < 6000 && !live; i++) { // 等 A 开库且在飞行可见(诊断消息的数据源;开库前拒跑只写「查不到」)
      live = liveTasksReport(db);
      if (!live?.length) { live = null; await new Promise((r) => setTimeout(r, 10)); }
    }
    assert.ok(live?.length, "A 的在飞行应在帽内可见");
    const b = await awaitClose(await cli(["--db", db], w.env));
    assert.equal(b.code, EXIT_DB_LOCKED, `B 应被 A 的锁拒(stdout=${b.out} stderr=${b.err})`);
    assert.match(b.err, new RegExp(`round=${id}`), "B 拒跑消息报出 A 的在飞轮号(真时序诊断面)");
    const ra = await awaitClose(a);
    assert.equal(ra.code, 0, `A 应不受 B 影响跑完:\n${ra.out}\n${ra.err}`);
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

// ── ⑥held 标记只活一代(返工第6条,变异③靶):held 进程内标记应从 process.env 删掉,
//    它再 spawn 的子进程 env 不含标记——否则孙子进程会自认已持锁、裸开库 ──
test("⑥held 标记不传孙子:held 进程内标记已删,新 spawn 的子进程 env 无标记", async () => {
  const { withDbLock, DB_LOCK_HELD_ENV: HELD } = await import("../db-lock.mjs");
  const { spawnSync } = await import("node:child_process");
  const prev = process.env[HELD];
  process.env[HELD] = "1";
  try {
    let grandEnvRaw;
    await withDbLock(async () => {
      grandEnvRaw = spawnSync(process.execPath, ["-e", "process.stdout.write(JSON.stringify(process.env))"], { encoding: "utf8" }).stdout;
    });
    assert.equal(process.env[HELD], undefined, "held 进程自身标记应已删(标记只活一代)");
    const grandEnv = JSON.parse(grandEnvRaw);
    assert.equal(grandEnv[HELD], undefined, "孙子进程 env 不应含 held 标记");
  } finally {
    if (prev !== undefined) process.env[HELD] = prev; // 恢复现场(进程内其他用例不受染)
    else delete process.env[HELD];
  }
});

// ── ⑦flock 起不来 ≠ 锁冲突(返工第3条,变异①靶):PATH 指空目录 → spawn flock ENOENT
//    → 立刻退出 3(ENVELOPE 运行期异常)+ stderr 报 flock,不当 16 也不空转等待额 ──
test("⑦flock 缺席:退出 3,stderr 报锁工具起不来,不当锁冲突 16", async () => {
  const emptyPath = fs.mkdtempSync(path.join(os.tmpdir(), "v2-dblock-noflock-"));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-dblock-tool-"));
  try {
    const p = await new Promise((resolve) => {
      const c = spawn(process.execPath, [RUN_HEALTH, "--db", path.join(tmp, "s.sqlite")],
        { env: { ...process.env, PATH: emptyPath }, cwd: path.resolve(HERE, "..") }); // PATH=空目录:flock 解析不到;node 本体用绝对路径不受染
      let err = "";
      c.stderr.on("data", (d) => (err += d));
      c.on("close", (code) => resolve({ code, err }));
    });
    assert.equal(p.code, 3, `flock 缺席应退出 3(ENVELOPE 运行期异常),实得 ${p.code}:\n${p.err}`);
    assert.match(p.err, /锁工具 flock 起不来/, "stderr 报锁工具故障(报对原因,不装锁冲突)");
    assert.doesNotMatch(p.err, /拒绝跑轮/, "不得走锁冲突 16 出口");
  } finally { fs.rmSync(emptyPath, { recursive: true, force: true }); fs.rmSync(tmp, { recursive: true, force: true }); }
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
