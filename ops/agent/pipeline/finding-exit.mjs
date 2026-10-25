// pipeline/finding-exit.mjs — finding 出口三件套:gh issue + 告警 webhook(票 #184;spec #180 首批租户 Q6)。
// 出口③(RETRO 摘要行)在 steps.mjs RETRO 步读 08 工件计数,不入本模块(步只测量不判断,摘要=零出口动作)。
// 出口只写不动作(结构性红线,票面钉死):从 finding 出发的代码路径仅两写口——
//   ①gh issue create(tools.mjs ghIssueCreate;gh 面唯一写面 GH_WRITE_SUBCOMMANDS,argv 头钉 [issue,create],
//     缺省标签 needs-triage=人裁终局);②apprise CLI 推送(与后端源活性告警 _alerts.push 同 env 同 URL 形:
//     IP_RADAR_ALERT_URLS 逗号/空白分隔多 URL,空=静音跳过)。无任何调权/停源/写数据面/规则库写口可达
//   ——依赖面闭集由 selftest-pipeline 结构性断言钉死(本模块 spawn 目标恰 apprise;gh 面在 tools.mjs 由
//   t4 注入 exec 捕获 argv 钉死;禁面符号零在场)。
// 触发面:ANCHOR_SWEEP 读数 ok 且 finding>0(#184 要点);finding=0/求值面死/replay 重放 → 全 skip 留痕
//   (审计重放零外发,ITEMIZE 回声律同款;无证据即无话)。工件形状破(逐行/计数自洽)也=不动作,
//   交 G_ANCHOR_SWEEP 门拦(宁少算)。
// 出口永不败轮:任何出口失败=失败信封记入 08-anchor-sweep-exits.json 与 state.finding_exits,轮照常成功
//   (信封 pipeline.finding_exits 留痕;skip/failed 同为合法态——webhook 未配置=skip 痕即票面语义)。
// dry-run:OPS_SWEEP_DRY_RUN=1 时只记 cmd/payload 零外发(默认关=生产真发;测试恒 dry-run)。
// emit 守卫(resume 防重发):出口工件先记 phase=emitting 再外发、终记 emitted;同轮重入见 emitting/emitted
//   一律不重发(崩溃窗内外发状态不可知,宁少算交人工核对——issue 重复开可人关,漏发可下轮补)。
//   守卫触发不改写工件(终审修单 M4):emitted 全稿存活=证据永不灭失,且守卫幂等——写回 skip 会让
//   同窗二次崩溃的重入误判首程→重发→重复外发(issue+webhook 双重复)。
// URL 脱敏:webhook URL 含凭据(lark://<token> 等),记录面只存 scheme+尾4(_alerts._redact_url 同律)。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { ghIssueCreate } from "../tools.mjs";

const execFileP = promisify(execFileCb);
const APPRISE_TIMEOUT_MS = 15_000; // apprise CLI 单批推送超时(防挂轮;库面 _alerts 无此面,CLI 面必须有)
const EXITS_ARTIFACT = "08-anchor-sweep-exits.json";

// URL 脱敏(_alerts._redact_url 同律):只留 scheme+尾 4 字符;余段 ≤8 只留 ***
const redactUrl = (u) => {
  const s = String(u), i = s.indexOf("://");
  if (i < 0) return "***";
  const rest = s.slice(i + 3);
  return `${s.slice(0, i)}://${rest.length > 8 ? `…${rest.slice(-4)}` : "***"}`;
};

// 巡检读数 → finding 投影(纯函数):只取指控行(ok=false)且逐行形状自洽(ip/expect/verdict/confidence/
// accusers 与 G_ANCHOR_SWEEP 门同字段);conflict(#188 benign②)=良性断言×指控同场留痕标记,
// 容缺投影(r.conflict===true;旧工件无字段=false,严格形状校验归 G_ANCHOR_SWEEP 门)。
// 任何坏行或 n_fail≠回算 → {ok:false}(出口不动作,门接管)。
export function parseFindings(d) {
  const rows = Array.isArray(d?.results) ? d.results : [];
  const findings = [];
  for (const r of rows) {
    if (!r || r.ok !== false) continue;
    if (typeof r.ip !== "string" || typeof r.expect !== "string" || typeof r.verdict !== "string" || !r.verdict
      || typeof r.confidence !== "number" || !Array.isArray(r.accusers) || !r.accusers.every((a) => typeof a === "string"))
      return { ok: false, reason: `finding 行形状非法(ip=${r?.ip ?? "?"})——工件自洽交 G_ANCHOR_SWEEP 拦,出口不动作(宁少算)` };
    findings.push({ ip: r.ip, expect: r.expect, verdict: r.verdict, confidence: r.confidence, accusers: r.accusers,
      conflict: r.conflict === true });
  }
  if (d && typeof d.n_fail === "number" && d.n_fail !== findings.length)
    return { ok: false, reason: `n_fail=${d.n_fail}≠finding 回算 ${findings.length}——工件自洽交 G_ANCHOR_SWEEP 拦,出口不动作` };
  return { ok: true, findings };
}

// issue 模板(票面四件:来源步/锚:期望vs实得/证据指针/needs-triage 标签)。纯函数,测试直钉。
export function findingIssueDraft({ roundId, findings, nTotal }) {
  const title = `[anchor-sweep] ${findings.length} finding(${roundId})`;
  const body = [
    "## 来源步",
    "ANCHOR_SWEEP(ops 健康轮生产查询路径锚巡检,#182;锚 finding 不持门——本 issue 是 finding 出口,只写不动作,#180 首批租户 Q6)",
    "",
    "## 锚:期望 vs 实得",
    ...findings.map((f) => `- ${f.ip}(expect=${f.expect}):实得 verdict=${f.verdict} confidence=${f.confidence} 指控源=${f.accusers.join(", ") || "(无)"}${f.conflict ? " 对立=verdict_conflict(良性断言×指控同场,#188 留痕人裁——宁少算不自动压制指控)" : ""}`),
    "",
    "## 证据指针",
    `- 巡检工件:ops/rounds/${roundId}/08-anchor-sweep.json(n_total=${nTotal},n_fail=${findings.length})`,
    "- 锚集与判定核真源:backend/ipdb/_eval/anchors.py",
    `- 出口记录:ops/rounds/${roundId}/08-anchor-sweep-exits.json`,
    "",
    "处置:needs-triage 人裁终局;出口面禁自动调权/停源/写数据(结构性钉死)。",
  ].join("\n");
  return { title, body, labels: ["needs-triage"] };
}

// webhook 出口(apprise CLI;永不抛)。三态 + 失败分类:ENOENT→channel_missing/超时→transient/其余→webhook_failed。
async function webhookExit({ title, body, urls, dryRun, exec = execFileP }) {
  if (!urls.length)
    return { status: "skip", urls_n: 0, reason: "IP_RADAR_ALERT_URLS 未配置(降级跳过,轮仍成功;_alerts 同静音律)" };
  if (dryRun)
    return { status: "dry_run", urls_n: urls.length, urls_redacted: urls.map(redactUrl), payload_head: `${title} / ${body.slice(0, 80)}` };
  try {
    await exec("apprise", ["--title", title, "--body", body, ...urls], { timeout: APPRISE_TIMEOUT_MS, maxBuffer: 1024 * 1024 });
    return { status: "posted", urls_n: urls.length, urls_redacted: urls.map(redactUrl) };
  } catch (e) {
    const timedOut = e?.killed === true || e?.signal === "SIGTERM" || e?.code === "ETIMEDOUT";
    const rc = e?.code === "ENOENT" ? 127 : (typeof e?.code === "number" ? e.code : (timedOut ? 124 : 1));
    const code = rc === 127 ? "channel_missing" : (timedOut ? "transient" : "webhook_failed");
    let reason = String(e?.stderr ?? e?.message ?? e).slice(0, 200);
    for (const u of urls) reason = reason.split(u).join(redactUrl(u)); // stderr 回显 URL 也脱敏
    return { status: "failed", code, reason: `apprise 通道失败(rc=${rc}):${reason}` };
  }
}

// 出口编排(ANCHOR_SWEEP 步消费;永不抛永不败轮)。返回 lean 记录(入 state/信封);
// 全稿(issue 草稿/webhook payload)只落 08-anchor-sweep-exits.json 工件(证据不灭失,信封不膨胀)。
export async function runFindingExits({ roundId, sweepD, dir, env = process.env, replayOf = null, exec = execFileP } = {}) {
  const record = { triggered: false, findings_n: 0, dry_run: false, reason: null, gh_issue: null, webhook: null, retrospective_summary: null };
  const artifactPath = dir ? path.join(dir, EXITS_ARTIFACT) : null;
  const writeArtifact = (extra) => { if (!artifactPath) return;
    fs.writeFileSync(`${artifactPath}.tmp`, JSON.stringify({ ...record, round_id: roundId, ...extra }, null, 2) + "\n");
    fs.renameSync(`${artifactPath}.tmp`, artifactPath); }; // 原子写(沿 _ops_store 判例)
  const skipAll = (reason, { keepArtifact = false } = {}) => { record.reason = reason;
    record.gh_issue = { status: "skip", reason };
    record.webhook = { status: "skip", reason };
    if (!keepArtifact) writeArtifact({ phase: "skip" });
    return record; }; // keepArtifact=守卫分支专用:工件已记 emitting/emitted 全稿,重写 skip 灭失外发证据(哲学1)
  if (!sweepD) return skipAll("anchor_sweep_degraded(求值面死,无读数即无 finding;降级旁路工件另案留痕)");
  const parsed = parseFindings(sweepD);
  record.findings_n = parsed.ok ? parsed.findings.length : (typeof sweepD.n_fail === "number" ? sweepD.n_fail : 0);
  if (!parsed.ok) return skipAll(parsed.reason);
  if (replayOf) return skipAll(`replay_zero_emit(审计重放零外发,replay_of=${replayOf};ITEMIZE 回声律同款)`);
  const findings = parsed.findings;
  if (!findings.length) return skipAll("findings=0(金标巡检全绿,出口不触发)");
  // emit 守卫:同轮出口工件已记 emitting/emitted → 不重发(崩溃窗内外发状态不可知,宁少算交人工)
  if (artifactPath) {
    try {
      const prev = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
      if (prev?.round_id === roundId && (prev.phase === "emitted" || prev.phase === "emitting"))
        return skipAll(`emit_guard(出口工件已记 phase=${prev.phase};resume 防重发,不自动重发——人工核对,漏发下轮补)`,
          { keepArtifact: true }); // 不重写工件(终审修单 M4):issue 草稿/issue_url/webhook_payload 全稿存活;守卫幂等
    } catch { /* 无工件=首程,照发 */ }
  }
  record.triggered = true;
  const dryRun = String(env.OPS_SWEEP_DRY_RUN ?? process.env.OPS_SWEEP_DRY_RUN ?? "") === "1";
  record.dry_run = dryRun;
  const draft = findingIssueDraft({ roundId, findings, nTotal: Array.isArray(sweepD.results) ? sweepD.results.length : null });
  writeArtifact({ phase: "emitting" }); // 先记意图再外发(emit 守卫的崩溃窗依据)
  const issue = await ghIssueCreate(draft, { dryRun, exec });
  record.gh_issue = issue.ok
    ? { status: dryRun ? "dry_run" : "created", labels: draft.labels, cmd_head: issue.cmd.slice(0, 200),
        ...(issue.issue_url ? { issue_url: issue.issue_url } : {}) }
    : { status: "failed", labels: draft.labels, code: issue.error.code, reason: String(issue.error.reason).slice(0, 200) };
  const urls = String(env.IP_RADAR_ALERT_URLS ?? process.env.IP_RADAR_ALERT_URLS ?? "").split(/,\s*|\s+/).filter(Boolean);
  record.webhook = await webhookExit({ title: draft.title, body: draft.body, urls, dryRun, exec });
  writeArtifact({ phase: "emitted", issue: draft, webhook_payload: { title: draft.title, body: draft.body } });
  return record;
}
