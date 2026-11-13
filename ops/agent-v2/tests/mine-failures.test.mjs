// mine-failures.test.mjs — #346 分析师工件红绿面:失败矿掘器(add-domain/mine-failures.mjs)。
// 契约 = 票 #346:输入 sweep 目录(dev/add-bench/sweeps/<名>/,布局 <题>/r<k>/<题>/trial.json
// ——dev/add-bench/sweep.mjs 一次性件的落件形状),输出分题失败测试函数计数 + 三失败
// 层位分类 + 跨题 Top 汇总;提案者工作技能(bench/add-domain/SKILL.md)的第一输入。
// 层位序(#346 票面):verify-gate(轮 failed + freshness 门面)> collection-error
// (摘要 ModuleNotFoundError/ImportError/cannot import)> behavior(FAILED 行)——
// VERIFY 红轮的模块缺席是门的下游后果,归层 ① 不归层 ②(graded-baseline-2 判例:
// 结构死题轮照打分,沙箱剥净=确定性 0)。
// 测试面全合成(题名 demo_*,非考题名);真 graded-baseline-2 对拍在票验收(报告贴段)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

import { classifyTrial, parseFailedFns, mineSweepDir } from "../bench/add-domain/mine-failures.mjs";

// fixture:合成 sweep 目录(布局同 dev/add-bench/sweep.mjs:<题>/r<k>/<题>/trial.json)
function makeFixture() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mine-failures-"));
  const mk = (q, run, trial) => {
    const d = path.join(tmp, q, run, q);
    fs.mkdirSync(d, { recursive: true });
    if (trial !== null) fs.writeFileSync(path.join(d, "trial.json"), JSON.stringify(trial));
  };
  const completed = (q, score) => ({
    ok: false, name: q, roundId: `demo-${q}`, round: { status: "completed" },
    leak: { ok: true, hits: [] }, score,
  });
  const gateRed = (q) => ({
    ok: false, name: q, roundId: `demo-${q}`,
    round: { status: "failed", error: { message: "GATE:VERIFY:鲜活度门:无活性证据(直接探活无 last-modified、家族 release/commits 证据未取得;无证据即无话,fail-closed)", detail: { code: "freshness_gate", stage: "VERIFY" } } },
    leak: { ok: true, hits: [] },
    score: { pass: 0, frac: 0, passed_fns: 0, total_fns: 6, summary: "tests/sources/test_demo_gate.py:12: in <module>\nE   ModuleNotFoundError: No module named 'ipdb._sources.demo_gate'\n=== 1 error in 0.07s ===" },
  });
  const importErr = (q) => completed(q, {
    pass: 0, frac: 0, passed_fns: 0, total_fns: 2,
    summary: "tests/sources/test_demo_import.py:1: in <module>\nE   ImportError: cannot import name 'DemoImportSource' from 'ipdb._sources.demo_import'\n=== 1 error in 0.07s ===",
  });
  const behavior = (q, fns) => completed(q, {
    pass: 0, frac: 0.4, passed_fns: 2, total_fns: 5,
    summary: `${fns.map((f) => `FAILED tests/sources/test_${q}.py::${f}`).join("\n")}\nFAILED tests/sources/test_${q}.py::${fns[0]} - assert False\nE   AssertionError: assert not [{...}]\n=== ${fns.length} failed, 2 passed in 0.01s ===`,
  });
  const passed = (q) => ({ ...completed(q, { pass: 1, frac: 1, passed_fns: 3, total_fns: 3, summary: "=== 3 passed in 0.01s ===" }), ok: true });

  // 题一 behavior:两次行为断言红(r1/r2)+ 一次 trial.json 缺席(r3,轮崩溃面)
  mk("demo_behavior", "r1", behavior("demo_behavior", ["test_alpha_row_shape", "test_alpha_dirty_row_dropped"]));
  mk("demo_behavior", "r2", behavior("demo_behavior", ["test_alpha_row_shape"]));
  mk("demo_behavior", "r3", null); // 目录在、trial.json 缺
  // 题二 verify-gate:三次 freshness 门红(摘要含 ModuleNotFoundError 但归层 ①)
  mk("demo_gate", "r1", gateRed("demo_gate"));
  mk("demo_gate", "r2", gateRed("demo_gate"));
  mk("demo_gate", "r3", gateRed("demo_gate"));
  // 题三 collection-error ×2 + 全绿 ×1
  mk("demo_import", "r1", importErr("demo_import"));
  mk("demo_import", "r2", passed("demo_import"));
  mk("demo_import", "r3", importErr("demo_import"));
  // 题四 leak 红:轮 completed、分数面挂、leak 命中(泄漏候选作废面)
  mk("demo_leak", "r1", {
    ok: false, name: "demo_leak", roundId: "demo-demo_leak", round: { status: "completed" },
    leak: { ok: false, hits: [{ source: "demo_leak_needle", kind: "name", needle: "demoleakneedle" }] },
    score: { pass: 0, frac: 0, passed_fns: 0, total_fns: 1, summary: "=== 1 failed, 0 passed in 0.01s ===" },
  });
  // 噪音目录(无 r<k> 子目录):非 run 布局,不入题面
  fs.mkdirSync(path.join(tmp, "zz_notes"), { recursive: true });
  return tmp;
}

test("parseFailedFns:FAILED 行取函数 id,同行「- assert」后缀剥掉,重复去重(宁少算)", () => {
  const s = [
    "FAILED tests/sources/test_demo.py::test_a_row_shape",
    "FAILED tests/sources/test_demo.py::test_a_row_shape - assert False",
    "FAILED tests/sources/test_demo.py::test_b_dirty_row_dropped - AssertionError: assert 0",
    "=== 2 failed, 3 passed in 0.01s ===",
  ].join("\n");
  assert.deepEqual(parseFailedFns(s), [
    "tests/sources/test_demo.py::test_a_row_shape",
    "tests/sources/test_demo.py::test_b_dirty_row_dropped",
  ]);
  assert.deepEqual(parseFailedFns(""), []);
  assert.deepEqual(parseFailedFns(undefined), []);
});

test("classifyTrial:verify-gate 层位序最高——轮 failed+freshness 门面压过摘要里的 ModuleNotFoundError", () => {
  const r = classifyTrial({
    ok: false,
    round: { status: "failed", error: { message: "GATE:VERIFY:鲜活度门:无活性证据", detail: { code: "freshness_gate", stage: "VERIFY" } } },
    score: { summary: "E   ModuleNotFoundError: No module named 'ipdb._sources.demo_gate'" },
  });
  assert.equal(r.layer, "verify-gate");
  assert.equal(r.reason, "freshness_gate");
});

test("classifyTrial:completed+摘要导入错=collection-error;FAILED 行=behavior;ok 轮=pass;leak 红=leak", () => {
  assert.equal(classifyTrial({
    ok: false, round: { status: "completed" },
    score: { summary: "ImportError: cannot import name 'X' from 'ipdb._sources.demo'" },
  }).layer, "collection-error");
  assert.equal(classifyTrial({
    ok: false, round: { status: "completed" },
    score: { summary: "FAILED tests/sources/test_demo.py::test_a\n=== 1 failed, 1 passed ===" },
  }).layer, "behavior");
  assert.equal(classifyTrial({
    ok: true, round: { status: "completed" }, leak: { ok: true },
    score: { pass: 1, frac: 1, summary: "=== 3 passed ===" },
  }).layer, "pass");
  assert.equal(classifyTrial({
    ok: false, round: { status: "completed" }, leak: { ok: false, hits: [{}] },
    score: { summary: "=== 1 failed, 0 passed ===" },
  }).layer, "leak");
  // 轮 failed 非 freshness(如 model_face)→ other 兜底不静默丢
  assert.equal(classifyTrial({
    ok: false, round: { status: "failed", error: { message: "GATE:IMPLEMENT:模型面红", detail: { code: "model_face" } } },
    score: { summary: "" },
  }).layer, "other");
});

test("mineSweepDir:分题层位计数 + 失败函数计数 + 跨题 Top + 缺席 trial.json 不静默丢", () => {
  const tmp = makeFixture();
  const r = mineSweepDir(tmp);
  assert.equal(r.sweep, path.basename(tmp));
  assert.equal(r.questions, 4);
  assert.equal(r.runs, 10);
  // 层位总量:behavior 2(r1/r2)+ gate 3 + collection 2 + pass 1 + leak 1 + other 1(缺席)
  assert.deepEqual(r.layerTotals, { "verify-gate": 3, "collection-error": 2, behavior: 2, pass: 1, leak: 1, other: 1 });
  const by = Object.fromEntries(r.perQuestion.map((q) => [q.name, q]));
  // 题一:r3 trial.json 缺席 → other 留痕;失败函数计数 r1 两函数各 1、r2 一函数再 +1
  assert.deepEqual(by.demo_behavior.layerCounts, { behavior: 2, other: 1 });
  assert.equal(by.demo_behavior.failedFnCounts[0][0], "tests/sources/test_demo_behavior.py::test_alpha_row_shape");
  assert.equal(by.demo_behavior.failedFnCounts[0][1], 2);
  assert.equal(by.demo_behavior.failedFnCounts[1][1], 1);
  assert.equal(by.demo_behavior.runs.find((x) => x.run === "r3").reason.includes("缺席"), true);
  // 题二:三次全归 verify-gate(不误报 collection-error)
  assert.deepEqual(by.demo_gate.layerCounts, { "verify-gate": 3 });
  // 题三:2 错 1 绿;均分 = (0+1+0)/3
  assert.deepEqual(by.demo_import.layerCounts, { "collection-error": 2, pass: 1 });
  assert.ok(Math.abs(by.demo_import.meanFrac - 1 / 3) < 1e-9);
  // 跨题 Top:alpha_row_shape 2 次居首,题归属记录在列
  assert.equal(r.topFailedFns[0][0], "tests/sources/test_demo_behavior.py::test_alpha_row_shape");
  assert.equal(r.topFailedFns[0][1], 2);
  assert.deepEqual(r.topFailedFns[0][2], ["demo_behavior"]);
});

test("mineSweepDir:目录不存在 throw(用法错);坏 JSON → other 留痕不炸", () => {
  assert.throws(() => mineSweepDir("/nonexistent-sweep-dir-346"), /sweep 目录不存在/);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mine-failures-bad-"));
  fs.mkdirSync(path.join(tmp, "demo_bad", "r1", "demo_bad"), { recursive: true });
  fs.writeFileSync(path.join(tmp, "demo_bad", "r1", "demo_bad", "trial.json"), "{not json");
  const r = mineSweepDir(tmp);
  assert.equal(r.layerTotals.other, 1);
  assert.ok(r.perQuestion[0].runs[0].reason.includes("不可解析"));
});

test("CLI:node mine-failures.mjs <sweepDir> 出文本报告 exit 0;--json 可解析且层位同", () => {
  const tmp = makeFixture();
  const here = path.resolve(import.meta.dirname, "..", "bench", "add-domain", "mine-failures.mjs");
  const text = execFileSync(process.execPath, [here, tmp], { encoding: "utf8" });
  assert.ok(text.includes("demo_behavior"));
  assert.ok(text.includes("verify-gate"));
  assert.ok(text.includes("collection-error"));
  assert.ok(text.includes("behavior"));
  assert.ok(text.includes("缺席"));
  const json = JSON.parse(execFileSync(process.execPath, [here, tmp, "--json"], { encoding: "utf8" }));
  assert.equal(json.questions, 4);
  assert.equal(json.layerTotals["verify-gate"], 3);
  // 用法错 exit 2
  let code = 0;
  try { execFileSync(process.execPath, [here], { encoding: "utf8" }); } catch (e) { code = e.status; }
  assert.equal(code, 2);
});
