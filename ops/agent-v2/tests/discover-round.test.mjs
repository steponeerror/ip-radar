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
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { runDiscoverRound, fauxBundle, RoundsDoc } from "../run-discover.mjs";
import { openHarness } from "../entry.mjs";
import { DISCOVERY_REPLAY, ensureRoundHost, roundHosts, executeDiscoveryTool } from "../tools/discovery-tools.mjs";
import { breakerFileOf } from "../../pipeline-core/pipeline/discovery-host.mjs";
import { parseBreakerState } from "../../pipeline-core/tools/breaker.mjs";

const execFile = promisify(execFileCb);
const HERE = path.resolve(import.meta.dirname, "..");
const FIXTURES = path.resolve(HERE, "..", "pipeline-core", "fixtures", "pipeline");
const ROUND = "2026-06-01-0400-discover";

function tmpTree(prefix) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  return { tmp, docsRoot: path.join(tmp, "docs"), opsRoot: path.join(tmp, "docs", "ops") };
}

// 任务侧 env=process.env 现读(旧律,buildCtx 注);in-proc 测试须同步设进程环境(于 finally 还原)。
// extraEnv=#415 旋钮/故障注入面(同进程环境,时限同本函数;凭证不入档律不破:只设测试旋钮)。
async function withRoundEnv(tree, extraEnv, fn) {
  const keys = ["DOCS_ROOT", "LEDGER_FILE", ...Object.keys(extraEnv)];
  const saved = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  process.env.DOCS_ROOT = tree.docsRoot;
  process.env.LEDGER_FILE = path.join(tree.opsRoot, "ledger.md");
  Object.assign(process.env, extraEnv);
  try { return await fn(); } finally {
    for (const k of keys) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}
async function runRound(tree, db, fixturesDir = FIXTURES, extraEnv = {}) { // fixturesDir 可覆盖(P0-③ 重试测:罐装短表首回合空文本)
  return withRoundEnv(tree, extraEnv, () => runDiscoverRound({
    roundId: ROUND,
    fixturesDir,
    dbPath: db ?? path.join(tree.tmp, "v2.sqlite"),
    env: { ...process.env },
    stderr: { write: () => true },
  }));
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

// ── #430 P3-6 可后补钉位:此前无测试到达的 SHORTLIST 终态出口逐条钉(注入=真实调用链上的
// 夹具/旋钮手术,零 mock;墙钟类出口按票面「诚实的测试写不出来宁可不写」不钉)──

test("#430 SHORTLIST 第二次 empty_text 出口:两回合皆空文本 → attempt 2 仍空 → 终态 empty_text,镜像 failed,stages=[SCAN]", async () => {
  const tree = tmpTree("v2-disc-empty2-");
  // 罐装短表两回合全零文本块(stopReason:"stop" 必须显式——无它 agent 循环不收口,第二回合
  // 变 submission_unanswered=另一出口;本测钉的是 empty_text 面):attempt 1 空文本走重发
  // (P0-③ 面),attempt 2 仍空 → shortlistSubmit 第二次 empty_text 出口(修前无测试到达)
  const fxDir = path.join(tree.tmp, "fixtures");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const shortlist = JSON.parse(fs.readFileSync(path.join(fxDir, "shortlist.json"), "utf8"));
  fs.writeFileSync(path.join(fxDir, "shortlist.json"), JSON.stringify({ ...shortlist, turns: [
    { role: "assistant", content: [], stopReason: "stop" }, { role: "assistant", content: [], stopReason: "stop" },
  ] }));
  try {
    const r = await runRound(tree, undefined, fxDir);
    assert.equal(r.status, "failed", JSON.stringify(r.error ?? r));
    assert.equal(r.error.message, "SHORTLIST:empty_text");
    assert.equal(r.error.detail?.code, "empty_text");
    assert.equal(r.error.detail?.stage, "SHORTLIST");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#430:第二次 empty_text=轮终态失败,镜像同写");
    assert.deepEqual(mirror.stages, ["SCAN"], "SHORTLIST 未成不造名");
    assert.equal(jsonOf(tree, "gates.json").records.at(-1).stage, "SCAN", "出口在门前:SHORTLIST 无门记录");
  } finally { rm(tree); }
});

// #430 评估记录:SHORTLIST postModelCall 花费帽红出口(④)在 faux 世界写不出诚实的 E2E,不钉。
// 实测卡点(2026-11-24,/tmp/gate430/probe-cost.mjs):pi-ai fauxProvider 活路径自算 usage 且
// cost 恒 0(罐装回合带 usage 只在 cloneMessage 回放面透传,活路径不读)→ 轮 usageNow.cost
// 恒 0,OPS_DISCOVER_SPEND_CAP_CNY 帽永不红。要钉得改 faux 活路径(pi-ai faux.js 把 cost 写死为 0、
// 从不调 calculateCost,给模型定义带费率表也没用——评审 P2-4)或新增花费注入缝;两者都不是夹具
// 手术,按票面「要大改不硬做」不钉。

test("#430 G_SHORTLIST 红出口:罐装 quote 改写(非证据面逐字 span)→ GATE:SHORTLIST → 镜像 failed,stages=[SCAN]", async () => {
  const tree = tmpTree("v2-disc-gshort-");
  // 夹具手术=最小:改 quote 一词破 span 逐字回引(d1-scan.json 罐装 _comment 自检面同款注入:
  // 「改 quote 或 text 即 span 门红」)
  const fxDir = path.join(tree.tmp, "fixtures");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const shortlist = JSON.parse(fs.readFileSync(path.join(fxDir, "shortlist.json"), "utf8"));
  const turns = shortlist.turns.map((t) => ({ ...t, content: (t.content ?? []).map((c) =>
    c.type === "text" ? { ...c, text: c.text.replace("月度全量 parquet", "月度 parquet") } : c) }));
  fs.writeFileSync(path.join(fxDir, "shortlist.json"), JSON.stringify({ ...shortlist, turns }));
  try {
    const r = await runRound(tree, undefined, fxDir);
    assert.equal(r.status, "failed", JSON.stringify(r.error ?? r));
    assert.match(r.error.message, /^GATE:SHORTLIST:/);
    assert.match(r.error.message, /quote 非证据面逐字 span/, "失败面=span 语义门本体(#208 T2 三负例的改写面)");
    const gates = jsonOf(tree, "gates.json").records;
    assert.equal(gates.at(-1).name, "G_SHORTLIST");
    assert.equal(gates.at(-1).pass, false, "门留痕=红");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#430:G_SHORTLIST 红=轮终态失败,镜像同写");
    assert.deepEqual(mirror.stages, ["SCAN"], "SHORTLIST 未成不造名");
  } finally { rm(tree); }
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

// ── #415 终态镜像覆盖全部终态出口(#408 评审 P3-1/P3-4/覆盖缺口)──────────────────────
// 面律:每条终态出口一条专项 E2E,断言镜像终态词 + stages 形状(已提交相位留痕、未成相位
// 不造名);注入点必须是真实调用链上的一环(预占工件路径让真步写真抛),不绕过被测出口。
const roundDirOf = (tree) => path.join(tree.opsRoot, "rounds", ROUND);
const mirrorOf = (tree) => JSON.parse(fs.readFileSync(path.join(roundDirOf(tree), "state.json"), "utf8"));
const jsonOf = (tree, f) => JSON.parse(fs.readFileSync(path.join(roundDirOf(tree), f), "utf8"));
const TILL_RETRO = ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO"]; // close 未成=镜像止于此(不造 CLOSE 名)
const rm = (tree) => fs.rmSync(tree.tmp, { recursive: true, force: true });

test("#415 close 步抛出口:09-budget.json 被占为目录 → CLOSE 步 EISDIR → 镜像 failed,stages 止于 RETRO", async () => {
  const tree = tmpTree("v2-disc-closethrow-");
  // 零缝注入:CLOSE 步(steps.mjs CLOSE→writeJson 裸 writeFileSync)写 09-budget.json 落到
  // 目录=EISDIR 抛——注入点=被测出口本体(步抛),门评估与报告写都没走到。
  fs.mkdirSync(path.join(roundDirOf(tree), "09-budget.json"), { recursive: true });
  try {
    const r = await runRound(tree);
    assert.equal(r.status, "failed", JSON.stringify(r));
    assert.match(r.error.message, /^CLOSE:EISDIR/, "失败面须是 CLOSE 步本体写 09-budget.json 抛(非报告写败/门红)");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#415:close 相位步抛=轮未成,镜像终态 failed");
    assert.deepEqual(mirror.stages, TILL_RETRO, "close 未成,镜像不造 CLOSE 名(宁少算)");
    assert.equal("stage" in mirror, false, "discover 镜像字段集稳定:终态写只改值不加 stage 键");
    const gates = jsonOf(tree, "gates.json").records;
    assert.equal(gates.at(-1).stage, "RETRO", "步抛在门前:CLOSE 无门记录(留痕面与镜像同口径)");
    assert.equal(fs.existsSync(path.join(tree.opsRoot, "packages")), false, "门前的出口不产报告件");
  } finally { rm(tree); }
});

test("#415 G_CLOSE 红出口:步后门前 09-budget 读数漂移(OPS_V2_FAULT=budget_drift 测试缝)→ GATE:CLOSE → 镜像 failed", async () => {
  const tree = tmpTree("v2-disc-gclose-");
  try {
    const r = await runRound(tree, undefined, FIXTURES, { OPS_V2_FAULT: "budget_drift" });
    assert.equal(r.status, "failed", JSON.stringify(r));
    assert.match(r.error.message, /^GATE:CLOSE:读数超帽:model_calls=/, "失败面须是 G_CLOSE 门红(门读盘上 09-budget.json 对拍帽)");
    const gates = jsonOf(tree, "gates.json").records;
    assert.equal(gates.at(-1).name, "G_CLOSE");
    assert.equal(gates.at(-1).pass, false, "门留痕=红");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#415:G_CLOSE 红=轮未成,镜像终态 failed");
    assert.deepEqual(mirror.stages, TILL_RETRO, "门红在 close 相位:镜像不造 CLOSE 名");
    // 被门读到的漂移件原样在盘(门存在的理由=工件漂移;证据不灭失)
    const budget = jsonOf(tree, "09-budget.json");
    assert.equal(budget.readings.model_calls, budget.env.OPS_DISCOVER_MAX_MODEL_CALLS + 1, "漂移读数=帽+1(注入面留盘可回算)");
    assert.equal(fs.existsSync(path.join(tree.opsRoot, "packages")), false, "门红出口不产报告件");
  } finally { rm(tree); }
});

test("#415 mid-round 步抛出口(MEASURE):d3-measure.json 被占为目录 → MEASURE:EISDIR → 镜像 failed,stages=[SCAN,SHORTLIST]", async () => {
  const tree = tmpTree("v2-disc-midthrow-");
  fs.mkdirSync(path.join(roundDirOf(tree), "d3-measure.json"), { recursive: true }); // 零缝注入(同 close 步抛)
  try {
    const r = await runRound(tree);
    assert.equal(r.status, "failed", JSON.stringify(r));
    assert.match(r.error.message, /^MEASURE:EISDIR/, "失败面须是 MEASURE 步本体写 d3 抛");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#415:mid-round 失败出口镜像终态 failed(修前=任务已 failed、镜像停在 running)");
    assert.deepEqual(mirror.stages, ["SCAN", "SHORTLIST"], "已提交相位留痕;MEASURE 未成不造名(宁少算)");
    assert.equal("stage" in mirror, false, "discover 镜像字段集稳定");
    assert.equal(fs.existsSync(path.join(roundDirOf(tree), "09-budget.json")), false, "轮止于 MEASURE:后续相位工件不产");
  } finally { rm(tree); }
});

test("#415 mid-round 预算墙出口(SHORTLIST 第 2 attempt 提交前):调用帽 1 → budget_exceeded → 镜像 failed,stages=[SCAN]", async () => {
  const tree = tmpTree("v2-disc-midbudget-");
  // 罐装短表首回合零文本(P0-③ 同面)+调用帽 1:attempt 1 耗掉唯一一次调用 → attempt 2
  // 提交前 preModelCall ①③ 拦(shortlistSubmit 出口,带 ctx 的失败面)
  const fxDir = path.join(tree.tmp, "fixtures");
  fs.cpSync(FIXTURES, fxDir, { recursive: true });
  const shortlist = JSON.parse(fs.readFileSync(path.join(fxDir, "shortlist.json"), "utf8"));
  fs.writeFileSync(path.join(fxDir, "shortlist.json"), JSON.stringify({ ...shortlist, turns: [{ role: "assistant", content: [] }, ...shortlist.turns] }));
  try {
    const r = await runRound(tree, undefined, fxDir, { OPS_DISCOVER_MAX_MODEL_CALLS: "1" });
    assert.equal(r.status, "failed", JSON.stringify(r));
    assert.equal(r.error.detail?.code, "budget_exceeded");
    assert.equal(r.error.detail?.stage, "SHORTLIST");
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "failed", "#415:提交前预算墙=轮终态失败,镜像同写");
    assert.deepEqual(mirror.stages, ["SCAN"], "SHORTLIST 未成不造名");
    assert.equal(mirror.budget_knobs.maxModelCalls, 1, "镜像保轮始冻结旋钮(终态写只改 status,盘上件其余原样)");
  } finally { rm(tree); }
});

test("#415 属主校验:异物任务(跨库撞已有轮目录)的失败出口不改判别轮终态镜像;未建轮的失败出口不凭空造件", async () => {
  const tree = tmpTree("v2-disc-owned-");
  const first = await runRound(tree, path.join(tree.tmp, "a.sqlite"));
  assert.equal(first.status, "completed");
  const snapshot = () => { const m = mirrorOf(tree); return [m.status, m.stages.join(",")]; };
  const before = snapshot();
  assert.deepEqual(before, ["done", "SCAN,SHORTLIST,MEASURE,ENQUEUE,RETRO,CLOSE"], "前提:首轮终态镜像");
  try {
    // ① 建轮守卫拦截(bad_round):盘上是别轮终态件 → 不写(写了=把别轮 done 改判 failed)
    const foreign = await runRound(tree, path.join(tree.tmp, "b.sqlite"));
    assert.equal(foreign.error.detail?.code, "bad_round");
    assert.deepEqual(snapshot(), before, "bad_round 出口不得改判别轮终态镜像");
    // ② 首相位头预算墙(建轮守卫之前;#415 前零 ctx 可判的出口形):同上不改判
    const walled = await runRound(tree, path.join(tree.tmp, "c.sqlite"), FIXTURES, { OPS_DISCOVER_WALL_CLOCK_S: "0" });
    assert.equal(walled.status, "failed", JSON.stringify(walled));
    assert.equal(walled.error.detail?.code, "wall_clock_exceeded", "注入面=相位头墙钟执法(帽 0=零预算即拒)");
    assert.deepEqual(snapshot(), before, "撞轮目录的异物任务预算墙出口不得改判别轮终态镜像");
  } finally { rm(tree); }
  // ③ 未建轮(全新树)首相位头预算墙:无件不造
  const fresh = tmpTree("v2-disc-owned-fresh-");
  try {
    const r = await runRound(fresh, undefined, FIXTURES, { OPS_DISCOVER_WALL_CLOCK_S: "0" });
    assert.equal(r.error.detail?.code, "wall_clock_exceeded");
    assert.equal(fs.existsSync(path.join(fresh.opsRoot, "rounds", ROUND)), false, "未过建轮守卫的失败出口不凭空造轮目录/镜像");
  } finally { rm(fresh); }
  // ④ 首相位步抛(骨架已写、零相位提交=属主校验第二支):自家骨架要写——否则状态文件停在 running 说谎
  const skeleton = tmpTree("v2-disc-owned-skel-");
  fs.mkdirSync(path.join(roundDirOf(skeleton), "d1-scan.json"), { recursive: true });
  try {
    const r = await runRound(skeleton);
    assert.match(r.error.message, /^SCAN:EISDIR/, JSON.stringify(r));
    const m = mirrorOf(skeleton);
    assert.equal(m.status, "failed", "#415:首相位步抛=轮终态失败,自家骨架镜像要写终态");
    assert.deepEqual(m.stages, [], "零相位提交:stages 空不造名");
  } finally { rm(skeleton); }
});

test("#415 中止出口:相位头崩溃的任务被 abortTask → outcome aborted,镜像 aborted(stages=已提交相位)", async () => {
  const tree = tmpTree("v2-disc-abort-");
  const db = path.join(tree.tmp, "v2.sqlite");
  // 第一段:子进程 CLI 在 shortlist 相位头 SIGKILL(crashHook 测试缝;上一相位 checkpoint 已提交)
  const env = { ...process.env, DOCS_ROOT: tree.docsRoot, LEDGER_FILE: path.join(tree.opsRoot, "ledger.md"), OPS_V2_CRASH_AFTER_PHASE: "shortlist" };
  try {
    const kill = await execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ROUND, "--fixtures", FIXTURES, "--db", db], { env }).catch((e) => e.code);
    assert.equal(kill, null, `SIGKILL 期望进程被杀(exit code ${kill} 非自杀)`);
    assert.equal(mirrorOf(tree).status, "running", "前提:崩溃后镜像停在 running(进度镜像)");
    // 第二段:同库开 harness,对在飞任务下中止标记 → abort 相位(真框架路径,零 mock)
    await withRoundEnv(tree, {}, async () => {
      const context = BACKGROUND_CONTEXT;
      const { harness } = await openHarness({ dbPath: db, models: await fauxBundle(FIXTURES) });
      try {
        const taskId = (await harness.snapshot(RoundsDoc, context)).rounds[ROUND].taskId;
        assert.equal(await harness.abortTask(taskId, context), "marked", "在飞任务应可下中止标记");
        const settled = await harness.waitForTask(taskId, context);
        assert.equal(settled.state.outcome?.status, "aborted", `中止终态应落:${JSON.stringify(settled.state.outcome)}`);
      } finally { await harness.close(context); }
    });
    const mirror = mirrorOf(tree);
    assert.equal(mirror.status, "aborted", "#415:中止=任务终态,镜像同词 aborted(修前=镜像停在 running)");
    assert.deepEqual(mirror.stages, ["SCAN"], "中止时已提交相位留痕;shortlist 未成不造名");
  } finally { rm(tree); }
});

test("#415 中止镜像写尽力不掷错:abort 相位 ctx 重建抛(中止进程 breaker 旋钮非法)→ outcome 仍 aborted,镜像原样不改判", async () => {
  const tree = tmpTree("v2-disc-abortthrow-");
  const db = path.join(tree.tmp, "v2.sqlite");
  // 第一段:同上,子进程 CLI 在 shortlist 相位头 SIGKILL,任务停在在飞
  const env = { ...process.env, DOCS_ROOT: tree.docsRoot, LEDGER_FILE: path.join(tree.opsRoot, "ledger.md"), OPS_V2_CRASH_AFTER_PHASE: "shortlist" };
  try {
    const kill = await execFile(process.execPath, [path.join(HERE, "run-discover.mjs"), ROUND, "--fixtures", FIXTURES, "--db", db], { env }).catch((e) => e.code);
    assert.equal(kill, null, `SIGKILL 期望进程被杀(exit code ${kill} 非自杀)`);
    const stateFile = path.join(roundDirOf(tree), "state.json");
    const before = fs.readFileSync(stateFile, "utf8");
    // 第二段:中止在一个 breaker 旋钮非法的进程环境里执行(env 现读不入档=执行中止的进程
    // 环境可与轮进程不同)→ abort 相位的 buildCtx→readBreakerKnobs 抛 usage 错=ctx 重建
    // 失败的真实调用链(零 mock)。镜像写不得反过来改判任务终态:outcome 仍是 aborted;
    // 写败=宁少算,进度镜像字节原样。
    const notes = [];
    const realWrite = process.stderr.write;
    await withRoundEnv(tree, { OPS_BREAKER_THRESHOLD: "不是数" }, async () => {
      process.stderr.write = (chunk, ...rest) => { notes.push(String(chunk)); return realWrite.call(process.stderr, chunk, ...rest); };
      const context = BACKGROUND_CONTEXT;
      const { harness } = await openHarness({ dbPath: db, models: await fauxBundle(FIXTURES) });
      try {
        const taskId = (await harness.snapshot(RoundsDoc, context)).rounds[ROUND].taskId;
        assert.equal(await harness.abortTask(taskId, context), "marked", "在飞任务应可下中止标记");
        const settled = await harness.waitForTask(taskId, context);
        assert.equal(settled.state.outcome?.status, "aborted", `中止终态不得被镜像写败吃掉(修前=abort 相位裸抛 → 任务判 faulted、aborted outcome 丢失):${JSON.stringify(settled.state.outcome)}`);
      } finally { await harness.close(context); }
    }).finally(() => { process.stderr.write = realWrite; });
    assert.equal(fs.readFileSync(stateFile, "utf8"), before, "镜像写败=宁少算:进度镜像字节原样(不造 aborted 件=不以未证之词入文)");
    assert.ok(notes.some((l) => l.includes("中止镜像写败") && l.includes("OPS_BREAKER_THRESHOLD")), `写败须留 stderr 注记:${notes.join("")}`);
  } finally { rm(tree); }
});
