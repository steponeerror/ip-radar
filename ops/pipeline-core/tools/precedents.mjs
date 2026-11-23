// tools/precedents.mjs — 判例检索单源(PR #177;判例 2026-10-24-discover-dual-channel-dead)。
// rg spawn argv 逐字对齐 python 参考实现;agent.mjs 宿主预注入同调 searchPrecedentsCore(单源)。
import fs from "node:fs";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import { B, DOCS_ROOT, execFileP } from "./shared.mjs";
import { envelope, classifyChannelError } from "./envelope.mjs";

// ── 判例检索单源(PR #177;判例 2026-10-24-discover-dual-channel-dead)────────────
// rg spawn argv 逐字对齐 backend/ipdb/_ops_store.rg_search_precedents(Python 参考实现,
// Python 面零改动):["rg","-i","-l","-g","*.md","-g","!_*",...每词 "-e",kw,dir]。
// 成功路径注入块与 lib.sh inject_precedents 逐字节等价(golden/inject-block.* 钉死;
// fmField 重实现 fm_block 拍平语义);失败面走 classifyChannelError 分类信封
// (rc=1 = 真零命中;rc≥2/ENOENT/超时 ≠ 零命中)。agent.mjs 宿主预注入同调本函数(单源);
// lib.sh inject_precedents 保留仅供 pipeline/steps.mjs(pipeline 面本批冻结不触;
// 两路输出 golden 字节等价由 selftest-t4 对拍钉死)。
export const RG_TIMEOUT_MS = 60_000; // _ops_store._RG_TIMEOUT_S 同值(两侧同签,勿单边改)

export function resolvePrecedentsDir(env = process.env) {
  // call-time 解析(契约表 PRECEDENTS_DIR phase=call-time;DOCS_ROOT 用模块顶 import-time 值兑底)
  return env.PRECEDENTS_DIR ?? path.join(env.DOCS_ROOT ?? DOCS_ROOT, "ops", "precedents");
}

// fmField — lib.sh fm_block 的 JS 逐语义重实现(frontmatter 顶层字段拍平摘要,非 YAML 解析)。
// 字节等价的隐藏细节(golden 钉死,以现行为准不顺手修正):
//   - key 行内联值记入,块标示符(> / |)起头不记:折叠字段首个续行拍平后带前导空格 →
//     「context:  」双空格是现行输出真形状;
//   - 字段块内任何非缩进行(含空行)= 块终止(awk exit 语义:单引号多行值 key 行后空行即截断);
//   - 续行/嵌套子键(reward 映射)两侧 [ \t] 裁剪后以单空格连接,空续行跳过。
export function fmField(text, field) {
  const lines = text.split("\n");
  if (lines[0] !== "---") return ""; // NR==1 非 ---:无 frontmatter
  let out = "", active = false;
  for (let i = 1; i < lines.length; i++) {
    const l = lines[i];
    if (/^---/.test(l)) break; // frontmatter 终线
    const m = l.match(/^([A-Za-z_][A-Za-z0-9_]*):/); // 顶层键(列 0;缩进子键不命中)
    if (m) {
      if (m[1] === field) {
        active = true;
        const rest = l.slice(m[0].length).replace(/^[ \t]+/, "").replace(/[ \t]+$/, "");
        if (rest !== "" && !/^[|>]/.test(rest)) out += (out === "" ? "" : " ") + rest;
      } else if (active) break; // 下一顶层键 = 本字段块结束
      continue;
    }
    if (active && /^[ \t]/.test(l)) {
      const line = l.replace(/^[ \t]+/, "").replace(/[ \t]+$/, "");
      if (line !== "") out += " " + line; // 首续行前导空格 = 双空格细节的来源
    } else if (active) break; // 非缩进行(含空行)= 字段块终止
  }
  return out;
}

// 返回 { block, files, trace }:block=注入块文本(逐字节等价 lib.sh;含尾换行);files=
// 排序去重命中路径(sort -u 语义;词法序——判例文件名全 ASCII 日期前缀,locale 无关);
// trace={cmd:真 argv,rc:真 rc}。失败抛 Error(.envelope={code,rc,reason} 分类信封 + .trace)。
export async function searchPrecedentsCore(keywords, { precedentsDir, env = process.env, timeoutMs = RG_TIMEOUT_MS } = {}) {
  const dir = path.resolve(precedentsDir ?? resolvePrecedentsDir(env));
  // execFile(file,args) 的 args 不含二进制名(Python subprocess 全 argv 含 "rg" ——两侧逻辑
  // argv 逐字对齐,此处拼接点不同);trace.cmd 展示含 rg 的完整逻辑 argv
  const args = ["-i", "-l", "-g", "*.md", "-g", "!_*"];
  for (const kw of keywords) args.push("-e", kw);
  args.push(dir);
  const cmd = ["rg", ...args].map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");
  let stdout = "";
  if (keywords.length) { // 零词守卫(lib.sh 同形:不跑 rg——rg 无 pattern 会 rc=2;Python 面由 ValueError 拒词,契约对拍不覆盖零词)
    try {
      ({ stdout } = await execFileP("rg", args, { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024, env }));
    } catch (e) {
      if (e.code === 1) stdout = String(e.stdout ?? ""); // rc=1 = 真零命中(Python 参考同语义;execFile 对非零退出 reject,此处置回成功面)
      else {
        const cls = classifyChannelError(e, "rg");
        throw Object.assign(new Error(cls.reason), { envelope: cls, trace: { cmd, rc: cls.rc } });
      }
    }
  }
  const files = [...new Set(stdout.split("\n").filter((l) => l !== ""))].sort();
  const kwsLine = keywords.join(" ");
  if (!files.length) {
    return { block: `### 注入判例(检索词: ${kwsLine})\n无判例(检索词: ${kwsLine})\n`, files, trace: { cmd, rc: 0 } };
  }
  const blockLines = [`### 注入判例(检索词: ${kwsLine})`];
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8"); // rg 输出行即路径(与 lib.sh fm_block "$f" 同读法)
    blockLines.push(`- ${path.basename(f)}`);
    for (const field of ["context", "human_ruling", "reward"]) blockLines.push(`  - ${field}: ${fmField(text, field)}`);
  }
  return { block: `${blockLines.join("\n")}\n`, files, trace: { cmd, rc: 0 } };
}

// ── 工具方法(实现零改动,经门面挂 ToolHost.prototype)─────────────────────
export const precedentsMethods = {
  searchPrecedents() {
    return {
      name: "search_precedents",
      label: "判例检索",
      description: "关键词词法检索(rg)判例库 docs/ops/precedents/(唯一跨轮记忆;无嵌入)。命中≤8 条(铁律⑦);零命中显式返回 none。包内引用判例只许引注入块或本工具命中的文件。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({
        keywords: Type.Array(Type.String({ minLength: 1, maxLength: 64 }), { minItems: 1, maxItems: 5 }),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), hits: Type.Array(Type.String()), hit_n: Type.Number(),
        truncated: Type.Boolean(), rg_rc: Type.Number(), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId, p) => {
        // PR #177 单源改造:原生 rg spawn(searchPrecedentsCore),失败面分类信封
        // (判例 2026-10-24-discover-dual-channel-dead:旧路径硬编码 trace rc:0 连失败
        // 路径也带、lib.sh 吞 stderr 2>/dev/null、ENOENT 塞字符串违反 Number 槽)。
        // 成功路径输出与旧 lib.sh 路径逐字节等价(golden 钉死);结构化字段只增不删。
        try {
          const { block, files, trace } = await searchPrecedentsCore(p.keywords);
          const all = files.map((f) => path.basename(f));
          const truncated = all.length > B.hitCap;
          const hits = all.slice(0, B.hitCap);
          hits.forEach((h) => this.searchHits.add(h));
          const st = { ok: true, hits, hit_n: hits.length, truncated, rg_rc: 0, trace };
          return this.finish(callId, "search_precedents", st,
            hits.length ? `${block.trim()}\n(命中 ${all.length} 条${truncated ? `,注入前 ${B.hitCap}(铁律⑦)` : ""})` : block.trim());
        } catch (e) {
          const env = envelope(e.envelope?.code ?? "rg_infra", e.envelope?.reason ?? e.message);
          return this.finish(callId, "search_precedents", { ...env, trace: e.trace ?? { cmd: "(未起跑)", rc: 1 } },
            `判例检索失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
};
