#!/usr/bin/env node
// exits.mjs — 自演化轮报告出口两件(票 #356 骨架 v1 交付面 4)。
//
// ①每轮 gh 票(轮结果单+工件路径;复用 v1 ghIssueCreate 单源——ops/pipeline-core/tools.mjs
//   measurement.mjs 的 gh 面,argv 头钉 [issue,create],凭证走 gh CLI 本体);
// ②异常 lark 推送(复用 finding 推送通道的通道契约:apprise CLI + env
//   IP_RADAR_ALERT_URLS 逗号/空白分隔多 URL,空=静音跳过;三态分类/超时/脱敏全同
//   ops/pipeline-core/pipeline/finding-exit.mjs webhookExit 律——v1 模块未导出该函数,且 v2
//   不 import v1 管线件,故按同律重写小面,词面不新造)。
// 出口永不败轮(finding-exit 同律):失败=记录,轮结果照常;记录全稿落轮工件
// exits.json(证据不灭失)。dry-run:env EVOLVE_EXITS_DRY_RUN=1 或 opts.dryRun
// (测试/装机演练面;缺省生产真发)。
// 标签:轮结果单 needs... 族里取 ready-for-human(跑完待人裁——票面「跑完出报告待人裁」,
// 冠军并 master 是人裁位)。
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { ghIssueCreate } from "../../../pipeline-core/tools.mjs";

const execFileP = promisify(execFileCb);
const APPRISE_TIMEOUT_MS = 15_000; // finding-exit 同值(防挂轮)

// URL 脱敏(finding-exit redactUrl 同律):只留 scheme+尾 4;余段 ≤8 只留 ***
export function redactUrl(u) {
  const s = String(u), i = s.indexOf("://");
  if (i < 0) return "***";
  const rest = s.slice(i + 3);
  return `${s.slice(0, i)}://${rest.length > 8 ? `…${rest.slice(-4)}` : "***"}`;
}

// 异常 lark 推送(apprise;永不抛)。三态 + 失败分类同 finding-exit webhookExit:
// 未配置→skip;ENOENT→channel_missing;超时→transient;其余→webhook_failed。
export async function pushAnomalyLark({ title, body, env = process.env, dryRun, exec = execFileP }) {
  const isDry = dryRun ?? String(env.EVOLVE_EXITS_DRY_RUN ?? "") === "1";
  const urls = String(env.IP_RADAR_ALERT_URLS ?? "").split(/,\s*|\s+/).filter(Boolean);
  if (!urls.length)
    return { status: "skip", urls_n: 0, reason: "IP_RADAR_ALERT_URLS 未配置(降级跳过,轮仍成功;finding 通道同静音律)" };
  if (isDry)
    return { status: "dry_run", urls_n: urls.length, urls_redacted: urls.map(redactUrl), payload_head: `${title} / ${String(body).slice(0, 80)}` };
  try {
    await exec("apprise", ["--title", String(title), "--body", String(body), ...urls], { timeout: APPRISE_TIMEOUT_MS, maxBuffer: 1024 * 1024 });
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

// 每轮 gh 票(轮结果单;dry-run 面 cmd 留痕零外发)。
export async function openRoundIssue({ title, body, labels = ["ready-for-human"], dryRun, exec }) {
  const isDry = dryRun ?? String(process.env.EVOLVE_EXITS_DRY_RUN ?? "") === "1";
  const r = await ghIssueCreate({ title, body, labels }, { dryRun: isDry, exec });
  return r.ok
    ? { status: isDry ? "dry_run" : "created", labels, cmd_head: r.cmd.slice(0, 200), ...(r.issue_url ? { issue_url: r.issue_url } : {}) }
    : { status: "failed", labels, code: r.error.code, reason: String(r.error.reason).slice(0, 200) };
}
