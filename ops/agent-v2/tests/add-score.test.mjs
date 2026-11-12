// add-score.test.mjs — #333 P2a 红绿面:真测试钥匙打分器(add-domain/score.mjs)。
// 契约 = spec §重实现基准协议「打分钥匙」:真逐源测试文件装回沙箱跑,过=1 不过=0,
// S = 通过源数/考题数;k 次重复出方差带;逐题报告含失败摘要。测试面零真 python——
// 解释器以 stub 脚本注入(退出码即分),真解释器姿势(主检出 venv 绝对路径 + cwd=
// 沙箱 backend/,AGENTS worktree 律)由端到端单题验证覆盖(票面交付项 4)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { scoreRuns, scoreQuestion, renderMarkdown, parsePytestTally } from "../bench/add-domain/score.mjs";

// fixture:repo 侧真测试文件(打分钥匙源)+ 两题 run 目录 + stub 解释器 + 冻结宇宙
function makeFixture() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "add-score-"));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "tests", "sources"), { recursive: true });
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", "test_q1.py"), "def test_q1():\n    assert True\n");
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", "test_q2.py"), "def test_q2():\n    assert False\n");
  const mkRun = (name) => fs.mkdirSync(path.join(tmp, "run1", name, "sandbox", "backend"), { recursive: true });
  mkRun("q1"); mkRun("q2");
  // stub 解释器:q1 过(退出 0),q2 挂(退出 1 + 固定失败输出)
  const stub = path.join(tmp, "py-stub.sh");
  fs.writeFileSync(stub, [
    "#!/bin/sh",
    'case "$*" in',
    "  *test_q1.py*) exit 0;;",
    "  *test_q2.py*) echo 'FAILED test_q2.py::test_q2 - assert False'; echo '=== 1 failed in 0.01s ==='; exit 1;;",
    "  *) echo 'unknown' >&2; exit 2;;",
    "esac",
  ].join("\n"));
  fs.chmodSync(stub, 0o755);
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    ...["q1", "q2"].map((n) => JSON.stringify({ split: "evolve", name: n, url: `https://${n}.example/f`, category: "threat", archetype: "Source", _why: "禁词引用:fixture" })),
  ].join("\n") + "\n");
  return { tmp, repo, stub, universePath, runDir: path.join(tmp, "run1") };
}

const common = (fx, over = {}) => ({
  runs: [fx.runDir], repo: fx.repo, python: fx.stub, universePath: fx.universePath, ...over,
});

test("scoreQuestion:钥匙装回 + 过=1/不过=0 + 失败摘要尾行", () => {
  const fx = makeFixture();
  const sandbox = path.join(fx.runDir, "q2", "sandbox");
  const r = scoreQuestion({ name: "q2", sandbox, repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(r.pass, 0);
  assert.ok(r.summary.includes("FAILED test_q2.py::test_q2"), `摘要须含失败行:${r.summary}`);
  // #343:纯挂面(旧 stub 装饰形摘要「=== 1 failed ===」)→ frac=0/1;计数入档
  assert.equal(r.frac, 0);
  assert.equal(r.passed_fns, 0);
  assert.equal(r.total_fns, 1);
  // 钥匙装回:真测试文件已拷入沙箱原位
  assert.ok(fs.existsSync(path.join(sandbox, "backend", "tests", "sources", "test_q2.py")));
  const ok = scoreQuestion({ name: "q1", sandbox: path.join(fx.runDir, "q1", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(ok.pass, 1);
  assert.equal(ok.summary, "");
  // #343:exit 0 = 全过,frac=1(stub 无摘要行 → 计数 null,不虚构)
  assert.equal(ok.frac, 1);
  assert.equal(ok.passed_fns, null);
  assert.equal(ok.total_fns, null);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreQuestion:超时 = 不过 0 + 摘要注明(stub sleep 压过 timeoutMs)", () => {
  const fx = makeFixture();
  const stub = path.join(fx.tmp, "py-slow.sh");
  fs.writeFileSync(stub, "#!/bin/sh\nsleep 5\nexit 0\n");
  fs.chmodSync(stub, 0o755);
  fs.mkdirSync(path.join(fx.runDir, "q1", "sandbox", "backend"), { recursive: true });
  const r = scoreQuestion({ name: "q1", sandbox: path.join(fx.runDir, "q1", "sandbox"), repo: fx.repo, python: stub, timeoutMs: 500 });
  assert.equal(r.pass, 0);
  assert.ok(r.summary.includes("超时"));
  // #343:超时面无摘要可解析 → 分子 0;collect-only fallback 同 stub 也被杀 → 分母 0
  assert.equal(r.frac, 0);
  assert.equal(r.total_fns, 0);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreRuns:S = 通过数/题数;k 次重复出方差带;逐题跨次计数", () => {
  const fx = makeFixture();
  const run2 = path.join(fx.tmp, "run2");
  fs.cpSync(fx.runDir, run2, { recursive: true });
  const res = scoreRuns(common(fx, { runs: [fx.runDir, run2] }));
  assert.equal(res.k, 2);
  assert.equal(res.runs.length, 2);
  for (const run of res.runs) {
    assert.equal(run.S, 0.5);
    assert.equal(run.questions.length, 2);
  }
  assert.equal(res.meanS, 0.5);
  assert.equal(res.stdevS, 0);
  assert.deepEqual(res.band, { minS: 0.5, maxS: 0.5 });
  const byName = Object.fromEntries(res.perQuestion.map((q) => [q.name, q.passes]));
  assert.deepEqual(byName, { q1: 2, q2: 0 });
  // 失败摘要留在逐题记录(打分后可见;盲测纪律 = 打分前不给)
  const q2 = res.runs[0].questions.find((q) => q.name === "q2");
  assert.ok(q2.summary.includes("FAILED test_q2.py::test_q2"));
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreRuns:判分确定(stub 输出确定 → 同输入双跑同 JSON)", () => {
  const fx = makeFixture();
  const a = JSON.stringify(scoreRuns(common(fx)));
  const b = JSON.stringify(scoreRuns(common(fx)));
  assert.equal(a, b);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreRuns:fail-closed——钥匙缺失/布局漂移/表外题均红", () => {
  const fx = makeFixture();
  // repo 无该题钥匙 → throw(无钥匙=打分面坏,不给静默零分)
  fs.rmSync(path.join(fx.repo, "backend", "tests", "sources", "test_q2.py"));
  assert.throws(() => scoreRuns(common(fx)), /test_q2\.py/);
  fs.writeFileSync(path.join(fx.repo, "backend", "tests", "sources", "test_q2.py"), "x");
  // 题目录缺 sandbox → throw(布局漂移:静默跳过会污染分母)
  fs.rmSync(path.join(fx.runDir, "q2", "sandbox"), { recursive: true, force: true });
  assert.throws(() => scoreRuns(common(fx)), /q2.*sandbox|sandbox.*q2/);
  // 表外题混入 run 目录 → throw(考题分母 = universe 单源);先补回 q2 sandbox 隔离前两断言的副作用
  fs.mkdirSync(path.join(fx.runDir, "q2", "sandbox", "backend"), { recursive: true });
  fs.mkdirSync(path.join(fx.runDir, "q9", "sandbox", "backend"), { recursive: true });
  assert.throws(() => scoreRuns(common(fx)), /q9/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreRuns:only 子集面——只考指定题(端到端单题验证面),表外 only 题红", () => {
  const fx = makeFixture();
  // 只考 q1:q2 无 sandbox 也合法(子集分母 = only 单源)
  fs.rmSync(path.join(fx.runDir, "q2"), { recursive: true, force: true });
  const res = scoreRuns(common(fx, { only: ["q1"] }));
  assert.equal(res.k, 1);
  assert.equal(res.runs[0].questions.length, 1);
  assert.equal(res.runs[0].questions[0].name, "q1");
  assert.equal(res.runs[0].S, 1);
  // only 名不在 universe → 红(子集仍须 universe 内)
  assert.throws(() => scoreRuns(common(fx, { only: ["q9"] })), /q9/);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("renderMarkdown:S/方差带/逐题表/失败摘要;无时间戳(双渲染字节同)", () => {
  const fx = makeFixture();
  const run2 = path.join(fx.tmp, "run2");
  fs.cpSync(fx.runDir, run2, { recursive: true });
  const res = scoreRuns(common(fx, { runs: [fx.runDir, run2] }));
  const md = renderMarkdown(res);
  assert.ok(md.includes("S = 0.5"));
  assert.ok(md.includes("k = 2"));
  assert.ok(md.includes("| q1 | 2/2 |"), `逐题表缺 q1 通过计数:${md.slice(0, 400)}`);
  assert.ok(md.includes("| q2 | 0/2 |"));
  assert.ok(md.includes("FAILED test_q2.py::test_q2"), "逐题失败摘要须入报表");
  assert.ok(!/\d{4}-\d{2}-\d{2}/.test(md), "报表不得含日期时间戳(确定性)");
  assert.equal(md, renderMarkdown(res));
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

// ── #343 分级钥匙:score_frac = passed/total 测试函数数 ──────────────────

test("parsePytestTally:摘要行计数——纯过/纯挂/混合/error 面/无测试;不可解析=null", () => {
  // 纯过(真实 -q 输出末行无装饰)
  assert.deepEqual(parsePytestTally("..F\n2 passed in 0.01s"), { failed: 0, passed: 2, errors: 0 });
  // 纯挂
  assert.deepEqual(parsePytestTally("3 failed in 0.10s"), { failed: 3, passed: 0, errors: 0 });
  // 混合(带 === 装饰形也须容)
  assert.deepEqual(parsePytestTally("=== 1 failed, 2 passed in 0.02s ==="), { failed: 1, passed: 2, errors: 0 });
  // setup error 面(error 如实入计)
  assert.deepEqual(parsePytestTally("1 failed, 1 passed, 1 error in 0.2s"), { failed: 1, passed: 1, errors: 1 });
  assert.deepEqual(parsePytestTally("2 errors in 0.3s"), { failed: 0, passed: 0, errors: 2 });
  // collection error 中断面(Interrupted;末行「1 error」/「no tests collected, 1 error」)
  assert.deepEqual(parsePytestTally("!!! Interrupted: 1 error during collection !!!\n1 error in 0.07s"), { failed: 0, passed: 0, errors: 1 });
  assert.deepEqual(parsePytestTally("no tests collected, 1 error in 0.08s"), { failed: 0, passed: 0, errors: 1 });
  // 无测试(exit 5 面)
  assert.deepEqual(parsePytestTally("no tests ran in 0.00s"), { failed: 0, passed: 0, errors: 0 });
  // skipped/xfail 族不入票面公式(M/(M+N) 字面)
  assert.deepEqual(parsePytestTally("2 passed, 1 skipped in 0.1s"), { failed: 0, passed: 2, errors: 0 });
  // 不可解析面:乱文/空 → null(fallback 分母的触发条件)
  assert.equal(parsePytestTally("hello world"), null);
  assert.equal(parsePytestTally(""), null);
  assert.equal(parsePytestTally(null), null);
});

// 分级面 fixture 工厂:stub 输出钉死 pytest 摘要行(真实 -q 末行形状,实验
// /tmp/g343-faces 2026-11-12 对拍)
function makeGradedFixture({ faceStub, repoFns = null }) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "add-score-frac-"));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "tests", "sources"), { recursive: true });
  for (const n of ["q1", "q2"]) fs.writeFileSync(path.join(repo, "backend", "tests", "sources", `test_${n}.py`), "def test_x():\n    assert True\n");
  const mkRun = (name) => fs.mkdirSync(path.join(tmp, "run1", name, "sandbox", "backend"), { recursive: true });
  mkRun("q1"); mkRun("q2");
  const log = path.join(tmp, "stub.log");
  const lines = ["#!/bin/sh", `echo "cwd=$PWD args=$*" >> ${JSON.stringify(log)}`];
  if (repoFns) {
    // collect-only 应答(repo 侧分母;parametrize 展开按项,与摘要行分子同口径):
    // 自带 case 块置前(匹配短序,防被按文件名匹配的 run 面吃掉)
    lines.push(
      `case "$*" in`,
      "  *--collect-only*)",
      ...repoFns.map((f) => `    echo 'tests/sources/test_q2.py::${f}'`),
      "    echo ''",
      "    echo 'N tests collected in 0.00s'",
      "    exit 0;;",
      "esac",
    );
  }
  lines.push(`case "$*" in`, ...faceStub, "  *) echo 'unknown' >&2; exit 2;;", "esac");
  const stub = path.join(tmp, "py-stub.sh");
  fs.writeFileSync(stub, lines.join("\n"));
  fs.chmodSync(stub, 0o755);
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    ...["q1", "q2"].map((n) => JSON.stringify({ split: "evolve", name: n, url: `https://${n}.example/f`, category: "threat", archetype: "Source", _why: "禁词引用:fixture" })),
  ].join("\n") + "\n");
  return { tmp, repo, stub, universePath, runDir: path.join(tmp, "run1"), log };
}

test("scoreQuestion 分级:纯过 frac=1(计数入档)/混合 frac=2/3/setup-error 面如实入分母", () => {
  // 纯过:exit 0 + 「3 passed」→ frac=1,passed_fns=3/total_fns=3
  let fx = makeGradedFixture({ faceStub: ["  *test_q1.py*) echo '3 passed in 0.01s'; exit 0;;"] });
  let r = scoreQuestion({ name: "q1", sandbox: path.join(fx.runDir, "q1", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(r.pass, 1);
  assert.equal(r.frac, 1);
  assert.equal(r.passed_fns, 3);
  assert.equal(r.total_fns, 3);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
  // 混合:exit 1 + 「1 failed, 2 passed」→ frac=2/3,pass=0
  fx = makeGradedFixture({ faceStub: ["  *test_q2.py*) echo '1 failed, 2 passed in 0.02s'; exit 1;;"] });
  r = scoreQuestion({ name: "q2", sandbox: path.join(fx.runDir, "q2", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(r.pass, 0);
  assert.equal(r.frac, 2 / 3);
  assert.equal(r.passed_fns, 2);
  assert.equal(r.total_fns, 3);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
  // setup error:exit 1 + 「1 failed, 1 passed, 1 error」→ 分母含 error 项 = 3
  fx = makeGradedFixture({ faceStub: ["  *test_q2.py*) echo '1 failed, 1 passed, 1 error in 0.2s'; exit 1;;"] });
  r = scoreQuestion({ name: "q2", sandbox: path.join(fx.runDir, "q2", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(r.frac, 1 / 3);
  assert.equal(r.total_fns, 3);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreQuestion 分级:collection error(exit 2 中断)→ 分子 0,分母 = repo 侧 --collect-only 数出的函数数", () => {
  const fx = makeGradedFixture({
    faceStub: ["  *test_q2.py*) echo 'ERROR tests/sources/test_q2.py - ModuleNotFoundError'; echo '!!! Interrupted: 1 error during collection !!!'; echo '1 error in 0.07s'; exit 2;;"],
    repoFns: ["test_a", "test_b", "test_c"],
  });
  const r = scoreQuestion({ name: "q2", sandbox: path.join(fx.runDir, "q2", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(r.pass, 0);
  assert.equal(r.frac, 0);
  assert.equal(r.passed_fns, 0);
  assert.equal(r.total_fns, 3, "分母 = collect-only 数出的 3 个测试函数");
  // fallback 调用面:collect-only 跑在 repo 侧 backend/(真钥匙+真实现在场,collection 必成)
  const log = fs.readFileSync(fx.log, "utf8");
  const calls = log.split("\n").filter(Boolean);
  assert.ok(calls.length >= 2, "打分跑 + collect-only fallback 两次调用");
  const collectCall = calls.find((c) => c.includes("--collect-only"));
  assert.ok(collectCall, `须有 --collect-only 调用:${log}`);
  assert.ok(collectCall.includes(`cwd=${path.join(fx.repo, "backend")}`), `collect-only 须跑在 repo 侧 backend/:${collectCall}`);
  assert.ok(collectCall.includes("tests/sources/test_q2.py"));
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

test("scoreRuns 分级聚合:逐 run meanFrac + 总 meanFrac + 逐题 frac 均分;renderMarkdown 出 frac 面", () => {
  // q1 纯过(frac=1)、q2 混合(frac=2/3)× 2 run:meanFrac=(1+2/3)/2=5/6
  const fx = makeGradedFixture({ faceStub: [
    "  *test_q1.py*) echo '2 passed in 0.01s'; exit 0;;",
    "  *test_q2.py*) echo '1 failed, 2 passed in 0.02s'; exit 1;;",
  ] });
  const run2 = path.join(fx.tmp, "run2");
  fs.cpSync(fx.runDir, run2, { recursive: true });
  const res = scoreRuns({ runs: [fx.runDir, run2], repo: fx.repo, python: fx.stub, universePath: fx.universePath });
  for (const run of res.runs) {
    assert.equal(run.S, 0.5, "score_pass 留档并存:S 不变");
    // 均分 =(1 + 2/3)/2:二进制浮点求和路径与字面 5/6 差 1ulp,epsilon 比对
    assert.ok(Math.abs(run.meanFrac - 5 / 6) < 1e-12, `meanFnc 期望 5/6,实得 ${run.meanFrac}`);
  }
  assert.ok(Math.abs(res.meanFrac - 5 / 6) < 1e-12);
  const q2 = res.perQuestion.find((q) => q.name === "q2");
  assert.equal(q2.passes, 0, "通过数副指标保留");
  assert.equal(q2.meanFrac, 2 / 3);
  const md = renderMarkdown(res);
  assert.ok(md.includes("frac = 0.8333"), `run 行须含 frac 均分:${md.slice(0, 500)}`);
  assert.ok(md.includes("| q2 | 0/2 | 0.6667 |"), `逐题表须含 frac 均分列:${md.slice(0, 600)}`);
  assert.ok(md.includes("| q1 | 2/2 | 1.0000 |"));
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});
