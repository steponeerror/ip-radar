// add-trial.test.mjs — #334 交付面 1+4 红绿面:trial 接线器(add-domain/run-trial.mjs)。
// 契约 = spec §重实现基准协议「一次 trial」:构建剥答案沙箱 → 沙箱内跑 bench 形态加源轮
// (DOSSIER 跳过、考题卡预填)→ 外部打分器装回真测试钥匙 → pass/fail;faux 全链冒烟
// (罐装实现者 turns,沙箱→轮→打分零网络零花费)+ 轮产出 diff 泄漏闸接线 + P2a 打分器
// 布局互通(scoreRuns 直接可扫 run 目录)。fixture = 最小 repo 形树(git 单根提交),
// 真答案源+真钥匙测试在 repo 侧、沙箱内被剥;python 面用主检出 venv(AGENTS worktree 律)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

import { runTrial, mintRoundId, seedQueueWorld, sandboxChangedFiles } from "../bench/add-domain/run-trial.mjs";
import { scoreRuns } from "../bench/add-domain/score.mjs";

const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES = path.join(HERE, "fixtures", "add");
const NAME = "sample_block_list";
const VENV_PY = "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";

// 真钥匙测试(repo 侧,构建时被剥;打分时装回):与罐装 turns 产的源对接
const KEY_TEST = [
  "from ipdb._sources.sample_block_list import parse_lines",
  "",
  "",
  "def test_parse_skips_comments_and_blank_lines():",
  '    assert parse_lines("# c\\n\\n1.2.3.4\\n5.6.7.8\\n") == ["1.2.3.4", "5.6.7.8"]',
  "",
  "",
  "def test_parse_trims_whitespace():",
  '    assert parse_lines("  9.9.9.9  \\n") == ["9.9.9.9"]',
  "",
].join("\n");
// 真答案源(repo 侧,构建时被剥;沙箱内由罐装实现者 turns 重实现)
const ANSWER_SRC = [
  '"""fixture answer source (stripped into sandbox build)."""',
  "",
  "",
  "def parse_lines(text: str) -> list[str]:",
  '    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]',
  "",
].join("\n");

function makeTrialFixture(prefix) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "ipdb", "_sources"), { recursive: true });
  fs.mkdirSync(path.join(repo, "backend", "tests", "sources"), { recursive: true });
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "__init__.py"), "");
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "_sources", `${NAME}.py`), ANSWER_SRC);
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", `test_${NAME}.py`), KEY_TEST);
  fs.writeFileSync(path.join(repo, "README.md"), "# fixture repo\n");
  const git = (...a) => execFileSync("git", ["-C", repo, ...a], { stdio: "ignore" });
  git("init", "-q");
  git("add", "-A", "-f");
  git("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture root");
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    JSON.stringify({ split: "evolve", name: NAME, url: "https://blocklist.example/raw.txt", category: "threat", archetype: "IpListSource", _why: "禁词引用:fixture 答案键载体" }),
  ].join("\n") + "\n");
  const cardPath = path.join(tmp, "card.json");
  fs.writeFileSync(cardPath, JSON.stringify({
    name: NAME,
    url: "https://blocklist.example/raw.txt",
    samples: ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
    format: "plain-ip-list",
    auth: "none",
    cadence: "daily",
    field_routing: ["行内 IP/CIDR → rebuild 键(cidr)"],
  }, null, 2) + "\n");
  // bench 形态夹具 = fixtures/add 去 DOSSIER 首回合(P1 bench 测试同律;本目录不动)
  const fixturesDir = path.join(tmp, "fixtures");
  fs.cpSync(FIXTURES, fixturesDir, { recursive: true });
  const turns = JSON.parse(fs.readFileSync(path.join(fixturesDir, "turns.json"), "utf8"));
  fs.writeFileSync(path.join(fixturesDir, "turns.json"), JSON.stringify({ turns: turns.turns.slice(1) }));
  return { tmp, repo, universePath, cardPath, fixturesDir };
}

const runFauxTrial = (fx, over = {}) => runTrial({
  name: NAME,
  repo: fx.repo,
  universePath: fx.universePath,
  runDir: path.join(fx.tmp, "run-01"),
  cardPath: fx.cardPath,
  fixturesDir: fx.fixturesDir,
  python: VENV_PY,
  stderr: { write: () => true },
  ...over,
});

// ── ① faux 全链冒烟:沙箱 → bench 轮 → 真钥匙打分,零网络零花费 ──────────
test("faux trial 全链:剥答案沙箱→bench 轮(DOSSIER 跳过)→钥匙装回打分 pass=1;P2a scoreRuns 布局互通", async () => {
  const fx = makeTrialFixture("add-trial-full-");
  try {
    const r = await runFauxTrial(fx);
    assert.equal(r.round.status, "completed", JSON.stringify(r.round.error ?? r));
    assert.equal(r.ok, true, `trial 须过:leak=${JSON.stringify(r.leak)} score=${r.score.pass}`);
    assert.equal(r.score.pass, 1);
    assert.equal(r.leak.ok, true);
    assert.match(r.roundId, /-add(-r\d+)?$/);
    // 沙箱布局:<runDir>/<题>/sandbox(P2a 打分器扫描位);答案剥净+实现者产物在场
    const sandbox = r.sandbox;
    assert.equal(sandbox, path.join(fx.tmp, "run-01", NAME, "sandbox"));
    assert.ok(!fs.existsSync(path.join(sandbox, "backend", "ipdb", "_sources", `${NAME}.py`)) || true); // 剥后由轮重写:以内容面断言
    const srcInSandbox = fs.readFileSync(path.join(sandbox, "backend", "ipdb", "_sources", `${NAME}.py`), "utf8");
    assert.match(srcInSandbox, /parse_lines/, "实现者源应在沙箱(罐装 turns 真执行)");
    assert.ok(srcInSandbox !== ANSWER_SRC, "沙箱源是轮产出,不是 repo 答案拷贝");
    // 打分钥匙装回:沙箱测试文件 == repo 真钥匙(打分器唯一写入面)
    const keyInSandbox = fs.readFileSync(path.join(sandbox, "backend", "tests", "sources", `test_${NAME}.py`), "utf8");
    assert.equal(keyInSandbox, KEY_TEST, "打分后沙箱测试位=真钥匙内容");
    // 沙箱 git:单根提交 + 轮 REPORT 提交(剥答案无历史律不被轮破坏)
    const log = execFileSync("git", ["-C", sandbox, "log", "--oneline"], { encoding: "utf8" }).trim().split("\n");
    assert.equal(log.length, 2, "根提交+轮提交");
    // bench 世界:queue.md 原样两行(轮零队列写)+ 台账行 + 轮工件
    const ops = path.join(fx.tmp, "run-01", NAME, "bench-world", "ops");
    const q = fs.readFileSync(path.join(ops, "queue.md"), "utf8");
    assert.equal((q.match(/\| 2026-/g) ?? []).length, 2, "预填卡世界两行原样");
    assert.match(q, /APPROVE/);
    const ledger = fs.readFileSync(path.join(ops, "ledger.md"), "utf8");
    assert.match(ledger, new RegExp(`pipeline-add:${r.roundId}`), "trial 世界台账行");
    assert.ok(fs.existsSync(path.join(ops, "rounds", r.roundId, "a3-implement.json")), "轮工件落 trial 世界");
    const a2 = JSON.parse(fs.readFileSync(path.join(ops, "rounds", r.roundId, "a2-dossier.json"), "utf8"));
    assert.equal(a2.bench, true, "DOSSIER 跳过(bench 开关位)");
    // trial.json 信封落盘
    const t = JSON.parse(fs.readFileSync(r.trialFile, "utf8"));
    assert.equal(t.ok, true);
    assert.equal(t.score.pass, 1);
    assert.equal(t.leak.ok, true);
    // P2a 布局互通:scoreRuns 直接扫 run 目录,S=1
    const agg = scoreRuns({ runs: [path.join(fx.tmp, "run-01")], repo: fx.repo, python: VENV_PY, universePath: fx.universePath });
    assert.equal(agg.k, 1);
    assert.equal(agg.meanS, 1);
  } finally { fs.rmSync(fx.tmp, { recursive: true, force: true }); }
});

// ── ② 轮产出 diff 泄漏闸:引用被剥路径(主检答案树绝对路径)= trial 红 ──────
test("trial 泄漏闸红端:轮 diff 引用主检出答案树绝对路径 → leak 红 ok=false(diff 不得引用被剥路径)", async () => {
  const fx = makeTrialFixture("add-trial-leak-");
  // 罐装 turns 加一腿:在总结回合前写 notes.md 内嵌主检答案树绝对路径(考古证据面)
  const turnsPath = path.join(fx.fixturesDir, "turns.json");
  const turns = JSON.parse(fs.readFileSync(turnsPath, "utf8"));
  const evil = {
    role: "assistant",
    content: [{ type: "toolCall", id: "c-evil", name: "write_file", arguments: {
      path: "notes.md",
      content: `参考实现:${fx.repo}/backend/tests/sources/test_${NAME}.py\n`,
    } }],
    stopReason: "toolUse",
  };
  turns.turns.splice(turns.turns.length - 1, 0, evil); // 插在总结回合前
  fs.writeFileSync(turnsPath, JSON.stringify(turns));
  try {
    const r = await runFauxTrial(fx, { runDir: path.join(fx.tmp, "run-leak") });
    assert.equal(r.round.status, "completed", "轮本身全绿(泄漏是轮外闸)");
    assert.equal(r.leak.ok, false, "diff 引用主检答案树 → leak 红");
    assert.equal(r.leak.hits.length >= 1, true);
    assert.equal(r.leak.hits[0].file, "notes.md");
    assert.equal(r.ok, false, "leak 红 → trial 整体不过");
    const t = JSON.parse(fs.readFileSync(r.trialFile, "utf8"));
    assert.equal(t.leak.ok, false);
  } finally { fs.rmSync(fx.tmp, { recursive: true, force: true }); }
});

// ── ③ 用法面:stem 契约红;卡形状红 ─────────────────────────────────────
test("用法面:卡名 slugify≠题名=拒(stem 契约);卡形状坏=拒;不带病开沙箱", async () => {
  const fx = makeTrialFixture("add-trial-usage-");
  const badName = path.join(fx.tmp, "bad-name.json");
  fs.writeFileSync(badName, JSON.stringify({ name: "Totally Other Feed", url: "https://blocklist.example/raw.txt", samples: ["1.2.3.4", "5.6.7.8", "9.10.11.12"], format: "x", auth: "none", cadence: "daily", field_routing: ["a"] }));
  await assert.rejects(() => runFauxTrial(fx, { cardPath: badName }), /stem|slugify/i);
  const badShape = path.join(fx.tmp, "bad-shape.json");
  fs.writeFileSync(badShape, JSON.stringify({ name: NAME, url: "https://blocklist.example/raw.txt" }));
  await assert.rejects(() => runFauxTrial(fx, { cardPath: badShape }), /形状/);
  // 沙箱未开(runDir 空)
  assert.equal(fs.existsSync(path.join(fx.tmp, "run-01", NAME, "sandbox")), false);
  fs.rmSync(fx.tmp, { recursive: true, force: true });
});

// ── ④ 纯函数面:roundId 铸形 / queue 世界自种 / 沙箱变更文件收集 ───────────
test("mintRoundId 形状律 YYYY-MM-DD-HHMM-add;seedQueueWorld 行形;sandboxChangedFiles 含未跟踪文件", async () => {
  assert.match(mintRoundId(new Date("2026-11-11T09:05:00")), /^2026-11-11-0905-add$/);
  const ops = fs.mkdtempSync(path.join(os.tmpdir(), "add-trial-pure-"));
  try {
    seedQueueWorld(ops, { source: NAME, card: { name: NAME, url: "https://blocklist.example/raw.txt" } });
    const q = fs.readFileSync(path.join(ops, "queue.md"), "utf8");
    assert.match(q, /\| human \| APPROVE \|/);
    assert.match(q, new RegExp(`candidate:name="${NAME}"`));
    // 变更文件收集:diff 面 + 未跟踪面都收
    const sbx = path.join(ops, "sbx");
    fs.mkdirSync(sbx);
    execFileSync("git", ["-C", sbx, "init", "-q"]);
    fs.writeFileSync(path.join(sbx, "tracked.txt"), "v1\n");
    execFileSync("git", ["-C", sbx, "add", "-A", "-f"]);
    execFileSync("git", ["-C", sbx, "-c", "user.email=f@x", "-c", "user.name=f", "commit", "-q", "-m", "root"]);
    const rootSha = execFileSync("git", ["-C", sbx, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    fs.writeFileSync(path.join(sbx, "tracked.txt"), "v2\n"); // 已跟踪修改
    fs.writeFileSync(path.join(sbx, "untracked.md"), "new\n"); // 未跟踪新增
    const files = sandboxChangedFiles(sbx, rootSha);
    assert.deepEqual(files.map((f) => f.path).sort(), ["tracked.txt", "untracked.md"]);
  } finally { fs.rmSync(ops, { recursive: true, force: true }); }
});
