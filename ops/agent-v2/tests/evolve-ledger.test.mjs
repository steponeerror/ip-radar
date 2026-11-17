// evolve-ledger.test.mjs — #356 骨架 v1 红绿面(单元):月帽台账 + 熄火状态件 +
// 噪声带判定(票面验收门「新增台账/熄火/带判定的单元测试」;驱动器全链另见
// evolve-e2e.test.mjs)。三件各自纯函数面,零网络零模型零花费。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  evolutionSpendCapCny, monthKeyIso, monthSpendTotalCny, admitEvolutionRound, appendEvolutionSpend, evolutionDevRoot,
} from "../bench/evolution/ledger.mjs";
import {
  STALL_LIMIT, evolutionStatePath, readEvolutionState, writeEvolutionState, domainStateOf,
  applyRoundOutcome, applyRefusal, markHaltedReported,
} from "../bench/evolution/state.mjs";
import { judgePaired } from "../bench/evolution/judge.mjs";

const tmpDir = (p) => fs.mkdtempSync(path.join(os.tmpdir(), p));
const NOW = new Date("2026-11-17T04:00:00+08:00"); // 固定钟:月窗=2026-11

// ── 月帽台账(推广 spend.json 机制:#337 同律 + 月窗差异面)──────────────────
test("帽缺省 200;env 覆写;非法值用法红", () => {
  assert.equal(evolutionSpendCapCny({}), 200);
  assert.equal(evolutionSpendCapCny({ EVOLVE_SPEND_CAP_CNY: "50" }), 50);
  assert.equal(evolutionSpendCapCny({ EVOLVE_SPEND_CAP_CNY: "" }), 200); // 空串=缺省
  assert.throws(() => evolutionSpendCapCny({ EVOLVE_SPEND_CAP_CNY: "-1" }), /须为非负数/);
  assert.throws(() => evolutionSpendCapCny({ EVOLVE_SPEND_CAP_CNY: "abc" }), /须为非负数/);
});

test("台账缺席=0;入账回算;当月窗只计同月(上月条目不计入)", () => {
  const tmp = tmpDir("evolve-ledger-");
  const ledger = path.join(tmp, "spend.json");
  try {
    assert.equal(monthSpendTotalCny(ledger, NOW), 0, "缺席=0");
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "2026-11-16-0400-evolve", domain: "add-domain", costCny: 30, now: new Date("2026-11-16T10:00:00Z") });
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "2026-11-17-0400-evolve", domain: "add-domain", costCny: 20.5, now: new Date("2026-11-17T01:00:00Z") });
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "2026-10-02-0400-evolve", domain: "add-domain", costCny: 999, now: new Date("2026-10-02T01:00:00Z") }); // 上月:不入当月窗
    assert.equal(monthSpendTotalCny(ledger, NOW), 50.5, "回算不信存量 total_cny,只计同月");
    const j = JSON.parse(fs.readFileSync(ledger, "utf8"));
    assert.equal(j.entries.length, 3);
    assert.equal(j.total_cny, 1049.5, "展示位 total=全量(跨月)");
    assert.deepEqual(j.entries.map((e) => e.domain), ["add-domain", "add-domain", "add-domain"], "跨域字段在位(首跑只 add-domain)");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("原子写(P2-①):rename 前崩=旧台账原样可解析,不撕裂;正常入账无 .tmp 残留", () => {
  const tmp = tmpDir("evolve-atomic-");
  const ledger = path.join(tmp, "spend.json");
  try {
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "r1", domain: "add-domain", costCny: 1, now: NOW });
    // 崩在 rename 前(直写半途被击杀的崩溃点):新内容只到 .tmp,旧台账不动
    const realRename = fs.renameSync;
    fs.renameSync = () => { throw new Error("simulated crash before rename"); };
    try {
      assert.throws(() => appendEvolutionSpend({ ledgerPath: ledger, roundId: "r2", domain: "add-domain", costCny: 2, now: NOW }), /simulated crash/);
    } finally { fs.renameSync = realRename; }
    const j = JSON.parse(fs.readFileSync(ledger, "utf8")); // 旧值完整可解析(永不撕裂)
    assert.deepEqual(j.entries.map((e) => e.round_id), ["r1"]);
    // 崩点收拾后再入账:正常落账,无 .tmp 残留
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "r3", domain: "add-domain", costCny: 3, now: NOW });
    assert.deepEqual(JSON.parse(fs.readFileSync(ledger, "utf8")).entries.map((e) => e.round_id), ["r1", "r3"]);
    assert.ok(!fs.existsSync(`${ledger}.tmp`));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("admit:帽内放行;当月累计严格大于帽才拒(边界同 run-trial #337);拒启零建面", () => {
  const tmp = tmpDir("evolve-admit-");
  const ledger = path.join(tmp, "spend.json");
  try {
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "r1", domain: "add-domain", costCny: 200, now: NOW });
    const atCap = admitEvolutionRound({ ledgerPath: ledger, env: {}, now: NOW });
    assert.equal(atCap.ok, true, "== 帽放行(严格大于才拦)");
    appendEvolutionSpend({ ledgerPath: ledger, roundId: "r2", domain: "add-domain", costCny: 0.01, now: NOW });
    const over = admitEvolutionRound({ ledgerPath: ledger, env: {}, now: NOW });
    assert.equal(over.ok, false);
    assert.equal(over.code, "spend_cap");
    assert.match(over.message, /¥200\.0100 超月帽 ¥200/);
    const lifted = admitEvolutionRound({ ledgerPath: ledger, env: { EVOLVE_SPEND_CAP_CNY: "300" }, now: NOW });
    assert.equal(lifted.ok, true, "env 覆写放行");
    const nextMonth = admitEvolutionRound({ ledgerPath: ledger, env: {}, now: new Date("2026-12-01T12:00:00+08:00") });
    assert.equal(nextMonth.ok, true, "月窗滚动:12 月从零计");
    assert.equal(nextMonth.total, 0);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("坏台账 fail-closed:坏 JSON/字段缺席/非法 at=infra 红(不猜不重建)", () => {
  const tmp = tmpDir("evolve-bad-");
  try {
    const p1 = path.join(tmp, "bad-json.json");
    fs.writeFileSync(p1, "{oops");
    assert.throws(() => monthSpendTotalCny(p1, NOW), /不是合法 JSON/);
    const p2 = path.join(tmp, "no-entries.json");
    fs.writeFileSync(p2, JSON.stringify({ total_cny: 5 }));
    assert.throws(() => monthSpendTotalCny(p2, NOW), /entries 缺席/);
    const p3 = path.join(tmp, "bad-cost.json");
    fs.writeFileSync(p3, JSON.stringify({ entries: [{ at: "2026-11-01T00:00:00Z", round_id: "r", domain: "d", cost_cny: "3" }] }));
    assert.throws(() => monthSpendTotalCny(p3, NOW), /cost_cny\/at 非法/);
    const p4 = path.join(tmp, "bad-at.json");
    fs.writeFileSync(p4, JSON.stringify({ entries: [{ at: "yesterday", round_id: "r", domain: "d", cost_cny: 3 }] }));
    assert.throws(() => monthSpendTotalCny(p4, NOW), /at 非形/);
    assert.throws(() => appendEvolutionSpend({ ledgerPath: p1, roundId: "r", domain: "d", costCny: 1 }), /追加前解析失败/);
    assert.throws(() => appendEvolutionSpend({ ledgerPath: path.join(tmp, "ok.json"), roundId: "r", domain: "d", costCny: NaN }), /须为有限数/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("evolutionDevRoot:env 覆写优先;monthKeyIso 年月键", () => {
  assert.equal(evolutionDevRoot({ EVOLVE_DEV_ROOT: "/tmp/x" }), "/tmp/x");
  assert.equal(monthKeyIso("2026-11-17T20:00:00Z"), "2026-11");
  assert.equal(evolutionStatePath({ EVOLVE_DEV_ROOT: "/tmp/x" }), path.join("/tmp", "x", "state.json"));
});

// ── 熄火状态件(冠军指针 + 连续 3 轮带内零增益)──────────────────────────────
test("状态件:缺席=空态;坏 JSON/形状=红;原子写读回", () => {
  const tmp = tmpDir("evolve-state-");
  const p = path.join(tmp, "state.json");
  try {
    assert.deepEqual(readEvolutionState(p), { domains: {} });
    writeEvolutionState(p, { domains: { "add-domain": { champion_ref: "abc", stall_rounds: 1 } } });
    assert.equal(domainStateOf(readEvolutionState(p), "add-domain").champion_ref, "abc");
    assert.equal(domainStateOf(readEvolutionState(p), "rrsi-domain").stall_rounds, 0, "未接线域缺省形(容缺读)");
    fs.writeFileSync(p, "{oops");
    assert.throws(() => readEvolutionState(p), /不是合法 JSON/);
    fs.writeFileSync(p, JSON.stringify({ nope: 1 }));
    assert.throws(() => readEvolutionState(p), /domains 缺席/);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("熄火计数:增益轮清零+指针前移;零增益连续 3 轮翻 halted;未判定轮不加不清", () => {
  assert.equal(STALL_LIMIT, 3, "票面:连续 3 轮带内零增益熄火");
  let st = { domains: {} };
  const dom = (s) => domainStateOf(s, "add-domain");
  st = applyRoundOutcome(st, "add-domain", { roundId: "r1", judged: true, gained: false });
  assert.equal(dom(st).stall_rounds, 1);
  st = applyRoundOutcome(st, "add-domain", { roundId: "r2", judged: false, gained: false, candidateRef: null }); // 护栏红/数据不足
  assert.equal(dom(st).stall_rounds, 1, "未判定轮不入熄火账");
  assert.equal(dom(st).last_round_id, "r2", "但轮号照记");
  st = applyRoundOutcome(st, "add-domain", { roundId: "r3", judged: true, gained: false });
  st = applyRoundOutcome(st, "add-domain", { roundId: "r4", judged: true, gained: false });
  assert.equal(dom(st).stall_rounds, 3);
  assert.equal(dom(st).halted, true, "达限翻熄火");
  assert.equal(dom(st).halted_reported, false, "报完才置位(驱动器管)");
  st = markHaltedReported(st, "add-domain");
  assert.equal(dom(st).halted_reported, true);
  st = applyRoundOutcome(st, "add-domain", { roundId: "r5", judged: true, gained: true, candidateRef: "deadbeef" });
  assert.equal(dom(st).halted, false, "增益轮复活");
  assert.equal(dom(st).stall_rounds, 0);
  assert.equal(dom(st).champion_ref, "deadbeef", "循环冠军指针前移(≠master 并入)");
  assert.throws(() => applyRoundOutcome(st, "add-domain", { roundId: "r6", judged: true, gained: true }), /candidateRef/, "增益轮缺指针=红");
  const before = dom(st);
  applyRefusal(st, "add-domain", { roundId: "r7", code: "spend_cap" });
  assert.deepEqual(dom(st), before, "applyRefusal 纯函数不改入参(返回新态)");
});

// ── 噪声带判定(同会话成对 + k≥3 律)──────────────────────────────────────
test("带判定:带内差(≤sd)=零增益;带外正差=gained;负差=零增益", () => {
  // 构造:cand−champ 逐对 [0.02, 0.01, 0.03] → mean=0.02, sd≈0.01 → 0.02>0.01 带外正
  const gainPairs = [
    { question: "a", replica: "r1", champFrac: 0.5, candFrac: 0.52 },
    { question: "a", replica: "r2", champFrac: 0.5, candFrac: 0.51 },
    { question: "a", replica: "r3", champFrac: 0.5, candFrac: 0.53 },
  ];
  const g = judgePaired({ pairs: gainPairs });
  assert.equal(g.insufficient, false);
  assert.equal(g.gained, true, "mean 0.02 > sd 0.01:带外正增益");
  assert.equal(g.champ_mean, 0.5);
  // 平移候选成带内:cand−champ 逐对 [0.02, −0.02, 0.02] → mean≈0.0067 sd≈0.023 → 带内
  const flatPairs = [
    { question: "a", replica: "r1", champFrac: 0.5, candFrac: 0.52 },
    { question: "a", replica: "r2", champFrac: 0.5, candFrac: 0.48 },
    { question: "a", replica: "r3", champFrac: 0.5, candFrac: 0.52 },
  ];
  const f = judgePaired({ pairs: flatPairs });
  assert.equal(f.gained, false, "噪声带内差异不是增益(SKILL.md k≥3 律)");
  assert.ok(f.mean_diff <= f.sd_diff);
  // 负差
  const negPairs = gainPairs.map((p) => ({ ...p, champFrac: p.candFrac, candFrac: p.champFrac }));
  assert.equal(judgePaired({ pairs: negPairs }).gained, false);
});

test("带判定:有效对 <3=数据不足(非增益非零增益,不入熄火账);崩对入 missing;逐题面在位", () => {
  const few = judgePaired({ pairs: [
    { question: "a", replica: "r1", champFrac: 0.5, candFrac: 0.9 },
    { question: "a", replica: "r2", champFrac: 0.5, candFrac: 0.9 },
  ] });
  assert.equal(few.insufficient, true);
  assert.equal(few.gained, false);
  assert.equal(few.band.low, null);
  const withMissing = judgePaired({ pairs: [
    { question: "a", replica: "r1", champFrac: 0.5, candFrac: 0.6 },
    { question: "a", replica: "r2", champFrac: 0.5, candFrac: 0.7 },
    { question: "a", replica: "r3", champFrac: 0.5, candFrac: 0.8 },
    { question: "b", replica: "r1", champFrac: null, candFrac: 0.4 }, // 崩 trial:无效对
    { question: "b", replica: "r2", champFrac: 0.4, candFrac: null },
  ] });
  assert.equal(withMissing.n, 3);
  assert.equal(withMissing.missing, 2);
  assert.equal(withMissing.gained, true, "仅有效对入统计");
  assert.deepEqual(withMissing.per_question.map((q) => q.question), ["a"], "逐题面只含有效对题");
});
