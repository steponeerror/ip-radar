// round-report.mjs — 运营轮报告件(packages/*.md)渲染+落盘单源(工单 #403)。
// Why:pipeline v1/v2 轮 CLOSE 从不写 $DOCS_ROOT/ops/packages/,而 UI「查看报告」链
// (OpsPage.tsx 档案子 tab → OpsPackagesSection → GET /api/ops/packages →
// backend/ipdb/_ops_read.py list_packages 只列该目录 *.md)停更在 2026-10-24 legacy 轮
// ——用户点开看不到本轮报告(断供)。本模块在 CLOSE 收口处把轮的确定性读数渲染成
// markdown 落 packages/,断供修复。
// 命名 `${date}-${type}-${HHMM}[-rN].md`:保持 frontend/src/pages/opsLedger.ts
// pkgMatchesRow 的「日期+轮型前缀」关联(改向即与台账行失联);backend
// _ops_store.validate_ops_filename 纯文件名形状兼容。
// 消费方向:ops/agent-v2 三接线零复制 import 本模块(仓内单向依赖惯例 v2→v1,方向勿反)。
// 纪律:内容全部确定性读盘上工件(缺件跳节不掷错,宁少算;不造无证据数字;无时钟
// 入文=幂等重写逐字节同);落盘原子写(tmp+rename,沿 _ops_store.atomic_write_text
// 判例);写败掷 {code:"infra"} 由调用面按既有失败路径收口(fail loud:静默=用户
// 再次看不到报告)。
import fs from "node:fs";
import path from "node:path";

const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
// 用量行=台账行同形(in=… out=… total=… cost=…,lib.sh ledger_append toFixed(8) 同口径)
const usageText = (u) => u == null ? "—" : `in=${u.input ?? 0} out=${u.output ?? 0} total=${u.totalTokens ?? 0} cost=${(u.cost ?? 0).toFixed(8)}`;

const ROUND_ID_RE = /^(\d{4}-\d{2}-\d{2})-(\d{4})-(health|discover)(-r\d+)?$/; // 旧 pipeline.mjs mkCtx 轮 id 律同形(后缀集=轮型集;-rN=replay 派生轮)

// 轮 id → 报告件名(2026-11-22-0500-discover → 2026-11-22-discover-0500.md)。
// 形状不合掷错(宁响不猜:名字是 pkgMatchesRow 关联面,猜一个=失联)。
export function reportNameOf(roundId) {
  const m = ROUND_ID_RE.exec(String(roundId));
  if (!m) throw Object.assign(new Error(`round_id 形状须 YYYY-MM-DD-HHMM-(health|discover):${roundId}`), { code: "bad_round" });
  return `${m[1]}-${m[3]}-${m[2]}${m[4] ?? ""}.md`;
}

// ── 分型读数(现读轮目录工件;缺席条目跳过=宁少算,缺席≠零 ──
function discoverReadings(dir) {
  const out = [];
  const d1 = j(path.join(dir, "d1-scan.json"));
  if (d1) {
    const ch = d1.channels ?? {};
    const parts = ["registry", "needs", "web"].filter((k) => ch[k]).map((k) => `${k}=${ch[k].n ?? 0}`);
    out.push(`- 候选宇宙:${(d1.candidates ?? []).length}${parts.length ? `(${parts.join(" ")})` : ""} — d1-scan.json`);
  }
  const d2 = j(path.join(dir, "d2-shortlist.json"));
  if (d2) out.push(`- 入围:${(d2.candidates ?? []).length}${d2.degraded ? `(降级:${d2.degraded})` : ""} — d2-shortlist.json`);
  const d3 = j(path.join(dir, "d3-measure.json"));
  if (d3) out.push(`- 测量:${d3.n ?? (d3.results ?? []).length}${typeof d3.hold_n === "number" ? `(hold=${d3.hold_n})` : ""} — d3-measure.json`);
  // 通道计数真源=09-budget.json readings.discover_channels(CLOSE 步先于报告落盘;
  // d3 自身只有逐候选结果,无聚合面)
  const channels = j(path.join(dir, "09-budget.json"))?.readings?.discover_channels?.channels;
  if (channels) {
    const cells = Object.entries(channels).map(([t, c]) => `${t} calls=${c.calls} ok=${c.ok} failed=${c.failed}${c.blocked ? ` blocked=${c.blocked}` : ""}`);
    if (cells.length) out.push(`- 通道:${cells.join(";")} — 09-budget.json readings.discover_channels`);
  }
  const d4 = j(path.join(dir, "d4-enqueue.json"));
  if (d4) out.push(`- 入队:enqueued=${d4.n_enqueued ?? (d4.enqueued ?? []).length} skipped=${d4.n_skipped ?? (d4.skipped ?? []).length} flagged=${d4.n_flagged ?? (d4.flagged ?? []).length} — d4-enqueue.json`);
  const ei = j(path.join(dir, "enqueue-issues.json")); // v2 issue 出口工件(#384;v1 轮缺席=跳过)
  if (ei) {
    out.push(`- issue 出口:status=${ei.status ?? "?"}${ei.reason ? `(${ei.reason})` : ""} issues_opened=${ei.issues_opened ?? 0} issues_failed=${ei.issues_failed ?? 0} — enqueue-issues.json`);
    for (const it of ei.issues ?? []) out.push(`  - ${it.status ?? "?"}:${it.candidate ?? it.title ?? "?"}${it.issue_url ? ` → ${it.issue_url}` : ""}${it.status === "failed" ? `(code=${it.code ?? "?"})` : ""}`);
  }
  return out;
}

function healthReadings(dir) {
  const out = [];
  const surv = j(path.join(dir, "02-verify-survivors.json"));
  if (surv) out.push(`- 幸存信号:${(surv.survivors ?? []).length} — 02-verify-survivors.json`);
  const sup = j(path.join(dir, "02-verify-suppressed.json"));
  if (sup) out.push(`- 抑制信号:${(sup.suppressed ?? []).length}(留痕降权,证据不灭失) — 02-verify-suppressed.json`);
  const h3 = j(path.join(dir, "03-triage-hypotheses.json"));
  if (h3) out.push(`- 假设:${(h3.hypotheses ?? []).length} — 03-triage-hypotheses.json`);
  const exits = j(path.join(dir, "08-anchor-sweep-exits.json"));
  if (exits) {
    out.push(`- 锚巡检 finding:${exits.findings_n ?? 0}(triggered=${String(exits.triggered)}${exits.reason ? `;${exits.reason}` : ""}) — 08-anchor-sweep-exits.json`);
    const gh = exits.gh_issue, wh = exits.webhook;
    if (gh || wh) out.push(`- 出口:gh_issue=${gh?.status ?? "—"}${gh?.issue_url ? ` ${gh.issue_url}` : ""};webhook=${wh?.status ?? "—"} — 08-anchor-sweep-exits.json`);
  }
  return out;
}

// 渲染 markdown(确定性:读盘上工件+信封,无时钟入文)。
function renderRoundReport({ roundId, type, engine, ctx, stages }) {
  const st = ctx.state ?? {};
  const L = [
    `# 运营轮报告 ${roundId}`, "",
    `- 轮次:${roundId}`,
    `- 类型:${type}`,
    `- 引擎:${engine}`,
    `- 模型面:${st.model_face ?? "—"}`,
    `- started_at:${st.started_at ?? "—"}`,
    `- 用量:${usageText(ctx.usage)}`,
  ];
  if (st.monthly_admission != null) { // A2 准入读数(月帽投影;缺席轮不写=不造数字)
    const m = st.monthly_admission;
    L.push(`- 月度准入:month=${m.month ?? "—"} spend=${m.spend ?? "—"} cap=${m.cap ?? "—"} projected=${m.projected ?? "—"}`);
  }
  const recs = stages ?? st.stages ?? [];
  if (recs.length) {
    L.push("", "## 相位", "", "| 相位 | 状态 | 用时ms | 用量 |", "|---|---|---|---|");
    for (const r of recs) L.push(`| ${r.name} | ${r.status} | ${r.dur_ms ?? 0} | ${usageText(r.usage)} |`);
  }
  const gates = j(path.join(ctx.dir, "gates.json"));
  if (gates?.records?.length) {
    L.push("", "## 门", "", "| 门 | 相位 | 结果 | 说明 |", "|---|---|---|---|");
    for (const g of gates.records) L.push(`| ${g.name} | ${g.stage} | ${g.pass ? "PASS" : "FAIL"} | ${g.pass ? "—" : String(g.reason ?? "—")} |`);
  }
  const readings = type === "discover" ? discoverReadings(ctx.dir) : healthReadings(ctx.dir);
  if (readings.length) L.push("", "## 分型读数", "", ...readings);
  if (ctx.envelope != null) L.push("", "## 信封", "", "```json", JSON.stringify(ctx.envelope, null, 2), "```", "");
  return L.join("\n");
}

// 渲染+落盘 <opsRoot>/packages/<name>.md(mkdir -p;幂等重写;原子写)。
// 写败掷 {code:"infra"}(调用面收口:旧引擎 finishClose→failStage 终态;v2 discover
// scriptPhase→finishFailed;v2 health runClose→既有 catch——三面同律 fail loud)。
export function writeRoundReport({ roundId, type, engine, ctx, stages, opsRoot }) {
  const name = reportNameOf(roundId); // 形状律先行(名字=关联面,宁响不猜)
  const text = renderRoundReport({ roundId, type, engine, ctx, stages });
  let p;
  try {
    const dir = path.join(String(opsRoot), "packages");
    fs.mkdirSync(dir, { recursive: true });
    p = path.join(dir, name);
    fs.writeFileSync(`${p}.tmp`, text);
    fs.renameSync(`${p}.tmp`, p);
  } catch (e) {
    throw Object.assign(new Error(`轮报告件写败(packages/${name}):${e.message}`), { code: "infra" });
  }
  return p;
}
