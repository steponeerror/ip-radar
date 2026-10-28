// budget-parity.test.mjs — T2 预算移植对拍(票 #226;spec 定案 3:budget.mjs 原样零复制 + 双点执法接线)
// 全程零网络零模型调用:GLM usage 用固定数值样本(形状取 T0 smoke 实测:单次 cost.total ≈ ¥0.00003–0.00004)。
// 对拍面:旧管线真源 ops/agent/pipeline/budget.mjs(只读 import)× v2 接线面(../budget.mjs 零复制 re-export
// + ../tasks/budget-guard.mjs 双点执法 guard + ../entry.mjs runRound 接线)。
// 断言口径:执法决策逐条一致(allow/deny/code/message)+ 剩余量逐条一致(帽−已用,符号值:负=超出)。
// 语义真源:ops/agent/DESIGN.md §6 预算四界行(迭代上限/token 轨迹/墙钟/花费帽 每轮 ¥3 ∧ 月度 ¥30,
// 同台账并发安全双点执法:准入+环内)+ 重复检测(工具调用哈希)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import * as oldBudget from "../../agent/pipeline/budget.mjs"; // 旧管线真源(只读对照;ops/agent 零改动红线)
import * as v2Budget from "../budget.mjs"; // v2 零复制接线面
import {
  admitRound, knobNames, postModelCall, preModelCall,
  resolveLedgerPath, roundKnobs, stepBoundary, sumUsageState,
} from "../tasks/budget-guard.mjs";
import { ROOT, runRound } from "../entry.mjs";

const V2_DIR = path.resolve(import.meta.dirname, "..");
const ENTRY = path.join(V2_DIR, "entry.mjs");

// —— 固定样本:票面参数(迭代帽/token 帽/墙钟/花费帽 ¥3 ∧ 月帽 ¥30 = 六旋钮生产缺省)+ GLM usage 数值样本 ——
const KNOB_ENV_SAMPLES = [
  { name: "生产缺省(空 env)", env: {} },
  { name: "收紧旋钮", env: {
    OPS_PIPELINE_MAX_MODEL_CALLS: "5", OPS_PIPELINE_TOKEN_BUDGET: "50000",
    OPS_PIPELINE_WALL_CLOCK_S: "600", OPS_PIPELINE_SPEND_CAP_CNY: "1",
    OPS_PIPELINE_MONTHLY_CAP_CNY: "9", OPS_PIPELINE_DUP_CALL_LIMIT: "2",
  } },
  { name: "零帽(宁少算极端面:帽=0=零预算即拒)", env: {
    OPS_PIPELINE_MAX_MODEL_CALLS: "0", OPS_PIPELINE_TOKEN_BUDGET: "0",
    OPS_PIPELINE_WALL_CLOCK_S: "0", OPS_PIPELINE_SPEND_CAP_CNY: "0",
  } },
];
// GLM usage 固定数值样本(glm-5.3-flash 量级;零网络:数字是死的,执法是纯函数)
const GLM_USAGE_SAMPLES = [
  { input: 1801, output: 76, totalTokens: 1877, cost: { input: 0.0000306, output: 0.0000064, total: 0.000037 } },
  { input: 120445, output: 3211, totalTokens: 123656, cost: { input: 0.0020476, output: 0.0002730, total: 0.0023206 } },
  { input: 65536, output: 1024, totalTokens: 66560, cost: { input: 0.0009432, output: 0.0001707, total: 0.00011139 } },
];
// 旧管线回合累计口径(agent.mjs subscribe:totalTokens += u.totalTokens ?? 0;cost += u.cost?.total ?? 0)
const accumulate = (samples) => {
  const acc = { totalTokens: 0, costCny: 0 };
  for (const u of samples) { acc.totalTokens += u.totalTokens ?? 0; acc.costCny += u.cost?.total ?? 0; }
  return acc;
};

test("零复制单源:v2 budget.mjs 导出面 = 旧管线 budget.mjs 逐名同引用(fork 即红)", () => {
  const oldKeys = Object.keys(oldBudget).sort();
  const v2Keys = Object.keys(v2Budget).sort();
  assert.deepEqual(v2Keys, oldKeys, `导出名集漂移:旧=${oldKeys} v2=${v2Keys}`);
  for (const k of oldKeys)
    assert.equal(v2Budget[k], oldBudget[k], `${k} 不是同一引用——零复制被破坏(整文件拷贝属违票兜底,须票面明示)`);
});

test("旋钮读面对拍:同 env → readBudgetKnobs/readDiscoverKnobs(旧)与 roundKnobs(v2)逐字段一致;非法=同文案用法错", () => {
  for (const { name, env } of KNOB_ENV_SAMPLES) {
    assert.deepEqual(roundKnobs(env, "health"), oldBudget.readBudgetKnobs(env), `health 旋钮漂移:${name}`);
    assert.deepEqual(roundKnobs(env, "discover"), oldBudget.readDiscoverKnobs(env), `discover 旋钮漂移:${name}`);
  }
  // discover 族无 tokenBudget 键(发现轮无 token 界,#207 T1);月帽/dup 共享同键
  assert.equal("tokenBudget" in roundKnobs({}, "discover"), false);
  assert.equal(roundKnobs({}, "discover").monthlyCapCny, roundKnobs({}, "health").monthlyCapCny);
  // 非法值:两面同 throw {usage:true} 同文案(exit 2 不带病跑轮判例)
  const capture = (fn) => { try { fn(); return null; } catch (e) { return e; } };
  for (const bad of ["-1", "abc"]) {
    const env = { OPS_PIPELINE_SPEND_CAP_CNY: bad };
    const o = capture(() => oldBudget.readBudgetKnobs(env));
    const n = capture(() => roundKnobs(env, "health"));
    assert.ok(o && n, `两面均须 throw:${bad}`);
    assert.equal(n.usage, true); assert.equal(o.usage, true);
    assert.equal(n.message, o.message, "用法错文案漂移");
  }
});

test("四界①③ attempt 前查对拍(旧 runModelStage 语义 × v2 preModelCall):决策/码/文案/剩余量逐条一致", () => {
  const knobs = oldBudget.readBudgetKnobs({}); // 生产缺省:12 调用/1800s
  const t0 = "2026-10-28T00:00:00.000Z";
  const cases = [ // [modelCalls, startedAtIso, nowMs 偏移, 说明]
    [0, t0, 0, "轮始零计数零流逝=放行"],
    [11, t0, 0, "第 12 次调用=帽内放行(等号放行)"],
    [12, t0, 0, "第 13 次调用=超帽拒(①)"],
    [0, t0, 1800_000, "流逝 1800s=帽内放行(等号放行)"],
    [0, t0, 1800_001, "流逝 1800.001s=超帽拒(③)"],
    [0, "not-a-date", 999_999, "不可解析起点=退化 0 不误杀"],
    [12, t0, 1800_001, "双违界=①先裁(旧检查点顺序:①→③)"],
  ];
  for (const [calls, startedAt, offMs, label] of cases) {
    const now = Date.parse(t0) + offMs;
    const oldDenyCalls = oldBudget.overCallsCap(calls, knobs.maxModelCalls);
    const oldDenyWall = oldBudget.overWallClock(startedAt, knobs.wallClockS, now);
    const d = preModelCall({ roundType: "health", knobs, modelCalls: calls, startedAtIso: startedAt, now });
    if (oldDenyCalls) {
      assert.equal(d.ok, false, label);
      assert.equal(d.code, "budget_exceeded", label);
      assert.equal(d.message, `预算四界①:模型调用将超帽(已计 ${calls}+1 > ${knobs.maxModelCalls},OPS_PIPELINE_MAX_MODEL_CALLS)`, `${label}:①文案漂移`);
      assert.equal(d.remaining.calls, knobs.maxModelCalls - calls, `${label}:①剩余调用数`);
    } else if (oldDenyWall) {
      assert.equal(d.ok, false, label);
      assert.equal(d.code, "wall_clock_exceeded", label);
      assert.equal(d.message, `预算四界③:墙钟 ${oldBudget.elapsedWallS(startedAt, now).toFixed(1)}s 超帽 ${knobs.wallClockS}s(OPS_PIPELINE_WALL_CLOCK_S)`, `${label}:③文案漂移`);
    } else {
      assert.equal(d.ok, true, label);
      assert.equal(d.remaining.calls, knobs.maxModelCalls - calls - 1, `${label}:attempt 后剩余调用数`);
    }
  }
  // 零帽特判(帽=0=零预算即拒;两界皆零面)
  const zero = oldBudget.readBudgetKnobs({ OPS_PIPELINE_MAX_MODEL_CALLS: "0", OPS_PIPELINE_WALL_CLOCK_S: "0" });
  const dz = preModelCall({ roundType: "health", knobs: zero, modelCalls: 0, startedAtIso: t0, now: Date.parse(t0) });
  assert.equal(dz.ok, false); assert.equal(dz.code, "budget_exceeded"); // ①先裁(0+1>0)
  // discover 文案指认 OPS_DISCOVER_*(#207 T1 per-type)
  const dk = oldBudget.readDiscoverKnobs({});
  const dd = preModelCall({ roundType: "discover", knobs: dk, modelCalls: dk.maxModelCalls, startedAtIso: t0, now: Date.parse(t0) });
  assert.equal(dd.message, `预算四界①:模型调用将超帽(已计 ${dk.maxModelCalls}+1 > ${dk.maxModelCalls},OPS_DISCOVER_MAX_MODEL_CALLS)`);
});

test("四界③ 相位边界查对拍(旧 runStages 步边界语义 × v2 stepBoundary)", () => {
  const knobs = oldBudget.readBudgetKnobs({});
  const t0 = "2026-10-28T00:00:00.000Z";
  for (const [offMs, expectOk] of [[0, true], [1800_000, true], [1800_001, false]]) {
    const now = Date.parse(t0) + offMs;
    const d = stepBoundary({ roundType: "health", knobs, startedAtIso: t0, now });
    assert.equal(d.ok, expectOk, `off=${offMs}`);
    assert.equal(d.ok, !oldBudget.overWallClock(t0, knobs.wallClockS, now), `off=${offMs}:决策须=旧 overWallClock`);
    if (!d.ok) {
      assert.equal(d.code, "wall_clock_exceeded");
      assert.equal(d.message, `预算四界③:墙钟 ${oldBudget.elapsedWallS(t0, now).toFixed(1)}s 超帽 ${knobs.wallClockS}s(OPS_PIPELINE_WALL_CLOCK_S)`);
    }
  }
  const z = oldBudget.readBudgetKnobs({ OPS_PIPELINE_WALL_CLOCK_S: "0" });
  assert.equal(stepBoundary({ roundType: "health", knobs: z, startedAtIso: t0, now: Date.parse(t0) }).ok, false, "零帽墙钟=恒拒");
});

test("四界②④ 结算后查对拍(旧 runModelStage 语义 × v2 postModelCall)+ GLM usage 样本累积", () => {
  const knobs = oldBudget.readBudgetKnobs({}); // token 200000 / spend ¥3
  const acc = accumulate(GLM_USAGE_SAMPLES);
  // 样本累计远低于帽 → 放行;剩余量 = 帽−已用(符号值)
  const d0 = postModelCall({ roundType: "health", knobs, totalTokens: acc.totalTokens, costCny: acc.costCny });
  assert.equal(d0.ok, true);
  assert.equal(d0.remaining.tokens, knobs.tokenBudget - acc.totalTokens);
  assert.equal(d0.remaining.spendCny, knobs.spendCapCny - acc.costCny);
  // 边界矩阵:等号放行,一尘即拒(②→④ 顺序;文案逐字对齐旧检查点)
  const cases = [
    [200000, 3, true, "双等号=放行"],
    [200001, 3, false, "token 超一=②拒"],
    [200000, 3.0000001, false, "花费超一尘=④拒"],
    [200001, 3.0000001, false, "双超=②先裁"],
  ];
  for (const [tokens, cost, ok, label] of cases) {
    const d = postModelCall({ roundType: "health", knobs, totalTokens: tokens, costCny: cost });
    assert.equal(d.ok, ok, label);
    assert.equal(d.ok, !(oldBudget.overTokenBudget(tokens, knobs.tokenBudget) || oldBudget.overSpendCap(cost, knobs.spendCapCny)), `${label}:决策须=旧纯函数`);
    if (!d.ok && oldBudget.overTokenBudget(tokens, knobs.tokenBudget))
      assert.equal(d.message, `预算四界②:token 轨迹 ${tokens} 超预算 ${knobs.tokenBudget}(OPS_PIPELINE_TOKEN_BUDGET)`, `${label}:②文案`);
    if (!d.ok && !oldBudget.overTokenBudget(tokens, knobs.tokenBudget))
      assert.equal(d.message, `预算四界④:花费 ¥${cost.toFixed(8)} 超帽 ¥${knobs.spendCapCny}(OPS_PIPELINE_SPEND_CAP_CNY)`, `${label}:④文案`);
  }
  // 发现轮:无 token 界(tokenBudget undefined 即跳过,巨量 token 只有 ④ 执法)
  const dk = oldBudget.readDiscoverKnobs({}); // spend ¥5
  assert.equal(postModelCall({ roundType: "discover", knobs: dk, totalTokens: 1e12, costCny: 4.99 }).ok, true);
  assert.equal(postModelCall({ roundType: "discover", knobs: dk, totalTokens: 1, costCny: 5.01 }).ok, false);
  // GLM 样本重复 k 份累计跨 ¥3 帽(迭代帽消费的实测量级路径)
  for (let k = 1; k <= 4; k++) {
    const a = accumulate(Array.from({ length: k }, () => GLM_USAGE_SAMPLES[1]));
    const d = postModelCall({ roundType: "health", knobs, totalTokens: a.totalTokens, costCny: a.costCny });
    assert.equal(d.ok, !(oldBudget.overTokenBudget(a.totalTokens, knobs.tokenBudget) || oldBudget.overSpendCap(a.costCny, knobs.spendCapCny)), `k=${k}`);
  }
});

test("环内 usage 聚合对拍:sumUsageState(harness UsageState)≡ 旧回合累计口径(GLM 样本)", () => {
  // v2 环内口径:轮 delta = settle 后 session usage − submit 前 snapshot(UsageState.models+tools 求和)。
  // UsageState.models 按 provider/modelId 累计(新回合叠加在同 key 上,非替换)——fixture 照此构造。
  const acc2 = (a, b) => ({ totalTokens: a.totalTokens + b.totalTokens, cost: { total: a.cost.total + b.cost.total } });
  const before = { models: { "zai-coding-cn/glm-5.3-flash": GLM_USAGE_SAMPLES[0] }, tools: {} };
  const after = {
    models: { "zai-coding-cn/glm-5.3-flash": acc2(GLM_USAGE_SAMPLES[0], GLM_USAGE_SAMPLES[1]) },
    tools: { probe_host: { totalTokens: 11, cost: { total: 0.0000011 } } },
  };
  const delta = {
    totalTokens: sumUsageState(after).totalTokens - sumUsageState(before).totalTokens,
    costCny: sumUsageState(after).costCny - sumUsageState(before).costCny,
  };
  const expect = { // 旧口径:本轮新发生的回合样本 = [1] + [probe 工具位]
    totalTokens: GLM_USAGE_SAMPLES[1].totalTokens + 11,
    costCny: GLM_USAGE_SAMPLES[1].cost.total + 0.0000011,
  };
  assert.ok(Math.abs(delta.totalTokens - expect.totalTokens) < 1e-9);
  assert.ok(Math.abs(delta.costCny - expect.costCny) < 1e-12);
  // 空库/缺字段退化面:零起步不炸
  assert.deepEqual(sumUsageState(undefined), { totalTokens: 0, costCny: 0 });
  assert.deepEqual(sumUsageState({ models: {}, tools: {} }), { totalTokens: 0, costCny: 0 });
});

test("月度准入对拍(¥30 ∧ est):admitRound(v2)与旧 admitOrRefuse 同裁决同文案同留痕", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-budget-admit-"));
  const mkLedger = (spendRows) => {
    const f = path.join(tmp, `ledger-${Math.random().toString(36).slice(2)}.md`);
    const month = oldBudget.monthNow();
    const lines = ["| 日期 | 轮次 | model | 用量 | 备注 |", "|---|---|---|---|---|"];
    spendRows.forEach((cost, i) => lines.push(`| ${month}-27 | 2026-${month.split("-")[1]}-0800-${i} | zai-coding-cn/glm-5.3-flash | in=1 out=2 total=3 cost=${cost} | r |`));
    // 异形行:他月行不计入、当月缺 cost 行=skipped
    lines.push(`| 2026-01-01 | old-round | m | in=1 out=1 total=2 cost=99 | r |`);
    lines.push(`| ${month}-28 | no-cost-round | m | in=1 | r |`);
    fs.writeFileSync(f, lines.join("\n") + "\n");
    return f;
  };
  const env = {}; // 生产缺省月帽 ¥30
  // 放行界:当月 29.93 + est 0.05 = 29.98 ≤ 30(等号放行面用 29.95+0.05=30.00)
  const okLedger = mkLedger([29.93]);
  const logs = [];
  const v2r = await admitRound({ env, roundType: "health", ledgerFile: okLedger, log: (l) => logs.push(l) });
  const oldFaceLedger = mkLedger([29.93]); // 旧面独立台账副本(拒绝才留痕;两副本同内容)
  const oldr = await oldBudget.admitOrRefuse({ ledgerFile: oldFaceLedger, capCny: env.OPS_PIPELINE_MONTHLY_CAP_CNY ?? 30, estCny: 0.05, env, log: () => {}, round: "health" });
  assert.equal(v2r.refused, false); assert.equal(oldr.refused, false);
  assert.deepEqual({ month: v2r.admission.month, spend: v2r.admission.spend, counted: v2r.admission.counted, skipped: v2r.admission.skipped, projected: v2r.admission.projected },
    { month: oldr.admission.month, spend: oldr.admission.spend, counted: oldr.admission.counted, skipped: oldr.admission.skipped, projected: oldr.admission.projected });
  assert.equal(v2r.admission.counted, 1, "当月 cost 行恰 1 计入"); assert.equal(v2r.admission.skipped, 1, "当月缺 cost 行恰 1 跳过");
  // 等号放行:29.95+0.05=30.00 ≤ 30
  const eq = await admitRound({ env, roundType: "health", ledgerFile: mkLedger([29.95]), log: () => {} });
  assert.equal(eq.refused, false, "等号=帽内放行");
  // 拒跑界:29.96+0.05=30.01 > 30 → 双面同拒;同码同文案;台账留痕行都写(行为等价含留痕)
  const v2RefLedger = mkLedger([29.96]);
  const v2ref = await admitRound({ env, roundType: "health", ledgerFile: v2RefLedger, log: (l) => logs.push(l) });
  const oldRefLedger = mkLedger([29.96]);
  const oldref = await oldBudget.admitOrRefuse({ ledgerFile: oldRefLedger, capCny: 30, estCny: 0.05, env, log: () => {}, round: "health" });
  assert.equal(v2ref.refused, true); assert.equal(oldref.refused, true);
  assert.equal(v2ref.code, oldref.code); assert.equal(v2ref.message, oldref.message, "拒跑文案漂移(refusalOf 单源,须逐字)");
  assert.match(v2ref.message, /月度预算拒跑:当月已花 ¥29\.96 \+ 本轮预算 ¥0\.05 > 月帽 ¥30/);
  for (const f of [v2RefLedger, oldRefLedger]) {
    const text = fs.readFileSync(f, "utf8");
    assert.match(text, /budget_monthly refused est=0\.05 cap=30/, `${f}:拒跑留痕行缺失`);
  }
  // est 非法=用法错(与旧 agent.mjs runRound 同读同校验同文案;校验先于读台账,admitRound reject)
  await assert.rejects(
    admitRound({ env: { OPS_PIPELINE_BUDGET_CNY: "-1" }, roundType: "health", ledgerFile: okLedger, log: () => {} }),
    (e) => e.usage === true && e.message === "OPS_PIPELINE_BUDGET_CNY 须为非负数,得到:-1",
  );
  assert.ok(logs.some((l) => l.includes("[admission] budget_monthly refused")), "[admission] log 行缺失");
  fs.rmSync(tmp, { recursive: true, force: true });
});

// est 校验的纯面对拍(admitRound 是 async,非法在校验即 throw——用同步子进程面钉 CLI exit 2)
test("月帽月读数对拍:monthNow/monthSpendOfLedgerText(v2 面=旧面)", () => {
  const month = oldBudget.monthNow();
  assert.equal(typeof month, "string"); assert.match(month, /^\d{4}-\d{2}$/);
  const sample = [
    `| ${month}-01 | r1 | m | in=1 out=1 total=2 cost=1.5 | x |`,
    `| ${month}-02 | r2 | m | in=1 out=1 total=2 cost=2.25 | x |`,
  ].join("\n");
  assert.deepEqual(v2Budget.monthSpendOfLedgerText(sample, month), oldBudget.monthSpendOfLedgerText(sample, month));
  assert.deepEqual(oldBudget.monthSpendOfLedgerText(sample, month), { spend: 3.75, counted: 2, skipped: 0 });
});

test("台账落位:LEDGER_FILE > DOCS_ROOT/ops/ledger.md > <仓根>/docs/ops/ledger.md(旧 agent.mjs runRound 同推导;#226 F1 钉死)", () => {
  // scaffold.test.mjs db 落位断言同模式。期望仓根取自 entry.mjs ROOT——entry 居 ops/agent-v2/ 浅一层,
  // 两层上移=仓根;budget-guard 居 tasks/ 子层须三层上移,推导深度不同而落点须同仓根(旧面缺省
  // = ops/agent/tools/shared.mjs DOCS_ROOT(仓根/docs)+ "ops/ledger.md";漂移=缺省 env 下月帽读到
  // 不存在文件,Σcost=0,¥30 kill switch 静默失效——F1 即此)。
  assert.equal(resolveLedgerPath({ LEDGER_FILE: "/tmp/ledger-x.md" }), "/tmp/ledger-x.md");
  assert.equal(resolveLedgerPath({ DOCS_ROOT: "/d" }), path.join("/d", "ops", "ledger.md"));
  assert.equal(resolveLedgerPath({}), path.join(ROOT, "docs", "ops", "ledger.md"),
    `缺省台账漂移:得 ${resolveLedgerPath({})},须 <仓根>/docs/ops/ledger.md`);
});

test("同参哈希对拍:dupKey/canonicalJson/dupRecord(v2 面=旧面;第 limit 次同参即拦)", () => {
  const tool = "web_search";
  const argVariants = [
    { q: "cve", lang: "zh", page: 1 },
    { page: 1, lang: "zh", q: "cve" }, // 键序无关
    { q: "cve", lang: "zh", page: 2 }, // 值变=新键
    { deep: { b: 1, a: [3, 2, 1] } }, // 嵌套+数组保序
    { uni: "判例预算四界" },
    undefined,
  ];
  // 键序无关性:同参数不同键序 → 同哈希(同参拦截的前提)
  assert.equal(v2Budget.dupKey(tool, argVariants[0]), v2Budget.dupKey(tool, argVariants[1]));
  assert.notEqual(v2Budget.dupKey(tool, argVariants[0]), v2Budget.dupKey(tool, argVariants[2]));
  for (const args of argVariants)
    assert.equal(v2Budget.dupKey(tool, args), oldBudget.dupKey(tool, args), "v2 dupKey 漂移");
  // dupRecord 序列:limit=3 → 第 3 次起 blocked;limit=0 → 停用
  for (const limit of [3, 0]) {
    const regOld = new Map(); const regV2 = new Map();
    const seq = [];
    for (let i = 0; i < 4; i++) {
      const o = oldBudget.dupRecord(regOld, tool, argVariants[0], limit);
      const n = v2Budget.dupRecord(regV2, tool, argVariants[0], limit);
      assert.equal(n.count, o.count); assert.equal(n.blocked, o.blocked);
      seq.push(n.blocked);
    }
    assert.deepEqual(seq, limit === 3 ? [false, false, true, true] : [false, false, false, false]);
  }
  const dupReg = new Map([[1, { tool, key: "k", count: 5 }], [2, { tool, key: "j", count: 9 }]]);
  assert.deepEqual(v2Budget.dupTop(dupReg, 1), oldBudget.dupTop(dupReg, 1));
});

test("entry 双点接线(零网络):拒跑信封/零帽拒/用法错 exit 2;拒跑零 harness 开销", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-budget-entry-"));
  const month = oldBudget.monthNow();
  const ledger = path.join(tmp, "ledger.md");
  fs.writeFileSync(ledger, `| 日期 | 轮次 | model | 用量 | 备注 |\n|---|---|---|---|---|\n| ${month}-27 | r | m | in=1 out=1 total=2 cost=29.96 | x |\n`);
  // ① 步前准入拒跑:29.96+0.05 > 30 → 信封 refused + code=budget_monthly + 台账留痕;零模型调用(拒跑先于 harness)
  const refused = await runRound({ roundId: "parity-refuse", content: "x", dbPath: path.join(tmp, "a.sqlite"), env: { LEDGER_FILE: ledger } });
  assert.equal(refused.status, "refused");
  assert.equal(refused.code, "budget_monthly");
  assert.match(refused.message, /月度预算拒跑/);
  assert.match(fs.readFileSync(ledger, "utf8"), /budget_monthly refused est=0\.05 cap=30/);
  // ② 零帽步前拒(四界①:0+1>0)——信封 failed+budget_exceeded,拒于 submit 前(零花费)
  const zeroCalls = await runRound({ roundId: "parity-zero-calls", content: "x", dbPath: path.join(tmp, "b.sqlite"), env: { OPS_PIPELINE_MAX_MODEL_CALLS: "0" } });
  assert.equal(zeroCalls.status, "failed");
  assert.equal(zeroCalls.code, "budget_exceeded");
  assert.match(zeroCalls.message, /预算四界①/);
  // ③ 零墙钟步前拒(四界③:帽=0 恒拒)
  const zeroWall = await runRound({ roundId: "parity-zero-wall", content: "x", dbPath: path.join(tmp, "c.sqlite"), env: { OPS_PIPELINE_WALL_CLOCK_S: "0" } });
  assert.equal(zeroWall.code, "wall_clock_exceeded");
  assert.match(zeroWall.message, /预算四界③/);
  // ④ 旋钮非法 → {usage:true} reject(CLI 面 exit 2,不带病跑轮)
  await assert.rejects(runRound({ roundId: "parity-bad-knob", content: "x", dbPath: path.join(tmp, "d.sqlite"), env: { OPS_PIPELINE_WALL_CLOCK_S: "abc" } }), (e) => e.usage === true);
  const cli = await new Promise((res) => {
    const c = spawn(process.execPath, [ENTRY, "parity-bad-knob-cli", "--content", "x", "--db", path.join(tmp, "e.sqlite")],
      { cwd: V2_DIR, env: { ...process.env, OPS_PIPELINE_WALL_CLOCK_S: "abc" } });
    let err = ""; c.stderr.on("data", (d) => { err += d; }); c.on("exit", (code) => res({ code, err }));
  });
  assert.equal(cli.code, 2, `旋钮非法须 exit 2(stderr=${cli.err})`);
  assert.match(cli.err, /OPS_PIPELINE_WALL_CLOCK_S 须为非负数/);
  fs.rmSync(tmp, { recursive: true, force: true });
});
