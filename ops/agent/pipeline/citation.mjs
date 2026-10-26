// citation.mjs — #208 T2:span 级逐字回引(发现轮)。
// 定位:纯函数面,零 IO/零模型/零网络。三律:
//  ① 逐字律:quote 必须是证据面的原样子串(不 trim/不规范化/不改写);
//  ② URL 边界律(判例自铸,spec T2 三负例):quote 里的 URL 形 token 须在证据面以
//    「定界整 token」在场——前缀子串(https://ip.thc vs 面内 https://ip.thc.org)与
//    超集串皆非在场(半真 URL ≠ 在场);定界=URL 合法字符集两侧不续(逗/分号按散文截断,
//    与 token 提取停集同源);
//  ③ 面入工件律:证据面取自轮工件(d1-scan 快照),不读活仓文件——回放可回算
//    (G_VERIFY 快照判例同源)。
// 与 T3 discover-candidate.mjs containsExactString 的分工:彼为「指针所指值逐字在
// 工件集合在场」(深度值等价);此为「quote 文本在单证据面逐字 span」——两律同源
// (皆零规范化),作用面不同。

import { evidencePtrForm, resolveEvidencePtr } from "./discover-candidate.mjs"; // 形律/指针解析=T3 导出面复用(单源);containsExactString 未导出→此处同律复刻
import { ARTIFACTS } from "../artifacts.mjs";

// 指针形分类(#208 T2 统一律):T3 两形(url/artifact)优先;其 null 再验透传形(scan)——
// 输入候选原样回传的 repo 相对路径/行锚(NEEDS.md:L14、backend/ipdb/_sources/x.py)。
// T3 discover-candidate.mjs 的两形闭集不动(2026-10-26 #208 处置裁定:彼=独立候选面必填律,
// 此=发现轮回引面透传律);透传形在 T3 侧归 null 形,在此归 scan——两闭集分立非冲突。
const SCAN_PTR_RE = /^[A-Za-z0-9_][A-Za-z0-9_.\/-]*(?::L\d+)?$/; // 无空白/无 #(否则前两形已收);可带 :L<行号> 行锚尾
function ptrForm(ptr) {
  const f = evidencePtrForm(ptr);
  if (f) return f;
  if (typeof ptr === "string" && SCAN_PTR_RE.test(ptr)) return "scan";
  return null;
}

const URL_TOKEN_RE = /https?:\/\/[^\s"'<>()[\]{},;]+/g; // token 停集=空白/引号/括类/中西逗分号
const URL_CHAR = /[A-Za-z0-9._~:/?#\[\]@!$&'()*+=%-]/; // RFC3986 保留+未保留;逗/分号除外(散文定界)

// containsExactString:与 T3 discover-candidate.mjs 私有同名函数同律复刻(深度逐字值搜,
// 零规范化/零前缀匹配——幽灵 URL 判例:半真 URL 不算在场)。T3 侧私有未导出(2026-10-26
// #208 处置裁定:T3 文件不动,同律单源锚定此处)。
function containsExactString(v, s) {
  if (v === s) return true;
  if (Array.isArray(v)) return v.some((x) => containsExactString(x, s));
  if (v && typeof v === "object") return Object.values(v).some((x) => containsExactString(x, s));
  return false;
}

// URL token 在证据面是否「定界在场」(任一次出现两侧皆非 URL 续字符)
function urlDelimited(hay, tok) {
  let i = hay.indexOf(tok);
  while (i !== -1) {
    const before = i === 0 ? "" : hay[i - 1];
    const after = hay[i + tok.length] ?? "";
    if (!URL_CHAR.test(before) && !URL_CHAR.test(after)) return true;
    i = hay.indexOf(tok, i + 1);
  }
  return false;
}

// spanMatcher(quote, evidenceText) → bool:quote 是否为证据面的合法回引。
// 拒:幽灵 URL / 半真 URL(前缀子串、超集)/ 大小写或标点改写 / 非串或空 quote。
export function spanMatcher(quote, evidenceText) {
  if (typeof quote !== "string" || quote.length === 0 || typeof evidenceText !== "string") return false;
  if (!evidenceText.includes(quote)) return false; // 逐字律(第一律:includes 是必要条件)
  const toks = quote.match(URL_TOKEN_RE) ?? [];
  for (const tok of toks) if (!urlDelimited(evidenceText, tok)) return false; // URL 边界律(第二律)
  return true;
}

// canonicalJson:键序稳定序列化(容器面=text 键缺省时的确定性证据面;SCAN 确定性判例同源)
export function canonicalJson(v) {
  if (v === null || typeof v !== "object") return JSON.stringify(v) ?? "null";
  if (Array.isArray(v)) return "[" + v.map(canonicalJson).join(",") + "]";
  const keys = Object.keys(v).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(v[k])).join(",") + "}";
}

// entryFace(scan 条目)→ 证据面文本:needs/web 条目带 text(原文行快照)优先;
// 缺省=条目 canonicalJson(结构性面,registry 面=此形)。
function entryFace(entry) {
  if (typeof entry?.text === "string" && entry.text.length > 0) return entry.text;
  return canonicalJson(entry);
}

// scanEvidenceFace(scan, ptr) → {ok:true,text,entry} | {ok:false,reason}
// 三形指针(T2 #208 统一律,prompt 透传契约同源):
//  ① 透传形(scan 形,如 NEEDS.md:L14 / backend/ipdb/_sources/x.py):条目 evidence_ptr
//     逐字等于 ptr → 该条目面;
//  ② 工件形(d1-scan.json#/candidates/N):工件名必须=d1-scan,walkPointer 后取所指值
//     (值=串则原样,容器则条目面/canonicalJson);
//  ③ URL 形:URL 须在宇宙某条目逐字在场(T3 containsExactString 同律)→ 该条目面。
export function scanEvidenceFace(scan, ptr) {
  if (!scan || !Array.isArray(scan.candidates)) return { ok: false, reason: "d1-scan 候选宇宙不可读" };
  if (typeof ptr !== "string" || ptr.length === 0) return { ok: false, reason: "指针为空" };
  const form = ptrForm(ptr);
  if (form === "scan") {
    const entry = scan.candidates.find((c) => c && c.evidence_ptr === ptr);
    if (!entry) return { ok: false, reason: `透传指针 ${ptr} 不在 d1-scan 候选宇宙(幽灵指针)` };
    return { ok: true, text: entryFace(entry), entry };
  }
  if (form === "artifact") {
    const file = ptr.split("#")[0];
    if (file !== ARTIFACTS.DISCOVER_SCAN) return { ok: false, reason: `工件形指针须指 ${ARTIFACTS.DISCOVER_SCAN}(得 ${file})` };
    const r = resolveEvidencePtr(ptr, { [ARTIFACTS.DISCOVER_SCAN]: scan });
    if (!r.ok) return { ok: false, reason: `指针解析失败:${r.reason}` };
    if (typeof r.value === "string" && r.value.length > 0) return { ok: true, text: r.value, entry: null };
    const entry = scan.candidates.find((c) => canonicalJson(c) === canonicalJson(r.value));
    return { ok: true, text: entry ? entryFace(entry) : canonicalJson(r.value), entry: entry ?? null };
  }
  if (form === "url") {
    const entry = scan.candidates.find((c) => containsExactString(c, ptr));
    if (!entry) return { ok: false, reason: `URL ${ptr} 未在 d1-scan 候选宇宙逐字在场(幽灵 URL)` };
    return { ok: true, text: entryFace(entry), entry };
  }
  return { ok: false, reason: `指针三形外:${ptr}` };
}
