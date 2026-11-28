// test_daily_digest.mjs — daily-digest.mjs 纯函数面单测(#368;CI 面=ci.yml 单行,
// 同 scripts/test_*.mjs 律)。钉:信封解析/红项判定/两源合并/空数据日/行数帽/
// 双渲染(P1-2)/48h 终局补报带(P1-3)/缺 gates 红(P2-1)/push 退出码(P2-3)。
// 只测纯函数:ssh/文件 IO 面由装机冒烟(票面「手动触发一次真收 lark」)覆盖。
import test from "node:test";
import assert from "node:assert/strict";
import {
  roundIdMs,
  inWindow,
  summarizeServerRound,
  parseLedgerRows,
  ledgerReadings,
  shadowNewRounds,
  summarizeEvolveRound,
  summarizeAddRound,
  collectRedItems,
  renderDigest,
  renderDigestPush,
  summarizeCadence,
  HEARTBEAT_RED_H,
  QUALITY_RED_H,
  pushExitCode,
  pushLark,
  splitScanBands,
  overdueRoundLines,
  plainClock,
  plainRedItem,
} from "./daily-digest.mjs";

// —— 轮 id 钟面与 24h 窗 ——

test("roundIdMs:服务器 id 按 UTC,本机 id 按 CST(-8h);坏形状 null", () => {
  assert.equal(roundIdMs("2026-11-20-1219-health"), Date.UTC(2026, 10, 20, 12, 19));
  assert.equal(roundIdMs("2026-11-20-1914-evolve", 480), Date.UTC(2026, 10, 20, 11, 14));
  assert.equal(roundIdMs("garbage"), null);
  assert.equal(roundIdMs(""), null);
});

test("inWindow:滚动 24h 边界(开区闭区)+ 时区偏移", () => {
  const now = Date.UTC(2026, 10, 20, 13, 0); // 21:00 CST
  assert.equal(inWindow("2026-11-20-0300-health", now), true); // 11:00 CST 今日
  assert.equal(inWindow("2026-11-19-2200-discover", now), true); // 06:00 CST 今日
  assert.equal(inWindow("2026-11-19-1200-health", now), false); // 昨午,窗外
  assert.equal(inWindow("2026-11-19-1301-health", now), true); // 恰窗内缘(now-24h+1min)
  assert.equal(inWindow("2026-11-19-1259-health", now), false);
  assert.equal(inWindow("2026-11-20-1914-evolve", now, { utcOffsetMin: 480 }), true); // 本机轮按 CST 面
  assert.equal(inWindow("2026-11-19-2159-evolve", now, { utcOffsetMin: 480 }), true); // 昨 21:59 CST(窗内缘=昨 21:00 CST)
  assert.equal(inWindow("2026-11-19-2059-evolve", now, { utcOffsetMin: 480 }), false); // 昨 20:59 CST=窗外
});

// —— 服务器轮信封(gates+exits)——

const gatesOk = { records: [{ name: "G_PROBE", pass: true }, { name: "G_VERIFY", pass: true }] };
const gatesFail = { records: [{ name: "G_PROBE", pass: true }, { name: "G_VERIFY", pass: false }] };
const exitsGreen = { triggered: false, findings_n: 0 };
const exitsRed = { triggered: true, findings_n: 2 };

test("summarizeServerRound:gates 全过=ok;败闸留名;缺 gates=null 不猜", () => {
  assert.deepEqual(summarizeServerRound("r1-health", gatesOk, exitsGreen).ok, true);
  const bad = summarizeServerRound("r2-health", gatesFail, null);
  assert.equal(bad.ok, false);
  assert.deepEqual(bad.failed_gates, ["G_VERIFY"]);
  const noGates = summarizeServerRound("r3-discover", null, null);
  assert.equal(noGates.ok, null);
  assert.equal(noGates.exits_triggered, false);
  assert.equal(summarizeServerRound("r4-health", gatesOk, exitsRed).findings_n, 2);
  assert.equal(summarizeServerRound("r4-health", gatesOk, exitsRed).exits_triggered, true);
});

// —— 台账行 ——

const LEDGER = [
  "# 注释行不入",
  "| 日期 | 轮型 | model | 用量 | 备注 |",
  "|---|---|---|---|---|",
  "| 2026-11-20 | health | pipeline-real | in=8357 out=747 total=9104 cost=0.00162705 | pipeline:2026-11-20-0300-health |",
  "| 2026-11-20 | health | — | — | memory_peak_bytes=774287360(=轮始基线) |",
  "| 2026-11-20 | health | — | — | budget_monthly refused est=0.05 cap=30 |",
  "| 2026-11-19 | health | pipeline-real | in=1 out=1 cost=0.5 | pipeline:2026-11-19-2200-discover |",
].join("\n");

test("parseLedgerRows:cost/round_id 提取;memory 行两字段 null;拒跑留痕行标记", () => {
  const rows = parseLedgerRows(LEDGER);
  assert.equal(rows.length, 4); // 表头/分隔线 cells<5 或无 round 数据被滤
  const cost = rows.find((r) => r.round_id === "2026-11-20-0300-health");
  assert.equal(cost.cost_cny, 0.00162705);
  const mem = rows.find((r) => r.raw.includes("memory_peak"));
  assert.equal(mem.cost_cny, null);
  assert.equal(mem.round_id, null);
  const refused = rows.find((r) => r.refused);
  assert.equal(refused.date, "2026-11-20");
});

test("ledgerReadings:窗内按轮 id 集合;当月按日期列;拒跑按窗 UTC 日期", () => {
  const rows = parseLedgerRows(LEDGER);
  const rd = ledgerReadings(rows, {
    windowRoundIds: new Set(["2026-11-20-0300-health"]),
    windowDates: ["2026-11-20", "2026-11-19"],
    month: "2026-11",
  });
  assert.equal(rd.window_cost_cny, 0.00162705);
  assert.equal(rd.window_rows_n, 1);
  assert.equal(rd.month_cost_cny, 0.50162705); // 0.00162705+0.5(memory/拒跑行无 cost 不计)
  assert.equal(rd.refusals.length, 1);
  const rdOtherMonth = ledgerReadings(rows, {
    windowRoundIds: new Set(),
    windowDates: [],
    month: "2026-10",
  });
  assert.equal(rdOtherMonth.month_cost_cny, 0);
  assert.equal(rdOtherMonth.refusals.length, 0);
});

// —— 发现轮 issue 开票读数(#384;enqueue-issues.json 直读,字段名与轮信封 issues_opened 同名) ——

test("summarizeServerRound:enqueue 工件读 issues_opened/issues_failed/候选名单;缺工件(健康轮/旧发现轮)=0", () => {
  const enqueue = { issues_opened: 2, issues_failed: 1,
    issues: [{ candidate: "rdns", status: "created", issue_url: "https://github.com/x/1" }, { candidate: "quality_cand", status: "created" }, { candidate: "dead_cand", status: "failed", code: "gh_error", reason: "…" }] };
  const r = summarizeServerRound("2026-11-22-2200-discover", { records: [] }, null, enqueue);
  assert.equal(r.ok, true);
  assert.equal(r.issues_opened, 2);
  assert.equal(r.issues_failed, 1);
  assert.deepEqual(r.issue_candidates, ["rdns", "quality_cand"], "只计 created 面(failed 不入名单)");
  const h = summarizeServerRound("2026-11-22-0300-health", { records: [] }, null, null);
  assert.equal(h.issues_opened, 0);
  assert.deepEqual(h.issue_candidates, []);
});

// —— 影子零增轮 ——

test("shadowNewRounds:cutoff 后增轮被抓,恰 cutoff 与更早不算", () => {
  const ids = ["2026-11-19-1940-health", "2026-11-20-1140-health", "2026-11-20-1219-health"];
  assert.deepEqual(shadowNewRounds(ids), ["2026-11-20-1219-health"]);
  assert.deepEqual(shadowNewRounds(["2026-11-20-0340-health"]), []);
  assert.deepEqual(shadowNewRounds([]), []);
});

// —— 演化/fleet 轮 ——

test("summarizeEvolveRound:ok/error.code;无信封=null", () => {
  assert.equal(summarizeEvolveRound({ ok: true, round_id: "r" }).ok, true);
  const bad = summarizeEvolveRound({ ok: false, round_id: "r", error: { code: "cards_missing" } });
  assert.equal(bad.ok, false);
  assert.equal(bad.code, "cards_missing");
  assert.equal(summarizeEvolveRound(null).ok, null);
  // 在跑轮占位对象(仅 round_id,无 ok 键)=未收口,不算红(readLocalFace 路径)
  const inFlight = summarizeEvolveRound({ round_id: "2026-11-20-1914-evolve" });
  assert.equal(inFlight.ok, null);
  assert.equal(inFlight.round_id, "2026-11-20-1914-evolve");
});

test("summarizeAddRound:failed 态或败闸=!ok;running+全过=ok;缺 gates=null", () => {
  assert.equal(summarizeAddRound("a-add", { status: "failed" }, gatesOk).ok, false);
  assert.equal(summarizeAddRound("a-add", { status: "running" }, gatesFail).ok, false);
  assert.equal(summarizeAddRound("a-add", { status: "running" }, gatesOk).ok, true);
  assert.equal(summarizeAddRound("a-add", null, null).ok, null);
  const adm = { status: "running", monthly_admission: { ok: false, spend: 29.96, est: 0.05, cap: 30 } };
  assert.equal(summarizeAddRound("a-add", adm, gatesOk).monthly_admission.ok, false);
});

// #430 口径(监督者定,用户可推翻):中止不算 ok——门全绿的中止轮此前被算绿(票面病);
// ok=false 且由 renderDigest/collectRedItems 单列「中止」行呈现(不判红:中止=人为停,
// 非失败证据;败闸照旧红,闸红是失败证据不因中止灭失)。
test("summarizeAddRound:aborted 不算 ok(#430)", () => {
  assert.equal(summarizeAddRound("a-add", { status: "aborted" }, gatesOk).ok, false);
  assert.equal(summarizeAddRound("a-add", { status: "aborted" }, gatesFail).ok, false, "败闸的中止轮照旧 !ok");
});

test("renderDigest/collectRedItems/renderDigestPush:中止轮单列「中止」行,不入绿账不判红(#430)", () => {
  const mk = (id, status, gates, ok) => ({ round_id: id, ok, status, failed_gates: gates, monthly_admission: null });
  const local = greenLocal({ add_rounds: [
    mk("2026-11-20-1000-add", "done", [], true),
    mk("2026-11-20-1100-add", "aborted", [], false),
  ] });
  const server = greenServer();
  const reds = collectRedItems({ server, local });
  assert.equal(reds.length, 0, "中止(gates 全绿)不判红——单列行呈现,不进 ⚠ 计数");
  const { body } = renderDigest({ dateLabel: "2026-11-20", server, local, reds });
  assert.match(body, /fleet add 1\/1 绿:1000✓/, "绿账分母不含中止轮");
  assert.match(body, /fleet add 中止 1 轮:1100/, "中止单列一行(#430)");
  assert.ok(!body.includes("1100✗") && !body.includes("1100?"), "中止轮不入绿行标记列");
  const push = renderDigestPush({ dateLabel: "2026-11-20", server, local, reds });
  assert.match(push.body, /自动加源 1\/1 成功:10:00✓/);
  assert.match(push.body, /有 1 轮没跑完就被停了/, "推送版同面单列(大白话)");
  // 败闸的中止轮仍红(证据面:闸红不因中止灭失)
  const local2 = greenLocal({ add_rounds: [mk("2026-11-20-1200-add", "aborted", ["G_VERIFY"], false)] });
  const reds2 = collectRedItems({ server: greenServer(), local: local2 });
  assert.equal(reds2.length, 1);
  assert.match(reds2[0], /fleet 2026-11-20-1200-add !ok\(status=aborted;闸败:G_VERIFY\)/);
  // 跨窗旧带同律(评审 P1-1:改前门全绿的中止轮次日会出一条假红项,推送文案还说成「失败」)
  const od = overdueRoundLines("fleet", [
    mk("2026-11-19-1100-add", "aborted", [], false),
    mk("2026-11-19-1200-add", "aborted", ["G_VERIFY"], false),
    mk("2026-11-19-1300-add", "failed", [], false),
  ]);
  assert.deepEqual(od.reds, [
    "fleet 2026-11-19-1200-add 终局 !ok(G_VERIFY)(跨窗补报)",
    "fleet 2026-11-19-1300-add 终局 !ok(status=failed)(跨窗补报)",
  ], "门全绿的中止轮不进红项;有没过的门的中止轮和失败轮照旧红");
  assert.equal(od.notes.length, 1);
  assert.match(od.notes[0], /fleet 2026-11-19-1100-add 已中止/);
});

// —— 红项判定(两源合并)——

test("collectRedItems:票面四类+影子+读取失败,逐条留轮 id;全绿为空", () => {
  const reds = collectRedItems({
    server: {
      error: "ssh: connect timed out",
      rounds: [
        { round_id: "2026-11-20-0300-health", ok: false, failed_gates: ["G_VERIFY"], exits_triggered: false, findings_n: 0 },
        { round_id: "2026-11-20-1100-health", ok: true, failed_gates: [], exits_triggered: true, findings_n: 3 },
      ],
      refusals: [{ date: "2026-11-20", raw: "| 2026-11-20 | health | — | — | budget_monthly refused est=0.05 cap=30 |" }],
      shadow_new: ["2026-11-20-1219-health"],
    },
    local: {
      evolve: {
        halted: true,
        stall_rounds: 1,
        last_round_id: "2026-11-19-1915-evolve",
        spend_total_cny: 26.19,
        rounds: [{ round_id: "2026-11-20-1914-evolve", ok: false, code: "cards_missing" }],
      },
      add_rounds: [
        { round_id: "2026-11-20-1000-add", ok: false, status: "failed", failed_gates: ["G_VERIFY"], monthly_admission: null },
        { round_id: "2026-11-20-1100-add", ok: true, status: "running", failed_gates: [], monthly_admission: { ok: false, spend: 29.96, est: 0.05, cap: 30 } },
      ],
    },
  });
  const joined = reds.join("\n");
  assert.match(joined, /服务器面读取失败/);
  assert.match(joined, /2026-11-20-0300-health 信封 !ok/);
  assert.match(joined, /finding 出口触发\(findings=3\)/);
  assert.match(joined, /拒启触帽留痕/);
  assert.match(joined, /影子树增轮/);
  assert.match(joined, /演化已熄火/);
  assert.match(joined, /演化轮 2026-11-20-1914-evolve !ok\(cards_missing\)/);
  assert.match(joined, /fleet 2026-11-20-1000-add !ok/);
  assert.match(joined, /fleet 月帽拒启/);
  assert.equal(collectRedItems({ server: { rounds: [] }, local: { evolve: { rounds: [] }, add_rounds: [] } }).length, 0);
});

test("collectRedItems:演化花费超帽(缺省帽 200)", () => {
  const reds = collectRedItems({
    server: {},
    local: { evolve: { spend_total_cny: 261.86, rounds: [] }, add_rounds: [] },
  });
  assert.equal(reds.length, 1);
  assert.match(reds[0], /超月帽 ¥200/);
});

// —— 渲染:两源合并 / 空数据日 / 行数帽 ——

const greenServer = (over = {}) => ({
  error: null,
  rounds: [
    { round_id: "2026-11-20-0300-health", ok: true, failed_gates: [], exits_triggered: false, findings_n: 0 },
    { round_id: "2026-11-20-1100-health", ok: true, failed_gates: [], exits_triggered: false, findings_n: 0 },
    { round_id: "2026-11-20-2200-discover", ok: true, failed_gates: [], exits_triggered: false, findings_n: 0, issues_opened: 1, issues_failed: 0, issue_candidates: ["gaoyifan_cn_ip"] },
  ],
  ledger: { window_cost_cny: 0.0032, month_cost_cny: 0.0049 },
  refusals: [],
  shadow_new: [],
  missed_note: null,
  ...over,
});
// #384 issue 0 张面(缺省夹具带 1 张,单独钉两态;旧 propose_rows 面退役)
const greenServerNoIssues = (over = {}) => greenServer({
  rounds: greenServer().rounds.map((r) => ({ ...r, issues_opened: 0, issues_failed: 0, issue_candidates: [] })),
  ...over,
});
const greenLocal = (over = {}) => ({
  evolve: {
    halted: false,
    stall_rounds: 1,
    last_round_id: "2026-11-19-1915-evolve",
    spend_total_cny: 26.19,
    rounds: [{ round_id: "2026-11-20-1914-evolve", ok: null, code: null }],
  },
  add_rounds: [
    {
      round_id: "2026-11-20-1000-add",
      ok: true,
      status: "running",
      failed_gates: [],
      monthly_admission: { ok: true, spend: 0.31, est: 0.05, cap: 30 },
    },
  ],
  ...over,
});

test("renderDigest:两源合并出稿,≤30 行,绿日标题无 ⚠", () => {
  const reds = collectRedItems({ server: greenServer(), local: greenLocal() });
  const { title, body } = renderDigest({ dateLabel: "2026-11-20", server: greenServer(), local: greenLocal(), reds });
  assert.equal(reds.length, 0);
  assert.equal(title, "ip-radar 日报 2026-11-20");
  assert.match(body, /健康 2\/2 绿:0300✓ 1100✓/);
  assert.match(body, /发现 1\/1 绿:2200✓/);
  assert.match(body, /发现轮 issue 1 张\(needs-triage\):gaoyifan_cn_ip/);
  assert.match(body, /影子树零增轮/);
  assert.match(body, /演化:未熄火\(stall=1\),当日轮 1914\(无信封,未收口\);花费 ¥26\.19\/¥200/);
  assert.match(body, /fleet add 1\/1 绿:1000✓;月帽 ¥0\.31\/¥30/);
  assert.ok(body.split("\n").length <= 30, `行数 ${body.split("\n").length}`);
});

test("renderDigest:空数据日=「当日无轮」且不发红", () => {
  const emptyServer = { error: null, rounds: [], ledger: { window_cost_cny: 0, month_cost_cny: 0 }, refusals: [], shadow_new: [], missed_note: null };
  const emptyLocal = { evolve: { halted: false, stall_rounds: 0, last_round_id: null, spend_total_cny: null, rounds: [] }, add_rounds: [] };
  const reds = collectRedItems({ server: emptyServer, local: emptyLocal });
  const { title, body } = renderDigest({ dateLabel: "2026-11-21", server: emptyServer, local: emptyLocal, reds });
  assert.equal(reds.length, 0);
  assert.ok(body.includes("当日无轮"), "空日须含「当日无轮」一行(票面验收)");
  assert.ok(body.split("\n").filter((l) => l.includes("当日无轮")).length >= 2); // 两面各一行
  assert.equal(title, "ip-radar 日报 2026-11-21");
});

test("renderDigest:红日标题带 ⚠(计数);红项超帽截断仍 ≤30 行", () => {
  const manyReds = Array.from({ length: 40 }, (_, i) => `红项${i}`);
  const { title, body } = renderDigest({ dateLabel: "2026-11-20", server: greenServer(), local: greenLocal(), reds: manyReds });
  assert.match(title, /⚠$/);
  assert.match(body.split("\n")[0], /⚠\(40 红项\)/);
  const n = body.split("\n").length;
  assert.ok(n <= 30, `行数 ${n}`);
  assert.match(body, /另 \d+ 条见 dev\/ops-digest\/2026-11-20\.md/);
});

// —— P1-2 双渲染:push 版截断,落盘版全量红项附录 ——

test("renderDigest:落盘版 fileBody 含全量红项附录;push 版截断不带余量(P1-2)", () => {
  const manyReds = Array.from({ length: 40 }, (_, i) => `红项${i}`);
  const { body, fileBody } = renderDigest({ dateLabel: "2026-11-20", server: greenServer(), local: greenLocal(), reds: manyReds });
  assert.ok(body.split("\n").length <= 30);
  assert.ok(!body.includes("红项39"), "push 版尾部余量应被截断");
  assert.match(fileBody, /## 红项附录\(全量 40 条/);
  assert.ok(fileBody.includes("- ⚠ 红项0") && fileBody.includes("- ⚠ 红项39"), "落盘附录全量不截断");
  assert.ok(fileBody.startsWith(body), "落盘版=push 版+附录(前缀保持)");
});

test("renderDigest:无红项日落盘版=push 版,无附录(P1-2)", () => {
  const server = greenServer();
  const local = greenLocal();
  const reds = collectRedItems({ server, local });
  assert.equal(reds.length, 0);
  const { body, fileBody } = renderDigest({ dateLabel: "2026-11-20", server, local, reds });
  assert.equal(fileBody, body);
});

// —— P1-3 跨窗终局补报带(48h 扫描)——

test("splitScanBands:窗内(≤24h)/旧带(24h<龄≤48h)/超带丢弃(P1-3)", () => {
  const now = Date.UTC(2026, 10, 20, 13, 0); // 21:00 CST 跑时
  const { window, overdue } = splitScanBands(
    [
      "2026-11-20-0300-health", // 窗内(11:00 CST)
      "2026-11-19-1301-health", // 恰 24h+1min 前 → 窗内
      "2026-11-19-1300-health", // 恰 24h 前 → 旧带(开区闭区同 inWindow)
      "2026-11-18-1301-health", // 47h59m 前 → 旧带
      "2026-11-18-1300-health", // 恰 48h 前 → 丢弃
      "garbage",                // 坏形状不猜
    ],
    now,
  );
  assert.deepEqual(window, ["2026-11-20-0300-health", "2026-11-19-1301-health"]);
  assert.deepEqual(overdue, ["2026-11-19-1300-health", "2026-11-18-1301-health"]);
  // 本机 CST 钟面同律:昨 21:00 CST 恰起跑的轮=评审活例(21:00 前起跑、窗后收口)
  const cst = splitScanBands(
    ["2026-11-19-2101-evolve", "2026-11-19-2100-evolve", "2026-11-19-2059-evolve"],
    now,
    { utcOffsetMin: 480 },
  );
  assert.deepEqual(cst.window, ["2026-11-19-2101-evolve"]);
  assert.deepEqual(cst.overdue, ["2026-11-19-2100-evolve", "2026-11-19-2059-evolve"]);
});

test("overdueRoundLines:ok:false=红、无信封=注记不红、ok:true 静默;why 链 code→闸→status(P1-3)", () => {
  const { reds, notes } = overdueRoundLines("演化轮", [
    { round_id: "2026-11-19-1914-evolve", ok: false, code: "cards_missing" },
    { round_id: "2026-11-19-1800-evolve", ok: null, code: null },
    { round_id: "2026-11-19-1700-evolve", ok: true, code: null },
  ]);
  assert.equal(reds.length, 1);
  assert.match(reds[0], /演化轮 2026-11-19-1914-evolve 终局 !ok\(cards_missing\)\(跨窗补报\)/);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /2026-11-19-1800-evolve 跨窗无信封\(在跑或未收口,不判红\)/);
  const fl = overdueRoundLines("fleet", [
    { round_id: "2026-11-19-1000-add", ok: false, failed_gates: ["G_VERIFY"], status: "failed" },
    { round_id: "2026-11-19-1100-add", ok: false, failed_gates: [], status: "failed" },
  ]);
  assert.match(fl.reds[0], /终局 !ok\(G_VERIFY\)/);
  assert.match(fl.reds[1], /终局 !ok\(status=failed\)/);
});

test("collectRedItems:窗内服务器轮缺 gates=红(P2-1);跨窗旧轮终局入红(P1-3)", () => {
  const reds = collectRedItems({
    server: {
      rounds: [{ round_id: "2026-11-20-0300-health", ok: null, failed_gates: [], exits_triggered: false, findings_n: 0 }],
      overdue_rounds: [
        { round_id: "2026-11-19-1200-health", ok: false, failed_gates: ["G_VERIFY"] },
        { round_id: "2026-11-19-0400-health", ok: null }, // 无信封旧轮 → 注记,不红
        { round_id: "2026-11-19-0300-health", ok: true }, // 绿旧轮静默
      ],
    },
    local: {
      evolve: { rounds: [], overdue_rounds: [{ round_id: "2026-11-19-1915-evolve", ok: false, code: "cards_missing" }] },
      add_rounds: [],
      overdue_add_rounds: [],
    },
  });
  const joined = reds.join("\n");
  assert.match(joined, /2026-11-20-0300-health gates\.json 缺\(窗内龄>1h,无在跑解释\)/); // P2-1
  assert.match(joined, /2026-11-19-1200-health 终局 !ok\(G_VERIFY\)\(跨窗补报\)/); // P1-3 服务器面
  assert.match(joined, /演化轮 2026-11-19-1915-evolve 终局 !ok\(cards_missing\)\(跨窗补报\)/);
  assert.ok(!joined.includes("2026-11-19-0400-health"), "无信封旧轮不红");
  assert.ok(!joined.includes("2026-11-19-0300-health"), "绿旧轮静默");
  assert.equal(reds.length, 3);
});

test("renderDigest:跨窗无信封轮出「终局补报」注记行,不计红(P1-3)", () => {
  const server = greenServer({ overdue_rounds: [{ round_id: "2026-11-19-1200-health", ok: null }] });
  const local = greenLocal({
    evolve: {
      ...greenLocal().evolve,
      overdue_rounds: [{ round_id: "2026-11-19-1915-evolve", ok: false, code: "cards_missing" }],
    },
    overdue_add_rounds: [],
  });
  const reds = collectRedItems({ server, local });
  assert.equal(reds.length, 1); // 只有跨窗终局红
  const { body } = renderDigest({ dateLabel: "2026-11-20", server, local, reds });
  assert.match(body, /- 终局补报:2026-11-19-1200-health 跨窗无信封/);
  assert.match(body, /演化轮 2026-11-19-1915-evolve 终局 !ok\(cards_missing\)\(跨窗补报\)/);
  assert.ok(body.split("\n").length <= 30);
});

// —— #550 节拍两行(月轮心跳龄 + 质量契约上次运行)——

const H = 3_600_000;
const NOW = Date.UTC(2026, 11, 1, 13, 0); // 21:00 CST 固定锚

test("summarizeCadence:心跳新/旧/读不到三态;旧文件标红(写死龄 0 的变异在此红)", () => {
  // 新心跳(2h 前)绿行无红
  const fresh = summarizeCadence({ heartbeatMtimeMs: NOW - 2 * H, nowMs: NOW });
  assert.deepEqual(fresh.lines, ["- 月轮心跳龄 2h", "- ⚠ 质量契约:从没跑过"]);
  assert.equal(fresh.reds.length, 1); // quality 缺省 null = 从没跑过红
  // 旧心跳(>30 天)红——若实现把心跳龄写死成 0,此断言红(变异证据 ②);quality 给新的,
  // 隔离心跳腿的红项
  const stale = summarizeCadence({ heartbeatMtimeMs: NOW - (HEARTBEAT_RED_H + 5) * H, qualityMtimeMs: NOW - H, nowMs: NOW });
  assert.match(stale.lines[0], /⚠ 月轮心跳龄 725h/);
  assert.deepEqual(stale.reds, ["月轮心跳龄 725h 超 30 天"]);
  // 读不到(服务器无文件)红;ssh 整体失败(readError)只注记不双计红
  const missing = summarizeCadence({ heartbeatMtimeMs: null, qualityMtimeMs: NOW - H, nowMs: NOW });
  assert.deepEqual(missing.reds, ["月轮心跳读不到(服务器 eval-heartbeat 缺席)"]);
  const sshFail = summarizeCadence({ heartbeatMtimeMs: null, heartbeatReadError: true, nowMs: NOW });
  assert.equal(sshFail.reds.length, 1); // 只有 quality 腿的红
  assert.match(sshFail.lines[0], /读不到\(服务器读取失败/);
});

test("summarizeCadence:质量契约新文件/旧文件/没有文件/读不到四态(#550)", () => {
  // 新文件(1h 前)绿;心跳也给新的,全绿零红
  const fresh = summarizeCadence({ heartbeatMtimeMs: NOW - H, qualityMtimeMs: NOW - H, nowMs: NOW });
  assert.deepEqual(fresh.lines, ["- 月轮心跳龄 1h", "- 质量契约上次运行 1h 前"]);
  assert.deepEqual(fresh.reds, []);
  // 旧文件(>35 天)红
  const stale = summarizeCadence({ heartbeatMtimeMs: NOW - H, qualityMtimeMs: NOW - (QUALITY_RED_H + 3) * H, nowMs: NOW });
  assert.match(stale.lines[1], /⚠ 质量契约上次运行 843h 前\(超 35 天\)/);
  assert.deepEqual(stale.reds, ["质量契约上次运行 843h 前(超 35 天)"]);
  // 没有文件 = 从没跑过,红(2026-11-28 现状:一份 quality-report 都没有)
  const never = summarizeCadence({ heartbeatMtimeMs: NOW - H, qualityMtimeMs: null, nowMs: NOW });
  assert.match(never.lines[1], /⚠ 质量契约:从没跑过/);
  assert.match(never.reds[0], /从没跑过/);
  // 目录读不了 ≠ 从没跑过,单独显形同样红
  const unread = summarizeCadence({ heartbeatMtimeMs: NOW - H, qualityMtimeMs: null, qualityUnreadable: true, nowMs: NOW });
  assert.match(unread.lines[1], /⚠ 质量契约:读不到/);
  assert.deepEqual(unread.reds, ["质量契约上次运行读不到"]);
});

test("summarizeCadence:时钟步进回跳(mtime 在未来)不涌现负数龄", () => {
  const c = summarizeCadence({ heartbeatMtimeMs: NOW + 10 * H, qualityMtimeMs: NOW, nowMs: NOW });
  assert.match(c.lines[0], /月轮心跳龄 0h/);
});

test("renderDigest/renderDigestPush:cadence 传入时出「节拍」节两行;不传时字节同旧(#550)", () => {
  const server = greenServer();
  const local = greenLocal();
  const reds = collectRedItems({ server, local });
  const noCadence = renderDigest({ dateLabel: "2026-11-20", server, local, reds });
  assert.ok(!noCadence.body.includes("## 节拍"), "不带 cadence 不出节拍节(旧调用面字节不变)");
  const cadence = summarizeCadence({ heartbeatMtimeMs: Date.UTC(2026, 10, 20, 5, 0), qualityMtimeMs: null, nowMs: Date.UTC(2026, 11, 1, 13, 0) });
  const withCadence = renderDigest({ dateLabel: "2026-11-20", server, local, reds, cadence });
  assert.match(withCadence.body, /## 节拍\n- 月轮心跳龄 \d+h\n- ⚠ 质量契约:从没跑过/);
  assert.ok(withCadence.body.split("\n").length <= 30);
  const push = renderDigestPush({ dateLabel: "2026-11-20", server, local, reds: [...reds, ...cadence.reds], cadence });
  assert.match(push.body, /## 节拍/);
  assert.match(push.body, /从没跑过.*变异基线|变异自检\+事故回放从来没有跑过/);
  // 节拍红项走大白话规则(非兜底):两件套齐;补救命令带
  // IP_RADAR_EVAL_ENV=monthly(#550 评审必须改3:不带会落 dev/,红项不会消)
  const plain = plainRedItem(cadence.reds[0], "2026-11-20");
  assert.match(plain, /从来没有跑过/);
  assert.match(plain, /--quality-contract/);
  assert.match(plain, /IP_RADAR_EVAL_ENV=monthly/);
});

// —— #383 lark 推送面大白话版(标题/骨架同技术面;落盘面字节不变由上方既有断言钉)——

test("plainClock:轮 id → 「11-21 凌晨 01:00」时段词;坏形状原样返回", () => {
  assert.equal(plainClock("2026-11-21-0100-add"), "11-21 凌晨 01:00");
  assert.equal(plainClock("2026-11-20-1219-health"), "11-20 中午 12:19");
  assert.equal(plainClock("2026-11-20-1914-evolve"), "11-20 晚上 19:14");
  assert.equal(plainClock("garbage"), "garbage");
});

test("plainRedItem:票面样例口径——fleet G_VERIFY 红项两件套(#383 样例原文)", () => {
  const s = plainRedItem("fleet 2026-11-21-0100-add !ok(status=failed;闸败:G_VERIFY)", "2026-11-21");
  assert.equal(
    s,
    "fleet:11-21 凌晨 01:00 的加源轮失败——没跑完就断在验证门(G_VERIFY)。下一步:多半是本机时钟抖动,重放一次通常就过;同一源连败 2 次会自动跳过并另行告警。",
  );
});

test("plainRedItem:各已知类型两件套齐备;未知类型兜底不编造处置", () => {
  const cases = [
    // [技术红项, 必含片段 ×2(发生了什么 / 下一步)]
    ["2026-11-20-0300-health 信封 !ok(闸败:G_PROBE、G_VERIFY)", /服务器:11-20 凌晨 03:00\(服务器时间\)的健康轮失败/, /等下一轮自动重跑/],
    ["2026-11-20-0300-health gates.json 缺(窗内龄>1h,无在跑解释)", /没留下成绩单/, /第二天同一时间还缺再登服务器/],
    ["2026-11-20-1100-health finding 出口触发(findings=3)", /金标巡检发现 3 个异常\(finding\)/, /三选一处置/],
    ["2026-11-20-1100-health 终局 !ok(G_VERIFY)(跨窗补报)", /昨天还在跑,现在收口了:失败/, /等下一轮自动重跑/],
    ["演化轮 2026-11-19-1915-evolve 终局 !ok(cards_missing)(跨窗补报)", /演化轮.*收口.*考题卡文件缺失/, /不会自愈/],
    ["fleet 2026-11-19-1000-add 终局 !ok(status=failed)(跨窗补报)", /加源轮.*收口.*状态 failed/, /等下一拍自动重试/],    ["拒启触帽留痕(2026-11-20):| 2026-11-20 | health | — | — | budget_monthly refused est=0.05 cap=30 |", /因当月花费到帽被拒启动/, /预算护栏在正常工作/],
    ["影子树增轮:2026-11-20-1219-health(影子 cron 应已停)", /影子目录冒出了新轮/, /登服务器检查影子定时任务/],
    ["演化已熄火(halted;上轮 2026-11-19-1915-evolve)", /循环已自停/, /设计内的自动停机/],
    ["演化轮 2026-11-20-1914-evolve !ok(cards_missing)", /考题卡文件缺失/, /gen-exam-cards\.mjs/],
    ["演化轮 2026-11-20-1914-evolve !ok(brand_new_code)", /失败码 brand_new_code\(brand_new_code\)/, /无现成建议——看 dev\/evolution\/rounds\/2026-11-20-1914-evolve\/report\.md,交代理分诊/],
    ["演化花费 ¥261.86 超月帽 ¥200", /本月花费 ¥261\.86 已超自设月帽/, /EVOLVE_SPEND_CAP_CNY/],
    ["fleet 2026-11-20-1100-add !ok(status=running;闸败:G_DOSSIER)", /交接单门\(G_DOSSIER\)/, /等下一拍自动重试/],
    ["fleet 月帽拒启(2026-11-20-1100-add:spend ¥29.96 + est ¥0.05 > 帽 ¥30)", /本月加源花费到帽被拒启/, /OPS_PIPELINE_MONTHLY_CAP_CNY/],
    ["服务器面读取失败:ssh: connect timed out", /读不到今天的轮数据/, /连续几天失败再人工登服务器/],
    ["窗内轮未读到信封:2026-11-20-0300-health", /没读到它的信封/, /等下一轮/],
  ];
  for (const [red, whatRe, nextRe] of cases) {
    const s = plainRedItem(red, "2026-11-20");
    assert.match(s, whatRe, `${red} → 发生了什么面缺:${s}`);
    assert.match(s, nextRe, `${red} → 下一步面缺:${s}`);
  }
  // 未知形状(未来新增红项类型)→ 兜底:不编造处置,指路落盘附录
  const unknown = plainRedItem("某种崭新的红项 2077", "2026-11-20");
  assert.match(unknown, /无现成建议——看 dev\/ops-digest\/2026-11-20\.md 红项附录与对应轮工件,交代理分诊/);
});

test("renderDigestPush:绿日骨架大白话(术语换中文:issue 0 张→没有新候选源提案);≤30 行;标题同技术面", () => {
  const server = greenServerNoIssues(); // issue 0 张面(缺省夹具带 1 张,单独钉两态)
  const local = greenLocal();
  const reds = collectRedItems({ server, local });
  const { title, body } = renderDigestPush({ dateLabel: "2026-11-20", server, local, reds });
  assert.equal(title, "ip-radar 日报 2026-11-20");
  assert.match(body, /健康轮 2\/2 正常:03:00✓、11:00✓\(服务器时间\)/);
  assert.match(body, /没有新的候选源提案\(issue 0 张\)/); // 定案 3 术语映射(#384 口径)
  const withIssues = renderDigestPush({ dateLabel: "2026-11-20", server: greenServer(), local, reds: [] });
  assert.match(withIssues.body, /1 个候选源提案已开 GitHub 工单等人裁决:gaoyifan_cn_ip/);
  assert.match(body, /影子目录没有新轮,切流干净 ✓/);
  assert.match(body, /演化:还在跑\(连续没赚头 1\/3\),今天 11-20 晚上 19:14 的轮还没收口;本月花费 ¥26\.19\/帽 ¥200/);
  assert.match(body, /自动加源 1\/1 成功:10:00✓;本月加源花费 ¥0\.31\/帽 ¥30/);
  assert.ok(body.split("\n").length <= 30, `行数 ${body.split("\n").length}`);
  assert.ok(!body.includes("## 红项"), "绿日无红项段");
});

test("renderDigestPush:红日红项逐条大白话带下一步;超帽截断仍 ≤30 行;空数据日也有「今天没有轮」", () => {
  const server = greenServer({
    rounds: [
      { round_id: "2026-11-20-0300-health", ok: false, failed_gates: ["G_VERIFY"], exits_triggered: false, findings_n: 0 },
      { round_id: "2026-11-20-1100-health", ok: true, failed_gates: [], exits_triggered: true, findings_n: 2 },
    ],
    shadow_new: ["2026-11-20-1219-health"],
    missed_note: "窗内轮未读到信封:2026-11-20-0300-health",
  });
  const local = greenLocal({
    evolve: {
      ...greenLocal().evolve,
      halted: true,
      rounds: [{ round_id: "2026-11-20-1914-evolve", ok: false, code: "cards_missing" }],
      spend_total_cny: 26.19,
    },
    add_rounds: [
      { round_id: "2026-11-20-1000-add", ok: false, status: "failed", failed_gates: ["G_VERIFY"], monthly_admission: null },
      { round_id: "2026-11-20-1100-add", ok: false, status: "failed", failed_gates: ["G_DOSSIER"], monthly_admission: { ok: false, spend: 29.96, est: 0.05, cap: 30 } },
    ],
  });
  const reds = collectRedItems({ server, local });
  reds.push(server.missed_note);
  assert.ok(reds.length >= 6);
  const { title, body } = renderDigestPush({ dateLabel: "2026-11-20", server, local, reds });
  assert.match(title, /⚠$/);
  assert.match(body, /⚠ fleet:11-20 上午 10:00 的加源轮失败——没跑完就断在验证门\(G_VERIFY\)。下一步:多半是本机时钟抖动/);
  assert.match(body, /影子目录冒出了新轮/);
  assert.match(body, /演化:循环已自停/);
  assert.ok(body.split("\n").length <= 30, `行数 ${body.split("\n").length}`);
  // 空数据日:推送版也保留「今天没有轮」一行(验收:全空也发)
  const emptyServer = { error: null, rounds: [], ledger: { window_cost_cny: 0, month_cost_cny: 0 }, refusals: [], shadow_new: [], missed_note: null };
  const emptyLocal = { evolve: { halted: false, stall_rounds: 0, last_round_id: null, spend_total_cny: null, rounds: [] }, add_rounds: [] };
  const empty = renderDigestPush({ dateLabel: "2026-11-21", server: emptyServer, local: emptyLocal, reds: [] });
  assert.ok(empty.body.includes("今天没有轮跑") && empty.body.includes("自动加源:今天没有轮"));
  // 超帽截断:40 条未知红项 → 截断行指针落盘件
  const many = Array.from({ length: 40 }, (_, i) => `未知红项${i}`);
  const truncated = renderDigestPush({ dateLabel: "2026-11-20", server: greenServer(), local: greenLocal(), reds: many });
  assert.ok(truncated.body.split("\n").length <= 30);
  assert.match(truncated.body, /另 \d+ 条见 dev\/ops-digest\/2026-11-20\.md/);
});

// —— P2-3 push 退出码 ——

test("pushExitCode:failed/channel_missing=1(失败显形);posted/skip=0(P2-3)", () => {
  assert.equal(pushExitCode("failed"), 1);
  assert.equal(pushExitCode("channel_missing"), 1);
  assert.equal(pushExitCode("posted"), 0);
  assert.equal(pushExitCode("skip"), 0); // 静音律:env 未配置不算失败
});

// —— apprise 旗标面(装机目标 apprise v2.2.0 无 --body-file,2026-11-20 实测订正)——

test("pushLark:argv 形状=--body 直传且不含 --body-file;env 缺省=skip 不调 apprise", async () => {
  const calls = [];
  const stub = async (cmd, args) => {
    calls.push([cmd, args]);
    return { ok: true, stdout: "", stderr: "", error: null };
  };
  process.env.IP_RADAR_ALERT_URLS = "lark://fixture-token";
  try {
    const posted = await pushLark("标题", "正文⚠多行", () => {}, stub);
    assert.equal(posted.status, "posted");
    assert.equal(calls.length, 1);
    const args = calls[0][1];
    assert.ok(args.includes("--body"), "须含 --body(v2.2.0 兼容)");
    assert.ok(!args.includes("--body-file"), "禁用 --body-file(装机目标 apprise v2.2.0 无此旗标)");
    assert.ok(args.includes("--title") && args.includes("标题") && args.includes("正文⚠多行"));
    assert.ok(args.includes("lark://fixture-token"));
    delete process.env.IP_RADAR_ALERT_URLS;
    const skipped = await pushLark("t", "b", () => {}, stub);
    assert.equal(skipped.status, "skip"); // 静音律
    assert.equal(calls.length, 1); // 未再碰 apprise
  } finally {
    delete process.env.IP_RADAR_ALERT_URLS;
  }
});
