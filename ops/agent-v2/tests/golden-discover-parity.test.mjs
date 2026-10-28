// golden-discover-parity.test.mjs — golden 对拍通道(票 #227 T3;ops/agent/golden/cases.json
// 发现轮管线例 pipeline_discover_full_faux):旧引擎(ops/agent/pipeline.mjs runPipeline,
// in-proc)vs 新任务面(ops/agent-v2 run-discover.mjs,子进程)逐工件 diff 清单。
// 达标律(票面):通道通+失败可读,不强求全绿——本测试硬断言=两侧都跑出轮终态+核心工件
// (d1/d3/d4/gates/queue 行)逐字节等价;已知差异面(09-budget env 快照/state 镜像/信封
// resumed 字段)以清单打印,人工对拍入报告。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);
const V2 = path.resolve(import.meta.dirname, "..");
const ROUND = "2026-06-01-0400-discover";
const FIXTURES = path.resolve(V2, "..", "agent", "fixtures", "pipeline");

test("golden 对拍 pipeline_discover_full_faux:旧 runPipeline vs v2 发现轮任务,逐工件 diff 清单", async () => {
  const tmpA = fs.mkdtempSync(path.join(os.tmpdir(), "v2-parity-old-"));
  const tmpB = fs.mkdtempSync(path.join(os.tmpdir(), "v2-parity-new-"));
  const envA = { ...process.env, DOCS_ROOT: path.join(tmpA, "docs"), LEDGER_FILE: path.join(tmpA, "docs", "ops", "ledger.md") };
  const envB = { ...process.env, DOCS_ROOT: path.join(tmpB, "docs"), LEDGER_FILE: path.join(tmpB, "docs", "ops", "ledger.md") };
  fs.mkdirSync(path.join(envA.DOCS_ROOT, "ops", "rules"), { recursive: true });
  fs.writeFileSync(path.join(envA.DOCS_ROOT, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [] }, null, 2) + "\n"); // golden 例抑制规则库 fixture(run-golden.mjs 同设)
  fs.mkdirSync(path.join(envB.DOCS_ROOT, "ops", "rules"), { recursive: true });
  fs.writeFileSync(path.join(envB.DOCS_ROOT, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [] }, null, 2) + "\n");

  // —— 旧侧:in-proc runPipeline(旧 golden runner 同调法;env 先于 import)——
  const saved = { DOCS_ROOT: process.env.DOCS_ROOT, LEDGER_FILE: process.env.LEDGER_FILE };
  Object.assign(process.env, { DOCS_ROOT: envA.DOCS_ROOT, LEDGER_FILE: envA.LEDGER_FILE });
  let oldEnv = null;
  try {
    const { runPipeline } = await import("../../agent/pipeline.mjs");
    const r = await runPipeline({ type: "discover", roundId: ROUND, fixturesDir: FIXTURES,
      stdout: { write: () => true }, stderr: { write: () => true } });
    oldEnv = r?.envelope ?? null;
  } finally {
    for (const k of Object.keys(saved)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
  assert.ok(oldEnv?.ok, `旧引擎例应跑出 ok 信封(通道通前提):${JSON.stringify(oldEnv)?.slice(0, 200)}`);

  // —— 新侧:子进程 run-discover.mjs(相位任务面,隔离进程环境)——
  const { stdout } = await execFile(process.execPath, [path.join(V2, "run-discover.mjs"), ROUND,
    "--fixtures", FIXTURES, "--db", path.join(tmpB, "v2.sqlite")], { env: envB });
  const newR = JSON.parse(stdout.trim().split("\n").filter((l) => l.startsWith("{")).pop());
  assert.equal(newR.status, "completed", `v2 例应终态 completed(失败面可读):${JSON.stringify(newR.error ?? newR).slice(0, 300)}`);
  const newEnv = newR.envelope;

  // —— 逐工件 diff 清单(核心面硬断言等价;观察面打印留报告)——
  const dirA = path.join(envA.DOCS_ROOT, "ops", "rounds", ROUND);
  const dirB = path.join(envB.DOCS_ROOT, "ops", "rounds", ROUND);
  const read = (d, f) => { try { return fs.readFileSync(path.join(d, f), "utf8"); } catch { return null; } };
  const rows = [];
  // 归一化:时间戳/dur_ms/路径(tmp 树)/usage 数值(模型自报口径异:旧=事件流,新=UsageDoc
  // 含 cacheWrite)/门 reason 中信封字节数——已知非语义面,归一后比;归一仍异才 DIFF。
  const norm = (s) => (s === null ? null : s
    .replace(/"(generated_at|updated_at|started_at|ended_at)":\s*"[^"]*"/g, '"$1": "T"')
    .replace(/"dur_ms":\s*\d+/g, '"dur_ms": 0')
    .replace(/"wall_s":\s*[\d.]+/g, '"wall_s": 0')
    .replace(/\d+ 字节/g, "N 字节")
    .replace(/\/tmp\/[A-Za-z0-9_.-]+/g, "/tmp/T")
    .replace(/"(input|output|totalTokens)":\s*\d+/g, '"$1": N')
    .replace(/"api":"[^"]*"/g, "")
    .replace(/,"(provider|model|timestamp)":[^,}]+/g, "")
    .replace(/,"durationMs":\d+/g, "")
    .replace(/,"usage":\{[^}]*\}/g, ""));
  const cmpText = (label, file, { core = false } = {}) => {
    const a = norm(read(dirA, file)), b = norm(read(dirB, file));
    const same = a !== null && b !== null && a === b;
    rows.push(`${same ? "SAME" : "DIFF"} ${label}${same ? "" : a === null ? "(旧缺)" : b === null ? "(新缺)" : "(内容异)"}`);
    if (core) assert.ok(same, `核心工件 ${file} 新旧不等价`);
    return same;
  };
  cmpText("d1-scan.json", "d1-scan.json", { core: true });
  cmpText("d2-shortlist.json", "d2-shortlist.json", { core: true });
  cmpText("d3-measure.json", "d3-measure.json", { core: true });
  cmpText("d4-enqueue.json", "d4-enqueue.json", { core: true });
  cmpText("gates.json", "gates.json", { core: true });
  cmpText("d2-transcript", "d2-shortlist-transcript.jsonl"); // 观察面:input/seed 行应同;message 行=pi 内核封装差异可能
  cmpText("09-budget.json", "09-budget.json"); // 观察面:usage 来源=UsageDoc 活和 vs 旧事件流累计;env 快照同环境应近
  cmpText("state.json", "state.json"); // v2 降级镜像(checkpoint 真源):stages/updated_at 异=预期
  // 队列行(数据行等价;文件头模板行=写口首建差异容忍)
  const qA = (read(path.join(envA.DOCS_ROOT, "ops"), "queue.md") ?? "").split("\n").filter((l) => l.startsWith("|"));
  const qB = (read(path.join(envB.DOCS_ROOT, "ops"), "queue.md") ?? "").split("\n").filter((l) => l.startsWith("|"));
  const dataRows = (q) => q.filter((l) => !/日期|---/.test(l));
  rows.push(`${JSON.stringify(dataRows(qA)) === JSON.stringify(dataRows(qB)) ? "SAME" : "DIFF"} queue.md 数据行`);
  assert.deepEqual(dataRows(qB), dataRows(qA), "队列数据行新旧不等价");
  // 台账轮次行
  const lA = (read(path.join(envA.DOCS_ROOT, "ops"), "ledger.md") ?? "").split("\n").filter((l) => l.includes(`pipeline-discover:${ROUND}`));
  const lB = (read(path.join(envB.DOCS_ROOT, "ops"), "ledger.md") ?? "").split("\n").filter((l) => l.includes(`pipeline-discover:${ROUND}`));
  rows.push(`${lA.length === lB.length && lA[0]?.split("|").slice(0, 5).join("|") === lB[0]?.split("|").slice(0, 5).join("|") ? "SAME" : "DIFF"} ledger 轮次行(数值列 usage 源异可容,结构列等价)`);
  assert.equal(lB.length, 1, "v2 台账轮次行恰一(重放零双记)");
  // 信封形状
  assert.deepEqual(newEnv.pipeline.stages.map((s) => [s.name, s.status]), oldEnv.pipeline.stages.map((s) => [s.name, s.status]), "相位序列/状态不等价");
  rows.push(`DIFF envelope.resumed_from(v2 恒 null,恢复证据在 task record;T5 冻结面)`);
  rows.push(`DIFF envelope.usage(v2=UsageDoc 活和 ${JSON.stringify(newEnv.usage)};旧=事件流累计 ${JSON.stringify(oldEnv.usage)})`);
  console.log(`[golden-parity] pipeline_discover_full_faux 逐件清单:\n  ${rows.join("\n  ")}`);
  fs.rmSync(tmpA, { recursive: true, force: true });
  fs.rmSync(tmpB, { recursive: true, force: true });
});
