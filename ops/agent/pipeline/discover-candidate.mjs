// pipeline/discover-candidate.mjs — 发现轮结构化候选面(票 #209/T3,ADR 0010;spec
// /tmp/discover-pipeline-spec.md T3 节)。三件:①candidate 形状校验(zod-free 手写
// 校验器——仓律零新 npm 依赖;SHORTLIST 模型产出的结构化候选必须过形才进下游)
// ②证据存在性校验(evidence_ptr 指向的工件键/URL 必须在给定工件集合真在场,缺=
// 候选丢弃+留痕清单——哲学③宁少算:证据不在场的候选不修不猜,只丢并留痕)
// ③候选卡行写入器(queue.md 三写口之一:action=PROPOSE 候选卡行,走 #139 flock
// 路径 appendQueueRowLocked;表头首行句 #217 T3.5 已翻正三写口如实描述——
// 「queue_action 唯一写口」旧句随本写口+ENQUEUE 候选行两新写口退役;
// #0006 人裁交互律不动——只写不动作,开票/接源全人裁)。
// 消费方:T1(发现轮管线骨架,并行工位)SHORTLIST/ENQUEUE 步;接线协议见 worktree
// 根 DP-T3-REPORT.md。本文件零仓依赖(queue-lock 是 tools/ 自含零 node_modules 面)。
import { createHash } from "node:crypto";
import { appendQueueRowLocked } from "../tools/queue-lock.mjs";

// 候选字段闭集(spec T3 节钉死的七键;未知键=拒——模型输出漂移要在形状层响,不静默吞)
export const CANDIDATE_FIELDS = Object.freeze(
  ["name", "url", "source_channel", "quote", "evidence_ptr", "exclusivity_estimate", "notes"]);
// 来源渠道闭集=SCAN 三来源(spec T1 节:源注册表现状/NEEDS.md 缺口行/外部目录面)。
// 协议面:与 T1 d1-scan.json 条目的来源渠道字段同闭集——T1/T3 合流时若 SCAN 扩来源,
// 此闭集与 T1 侧同批扩(单源裁决留合流批,此处先钉三员)。
export const SOURCE_CHANNELS = Object.freeze(["registry", "needs", "web"]);
// 长度帽(表格/工件面防失控;与工具面 url maxLength=500 同量级)
export const CANDIDATE_MAX = Object.freeze({ name: 200, url: 500, quote: 1000, notes: 2000, evidence_ptr: 600 });

// evidence_ptr 两形(spec T3:指向工件键/URL):
//   artifact 形:<工件名>#<json指针> —— 工件名=裸文件名(无路径分隔),指针 / 起步、
//     逐段走对象键/数组下标(RFC6901-lite,~0/~1 转义支持);不收空指针(整工件指认
//     无法对账到具体证据条目——宁少算)。
//   url 形:http(s) URL —— 必须在给定工件集合里逐字在场(防幽灵 URL;span 级语义
//     面在 T2 spanMatcher,T3 只管「在场」存在性)。
const URL_RE = /^https?:\/\/\S+$/;
const ARTIFACT_PTR_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*#\/.*$/;
export function evidencePtrForm(ptr) {
  if (typeof ptr !== "string" || ptr.length > CANDIDATE_MAX.evidence_ptr) return null;
  if (URL_RE.test(ptr)) return "url";
  if (ARTIFACT_PTR_RE.test(ptr)) return "artifact";
  return null;
}

// 手写校验器(零依赖;返回 {ok:true,candidate} | {ok:false,code:"shape",reason})。
// notes 可缺省(备注非证据);其余六键必填。错型/缺键/闭集外/未知键=拒,reason 点名。
export function validateCandidate(c) {
  const no = (reason) => ({ ok: false, code: "shape", reason });
  if (c == null || typeof c !== "object" || Array.isArray(c)) return no("candidate 必须是非数组对象");
  const unknown = Object.keys(c).filter((k) => !CANDIDATE_FIELDS.includes(k));
  if (unknown.length) return no(`未知键 ${unknown.join(",")}(闭集:${CANDIDATE_FIELDS.join("/")})`);
  for (const k of ["name", "url", "source_channel", "quote", "evidence_ptr"]) {
    if (typeof c[k] !== "string" || !c[k].trim()) return no(`${k} 缺失或非非空字符串`);
  }
  if (c.name.length > CANDIDATE_MAX.name) return no(`name 超 ${CANDIDATE_MAX.name} 字`);
  if (!URL_RE.test(c.url) || c.url.length > CANDIDATE_MAX.url) return no(`url 须 http(s) 形且 ≤${CANDIDATE_MAX.url} 字`);
  if (!SOURCE_CHANNELS.includes(c.source_channel))
    return no(`source_channel 必须在闭集内:${SOURCE_CHANNELS.join("/")}`);
  if (c.quote.length > CANDIDATE_MAX.quote) return no(`quote 超 ${CANDIDATE_MAX.quote} 字(span 级回引面=T2)`);
  if (!evidencePtrForm(c.evidence_ptr))
    return no("evidence_ptr 须两形之一:<工件名>#</json指针> 或 http(s) URL");
  const ex = c.exclusivity_estimate;
  if (typeof ex !== "number" || !Number.isFinite(ex) || ex < 0 || ex > 1)
    return no("exclusivity_estimate 须为 [0,1] 数(入队硬门 ≥0.25 的裁决在 T1 ENQUEUE,不在此)");
  if (c.notes !== undefined && (typeof c.notes !== "string" || c.notes.length > CANDIDATE_MAX.notes))
    return no(`notes 须字符串且 ≤${CANDIDATE_MAX.notes} 字(可缺省)`);
  return { ok: true, candidate: c };
}

// 批面:形状分拣(valid 进下游,dropped 留痕——与证据存在性同律:只丢不修)。
export function validateCandidates(list) {
  const valid = [], dropped = [];
  (Array.isArray(list) ? list : []).forEach((c, i) => {
    const r = validateCandidate(c);
    if (r.ok) valid.push(c);
    else dropped.push({ index: i, name: c?.name ?? null, url: c?.url ?? null, reason: r.reason });
  });
  return { valid, dropped };
}

// ── 证据存在性(纯函数)──────────────────────────────────────────────────
// artifacts: { <工件名>: 已解析 JSON } —— 调用方(T1)从工件树读入后传入;本函数
// 零 IO(回放可算)。
function walkPointer(doc, ptr) {
  let cur = doc;
  if (ptr === "") return { ok: true, value: cur };
  for (const raw of ptr.slice(1).split("/")) {
    const seg = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (cur == null || typeof cur !== "object") return { ok: false, reason: `指针段 «${seg}» 前已非容器` };
    if (Array.isArray(cur)) {
      if (!/^\d+$/.test(seg) || Number(seg) >= cur.length) return { ok: false, reason: `数组下标 «${seg}» 不在场` };
      cur = cur[Number(seg)];
    } else {
      if (!Object.prototype.hasOwnProperty.call(cur, seg)) return { ok: false, reason: `键 «${seg}» 不在场` };
      cur = cur[seg];
    }
  }
  return { ok: true, value: cur };
}
function containsExactString(v, s) { // 深度逐字值搜(不做规范化/前缀匹配——幽灵 URL 判例:半真 URL 不算在场)
  if (v === s) return true;
  if (Array.isArray(v)) return v.some((x) => containsExactString(x, s));
  if (v && typeof v === "object") return Object.values(v).some((x) => containsExactString(x, s));
  return false;
}
export function resolveEvidencePtr(ptr, artifacts) {
  const form = evidencePtrForm(ptr);
  if (!form) return { ok: false, reason: "evidence_ptr 形状坏(须 <工件名>#</指针> 或 http(s) URL)" };
  if (form === "url") {
    const hit = Object.keys(artifacts ?? {}).some((f) => containsExactString(artifacts[f], ptr));
    return hit ? { ok: true } : { ok: false, reason: `URL 未在给定工件集合逐字在场:${ptr}` };
  }
  const h = ptr.indexOf("#");
  const file = ptr.slice(0, h), rest = ptr.slice(h + 1);
  if (!Object.prototype.hasOwnProperty.call(artifacts ?? {}, file))
    return { ok: false, reason: `工件不在集合:${file}` };
  const w = walkPointer(artifacts[file], rest);
  return w.ok ? { ok: true, value: w.value } : { ok: false, reason: `${file} 内指针 ${rest} 不在场:${w.reason}` };
}
// 证据存在性过滤:缺=丢+留痕(dropped 行带 index/name/url/evidence_ptr/reason,
// 供 T1 ENQUEUE 工件与 G_ENQUEUE 对账面消费——证据永不灭失)。
export function filterCandidatesByEvidence(candidates, artifacts) {
  const kept = [], dropped = [];
  (Array.isArray(candidates) ? candidates : []).forEach((c, i) => {
    const r = resolveEvidencePtr(c?.evidence_ptr, artifacts);
    if (r.ok) kept.push(c);
    else dropped.push({ index: i, name: c?.name ?? null, url: c?.url ?? null,
      evidence_ptr: c?.evidence_ptr ?? null, reason: r.reason });
  });
  return { kept, dropped };
}

// ── 候选卡行(ENQUEUE 面行形制)───────────────────────────────────────────
// action=PROPOSE(spec T3 钉「status=proposal」):与 queue_action 工具的 ENQUEUE/REJECT
// 闭集分立——那两词是运营轮已测量源的动作词(其语义门独占 exclusive_probe 实测);
// 候选卡=发现轮 pre-验证提案(排他率是预估非实测)。#0006 人裁交互律:只写不动作,
// 人裁否决=删行(veto_cmd 同形)。queue.md 冻结表头不动;表头注释「queue_action 唯一
// 写口」措辞自本写入器起过时——表头是跨语言双源冻结形状(#139 哨对拍),改词须
// python 侧同批;留 T4/合流批裁决(见 DP-T3-REPORT.md 余项)。
export const CANDIDATE_ACTION = "PROPOSE";

// source 列(slug):host slug + url md5 前 6 位。判重键=action+source(appendQueueRowCore
// 冻结语义)→ 同候选跨轮幂等(重提案=dedup 跳过),同 host 异 url 候选不互撞。
export function candidateSourceSlug(url) {
  let host = "";
  try { host = new URL(url).hostname; } catch { /* 形状面已拦,兜底哈希支住唯一性 */ }
  const slug = host.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 20) || "site";
  const hash = createHash("md5").update(String(url)).digest("hex").slice(0, 6);
  return `${slug}_${hash}`;
}
// 卡行 evidence 面=指针卡字段(全文候选+quote 在 shortlist 工件;行=人裁索引,不重复
// 全文——宁少算)。call_id 命名空间 "candidate":候选卡的证据是工件指针不是本会话
// 测量调用,evidence_ptr 即指针。
export function candidateCardEvidence(candidate) {
  return ["name", "url", "source_channel", "exclusivity_estimate", "evidence_ptr"]
    .map((f) => ({ call_id: "candidate", field: f, value: candidate[f] }));
}
// 写入器:先形状校验(坏候选=零写,宁少算),后走 #139 flock 路径(与 python
// append_queue 同锁域互斥);幂等由 appendQueueRowCore 判重面收口。
export async function appendCandidateCard(candidate, { round, queueFile } = {}) {
  if (!round || typeof round !== "string") return { ok: false, code: "shape", reason: "round 缺失(发现轮 round-id)" };
  if (!queueFile || typeof queueFile !== "string") return { ok: false, code: "shape", reason: "queueFile 缺失" };
  const v = validateCandidate(candidate);
  if (!v.ok) return { ok: false, code: "shape", reason: `候选卡拒写(形状):${v.reason}` };
  return appendQueueRowLocked({
    queueFile,
    action: CANDIDATE_ACTION,
    source: candidateSourceSlug(candidate.url),
    round,
    evidence: candidateCardEvidence(candidate),
  });
}
