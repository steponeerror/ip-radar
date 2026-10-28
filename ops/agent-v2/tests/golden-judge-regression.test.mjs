// golden-judge-regression.test.mjs — legacy 判断器面回归钉(票 #232;口径裁决 A+C,父会话
// 2026-10-28)。cases.json 8 个判断器例(health_summary_format/discover_predicate_hit/
// discover_midround_search_citation/neg1-3/boundary×2)驱动的是 legacy agent.mjs runRound
// 回路(ToolHost+写前语义门+收口四件)——spec T3 明示该面不迁 v2(tools/discovery-tools.mjs
// 头注:fetch_url/gh_search 留 legacy 面),故本文件不是管线对拍,而是「v2 依赖世界
// (pi-durable@1.4.0 + ops/agent 双 node_modules 共存,scaffold 单实例钉)不破坏 legacy
// 判断器面」的回归钉:在 v2 测试套内子进程起 ops/agent/golden/run-golden.mjs(ops/agent
// 零改动),faux 层全 10 例(8 判断器 + 2 管线,= runner 缺省层)须 GOLDENPASS 全绿。
// 切流删旧时本钉随 legacy 面退役(SHADOW-RUNBOOK §SAME 门槛行同口径)。
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs";

const execFile = promisify(execFileCb);
const V2 = path.resolve(import.meta.dirname, "..");
const RUNNER = path.resolve(V2, "..", "agent", "golden", "run-golden.mjs");
const CASES = JSON.parse(fs.readFileSync(path.resolve(V2, "..", "agent", "golden", "cases.json"), "utf8")).cases;
const JUDGE_IDS = CASES.filter((c) => c.tier === "faux" && c.kind !== "pipeline").map((c) => c.id); // 8 判断器例(裁决口径)

test("legacy 判断器 8 例回归钉:判断器面断言词汇表外零漂移(run-golden.mjs --case 逐例 GOLDENPASS)", async () => {
  // 逐例子进程(= runner 自身隔离形态:DOCS_ROOT/PATH env 每例独立,零网络全 faux);
  // 8 例复用 runner 的世界置备/断言评估零复制——本钉只派生与判绿,不 fork 判断逻辑。
  for (const id of JUDGE_IDS) {
    let stdout = "";
    try {
      ({ stdout } = await execFile(process.execPath, [RUNNER, "--case", id], { timeout: 300_000, maxBuffer: 32 * 1024 * 1024 }));
    } catch (e) { // runner 非零退出时 execFile 先拒——捕获后仍走 match,让 GOLDENFAIL 明细面世(P2)
      stdout = e.stdout ?? String(e);
    }
    assert.match(stdout, new RegExp(`^GOLDENPASS ${id}$`, "m"), `判断器例 ${id} 未 GOLDENPASS:\n${stdout.slice(0, 800)}`);
  }
});

test("管线例判断面回归钉:faux 层全 10 例(8 判断器+2 管线)= runner 缺省层 PASS=10 FAIL=0", async () => {
  // 父进程模式逐例派生子进程(runner 缺省=faux 层;与上行互补:钉选层缺省恒 faux,
  // 防 smoke 层误进 CI——修正③判例面)。smoke 例零凭证零网络永不入本钉。
  const { stdout: sum } = await (async () => { try {
    return await execFile(process.execPath, [RUNNER], { timeout: 600_000, maxBuffer: 32 * 1024 * 1024 });
  } catch (e) { return { stdout: e.stdout ?? String(e) }; } })(); // 同上:非零退出时保 stdout 入断言消息(P2)
  assert.match(sum, /^golden: PASS=10 FAIL=0$/m, `faux 层非全绿:\n${sum.slice(-1200)}`);
});
