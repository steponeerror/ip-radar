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
//   双渲染(P1-2):push 版 ≤30 行(红项截断,余量指针落盘件);落盘版=push 版+
//   全量红项附录(不截断)——截断只截推送面,不截档。
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
  // 双渲染(P1-2):落盘版追加全量红项附录——push 版截断的余量只在档上,不灭失。
  const fileBody = reds.length
    ? `${body}\n\n## 红项附录(全量 ${reds.length} 条;push 版仅截断列表)\n\n${reds.map((r) => `- ⚠ ${r}`).join("\n")}`
    : body;
  return { title: `ip-radar 日报 ${dateLabel}${reds.length ? " ⚠" : ""}`, body, fileBody };
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
  const { title, body, fileBody } = renderDigest({ dateLabel, server, local, reds });

  const digestDir = path.join(root, "dev/ops-digest");
  fs.mkdirSync(digestDir, { recursive: true });
  const outFile = path.join(digestDir, `${dateLabel}.md`);
  fs.writeFileSync(outFile, `${fileBody}\n`); // 落盘=全量版(双渲染,P1-2)
  console.log(body);
  console.log(
    `\n[落盘] ${outFile}(push 版 ${body.split("\n").length}/${MAX_LINES} 行${reds.length ? `;附录全量 ${reds.length} 条红` : ""})`,
  );
  if (push) {
    // push 面吃截断 body(行数帽),不吃落盘全量版——两版本分开出(P1-2)。
    const res = await pushLark(title, body, console.error);
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
