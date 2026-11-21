#!/usr/bin/env node
// daily-digest.mjs — 每日 lark 日报(#368;2026-11-20 用户裁 Q4=每天 21:00 一份摘要,
// Q6=免正式观察期、日报即观察——连续 14 天全绿→旧管线退役 PR,2026-12-04 核)。
// 零依赖(node 内建 + ssh 免密),汇总两面当日信号:
//   服务器面(ssh root@203.88.124.85 → docker exec ip-lookup-tool-ipradar-1):
//     /app/data/ops/rounds/ 当日健康轮+发现轮信封(gates.json 全 records pass=ok;
//     08-anchor-sweep-exits.json findings/triggered)、ledger.md 当日 cost 行与
//     budget_monthly 拒跑留痕行、queue.md 当日 PROPOSE 行、/app/data/ops-shadow
//     零增轮断言(切流后影子 cron 已停,增轮=回退不彻底,SHADOW-RUNBOOK §已切流)。
//   本机面(主检出):dev/evolution/state.json(halted/stall)+当日轮 envelope.json、
//     dev/evolution/spend.json 对月帽(缺省 ¥200,env EVOLVE_SPEND_CAP_CNY 同键)、
//     docs/ops/rounds/*-add/ 当日 fleet 轮(state.json status+gates.json+monthly_admission)。
// 红项(标题 ⚠;票面:任一信封 !ok / findings>0 / halted / 拒启触帽):另计影子增轮、
//   服务器读取失败(失败可见优于静默空面——无证据≠清白)。
// 窗口口径:滚动 24h(跑时 now-24h < 轮起 ≤ now)。轮 id 钟面:服务器=UTC
//   (宿主 04/12/20 本地=容器 03/11/19 UTC);本机演化/fleet=CST(+08:00)。21:00 CST 跑
//   时 24h 窗恰好覆盖本 CST 日全部自动轮:健康 03xx/11xx UTC(11/19 时 CST)、发现轮
//   前日 22:00 UTC(06:00 CST)、本机当日轮。台账/queue 行无钟面只有日期列,按窗跨到的
//   两个 UTC 日期取(粒度差 ≤24h,日报观察面可容;对账面仍以台账细胞为准,ENVELOPE.md)。
//   终局补报带(#368 评审 P1-3):扫描放宽 48h——21:00 前起跑、窗后收口的轮,其终局
//   按轮 id 钟面任何常规 24h 窗都读不到(窗按起跑钟面过滤);旧带(24h<龄≤48h)轮仅当
//   ok:false(红)或无信封(注记行;在跑/未收口不猜红)时补报终局,ok:true 静默(绿不入补报)。
// 落盘:dev/ops-digest/<YYYY-MM-DD>.md(不 commit,放置规范 dev/ 律;证据永不灭失)。
//   三面(#383 大白话化):落盘版=技术面全量(push 摘要+全量红项附录,字节不变——证据面
//   不漂移);lark 推送版=renderDigestPush 大白话(≤30 行,单行可变长;红项带「发生了什么+
//   下一步怎么办」两件套,处置方向来自 RED_ADVICE 对照表,不含具体命令)。
// 推送:--push 时 apprise --title --body(execFile 参数数组直传,无 shell 免转义;
//   装机目标 apprise v2.2.0 无 --body-file 旗标,2026-11-20 实测订正)读 env IP_RADAR_ALERT_URLS
//   (逗号/空白分隔多 URL;未配置=静音跳过——evolution exits.mjs pushAnomalyLark 同律)。
// 用法:node scripts/daily-digest.mjs [--dry-run] [--push] [--root <repo根>]
//   缺省=dry-run(汇总+落盘+stdout,不推送);--dry-run 显式同义;--push 才真发。
//   --root 缺省=脚本上溯仓根(生产 timer 在主检出跑;worktree 冒烟用 --root 指主检出)。
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFile as execFileCb } from "node:child_process";
import { fileURLToPath } from "node:url";

const execFileP = (cmd, args, opts) =>
  new Promise((resolve) => {
    execFileCb(cmd, args, opts, (error, stdout, stderr) =>
      resolve({ ok: !error, stdout: String(stdout ?? ""), stderr: String(stderr ?? ""), error }));
  });

// —— 常量(生产面;env 可换腿=测试/迁移面)——
const SSH_HOST = process.env.DIGEST_SSH_HOST || "root@203.88.124.85";
const SSH_CONTAINER = process.env.DIGEST_SSH_CONTAINER || "ip-lookup-tool-ipradar-1";
const OPS_ROUNDS = "/app/data/ops/rounds";
const OPS_LEDGER = "/app/data/ops/ledger.md";
const OPS_QUEUE = "/app/data/ops/queue.md";
const SHADOW_ROUNDS = "/app/data/ops-shadow/docs/ops/rounds";
// 切流后影子树最后合法轮(#364 切流 2026-11-20 晚,末影子轮 1140 早于切流点;
// 此后任何字典序更大的影子轮=影子 cron 复活,SHADOW-RUNBOOK §已切流「影子残件」清单)。
const SHADOW_CUTOFF_ROUND = "2026-11-20-1140-health";
const CST_OFFSET_MIN = 480; // 本机轮 id 钟面=CST;UTC = id 钟面 -8h
const WINDOW_MS = 24 * 3600 * 1000;
const SCAN_MS = 48 * 3600 * 1000; // 终局补报带扫描窗(P1-3);分带见 splitScanBands
const EVOLVE_CAP_CNY = Number(process.env.EVOLVE_SPEND_CAP_CNY || 200);
const MAX_LINES = 30; // 票面:markdown ≤30 行

// —— 纯函数面(scripts/test_daily_digest.mjs 钉)——

// 轮 id `YYYY-MM-DD-HHMM-<kind>` → epoch ms;utcOffsetMin=id 钟面对 UTC 的偏移量
// (服务器轮 0;本机轮 CST=480 → UTC=id 钟面 -8h)。形状不匹配 → null(不猜,无证据即无话)。
export function roundIdMs(roundId, utcOffsetMin = 0) {
  const m = /^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})-/.exec(String(roundId || ""));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) - utcOffsetMin * 60_000;
}

export function inWindow(roundId, nowMs, { utcOffsetMin = 0, windowMs = WINDOW_MS } = {}) {
  const t = roundIdMs(roundId, utcOffsetMin);
  return t !== null && nowMs - windowMs < t && t <= nowMs;
}

// 48h 扫描带分带(P1-3):窗内(龄≤24h)轮正常入日报;旧带(24h<龄≤48h)轮只走
// 终局补报(overdueRoundLines);>48h/未来轮/坏形状丢弃(坏形状不猜,无证据即无话)。
export function splitScanBands(roundIds, nowMs, { utcOffsetMin = 0, windowMs = WINDOW_MS, scanMs = SCAN_MS } = {}) {
  const window = [];
  const overdue = [];
  for (const id of roundIds ?? []) {
    const t = roundIdMs(id, utcOffsetMin);
    if (t === null || t > nowMs || t <= nowMs - scanMs) continue;
    (t > nowMs - windowMs ? window : overdue).push(id);
  }
  return { window, overdue };
}

// 服务器轮信封:gates.json(全 records pass=ok)+ 08-anchor-sweep-exits.json(finding 出口)。
// 缺 gates=无信封面 → ok:null(不猜红也不猜绿,无证据即无话)。
export function summarizeServerRound(roundId, gates, exits) {
  const failed = Array.isArray(gates?.records)
    ? gates.records.filter((r) => r && r.pass === false).map((r) => r.name || r.stage || "?")
    : null;
  return {
    round_id: roundId,
    ok: failed === null ? null : failed.length === 0,
    failed_gates: failed ?? [],
    exits_triggered: exits ? Boolean(exits.triggered) : false,
    findings_n: exits ? Number(exits.findings_n ?? 0) : 0,
  };
}

// 台账行解析:`| 日期 | 轮型 | model | 用量(…cost=x) | 备注(pipeline:<round_id>) |`
// memory_peak 行无 cost/round_id → 两字段 null(只作行存在,不计花费)。
export function parseLedgerRows(text) {
  return String(text || "")
    .split("\n")
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.split("|").map((c) => c.trim()))
    // 数据行判定=日期列形状(表头/分隔行无日期形状,滤掉不猜)
    .filter((cells) => /^\d{4}-\d{2}-\d{2}$/.test(cells[1] || ""))
    .map((cells) => {
      const joined = cells.join("|");
      const cost = /cost=([0-9.]+)/.exec(joined);
      const rid = /pipeline:([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-(?:health|discover))\|/.exec(
        `${joined}|`,
      );
      return {
        date: cells[1] || "",
        kind: cells[2] || "",
        cost_cny: cost ? Number(cost[1]) : null,
        round_id: rid ? rid[1] : null,
        refused: joined.includes("budget_monthly refused"),
        raw: cells.join("|"),
      };
    });
}

// 台账读数:窗内(按 round_id ∈ 窗内轮集;台账行自带轮 id 细胞,不靠日期列猜)+
// 当月(cost 行按日期列月份合计,monthSpendOfLedgerText 同口径消费面)。
// 拒跑留痕行无 round_id,按日期列 ∈ 窗跨到的 UTC 日期计(文件头已声明粒度差)。
export function ledgerReadings(rows, { windowRoundIds, windowDates, month }) {
  const inWin = rows.filter((r) => r.round_id && windowRoundIds.has(r.round_id));
  const monthRows = rows.filter((r) => r.cost_cny !== null && r.date.startsWith(month));
  return {
    window_cost_cny: inWin.reduce((s, r) => s + (r.cost_cny ?? 0), 0),
    window_rows_n: inWin.length,
    month_cost_cny: monthRows.reduce((s, r) => s + r.cost_cny, 0),
    month_counted: monthRows.length,
    refusals: rows.filter((r) => r.refused && windowDates.includes(r.date)),
  };
}

// queue.md PROPOSE 行:`| 日期 | 轮次 | action | source | … |`
export function parseQueueProposeRows(text) {
  return String(text || "")
    .split("\n")
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.split("|").map((c) => c.trim()))
    .filter((cells) => cells.length >= 4 && cells[3] === "PROPOSE")
    .map((cells) => ({ date: cells[1] || "", source: cells[4] || "" }));
}

export function selectProposeRows(rows, dates) {
  return rows.filter((r) => dates.includes(r.date));
}

// 影子零增轮断言:id > cutoff(同形定宽 id,字典序=时间序)。
export function shadowNewRounds(shadowRoundIds, cutoff = SHADOW_CUTOFF_ROUND) {
  return shadowRoundIds.filter((id) => id > cutoff);
}

// 演化轮:run-round 收口才写 envelope.json;在跑轮无信封(或无 ok 键)→ ok:null
// (未收口不算红;调用方可用无 ok 键的占位对象携带 round_id——「有信封」看 ok 键存在,
// 不看对象 truthy,防在跑轮误判 !ok)。
export function summarizeEvolveRound(envelope) {
  const has = envelope != null && typeof envelope === "object" && "ok" in envelope;
  return {
    round_id: envelope?.round_id ?? null,
    ok: has ? Boolean(envelope.ok) : null,
    code: envelope?.error?.code ?? null,
  };
}

// fleet add 轮:state.json status + gates.json。ok = 非 failed 且 gates 全过;gates 缺
// → ok:null。running 态如实报,不算红(在跑/跨窗轮由 48h 终局补报带收口,P1-3)。
export function summarizeAddRound(roundId, state, gates) {
  const failed = Array.isArray(gates?.records)
    ? gates.records.filter((r) => r && r.pass === false).map((r) => r.name || r.stage || "?")
    : null;
  const status = state?.status ?? null;
  const ok = failed === null ? null : failed.length === 0 && status !== "failed";
  return {
    round_id: roundId,
    ok,
    status,
    failed_gates: failed ?? [],
    monthly_admission: state?.monthly_admission ?? null,
  };
}

// 跨窗旧轮(24h<龄≤48h,splitScanBands 旧带)终局补报(P1-3):昨窗在跑、窗后
// 收口的轮,终局信封任何常规 24h 窗都读不到。ok:false=红(确定性失败,截窗不灭失);
// 无信封/缺 gates=注记行(在跑或未收口,无证据≠清白但不猜红);ok:true=静默(绿不入
// 补报,行数帽留给红面)。face=红项前缀(服务器=""/演化轮/fleet,同 collectRedItems 律)。
export function overdueRoundLines(face, rounds) {
  const reds = [];
  const notes = [];
  for (const r of rounds ?? []) {
    const why =
      r.code ??
      (r.failed_gates?.length ? r.failed_gates.join("、") : null) ??
      (r.status ? `status=${r.status}` : null) ??
      "?";
    if (r.ok === false) reds.push(`${face ? `${face} ` : ""}${r.round_id} 终局 !ok(${why})(跨窗补报)`);
    else if (r.ok === null) notes.push(`${face ? `${face} ` : ""}${r.round_id} 跨窗无信封(在跑或未收口,不判红)`);
  }
  return { reds, notes };
}

// 红项判定(票面四类 + 影子增轮 + 读取失败 + 跨窗终局;每条自带轮 id 定位,人裁入口)。
export function collectRedItems({ server, local }) {
  const reds = [];
  if (server.error) reds.push(`服务器面读取失败:${server.error}`);
  for (const r of server.rounds ?? []) {
    if (r.ok === false) reds.push(`${r.round_id} 信封 !ok(闸败:${r.failed_gates.join("、") || "?"})`);
    // P2-1:窗内轮缺 gates.json=红——cron 轮墙钟帽≤35min,21:00 时窗内轮龄>1h,
    // 无「在跑」解释;流产轮不允静默("?" 面已够,红项才入 ⚠ 计数)。
    else if (r.ok === null) reds.push(`${r.round_id} gates.json 缺(窗内龄>1h,无在跑解释)`);
    if (r.exits_triggered || r.findings_n > 0)
      reds.push(`${r.round_id} finding 出口触发(findings=${r.findings_n})`);
  }
  // P1-3:旧带终局红(注记行走 renderDigest,不计数)
  reds.push(...overdueRoundLines("", server.overdue_rounds).reds);
  reds.push(...overdueRoundLines("演化轮", local.evolve?.overdue_rounds).reds);
  reds.push(...overdueRoundLines("fleet", local.overdue_add_rounds).reds);
  for (const r of server.refusals ?? [])
    reds.push(`拒启触帽留痕(${r.date}):${r.raw.slice(0, 80)}`);
  for (const id of server.shadow_new ?? []) reds.push(`影子树增轮:${id}(影子 cron 应已停)`);
  const ev = local.evolve ?? {};
  if (ev.halted) reds.push(`演化已熄火(halted;上轮 ${ev.last_round_id ?? "?"})`);
  for (const r of ev.rounds ?? [])
    if (r.ok === false) reds.push(`演化轮 ${r.round_id} !ok(${r.code ?? "?"})`);
  if (typeof ev.spend_total_cny === "number" && ev.spend_total_cny > EVOLVE_CAP_CNY)
    reds.push(`演化花费 ¥${ev.spend_total_cny.toFixed(2)} 超月帽 ¥${EVOLVE_CAP_CNY}`);
  for (const r of local.add_rounds ?? []) {
    if (r.ok === false)
      reds.push(`fleet ${r.round_id} !ok(status=${r.status ?? "?"};闸败:${r.failed_gates.join("、") || "?"})`);
    if (r.monthly_admission && r.monthly_admission.ok === false)
      reds.push(
        `fleet 月帽拒启(${r.round_id}:spend ¥${r.monthly_admission.spend} + est ¥${r.monthly_admission.est} > 帽 ¥${r.monthly_admission.cap})`,
      );
  }
  return reds;
}

const fmtCny = (n) => `¥${Number(n).toFixed(2)}`;
const shortId = (id) => String(id).replace(/^\d{4}-\d{2}-\d{2}-(\d{4})-.*$/, "$1");
const mark = (r) => (r.ok === true ? "✓" : r.ok === false ? "✗" : "?");

// 渲染:markdown ≤30 行(票面);无轮日=「当日无轮」一行(验收:全空也发一行)。
// 红项列表超帽时截断,余量指落盘件(证据永不灭失,推送面保行数帽)。
export function renderDigest({ dateLabel, server, local, reds }) {
  const lines = [];
  lines.push(`# ip-radar 日报 ${dateLabel}${reds.length ? ` ⚠(${reds.length} 红项)` : ""}`);
  lines.push("");
  lines.push("## 服务器(健康+发现,24h 窗)");
  if (server.error) lines.push(`- ⚠ 读取失败:${server.error}`);
  const health = (server.rounds ?? []).filter((r) => r.round_id.endsWith("-health"));
  const discover = (server.rounds ?? []).filter((r) => r.round_id.endsWith("-discover"));
  if (!health.length && !discover.length && !server.error) lines.push("- 当日无轮");
  if (health.length)
    lines.push(`- 健康 ${health.filter((r) => r.ok === true).length}/${health.length} 绿:${health.map((r) => shortId(r.round_id) + mark(r)).join(" ")}`);
  if (discover.length)
    lines.push(`- 发现 ${discover.filter((r) => r.ok === true).length}/${discover.length} 绿:${discover.map((r) => shortId(r.round_id) + mark(r)).join(" ")}`);
  const propose = server.propose_rows ?? [];
  lines.push(propose.length ? `- PROPOSE ${propose.length} 行:${propose.map((p) => p.source).join("、")}` : "- PROPOSE 0 行");
  lines.push(
    `- cost(窗)${fmtCny(server.ledger?.window_cost_cny ?? 0)};当月 ${fmtCny(server.ledger?.month_cost_cny ?? 0)}${server.refusals?.length ? `;⚠ 拒启 ×${server.refusals.length}` : ""}`,
  );
  lines.push((server.shadow_new ?? []).length ? `- ⚠ 影子树增轮:${server.shadow_new.join("、")}` : "- 影子树零增轮 ✓");
  if (server.missed_note) lines.push(`- ⚠ ${server.missed_note}`);
  const srvOd = overdueRoundLines("", server.overdue_rounds).notes;
  if (srvOd.length) lines.push(`- 终局补报:${srvOd.join("、")}`);
  lines.push("");
  lines.push("## 本机(演化+fleet)");
  const ev = local.evolve ?? {};
  const evRounds = ev.rounds ?? [];
  const r0 = evRounds[0];
  lines.push(
    `- 演化:${ev.halted ? "⚠ halted" : `未熄火(stall=${ev.stall_rounds ?? 0})`}` +
      `${r0 ? `,当日轮 ${shortId(r0.round_id)}${r0.ok === true ? "✓" : r0.ok === false ? `✗(${r0.code})` : "(无信封,未收口)"}` : ",当日无轮"}` +
      (typeof ev.spend_total_cny === "number" ? `;花费 ${fmtCny(ev.spend_total_cny)}/${fmtCny(EVOLVE_CAP_CNY)}` : ""),
  );
  const adds = local.add_rounds ?? [];
  if (!adds.length) lines.push("- fleet add 当日无轮");
  else {
    const adm = adds.find((r) => r.monthly_admission)?.monthly_admission;
    lines.push(
      `- fleet add ${adds.filter((r) => r.ok === true).length}/${adds.length} 绿:` +
        adds.map((r) => `${shortId(r.round_id)}${r.ok === true ? "✓" : r.ok === false ? `✗(${r.failed_gates[0] ?? r.status})` : "?"}`).join(" ") +
        (adm ? `;月帽 ${fmtCny(adm.spend)}/${fmtCny(adm.cap)}` : ""),
    );
  }
  const localOd = [
    ...overdueRoundLines("演化轮", local.evolve?.overdue_rounds).notes,
    ...overdueRoundLines("fleet", local.overdue_add_rounds).notes,
  ];
  if (localOd.length) lines.push(`- 终局补报:${localOd.join("、")}`);
  if (reds.length) {
    lines.push("");
    lines.push("## 红项");
    const shown = reds.slice(0, MAX_LINES - lines.length - 2);
    for (const r of shown) lines.push(`- ⚠ ${r}`);
    if (reds.length > shown.length)
      lines.push(`- …另 ${reds.length - shown.length} 条见 dev/ops-digest/${dateLabel}.md`);
  }
  const body = lines.join("\n");
  // 技术摘要面+落盘全量面(P1-2 双渲染;#383 后 lark 推送另走 renderDigestPush,本函数面不变):
  // 落盘版追加全量红项附录——摘要截断的余量只在档上,不灭失。
  const fileBody = reds.length
    ? `${body}\n\n## 红项附录(全量 ${reds.length} 条;push 版仅截断列表)\n\n${reds.map((r) => `- ⚠ ${r}`).join("\n")}`
    : body;
  return { title: `ip-radar 日报 ${dateLabel}${reds.length ? " ⚠" : ""}`, body, fileBody };
}

// ── #383 lark 推送面大白话渲染(定案 2 双面律:本区段只新增,renderDigest/fileBody 字节不变)──
// 每条红项两件套:发生了什么(大白话重述)+ 下一步怎么办(方向级处置,不含具体命令,
// 用户裁定 Q9)。红项归类按 collectRedItems 的技术字符串正则匹配——新增红项形状未归类时
// 走兜底话术(老实说无现成建议并指路,不编造处置,定案 6)。

// 轮 id `YYYY-MM-DD-HHMM-<kind>` → 「11-21 凌晨 01:00」(钟面=轮 id 自带钟:服务器轮=UTC
// 由调用方标注「服务器时间」,本机轮=CST——不在此换算,保持与轮 id/工件可对回)。
export function plainClock(roundId) {
  const m = /^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})-/.exec(String(roundId || ""));
  if (!m) return String(roundId || "?");
  const hh = +m[4];
  const tod = hh < 5 ? "凌晨" : hh < 8 ? "早上" : hh < 11 ? "上午" : hh < 13 ? "中午" : hh < 17 ? "下午" : hh < 19 ? "傍晚" : "晚上";
  return `${m[2]}-${m[3]} ${tod} ${m[4]}:${m[5]}`;
}

// 闸名 → 中文(定案 3:中文说清,代号括号留——G_* 是回查工单的检索键)
const PLAIN_GATE = Object.freeze({
  G_VERIFY: "验证门", G_DOSSIER: "交接单门", G_IMPLEMENT: "实现门",
  G_GATE: "终门", G_REPORT: "报告门", G_CLOSE: "收口门", G_ANCHOR_SWEEP: "金标巡检门",
});
const plainGate = (g) => `${PLAIN_GATE[g] ?? "关卡"}(${g})`;
const plainKind = (id) => (id.endsWith("-health") ? "健康轮" : id.endsWith("-discover") ? "发现轮" : id.endsWith("-evolve") ? "演化轮" : id.endsWith("-add") ? "加源轮" : "轮");

// 「失败类型→建议动作」对照表(定案 6:每条带票号出处;只给方向,不写具体命令)。
export const RED_ADVICE = Object.freeze({
  serverGate: "等下一轮自动重跑;同一道门连续两天红再人工查,单次偶发不用动", // #368 日报观察面;服务器 cron 每日自动重跑
  serverNoGates: "等下一轮自动重跑;第二天同一时间还缺再登服务器看容器日志", // #368 P2-1:窗内龄>1h 缺 gates=流产轮不允静默
  findingExit: "巡检异常已自动开 GitHub 工单并另推一条告警,按那条告警的三选一处置即可,日报里不用重复动作", // #184 出口只写不动作
  budgetRefused: "不用动,这是预算护栏在正常工作;要继续跑须人裁抬月帽,或等下月自动恢复", // #356/#366 拒启双面:留痕未起跑零花费
  shadowNew: "需要人工处理:登服务器检查影子定时任务有没有清干净(切流清单见 SHADOW-RUNBOOK),不清会一直误报", // #364 切流:影子 cron 应已停,增轮=回退不彻底
  evolveHalted: "这是设计内的自动停机,不用动;要不要重启演化由人裁(重启须人面改 dev/evolution/state.json),不重启只是不再自动试新方案", // #356:连续 3 轮带内零增益自停
  evolveOverCap: "后续演化轮会被拒启(拒启会留痕);要继续跑须人裁抬帽(env EVOLVE_SPEND_CAP_CNY)或等下月", // #356 月帽拒启面
  fleetVerifyClock: "多半是本机时钟抖动,重放一次通常就过;同一源连败 2 次会自动跳过并另行告警", // #377 时钟步进判例(验证门偶发红=时钟族 flake,重试即过)+ #366 连败 2 跳过
  fleetGate: "等下一拍自动重试;同一源连败 2 次会自动跳过并另行告警,那时再人工复盘", // #366:失败不重试同轮,下一拍另起
  fleetMonthly: "不用动,预算护栏正常工作;想继续跑由人裁抬帽(env OPS_PIPELINE_MONTHLY_CAP_CNY)或等下月", // #366:月帽拒启未起跑不计失败
  sshFail: "偶发网络问题等明天自动恢复;连续几天失败再人工登服务器排查 ssh 和容器", // #368:失败可见优于静默空面
  missedNote: "等下一轮;连续出现再人工查服务器轮目录", // #368 两日 glob 兜底注记
});

// 演化失败码 → (发生了什么 / 下一步)(#356 骨架错误面;未知码走 unknown 兜底不缩造)
export const EVOLVE_CODE_PLAIN = Object.freeze({
  cards_missing: ["考题卡文件缺失,轮没法考试", "这是配置面问题不会自愈:按轮报告核对考题卡目录(env EVOLVE_CARDS_DIR;生成入口 gen-exam-cards.mjs),交人工或代理处理"], // #356
  guardrail_red: ["提案改动碰到了受保护文件,被护栏拦下、候选作废", "护栏正常工作,下一轮会自动再试;连续多轮都这样再交代理分诊"], // #356 保护名单闸
  model_face: ["提案者 AI 会话没正常收尾,轮失败收口", "偶发面,下一轮自动重试;同一失败码连续出现再人工查模型配置"], // #356
  judge_insufficient: ["考试成对数据不足,判不出输赢,轮按失败收口(不计熄火)", "多为考试偶发崩溃,下一轮自动重试;连续出现再人工查"], // #356 判定面
  trial_spend_cap: ["考试花费到了单轮帽,停批收口", "预算护栏正常工作,已跑部分已入账;下一轮/下月自动恢复"], // #356+#337 花费帽
  orphan_reconciled: ["上次运行被击杀或崩溃,这轮启动时已自动补账收口", "对账已自动完成,不用动;这台机器频繁非正常停机才值得查原因"], // #356 启动对账 P2-4②
  orphan_pre_flush: ["上次运行崩得太早,断点文件没写下来,花费追不回(按零费留痕收口)", "已自动收口留档,不用动;频繁出现再查运行环境的超时帽/内存"], // #356 pre-flush 孤儿 P2-②
  bad_round: ["轮次编号形状不对,轮没起跑", "调度参数面问题,人工核对定时器/脚本传入的轮 id"], // #356/#366 形状律
});

// 跨窗终局补报的 why(code/闸名/status)分流在 RED_PLAIN_RULES 的跨窗规则内联(按 face 取表)

// 红项技术字符串 → 大白话两件套(规则序=先具体后宽泛;未命中走兜底)
const RED_PLAIN_RULES = [
  [/^fleet 月帽拒启\((\S+):spend ¥([\d.]+) \+ est ¥([\d.]+) > 帽 ¥([\d.]+)\)$/,
    (m) => `fleet:${plainClock(m[1])} 想给源跑加源轮,但本月加源花费到帽被拒启(已花 ¥${m[2]}+这轮预估 ¥${m[3]}>月帽 ¥${m[4]},未起跑零花费)。下一步:${RED_ADVICE.fleetMonthly}。`],
  [/^fleet (\S+) !ok\(status=(\S+);闸败:(.*)\)$/,
    (m) => {
      const gates = m[3].split("、");
      if (gates.includes("G_VERIFY"))
        return `fleet:${plainClock(m[1])} 的加源轮失败——没跑完就断在验证门(G_VERIFY)。下一步:${RED_ADVICE.fleetVerifyClock}。`;
      return `fleet:${plainClock(m[1])} 的加源轮失败(状态 ${m[2]})——没过 ${gates.map(plainGate).join("、")}。下一步:${RED_ADVICE.fleetGate}。`;
    }],
  [/^(演化轮|fleet|) ?(\S+) 终局 !ok\((.+?)\)\(跨窗补报\)$/,
    (m) => {
      const face = m[1] || "服务器";
      const clock = `${plainClock(m[2])}${m[1] ? "" : "(服务器时间)"}的${plainKind(m[2])}`;
      if (m[1] === "fleet")
        return `fleet:${plainClock(m[2])}的加源轮 昨天还在跑,现在收口了:失败,${/^G_/.test(m[3]) ? `没过 ${plainGate(m[3])}` : `状态 ${m[3].replace(/^status=/, "")}`}(跨窗补报)。下一步:${m[3] === "G_VERIFY" ? RED_ADVICE.fleetVerifyClock : RED_ADVICE.fleetGate}。`;
      if (m[1] === "演化轮") {
        const known = EVOLVE_CODE_PLAIN[m[3]];
        return `演化:${plainClock(m[2])}的演化轮 昨天还在跑,现在收口了:失败——${known ? known[0] : `失败码 ${m[3]}`}(${m[3]})(跨窗补报)。下一步:${known ? known[1] : `无现成建议——看 dev/evolution/rounds/${m[2]}/report.md,交代理分诊`}。`;
      }
      return `服务器:${clock} 昨天还在跑,现在收口了:失败,${/^G_/.test(m[3]) ? `没过 ${plainGate(m[3])}` : `原因 ${m[3]}`}(跨窗补报)。下一步:${RED_ADVICE.serverGate}。`;
    }],
  [/^演化轮 (\S+) !ok\((\S+)\)$/,
    (m) => {
      const known = EVOLVE_CODE_PLAIN[m[2]];
      return `演化:${plainClock(m[1])} 的演化轮失败——${known ? known[0] : `失败码 ${m[2]}`}(${m[2]})。下一步:${known ? known[1] : `无现成建议——看 dev/evolution/rounds/${m[1]}/report.md,交代理分诊`}。`;
    }],
  [/^演化已熄火\(halted;上轮 (\S+)\)$/,
    (m) => `演化:循环已自停(连续 3 轮没赚头,halted;上轮 ${m[1]})。下一步:${RED_ADVICE.evolveHalted}。`],
  [/^演化花费 ¥([\d.]+) 超月帽 ¥([\d.]+)$/,
    (m) => `演化:本月花费 ¥${m[1]} 已超自设月帽 ¥${m[2]}。下一步:${RED_ADVICE.evolveOverCap}。`],
  [/^拒启触帽留痕\((\d{4}-\d{2}-\d{2})\):(.*)$/,
    (m) => `服务器:${m[1]} 的轮因当月花费到帽被拒启动(拒启留痕,未花钱)。下一步:${RED_ADVICE.budgetRefused}。`],
  [/^影子树增轮:(\S+)(\(影子 cron 应已停\))?$/,
    (m) => `服务器:影子目录冒出了新轮 ${m[1]}——切流后影子定时任务应该已停,增轮=还有东西在跑。下一步:${RED_ADVICE.shadowNew}。`],
  [/^(\S+) finding 出口触发\(findings=(\d+)\)$/,
    (m) => `服务器:${plainClock(m[1])}(服务器时间)的${plainKind(m[1])}里,金标巡检发现 ${m[2]} 个异常(finding)——有 IP 的查询结果和标准答案对不上。下一步:${RED_ADVICE.findingExit}。`],
  [/^(\S+) gates\.json 缺\(窗内龄>1h,无在跑解释\)$/,
    (m) => `服务器:${plainClock(m[1])}(服务器时间)的${plainKind(m[1])}跑了但没留下成绩单(gates.json 缺)——多半中途崩了。下一步:${RED_ADVICE.serverNoGates}。`],
  [/^(\S+) 信封 !ok\(闸败:(.*)\)$/,
    (m) => `服务器:${plainClock(m[1])}(服务器时间)的${plainKind(m[1])}失败——没过 ${m[2].split("、").map(plainGate).join("、")}。下一步:${RED_ADVICE.serverGate}。`],
  [/^服务器面读取失败:(.*)$/,
    (m) => `服务器:日报连不上服务器,读不到今天的轮数据(${m[1]})——读不到不等于一切正常。下一步:${RED_ADVICE.sshFail}。`],
  [/^窗内轮未读到信封:(.*)$/,
    (m) => `服务器:窗内有轮但没读到它的信封(${m[1]})。下一步:${RED_ADVICE.missedNote}。`],
];

// 单条红项 → 大白话(未命中规则=未知失败类型,兜底指路不编造)
export function plainRedItem(red, dateLabel) {
  for (const [re, fn] of RED_PLAIN_RULES) {
    const m = re.exec(String(red));
    if (m) return fn(m);
  }
  return `${red}。下一步:无现成建议——看 dev/ops-digest/${dateLabel}.md 红项附录与对应轮工件,交代理分诊。`;
}

// lark 推送版渲染(#383:标题/三段骨架同技术面,行文案大白话;≤30 行帽保留,单行可变长)
export function renderDigestPush({ dateLabel, server, local, reds }) {
  const timeMark = (r) => {
    const m = /^(?:\d{4}-\d{2}-\d{2}-)(\d{2})(\d{2})-/.exec(String(r.round_id || ""));
    return m ? `${m[1]}:${m[2]}${mark(r)}` : `${shortId(r.round_id)}${mark(r)}`;
  };
  const lines = [];
  lines.push(`# ip-radar 日报 ${dateLabel}${reds.length ? ` ⚠(${reds.length} 红项)` : ""}`);
  lines.push("");
  lines.push("## 服务器(健康+发现,24h 窗)");
  if (server.error) lines.push(`- ⚠ 连不上服务器,今天读不到服务器数据:${server.error}`);
  const health = (server.rounds ?? []).filter((r) => r.round_id.endsWith("-health"));
  const discover = (server.rounds ?? []).filter((r) => r.round_id.endsWith("-discover"));
  if (!health.length && !discover.length && !server.error) lines.push("- 今天没有轮跑");
  if (health.length)
    lines.push(`- 健康轮 ${health.filter((r) => r.ok === true).length}/${health.length} 正常:${health.map(timeMark).join("、")}(服务器时间)`);
  if (discover.length)
    lines.push(`- 发现轮 ${discover.filter((r) => r.ok === true).length}/${discover.length} 正常:${discover.map(timeMark).join("、")}(服务器时间)`);
  const propose = server.propose_rows ?? [];
  lines.push(
    propose.length
      ? `- ${propose.length} 个候选源提案等人工裁决(PROPOSE):${propose.map((p) => p.source).join("、")}`
      : "- 没有新的候选源提案(PROPOSE 0 行)",
  );
  lines.push(
    `- 花费:近 24h ${fmtCny(server.ledger?.window_cost_cny ?? 0)},本月累计 ${fmtCny(server.ledger?.month_cost_cny ?? 0)}` +
      (server.refusals?.length ? `;另有 ${server.refusals.length} 次到帽拒启(见红项)` : ""),
  );
  lines.push((server.shadow_new ?? []).length ? `- ⚠ 影子目录出现新轮(见红项)` : "- 影子目录没有新轮,切流干净 ✓");
  if (server.missed_note) lines.push(`- ⚠ ${server.missed_note}(见红项)`);
  const srvOd = (server.overdue_rounds ?? []).filter((r) => r.ok === null).map((r) => plainClock(r.round_id));
  if (srvOd.length) lines.push(`- 昨天的轮还没收口(在跑或没成绩单,不算红):${srvOd.join("、")}`);
  lines.push("");
  lines.push("## 本机(演化+fleet)");
  const ev = local.evolve ?? {};
  const evRounds = ev.rounds ?? [];
  const r0 = evRounds[0];
  lines.push(
    `- 演化:${ev.halted ? "⚠ 已自停(见红项)" : `还在跑(连续没赚头 ${ev.stall_rounds ?? 0}/3)`}` +
      `${r0 ? `,今天 ${plainClock(r0.round_id)} 的轮${r0.ok === true ? "跑完 ✓" : r0.ok === false ? `失败(${r0.code ?? "?"},见红项)` : "还没收口"}` : ",今天没有轮"}` +
      (typeof ev.spend_total_cny === "number" ? `;本月花费 ${fmtCny(ev.spend_total_cny)}/帽 ${fmtCny(EVOLVE_CAP_CNY)}` : ""),
  );
  const adds = local.add_rounds ?? [];
  if (!adds.length) lines.push("- 自动加源:今天没有轮");
  else {
    const adm = adds.find((r) => r.monthly_admission)?.monthly_admission;
    lines.push(
      `- 自动加源 ${adds.filter((r) => r.ok === true).length}/${adds.length} 成功:${adds.map(timeMark).join("、")}` +
        (adm ? `;本月加源花费 ${fmtCny(adm.spend)}/帽 ${fmtCny(adm.cap)}` : ""),
    );
  }
  const localOd = [
    ...(local.evolve?.overdue_rounds ?? []).filter((r) => r.ok === null).map((r) => `${plainClock(r.round_id)}(演化)`),
    ...(local.overdue_add_rounds ?? []).filter((r) => r.ok === null).map((r) => `${plainClock(r.round_id)}(fleet)`),
  ];
  if (localOd.length) lines.push(`- 昨天的轮还没收口(在跑或没成绩单,不算红):${localOd.join("、")}`);
  if (reds.length) {
    lines.push("");
    lines.push("## 红项");
    const shown = reds.slice(0, MAX_LINES - lines.length - 2);
    for (const r of shown) lines.push(`- ⚠ ${plainRedItem(r, dateLabel)}`);
    if (reds.length > shown.length)
      lines.push(`- …另 ${reds.length - shown.length} 条见 dev/ops-digest/${dateLabel}.md`);
  }
  return { title: `ip-radar 日报 ${dateLabel}${reds.length ? " ⚠" : ""}`, body: lines.join("\n") };
}

// P2-3:push 失败要显形——apprise 失败/缺席 → exitCode=1(oneshot 不自动重试语义
// 不变,失败显形为 failed unit 交人看 journal);skip=静音律(env 未配置)不算失败。
export function pushExitCode(status) {
  return status === "failed" || status === "channel_missing" ? 1 : 0;
}

// —— IO 面 ——

// 单次 ssh 拉全量(限流友好):轮目录三日 glob(48h 扫描带跨到的 UTC 日期,P1-3)+
// 逐轮 gates/exits + 台账 + queue + 影子树清单。行标记协议:标记行 `__XXX__` 起节;
// 轮体两行 `__GATES__<json>` / `__EXITS__<json>`(tr -d "\n" 压单行——pretty JSON
// 的换行是排版字节,压掉不伤语义,字符串值内换行本就是 \n 转义)。内层 sh 单引号律:
// 脚本体只含双引号。
const SSH_INNER = [
  "echo __ROUNDS__; ls /app/data/ops/rounds 2>/dev/null;",
  'for p in /app/data/ops/rounds/"$(date -u +%Y-%m-%d)"-* /app/data/ops/rounds/"$(date -u -d @"$(( $(date -u +%s) - 86400 ))" +%Y-%m-%d)"-* /app/data/ops/rounds/"$(date -u -d @"$(( $(date -u +%s) - 172800 ))" +%Y-%m-%d)"-*; do',
  '  [ -d "$p" ] || continue; echo "__ROUND__${p##*/}";',
  '  echo "__GATES__$(cat "$p/gates.json" 2>/dev/null | tr -d "\\n")";',
  '  echo "__EXITS__$(cat "$p/08-anchor-sweep-exits.json" 2>/dev/null | tr -d "\\n")";',
  "done;",
  `echo __LEDGER__; cat ${OPS_LEDGER} 2>/dev/null;`,
  `echo __QUEUE__; cat ${OPS_QUEUE} 2>/dev/null;`,
  `echo __SHADOW__; ls ${SHADOW_ROUNDS} 2>/dev/null;`,
].join("\n");

function parseSshSections(text) {
  const sections = new Map();
  let cur = null;
  for (const line of String(text).split("\n")) {
    if (line.startsWith("__ROUND__")) {
      cur = `ROUND:${line.slice("__ROUND__".length).trim()}`;
      sections.set(cur, { gates: null, exits: null });
    } else if (line.startsWith("__GATES__")) {
      if (cur?.startsWith("ROUND:")) sections.get(cur).gates = line.slice("__GATES__".length);
    } else if (line.startsWith("__EXITS__")) {
      if (cur?.startsWith("ROUND:")) sections.get(cur).exits = line.slice("__EXITS__".length);
    } else if (/^__(ROUNDS|LEDGER|QUEUE|SHADOW)__\s*$/.test(line)) {
      cur = line.slice(2, -2);
      sections.set(cur, []);
    } else if (cur && sections.has(cur) && !cur.startsWith("ROUND:")) {
      sections.get(cur).push(line);
    }
  }
  return sections;
}

const parseJsonOrNull = (s) => {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
};

async function readServerFace(nowMs) {
  const remote = `docker exec ${SSH_CONTAINER} sh -c '${SSH_INNER.replace(/'/g, "")}'`;
  const res = await execFileP("ssh", [SSH_HOST, remote], { timeout: 60_000, maxBuffer: 16 * 1024 * 1024 });
  if (!res.ok)
    return { error: (res.stderr || res.error?.message || "ssh 非零退出").split("\n")[0].slice(0, 120) };

  const sec = parseSshSections(res.stdout);
  const allRoundIds = (sec.get("ROUNDS") ?? []).map((s) => s.trim()).filter(Boolean);
  // P1-3:48h 扫描带分带——窗内正常入 rounds,旧带入 overdue_rounds(终局补报)。
  const { window: winIds, overdue: odIds } = splitScanBands(allRoundIds, nowMs);
  const rounds = [];
  const overdue_rounds = [];
  for (const [key, body] of sec) {
    if (!key.startsWith("ROUND:")) continue;
    const id = key.slice("ROUND:".length);
    if (winIds.includes(id)) rounds.push(summarizeServerRound(id, parseJsonOrNull(body.gates), parseJsonOrNull(body.exits)));
    else if (odIds.includes(id)) overdue_rounds.push(summarizeServerRound(id, parseJsonOrNull(body.gates), parseJsonOrNull(body.exits)));
  }
  const ledgerRows = parseLedgerRows((sec.get("LEDGER") ?? []).join("\n"));
  const queueRows = parseQueueProposeRows((sec.get("QUEUE") ?? []).join("\n"));
  const shadowIds = (sec.get("SHADOW") ?? []).map((s) => s.trim()).filter(Boolean);
  const utcDate = (ms) => new Date(ms).toISOString().slice(0, 10);
  const windowDates = [utcDate(nowMs), utcDate(nowMs - WINDOW_MS)];
  const ledger = ledgerReadings(ledgerRows, {
    windowRoundIds: new Set(rounds.map((r) => r.round_id)),
    windowDates,
    month: utcDate(nowMs).slice(0, 7),
  });
  // 两日 glob 漏检兜底(容器 date 兼容性面):全量清单有窗内轮但没读到 → 注记(不猜红)。
  const missed = allRoundIds.filter(
    (id) => inWindow(id, nowMs, { utcOffsetMin: 0 }) && !rounds.some((r) => r.round_id === id),
  );
  return {
    rounds,
    overdue_rounds,
    ledger,
    refusals: ledger.refusals,
    propose_rows: selectProposeRows(queueRows, windowDates),
    shadow_new: shadowNewRounds(shadowIds),
    missed_note: missed.length ? `窗内轮未读到信封:${missed.join("、")}` : null,
  };
}

function readJsonSafe(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function listRoundIds(dir, suffix) {
  try {
    return fs
      .readdirSync(dir)
      .filter((id) => id.endsWith(suffix))
      .sort();
  } catch {
    return [];
  }
}

function readLocalFace(root, nowMs) {
  const cst = { utcOffsetMin: CST_OFFSET_MIN };
  const evolveState = readJsonSafe(path.join(root, "dev/evolution/state.json"));
  const evolveSpend = readJsonSafe(path.join(root, "dev/evolution/spend.json"));
  const evolveRoundsDir = path.join(root, "dev/evolution/rounds");
  const domains = Object.values(evolveState?.domains ?? {});
  // P1-3:48h 扫描带分带——窗内正常入 rounds,旧带入 overdue_rounds(终局补报)。
  const { window: evolveWindowIds, overdue: evolveOverdueIds } = splitScanBands(
    listRoundIds(evolveRoundsDir, "-evolve"),
    nowMs,
    cst,
  );
  const evolve = {
    halted: domains.some((d) => d.halted),
    stall_rounds: Math.max(0, ...domains.map((d) => d.stall_rounds ?? 0)),
    last_round_id: domains.map((d) => d.last_round_id).find(Boolean) ?? null,
    spend_total_cny: typeof evolveSpend?.total_cny === "number" ? evolveSpend.total_cny : null,
    rounds: evolveWindowIds.reverse().map((id) => {
      const env = readJsonSafe(path.join(evolveRoundsDir, id, "envelope.json"));
      return summarizeEvolveRound(env ?? { round_id: id }); // 无信封=在跑轮,ok:null 不算红
    }),
    overdue_rounds: evolveOverdueIds.reverse().map((id) => {
      const env = readJsonSafe(path.join(evolveRoundsDir, id, "envelope.json"));
      return summarizeEvolveRound(env ?? { round_id: id });
    }),
  };
  const addRoundsDir = path.join(root, "docs/ops/rounds");
  const { window: addWindowIds, overdue: addOverdueIds } = splitScanBands(
    listRoundIds(addRoundsDir, "-add"),
    nowMs,
    cst,
  );
  const add_rounds = addWindowIds.map((id) =>
    summarizeAddRound(
      id,
      readJsonSafe(path.join(addRoundsDir, id, "state.json")),
      readJsonSafe(path.join(addRoundsDir, id, "gates.json")),
    ),
  );
  const overdue_add_rounds = addOverdueIds.map((id) =>
    summarizeAddRound(
      id,
      readJsonSafe(path.join(addRoundsDir, id, "state.json")),
      readJsonSafe(path.join(addRoundsDir, id, "gates.json")),
    ),
  );
  return { evolve, add_rounds, overdue_add_rounds };
}

// apprise 推送:--body 走 execFile 参数数组(无 shell,免转义;body ≤30 行远小于
// ARG_MAX)。装机目标 apprise v2.2.0 无 --body-file 旗标(2026-11-20 实测;原评审
// 「--body-file 免转义」判定据此订正)。exec 可注入=测试钉 argv 形状用。
export async function pushLark(title, body, log, exec = execFileP) {
  const urls = String(process.env.IP_RADAR_ALERT_URLS ?? "").split(/,\s*|\s+/).filter(Boolean);
  if (!urls.length) {
    log("推送跳过:IP_RADAR_ALERT_URLS 未配置(静音律,evolution exits 同律)");
    return { status: "skip" };
  }
  const candidates = ["apprise", path.join(os.homedir(), ".local/bin/apprise")];
  for (const cmd of candidates) {
    const res = await exec(cmd, ["--title", title, "--body", body, ...urls], {
      timeout: 30_000,
      maxBuffer: 1024 * 1024,
    });
    if (res.ok) {
      log(`已推送 lark(apprise=${cmd},URL ×${urls.length})`);
      return { status: "posted" };
    }
    if (res.error?.code !== "ENOENT") {
      log(`apprise 失败(rc=${res.error?.code ?? "?"}):${res.stderr.slice(0, 160)}`);
      return { status: "failed" };
    }
  }
  log("apprise 不在 PATH 也无 ~/.local/bin/apprise(ENOENT)");
  return { status: "channel_missing" };
}

async function main() {
  const args = process.argv.slice(2);
  const push = args.includes("--push");
  const rootIdx = args.indexOf("--root");
  const root =
    rootIdx >= 0 ? path.resolve(args[rootIdx + 1]) : path.resolve(fileURLToPath(import.meta.url), "..", "..");
  const nowMs = Date.now();
  const dateLabel = new Date(nowMs + CST_OFFSET_MIN * 60_000).toISOString().slice(0, 10);

  const server = await readServerFace(nowMs);
  const local = readLocalFace(root, nowMs);
  const reds = collectRedItems({ server, local });
  if (server.missed_note) reds.push(server.missed_note);
  const { fileBody } = renderDigest({ dateLabel, server, local, reds });
  const pushFace = renderDigestPush({ dateLabel, server, local, reds }); // #383:lark 吃大白话版

  const digestDir = path.join(root, "dev/ops-digest");
  fs.mkdirSync(digestDir, { recursive: true });
  const outFile = path.join(digestDir, `${dateLabel}.md`);
  fs.writeFileSync(outFile, `${fileBody}\n`); // 落盘=技术面全量版(证据面不漂移,#383 双面律)
  console.log(pushFace.body);
  console.log(
    `\n[落盘] ${outFile}(lark 推送版 ${pushFace.body.split("\n").length}/${MAX_LINES} 行,技术面入档${reds.length ? `;附录全量 ${reds.length} 条红` : ""})`,
  );
  if (push) {
    // push 面吃大白话版(行数帽),不吃落盘技术全量版——两版本分开出(双面律)。
    const res = await pushLark(pushFace.title, pushFace.body, console.error);
    process.exitCode = pushExitCode(res.status); // P2-3:失败显形(oneshot 不自动重试)
  } else console.log("[模式] dry-run(未推送;推送=--push)");
  // 红项=日报内容而非脚本失败(票面:红项入标题交人裁)。退出码:红项恒 0;非零仅
  // 两处=脚本自身异常(exit 3)/推送失败(P2-3,apprise 失败或缺席显形 failed unit)。
}

// 测试 import 纯函数面;CLI 直跑才走 main(node --test 不触发 main)。
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(e);
    process.exit(3);
  });
}
