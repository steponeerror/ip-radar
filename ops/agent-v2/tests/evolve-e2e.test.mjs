// evolve-e2e.test.mjs — #356 骨架 v1 红绿面(端到端):驱动器从排程触发到轮报告落盘
// 全链,罐装模型面(faux 提案者会话驱动真编码工具 + faux trial 全链),零网络零花费
// 零真扫描(票面验收门)。fixture 世界 = add-trial.test.mjs 同款最小 repo 形树
// (1 题 sample_block_list,真答案源+真钥匙测试 repo 侧、沙箱内被剥;worktree/护栏/
// 出口经注入缝:git 真跑、护栏 exec 桩、出口 dry-run)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb, execFileSync } from "node:child_process";
import { promisify } from "node:util";

import { runEvolveRound, diffFaceGateTouched, reconcileOrphanRounds } from "../bench/evolution/run-round.mjs";
import { EVOLVE_PROTECTED_FACES, evolutionDomainOf } from "../bench/evolution/domains.mjs"; // 保护名单单源(delta P1:5 前缀+3 执法链单件,域适配器显式声明)
import { runTrial } from "../bench/add-domain/run-trial.mjs";
import { readEvolutionState, writeEvolutionState, domainStateOf, evolutionStatePath } from "../bench/evolution/state.mjs";
import { monthSpendTotalCny } from "../bench/evolution/ledger.mjs";

const realExec = promisify(execFileCb);
const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES_ADD = path.join(HERE, "fixtures", "add");
const FIXTURES_EVOLVE = path.join(HERE, "fixtures", "evolve");
const VENV_PY = "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
const NAME = "sample_block_list";

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
const ANSWER_SRC = [
  '"""fixture answer source (stripped into sandbox build)."""',
  "",
  "",
  "def parse_lines(text: str) -> list[str]:",
  '    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]',
  "",
].join("\n");

// e2e fixture 世界:mini repo(单根提交;含驱动器要读的 SKILL.md 占位)+ 冻结宇宙
// (1 题 evolve)+ 考题卡 + faux trial 夹具(fixtures/add 去 DOSSIER 首回合,同律)。
function makeEvolveFixture(prefix) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "ipdb", "_sources"), { recursive: true });
  fs.mkdirSync(path.join(repo, "backend", "tests", "sources"), { recursive: true });
  fs.mkdirSync(path.join(repo, "ops", "agent-v2", "bench", "add-domain"), { recursive: true });
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "__init__.py"), "");
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "_sources", `${NAME}.py`), ANSWER_SRC);
  fs.writeFileSync(path.join(repo, "backend", "tests", "sources", `test_${NAME}.py`), KEY_TEST);
  // SKILL.md 占位(驱动器读 repo/<skillRel> 作提案者工作指令;内容面本测试不消费)
  fs.writeFileSync(path.join(repo, "ops", "agent-v2", "bench", "add-domain", "SKILL.md"), "# fixture 工作指令占位(e2e)\n");
  const git = (...a) => execFileSync("git", ["-C", repo, ...a], { stdio: "ignore" });
  git("init", "-q", "-b", "main");
  git("add", "-A", "-f");
  git("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture root");
  const universePath = path.join(tmp, "universe.jsonl");
  fs.writeFileSync(universePath, [
    JSON.stringify({ kind: "ipradar-add-universe", frozen: true }),
    JSON.stringify({ split: "evolve", name: NAME, url: "https://blocklist.example/raw.txt", category: "threat", archetype: "IpListSource", _why: "禁词引用:fixture 答案键载体" }),
  ].join("\n") + "\n");
  const cardsDir = path.join(tmp, "cards");
  fs.mkdirSync(cardsDir);
  fs.writeFileSync(path.join(cardsDir, `${NAME}.json`), JSON.stringify({
    name: NAME,
    url: "https://blocklist.example/raw.txt",
    samples: ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
    format: "plain-ip-list",
    auth: "none",
    cadence: "daily",
    field_routing: ["行内 IP/CIDR → rebuild 键(cidr)"],
  }, null, 2) + "\n");
  const trialFixtures = path.join(tmp, "trial-fixtures");
  fs.cpSync(FIXTURES_ADD, trialFixtures, { recursive: true });
  const turns = JSON.parse(fs.readFileSync(path.join(trialFixtures, "turns.json"), "utf8"));
  fs.writeFileSync(path.join(trialFixtures, "turns.json"), JSON.stringify({ turns: turns.turns.slice(1) }));
  return { tmp, repo, universePath, cardsDir, trialFixtures };
}

// 注入 exec:git 真跑(worktree/commit 面要真);bash(护栏前置 prep)/node/npm 桩绿。
// makeNpmRed = 护栏红注入变体(npm 桩抛 rc=1,首护栏即红)。calls=调用记录面
// (P2-③ 断言:护栏前覆写调用在护栏执行之前)。
function stubExec({ npmRed = false } = {}) {
  const calls = [];
  const fn = async (file, args, opts) => {
    calls.push({ file, args });
    if (file === "git") return realExec(file, args, opts);
    if (file === "npm" && npmRed)
      throw Object.assign(new Error("stub: guardrail red"), { code: 1, stdout: "", stderr: "stub guardrail red" });
    return { stdout: "", stderr: "" };
  };
  fn.calls = calls;
  return fn;
}

// 注入 trial 执行器:直接进程内跑 runTrial(faux 夹具;repo=该面 worktree=沙箱基真源)
const trialRunnerVia = (fx) => async (a) => runTrial({
  name: a.name,
  runDir: a.runDir,
  cardPath: a.cardPath,
  repo: a.faceRepo,
  universePath: fx.universePath,
  fixturesDir: a.fixturesDir,
  python: VENV_PY,
  stderr: { write: () => true },
});

const quiet = { write: () => true };

// ── ① 全链.faith:faux 提案者会话→worktree 候选面→护栏→同会话成对 trial×k→
//      噪声带判定(两面同夹具=零增益)→台账/状态/轮报告/gh 票 dry-run 落盘 ──────────
test("faux 端到端:排程触发→轮报告落盘全链(罐装模型面,零真扫描)", async () => {
  const fx = makeEvolveFixture("evolve-e2e-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const roundId = "2026-11-17-1200-evolve";
  try {
    const exec = stubExec();
    const r = await runEvolveRound({
      roundId, domain: "add-domain",
      repo: fx.repo, devRoot,
      universePath: fx.universePath, cardsDir: fx.cardsDir,
      fixturesDir: FIXTURES_EVOLVE, trialFixturesDir: fx.trialFixtures,
      k: 3, dryRun: true,
      exec, trialRunner: trialRunnerVia(fx), stderr: quiet,
    });
    // P2-③:护栏块前重跑 worktree-prep.sh --overwrite 覆写候选 node_modules
    // (防投毒:node_modules gitignored,diff 面闸两腿看不见)且先于护栏执行
    const iOverwrite = exec.calls.findIndex((c) => c.file === "bash" && c.args[1] === "--overwrite");
    const iGuard = exec.calls.findIndex((c) => c.file === "npm");
    assert.ok(iOverwrite >= 0, "护栏前有 worktree-prep --overwrite 覆写调用");
    assert.ok(iGuard >= 0 && iOverwrite < iGuard, "覆写调用先于护栏①(npm test)");
    // 信封:轮完成,判定=带内零增益(两面同夹具 frac 全等 → mean_diff=0)
    assert.equal(r.status, "completed");
    assert.equal(r.envelope.ok, true);
    assert.equal(r.envelope.outcome, "zero_gain");
    assert.equal(r.envelope.judge.n, 3, "1 题 × k=3 成对");
    assert.equal(r.envelope.judge.mean_diff, 0);
    assert.equal(r.envelope.judge.missing, 0);
    assert.equal(r.envelope.champion.after, r.envelope.champion.before, "零增益:循环冠军指针不动");
    // 三护栏+头部 diff 面闸:桩面全绿(skipped 无);只改开放面(implement.md)→闸过
    assert.deepEqual(r.envelope.guardrails.map((g) => g.status), ["pass", "pass", "pass", "pass"]);
    assert.equal(r.envelope.guardrails[0].name, "diff 面闸");
    assert.equal(r.envelope.stall.rounds, 1, "零增益入熄火计数(1/3)");
    assert.equal(r.envelope.stall.halted, false);
    // 花费:faux 双面零花费,月帽台账入账 0(留痕)
    assert.equal(r.envelope.spend.proposer_cny + r.envelope.spend.trials_cny, 0);
    const roundDir = r.envelope.round_dir;
    assert.equal(monthSpendTotalCny(path.join(devRoot, "spend.json")), 0);
    // 工件落盘:报告/信封/出口/提案者报告/矿掘/断点件
    for (const f of ["report.md", "envelope.json", "exits.json", "proposer-report.md", "mining.txt", "round.json"])
      assert.ok(fs.existsSync(path.join(roundDir, f)), `工件缺席:${f}`);
    const report = fs.readFileSync(path.join(roundDir, "report.md"), "utf8");
    assert.match(report, /零增益/, "报告含判定词");
    assert.match(report, new RegExp(devRoot), "报告含工件路径");
    assert.match(fs.readFileSync(path.join(roundDir, "proposer-report.md"), "utf8"), /罐装/, "提案者终答=faux 报告文本");
    assert.match(fs.readFileSync(path.join(roundDir, "mining.txt"), "utf8"), /首轮/, "首轮矿掘占位");
    // 出口:每轮 gh 票 dry_run(cmd 留痕零外发);zero_gain 非异常 → lark skip
    const exits = JSON.parse(fs.readFileSync(path.join(roundDir, "exits.json"), "utf8"));
    assert.equal(exits.issue.status, "dry_run");
    assert.match(exits.issue.cmd_head, /gh issue create/);
    assert.equal(exits.anomaly.status, "skip");
    // 候选面:提案者 worktree 分支上有提交(罐装回合真 commit),候选≠基线
    const rj = JSON.parse(fs.readFileSync(path.join(roundDir, "round.json"), "utf8"));
    assert.equal(rj.phase, "swept");
    assert.notEqual(rj.candidate_ref, r.envelope.champion.before);
    assert.ok(fs.existsSync(path.join(r.envelope.worktree, "ops", "agent", "prompts", "add", "implement.md")), "罐装编辑落在候选 worktree(沙箱遏制面)");
    // trial 批:两面各 3 副本,trial.json 断点件在位;同会话成对布局 <face>/<题>/r<i>
    for (const face of ["champion", "candidate"])
      for (let i = 1; i <= 3; i++)
        assert.ok(fs.existsSync(path.join(roundDir, "sweeps", face, NAME, `r${i}`, NAME, "trial.json")), `trial.json 缺席:${face} r${i}`);
    // 状态件:熄火 1/3;冠军指针仍空(零增益不前移)
    const dom = domainStateOf(readEvolutionState(evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot })), "add-domain");
    assert.equal(dom.stall_rounds, 1);
    assert.equal(dom.champion_ref, r.envelope.champion.before, "首跑种子已落盘;零增益不前移");
    assert.equal(dom.last_round_id, roundId);
  } finally {
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "worktrees", roundId)], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "champions", "add-domain")], { stdio: "ignore" }); } catch { /* 同上 */ }
    fs.rmSync(fx.tmp, { recursive: true, force: true });
  }
});

// ── ② 月帽拒启:当月累计超帽 → refused(spend_cap),首拒开票推 lark(dry-run),零建面 ──
test("月帽拒启:超帽 refused+首拒出口;连续同 code 第二拍去重(不刷屏)", async () => {
  const fx = makeEvolveFixture("evolve-cap-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  fs.mkdirSync(devRoot, { recursive: true });
  fs.writeFileSync(path.join(devRoot, "spend.json"), JSON.stringify({
    entries: [{ at: new Date().toISOString(), round_id: "seed", domain: "add-domain", cost_cny: 200.01 }],
    total_cny: 200.01,
  }, null, 2) + "\n");
  try {
    const env = { ...process.env, EVOLVE_SPEND_CAP_CNY: "200", IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" };
    const r1 = await runEvolveRound({
      roundId: "2026-11-17-1300-evolve", domain: "add-domain",
      repo: fx.repo, devRoot, env, fixturesDir: FIXTURES_EVOLVE, dryRun: true, exec: stubExec(), stderr: quiet,
    });
    assert.equal(r1.status, "refused");
    assert.equal(r1.code, "spend_cap");
    assert.match(r1.envelope.error.message, /超月帽/);
    assert.equal(r1.envelope.issue.status, "dry_run", "首拒开票(dry-run)");
    assert.equal(r1.envelope.anomaly.status, "dry_run", "超帽=异常推 lark(dry-run)");
    assert.ok(!fs.existsSync(path.join(devRoot, "worktrees")), "拒启零建面(无 worktree)");
    const r2 = await runEvolveRound({
      roundId: "2026-11-17-1315-evolve", domain: "add-domain",
      repo: fx.repo, devRoot, env, fixturesDir: FIXTURES_EVOLVE, dryRun: true, exec: stubExec(), stderr: quiet,
    });
    assert.equal(r2.status, "refused");
    assert.equal(r2.envelope.issue.status, "skip", "连续同 code 拒启去重:不开票");
    assert.equal(r2.envelope.anomaly.status, "skip", "去重:不推 lark");
    const dom = domainStateOf(readEvolutionState(evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot })), "add-domain");
    assert.equal(dom.last_refusal.code, "spend_cap");
    assert.equal(dom.last_refusal.round_id, "2026-11-17-1315-evolve");
  } finally { fs.rmSync(fx.tmp, { recursive: true, force: true }); }
});

// ── ③ 护栏红:首护栏红即轮终(异常 lark dry-run),零 trial,熄火账不加 ──────────
test("护栏红:候选作废轮终+异常出口;未判定轮不入熄火账;台账入提案者花费(0)", async () => {
  const fx = makeEvolveFixture("evolve-guard-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const roundId = "2026-11-17-1400-evolve";
  try {
    const r = await runEvolveRound({
      roundId, domain: "add-domain",
      repo: fx.repo, devRoot,
      env: { ...process.env, IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" },
      universePath: fx.universePath, cardsDir: fx.cardsDir,
      fixturesDir: FIXTURES_EVOLVE, trialFixturesDir: fx.trialFixtures,
      k: 3, dryRun: true,
      exec: stubExec({ npmRed: true }), trialRunner: trialRunnerVia(fx), stderr: quiet,
    });
    assert.equal(r.status, "failed");
    assert.equal(r.code, "guardrail_red");
    assert.match(r.envelope.error.message, /护栏红:v2 全套/);
    assert.equal(r.envelope.anomaly.status, "dry_run", "护栏红=异常推 lark(dry-run)");
    const roundDir = path.join(devRoot, "rounds", roundId);
    assert.ok(!fs.existsSync(path.join(roundDir, "sweeps")), "护栏红零 trial 批");
    const dom = domainStateOf(readEvolutionState(evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot })), "add-domain");
    assert.equal(dom.stall_rounds, 0, "未判定轮不入熄火账");
    const ledger = JSON.parse(fs.readFileSync(path.join(devRoot, "spend.json"), "utf8"));
    assert.equal(ledger.entries.length, 1);
    assert.equal(ledger.entries[0].cost_cny, 0, "faux 提案者花费 0,入账留痕");
    assert.equal(ledger.entries[0].round_id, roundId);
  } finally {
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "worktrees", roundId)], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "champions", "add-domain")], { stdio: "ignore" }); } catch { /* 同上 */ }
    fs.rmSync(fx.tmp, { recursive: true, force: true });
  }
});

// ── ④ 域留位:未接线域=用法红(接口域配置化,rrsi/health 不在表)────────────────
test("未接线域=用法红(域配置化留位)", async () => {
  await assert.rejects(
    () => runEvolveRound({ roundId: "2026-11-17-1500-evolve", domain: "rrsi-domain", repo: "/nonexistent", devRoot: "/nonexistent", dryRun: true, stderr: quiet }),
    /域未接线:rrsi-domain/,
  );
});

// P1-1 红面夹具:罐装提案者改保护名单内路径(钥匙测试本体,backend/)——已提交 diff 须被闸拦
function protectedEditProposerFixtures(tmp) {
  const dir = path.join(tmp, "prop-fixtures-protected");
  fs.cpSync(FIXTURES_EVOLVE, dir, { recursive: true });
  const turns = JSON.parse(fs.readFileSync(path.join(dir, "turns.json"), "utf8"));
  // 换新 toolCall id:pi 会话层对罐装回合的 call id 有重放归一(同 id 复用会重放原回合
  // 参数),新 id 保证注入回合按本夹具参数真执行(minifaux 判例:新 id 生效、原 id 回原参)
  turns.turns[0].content[0].id = "e-write-prot-1";
  turns.turns[0].content[0].arguments = { path: `backend/tests/sources/test_${NAME}.py`, content: "# hijack: candidate edits the scoring key face (P1-1 red fixture)\n" };
  fs.writeFileSync(path.join(dir, "turns.json"), JSON.stringify(turns, null, 2) + "\n");
  return dir;
}

// ── ⑤ P1-1 候选面自判分洞:提案者改保护名单(钥匙测试面)→ diff 面闸护栏红同罚──
//      只改开放面的绿面由①钉(implement.md 过闸,四护栏全绿)。
test("diff 面闸:候选改保护名单(钥匙测试)→护栏红,零 trial,熄火账不加", async () => {
  const fx = makeEvolveFixture("evolve-p1gate-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const roundId = "2026-11-17-1600-evolve";
  try {
    const r = await runEvolveRound({
      roundId, domain: "add-domain",
      repo: fx.repo, devRoot,
      universePath: fx.universePath, cardsDir: fx.cardsDir,
      fixturesDir: protectedEditProposerFixtures(fx.tmp), trialFixturesDir: fx.trialFixtures,
      env: { ...process.env, IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" },
      k: 3, dryRun: true,
      exec: stubExec(), trialRunner: trialRunnerVia(fx), stderr: quiet,
    });
    assert.equal(r.status, "failed");
    assert.equal(r.code, "guardrail_red");
    assert.match(r.envelope.error.message, /护栏红:diff 面闸/);
    // 首红即停:余三护栏记 skipped;触表路径在闸尾巴可追溯(失败面护栏表落 round.json)
    const rj = JSON.parse(fs.readFileSync(path.join(devRoot, "rounds", roundId, "round.json"), "utf8"));
    assert.deepEqual(rj.guardrails.map((g) => g.status), ["red", "skipped", "skipped", "skipped"]);
    assert.equal(rj.guardrails[0].name, "diff 面闸");
    assert.match(rj.guardrails[0].tail, /backend\/tests\/sources\/test_sample_block_list\.py/);
    assert.ok(!fs.existsSync(path.join(devRoot, "rounds", roundId, "sweeps")), "护栏红零 trial 批");
    assert.equal(r.envelope.anomaly.status, "dry_run", "护栏红=异常推 lark(dry-run)");
    const dom = domainStateOf(readEvolutionState(evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot })), "add-domain");
    assert.equal(dom.stall_rounds, 0, "未判定轮不入熄火账");
    const ledger = JSON.parse(fs.readFileSync(path.join(devRoot, "spend.json"), "utf8"));
    assert.equal(ledger.entries.length, 1);
    assert.equal(ledger.entries[0].cost_cny, 0, "faux 提案者花费 0,入账留痕");
  } finally {
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "worktrees", roundId)], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "champions", "add-domain")], { stdio: "ignore" }); } catch { /* 同上 */ }
    fs.rmSync(fx.tmp, { recursive: true, force: true });
  }
});

// ── ⑤′ P1-1 单面:diff 面闸的 git 取数(已提交/untracked/改名出保护区都显形;开放面绿)──
test("diff 面闸单面:untracked 触名单+改名出保护区显形;开放面=绿", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "evolve-gate-unit-"));
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "backend", "ipdb"), { recursive: true });
  fs.mkdirSync(path.join(repo, "ops", "agent", "prompts", "add"), { recursive: true });
  fs.writeFileSync(path.join(repo, "backend", "ipdb", "x.py"), "x\n");
  fs.writeFileSync(path.join(repo, "ops", "agent", "prompts", "add", "implement.md"), "doc\n");
  const git = (...a) => execFileSync("git", ["-C", repo, ...a], { stdio: "ignore" });
  git("init", "-q", "-b", "main");
  git("add", "-A", "-f");
  git("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base");
  const base = execFileSync("git", ["-C", repo, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const wt = path.join(tmp, "wt");
  execFileSync("git", ["-C", repo, "worktree", "add", "-q", "-b", "cand", wt, base], { stdio: "ignore" });
  const gitWt = (...a) => execFileSync("git", ["-C", wt, ...a], { stdio: "ignore" });
  try {
    // 已提交:开放面编辑 → 绿
    fs.writeFileSync(path.join(wt, "ops", "agent", "prompts", "add", "implement.md"), "edited\n");
    gitWt("add", "-A");
    gitWt("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "open edit");
    assert.deepEqual(await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }), []);
    // untracked(未提交)触名单 → 显形(驱动器代提交前的残面也拦得住)
    fs.mkdirSync(path.join(wt, "ops", "agent-v2", "bench", "evolution"), { recursive: true });
    fs.writeFileSync(path.join(wt, "ops", "agent-v2", "bench", "evolution", "judge.mjs"), "hijack\n");
    assert.deepEqual(
      await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }),
      ["ops/agent-v2/bench/evolution/judge.mjs"],
    );
    // 改名出保护区(--no-renames:旧路径以删除形态显形,不可用改名绕闸)
    fs.rmSync(path.join(wt, "ops", "agent-v2", "bench", "evolution", "judge.mjs"));
    fs.renameSync(path.join(wt, "backend", "ipdb", "x.py"), path.join(wt, "evil.py"));
    gitWt("add", "-A");
    gitWt("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "rename out");
    assert.deepEqual(
      await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }),
      ["backend/ipdb/x.py"],
    );
    // delta P1 三件执法链各一红面:护栏②副本(leak-check)、其名单解析(roster)、
    // 护栏①脚本面(package.json scripts.test)——候选树内副本可中和护栏的三条路全上锁
    fs.writeFileSync(path.join(wt, "ops", "agent-v2", "bench", "leak-check.mjs"), "// hijack: neutralize leak gate\n");
    gitWt("add", "-A");
    gitWt("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "hijack leak-check");
    assert.deepEqual(
      await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }),
      ["backend/ipdb/x.py", "ops/agent-v2/bench/leak-check.mjs"],
    );
    fs.writeFileSync(path.join(wt, "ops", "agent-v2", "bench", "roster.mjs"), "// hijack: parseRoster -> []\n");
    gitWt("add", "-A");
    gitWt("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "hijack roster");
    assert.deepEqual(
      await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }),
      ["backend/ipdb/x.py", "ops/agent-v2/bench/leak-check.mjs", "ops/agent-v2/bench/roster.mjs"],
    );
    fs.writeFileSync(path.join(wt, "ops", "agent-v2", "package.json"), JSON.stringify({ scripts: { test: "node -e 0" } }, null, 2) + "\n");
    gitWt("add", "-A");
    gitWt("-c", "user.email=f@x.example", "-c", "user.name=fixture", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "hijack npm test");
    assert.deepEqual(
      await diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: EVOLVE_PROTECTED_FACES }),
      ["backend/ipdb/x.py", "ops/agent-v2/bench/leak-check.mjs", "ops/agent-v2/bench/roster.mjs", "ops/agent-v2/package.json"],
    );
    // 名单形状:八面=五前缀+三执法链单件;域适配器显式声明(driver 从适配器读)
    assert.equal(EVOLVE_PROTECTED_FACES.length, 8, "保护名单八面:backend/tests/fixtures/bench-add-domain/bench-evolution + leak-check/roster/package.json");
    assert.deepEqual(evolutionDomainOf("add-domain").protectedFaces, EVOLVE_PROTECTED_FACES, "add-domain 域显式声明名单(domains.mjs 单源)");
    // 名单缺席=用法红(接线新域漏声明 protectedFaces=闸面红,不静默绿)
    await assert.rejects(
      () => diffFaceGateTouched(realExec, { worktree: wt, baseRef: base, faces: undefined }),
      /保护名单缺席/,
    );
  } finally {
    try { execFileSync("git", ["-C", repo, "worktree", "remove", "--force", wt], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

// P1-2 试跑器注入:可控花费与花费帽拒跑(exit 4 语义),trial.json 落盘可续跑
const trialRunnerWithCap = ({ capAfter = Infinity, cost = 0.25 } = {}) => {
  let calls = 0;
  return async (a) => {
    calls += 1;
    if (calls > capAfter) throw Object.assign(new Error("stub: trial 花费帽拒跑(run-trial exit 4)"), { code: "trial_spend_cap" });
    const t = { name: a.name, round: { usage: { cost } }, score: { frac: 0.5 } };
    const p = path.join(a.runDir, a.name, "trial.json");
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(t) + "\n");
    return t;
  };
};

// ── ⑥ P1-2 续跑漏账:失败收口入账后续跑完成,两次金额都进台账(补差非跳过)──
test("续跑补差入账:trial 花费帽失败入账 ¥0.5 后同轮续跑完成,再补 ¥1.0(总额 1.5)", async () => {
  const fx = makeEvolveFixture("evolve-resume-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const roundId = "2026-11-17-1700-evolve";
  const ledger = path.join(devRoot, "spend.json");
  const roundJson = path.join(devRoot, "rounds", roundId, "round.json");
  const base = {
    roundId, domain: "add-domain",
    repo: fx.repo, devRoot,
    universePath: fx.universePath, cardsDir: fx.cardsDir,
    fixturesDir: FIXTURES_EVOLVE, trialFixturesDir: fx.trialFixtures,
    k: 3, dryRun: true,
    exec: stubExec(), stderr: quiet,
  };
  try {
    // 第一趟:第 3 个 trial(1 题 × k3 × 2 面=6 个)遇花费帽拒跑 → finishFailed 入账 0.5
    const r1 = await runEvolveRound({ ...base, trialRunner: trialRunnerWithCap({ capAfter: 2 }) });
    assert.equal(r1.status, "failed");
    assert.equal(r1.code, "trial_spend_cap");
    const j1 = JSON.parse(fs.readFileSync(roundJson, "utf8"));
    assert.equal(j1.phase, "sweeping");
    assert.equal(j1.trials_cost_cny, 0.5);
    assert.equal(j1.ledger_appended_cny, 0.5, "已入账金额记在断点件(非布尔)");
    let entries = JSON.parse(fs.readFileSync(ledger, "utf8")).entries;
    assert.equal(entries.length, 1);
    assert.equal(entries[0].cost_cny, 0.5);
    // 第二趟:同 roundId 续跑(断点件+trial.json 复用),完成到收口步只补差额
    const r2 = await runEvolveRound({ ...base, trialRunner: trialRunnerWithCap({}) });
    assert.equal(r2.status, "completed");
    assert.equal(r2.envelope.outcome, "zero_gain");
    assert.equal(r2.envelope.spend.trials_cny, 1.5, "6 trial × 0.25 全量在账");
    entries = JSON.parse(fs.readFileSync(ledger, "utf8")).entries;
    assert.deepEqual(entries.map((e) => e.cost_cny), [0.5, 1.0], "两笔:失败收口 0.5 + 续跑补差 1.0");
    assert.ok(entries.every((e) => e.round_id === roundId));
    assert.equal(monthSpendTotalCny(ledger), 1.5, "月帽读数=轮总花费(不漏不双)");
    const j2 = JSON.parse(fs.readFileSync(roundJson, "utf8"));
    assert.equal(j2.ledger_appended_cny, 1.5);
    assert.equal(j2.trials_fresh, 6);
    assert.equal(j2.trials_resumed, 2, "帽前 2 个 trial 断点复用不重跑不重记账");
  } finally {
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "worktrees", roundId)], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "champions", "add-domain")], { stdio: "ignore" }); } catch { /* 同上 */ }
    fs.rmSync(fx.tmp, { recursive: true, force: true });
  }
});

// ── ⑦ P2-3 熄火拒启出口闸:halted_reported 在位=静默;未报=补报一次后置位──
test("熄火拒启:已报=静默(skip 出口零外发);未报=补报一次+置位,再拍静默", async () => {
  const fx = makeEvolveFixture("evolve-stalled-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const statePath = evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot });
  const env = { ...process.env, IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" };
  const go = (rid) => runEvolveRound({
    roundId: rid, domain: "add-domain", repo: fx.repo, devRoot,
    fixturesDir: FIXTURES_EVOLVE, env, dryRun: true, exec: stubExec(), stderr: quiet,
  });
  try {
    // 已报位在(产出轮报完置位):拒启静默——不开票不推 lark(置位后=静默拒启不重发)
    writeEvolutionState(statePath, { domains: { "add-domain": { champion_ref: "abc", stall_rounds: 3, halted: true, halted_reported: true, last_refusal: null, last_round_id: "2026-11-10-0400-evolve" } } });
    const r1 = await go("2026-11-17-1800-evolve");
    assert.equal(r1.status, "refused");
    assert.equal(r1.code, "stalled");
    assert.equal(r1.envelope.issue.status, "skip");
    assert.match(r1.envelope.issue.reason, /halted_reported/);
    assert.equal(r1.envelope.anomaly.status, "skip");
    assert.ok(!fs.existsSync(path.join(devRoot, "worktrees")), "拒启零建面");
    // 未报位(产出轮报前崩溃):本拍补报(开票+推 lark)并置位
    writeEvolutionState(statePath, { domains: { "add-domain": { champion_ref: "abc", stall_rounds: 3, halted: true, halted_reported: false, last_refusal: null, last_round_id: "2026-11-10-0400-evolve" } } });
    const r2 = await go("2026-11-17-1815-evolve");
    assert.equal(r2.status, "refused");
    assert.equal(r2.envelope.issue.status, "dry_run", "补报:开票(dry-run)");
    assert.equal(r2.envelope.anomaly.status, "dry_run", "补报:推 lark(dry-run)");
    assert.equal(domainStateOf(readEvolutionState(statePath), "add-domain").halted_reported, true, "补报完即置位");
    // 再拍:静默
    const r3 = await go("2026-11-17-1830-evolve");
    assert.equal(r3.envelope.issue.status, "skip");
    assert.equal(r3.envelope.anomaly.status, "skip");
    const dom = domainStateOf(readEvolutionState(statePath), "add-domain");
    assert.equal(dom.last_refusal.code, "stalled");
    assert.equal(dom.last_refusal.round_id, "2026-11-17-1830-evolve");
  } finally { fs.rmSync(fx.tmp, { recursive: true, force: true }); }
});

// ── ⑧ P2-4② 孤儿轮:启动对账收口入台账(新轮才准启;同 roundId 续跑不误判孤儿)──
test("启动对账:无终态孤儿轮收口入台账+异常出口,然后新轮才启", async () => {
  const fx = makeEvolveFixture("evolve-orphan-");
  const devRoot = path.join(fx.tmp, "dev-evolution");
  const orphanId = "2026-11-16-0400-evolve";
  const orphanDir = path.join(devRoot, "rounds", orphanId);
  fs.mkdirSync(orphanDir, { recursive: true });
  fs.writeFileSync(path.join(orphanDir, "round.json"), JSON.stringify({
    round_id: orphanId, domain: "add-domain", phase: "sweeping",
    proposer_cost_cny: 0.5, trials_cost_cny: 3.0,
  }, null, 2) + "\n"); // 无 envelope.json=孤儿(systemd 击杀路径,finishFailed 未执行)
  const lines = [];
  const roundId = "2026-11-17-1900-evolve";
  try {
    const r = await runEvolveRound({
      roundId, domain: "add-domain",
      repo: fx.repo, devRoot,
      universePath: fx.universePath, cardsDir: fx.cardsDir,
      fixturesDir: FIXTURES_EVOLVE, trialFixturesDir: fx.trialFixtures,
      env: { ...process.env, IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" },
      k: 3, dryRun: true,
      exec: stubExec(), trialRunner: trialRunnerVia(fx),
      stderr: { write: (l) => { lines.push(String(l)); return true; } },
    });
    // 新轮照启并完成(对账先行:孤儿收口日志在新轮日志之前)
    assert.equal(r.status, "completed");
    const iOrphan = lines.findIndex((l) => l.includes("启动对账:孤儿轮"));
    const iRound = lines.findIndex((l) => l.includes(`[evolve] round=${roundId}`));
    assert.ok(iOrphan >= 0 && iRound >= 0 && iOrphan < iRound, "对账先于新轮起跑");
    // 孤儿收口:补账 ¥3.5 入月帽 + 终态信封/报告/出口 + 异常推 lark
    const ledger = JSON.parse(fs.readFileSync(path.join(devRoot, "spend.json"), "utf8"));
    assert.deepEqual(ledger.entries.map((e) => ({ id: e.round_id, c: e.cost_cny })), [
      { id: orphanId, c: 3.5 },
      { id: roundId, c: 0 },
    ], "孤儿断点件在账花费 0.5+3.0 全额入账;新轮 faux 零花费留痕");
    assert.equal(monthSpendTotalCny(path.join(devRoot, "spend.json")), 3.5);
    const oj = JSON.parse(fs.readFileSync(path.join(orphanDir, "round.json"), "utf8"));
    assert.equal(oj.ledger_appended_cny, 3.5, "断点件同步已入账额(再对账幂等)");
    const oe = JSON.parse(fs.readFileSync(path.join(orphanDir, "envelope.json"), "utf8"));
    assert.equal(oe.error.code, "orphan_reconciled");
    assert.ok(fs.existsSync(path.join(orphanDir, "report.md")));
    const ox = JSON.parse(fs.readFileSync(path.join(orphanDir, "exits.json"), "utf8"));
    assert.equal(ox.issue.status, "dry_run");
    assert.equal(ox.anomaly.status, "dry_run", "孤儿收口=异常报告");
    // state:孤儿留痕(未判定不加不清熄火账);新轮完成后再记新轮号
    const dom = domainStateOf(readEvolutionState(evolutionStatePath({ EVOLVE_DEV_ROOT: devRoot })), "add-domain");
    assert.equal(dom.last_round_id, roundId);
    assert.equal(dom.stall_rounds, 1, "孤儿未判定不入熄火账;新轮 zero_gain 记 1");
  } finally {
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "worktrees", roundId)], { stdio: "ignore" }); } catch { /* 树随 tmp 删 */ }
    try { execFileSync("git", ["-C", fx.repo, "worktree", "remove", "--force", path.join(devRoot, "champions", "add-domain")], { stdio: "ignore" }); } catch { /* 同上 */ }
    fs.rmSync(fx.tmp, { recursive: true, force: true });
  }
});

// ── ⑨ P2-② pre-flush 孤儿:有会话痕迹(evolve.sqlite)而无断点件——零费信封留痕;──
//      无会话痕迹(仅 mining.txt)=会话未开零花费,不收口;幂等+同轮续跑跳过 ──────
test("启动对账:pre-flush 孤儿(会话痕迹在、断点件从未落盘)→零费信封,追不回留痕", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "evolve-preflush-"));
  const devRoot = path.join(tmp, "dev-evolution");
  const preFlushId = "2026-11-16-2200-evolve";
  const preFlushDir = path.join(devRoot, "rounds", preFlushId);
  fs.mkdirSync(preFlushDir, { recursive: true });
  fs.writeFileSync(path.join(preFlushDir, "evolve.sqlite"), "(fake session db)——崩在提案者会话窗:round.json 从未落盘\n");
  fs.writeFileSync(path.join(preFlushDir, "mining.txt"), "(首轮矿掘占位)\n");
  const noSessionId = "2026-11-16-2230-evolve"; // 仅 mining.txt:会话未开零花费
  fs.mkdirSync(path.join(devRoot, "rounds", noSessionId), { recursive: true });
  fs.writeFileSync(path.join(devRoot, "rounds", noSessionId, "mining.txt"), "(崩在会话开之前)\n");
  const resumingId = "2026-11-16-2250-evolve"; // 同轮断点续跑面(有痕迹也跳过)
  fs.mkdirSync(path.join(devRoot, "rounds", resumingId), { recursive: true });
  fs.writeFileSync(path.join(devRoot, "rounds", resumingId, "evolve.sqlite"), "(resuming)\n");
  const lines = [];
  try {
    const closed = await reconcileOrphanRounds({
      devRoot, skipRoundId: resumingId,
      env: { ...process.env, IP_RADAR_ALERT_URLS: "lark://fixture-token-1234" },
      dryRun: true, exec: stubExec(),
      stderr: { write: (l) => { lines.push(String(l)); return true; } },
    });
    // 只收 pre-flush 孤儿:零费(花费不可追不伪造,无台账笔目)+域不可知
    assert.deepEqual(closed, [{ round_id: preFlushId, domain: null, appended_cny: 0 }]);
    assert.ok(!fs.existsSync(path.join(devRoot, "spend.json")), "零费信封不入台账(不伪造)");
    const oe = JSON.parse(fs.readFileSync(path.join(preFlushDir, "envelope.json"), "utf8"));
    assert.equal(oe.error.code, "orphan_pre_flush");
    assert.equal(oe.domain, null);
    assert.equal(oe.spend.appended_now_cny, 0);
    assert.match(oe.error.message, /追不回留痕|不可追/);
    assert.ok(fs.existsSync(path.join(preFlushDir, "report.md")), "报告留痕");
    const ox = JSON.parse(fs.readFileSync(path.join(preFlushDir, "exits.json"), "utf8"));
    assert.equal(ox.issue.status, "dry_run", "开票(dry-run)");
    assert.equal(ox.anomaly.status, "dry_run", "异常推 lark(dry-run)");
    // 无会话痕迹/同轮续跑面:不收口(无信封)
    assert.ok(!fs.existsSync(path.join(devRoot, "rounds", noSessionId, "envelope.json")), "仅 mining.txt=会话未开,不收口");
    assert.ok(!fs.existsSync(path.join(devRoot, "rounds", resumingId, "envelope.json")), "本轮 roundId 跳过");
    // 幂等:再对账(终态在)零动作(同轮续跑面照旧跳过)
    const again = await reconcileOrphanRounds({ devRoot, skipRoundId: resumingId, env: {}, dryRun: true, exec: stubExec(), stderr: quiet });
    assert.deepEqual(again, []);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
