#!/usr/bin/env node
// selftest-t4.mjs — T4 语义门/负例三发/SSRF/读面/队列幂等 单测(不花 API、不真调网络:
// SSRF 用字面环回/链路本地地址在 DNS 解析前即拒;probe 键量用纯函数)。
// 输出行 T4PASS/T4FAIL 由 selftest.sh 计数;任一 FAIL 退出非零。
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFileP = promisify(execFileCb);
const AGENT = path.dirname(fileURLToPath(import.meta.url));
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "t4-selftest-"));
let pass = 0, fail = 0;
const ok = (name) => { pass++; console.log(`T4PASS ${name}`); };
const bad = (name, err) => { fail++; console.log(`T4FAIL ${name}: ${err}`); };
async function t(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } }

const { loadModels } = await import("./models.mjs");
const {
  ToolHost, checkPrivateIp, countFeedKeys, closureCheck, checkReadablePath, pinnedLookup, safeFetch,
  // PR #177(工具通道修复,判例 2026-10-24-discover-dual-channel-dead):判例检索 JS 单源核心
  // 与通道错误分类器——RED 面先行(未实现时 undefined,下列各例红而不炸装载)。
  searchPrecedentsCore, classifyChannelError,
  // PR3a 发现通道三件纯函数核(2026-10-24 裁定;web_search 引擎 = pi-web-access MCP,同日中程用户令):
  normalizeJinaRead, parseSerp, parseRss, RSS_FRESH_DAYS, classifyWebStatus, parseMcpSearchText, classifyMcpSearchError,
  // 票 #182(金标巡检 harness):ops 轮锚巡检 CLI 单源(matrixScanCli 同型;通道四码兼容)
  anchorSweepCli,
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

// ── 票 #143 多供应商装载:builtin 全家注册 + qualified resolve + 逐家凭证 ──
// fixture:auth.json 两家凭证(zai + anthropic);用户层 provider(lmstudio 形,
// 非 builtin)从 providerConfig 构造——baseUrl/api/apiKey 全在 provider 层。
fs.writeFileSync(path.join(TMP, "auth-multi.json"), JSON.stringify({
  "zai-coding-cn": { type: "api_key", key: "fixture-zai" },
  "anthropic": { type: "api_key", key: "fixture-anthropic" },
}));
fs.writeFileSync(path.join(TMP, "models-multi.json"), JSON.stringify({
  providers: {
    lmstudio: {
      baseUrl: "http://127.0.0.1:1234/v1", api: "openai-completions", apiKey: "lm-studio",
      models: [{ id: "ornith-1.5-9b", name: "Ornith", input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    },
  },
}));

await t("models:builtin 多家装载(pi-ai registry;离线,resolve 不触网)", async () => {
  const { models } = await loadModels({ authPath: path.join(TMP, "auth-multi.json") });
  const anthropic = models.getModels("anthropic");
  assert.ok(anthropic.length > 0, "anthropic builtin 目录应已装载");
  const m = models.getModel("anthropic", anthropic[0].id);
  assert.equal(m?.provider, "anthropic");
  assert.equal(m?.api, "anthropic-messages");
});

await t("models:qualified resolve(provider/model;裸值=缺省 zai)+ 逐家凭证入店", async () => {
  const { models, resolve, credentials } = await loadModels({
    modelsPath: path.join(TMP, "models-multi.json"),
    authPath: path.join(TMP, "auth-multi.json"),
  });
    // qualified:builtin 家(anthropic)+ 用户层构造家(lmstudio)各一发;
    // anthropic 模型 id 从装载目录动态取(目录内容随 pi-ai 版本浮动,不钉字面量)
    const claudeId = models.getModels("anthropic")[0].id;
    process.env.OPS_MODEL_HEALTH = `anthropic/${claudeId}`;
    process.env.OPS_MODEL_DISCOVER = "lmstudio/ornith-1.5-9b";
    assert.equal(resolve("health").provider, "anthropic");
    assert.equal(resolve("health").id, claudeId);
    assert.equal(resolve("discover").provider, "lmstudio");
    assert.equal(resolve("discover").baseUrl, "http://127.0.0.1:1234/v1", "非 builtin provider 继承 provider 层 baseUrl");
    assert.equal((await credentials.read("anthropic"))?.key, "fixture-anthropic", "auth.json 逐家凭证");
    assert.equal((await credentials.read("lmstudio"))?.key, "lm-studio", "provider 层 apiKey 字面量入店");
    // 裸值(无 /)= 缺省 zai(向后兼容:#140 既有配置/env 面)
    delete process.env.OPS_MODEL_HEALTH;
    assert.equal(resolve("health").provider, "zai-coding-cn");
    assert.equal(resolve("health").id, "glm-5.3-flash");
    delete process.env.OPS_MODEL_DISCOVER;
  });

await t("models:未知 provider/模型 显式报错(错误面含 provider 名与已装载摘要)", async () => {
  const { resolve } = await loadModels({ authPath: path.join(TMP, "auth-multi.json") });
  process.env.OPS_MODEL_HEALTH = "no-such-provider/foo";
  try {
    assert.throws(() => resolve("health"), /no-such-provider/);
  } finally { delete process.env.OPS_MODEL_HEALTH; }
  process.env.OPS_MODEL_HEALTH = "anthropic/no-such-model";
  try {
    assert.throws(() => resolve("health"), /anthropic\/no-such-model/);
  } finally { delete process.env.OPS_MODEL_HEALTH; }
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
  const h2 = new ToolHost("discover", { queueFile: path.join(TMP, "q-budget.md"), artifactDir: TMP });
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
  const h3 = new ToolHost("discover", { queueFile: path.join(TMP, "queue.md"), artifactDir: TMP });
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

// ── PR #177 工具通道修复(判例 2026-10-24-discover-dual-channel-dead):search_precedents 单源 ──
// 事故面:search_precedents 失败不可诊断(trace 硬编码 rc:0/lib.sh 吞 stderr 2>/dev/null/
// ENOENT 塞字符串违反 outputSchema Number 槽)。本节钉:golden 字节等价(JS 核心 = lib.sh
// 现行 = 入库快照)+ 失败面分类(信封四码)+ gh_search 分类落地 + JS↔Python 契约对拍。
// fixture = fixtures/precedents 真实判例库快照(23 件含 _schema/_INDEX,排除面有真实对象)。
const FIXTURES_PREC = path.join(AGENT, "fixtures", "precedents");
const GOLDEN_KWS = fs.readFileSync(path.join(AGENT, "golden", "inject-block.discover-kws.golden.txt"), "utf8");
const GOLDEN_ZERO = fs.readFileSync(path.join(AGENT, "golden", "inject-block.zerohit.golden.txt"), "utf8");
const DISCOVER_KWS = ["排他率", "聚合器", "许可", "体量", "冻结", "sunset"];
const libshInject = async (kws) => (await execFileP("bash",
  ["-c", '. "$0"; inject_precedents "$@"', path.join(AGENT, "lib.sh"), ...kws],
  { env: { ...process.env, PRECEDENTS_DIR: FIXTURES_PREC }, timeout: 60_000 })).stdout;

await t("search_precedents core:golden 字节等价(JS 核心 = lib.sh 现行输出 = 入库快照;含折叠字段双空格/空行截断隐藏细节)", async () => {
  assert.equal(typeof searchPrecedentsCore, "function", "searchPrecedentsCore 未导出(RED 面应先红)");
  const { block } = await searchPrecedentsCore(DISCOVER_KWS, { precedentsDir: FIXTURES_PREC });
  assert.equal(block, GOLDEN_KWS, "JS 核心注入块与 golden 快照不逐字节等价");
  // lib.sh 退役注记后仍是 pipeline/steps.mjs 面真源:两路输出恒同文(字节对拍)
  assert.equal(await libshInject(DISCOVER_KWS), GOLDEN_KWS, "lib.sh 现行输出与 golden 快照漂移(golden 须同 PR 显式重钉)");
});

await t("search_precedents core:零命中块字节等价 + 空词守卫(lib.sh 同形,不 spawn)", async () => {
  const zero = await searchPrecedentsCore(["不存在的词xyz"], { precedentsDir: FIXTURES_PREC });
  assert.equal(zero.block, GOLDEN_ZERO, "零命中块「无判例」行不等");
  assert.deepEqual(zero.files, []);
  assert.equal(zero.trace.rc, 0);
  const empty = await searchPrecedentsCore([], { precedentsDir: FIXTURES_PREC }); // lib.sh 零词守卫:不跑 rg 恒「无判例」
  assert.equal(empty.block, "### 注入判例(检索词: )\n无判例(检索词: )\n");
});

await t("search_precedents core:失败面分类(ENOENT→channel_missing+rc127 Number;超时→transient;rc≥2→rg_infra 兑底)", async () => {
  const STUB = fs.mkdtempSync(path.join(os.tmpdir(), "t4-rg-stub-"));
  const mkRg = (body) => { fs.writeFileSync(path.join(STUB, "rg"), `#!/bin/bash\n${body}\n`); fs.chmodSync(path.join(STUB, "rg"), 0o755); };
  try {
    // ENOENT(容器无 rg 判例同面):env 注入面隔裹 PATH,不动全局
    await assert.rejects(
      searchPrecedentsCore(["排他率"], { precedentsDir: FIXTURES_PREC, env: { ...process.env, PATH: "/nonexistent-ops-t4" } }),
      (e) => e.envelope?.code === "channel_missing" && e.trace?.rc === 127 && typeof e.trace?.rc === "number");
    // 超时(测试注入 timeoutMs 300ms + 沉睡 stub;生产 60s)
    mkRg("sleep 30");
    await assert.rejects(
      searchPrecedentsCore(["排他率"], { precedentsDir: FIXTURES_PREC, env: { ...process.env, PATH: `${STUB}:${process.env.PATH}` }, timeoutMs: 300 }),
      (e) => e.envelope?.code === "transient");
    // rc≥2 = 基础设施故障≠零命中(Minor-3 判例,兑底码保留)
    mkRg("echo 'rg 检索失败' >&2; exit 3");
    await assert.rejects(
      searchPrecedentsCore(["排他率"], { precedentsDir: FIXTURES_PREC, env: { ...process.env, PATH: `${STUB}:${process.env.PATH}` } }),
      (e) => e.envelope?.code === "rg_infra" && e.trace?.rc === 3);
  } finally { fs.rmSync(STUB, { recursive: true, force: true }); }
});

await t("search_precedents 工具面:成功路径 hits/hit_n/truncated(铁律⑦)+ 闭集登记;失败信封带分类 code+真 rc Number+下一步提示", async () => {
  const sp = host.tools.find((x) => x.name === "search_precedents");
  const origPrec = process.env.PRECEDENTS_DIR;
  process.env.PRECEDENTS_DIR = FIXTURES_PREC;
  try {
    const r1 = await sp.execute("t_sp1", { keywords: ["排他率"] });
    const sc1 = r1.structuredContent;
    assert.equal(sc1.ok, true);
    assert.ok(sc1.hit_n > 0 && sc1.hit_n <= 8, "命中入闭集且≤8");
    assert.equal(sc1.trace.rc, 0);
    assert.match(sc1.trace.cmd, /^rg -i -l/, "trace.cmd = 真 argv(不再硬编码 inject_precedents 行)");
    for (const h of sc1.hits) assert.ok(host.searchHits.has(h), "命中须进闭集登记");
    const r2 = await sp.execute("t_sp2", { keywords: DISCOVER_KWS });
    assert.equal(r2.structuredContent.truncated, true, "多词并集>8 须截断标记");
    assert.equal(r2.structuredContent.hit_n, 8);
  } finally { process.env.PRECEDENTS_DIR = origPrec; }
  // 失败面(全局 PATH 临时指走;execute 走 process.env,同步改后 await 恢复)
  const origPath = process.env.PATH;
  process.env.PATH = "/nonexistent-ops-t4";
  try {
    const r = await sp.execute("t_sp3", { keywords: ["排他率"] });
    const sc = r.structuredContent;
    assert.equal(sc.ok, false);
    assert.equal(sc.code, "channel_missing");
    assert.ok(typeof sc.trace.rc === "number", "trace.rc 恒 Number(ENOENT 不得塞字符串——事故面)");
    assert.equal(sc.trace.rc, 127);
    assert.match(sc.reason, /人裁/, "每码文案带下一步合法动作");
  } finally { process.env.PATH = origPath; }
});

await t("gh_search:分类落地(ENOENT→channel_missing rc127;not logged in→channel_auth;rate limit→quota;403+rate limit 并存→quota 次级限流;兑底 gh_error);trace.rc 恒 Number;argv 无 --page;成功路径零改动", async () => {
  const gh = host.tools.find((x) => x.name === "gh_search");
  const GHSTUB = fs.mkdtempSync(path.join(os.tmpdir(), "t4-gh-stub-"));
  const mkGh = (body) => { fs.writeFileSync(path.join(GHSTUB, "gh"), `#!/bin/bash\n${body}\n`); fs.chmodSync(path.join(GHSTUB, "gh"), 0o755); };
  const run = async () => (await gh.execute("t_gh", { query: "blocklist", kind: "repos" })).structuredContent;
  const withPath = async (p) => { const o = process.env.PATH; process.env.PATH = p; try { return await run(); } finally { process.env.PATH = o; } };
  try {
    let sc = await withPath("/nonexistent-ops-t4"); // 判例 2026-10-24:容器无 gh 全灭面
    assert.equal(sc.code, "channel_missing");
    assert.equal(sc.trace.rc, 127);
    assert.ok(typeof sc.trace.rc === "number");
    mkGh("echo 'gh: To get started, run: gh auth login. fatal: not logged in' >&2; exit 4");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "channel_auth");
    assert.equal(sc.trace.rc, 4);
    assert.match(sc.reason, /GH_TOKEN|人裁/);
    mkGh("echo 'API rate limit exceeded' >&2; exit 1");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "quota");
    assert.equal(sc.trace.rc, 1);
    mkGh("echo 'HTTP 403: rate limit exceeded' >&2; exit 1");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "quota", "403+rate limit = GitHub 次级限流归 quota(审后修 P2-3:quota 先于 channel_auth)");
    mkGh("echo 'To get started with GitHub CLI, please run:  gh auth login' >&2; exit 1");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "channel_auth", "真免凭据报文(2026-10-24 GH_CONFIG_DIR 隔离实测)归 channel_auth");
    mkGh("echo 'HTTP 403: Forbidden' >&2; exit 1");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "channel_auth", "纯 403(无限流文案)归 channel_auth(词边界防 URL/计数误配)");
    mkGh("echo 'boom' >&2; exit 7");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "gh_error", "原兑底码兼容保留");
    assert.equal(sc.trace.rc, 7);
    // 通道复验轮修复(2026-10-24):gh 2.103.x search 无 --page——argv 不得再拼(旧实现恒拼放 100% 必死)
    mkGh("echo \"$@\" >&2; exit 1");
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.code, "gh_error");
    assert.equal(sc.trace.rc, 1);
    assert.ok(!/\s--page(\s|$)/.test(sc.trace.cmd), `argv 不应再含 --page:${sc.trace.cmd}`);
    mkGh(`printf '%s' '${JSON.stringify([{ fullName: "a/b", description: "d", stargazersCount: 1, size: 3, url: "u" }])}'`);
    sc = await withPath(`${GHSTUB}:${process.env.PATH}`);
    assert.equal(sc.ok, true); // 成功路径零改动
    assert.equal(sc.total, 1);
  } finally { fs.rmSync(GHSTUB, { recursive: true, force: true }); }
});

await t("safeFetch:headers TDZ 回归(#173 注入面撞函数体旧变量名;通道复验轮 0634 实锤)", async () => {
  // 旧虫在构造请求头处即炸(零网络路径可复现):任何调用(含 DNS 必败)都抛
  // Cannot access 'headers' before initialization。修复后不可达主机应得网络面错误而非 TDZ。
  const err = await safeFetch("https://nonexistent-host-opst4.invalid/x").then(() => null, (e) => e);
  assert.ok(err instanceof Error, "不可达主机应抛错");
  assert.ok(!/before initialization/.test(String(err?.message)), `不得再抛 TDZ:${err?.message}`);
});

await t("classifyChannelError:四码优先级闭集(channel_missing>quota>channel_auth>transient>兑底,审后修 P2-3 调序);每码文案带下一步合法动作", () => {
  assert.equal(typeof classifyChannelError, "function", "classifyChannelError 未导出(RED 面应先红)");
  const mk = (o) => Object.assign(new Error(o.msg ?? "x"), o);
  assert.equal(classifyChannelError(mk({ code: "ENOENT", msg: "spawn gh ENOENT" }), "gh").code, "channel_missing");
  assert.equal(classifyChannelError(mk({ code: 127, stderr: "whatever" }), "rg").code, "channel_missing", "rc=127 同码(spawn ENOENT 同面)");
  assert.equal(classifyChannelError(mk({ code: 1, stderr: "HTTP 403: rate limit exceeded" }), "gh").code, "quota", "403+rate limit = 次级限流归 quota(quota 先于 channel_auth,审后修 P2-3)");
  assert.equal(classifyChannelError(mk({ code: 1, stderr: "rate limit exceeded" }), "gh").code, "quota");
  assert.equal(classifyChannelError(mk({ code: 1, killed: true, signal: "SIGTERM", msg: "Command timed out" }), "gh").code, "transient");
  assert.equal(classifyChannelError(mk({ code: 5, stderr: "weird" }), "gh").code, "gh_error", "gh 兑底保留");
  assert.equal(classifyChannelError(mk({ code: 5, stderr: "weird" }), "rg").code, "rg_infra", "rg 兑底保留");
  for (const e of [mk({ code: "ENOENT" }), mk({ code: 1, stderr: "not logged in" }), mk({ code: 1, stderr: "rate limit" }),
    mk({ code: 1, killed: true, signal: "SIGTERM" }), mk({ code: 5, stderr: "weird" })]) {
    assert.match(classifyChannelError(e, "gh").reason, /下一步/, "错误文案须能引导模型自纠或升级(MCP isError 语义,2026-07-28)");
  }
});

// ── PR3a 发现通道三件(web_read/web_search/rss_parse;DESIGN §6 2026-10-24 裁定)──
await t("normalizeJinaRead:元数据前缀剥离/Title 提取/max_chars 截断/无前缀容错", () => {
  assert.equal(typeof normalizeJinaRead, "function", "normalizeJinaRead 未导出(RED 面应先红)");
  const md = "Title: Awesome Blocklists\n\nURL Source: https://example.com/awesome\n\nMarkdown Content:\n# heading\n\n正文内容……";
  const n1 = normalizeJinaRead(md, { maxChars: 1000 });
  assert.equal(n1.title, "Awesome Blocklists");
  assert.match(n1.content, /^# heading/, "元数据三行前缀(Title/URL Source/Markdown Content)须剥离");
  assert.equal(n1.truncated, false);
  const n2 = normalizeJinaRead(md, { maxChars: 8 });
  assert.equal(n2.chars_n, 8, "截断头 N 字");
  assert.equal(n2.truncated, true);
  const n3 = normalizeJinaRead("裸正文无元数据前缀", {});
  assert.equal(n3.title, null);
  assert.equal(n3.content, "裸正文无元数据前缀");
  assert.equal(n3.truncated, false);
  // 审后修 P2 钉:Published Time 前缀行同样剥离(带日期页面真形,首发 fixture 遗漏)
  const md4 = "Title: T\n\nURL Source: https://example.com/x\n\nPublished Time: Fri, 23 Oct 2026 22:53:33 GMT\n\nMarkdown Content:\n正文AA";
  const n4 = normalizeJinaRead(md4, { maxChars: 1000 });
  assert.ok(!n4.content.includes("Published Time"), "Published Time 行不得漏入正文");
  assert.equal(n4.content, "正文AA");
  assert.equal(n4.title, "T");
});

await t("parseSerp:数组/data 包裹两形;畸形行(字符串/null/数字/缺 url)跳过不冒充;num 本地截断+truncated;非 JSON→io_error", () => {
  assert.equal(typeof parseSerp, "function", "parseSerp 未导出(RED 面应先红)");
  const rows = [
    { title: "a", url: "https://a.example", snippet: "sa" },
    "畸形字符串行", null, 42,
    { title: "缺 url", snippet: "x" },
    { title: "desc 槽", url: "https://b.example", description: "description 兜底槽" },
  ];
  const p1 = parseSerp(JSON.stringify(rows), { num: 5 });
  assert.equal(p1.n, 2, "缺 url/非对象行不入结果(宁少算不冒充)");
  assert.deepEqual(p1.results.map((r) => r.url), ["https://a.example", "https://b.example"]);
  assert.equal(p1.results[1].snippet, "description 兜底槽");
  assert.equal(p1.truncated, false);
  const p2 = parseSerp(JSON.stringify({ data: rows }), { num: 1 });
  assert.equal(p2.n, 1);
  assert.equal(p2.truncated, true, "服务端多回本地截断须标");
  for (const bad of ["not json", '{"data": 42}', '{"x": 1}']) {
    assert.throws(() => parseSerp(bad, {}), (e) => e.code === "io_error");
  }
});

await t("parseRss:RSS2.0/Atom 双形状;新鲜门 30(5 天=新鲜/40 天=过期,相对日期);CDATA 剥;坏 XML→io_error;零时间→fresh null", () => {
  assert.equal(typeof parseRss, "function", "parseRss 未导出(RED 面应先红)");
  assert.equal(RSS_FRESH_DAYS, 30, "独立常量 30(勿复用 FROZEN_DAYS=180,门线语义不同)");
  const rss = `<?xml version="1.0"?><rss><channel><title>t</title>
<item><title>旧条</title><link>https://x/1</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
<item><title><![CDATA[新 条]]></title><link>https://x/2</link><pubDate>${new Date(Date.now() - 5 * 86400_000).toUTCString()}</pubDate></item>
</channel></rss>`;
  const r1 = parseRss(rss, {});
  assert.equal(r1.items_n, 2);
  assert.match(r1.latest_pubdate, /GMT/);
  assert.equal(r1.fresh, true, "最新 5 天 ≤30 天新鲜门");
  assert.deepEqual(r1.sample, ["旧条", "新 条"], "CDATA 剥离入样本");
  const updated40d = new Date(Date.now() - 40 * 86400_000).toISOString();
  const atom = `<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>atom 甲</title><link rel="alternate" href="https://y/1"/>${""}<updated>${updated40d}</updated></entry>
<entry><title>atom 无时间</title><link href="https://y/2"/></entry>
</feed>`;
  const r2 = parseRss(atom, {});
  assert.equal(r2.items_n, 2, "Atom entry 计数(自闭合 link href 形状)");
  assert.equal(r2.fresh, false, "40 天 >30 天新鲜门");
  assert.equal(r2.latest_pubdate, updated40d);
  const noDates = "<rss><channel><item><title>a</title><link>u</link></item></channel></rss>";
  const r3 = parseRss(noDates, {});
  assert.equal(r3.latest_pubdate, null);
  assert.equal(r3.fresh, null, "无可解析时间=缺读数≠过期(fetch_url age_days NO-LM 同型)");
  for (const bad of ["not xml", "", "<html><body>网页非 feed</body></html>"]) {
    assert.throws(() => parseRss(bad, {}), (e) => e.code === "io_error");
  }
});

await t("分类:402/balance→quota(quota 正则扩 PR3a);quota 文案「充值或窗口恢复」;403 仍 channel_auth(词边界面);HTTP 状态面同族", () => {
  const mk = (stderr) => Object.assign(new Error("x"), { code: 1, stderr });
  assert.equal(classifyChannelError(mk("HTTP 402: Payment Required"), "gh").code, "quota", "402 显式归 quota 不归 channel_auth");
  assert.equal(classifyChannelError(mk("insufficient balance"), "gh").code, "quota");
  assert.match(classifyChannelError(mk("rate limit exceeded"), "gh").reason, /充值或窗口恢复/, "余额形态文案:充值或窗口恢复后自然可用");
  assert.equal(classifyChannelError(mk("HTTP 403: Forbidden"), "gh").code, "channel_auth", "纯 403 不因 402 扩词误归 quota");
  // HTTP 状态面(web_read/web_search 共用):同族四码判定
  assert.equal(classifyWebStatus(402, "", "web_search").code, "quota");
  assert.equal(classifyWebStatus(200, "Insufficient Balance", "web_search").code, "quota", "状态面文案含余额词同归 quota");
  assert.match(classifyWebStatus(402, "", "web_search").reason, /充值或窗口恢复/);
  assert.equal(classifyWebStatus(403, "", "web_read").code, "channel_auth");
  assert.equal(classifyWebStatus(500, "boom", "web_read").code, "http_error", "非通道面状态归 http_error(暂态族,同 fetch_url 语义)");
});

// ── 票 #182:anchorSweepCli——ops 轮锚巡检 CLI 单源(matrixScanCli 同型;faux 查询面零网络)──
await t("anchorSweepCli:faux 查询面——读数(finding 在场仍 ok/rc 0)/error 信封透传/ENOENT→channel_missing/超时→transient(通道四码兼容)", async () => {
  assert.equal(typeof anchorSweepCli, "function", "anchorSweepCli 未导出(RED 面应先红)");
  // 罐装 sweep(事故判例形:#183 整改前 114DNS=cps+ziyadnz 假印证 finding——票 #182 明示 fixture 不依赖整改)
  const CANNED = { kind: "anchor_sweep", anchors: [["8.8.8.8", "clean"], ["114.114.114.114", "clean"]],
    n_total: 2, n_fail: 1,
    failures: [{ ip: "114.114.114.114", expect: "clean", reason: "expected clean, got malicious" }],
    results: [
      { ip: "8.8.8.8", expect: "clean", ok: true, reason: null, verdict: "benign", confidence: 0, accusers: [] },
      { ip: "114.114.114.114", expect: "clean", ok: false, reason: "expected clean, got malicious", verdict: "malicious", confidence: 55, accusers: ["cps_collected_iocs", "ziyadnz"] }] };
  const shell = (name, body) => { const p = path.join(TMP, name);
    fs.writeFileSync(p, `#!/usr/bin/env bash\n${body}`); fs.chmodSync(p, 0o755); return p; };
  const stubOk = shell("py-sweep-ok", `printf '%s\n' '${JSON.stringify(CANNED).replace(/'/g, "'\\''")}'\n`);
  const r = await anchorSweepCli({ evalPy: stubOk, dataDir: "/tmp/d" });
  assert.equal(r.ok, true, "finding 在场仍是读数非故障(不持门语义在 CLI 面=rc 0)");
  assert.equal(r.rc, 0);
  assert.deepEqual(r.d, CANNED, "读数原样透传(步侧零改写)");
  assert.match(r.cmd, /--anchor-sweep --json/, "命令面=anchor-sweep 求值 CLI(误配 OPS_EVAL_PY 可辨)");
  const stubErr = shell("py-sweep-err", `printf '%s\n' '{"error":{"code":"internal","message":"load_db failed: disk","hint":"h"}}'\nexit 1\n`);
  const r2 = await anchorSweepCli({ evalPy: stubErr, dataDir: "/tmp/d" });
  assert.equal(r2.ok, false, "error 信封=失败非读数(--json 面不裸栈,spec §5.2)");
  assert.equal(r2.env.code, "internal", "python 侧 code 透传");
  assert.equal(r2.env.reason, "load_db failed: disk");
  const r3 = await anchorSweepCli({ evalPy: path.join(TMP, "no-such-python"), dataDir: "/tmp/d" });
  assert.equal(r3.ok, false);
  assert.equal(r3.env.code, "channel_missing", "ENOENT 归四码 channel_missing(通道四码兼容,PR #177)");
  const stubHang = shell("py-sweep-hang", "sleep 5\n");
  const r4 = await anchorSweepCli({ evalPy: stubHang, dataDir: "/tmp/d", timeoutMs: 400 });
  assert.equal(r4.ok, false);
  assert.equal(r4.env.code, "transient", "超时归四码 transient;gh/rg 兑底码不复用于 python 面");
});

await t("parseMcpSearchText:MCP wire 文本归一(真 fixture:provider/Sources 条目/机会式 snippet/Error 行;pi-web-access 0.44.0 实拍)", () => {
  assert.equal(typeof parseMcpSearchText, "function", "parseMcpSearchText 未导出(RED 面应先红)");
  const FX = `**Provider:** duckduckgo

ipsets dynamically updated with firehol's update-ipsets.sh script - firehol/blocklist-ipsets
Source: blocklist-ipsets/firehol_level1.netset at master - GitHub (https://github.com/firehol/blocklist-ipsets/blob/master/firehol_level1.netset)

Level 1 provides basic security against the most well-known attackers, with the minimum of false positives.
Source: GitHub - firehol/blocklist-ipsets: ipsets dynamically updated with ... (https://github.com/firehol/blocklist-ipsets)

---

**Sources:**
1. blocklist-ipsets/firehol_level1.netset at master - GitHub
   https://github.com/firehol/blocklist-ipsets/blob/master/firehol_level1.netset

2. GitHub - firehol/blocklist-ipsets: ipsets dynamically updated with ...
   https://github.com/firehol/blocklist-ipsets
---
Full search results are stored as responseId "mvm3csdaklwbz7".`;
  const p = parseMcpSearchText(FX);
  assert.equal(p.provider, "duckduckgo");
  assert.equal(p.results.length, 2, "Sources 块逐条目机解");
  assert.deepEqual(p.results.map((r) => r.url), [
    "https://github.com/firehol/blocklist-ipsets/blob/master/firehol_level1.netset",
    "https://github.com/firehol/blocklist-ipsets",
  ]);
  assert.match(p.results[0].snippet, /^ipsets dynamically/, "Source: 尾行前文=机会式 snippet");
  assert.match(p.results[1].snippet, /false positives/);
  assert.equal(p.error, null);
  // 错误面:provider 失败以 Error: 行内嵌(isError:false,包内吞进 query 结果;真网实拍形)
  const err = parseMcpSearchText("**Provider:** duckduckgo\n\nError: Configured search routing exhausted:\n  - duckduckgo [network]: fetch failed\n");
  assert.equal(err.results.length, 0);
  assert.match(err.error, /routing exhausted/);
  // 零命中真形(answer 空):无 Sources 条目也无 Error → 成功零命中(宁少算不冒充失败)
  const zero = parseMcpSearchText("**Provider:** duckduckgo\n\nNo results found.");
  assert.equal(zero.results.length, 0);
  assert.equal(zero.error, null);
  // 审后修 P2 钉:wire 漂移哨——三无(provider/Sources/Error)且非空 → io_error 执出
  // (升级后语法变形不得伪装成零命中;成功面必有 Provider 头,0.44.0 真网实拍钉)
  assert.throws(() => parseMcpSearchText("Some totally changed format v9\nno markers at all"), (e) => e.code === "io_error");
});

await t("classifyMcpSearchError:四码同族(quota/credential/network/config 各归位;ENOENT→channel_missing rc127;超时→transient rc124;402/balance→quota;坏配置→channel_missing;兑底 io_error 带下一步)", () => {
  assert.equal(typeof classifyMcpSearchError, "function", "classifyMcpSearchError 未导出(RED 面应先红)");
  assert.equal(classifyMcpSearchError(new Error("jina search failed (quota): HTTP 402: Payment Required")).code, "quota");
  assert.equal(classifyMcpSearchError(new Error("insufficient balance")).code, "quota");
  assert.equal(classifyMcpSearchError(new Error("routing exhausted: - duckduckgo [quota]: rate limited")).code, "quota");
  assert.equal(classifyMcpSearchError(new Error("brave search failed (credential): missing key")).code, "channel_auth");
  assert.equal(classifyMcpSearchError(new Error("Configured search routing exhausted:\n  - duckduckgo [network]: fetch failed")).code, "transient");
  assert.equal(classifyMcpSearchError(new Error("MCP CLI 提前退出(rc=1):Failed to parse /ops/web-search.json: Expected property name")).code, "channel_missing", "坏配置=部署面(通道不可用)");
  const enoent = Object.assign(new Error("spawn node ENOENT"), { code: "ENOENT" });
  assert.equal(classifyMcpSearchError(enoent).code, "channel_missing");
  assert.equal(classifyMcpSearchError(enoent).rc, 127);
  const to = classifyMcpSearchError(Object.assign(new Error("MCP 会话超时(>40000ms)"), { killed: true }));
  assert.equal(to.code, "transient");
  assert.equal(to.rc, 124);
  assert.equal(classifyMcpSearchError(new Error("MCP 协议错误:weird")).code, "io_error");
  for (const e of [enoent, new Error("x search failed (quota): y"), new Error("weird")]) {
    assert.match(classifyMcpSearchError(e).reason, /下一步/, "每码文案带下一步合法动作(MCP isError 语义)");
  }
});

await t("web_search 引擎接线:pi-web-access MCP CLI 可拉起(离线 initialize+tools/list 含 web_search;真网面部署段验)", async () => {
  const cli = path.join(AGENT, "node_modules", "pi-web-access", "dist", "mcp-cli.js");
  assert.ok(fs.existsSync(cli), "pi-web-access 未装配(npm ci 面;package.json pin 0.44.0)");
  const r = await new Promise((resolve, reject) => {
    const child = execFileCb(process.execPath, [cli], { timeout: 30_000 }, () => { /* exit 由 timeout 兑底 */ });
    let buf = "";
    const send = (o) => child.stdin.write(JSON.stringify(o) + "\n");
    child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const l = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!l.trim()) continue;
        const m = JSON.parse(l);
        if (m.id === 1) { send({ jsonrpc: "2.0", method: "notifications/initialized" }); send({ jsonrpc: "2.0", id: 2, method: "tools/list" }); }
        if (m.id === 2) { child.kill(); resolve(m.result); }
      }
    });
    child.on("exit", () => reject(new Error("MCP CLI 提前退出(离线 initialize 不应触网)")));
    send({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t4-selftest", version: "0" } } });
  });
  assert.ok(r.tools.some((tt) => tt.name === "web_search"), `MCP 工具面应含 web_search:${r.tools.map((tt) => tt.name).join(",")}`);
});

await t("web_search:坏路由配置(物化面损坏)→ channel_missing 信封(零网络;CLI 启动即崩,stderr 真因入信封)", async () => {
  const BAD = fs.mkdtempSync(path.join(os.tmpdir(), "t4-pwa-bad-"));
  fs.writeFileSync(path.join(BAD, "web-search.json"), "{broken json");
  const ws = host.tools.find((x) => x.name === "web_search");
  const orig = process.env.PI_CODING_AGENT_DIR;
  process.env.PI_CODING_AGENT_DIR = BAD;
  try {
    const r = await ws.execute("t_ws_bad", { query: "offline" });
    const sc = r.structuredContent;
    assert.equal(sc.ok, false);
    assert.equal(sc.code, "channel_missing");
    assert.match(sc.reason, /web-search\.json/, "stderr 真因(配置面)须入信封");
    assert.equal(typeof sc.trace.rc, "number");
  } finally {
    if (orig !== undefined) process.env.PI_CODING_AGENT_DIR = orig; else delete process.env.PI_CODING_AGENT_DIR;
    fs.rmSync(BAD, { recursive: true, force: true });
  }
});

await t("web_read:目标 url 环回先拒(SSRF 同 fetch_url 规,零网络——Jina 中继不当内网探针)", async () => {
  const wr = host.tools.find((x) => x.name === "web_read");
  const r = await wr.execute("t_wr0", { url: "http://127.0.0.1:9/x" });
  assert.equal(r.structuredContent.ok, false);
  assert.equal(r.structuredContent.code, "ssrf");
  assert.ok(!r.isError, "SSRF 拒 = 结构化信封,非异常");
});

await t("预算行:发现通道三件每轮 8/6/6(防失控非省钱,2026-10-24 裁定)", () => {
  const b = new ToolHost("discover").budgets;
  assert.equal(b.web_read, 8);
  assert.equal(b.web_search, 6);
  assert.equal(b.rss_parse, 6);
});

await t("契约对拍:JS 核心 ↔ Python rg_search_precedents 命中集相等(多词 OR/CJK/零命中/_schema 排除;共享 fixture;Python 面零改动)", async () => {
  // Python 参考实现 = backend/ipdb/_ops_store.py rg_search_precedents(argv 逐字对齐真源);
// ops_root() = $IP_RADAR_DATA_DIR/ops → 指到 fixtures 使两侧扫同一目录。
// 供给守卫:python3 导入 ipdb 失败 → T4SKIP(不计数不计红,环境缺席非契约破坏)。
  const ROOTDIR = path.resolve(AGENT, "..", "..");
  let pyOk = true;
  try {
    await execFileP("python3", ["-c", "import sys; sys.path.insert(0,'backend'); import ipdb._ops_store"], { cwd: ROOTDIR, timeout: 60_000 });
  } catch { pyOk = false; }
  if (!pyOk) { console.log("T4SKIP 契约对拍: python3 导入 ipdb 失败(供给缺席;backend venv 面由 backend job 保证)"); return; }
  // 共享目录:拷 fixture 快照到标准 ops 树(<tmp>/data/ops/precedents)——Python 面扫
  // $IP_RADAR_DATA_DIR/ops/precedents,JS 面扫同一目录(两侧根派生链不同,树形对齐)
  const DATA = fs.mkdtempSync(path.join(os.tmpdir(), "t4-parity-data-"));
  const PREDIR = path.join(DATA, "ops", "precedents");
  fs.mkdirSync(PREDIR, { recursive: true });
  for (const f of fs.readdirSync(FIXTURES_PREC)) fs.copyFileSync(path.join(FIXTURES_PREC, f), path.join(PREDIR, f));
  try {
    const pyHits = async (kws) => JSON.parse((await execFileP("python3",
      ["-c", "import sys,json; sys.path.insert(0,'backend'); from ipdb._ops_store import rg_search_precedents; print(json.dumps(rg_search_precedents(sys.argv[1:])))", ...kws],
      { cwd: ROOTDIR, env: { ...process.env, IP_RADAR_DATA_DIR: DATA }, timeout: 60_000 })).stdout);
    const jsHits = async (kws) => (await searchPrecedentsCore(kws, { precedentsDir: PREDIR })).files.map((f) => path.basename(f));
    for (const kws of [["排他率"], ["排他率", "sunset"], ["冻结", "死键"], ["mirror"], ["不存在的词xyz"]]) {
      const js = await jsHits(kws), py = await pyHits(kws);
      assert.deepEqual(js, py, `命中集不等(检索词 ${kws.join(" ")}):js=${js.join(",")} py=${py.join(",")}`);
      for (const n of js) assert.ok(!n.startsWith("_"), `_ 前缀件不得进命中(_schema/_INDEX 排除面):${n}`);
    }
  } finally { fs.rmSync(DATA, { recursive: true, force: true }); }
});

await t("结构钉:agent.mjs 预注入改调同源(不再 runLib inject_precedents);lib.sh 函数保留(pipeline/steps.mjs 仍调,退役注记)", () => {
  const agentSrc = fs.readFileSync(path.join(AGENT, "agent.mjs"), "utf8");
  assert.ok(!agentSrc.includes('runLib("inject_precedents"'), "宿主预注入应改调 tools.mjs searchPrecedentsCore(同源单源)");
  assert.ok(agentSrc.includes("searchPrecedentsCore"), "预注入须走 JS 核心");
  const libshSrc = fs.readFileSync(path.join(AGENT, "lib.sh"), "utf8");
  assert.match(libshSrc, /inject_precedents\(\)/, "lib.sh 函数须保留:pipeline/steps.mjs synthInput 仍调用(pipeline 面冻结不触)");
});

await t("工具面:discover=10 工具(PR3a +发现通道三件)、health=1 工具,全部声明 outputSchema+annotations", () => {
  const d = new ToolHost("discover").tools.map((x) => x.name).sort();
  assert.deepEqual(d, ["exclusive_probe", "fetch_url", "gh_search", "matrix_scan_summary", "queue_action", "read_file", "rss_parse", "search_precedents", "web_read", "web_search"]);
  const h = new ToolHost("health").tools.map((x) => x.name);
  assert.deepEqual(h, ["health_snapshot"]);
  for (const tool of [...new ToolHost("discover").tools, ...new ToolHost("health").tools]) {
    assert.ok(tool.outputSchema, `${tool.name} 缺 outputSchema(铁律③)`);
    assert.ok(tool.annotations, `${tool.name} 缺 annotations`);
  }
  const qa = new ToolHost("discover").tools.find((x) => x.name === "queue_action");
  assert.equal(qa.annotations.readOnlyHint, false, "唯一写工具 readOnly=false");
});

// ── 评审环修正波 1 钉子(修正②③④;零 API 零网络) ──────────────────────
await t("修正②:exclusive_probe 声明 executionMode=sequential(SDK 1.3.0 每工具执行模式,批次含本工具即整批逐个执行——串行为真,不再只序落定)", () => {
  const ep = new ToolHost("discover").tools.find((x) => x.name === "exclusive_probe");
  assert.equal(ep.executionMode, "sequential", "缺声明则 SDK 缺省 parallel,探针可并发(下载/_eval LMDB 读压)");
  for (const other of new ToolHost("discover").tools.filter((x) => x.name !== "exclusive_probe")) {
    assert.notEqual(other.executionMode, "sequential", "非探针工具不受牵连,保持缺省并发");
  }
});

await t("修正③:选层纯函数——--smoke 单独=smoke 层;缺省=faux 层;--only 钉单例(跨层)", async () => {
  const { selectCases } = await import("./golden/run-golden.mjs");
  const cases = JSON.parse(fs.readFileSync(path.join(AGENT, "golden/cases.json"), "utf8")).cases;
  const ids = (tier) => cases.filter((c) => c.tier === tier).map((c) => c.id);
  assert.deepEqual(selectCases(cases, { smoke: true }).map((c) => c.id), ids("smoke"), "--smoke 单独须选且仅选 smoke 层");
  assert.deepEqual(selectCases(cases, {}).map((c) => c.id), ids("faux"), "缺省 faux 层(旧缺陷:恒 faux)");
  assert.deepEqual(selectCases(cases, { smoke: true, only: "smoke_health" }).map((c) => c.id), ["smoke_health"], "--smoke --only 钉 smoke 单例");
  assert.deepEqual(selectCases(cases, { only: "discover_predicate_hit" }).map((c) => c.id), ["discover_predicate_hit"], "--only 可跨层钉 faux 单例");
  assert.deepEqual(selectCases(cases, { only: "不存在" }), [], "--only 未命中=空计划");
});

await t("修正④:smoke 层 fixture 树保全(台账/包=记账工件不灭失);faux 层照旧即删", async () => {
  const { cleanupFixture } = await import("./golden/run-golden.mjs");
  const smokeTmp = fs.mkdtempSync(path.join(os.tmpdir(), "gfix4-smoke-"));
  fs.mkdirSync(path.join(smokeTmp, "docs/ops/packages"), { recursive: true });
  const ledger = path.join(smokeTmp, "docs/ops/ledger.md");
  const pkg = path.join(smokeTmp, "docs/ops/packages/2026-10-20-discover-0000.md");
  fs.writeFileSync(ledger, "| 2026-10-20 | discover | glm-5.3 | in=1 | |\n");
  fs.writeFileSync(pkg, "## 注入判例\n");
  const kept = cleanupFixture("smoke", smokeTmp);
  assert.equal(kept, smokeTmp, "smoke 返回保全路径(结果行打印后仍整树在)");
  assert.ok(fs.existsSync(ledger) && fs.existsSync(pkg), "smoke 台账行+裁决包保全");
  const fauxTmp = fs.mkdtempSync(path.join(os.tmpdir(), "gfix4-faux-"));
  assert.equal(cleanupFixture("faux", fauxTmp), null, "faux 返回 null");
  assert.ok(!fs.existsSync(fauxTmp), "faux 一次性树照旧清理");
});

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`t4-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
