// bench-round.test.mjs — 重发现基准票 A(票 #318;spec docs/research/2026-11-07-rediscover-bench-spec.md
// §3.1/§8-A)测试面:bench 盲测轮 runner 复用 ops.discover-round 相位机,注入
// ①bench SCAN 变体(候选宇宙=仅 NEEDS.md 行,零注册表面)②相位截断到 SHORTLIST
// (MEASURE/ENQUEUE/RETRO 跳过,CLOSE 保留=usage/花费读数工件)③沙箱 opsRoot=
// dev/bench-rediscover/<roundId>/(台账/熔断/工件全进沙箱,绝不写真实 docs/ops/)。
// 全部 faux 面(零网络零花费,CI 可跑);真实模式零漂移由既有 golden 对拍面钉
// (golden-discover-parity/golden-smoke-gated 等,不在本文件)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { runBenchRound } from "../bench/run-bench.mjs";
import { benchScan } from "../bench/scan.mjs";

const execFile = promisify(execFileCb);
const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES = path.resolve(HERE, "..", "agent", "fixtures", "pipeline");
const ROUND = "2026-06-01-0500-discover";

function tmpTree(prefix) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  return { tmp, benchRoot: path.join(tmp, "bench-rediscover"), realDocs: path.join(tmp, "docs") };
}

// 真实树替身(env.DOCS_ROOT 指向):bench 轮后必须零触碰(沙箱隔离断言面)。
function benchEnv(tree) {
  return { ...process.env, DOCS_ROOT: tree.realDocs };
}

test("bench 全链 faux 轮:SCAN 零注册表面 + 相位截断 SCAN→SHORTLIST→CLOSE + 沙箱隔离", async () => {
  const tree = tmpTree("v2-bench-full-");
  try {
    const r = await runBenchRound({
      roundId: ROUND,
      fixturesDir: FIXTURES,
      benchRoot: tree.benchRoot,
      dbPath: path.join(tree.tmp, "bench.sqlite"),
      env: benchEnv(tree),
      stderr: { write: () => true },
    });
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    const env = r.envelope;
    assert.equal(env.ok, true, JSON.stringify(env));
    // 相位截断(票面②):三相位恰;MEASURE/ENQUEUE/RETRO 不在 stages。
    assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "CLOSE"]);
    // 产出含 usage/花费读数(信封 usage 面;CLOSE 的 09-budget.json 详读数见下)。
    for (const k of ["input", "output", "totalTokens", "cost"]) assert.ok(k in env.usage, `usage.${k} 缺席`);

    const opsRoot = path.join(tree.benchRoot, ROUND);
    const dir = path.join(opsRoot, "rounds", ROUND);
    assert.ok(fs.existsSync(dir), "沙箱轮目录缺席");
    // ①bench SCAN 变体:候选宇宙=仅 needs 行,零 source_registry/integrated 行;
    //   罐装宇宙(共享 fixture d1-scan.json 带 1 条 registry 行)也必须被滤成零。
    const scan = JSON.parse(fs.readFileSync(path.join(dir, "d1-scan.json"), "utf8"));
    assert.ok(scan.candidates.length > 0, "罐装 needs 行不应被滤空");
    for (const c of scan.candidates) {
      assert.equal(c.source_channel, "needs", `bench 候选 ${c.name} 须 needs 渠道`);
      assert.notEqual(c.status, "integrated", "bench 宇宙零 integrated 行");
      assert.match(c.evidence_ptr, /^NEEDS\.md:L\d+$/, "needs 行锚形");
    }
    assert.equal(scan.candidates.filter((c) => c.source_channel === "source_registry").length, 0, "零注册表面");
    assert.deepEqual(scan.candidates.map((c) => c.name), ["rDNS 主机名", "carrier / is_isp 出中国段"], "罐装 registry 行(feodo_tracker)须被滤除");
    assert.equal(scan.channels.registry.n, 0, "channels.registry.n=0(计数与实数自洽)");
    assert.equal(scan.channels.needs.n, scan.candidates.length);
    // SHORTLIST 工件(span 门在过滤后宇宙上照常过=罐装 quote 全挂 needs 行)。
    const short = JSON.parse(fs.readFileSync(path.join(dir, "d2-shortlist.json"), "utf8"));
    assert.equal(short.candidates.length, 2);
    // 相位截断工件面:d3/d4/queue/retro 全无(MEASURE/ENQUEUE/RETRO 未跑)。
    assert.equal(fs.existsSync(path.join(dir, "d3-measure.json")), false, "bench 轮不得产 d3-measure.json");
    assert.equal(fs.existsSync(path.join(dir, "d4-enqueue.json")), false, "bench 轮不得产 d4-enqueue.json");
    assert.equal(fs.existsSync(path.join(opsRoot, "queue.md")), false, "bench 轮不得写 queue.md");
    assert.equal(fs.existsSync(path.join(opsRoot, "retro", `${ROUND}.json`)), false, "bench 轮不得写 retro");
    // CLOSE 保留:09-budget.json 落沙箱(usage/花费/月度投影读数工件)。
    const budget = JSON.parse(fs.readFileSync(path.join(dir, "09-budget.json"), "utf8"));
    assert.ok(Number.isFinite(budget.readings.usage.cost), "花费读数缺席");
    assert.equal(budget.readings.model_calls, 1);
    // 门全绿恰三门。
    const gates = JSON.parse(fs.readFileSync(path.join(dir, "gates.json"), "utf8"));
    assert.equal(gates.records.length, 3, "恰三门留痕(SCAN/SHORTLIST/CLOSE)");
    for (const rec of gates.records) assert.equal(rec.pass, true, `${rec.stage} 门红:${rec.reason}`);
    // ③沙箱隔离:真实树替身零触碰(目录不得被建);台账=沙箱自有(成功轮零台账行,
    // 文件本身缺席=拒跑留痕/RETRO 台账/breaker 转移留痕全未发生)。
    assert.equal(fs.existsSync(tree.realDocs), false, "真实 docs 树被触碰(沙箱隔离破)");
    assert.equal(fs.existsSync(path.join(opsRoot, "ledger.md")), false, "faux 成功轮不应落台账行");
  } finally {
    fs.rmSync(tree.tmp, { recursive: true, force: true });
  }
});

test("benchScan 真面:repo NEEDS.md 解析 → 零 source_registry 行,行锚+text 原文面齐", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-bench-scan-"));
  const dir = path.join(tmp, "rounds", ROUND);
  fs.mkdirSync(dir, { recursive: true });
  try {
    const ctx = { dir, roundId: ROUND, modelFace: "real", fixturesDir: null };
    benchScan(ctx);
    const scan = JSON.parse(fs.readFileSync(path.join(dir, "d1-scan.json"), "utf8"));
    assert.equal(scan.round_id, ROUND);
    assert.ok(scan.candidates.length > 0, "真仓 NEEDS.md 有 open/候选 行");
    for (const c of scan.candidates) {
      assert.equal(c.source_channel, "needs");
      assert.ok(["open", "候选"].includes(c.status), "缺口行状态闭集");
      assert.match(c.evidence_ptr, /^NEEDS\.md:L\d+$/);
      assert.ok(typeof c.text === "string" && c.text.trim(), "text 原文面在场(span 门对账面)");
    }
    assert.equal(scan.candidates.filter((c) => c.source_channel === "source_registry").length, 0, "零注册表面");
    assert.equal(scan.channels.registry.n, 0);
    assert.equal(scan.channels.needs.n, scan.candidates.length);
    assert.equal(scan.channels.web.status, "placeholder", "web 渠道占位律(Q9:搜索职责在 SHORTLIST)");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("roundId 形状律沿用:bench 轮坏形状 → failed/bad_round(不触沙箱不开库)", async () => {
  const tree = tmpTree("v2-bench-shape-");
  try {
    const r = await runBenchRound({
      roundId: "not-a-round-id",
      fixturesDir: FIXTURES,
      benchRoot: tree.benchRoot,
      dbPath: path.join(tree.tmp, "bench.sqlite"),
      env: benchEnv(tree),
      stderr: { write: () => true },
    });
    assert.equal(r.status, "failed");
    assert.equal(r.error.code, "bad_round");
    assert.match(r.error.message, /YYYY-MM-DD-HHMM-discover/);
    assert.equal(fs.existsSync(tree.benchRoot), false, "坏形状轮不得建沙箱");
  } finally {
    fs.rmSync(tree.tmp, { recursive: true, force: true });
  }
});

test("CLI 冒烟(faux 零网络零花费):run-bench.mjs → exit 0 + 末行信封 ok:true + 沙箱落件", async () => {
  const tree = tmpTree("v2-bench-cli-");
  try {
    const { stdout } = await execFile(process.execPath, [
      path.join(HERE, "bench", "run-bench.mjs"), ROUND,
      "--fixtures", FIXTURES, "--bench-root", tree.benchRoot, "--db", path.join(tree.tmp, "bench.sqlite"),
    ], { env: benchEnv(tree) });
    const line = stdout.trim().split("\n").filter((l) => l.startsWith("{")).pop();
    const env = JSON.parse(line);
    assert.equal(env.ok, true, JSON.stringify(env));
    assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "CLOSE"]);
    assert.ok(fs.existsSync(path.join(tree.benchRoot, ROUND, "rounds", ROUND, "d2-shortlist.json")), "CLI 沙箱工件缺席");
    assert.equal(fs.existsSync(tree.realDocs), false, "CLI 面亦不得触碰真实 docs 树");
  } finally {
    fs.rmSync(tree.tmp, { recursive: true, force: true });
  }
});
