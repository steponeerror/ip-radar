// cron-launchers.test.mjs — cron 入口 CLI 冻结面(票 #229 T5 任务书①:exit 码表 0/1/2/3、
// 信封形状、stderr 进度行、幂等复用、toPhase 停笔、拒跑信封)。子进程真 CLI 面(spawn
// run-health.mjs),世界=shadow-diff seedWorld 导出面(判例+规则+01/02 前置工件+永败
// eval stub);CLOSE 面全链在此钉(shadow 对拍载具停笔 RETRO,CLOSE 同构由本测补)。
// run-discover.mjs 同律,其信封面已由 golden-discover-parity 测钉,此处不重复。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { seedWorld } from "../shadow-diff.mjs";

const HERE = import.meta.dirname;
const AGENT = path.resolve(HERE, "..", "..", "agent");
const FIXTURES = path.join(AGENT, "fixtures", "pipeline");
const today = new Date().toISOString().slice(0, 10);
// 测试用轮 id:同分钟+序数偏移(形状律 \d{4} 只验数字面,1870 等仍合法;字母后缀会进 HHMM 段违形状)
const rid = (n = 0) => { const d = new Date(); return `${today}-${String(d.getHours()).padStart(2, "0")}${String((d.getMinutes() + n) % 100).padStart(2, "0")}-health`; }; // 分钟位+n(mod 100),保 \d{4} 形状

function cli(args, world, extraEnv = {}) {
  return new Promise((resolve) => {
    const p = spawn("node", [path.join(HERE, "..", "run-health.mjs"), ...args],
      { env: { ...world.env, ...extraEnv }, cwd: path.resolve(HERE, "..", "..") });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => resolve({ code, out, err }));
  });
}
const lastLine = (s) => s.trimEnd().split("\n").at(-1);

test("run-health 全链:exit 0,stdout 末行=旧形成功信封,CLOSE 门在,gates 有 G_CLOSE", async () => {
  const id = rid();
  const w = seedWorld(id);
  try {
    // from-phase TRIAGE:零网络红线(PROBE/VERIFY=真探测面不可入测试;CLOSE 同构是本测目标)
    const r = await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite")], w);
    assert.equal(r.code, 0, `stderr:\n${r.err}`);
    const env = JSON.parse(lastLine(r.out));
    assert.equal(env.ok, true);
    assert.equal(env.round, "health");
    assert.deepEqual(Object.keys(env).sort(), ["ok", "pipeline", "pkg", "queue_writes", "round", "usage", "verify"].sort(), "健康成功信封键闭集(P2-⑩;ENVELOPE.md 冻结面)");
    assert.equal(env.pipeline.round_id, id);
    assert.ok(env.pipeline.stages.some((s) => s.name === "CLOSE"), "stages 含 CLOSE");
    assert.ok(env.usage && "cost" in env.usage, "信封带 usage.cost");
    assert.match(r.err, /\[v2-health\] round=/, "stderr 进度行");
    const gates = fs.readFileSync(path.join(w.roundDir, "gates.json"), "utf8");
    assert.match(gates, /G_CLOSE/, "gates.json 有 G_CLOSE");
    assert.ok(fs.existsSync(path.join(w.roundDir, "09-budget.json")), "09-budget.json 落件");
    assert.match(fs.readFileSync(path.join(w.ops, "ledger.md"), "utf8"), new RegExp(`\\| ${today} \\| health \\|`), "台账兼容行");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("run-health 幂等:同库同轮复用任务,二次运行零新建同信封", async () => {
  const id = rid(1);
  const w = seedWorld(id);
  try {
    const db = path.join(w.tmp, "s.sqlite");
    const r1 = await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", db], w);
    const r2 = await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", db], w);
    assert.equal(r1.code, 0); assert.equal(r2.code, 0);
    assert.match(r2.err, /复用任务/, "stderr 报复用");
    assert.equal(lastLine(r1.out), lastLine(r2.out), "两次信封逐字同");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("run-health --to-phase RETRO:停笔 RETRO,无 G_CLOSE/09-budget,台账行仍在", async () => {
  const id = rid(2);
  const w = seedWorld(id);
  try {
    const r = await cli([id, "--from-phase", "TRIAGE", "--to-phase", "RETRO", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite")], w);
    assert.equal(r.code, 0, `stderr:\n${r.err}`);
    const env = JSON.parse(lastLine(r.out));
    assert.equal(env.ok, true);
    assert.ok(!env.pipeline.stages.some((s) => s.name === "CLOSE"), "stages 止于 RETRO");
    const gates = fs.readFileSync(path.join(w.roundDir, "gates.json"), "utf8");
    assert.doesNotMatch(gates, /G_CLOSE/);
    assert.ok(!fs.existsSync(path.join(w.roundDir, "09-budget.json")));
    assert.match(fs.readFileSync(path.join(w.ops, "ledger.md"), "utf8"), new RegExp(`\\| ${today} \\| health \\|`), "RETRO 台账行");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("run-health 拒跑:月帽打满 → exit 1 + {ok:false,round:health,error.code=budget_monthly}", async () => {
  const id = rid(3);
  const w = seedWorld(id);
  try {
    fs.writeFileSync(path.join(w.ops, "ledger.md"),
      `| ${today} | health | faux-pipeline | in=1 out=1 total=2 cost=30.00000000 | pipeline:spent | test |\n`);
    const r = await cli([id, "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite")], w);
    assert.equal(r.code, 1);
    const env = JSON.parse(lastLine(r.out));
    assert.equal(env.ok, false);
    assert.equal(env.round, "health");
    assert.equal(env.error.code, "budget_monthly");
    assert.match(r.err, /\[admission\] budget_monthly refused/);
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("run-health 用法错:缺 roundId → exit 2;非法 toPhase → exit 2;非法 --model → exit 2", async () => {
  const w = seedWorld(rid(4));
  try {
    const r1 = await cli([], w);
    assert.equal(r1.code, 2);
    const r2 = await cli([rid(4), "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite"), "--to-phase", "NOPE"], w);
    assert.equal(r2.code, 2);
    const r3 = await cli([rid(4), "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite"), "--from-phase", "RETRO", "--to-phase", "TRIAGE"], w);
    assert.equal(r3.code, 2, "toPhase 早于 fromPhase 拒");
    const r4 = await cli([rid(4), "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite"), "--model", "noprovider"], w);
    assert.equal(r4.code, 2, "--model 缺 provider/modelId 斜杠拒");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("P0-④ 健康轮跨库撞轮目录:同轮 id 换新 db → exit 1 bad_round,台账不双写", async () => {
  const id = rid(6);
  const w = seedWorld(id);
  try {
    const r1 = await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s1.sqlite")], w);
    assert.equal(r1.code, 0, `首轮应成功:\n${r1.err}`);
    assert.ok(fs.existsSync(path.join(w.roundDir, ".v2-claim.json")), "认领件落轮目录");
    const r2 = await cli([id, "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s2.sqlite")], w); // 新库=新任务撞异主认领
    assert.equal(r2.code, 1);
    const env2 = JSON.parse(lastLine(r2.out));
    assert.equal(env2.error.code, "bad_round", `跨库撞轮须 bad_round:\n${r2.out}`);
    assert.match(env2.error.message, /认领/);
    const ledger = fs.readFileSync(path.join(w.ops, "ledger.md"), "utf8");
    assert.equal((ledger.match(/\| health \|/g) ?? []).length, 1, "拒轮不写台账,首轮一行不双写");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("P2-⑩ 运行期异常:--db 指不可写路径(父路径是文件)→ exit 3,stdout 零信封", async () => {
  const w = seedWorld(rid(7));
  try {
    fs.writeFileSync(path.join(w.tmp, "file-not-dir"), "x"); // 父路径是文件 → 开库 ENOTDIR → launcher 异常面
    const r = await cli([rid(7), "--from-phase", "TRIAGE", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "file-not-dir", "s.sqlite")], w);
    assert.equal(r.code, 3);
    assert.equal(r.out.trim(), "", "运行期异常不发 JSON 信封(ENVELOPE.md 码表:3=launcher 自身)");
    assert.ok(r.err.includes("Error"), "stderr 带栈");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("P2-5 轮 id 形状律:非 YYYY-MM-DD-HHMM-health → exit 1 bad_round(先于准入,note-9 序)", async () => {
  const w = seedWorld("x");
  try {
    const r = await cli(["2026-10-28-heath-typo", "--fixtures", FIXTURES, "--db", path.join(w.tmp, "s.sqlite")], w);
    assert.equal(r.code, 1);
    const env = JSON.parse(lastLine(r.out));
    assert.equal(env.error.code, "bad_round");
    assert.doesNotMatch(r.err, /\[admission\]/, "形状错不触发准入拒跑(序:校验先于准入)");
  } finally { fs.rmSync(w.tmp, { recursive: true, force: true }); }
});

test("P1-1 对拍闸门:双面皆败 → SIDE-FAILED 判 DIFF exit 1(不假 SAME)", async () => {
  // 评审员实证面:双面同因败(缺 fixtures)旧版 VERDICT SAME exit 0——闸门自身失败语义回归钉
  const r = await new Promise((resolve) => {
    const p = spawn("node", [path.join(HERE, "..", "shadow-diff.mjs"), rid(5), "--fixtures", "/tmp/definitely-missing-fixtures-t229"],
      { cwd: path.resolve(HERE, "..", "..") });
    let out = ""; p.stdout.on("data", (d) => (out += d)); p.on("error", (e) => resolve({ code: -1, out: String(e) })); p.on("close", (code) => resolve({ code, out }));
  });
  assert.equal(r.code, 1, `双面同因败不得 exit 0:\n${r.out}`);
  assert.match(r.out, /SIDE-FAILED/);
  assert.match(r.out, /VERDICT DIFF/);
});
