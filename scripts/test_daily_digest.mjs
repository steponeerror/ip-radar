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
  parseQueueProposeRows,
  selectProposeRows,
  shadowNewRounds,
  summarizeEvolveRound,
  summarizeAddRound,
  collectRedItems,
  renderDigest,
  pushExitCode,
  pushLark,
  splitScanBands,
  overdueRoundLines,
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

// —— queue PROPOSE 行 ——

const QUEUE = [
  "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |",
  "|---|---|---|---|---|---|---|",
  "| 2026-11-18 | needs-x | PROPOSE | gaoyifan_cn_ip | — | candidate:name=… | 是 |",
  "| 2026-10-19 | discover | REJECT | threatview_c2 | sunset_frozen | call… | 是 |",
].join("\n");

test("parseQueueProposeRows:只取 action=PROPOSE;selectProposeRows 按窗日期", () => {
  const rows = parseQueueProposeRows(QUEUE);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].source, "gaoyifan_cn_ip");
  assert.equal(selectProposeRows(rows, ["2026-11-20", "2026-11-19"]).length, 0);
  assert.equal(selectProposeRows(rows, ["2026-11-20", "2026-11-18"]).length, 1);
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
  ],
  ledger: { window_cost_cny: 0.0032, month_cost_cny: 0.0049 },
  refusals: [],
  propose_rows: [{ date: "2026-11-19", source: "gaoyifan_cn_ip" }],
  shadow_new: [],
  missed_note: null,
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
  assert.match(body, /PROPOSE 1 行:gaoyifan_cn_ip/);
  assert.match(body, /影子树零增轮/);
  assert.match(body, /演化:未熄火\(stall=1\),当日轮 1914\(无信封,未收口\);花费 ¥26\.19\/¥200/);
  assert.match(body, /fleet add 1\/1 绿:1000✓;月帽 ¥0\.31\/¥30/);
  assert.ok(body.split("\n").length <= 30, `行数 ${body.split("\n").length}`);
});

test("renderDigest:空数据日=「当日无轮」且不发红", () => {
  const emptyServer = { error: null, rounds: [], ledger: { window_cost_cny: 0, month_cost_cny: 0 }, refusals: [], propose_rows: [], shadow_new: [], missed_note: null };
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
