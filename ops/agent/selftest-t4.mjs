#!/usr/bin/env node
// selftest-t4.mjs — T4 语义门/负例三发/SSRF/读面/队列幂等 单测(不花 API、不真调网络:
// SSRF 用字面环回/链路本地地址在 DNS 解析前即拒;probe 键量用纯函数)。
// 输出行 T4PASS/T4FAIL 由 selftest.sh 计数;任一 FAIL 退出非零。
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AGENT = path.dirname(fileURLToPath(import.meta.url));
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "t4-selftest-"));
let pass = 0, fail = 0;
const ok = (name) => { pass++; console.log(`T4PASS ${name}`); };
const bad = (name, err) => { fail++; console.log(`T4FAIL ${name}: ${err}`); };
async function t(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } }

const { loadModels } = await import("./models.mjs");
const {
  ToolHost, checkPrivateIp, countFeedKeys, closureCheck, checkReadablePath, pinnedLookup,
} = await import("./tools.mjs");

// ── fixture:用户 models.json(flash 定义,无 api/baseUrl)+ models-store(glm-5.3 全量)+ auth ──
fs.writeFileSync(path.join(TMP, "models.json"), JSON.stringify({
  providers: { "zai-coding-cn": { models: [{
    id: "glm-5.3-flash", name: "GLM-5.3-Flash", reasoning: true,
    thinkingLevelMap: { off: null, minimal: null, low: "low", high: "high", max: "max" },
    input: ["text", "image"], contextWindow: 1000000, maxTokens: 131072,
    cost: { input: 0.14, output: 0.44, cacheRead: 0.04, cacheWrite: 0 },
    compat: { supportsStore: false, supportsDeveloperRole: false, supportsReasoningEffort: true, maxTokensField: "max_tokens", thinkingFormat: "zai", zaiToolStream: true },
  }] } },
}));
fs.writeFileSync(path.join(TMP, "models-store.json"), JSON.stringify({
  "zai-coding-cn": { models: [{
    id: "glm-5.3", name: "GLM-5.3", api: "openai-completions", provider: "zai-coding-cn",
    baseUrl: "https://open.bigmodel.cn/api/coding/paas/v4", reasoning: true,
    input: ["text"], cost: { input: 1.4, output: 4.4, cacheRead: 0.26, cacheWrite: 0 },
    contextWindow: 1000000, maxTokens: 131072, type: "chat",
  }] },
}));
fs.writeFileSync(path.join(TMP, "auth.json"), JSON.stringify({
  "zai-coding-cn": { type: "api_key", key: "fixture-key" },
}));

await t("models:三层装载——flash 继承 api/baseUrl,store glm-5.3 保全量,凭证入店", async () => {
  const { models, resolve, credentials } = await loadModels({
    modelsPath: path.join(TMP, "models.json"),
    storePath: path.join(TMP, "models-store.json"),
    authPath: path.join(TMP, "auth.json"),
  });
  const flash = resolve("health"), main = resolve("discover");
  assert.equal(flash.id, "glm-5.3-flash");
  assert.equal(flash.api, "openai-completions", "用户 json 缺省字段须继承下层默认");
  assert.ok(flash.baseUrl.startsWith("https://"));
  assert.equal(flash.provider, "zai-coding-cn");
  assert.equal(flash.cost.input, 0.14, "用户层 cost 覆盖内置");
  assert.equal(main.id, "glm-5.3");
  assert.equal(main.cost.output, 4.4, "store 层全量直取");
  assert.equal(models.getModel("zai-coding-cn", "glm-5.3")?.id, "glm-5.3");
  assert.equal((await credentials.read("zai-coding-cn"))?.key, "fixture-key");
});

// ── 语义门(伪 evidence 登记表;beforeToolCall 直调,不建 Agent)──────────────────
const host = new ToolHost("discover");
const gate = (args) => host.beforeToolCall({
  assistantMessage: { content: [] },
  toolCall: { id: "call_gate", name: "queue_action", arguments: args },
  args, context: { messages: [], tools: [] },
});
const blocked = async (args, why) => {
  const r = await gate(args);
  assert.ok(r?.block, `期望被门挡(应含:${why})却放行`);
  assert.ok(String(r.reason).includes(why), `reason 应含「${why}」实得:${r.reason}`);
};
const passes = async (args) => {
  const r = await gate(args);
  assert.equal(r, undefined, `期望放行却被挡:${r?.reason}`);
};
const REG = (id, tool, sc) => host.registry.register(id, tool, sc);
const EV = (call_id, field, value) => ({ call_id, field, value });

await t("负例①:无实测 ENQUEUE 被门挡(编造 call_id)", () =>
  blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_ghost", "exclusive_rate", 0.587)] }, "未知"));

await t("负例②:失败信封作 evidence 被拒(ok:false 不得作数)", async () => {
  REG("call_p0", "exclusive_probe", { ok: false, code: "control_failed", reason: "对照闸失败" });
  await blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_p0", "code", "control_failed")] }, "失败信封");
});

await t("门:ENQUEUE 排他率 24.9% < 0.25 被挡(边界)", async () => {
  REG("call_p1", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.249, exclusive: 74, sampled: 300 });
  await blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_p1", "exclusive_rate", 0.249)] }, "0.25");
});

await t("门:ENQUEUE 25.0% 恰过线 + 值逐字绑定 → 放行", async () => {
  REG("call_p2", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.25, exclusive: 75, sampled: 300 });
  await passes({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_p2", "exclusive_rate", 0.25)] });
});

await t("门:ENQUEUE 值不符(复述 0.5 vs 实测 0.587)被挡", async () => {
  REG("call_p3", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.587, exclusive: 176, sampled: 300 });
  await blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_p3", "exclusive_rate", 0.5)] }, "不符");
});

await t("门:ENQUEUE 对照闸未过(control_pass:false)被挡", async () => {
  REG("call_p4", "exclusive_probe", { ok: true, control_pass: false, exclusive_rate: 0.9, exclusive: 270, sampled: 300 });
  await blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_p4", "exclusive_rate", 0.9)] }, "对照");
});

await t("门:REJECT mirror_echo 实测 20.3% 回声 → 放行", async () => {
  REG("call_p5", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.203, exclusive: 61, sampled: 300 });
  await passes({ source: "cand_b", action: "REJECT", predicate: "mirror_echo", rationale: "r",
    evidence: [EV("call_p5", "exclusive_rate", 0.203)] });
});

await t("门:REJECT mirror_echo 实测 50% 与回声主张矛盾 → 挡", async () => {
  REG("call_p6", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.5, exclusive: 150, sampled: 300 });
  await blocked({ source: "cand_b", action: "REJECT", predicate: "mirror_echo", rationale: "r",
    evidence: [EV("call_p6", "exclusive_rate", 0.5)] }, "矛盾");
});

await t("门:REJECT mirror_echo 无实测一律阻断(判例代码化)", () =>
  blocked({ source: "cand_b", action: "REJECT", predicate: "mirror_echo", rationale: "r", evidence: [] }, "实测"));

await t("门:REJECT sunset_frozen 双 URL 均冻结 → 放行", async () => {
  REG("call_f1", "fetch_url", { ok: true, status: 200, age_days: 245, last_modified: "x" });
  REG("call_f2", "fetch_url", { ok: true, status: 200, age_days: 300, last_modified: "y" });
  await passes({ source: "cand_c", action: "REJECT", predicate: "sunset_frozen", rationale: "r",
    evidence: [EV("call_f1", "age_days", 245), EV("call_f2", "age_days", 300)] });
});

await t("门:sunset 任一 URL 活跃即不命中(Review Focus 3)", async () => {
  REG("call_f3", "fetch_url", { ok: true, status: 200, age_days: 245, last_modified: "x" });
  REG("call_f4", "fetch_url", { ok: true, status: 200, age_days: 3, last_modified: "z" });
  await blocked({ source: "cand_c", action: "REJECT", predicate: "sunset_frozen", rationale: "r",
    evidence: [EV("call_f3", "age_days", 245), EV("call_f4", "age_days", 3)] }, "活跃");
});

await t("门:sunset NO-LM(age_days=null)不是冻结证据", async () => {
  REG("call_f5", "fetch_url", { ok: true, status: 200, age_days: null, last_modified: null });
  await blocked({ source: "cand_c", action: "REJECT", predicate: "sunset_frozen", rationale: "r",
    evidence: [EV("call_f5", "age_days", null)] }, "age_days");
});

await t("门:REJECT zero_asset gh repos size=8KB → 放行;size=5MB → 挡;无 gh 证据 → 挡", async () => {
  REG("call_g1", "gh_search", { ok: true, kind: "repos", query: "x", results: [{ full_name: "a/b", size_kb: 8 }] });
  await passes({ source: "cand_d", action: "REJECT", predicate: "zero_asset", rationale: "r",
    evidence: [EV("call_g1", "results.0.size_kb", 8)] });
  REG("call_g2", "gh_search", { ok: true, kind: "repos", query: "x", results: [{ full_name: "a/b", size_kb: 5000 }] });
  await blocked({ source: "cand_d", action: "REJECT", predicate: "zero_asset", rationale: "r",
    evidence: [EV("call_g2", "results.0.size_kb", 5000)] }, "资产");
  await blocked({ source: "cand_d", action: "REJECT", predicate: "zero_asset", rationale: "r",
    evidence: [EV("call_f1", "age_days", 245)] }, "gh_search");
});

await t("门:谓词不在闭集 / REJECT 缺谓词 → 挡", async () => {
  await blocked({ source: "cand_d", action: "REJECT", predicate: "vibes", rationale: "r", evidence: [] }, "谓词");
  await blocked({ source: "cand_d", action: "REJECT", rationale: "r", evidence: [] }, "谓词");
});

await t("门:引用非测量工具(queue_action 套娃)被挡", async () => {
  REG("call_q1", "queue_action", { ok: true, appended: true, exclusive_rate: 0.99 });
  await blocked({ source: "cand_a", action: "ENQUEUE", rationale: "r",
    evidence: [EV("call_q1", "exclusive_rate", 0.99)] }, "测量");
});

await t("门:queue 预算 ≤10/轮,第 11 次被挡(真实 execute 路径计数,不手工 spend)", async () => {
  const h2 = new ToolHost("discover", { queueFile: path.join(TMP, "q-budget.md") });
  h2.registry.register("p0", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.5 });
  const qa = h2.tools.find((x) => x.name === "queue_action");
  const argsFor = (s) => ({ source: s, action: "ENQUEUE", rationale: "r", evidence: [EV("p0", "exclusive_rate", 0.5)] });
  for (let i = 0; i < 10; i++) { // 真实路径:execute 内 budgetSpend(评审 Important-1 修复面)
    const r = await qa.execute(`c${i}`, argsFor(`s_${i}`));
    assert.equal(r.structuredContent.appended, true);
  }
  assert.equal(h2.spent["queue_action"], 10, "execute 真实计数(不再依赖测试代炉)");
  const r = await h2.beforeToolCall({ assistantMessage: { content: [] }, toolCall: { id: "cx", name: "queue_action", arguments: argsFor("s_x") }, args: argsFor("s_x"), context: { messages: [], tools: [] } });
  assert.ok(r?.block && r.reason.includes("预算"), `第 11 次应挡:${r?.reason}`);
});

await t("SSRF:pinnedLookup 只吐已验证地址集(堵双解析重绑定,评审 Important-2)", () => {
  let got = null;
  const lookup = pinnedLookup(["93.184.216.34"]);
  lookup("example.com", { all: true }, (err, addrs) => { got = { err, addrs }; });
  assert.ok(!got.err);
  assert.deepEqual(got.addrs, [{ address: "93.184.216.34", family: 4 }], "无论二次解析返回什么,连接层只见已验证集");
  const v6 = pinnedLookup(["2606:2800:220:1::1"]);
  let got6 = null;
  v6("h", {}, (err, addrs) => { got6 = { err, addrs }; });
  assert.deepEqual(got6.addrs, [{ address: "2606:2800:220:1::1", family: 6 }], "v6 family 标注");
  // IP 字面量:验证后空集,fail-closed(若 lookup 仍被调,连接报错而非绕过)
  let gotE = null;
  pinnedLookup([])("h", {}, (err, addrs) => { gotE = { err, addrs }; });
  assert.deepEqual(gotE.addrs, []);
});

// ── 负例③:编造判例路径被闭合校验拦(闭集成员校验,非存在性)────────────────────
await t("负例③:closureCheck 编造路径被拦(真实文件不在闭集也算编造)", () => {
  const real = "2026-10-18-malicious-ip-mapping-vs-key-overlap.md";
  const allowed = new Set([real]);
  const pkgOk = `## 注入判例\n- ${real}\n`;
  closureCheck(pkgOk, allowed); // 不抛
  const pkgFake = `## 注入判例\n- 2026-10-18-z-i-y-a-d-n-z-aggregator-misjudge.md\n`;
  assert.throws(() => closureCheck(pkgFake, allowed), /闭合|不在/);
  closureCheck(`## 注入判例\n无判例(检索词: x)\n`, new Set());
});

// ── SSRF / 读面 / 键量(执行层,字面地址 DNS 前拒,无网络)──────────────────────
await t("SSRF:环回/链路本地/私网字面地址被拒", async () => {
  assert.ok(checkPrivateIp("127.0.0.1"));
  assert.ok(checkPrivateIp("169.254.169.254"));
  assert.ok(checkPrivateIp("10.1.2.3"));
  assert.ok(checkPrivateIp("192.168.1.1"));
  assert.ok(checkPrivateIp("172.16.0.9"));
  assert.ok(checkPrivateIp("::1"));
  assert.ok(checkPrivateIp("::ffff:10.0.0.1"));
  assert.ok(!checkPrivateIp("8.8.8.8"));
  const fu = host.tools.find((x) => x.name === "fetch_url");
  const r = await fu.execute("t1", { url: "http://127.0.0.1:9/x", method: "HEAD" });
  assert.equal(r.structuredContent.ok, false);
  assert.equal(r.structuredContent.code, "ssrf");
  assert.ok(!r.isError, "SSRF 拒 = 结构化信封,非异常");
});

await t("读面:.env/密钥模式/.venv/data/越界被拒;白名单内可读", async () => {
  // 拒读模式须在白名单内测试(tmp 在白名单外会先撞越界)
  const FIX = path.join(AGENT, ".selftest-t4-fixture");
  fs.mkdirSync(FIX, { recursive: true });
  try {
    assert.throws(() => checkReadablePath(path.join(FIX, "prod.env")), /\.env/);
    assert.throws(() => checkReadablePath(path.join(FIX, "secrets.pem")), /密钥/);
    assert.throws(() => checkReadablePath("/etc/passwd"), /越界/);
    assert.ok(checkReadablePath(path.join(FIX, "notes.md")));
    const rf = host.tools.find((x) => x.name === "read_file");
    const r = await rf.execute("t2", { path: path.join(FIX, "prod.env") });
    assert.equal(r.structuredContent.ok, false);
    assert.equal(r.structuredContent.code, "denied");
    fs.writeFileSync(path.join(FIX, "notes.md"), "line1\nline2\n");
    const r2 = await rf.execute("t3", { path: path.join(FIX, "notes.md") });
    assert.equal(r2.structuredContent.ok, true);
    assert.match(r2.structuredContent.content, /line1/);
  } finally { fs.rmSync(FIX, { recursive: true, force: true }); }
});

await t("键量:probe 键计数 + 上限信封", () => {
  const feed = Array.from({ length: 1500 }, (_, i) => `1.2.3.${(i % 254) + 1}`).join("\n");
  assert.equal(countFeedKeys(feed), 254, "去重计数");
  assert.ok(countFeedKeys("no ips here") === 0);
});

// ── queue_action 执行面:行模板渲染 + 幂等去重 + veto_cmd ──────────────────────
await t("队列:模板渲染落行/幂等去重/vetoable+veto_cmd", async () => {
  const h3 = new ToolHost("discover", { queueFile: path.join(TMP, "queue.md") });
  h3.registry.register("call_p9", "exclusive_probe", { ok: true, control_pass: true, exclusive_rate: 0.587, exclusive: 176, sampled: 300 });
  const qa = h3.tools.find((x) => x.name === "queue_action");
  const r1 = await qa.execute("t4", { source: "cand_x", action: "ENQUEUE", rationale: "看好", evidence: [EV("call_p9", "exclusive_rate", 0.587)] });
  assert.equal(r1.structuredContent.appended, true);
  assert.equal(r1.structuredContent.vetoable, true);
  assert.match(r1.structuredContent.veto_cmd, /cand_x/);
  assert.match(r1.structuredContent.veto_cmd, /queue\.md/);
  const row = fs.readFileSync(path.join(TMP, "queue.md"), "utf8");
  assert.match(row, /\| ENQUEUE \| cand_x \|/);
  assert.ok(!row.includes("看好"), "rationale 不得落队列行(社工信道)");
  const r2 = await qa.execute("t5", { source: "cand_x", action: "ENQUEUE", rationale: "再看", evidence: [EV("call_p9", "exclusive_rate", 0.587)] });
  assert.equal(r2.structuredContent.appended, false);
  assert.equal(r2.structuredContent.dedup, true);
  assert.equal(fs.readFileSync(path.join(TMP, "queue.md"), "utf8").split("\n").filter((l) => l.includes("cand_x")).length, 1);
});

await t("工具面:discover=7 工具、health=1 工具,全部声明 outputSchema+annotations", () => {
  const d = new ToolHost("discover").tools.map((x) => x.name).sort();
  assert.deepEqual(d, ["exclusive_probe", "fetch_url", "gh_search", "matrix_scan_summary", "queue_action", "read_file", "search_precedents"]);
  const h = new ToolHost("health").tools.map((x) => x.name);
  assert.deepEqual(h, ["health_snapshot"]);
  for (const tool of [...new ToolHost("discover").tools, ...new ToolHost("health").tools]) {
    assert.ok(tool.outputSchema, `${tool.name} 缺 outputSchema(铁律③)`);
    assert.ok(tool.annotations, `${tool.name} 缺 annotations`);
  }
  const qa = new ToolHost("discover").tools.find((x) => x.name === "queue_action");
  assert.equal(qa.annotations.readOnlyHint, false, "唯一写工具 readOnly=false");
});

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`t4-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
