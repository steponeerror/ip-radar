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

async function runRound(tree, db, fixturesDir = FIXTURES) { // fixturesDir 可覆盖(P0-③ 重试测:罐装短表首回合空文本)
  // 任务侧 env=process.env 现读(旧律,buildCtx 注);in-proc 测试须同步设进程环境(于 finally 还原)。
  const keys = ["DOCS_ROOT", "LEDGER_FILE"];
  const saved = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  process.env.DOCS_ROOT = tree.docsRoot;
  process.env.LEDGER_FILE = path.join(tree.opsRoot, "ledger.md");
  try {
    return await runDiscoverRound({
      roundId: ROUND,
      fixturesDir,
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

test("全链 faux 轮:信封 ok + 六步工件 + issue 出口留痕(faux 零外发)+ 门全绿 + 台账行", async () => {
  const tree = tmpTree("v2-disc-full-");
  const r = await runRound(tree);
  assert.equal(r.status, "completed", JSON.stringify(r));
  const env = r.envelope;
  assert.equal(env.ok, true);
  assert.deepEqual(Object.keys(env).sort(), ["issues_opened", "ok", "pipeline", "pkg", "queue_writes", "round", "usage", "verify"].sort(), "#384:信封键闭集新增 issues_opened(queue_writes 保留恒空数组=回放兼容)");
  assert.equal(env.issues_opened, 0, "faux 轮零外发,issue 计数恒 0");
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"]);
  // usage 求和律(旧 pipeline_ok 断言面):各步 usage 之和 == 信封 usage(脚本步 null 不回声)
  const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
  for (const s of env.pipeline.stages) if (s.usage) for (const k of Object.keys(sum)) sum[k] += s.usage[k];
  assert.deepEqual(sum, env.usage);
  const dir = path.join(tree.opsRoot, "rounds", ROUND);
  for (const f of ["d1-scan.json", "d2-shortlist.json", "d2-shortlist-transcript.jsonl", "d3-measure.json", "d4-enqueue.json", "enqueue-issues.json", "09-budget.json", "gates.json", "state.json"])
    assert.ok(fs.existsSync(path.join(dir, f)), `工件缺:${f}`);
  // #408:CLOSE 终态回写——state.json 镜像不得停在 running(轮实际已结束,状态文件在
  // 说谎;#405 报告件补上后的同位遗留)。终态词沿用 v1 status 流(done/failed),
  // stages 名单镜像推进到含 CLOSE。
  const mirror = JSON.parse(fs.readFileSync(path.join(dir, "state.json"), "utf8"));
  assert.equal(mirror.status, "done", "#408:CLOSE 后 state.json 终态应为 done(缺陷面=停在 running)");
  assert.deepEqual(mirror.stages, ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"], "#408:终态镜像 stages 名单含 CLOSE");
  // #384:出口改 GH issue——queue.md PROPOSE 行停写(v2 轮零 queue 写口,文件不建);
  // 出口留痕落 enqueue-issues.json(faux 零外发 skip 面,审计面恒落)。
  assert.ok(!fs.existsSync(path.join(tree.opsRoot, "queue.md")), "#384 后 v2 发现轮不得写 queue.md(PROPOSE 停写)");
  const issues = JSON.parse(fs.readFileSync(path.join(dir, "enqueue-issues.json"), "utf8"));
  assert.equal(issues.status, "skip");
  assert.match(issues.reason, /faux_zero_emit/, "faux 轮零外发留痕");
  assert.equal(issues.issues_opened, 0);
  const gates = JSON.parse(fs.readFileSync(path.join(dir, "gates.json"), "utf8"));
  assert.equal(gates.records.length, 6, "六步各一门留痕(appendGateBypass 降级旁路同入 records;P2-⑨ 原恒真 filter 删)");
  for (const rec of gates.records) assert.equal(rec.pass, true, `${rec.stage} 门红:${rec.reason}`);
  const budget = JSON.parse(fs.readFileSync(path.join(dir, "09-budget.json"), "utf8"));
  assert.equal(budget.readings.discover_channels.channels.web_read.calls, 1);
  const ledger = fs.readFileSync(path.join(tree.opsRoot, "ledger.md"), "utf8");
  assert.match(ledger, /pipeline-discover:2026-06-01-0400-discover/, "台账轮次行缺失");
  // #403:轮报告件入 packages/(UI「查看报告」面;命名=<date>-<type>-<HHMM>.md 保
  // pkgMatchesRow 前缀关联);#420 起结论先行+概览表——轮次/引擎折入标题/概览行,旧
  // 「轮次:/引擎:」行断言随之改向;结论行=分型工件确定性推导(d4 入队读数+issue 出口)。
  const pkgPath = path.join(tree.opsRoot, "packages", "2026-06-01-discover-0400.md");
  assert.ok(fs.existsSync(pkgPath), "#403:报告件未落 packages/(断供修复面)");
  const rep = fs.readFileSync(pkgPath, "utf8");
  assert.match(rep, /^# 运营轮报告 2026-06-01-0400-discover$/m, "#420:标题含轮次 id(旧轮次:行折入)");
  assert.match(rep, /^\*\*结论:发现轮入队 1\(跳过 1 \/ 标记 0\);issue 出口 skip\(开 0 \/ 败 0\)。\*\*$/m, "#420:结论先行(d4+enqueue-issues 确定性推导,不造数字)");
  assert.match(rep, /\| 类型 \| discover\(引擎 pipeline-v2/, "#420:概览类型行含引擎(旧引擎:行折入)");
  assert.match(rep, /\| SCAN \| done \|/, "相位表含 SCAN 行");
  assert.match(rep, /\| CLOSE \| done \| 0\.0s \|/, "评审 P2-1 → #420:用时列人读化,CLOSE dur_ms=0 → 0.0s(无时钟入文=幂等重写逐字节同;毫秒精确值在信封 stages,证据不灭失)");
  assert.match(rep, /## 门/, "门节在场");
  assert.match(rep, /候选宇宙:3\(registry=1 needs=2 web=0\)/, "分型读数=d1 实测计数(不造数字)");
  assert.match(rep, /## 信封/, "信封节在场(证据不灭失)");
  const fenced = rep.split("```json\n")[1]?.split("\n```")[0];
  assert.equal(JSON.parse(fenced).pipeline.round_id, ROUND, "信封 fenced JSON 可解析且 round_id 对上");
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});

test("#408 CLOSE 失败面终态:报告件写败(packages 被占为文件)→ 镜像 failed,stages 止于 RETRO", async () => {
  const tree = tmpTree("v2-disc-closefail-");
  fs.mkdirSync(tree.opsRoot, { recursive: true });
  fs.writeFileSync(path.join(tree.opsRoot, "packages"), "占位文件(writeRoundReport mkdir 即败)");
  try {
    const r = await runRound(tree);
    assert.equal(r.status, "failed", JSON.stringify(r));
    assert.match(r.error.message, /轮报告件写败/, "报告件 fail-loud 路径(#403 判例)是本测的失败注入面");
    const mirror = JSON.parse(fs.readFileSync(path.join(tree.opsRoot, "rounds", ROUND, "state.json"), "utf8"));
    assert.equal(mirror.status, "failed", "#408:close 相位失败出口镜像终态 failed(v1 failStage 同语义)");
    assert.deepEqual(mirror.stages, ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO"], "close 未成,镜像不造 CLOSE 名(宁少算)");
    fs.rmSync(tree.tmp, { recursive: true, force: true });
  } catch (e) { fs.rmSync(tree.tmp, { recursive: true, force: true }); throw e; }
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
  assert.equal(foreign.error.detail?.code, "bad_round", "建轮守卫域错经 finishFailed 落 detail.code(P0-①)");
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});

test("P0-① CLI 级跨库撞轮:失败信封 error.code=bad_round 非 infra(detail.code 塌缩修复)", async () => {
  const tree = tmpTree("v2-disc-cli-badround-");
  const env = { ...process.env, DOCS_ROOT: tree.docsRoot, LEDGER_FILE: path.join(tree.opsRoot, "ledger.md") };
  const run = (db) => execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ROUND, "--fixtures", FIXTURES, "--db", db], { env }).catch((e) => e);
  try {
    const r1 = await run(path.join(tree.tmp, "a.sqlite"));
    assert.equal(JSON.parse(r1.stdout.trim().split("\n").pop()).ok, true, "首轮应成功");
    const r2 = await run(path.join(tree.tmp, "b.sqlite")); // 换库=新任务撞已有轮目录
    assert.equal(r2.code, 1, `stderr:\n${r2.stderr ?? ""}`);
    const env2 = JSON.parse(r2.stdout.trim().split("\n").pop());
    assert.equal(env2.ok, false);
    assert.equal(env2.error.code, "bad_round", `真码应从 detail.code 透出而非 infra:\n${r2.stdout}`);
    assert.match(env2.error.message, /已存在/);
  } finally { fs.rmSync(tree.tmp, { recursive: true, force: true }); }
});

test("P0-⑥ run-discover --model 校验:缺斜杠/空段 → exit 2;real 面漏 --model → exit 2", async () => {
  const tree = tmpTree("v2-disc-model-");
  const env = { ...process.env, DOCS_ROOT: tree.docsRoot, LEDGER_FILE: path.join(tree.opsRoot, "ledger.md") };
  const run = (args) => execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ...args], { env }).catch((e) => e);
  try {
    assert.equal((await run([ROUND, "--model", "noprovider"])).code, 2, "--model 缺斜杠=用法错");
    assert.equal((await run([ROUND, "--model", "prov/"])).code, 2, "--model 空段=用法错");
    const r3 = await run([ROUND]); // real 面无 --model(不带 --fixtures)
    assert.equal(r3.code, 2, "real 面 --model 缺=用法错(原裸 Error 落 exit 3)");
    assert.equal(r3.stdout.trim(), "", "用法错不发信封");
  } finally { fs.rmSync(tree.tmp, { recursive: true, force: true }); }
});

test("P0-③ SHORTLIST empty_text 首败重试:attempt 即调用同计,attempts=2 后成", async () => {
  const tree = tmpTree("v2-disc-retry-");
  // 罐装短表首回合零文本块(empty_text 面)→ 重发新 requestId;次回合=原好回合
  const fxDir = path.join(tree.tmp, "fixtures");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const shortlist = JSON.parse(fs.readFileSync(path.join(fxDir, "shortlist.json"), "utf8"));
  fs.writeFileSync(path.join(fxDir, "shortlist.json"), JSON.stringify({ ...shortlist, turns: [{ role: "assistant", content: [] }, ...shortlist.turns] }));
  try {
    const r = await runRound(tree, path.join(tree.tmp, "v2.sqlite"), fxDir);
    assert.equal(r.status, "completed", JSON.stringify(r.error ?? r));
    const short = r.envelope.pipeline.stages.find((s) => s.name === "SHORTLIST");
    assert.equal(short.attempts, 2, "首败重试后第二轮成功");
    // 重试同计面:usageNow=会话累计(含失败回合)且仍过花费/预算门;模型调用计数在
    // 健康轮同型修复面断言(health-e2e:readings.model_calls 5)
    const budget = JSON.parse(fs.readFileSync(path.join(tree.opsRoot, "rounds", ROUND, "09-budget.json"), "utf8"));
    assert.equal(budget.readings.model_calls, 2, "失败 attempt 同计(旧律 budget.mjs:34)");
    fs.rmSync(tree.tmp, { recursive: true, force: true });
  } catch (e) { fs.rmSync(tree.tmp, { recursive: true, force: true }); throw e; }
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
  // T5 冻结面(stdout 末行=旧形信封):completed ⟺ ok:true(envelope.mjs 信封纪律)
  assert.equal(r.ok, true, JSON.stringify(r.error ?? r));
  assert.deepEqual(r.pipeline.stages.map((s) => s.name), ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"], "恢复后每步恰一次");
  fs.rmSync(tree.tmp, { recursive: true, force: true });
});
