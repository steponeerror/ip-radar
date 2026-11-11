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

import { scoreRuns, scoreQuestion, renderMarkdown } from "../bench/add-domain/score.mjs";

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
  // 钥匙装回:真测试文件已拷入沙箱原位
  assert.ok(fs.existsSync(path.join(sandbox, "backend", "tests", "sources", "test_q2.py")));
  const ok = scoreQuestion({ name: "q1", sandbox: path.join(fx.runDir, "q1", "sandbox"), repo: fx.repo, python: fx.stub, timeoutMs: 30000 });
  assert.equal(ok.pass, 1);
  assert.equal(ok.summary, "");
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
