// discover-round.test.mjs — 发现轮任务化测试面(票 #227 T3)。
// 面:①replay 声明闭集表 ②全链 faux 轮(信封+工件+队列行+门全绿+台账行)
// ③同 id 重跑=bad_round(旧律) ④breaker 五通道写侧随迁(失败 verdict 落盘)
// ⑤相位头 SIGKILL 崩溃→同库 resume 续跑(相位边界恢复点;faux 零网络零花费)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { runDiscoverRound } from "../run-discover.mjs";
import { DISCOVERY_REPLAY, ensureRoundHost, roundHosts, executeDiscoveryTool } from "../tools/discovery-tools.mjs";
import { breakerFileOf } from "../../agent/pipeline/discovery-host.mjs";
import { parseBreakerState } from "../../agent/tools/breaker.mjs";

const execFile = promisify(execFileCb);
const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES = path.resolve(HERE, "..", "agent", "fixtures", "pipeline");
const ROUND = "2026-06-01-0400-discover";

function tmpTree(prefix) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  return { tmp, docsRoot: path.join(tmp, "docs"), opsRoot: path.join(tmp, "docs", "ops") };
}

async function runRound(tree, db) {
  // 任务侧 env=process.env 现读(旧律,buildCtx 注);in-proc 测试须同步设进程环境(于 finally 还原)。
  const keys = ["DOCS_ROOT", "LEDGER_FILE"];
  const saved = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  process.env.DOCS_ROOT = tree.docsRoot;
  process.env.LEDGER_FILE = path.join(tree.opsRoot, "ledger.md");
  try {
    return await runDiscoverRound({
      roundId: ROUND,
      fixturesDir: FIXTURES,
      dbPath: db ?? path.join(tree.tmp, "v2.sqlite"),
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

test("replay 声明闭集表(重查询 unsafe/纯读 safe;与 tools/discovery-tools.mjs 注释单源)", () => {
  assert.deepEqual(DISCOVERY_REPLAY, { web_read: "safe", web_search: "unsafe", rss_parse: "safe" });
});

test("全链 faux 轮:信封 ok + 六步工件 + PROPOSE 队列行 + 门全绿 + 台账行", async () => {
  const tree = tmpTree("v2-disc-full-");
  const r = await runRound(tree);
  assert.equal(r.status, "completed", JSON.stringify(r));
  const env = r.envelope;
  assert.equal(env.ok, true);
  assert.deepEqual(Object.keys(env).sort(), ["ok", "pipeline", "pkg", "queue_writes", "round", "usage", "verify"].sort());
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"]);
  // usage 求和律(旧 pipeline_ok 断言面):各步 usage 之和 == 信封 usage(脚本步 null 不回声)
  const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
  for (const s of env.pipeline.stages) if (s.usage) for (const k of Object.keys(sum)) sum[k] += s.usage[k];
  assert.deepEqual(sum, env.usage);
  const dir = path.join(tree.opsRoot, "rounds", ROUND);
  for (const f of ["d1-scan.json", "d2-shortlist.json", "d2-shortlist-transcript.jsonl", "d3-measure.json", "d4-enqueue.json", "09-budget.json", "gates.json", "state.json"])
    assert.ok(fs.existsSync(path.join(dir, f)), `工件缺:${f}`);
  const gates = JSON.parse(fs.readFileSync(path.join(dir, "gates.json"), "utf8"));
  assert.deepEqual(gates.records.map((x) => [x.stage, x.pass]).filter(([s]) => s !== "RETRO" || true).length >= 6, true);
  for (const rec of gates.records) assert.equal(rec.pass, true, `${rec.stage} 门红:${rec.reason}`);
  const queue = fs.readFileSync(path.join(tree.opsRoot, "queue.md"), "utf8");
  assert.match(queue, /\| 2026-06-01-0400-discover \| PROPOSE \| rdns \|/, "PROPOSE 队列行缺失");
  const budget = JSON.parse(fs.readFileSync(path.join(dir, "09-budget.json"), "utf8"));
  assert.equal(budget.readings.discover_channels.channels.web_read.calls, 1);
  const ledger = fs.readFileSync(path.join(tree.opsRoot, "ledger.md"), "utf8");
  assert.match(ledger, /pipeline-discover:2026-06-01-0400-discover/, "台账轮次行缺失");
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});

test("同库同轮重放=复用任务零双写;跨库新任务撞轮目录=bad_round(旧律 ops 树守卫)", async () => {
  const tree = tmpTree("v2-disc-badround-");
  const db = path.join(tree.tmp, "v2.sqlite");
  const first = await runRound(tree, db);
  assert.equal(first.status, "completed");
  // 同库重跑(v2 幂等键律):复用终态任务重放,零新建零追加台账(旧「同 id 走 replay」的 v2 等价)
  const again = await runRound(tree, db);
  assert.equal(again.status, "completed");
  assert.equal(again.taskId, first.taskId, "同库同轮应复用任务而非新建");
  const ledger = fs.readFileSync(path.join(tree.opsRoot, "ledger.md"), "utf8");
  assert.equal((ledger.match(/pipeline-discover:2026-06-01-0400-discover/g) ?? []).length, 1, "重放不得双记台账");
  // 跨库新任务(另一 db,同 ops 树):建轮守卫拦截 bad_round(异物任务撞已有轮目录)
  const foreign = await runRound(tree, path.join(tree.tmp, "v2-foreign.sqlite"));
  assert.equal(foreign.status, "failed");
  assert.match(foreign.error.message, /已存在/);
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});

test("breaker 写侧随迁:失败 verdict 经宿主适配器落 breaker.json(通道计数+consec)", async () => {
  // 直调宿主核(与 defineTool execute 同入口):罐装 ok:false 读数 → 旧律 breaker.record
  // → breaker.json 落盘(成功 verdict 在闭路零 consec 时零写=回声律,见 breaker.mjs applyResult)。
  const tree = tmpTree("v2-disc-breaker-");
  fs.mkdirSync(tree.opsRoot, { recursive: true });
  const dir = path.join(tree.opsRoot, "rounds", ROUND);
  fs.mkdirSync(dir, { recursive: true });
  const ctx = {
    dir, opsRoot: tree.opsRoot, roundId: ROUND, env: { DOCS_ROOT: tree.docsRoot },
    log: () => {}, modelFace: "faux", fixturesDir: FIXTURES,
    budgetKnobs: { dupCallLimit: 3 }, breakerKnobs: undefined, ledgerFile: path.join(tree.opsRoot, "ledger.md"),
  };
  const host = ensureRoundHost(ctx, "conv-test-breaker");
  // 罐装计数码失败面(breaker.mjs BREAKER_COUNTED_CODES=channel_auth/channel_missing/quota;
  // io_error 非计数码不改态——旧律):临时 fixtures 只罐 ok:false code=quota 行。
  const fxDir = path.join(tree.tmp, "fixtures");
  fs.mkdirSync(fxDir, { recursive: true });
  fs.writeFileSync(path.join(fxDir, "measure.json"), JSON.stringify({ web_reads: [{ url: "https://quota.invalid/x", ok: false, code: "quota", reason: "罐装配额失败面" }] }));
  ctx.fixturesDir = fxDir;
  const host2 = ensureRoundHost({ ...ctx, discoverHost: undefined, dupRegistry: new Map() }, "conv-test-breaker2");
  const r = await executeDiscoveryTool(host2, "web_read", "measure-99", { url: "https://quota.invalid/x" });
  assert.equal(r.structuredContent.ok, false);
  assert.equal(r.structuredContent.code, "quota");
  const st = parseBreakerState(fs.readFileSync(breakerFileOf(ctx), "utf8"));
  assert.equal(st.channels.web_read.state, "closed");
  assert.equal(st.channels.web_read.consec, 1, "quota=计数码失败,consec 应 1(写侧随迁实证)");
  roundHosts.clear();
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});

test("相位头 SIGKILL 崩溃 → 同库 resume 续跑到 CLOSE(相位边界恢复点+startedAtIso 续算)", async () => {
  const tree = tmpTree("v2-disc-crash-");
  const db = path.join(tree.tmp, "v2.sqlite");
  const env = { ...process.env, DOCS_ROOT: tree.docsRoot, LEDGER_FILE: path.join(tree.opsRoot, "ledger.md"), OPS_V2_CRASH_AFTER_PHASE: "shortlist" };
  const kill = await execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ROUND, "--fixtures", FIXTURES, "--db", db], { env }).catch((e) => e.code);
  assert.equal(kill, null, `SIGKILL 期望进程被杀(exit code ${kill} 非自杀)`);
  assert.ok(fs.existsSync(path.join(tree.opsRoot, "rounds", ROUND, "d1-scan.json")), "scan 工件应先于崩溃落盘");
  delete env.OPS_V2_CRASH_AFTER_PHASE;
  const { stdout } = await execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ROUND, "--fixtures", FIXTURES, "--db", db], { env });
  const line = stdout.trim().split("\n").filter((l) => l.startsWith("{")).pop();
  const r = JSON.parse(line);
  assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
  assert.deepEqual(r.envelope.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"], "恢复后每步恰一次");
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});
