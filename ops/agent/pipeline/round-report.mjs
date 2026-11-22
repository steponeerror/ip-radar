// round-report.mjs — 运营轮报告件(packages/*.md)渲染+落盘单源(工单 #403)。
// Why:pipeline v1/v2 轮 CLOSE 从不写 $DOCS_ROOT/ops/packages/,而 UI「查看报告」链
// (OpsPage.tsx 档案子 tab → OpsPackagesSection → GET /api/ops/packages →
// backend/ipdb/_ops_read.py list_packages 只列该目录 *.md)停更在 2026-10-24 legacy 轮
// ——用户点开看不到本轮报告(断供)。本模块在 CLOSE 收口处把轮的确定性读数渲染成
// markdown 落 packages/,断供修复。
// Why(#420 人读面重构,用户判例「报告可读性太差,人要自己从表里挖这轮有没有事」):
// 首屏=结论先行——**结论:一句话**置顶(推导规则见 conclusionOf,全部读盘上工件,
// 缺席工件不写该分句=宁少算);旧头部 bullet 列表折入「## 概览」表;相位表用人读用时
// (0.1s 精度/≥60s 走 1m06s 形,毫秒精确值在信封 JSON,证据不灭失)。门/分型读数/
// 信封三节照旧。前端配套受控 markdown 渲染(frontend/src/components/MarkdownDoc.tsx)。
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
// 概览金额(#420):有限数→toFixed(8) 台账同口径(0.10520580999999996 → 0.10520581);
// 非数/缺席→—(宁少算不造数字)
const cny8 = (x) => (typeof x === "number" && Number.isFinite(x)) ? x.toFixed(8) : "—";
// 概览表人读用量形(#420):数字用 · 分隔,金额走 cny8(有限数守卫,NaN/Infinity→—);
// 台账原始同形串(in=… out=…)仍在轮台账行。
const usageHuman = (u) => u == null ? "—" : `in ${u.input ?? 0} · out ${u.output ?? 0} · total ${u.totalTokens ?? 0} · ¥${cny8(u.cost ?? 0)}`;
// 人读用时(#420):<60s → 38.9s(0.1s 精度);≥60s → 1m06s;毫秒精确值在信封 JSON
// (相位记录 dur_ms),人读面不重复高精度。0 → 0.0s(确定值,非缺席)。
const humanDur = (ms) => {
  const v = ms ?? 0;
  if (v < 60000) return `${(v / 1000).toFixed(1)}s`;
  const totalS = Math.round(v / 1000);
  return `${Math.floor(totalS / 60)}m${String(totalS % 60).padStart(2, "0")}s`;
};

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

// ── 结论推导(#420 结论先行;全部读盘上工件,缺席工件不写该分句=宁少算)──
// 优先级:门红最高(gates.json 任一 record !pass → 有门红+失败门名列);相位里
// failed/crashed → 提及(防御面:正常成功轮不达);随后 per-type 分型读数。正常轮
// gates.json 恒在场(CLOSE 前写),末尾 fallback 不可达——仍给确定性文案不掷错。
function conclusionOf({ type, dir, stages }) {
  const gates = j(path.join(dir, "gates.json"));
  const failedGates = (gates?.records ?? []).filter((r) => !r.pass).map((r) => r.name);
  const parts = [];
  if (failedGates.length) parts.push(`有门红:${failedGates.join("、")}`);
  const badStages = (stages ?? []).filter((r) => r.status === "failed" || r.status === "crashed").map((r) => r.name);
  if (badStages.length) parts.push(`相位异常:${badStages.join("、")}`);
  if (type === "health") {
    // 计数面=分型读数同源工件;抑制信号入非零判定但不出全绿分句(留痕降权面,
    // 非零亦提示复核——评审 #420 P3-1 注释对齐行为)
    const counts = [];
    const surv = j(path.join(dir, "02-verify-survivors.json"));
    if (surv) counts.push(["幸存信号", (surv.survivors ?? []).length]);
    const sup = j(path.join(dir, "02-verify-suppressed.json"));
    if (sup) counts.push(["抑制信号", (sup.suppressed ?? []).length]);
    const h3 = j(path.join(dir, "03-triage-hypotheses.json"));
    if (h3) counts.push(["假设", (h3.hypotheses ?? []).length]);
    const exits = j(path.join(dir, "08-anchor-sweep-exits.json"));
    if (exits) counts.push(["锚巡检 finding", exits.findings_n ?? 0]);
    const nonzero = counts.filter(([, n]) => n > 0);
    if (nonzero.length) parts.push(`有信号待看:${nonzero.map(([l, n]) => `${l} ${n}`).join(" / ")}`);
    else if (counts.length) parts.push(`全绿,无需动作。${counts.filter(([l]) => l !== "抑制信号").map(([l, n]) => `${l} ${n}`).join(" / ")}`);
  } else if (type === "discover") {
    const d4 = j(path.join(dir, "d4-enqueue.json"));
    if (d4) {
      parts.push(`发现轮入队 ${d4.n_enqueued ?? (d4.enqueued ?? []).length}(跳过 ${d4.n_skipped ?? (d4.skipped ?? []).length} / 标记 ${d4.n_flagged ?? (d4.flagged ?? []).length})`);
      const ei = j(path.join(dir, "enqueue-issues.json")); // v2 issue 出口工件(#384;v1 轮缺席=跳过)
      if (ei) parts.push(`issue 出口 ${ei.status ?? "?"}(开 ${ei.issues_opened ?? 0} / 败 ${ei.issues_failed ?? 0})`);
    }
  }
  // 分句自不带句号,末尾统一一个。(多分句并存=防御面:门红+相位异常+读数同现,分号隔开)
  return parts.length ? `${parts.join(";")}。` : "门与分型读数工件缺席,详见信封。"; // 防御面(不可达见头注)
}

// 渲染 markdown(确定性:读盘上工件+信封,无时钟入文)。#420 起结论先行+概览表:
// 人读面首屏即「这轮有没有事」,原始数字全部仍在(门表/分型读数/信封,证据不灭失)。
// 相位表前两列形「| NAME | status |」冻结(v2/selftest 断言依赖);每相位用量细目
// 折入信封 JSON stages,人读表不重复——信封缺席=每相位用量证据缺口(v1/v2 三接线
// 今日恒传 ctx.envelope,未来接线勿裸调,评审 #420 P3-3)。
function renderRoundReport({ roundId, type, engine, ctx, stages }) {
  const st = ctx.state ?? {};
  const L = [
    `# 运营轮报告 ${roundId}`, "",
    `**结论:${conclusionOf({ type, dir: ctx.dir, stages: stages ?? st.stages })}**`, "",
    "## 概览", "",
    "| 项 | 值 |", "|---|---|",
    `| 类型 | ${type}(引擎 ${engine} · 模型面 ${st.model_face ?? "—"}) |`,
    `| 开始 | ${st.started_at ?? "—"} |`,
    `| 用量 | ${usageHuman(ctx.usage)} |`,
  ];
  if (st.monthly_admission != null) { // A2 准入读数(月帽投影;缺席轮不写=不造数字)
    const m = st.monthly_admission;
    // 帽=旋钮原值(整数字面 ¥30);已花/投影=浮点噪声金额,toFixed(8) 台账同口径
    L.push(`| 月度准入 | ${m.month ?? "—"} 已花 ¥${cny8(m.spend)} / 帽 ¥${m.cap ?? "—"} / 投影 ¥${cny8(m.projected)} |`);
  }
  const recs = stages ?? st.stages ?? [];
  if (recs.length) {
    L.push("", "## 相位", "", "| 相位 | 状态 | 用时 |", "|---|---|---|");
    for (const r of recs) L.push(`| ${r.name} | ${r.status} | ${humanDur(r.dur_ms)} |`);
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
