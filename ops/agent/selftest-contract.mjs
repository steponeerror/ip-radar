#!/usr/bin/env node
// selftest-contract.mjs — Task 1 spawn 契约三层测试(零 API:faux 或前置-throw 两路)。
// a. 契约表双向对拍:SPAWN_CONTRACT_ENV ↔ 生产文件真读(agent/tools/models 的 process.env.X
//    + 计算读取按轮次闭集展开 + models.mjs envApiKeyAuth 声明 key + lib.sh ${VAR:-} 侧名);
//    GH_TOKEN 豁免(gh CLI 自读);PI_BIN/RUN_PI_RAW_OUT 出界钉死(已退役 run_pi 的 fixture 面;T3 删尽后名灭,禁入表断言留作防复活绊线)。
// b. in-process main(faux provider,golden 同型):成功轮单行 JSON 轮次信封逐字段 + stderr 进度行;
//    失败轮 code=model_face/empty_text 信封(pkg 缺席)+ closure_check 带 pkg 信封(reviewer
//    Minor-1,T2:包已落盘的失败面必须回传工件——轮次失败≠工件灭失,P2 消费面)。
// c. 真 spawn 冒烟(badround 前置 throw / 用法错 exit 2):两路都在 loadModels 之前,不触网不读模型目录。
// 输出行 CONTRACTPASS/CONTRACTFAIL,selftest.sh §11 计数;任一 FAIL 退出非零。
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFileCb);
const AGENT = path.dirname(fileURLToPath(import.meta.url));
let pass = 0, fail = 0;
const ok = (name) => { pass++; console.log(`CONTRACTPASS ${name}`); };
const bad = (name, err) => { fail++; console.log(`CONTRACTFAIL ${name}: ${err}`); };
async function t(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } }

const src = (f) => fs.readFileSync(path.join(AGENT, f), "utf8");
const SRCS = { agent: src("agent.mjs"), tools: src("tools.mjs"), models: src("models.mjs"), libsh: src("lib.sh"),
  // P2 P0(spec #161):pipeline 面入扫描——OPS_PIPELINE/OPS_PIPELINE_BUDGET_CNY 的真读取方在
  // pipeline.mjs(值闭集校验/预算门);对拍不变式(表内每项真被读/读取∈表)延展覆盖
  pipeline: src("pipeline.mjs"), pipelineSteps: src("pipeline/steps.mjs"),
  pipelineGates: src("pipeline/gates.mjs"), pipelineFaux: src("pipeline/faux.mjs"),
  // 票 #199 交付A(P15 预算四界):旋钮单源读面入扫描——六 OPS_PIPELINE_* 真读方在
  // budget.mjs readBudgetKnobs(引擎检查点/双面准入/调用哈希同面)
  pipelineBudget: src("pipeline/budget.mjs"),
  // 票 #184(finding 出口三件套):出口模块入扫描——OPS_SWEEP_DRY_RUN/IP_RADAR_ALERT_URLS 真读方
  pipelineFindingExit: src("pipeline/finding-exit.mjs"),
  // 票 #195(C6 tools.mjs 分层):面文件入扫描——env 读取面(DOCS_ROOT/OPS_EVAL_PY/
  // OPS_DATA_DIR/OPS_FETCH_MAX_BYTES/OPS_PROBE_* 等)真读方自 tools.mjs 移入
  // tools/shared.mjs;对拍不变式(表内每项真被读/读取∈表)随面延展覆盖
  toolsShared: src("tools/shared.mjs"), toolsEnvelope: src("tools/envelope.mjs"),
  toolsRegistry: src("tools/registry.mjs"), toolsPrecedents: src("tools/precedents.mjs"),
  toolsMeasurement: src("tools/measurement.mjs"), toolsDiscovery: src("tools/discovery.mjs"),
  // 票 #199 交付B(P16 跨轮熔断):旋钮单源读面入扫描——OPS_BREAKER_* 真读方在
  // tools/breaker.mjs readBreakerKnobs(宿主接线/09-budget.json 快照同面)
  toolsBreaker: src("tools/breaker.mjs"),
  // #139 挂账②:锁基建入扫描(零 env 读取,现状无表项;未来若读 env 会被
  // 「读取∈表」不变式拦下,防静默扩面)
  toolsQueueLock: src("tools/queue-lock.mjs") };

// ── fixture(in-process 用;golden writePrecedents 同型:env 先于 agent.mjs import)──
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "contract-selftest-"));
const DOCS = path.join(TMP, "docs");
const PREC = "2026-06-01-contract-fixture.md";
const precDir = path.join(DOCS, "ops", "precedents");
fs.mkdirSync(precDir, { recursive: true });
fs.writeFileSync(path.join(precDir, PREC),
  `---\nid: 2026-06-01-contract-fixture\ndate: 2026-06-01\nsubject: fixture — 契约测试判例(排他率命中)\ncontext: >\n  契约回放 fixture。\nhuman_ruling: >\n  认可。\nreward:\n  hard_gates: {}\n  ruling_agreement: agreed\n---\n\n正文检索词:排他率 聚合器 冻结。\n`);
fs.writeFileSync(path.join(precDir, "_schema.md"), "schema 说明(注入排除面)。\n");
// 闭集外真文件(reviewer Minor-1 fixture):库内真实存在(存在性校验过)但正文检索词
// 刻意避开 KWS.discover 全部词(排他率/聚合器/许可/体量/冻结/sunset)→ 永不进闭集,
// 收口时闭集成员校验(tools.mjs closureCheck)抛错——引它 = closure_check 失败面。
// 不能引纯编造路径:那会先撞 lib.sh 存在性层(verify_failed),到不了闭集层。
const UNINJ = "2026-05-01-contract-uninjected.md";
fs.writeFileSync(path.join(precDir, UNINJ),
  `---\nid: 2026-05-01-contract-uninjected\ndate: 2026-05-01\nsubject: fixture — 闭集外真文件(closure_check 面)\ncontext: >\n  库内存在但检索不命中:存在性过、闭集拦。\nhuman_ruling: >\n  认可。\nreward:\n  hard_gates: {}\n  ruling_agreement: agreed\n---\n\n正文检索词:裁决 回放。\n`);
process.env.DOCS_ROOT = DOCS; // tools.mjs import 期读 docs 根——必须先于 import
process.env.PRECEDENTS_DIR = precDir;
process.env.LEDGER_FILE = path.join(DOCS, "ops", "ledger.md");

const mod = await import("./agent.mjs");
const main = mod.main;
const SPAWN_CONTRACT_ENV = mod.SPAWN_CONTRACT_ENV;
const ERROR_CODES = mod.ERROR_CODES;

// ── a. 契约表双向对拍 ─────────────────────────────────────────────────────
const computeReads = () => {
  const reads = new Set();
  let unknownTemplate = null;
  for (const s of [SRCS.agent, SRCS.tools, SRCS.models, SRCS.pipeline, SRCS.pipelineSteps, SRCS.pipelineGates, SRCS.pipelineFaux, SRCS.pipelineBudget, SRCS.pipelineFindingExit, SRCS.toolsShared, SRCS.toolsEnvelope, SRCS.toolsRegistry, SRCS.toolsPrecedents, SRCS.toolsMeasurement, SRCS.toolsDiscovery, SRCS.toolsBreaker, SRCS.toolsQueueLock]) {
    for (const m of s.matchAll(/process\.env\.([A-Za-z_][A-Za-z0-9_]*)/g)) reads.add(m[1]);
    // 方括号字符串读形(reviewer Minor-2,T2):process.env["QUOTED_NAME"]/['X']——与点形
    // 同名集并入对拍;引号族与反引号族(下方)互不重叠。动态下标读形 process.env[expr]
    // 为已声明盲区(现存为零,需作用域感知扫描,词法正则会误收)。
    for (const m of s.matchAll(/process\.env\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]/g)) reads.add(m[1]);
    // 计算读取(models.mjs:`process.env[`OPS_MODEL_${round.toUpperCase()}`]`)按轮次闭集展开
    for (const m of s.matchAll(/process\.env\[\s*`([^`]+)`\s*\]/g)) {
      const mm = m[1].match(/^([A-Z_]+)\$\{round\.toUpperCase\(\)\}$/);
      if (!mm) { unknownTemplate = m[1]; continue; }
      for (const r of ["health", "discover"]) reads.add(mm[1] + r.toUpperCase()); // argv 轮次闭集(冻结)
    }
  }
  // envApiKeyAuth 声明式 env key(pi-ai 请求期读;models.mjs 不直写 process.env.X)
  for (const m of SRCS.models.matchAll(/envApiKeyAuth\(\s*"[^"]+"\s*,\s*\[\s*"([A-Za-z_][A-Za-z0-9_]*)"/g)) reads.add(m[1]);
  // JS 解构形 `const { X } = process.env` 为已声明盲区(reviewer Minor-2):现存为零,
  // 需作用域感知扫描,词法正则会误收局部解构——零现状下收录成本>收益,注释钉界。
  // lib.sh 的 bash 侧名:${VAR:-...} 形(env 可覆盖面;限大写——${epoch:-} 是局部变量
  // 不是 env 面);:= 赋默认 / :? 出错退出变体(Minor-2)同属 env 覆盖面,一并收录
  // (现存为零,收录即防未来漂入时漏对拍)。
  for (const m of SRCS.libsh.matchAll(/\$\{([A-Z][A-Z0-9_]*)(?::-|:=|:\?)/g)) reads.add(m[1]);
  return { reads, unknownTemplate };
};
const READS = computeReads();
const tableNames = () => new Set((SPAWN_CONTRACT_ENV ?? []).map((e) => e?.name));

await t("导出面:main(argv,io)/SPAWN_CONTRACT_ENV/ERROR_CODES 可导入", () => {
  assert.equal(typeof main, "function", "main 应为导出函数");
  assert.ok(Array.isArray(SPAWN_CONTRACT_ENV), "SPAWN_CONTRACT_ENV 非数组");
  assert.ok(Array.isArray(ERROR_CODES), "ERROR_CODES 非数组");
});

await t("表对拍:扫描器收录的 env 读取面(计算模板无未知形)", () => {
  assert.equal(READS.unknownTemplate, null, `未收录的 process.env[··] 计算读取模板,对拍器需同步`);
});

await t("表:SPAWN_CONTRACT_ENV 名集=规格 16 项+…(增补链见 agent.mjs 注;#199 交付A 尾部再追 OPS_PIPELINE_MAX_MODEL_CALLS/OPS_PIPELINE_TOKEN_BUDGET/OPS_PIPELINE_WALL_CLOCK_S/OPS_PIPELINE_SPEND_CAP_CNY/OPS_PIPELINE_MONTHLY_CAP_CNY/OPS_PIPELINE_DUP_CALL_LIMIT——pipeline/budget.mjs readBudgetKnobs 单源实读;#207 T1 再追 OPS_DISCOVER_MAX_MODEL_CALLS/OPS_DISCOVER_WALL_CLOCK_S/OPS_DISCOVER_SPEND_CAP_CNY——readDiscoverKnobs 单源实读,月帽共享不另立行)", () => {
  assert.deepEqual([...tableNames()].sort(), ["DOCS_ROOT", "GH_TOKEN", "IP_RADAR_ALERT_URLS", "JINA_API_KEY", "LEDGER_FILE", "OPS_ANCHOR_SWEEP_TIMEOUT_MS", "OPS_AUTH", "OPS_DATA_DIR",
    "OPS_EVAL_PY", "OPS_FETCH_MAX_BYTES", "OPS_MATRIX_TIMEOUT_MS", "OPS_MODELS", "OPS_MODEL_DISCOVER",
    "OPS_MODEL_HEALTH", "OPS_MODELS_STORE", "OPS_PIPELINE", "OPS_PIPELINE_BUDGET_CNY", "OPS_PROBE_CLI_TIMEOUT_MS",
    "OPS_PROBE_MAX_BYTES", "OPS_PROBE_MAX_KEYS", "OPS_SWEEP_DRY_RUN", "PI_CODING_AGENT_DIR",
    "PRECEDENTS_DIR", "ZAI_CODING_CN_API_KEY",
    "OPS_PIPELINE_MAX_MODEL_CALLS", "OPS_PIPELINE_TOKEN_BUDGET", "OPS_PIPELINE_WALL_CLOCK_S",
    "OPS_PIPELINE_SPEND_CAP_CNY", "OPS_PIPELINE_MONTHLY_CAP_CNY", "OPS_PIPELINE_DUP_CALL_LIMIT",
    "OPS_DISCOVER_MAX_MODEL_CALLS", "OPS_DISCOVER_WALL_CLOCK_S", "OPS_DISCOVER_SPEND_CAP_CNY", // #207 T1 发现轮三旋钮
    "OPS_BREAKER_THRESHOLD", "OPS_BREAKER_COOLDOWN_S"].sort()); // #199 交付B:tools/breaker.mjs readBreakerKnobs 单源实读
});

await t("表:元素形状 {name,default,consumer,phase}/phase 闭集/名唯一", () => {
  const names = (SPAWN_CONTRACT_ENV ?? []).map((e) => e?.name);
  assert.equal(new Set(names).size, names.length, "名重复");
  for (const e of SPAWN_CONTRACT_ENV) {
    for (const k of ["name", "default", "consumer", "phase"]) assert.equal(typeof e[k], "string", `${e.name}.${k} 非字符串`);
    assert.ok(["import-time", "call-time"].includes(e.phase), `${e.name}.phase=${e.phase} 不在闭集`);
  }
});

await t("表对拍:表内每项真被读(GH_TOKEN/JINA_API_KEY/PI_CODING_AGENT_DIR 豁免——外部自读:gh CLI/pi-web-access 包在子进程读,tools.mjs 不读)", () => {
  const EXTERN = new Set(["GH_TOKEN", "JINA_API_KEY", "PI_CODING_AGENT_DIR"]); // PR3a 后两名同 GH_TOKEN 豁免型
  const missing = [...tableNames()].filter((n) => !EXTERN.has(n) && !READS.reads.has(n));
  assert.deepEqual(missing, [], "表内名字无人读(死表项)");
});

await t("表对拍:OPS_*|ZAI_*|DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE 读取 ∈ 表;PI_BIN/RUN_PI_RAW_OUT 出界钉死", () => {
  const nsRe = /^(OPS_|ZAI_)/;
  const named = new Set(["DOCS_ROOT", "PRECEDENTS_DIR", "LEDGER_FILE"]);
  for (const n of READS.reads) {
    if (n === "PI_BIN" || n === "RUN_PI_RAW_OUT") continue; // 已退役 run_pi 的 fixture 面(T3 删尽,名灭;此行为防御性残留,断言保留作绊线)
    if (nsRe.test(n) || named.has(n)) assert.ok(tableNames().has(n), `${n} 被读但不在 SPAWN_CONTRACT_ENV`);
  }
  assert.ok(!tableNames().has("PI_BIN") && !tableNames().has("RUN_PI_RAW_OUT"), "fixture 面名字不得入表");
});

await t("表:error.code 闭集 14 词(ERROR_CODES 导出面;#199 交付A 9→13,交付B 13→14 channel_open)", () => {
  assert.deepEqual([...ERROR_CODES].sort(), ["bad_round", "closure_check", "empty_text", "foreign_tool", "infra",
    "ledger_failed", "model_face", "sandbox_violation", "verify_failed",
    "budget_exceeded", "wall_clock_exceeded", "budget_monthly", "repeat_storm", "channel_open"].sort());
});

// ── b. in-process main(faux provider,golden 同型;零 API)──────────────────
const { fauxProvider, fauxAssistantMessage, fauxToolCall, fauxText, fauxThinking, createModels } =
  await import("@earendil-works/pi-ai");
const fauxIO = (turns) => {
  const faux = fauxProvider({ models: [{ id: "faux-contract" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses(turns);
  return { models: { models, resolve: () => faux.getModel() } };
};
const mkIO = () => {
  const buf = { stdout: "", stderr: "" };
  return {
    stdout: { write: (s) => { buf.stdout += s; return true; } },
    stderr: { write: (s) => { buf.stderr += s; return true; } },
    buf,
  };
};
const singleLineJSON = (s) => {
  const lines = s.split("\n");
  assert.equal(lines.length, 2, `stdout 应恰一行+末尾换行,实得 ${lines.length - 1} 行:${JSON.stringify(s.slice(0, 200))}`);
  assert.equal(lines[1], "", "stdout 末尾应恰一个换行");
  return JSON.parse(lines[0]);
};
const successTurns = () => [
  fauxAssistantMessage([fauxToolCall("search_precedents", { keywords: ["排他率"] }, { id: "call_sp1" })], { stopReason: "toolUse" }),
  // 票 #142 stderr 修约锚例:fetch_url 私网字面量 → SSRF 拒绝(零网络,guardHop
  // 先于连接抛)→ [tool-result] fail code=ssrf 完成行断言面。
  fauxAssistantMessage([fauxToolCall("fetch_url", { url: "http://127.0.0.1:9/x", method: "HEAD" }, { id: "call_ff1" })], { stopReason: "toolUse" }),
  fauxAssistantMessage([fauxText(`## 注入判例\n- ${PREC}\n\n## 摘要\n契约回放:stdout 单行 JSON 轮次信封。`)]),
];

await t("in-process:成功轮 stdout 单行 JSON 轮次信封(ok/round/pkg/usage/queue_writes/verify 逐字段)", async () => {
  const io = mkIO();
  const rc = await main(["discover", "契约回放:stdout 单行 JSON 信封"], { ...io, ...fauxIO(successTurns()) });
  assert.equal(rc, 0);
  const env = singleLineJSON(io.buf.stdout);
  assert.equal(env.ok, true);
  assert.equal(env.round, "discover");
  assert.deepEqual(Object.keys(env).sort(), ["ok", "pkg", "queue_writes", "round", "usage", "verify"]);
  assert.ok(path.isAbsolute(env.pkg) && fs.existsSync(env.pkg), `pkg 应绝对路径且真存在:${env.pkg}`);
  for (const k of ["input", "output", "totalTokens", "cost"]) assert.equal(typeof env.usage[k], "number", `usage.${k} 应数字`);
  assert.deepEqual(env.queue_writes, []);
  assert.deepEqual(env.verify, { ok: true, cited: 1 });
});

await t("in-process:成功轮 stderr 横幅+usage/verify 行+[turn]/[tool] 进度行(格式钉现状)", async () => {
  const io = mkIO();
  await main(["discover", "契约回放:stderr 进度行"], { ...io, ...fauxIO(successTurns()) });
  const se = io.buf.stderr;
  assert.match(se, /round: discover 完成 → /, "完成横幅(stderr)");
  assert.match(se, /usage: in=\d+ out=\d+ total=\d+ cost=/, "usage 行(stderr)");
  assert.match(se, /verify_cited_precedents: 1 条判例路径全部存在/, "verify 消息(stderr)");
  assert.match(se, /\[turn \d+\] stopReason=/, "[turn] 进度行");
  assert.match(se, /\[tool\] search_precedents\(call_sp1\)/, "[tool] 进度行");
  assert.ok(!io.buf.stdout.includes("完成"), "横幅不得留在 stdout");
});

// 票 #142 stderr 修约:[tool] 行带参数一行摘要(看得出在查什么)+ [tool-result] 完成行
// (成功带关键读数 / 失败带 code)。参数摘要与读数 = 工具闭集逐一的人读关键位,
// 锚例覆盖两极:成功读数(search_precedents hits)与失败码(fetch_url SSRF)。
await t("in-process:[tool] 行含参数摘要 + [tool-result] 完成行(ok 读数/fail code)", async () => {
  const io = mkIO();
  await main(["discover", "契约回放:工具行参数摘要"], { ...io, ...fauxIO(successTurns()) });
  const se = io.buf.stderr;
  assert.match(se, /\[tool\] search_precedents\(call_sp1\) 排他率/, "[tool] 参数摘要行(关键词拼接)");
  assert.match(se, /\[tool-result\] search_precedents\(call_sp1\) ok hits=1/, "[tool-result] ok 行带关键读数");
  assert.match(se, /\[tool\] fetch_url\(call_ff1\) HEAD http:\/\/127\.0\.0\.1:9\/x/, "[tool] fetch_url 参数摘要(method+url)");
  assert.match(se, /\[tool-result\] fetch_url\(call_ff1\) fail code=ssrf/, "[tool-result] fail 行带 code");
});

await t("in-process:失败轮 model_face(stopReason=error)信封+pkg 缺席", async () => {
  const io = mkIO();
  const rc = await main(["discover", "失败面回放"], {
    ...io, ...fauxIO([fauxAssistantMessage([fauxText("部分文本")], { stopReason: "error", errorMessage: "faux 模型失败面" })]),
  });
  assert.equal(rc, 1);
  const env = singleLineJSON(io.buf.stdout);
  assert.equal(env.ok, false);
  assert.equal(env.round, "discover");
  assert.deepEqual(Object.keys(env).sort(), ["error", "ok", "round"], "pkg 未落盘不得带");
  assert.equal(env.error.code, "model_face");
  assert.match(env.error.message, /模型失败面 stopReason=error/);
  assert.ok(io.buf.stderr.includes("round 失败:"), "失败原因行(stderr)");
});

await t("in-process:失败轮 empty_text(最终文本为空)信封", async () => {
  const io = mkIO();
  const rc = await main(["discover", "失败面回放"], { ...io, ...fauxIO([fauxAssistantMessage([fauxThinking("只有思考无正文")])]) });
  assert.equal(rc, 1);
  const env = singleLineJSON(io.buf.stdout);
  assert.equal(env.ok, false);
  assert.equal(env.error.code, "empty_text");
  assert.equal(env.error.message, "最终文本为空");
});

// reviewer Minor-1(T2):closure_check 带 pkg 失败信封——钉「轮次失败≠工件灭失」主承诺面(P2 消费方要的正是它)。
// 判据分界:引用必须真实在盘但闭集外——纯编造路径会先撞 lib.sh 存在性层(verify_failed),
// 到不了闭集层;golden neg3 同机制(「存在性校验通过,闭集成员校验抛错」)。fixture 专设
// 闭集外真文件 UNINJ(库内存在、检索词不命中 KWS,永不进闭集)。
await t("in-process:失败轮 closure_check 带 pkg(包已落盘,失败信封必须回传工件)", async () => {
  const io = mkIO();
  const rc = await main(["discover", "失败面回放:引用闭集外真文件"], {
    ...io, ...fauxIO([fauxAssistantMessage([fauxText(`## 注入判例\n- ${UNINJ}\n\n## 摘要\n契约回放:closure_check 失败面。`)])]),
  });
  assert.equal(rc, 1);
  const env = singleLineJSON(io.buf.stdout);
  assert.equal(env.ok, false);
  assert.equal(env.error.code, "closure_check");
  assert.deepEqual(Object.keys(env).sort(), ["error", "ok", "pkg", "round"], "包已落盘:失败信封必须带 pkg");
  assert.ok(typeof env.pkg === "string" && path.isAbsolute(env.pkg) && fs.existsSync(env.pkg), `pkg 应绝对路径且真在盘:${env.pkg}`);
  assert.ok(io.buf.stderr.includes("round 失败:"), "失败原因行(stderr)");
});

// ── c. 真 spawn 冒烟(前置-throw 两路;loadModels 之前,零 API 零网)─────────
// env 参数(2026-10-24):委派死锁回归需向子进程注入 OPS_PIPELINE/OPS_PIPELINE_BUDGET_CNY。
const spawnAgent = (args, env = {}) => execFileP(process.execPath, [path.join(AGENT, "agent.mjs"), ...args],
  { timeout: 60_000, env: { ...process.env, ...env } })
  .then(({ stdout, stderr }) => ({ rc: 0, stdout, stderr }))
  .catch((e) => ({ rc: typeof e.code === "number" ? e.code : -1, stdout: e.stdout ?? "", stderr: e.stderr ?? "" }));

await t("spawn:badround exit 1 + stdout 单行 JSON code=bad_round", async () => {
  const r = await spawnAgent(["badround", "x"]);
  assert.equal(r.rc, 1);
  const env = singleLineJSON(r.stdout);
  assert.equal(env.ok, false);
  assert.equal(env.round, "badround");
  assert.equal(env.error.code, "bad_round");
  assert.match(r.stderr, /轮次必须是 health\|discover/);
});

await t("spawn:用法错 exit 2 + stdout 空纯 stderr", async () => {
  const r = await spawnAgent([]);
  assert.equal(r.rc, 2);
  assert.equal(r.stdout, "", "用法错不发 JSON");
  assert.match(r.stderr, /用法:/);
});

// 2026-10-24 委派死锁回归:OPS_PIPELINE=pipeline 下 agent.mjs(主模块)动态 import
// pipeline.mjs,若 pipeline 静态依赖图绕回 agent.mjs(ERROR_CODES 旧取法)即顶层 await
// 死锁——形态 = rc 13 + stderr "unsettled top-level await" + stdout 空。探针选 usage
// 前置 throw 路径(budget 非法 → pipeline mkCtx usage:true → exit 2 用法错):import
// 可落定才能到达;零 API 零网(触发在 loadModels 之前)。e2e 不设 OPS_PIPELINE,
// 此路径 CI 覆盖面唯一。
await t("spawn:OPS_PIPELINE=pipeline 委派可落定(死锁回归:exit 2 用法错,非 rc13 unsettled)", async () => {
  const r = await spawnAgent(["health", "x"], { OPS_PIPELINE: "pipeline", OPS_PIPELINE_BUDGET_CNY: "abc" });
  assert.equal(r.rc, 2, `期望 2(usage),得到 ${r.rc}:${r.stderr.slice(0, 200)}`);
  assert.equal(r.stdout, "", "用法错不发 JSON");
  assert.match(r.stderr, /用法:/);
  assert.ok(!r.stderr.includes("unsettled"), `不得再出现 unsettled top-level await:${r.stderr.slice(0, 200)}`);
});

// ── #139 挂账②:锁路径跨语言对拍哨(形制同 selftest.sh §14 锚集对拍:python 文本解析 ↔ JS 实跑) ──
// 两侧锁文件必须同源同址(python ops_root()/QUEUE_LOCK_NAME ↔ node
// queueFile+".lock"),锁路径推导各自实现会漂移=双边锁开窗(互不互认)。
// CI frontend job 无 backend python 依赖 → 文本解析 _ops_store.py 抽字面量,
// 不 import ipdb(同 §14 python heredoc 不得依赖的裁例)。
await t("锁路径对拍:python QUEUE_LOCK_NAME ↔ node queueLockPath 同源同址(#139 挂账②)", async () => {
  const py = fs.readFileSync(path.join(AGENT, "..", "..", "backend", "ipdb", "_ops_store.py"), "utf8");
  const m = py.match(/QUEUE_LOCK_NAME = "([^"]+)"/);
  assert.ok(m, "_ops_store.py 缺 QUEUE_LOCK_NAME 字面量(锁路径契约漂移)");
  assert.equal(m[1], "queue.md.lock", "python 锁名漂移(须 = queue.md+'.lock')");
  assert.ok(py.includes("ops_root() / QUEUE_LOCK_NAME"),
    "queue_lock_path 必须 = ops_root()/QUEUE_LOCK_NAME(与 queue.md 同目录)");
  const { queueLockPath } = await import("./tools/queue-lock.mjs");
  // 生产同址链:P2 桥 _ops_rounds._round_env 注入 DOCS_ROOT=ops_root().parent →
  // node 默认 queueFile=DOCS_ROOT/ops/queue.md ≡ python ops_root()/queue.md 同一文件,
  // 锁路径同理同址才互认互斥
  const h = new (await import("./tools.mjs")).ToolHost("discover", { artifactDir: TMP });
  assert.equal(h.queueFile, path.join(DOCS, "ops", "queue.md"), "host 默认 queueFile 落位漂移");
  assert.equal(queueLockPath(h.queueFile), path.join(DOCS, "ops", m[1]),
    "node 锁路径 = queue.md 同目录同名+.lock,须与 python ops_root()/QUEUE_LOCK_NAME 同址");
  // 接线钉死:registry 面真消费锁封装(漂移 = queue_action 绕开跨进程锁,竞态窗复活)
  assert.match(SRCS.toolsRegistry, /appendQueueRowLocked/,
    "registry.mjs queueAction 未消费 appendQueueRowLocked(竞态窗复活)");
});

await t("锁路径对拍:python LEDGER_LOCK_NAME ↔ node ledgerLockPath 同源同址(#199 A3)", async () => {
  const py = fs.readFileSync(path.join(AGENT, "..", "..", "backend", "ipdb", "_ops_store.py"), "utf8");
  const m = py.match(/LEDGER_LOCK_NAME = "([^"]+)"/);
  assert.ok(m, "_ops_store.py 缺 LEDGER_LOCK_NAME 字面量(锁路径契约漂移)");
  assert.equal(m[1], "ledger.md.lock", "python 台账锁名漂移(须 = ledger.md+'.lock')");
  assert.ok(py.includes("ops_root() / LEDGER_LOCK_NAME"),
    "ledger_lock_path 必须 = ops_root()/LEDGER_LOCK_NAME(与 ledger.md 同目录)");
  const { ledgerLockPath } = await import("./pipeline/budget.mjs");
  // 生产同址链同 queue 哨:桥注入 LEDGER_FILE=ops_root()/ledger.md → node 派生
  // 锁路径与 python 同一文件,读写互认互斥;月度读面/拒跑留痕行同域。
  assert.equal(ledgerLockPath(path.join(DOCS, "ops", "ledger.md")), path.join(DOCS, "ops", m[1]),
    "node 锁路径 = ledger.md 同目录同名+.lock,须与 python ops_root()/LEDGER_LOCK_NAME 同址");
  assert.match(SRCS.pipelineBudget, /readLedgerTextLocked[\s\S]*?execFileP\("flock"/,
    "月度读面须经 flock 持锁(绕开=准入读到撕裂行)");
  assert.match(SRCS.libsh, /ledger_append\(\)[\s\S]*?flock "\$LEDGER_FILE\.lock"/,
    "lib.sh 写面 ledger_append 须持 flock(双写面缺一即竞态窗)");
  assert.match(py, /def append_ledger[\s\S]*?with _ledger_lock\(\):/,
    "python 写面 append_ledger 须持 _ledger_lock");
});

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`contract-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
