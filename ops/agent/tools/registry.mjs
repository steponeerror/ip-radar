// tools/registry.mjs — 工具面闭集/白名单单源(票 #195 C6 分层):MEASUREMENT_TOOLS
// (evidence 只认测量工具)/PREDICATES(REJECT 谓词闭集)/GH_WRITE_SUBCOMMANDS(gh 面
// 唯一写面闭集,票 #184)+ 读面白名单执法(checkReadablePath/DENY_*)+ 证据解析
// (resolveField)/判例引用闭合(closureCheck)/structuredContent 登记表(ResultRegistry)
// 与两个执法工具方法(read_file 白名单读 / queue_action 唯一写;经门面挂 ToolHost)。
import fs from "node:fs";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import { B, ROOT, DOCS_ROOT, ts, artifactPath } from "./shared.mjs";
import { envelope } from "./envelope.mjs";

export const PREDICATES = ["sunset_frozen", "mirror_echo", "zero_asset"]; // discover 谓词表闭集
export const MEASUREMENT_TOOLS = new Set(["fetch_url", "gh_search", "exclusive_probe", "matrix_scan_summary"]);
// 发现通道三件(web_read/web_search/rss_parse,PR3a)不进 MEASUREMENT_TOOLS:与测量工具的边界
// =数据形状天然隔离(发现线索非硬门数字),evidence 语义门不因发现通道放宽(DESIGN §6 2026-10-24 裁定)。
// ── gh 面子命令白名单(票 #184;spec #180 首批租户 Q6 授权写通道)──────────────────
// search=只读模型工具(ghSearch,每轮≤15);issue create=gh 面唯一写面,仅 finding 出口脚本步
// (pipeline/finding-exit.mjs)消费——模型工具面零新增写口(MEASUREMENT_TOOLS 不动,evidence
// 语义门不受污染);写面闭集扩张=spec 变更。标签缺省 needs-triage(triage-labels 五默认角色,人裁终局)。
export const GH_WRITE_SUBCOMMANDS = ["issue create"];
// ── 读面白名单(融合必保 4:显式拒 .env/密钥模式/.venv/data;门=实现双层之实现层)──
const DENY_NAME = [/\.env(\.|$)/i, /\.pem$/i, /\.p12$/i, /\.key$/i, /(^|[-_.])(priv|secret|credential)s?([-_.]|$)/i];
const DENY_SEG = [".git", ".venv", "node_modules", "backend/data"];
export function checkReadablePath(absPath) {
  // 不存在的路径不 realpath(ENOENT 会抢在拒读判定前炸):词法归一化即可支撑白名单/拒读判定
  const real = fs.existsSync(absPath) ? fs.realpathSync(absPath) : path.resolve(absPath);
  const rootOf = (r) => (fs.existsSync(r) ? fs.realpathSync(r) : path.resolve(r));
  const roots = [rootOf(ROOT), rootOf(DOCS_ROOT)];
  if (!roots.some((r) => real === r || real.startsWith(r + path.sep))) {
    throw new Error(`路径越界(白名单=仓根+docs 根):${absPath}`);
  }
  const rel = path.relative(ROOT, real);
  if (DENY_SEG.some((s) => rel.split(path.sep).includes(s) || rel.includes(s + path.sep))) {
    throw new Error(`路径禁读(${DENY_SEG.join("/")}):${absPath}`);
  }
  const base = path.basename(real).toLowerCase();
  if (DENY_NAME.some((re) => re.test(base))) throw new Error(`疑似密钥/凭证文件拒读(.env/密钥模式):${absPath}`);
  return real;
}

// evidence 字段点路径解析:"results.0.size_kb" / "results[0].size_kb" → 嵌套取值;无命中 undefined。
// 导出供金轨迹 runner 复用同一解析语义(T6,避免断言侧另起炉灶)。
export function resolveField(obj, field) {
  const parts = String(field).replace(/\[(\d+)\]/g, ".$1").split(".");
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object" || !(p in cur)) return undefined;
    cur = cur[p];
  }
  return cur;
}

// ── 判例引用闭合校验(铁律④:路径 ∈ 预注入 ∪ 本会话检索命中;存在性不够)────────
export function closureCheck(pkgText, allowed /* Set<string> 文件名 */) {
  const lines = pkgText.split("\n");
  const sec = []; let inSec = false;
  for (const l of lines) {
    if (/^#+\s.*注入判例/.test(l)) { inSec = true; continue; }
    if (inSec && /^#+\s/.test(l)) break;
    if (inSec) sec.push(l);
  }
  if (!sec.length) throw new Error("闭合校验:包缺少「注入判例」节");
  const toks = [...new Set(sec.flatMap((l) => (l.match(/[A-Za-z0-9_\-./]+\.md/g) ?? []).map((t) => path.basename(t))))];
  if (!toks.length) {
    if (sec.some((l) => l.includes("无判例"))) return { cited: 0 };
    throw new Error("闭合校验:注入判例节既无路径也无「无判例」");
  }
  const bad = toks.filter((t) => !allowed.has(t));
  if (bad.length) throw new Error(`闭合校验:判例路径不在(预注入∪本会话检索命中)闭集:${bad.join(", ")}(防真实文件假引用)`);
  return { cited: toks.length };
}
// ── 本会话 structuredContent 登记 + 写前语义门(铁律①)────────────────────────
export class ResultRegistry {
  constructor() { this.byCall = new Map(); }
  register(callId, toolName, sc) { this.byCall.set(callId, { tool: toolName, sc }); }
  get(callId) { return this.byCall.get(callId); }
}

// ── 执法工具方法(实现零改动,经门面 Object.assign 挂 ToolHost.prototype)────
export const registryMethods = {
  readFile() {
    return {
      name: "read_file",
      label: "白名单读文件",
      description: "只读。白名单=本仓根+docs 根;拒 .env/密钥模式/.venv/backend-data/node_modules。≤50KB/2000 行,支持 pattern 过滤(grep -E 语义)与 offset/limit。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({
        path: Type.String({ minLength: 1, maxLength: 512 }),
        pattern: Type.Optional(Type.String({ maxLength: 128, description: "正则过滤,仅保留命中行" })),
        offset: Type.Optional(Type.Number({ minimum: 1, maximum: 100000 })),
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 2000 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), path: Type.String(), lines_n: Type.Number(),
        bytes_n: Type.Number(), truncated: Type.Boolean(), content: Type.String(),
      }),
      execute: async (callId, p) => {
        let real;
        try {
          real = checkReadablePath(path.resolve(p.path));
          const stat = fs.statSync(real);
          if (!stat.isFile()) throw Object.assign(new Error("不是普通文件"), { code: "denied" });
          const truncatedBytes = stat.size > B.readBytes;
          const text = fs.readFileSync(real, "utf8").slice(0, B.readBytes);
          let lines = text.split("\n");
          if (p.pattern) {
            let re; try { re = new RegExp(p.pattern); } catch { throw Object.assign(new Error("pattern 非法正则"), { code: "bad_pattern" }); }
            lines = lines.filter((l) => re.test(l));
          }
          const off = (p.offset ?? 1) - 1;
          const lim = p.limit ?? B.readLines;
          const sliced = lines.slice(off, off + lim);
          const st = {
            ok: true, path: real, lines_n: sliced.length, bytes_n: stat.size,
            truncated: truncatedBytes || off + lim < lines.length, content: sliced.join("\n"),
          };
          return this.finish(callId, "read_file", st, sliced.join("\n") || "(空)");
        } catch (e) {
          const env = envelope(e.code === "denied" || /白名单|禁读|密钥/.test(e.message) ? "denied" : (e.code ?? "io_error"), e.message);
          return this.finish(callId, "read_file", { ...env, path: p.path }, `读文件失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
  queueAction() {
    return {
      name: "queue_action",
      label: "动作入队(唯一写)",
      description: "唯一写工具:把 ENQUEUE(自动入队,须本会话 exclusive_probe 实测 rate≥0.25 且对照闸过)/REJECT(谓词闭集 sunset_frozen|mirror_echo|zero_asset,写前语义门从 structuredContent 重算谓词)追加到 docs/ops/queue.md。append-only、幂等去重、恒可否决(veto_cmd);rationale 只落工件包不进行列。evidence[]={call_id,field,value} 必须逐字对应本会话测量工具的结构化返回。",
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      parameters: Type.Object({
        source: Type.String({ pattern: "^[a-z0-9_]{1,32}$" }),
        action: Type.Union([Type.Literal("ENQUEUE"), Type.Literal("REJECT")]),
        predicate: Type.Optional(Type.Union([Type.Literal("sunset_frozen"), Type.Literal("mirror_echo"), Type.Literal("zero_asset")])),
        rationale: Type.String({ minLength: 1, maxLength: 2000 }),
        evidence: Type.Array(Type.Object({
          call_id: Type.String({ minLength: 1 }),
          field: Type.String({ minLength: 1 }),
          value: Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Null()]),
        }), { minItems: 1, maxItems: 16 }),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), appended: Type.Boolean(), dedup: Type.Boolean(),
        action: Type.String(), source: Type.String(), vetoable: Type.Boolean(), veto_cmd: Type.String(),
      }),
      execute: async (callId, p) => {
        // 预算计数走真实路径:queue_action 不经 finish()(非测量工具,不进登记表),
        // 若不在此计数 spent 永不增长、10/轮上限永不触发(评审 Important-1,2026-10-19)
        this.budgetSpend("queue_action");
        // 幂等去重:同 action+source 已在队列 → 返回既有事实,不双写
        let existing = "";
        try { existing = fs.readFileSync(this.queueFile, "utf8"); } catch { /* 首建 */ }
        const dedupRe = new RegExp(`\\| \\d{4}-\\d{2}-\\d{2} \\| [^|]+ \\| ${p.action} \\| ${p.source} \\|`);
        const dedup = dedupRe.test(existing);
        let lineN = existing ? existing.trimEnd().split("\n").length : 0;
        const rel = path.relative(ROOT, this.queueFile);
        const vetoCmd = `sed -i '/| ${p.action} | ${p.source} |/d' ${rel}`;
        if (!dedup) {
          if (!existing) {
            fs.mkdirSync(path.dirname(this.queueFile), { recursive: true });
            fs.writeFileSync(this.queueFile,
              "# 源生命周期动作队列(queue_action 唯一写口;行由 host 模板渲染,rationale 只落工件)\n\n"
              + "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n|---|---|---|---|---|---|---|\n");
            lineN = 4;
          }
          const ev = p.evidence.map((e) => `${e.call_id}:${e.field}=${JSON.stringify(e.value)}`).join(";");
          const row = `| ${new Date().toISOString().slice(0, 10)} | ${this.round} | ${p.action} | ${p.source} | ${p.predicate ?? "—"} | ${ev} | 是(否决=删除本行) |`;
          fs.appendFileSync(this.queueFile, `${row}\n`);
          lineN += 1;
          const rpath = artifactPath(this.artifactDir, "queue-rationale", "md");
          fs.appendFileSync(rpath, `## ${ts()} ${p.action} ${p.source}\n- predicate: ${p.predicate ?? "(无)"}\n- evidence: ${JSON.stringify(p.evidence)}\n- rationale(模型原话,仅人裁阅读,不进队列行):\n\n${p.rationale}\n\n`);
          this.artifacts.push(rpath);
        }
        const st = {
          ok: true, appended: !dedup, dedup, action: p.action, source: p.source,
          predicate: p.predicate ?? null, vetoable: true, veto_cmd: vetoCmd, queue_file: rel,
        };
        this.queueWrites.push(st);
        const c = `${p.action} ${p.source}${dedup ? "(已在队列,幂等去重,未双写)" : " 已入队"};恒可否决:veto_cmd = \`${vetoCmd}\`;rationale 已落工件(包脚注)。`;
        return { content: [{ type: "text", text: c }], details: {}, structuredContent: st };
      },
    };
  },
};
