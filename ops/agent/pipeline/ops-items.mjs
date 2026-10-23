// pipeline/ops-items.mjs — 条目库桥(P4,票 #166):_ops_items 树的 Node 侧落笔面。
// 语义镜像 backend/ipdb/_ops_items.py create_item(同树同形同幂等;纪律=只碰 ops/agent,
// 不改 backend):同 dedup_key 在飞(active|snoozed)→ 零写返回既有条目;同 key 终态
// (done|dismissed)→ 复开新条目 supersedes 链指最近旧条(mtime 最大者,review Finding 1
// 同律),原条目永不删;文件名内容寻址 sha1[:10](含 supersedes 目标,同日连环复开不撞名)。
// 回声防线(#166):evidence.round_id === 本轮 replay_of 的在飞条目 = 原轮自己的产物,
// echo 回原 outcome 零写(replay 确定性:审计重放不改生产条目面;ITEMIZE 半程崩溃重放
// 由 manifest 缺席时走同一路径救回部分写入)。
// YAML 面:渲染=受控子集(全串双引号 JSON 转义/裸键/两空格缩进),解析=行扫(顶层键 +
// dedup_key/evidence 子键),PyYAML safe_load 可往返读回(树与 backend 共享,写字形以
// Python 读得回为验收面;自家解析只取 status/dedup_key/supersedes/evidence.round_id)。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

// ── 旗标 → 条目签查表(与 P1 探测器同空间;#164 偏离②收口)────────────────────
// probe_class/error_signature 词表 = _ops_detectors.py 产条粒度:download(下载失败族)/
// staleness(新鲜度族)。健康轮旗标映射:
//   unreachable → download 族,error_signature = 折叠族映射(下方 foldErrorFamily,
//     #164 偏离①钉死:lib.sh _ff_probe 第 4 列=精确码族 http_<code>/net_timeout/net_fail
//     (#166 审 P2-1:curl 超时 rc=28 分腿对齐探测器 timeout 族),
//     _ops_detectors._error_family 条目侧=401/403 单列、其余 4xx 折叠 http_4xx、
//     5xx→http_5xx、超时→timeout、传输层败→network、认不出→download 兜底;
//     两侧同因同签(含超时腿),在飞不双开);
//   frozen → staleness 族,error_signature="age_gt_2x_refresh"(run_staleness_detector
//     同键:冻结 = HEAD age_days ≥ 180 > 2× 任何刷新周期(stale_days ≤30 → 周期 ≤720h),
//     源新鲜度同因,P1 已产条在飞则健康轮不重开)。
export const CAUSE_GROUP_BY_BUCKET = { frozen: "staleness", unreachable: "download_failure" }; // 对齐 _ops_detectors.CAUSE_GROUPS 词表
export function foldErrorFamily(fam) {
  if (fam === "http_401" || fam === "http_403") return fam; // 匿名撞鉴权墙单列(_error_family 同口径)
  if (/^http_4\d\d$/.test(fam ?? "")) return "http_4xx"; // 折叠族(404/429 等同族:同族失败同因去重)
  if (/^http_5\d\d$/.test(fam ?? "")) return "http_5xx";
  if (fam === "net_fail") return "network"; // 传输层败 → network 族(DNS/连接,拼写对齐)
  if (fam === "net_timeout") return "timeout"; // curl 超时(rc=28,lib.sh #166 审 P2-1 分腿)→ timeout;对拍=_ops_detectors._error_family 超时文本同归 timeout——同因超时两侧同签,在飞不双开对超时类生效
  return "download"; // 兜底族(=_ops_detectors._FALLBACK_FAMILY;缺第 4 列/认不出)
}
export function itemSignature(flag) { // 旗标 → (probe_class, error_signature) 查表,零模型
  if (flag?.bucket === "unreachable") return { probe_class: "download", error_signature: foldErrorFamily(flag.error_family) };
  if (flag?.bucket === "frozen") return { probe_class: "staleness", error_signature: "age_gt_2x_refresh" };
  throw Object.assign(new Error(`旗标 bucket 闭集外:${flag?.bucket}(旗标面=frozen|unreachable)`), { code: "infra" });
}
export const fullDedupKey = (flag) => { const s = itemSignature(flag); return `${flag.source}|${s.probe_class}|${s.error_signature}`; };

// ── 受控 YAML 子集:渲染/解析 ───────────────────────────────────────────────
const yamlScalar = (v) => typeof v === "string" ? JSON.stringify(v) : String(v); // 双引号串=YAML 合法形(PyYAML 往返)
function yamlBlock(v, indent) {
  const pad = " ".repeat(indent);
  if (v === null || v === undefined || typeof v !== "object") return yamlScalar(v ?? null);
  if (Array.isArray(v)) {
    if (!v.length) return "[]";
    return v.map((x) => x !== null && typeof x === "object" && !Array.isArray(x)
      ? Object.entries(x).map(([k, val], i) => `${i === 0 ? `${pad}- ` : " ".repeat(indent + 2)}${k}: ${yamlScalar(val)}`).join("\n") // 列表项字典:首键随 - 缩进 +2
      : `${pad}- ${yamlScalar(x)}`).join("\n");
  }
  const lines = [];
  for (const [k, val] of Object.entries(v)) {
    if (val !== null && typeof val === "object") {
      const empty = Array.isArray(val) ? !val.length : !Object.keys(val).length;
      lines.push(empty ? `${pad}${k}: ${Array.isArray(val) ? "[]" : "{}"}` : `${pad}${k}:\n${yamlBlock(val, indent + 2)}`);
    } else lines.push(`${pad}${k}: ${yamlScalar(val)}`);
  }
  return lines.join("\n");
}
// 十字段冻结序 = _ops_items.ITEM_FIELDS(sort_keys=False 插入序同形);supersedes 复开才携带
const ITEM_FIELD_ORDER = ["id", "action", "args", "evidence", "impact", "rollback", "dedup_key", "severity", "cause_group", "status"];
export function renderItem(fm, summary) {
  const ordered = {};
  for (const k of ITEM_FIELD_ORDER) ordered[k] = fm[k];
  if (fm.supersedes !== undefined && fm.supersedes !== null) ordered.supersedes = fm.supersedes;
  return `---\n${yamlBlock(ordered, 0)}\n---\n\n${summary}`;
}
// 行扫解析(受控面:顶层标量键 + 一层子块键;自家写入全双引号,backend 写入裸串同收)
const parseScalar = (s) => { const t = s.trim(); if (t.startsWith('"')) { try { return JSON.parse(t); } catch { return t; } }
  if (t === "true") return true; if (t === "false") return false; if (t === "null") return null;
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t); return t; };
export function parseItem(text, name) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!m) throw Object.assign(new Error(`条目 frontmatter 缺:${name}(_ops_items 十字段冻结面)`), { code: "infra" });
  const fm = {}; const sub = {}; let cur = null;
  for (const line of m[1].split("\n")) {
    const top = line.match(/^([a-z_]+):(.*)$/);
    if (top && !line.startsWith(" ")) { fm[top[1]] = parseScalar(top[2]); cur = top[1] === "dedup_key" || top[1] === "evidence" ? top[1] : null; continue; }
    const kv = line.match(/^  ([a-z_]+):(.*)$/);
    if (kv && cur) sub[cur] = { ...(sub[cur] ?? {}), [kv[1]]: parseScalar(kv[2]) }; // 深缩进续行(块串)不命中,自然跳过
  }
  if (!fm.status || !(sub.dedup_key ?? {}).source)
    throw Object.assign(new Error(`条目 status/dedup_key.source 缺:${name}`), { code: "infra" }); // 宁响亮不猜测(_ops_items._parse_item 同口径)
  return { id: fm.id ?? name.replace(/\.md$/, ""), status: fm.status, supersedes: fm.supersedes ?? null,
    round_id: (sub.evidence ?? {}).round_id ?? null, dedup_key: sub.dedup_key };
}
export function parseItemsTree(itemsDir) { // 全树扫描(坏文件=infra,不让幂等判读跑在不可信数据上)
  if (!fs.existsSync(itemsDir)) return [];
  return fs.readdirSync(itemsDir).filter((f) => f.endsWith(".md")).sort().reverse() // 倒序=确定性遍历(Python 同款)
    .map((f) => { const p = path.join(itemsDir, f); return { file: f, mtimeMs: fs.statSync(p).mtimeMs, ...parseItem(fs.readFileSync(p, "utf8"), f) }; });
}

// ── 写前校验(镜像 _ops_items.validate_item_entry 的 JS 面;写什么校什么)────────
const SOURCE_RE = /^[a-z0-9_]{1,32}$/; // = _ops_items._SOURCE_RE(T4 冻结队列源形状,独立抄录同拼写)
const ITEM_STATUSES = ["active", "snoozed", "done", "dismissed"];
const ITEM_SEVERITIES = ["high", "medium", "low"];
function validateItem(fm, itemsDir) {
  for (const k of ITEM_FIELD_ORDER) if (fm[k] === undefined || fm[k] === null || fm[k] === "") throw Object.assign(new Error(`条目缺必填字段 ${k}`), { code: "verify_failed" });
  if (typeof fm.action !== "string" || !fm.action.trim()) throw Object.assign(new Error("action 必须是非空字符串"), { code: "verify_failed" });
  if (typeof fm.args !== "object" || Array.isArray(fm.args)) throw Object.assign(new Error("args 必须是映射(动作参数)"), { code: "verify_failed" });
  if (typeof fm.evidence !== "object" || !Object.keys(fm.evidence).length) throw Object.assign(new Error("evidence 必须是非空映射(无证据即无话)"), { code: "verify_failed" });
  for (const k of ["impact", "rollback", "cause_group"]) if (typeof fm[k] !== "string" || !fm[k].trim()) throw Object.assign(new Error(`${k} 必须是非空字符串(四键后果文案面)`), { code: "verify_failed" });
  const dk = fm.dedup_key;
  if (typeof dk !== "object" || Object.keys(dk).sort().join(",") !== "error_signature,probe_class,source")
    throw Object.assign(new Error(`dedup_key 恰含三键(source,probe_class,error_signature)`), { code: "verify_failed" });
  for (const k of Object.keys(dk)) if (typeof dk[k] !== "string" || !dk[k]) throw Object.assign(new Error(`dedup_key.${k} 必须是非空字符串`), { code: "verify_failed" });
  if (!SOURCE_RE.test(dk.source)) throw Object.assign(new Error(`dedup_key.source 形状非法(^[a-z0-9_]{1,32}$):${dk.source}`), { code: "verify_failed" });
  if (!ITEM_SEVERITIES.includes(fm.severity)) throw Object.assign(new Error(`severity 闭集外:${fm.severity}`), { code: "verify_failed" });
  if (fm.status !== "active") throw Object.assign(new Error(`产条 status 恒 active(复开走链指非就地迁移):${fm.status}`), { code: "verify_failed" });
  if (fm.supersedes != null && (!fs.existsSync(path.join(itemsDir, `${fm.supersedes}.md`))))
    throw Object.assign(new Error(`supersedes 指向不存在条目:${fm.supersedes}`), { code: "verify_failed" });
}

// json.dumps(args, sort_keys=True, ensure_ascii=False) 字节对齐(摘要入参;Python 默认分隔符 ", "/": ")
const pyJson = (obj) => `{${Object.keys(obj).sort().map((k) => `${JSON.stringify(k)}: ${JSON.stringify(obj[k])}`).join(", ")}}`;

// 产条(确定性,零 LLM):十字段 frontmatter + 人读摘要正文一条一文件,写 ops/items 树。
// spec={source,probe_class,error_signature,action,args,evidence,impact,rollback,severity,cause_group,summary,round_id}
// 跨语言镜像钉子面(审后修 P1-2):仅供 selftest 对拍 _ops_items.py 金常量;createOpsItem 内部 digest 同拼法。
// 双向注释律:backend/ipdb/_ops_items.py create_item 改拼接收=先过 selftest 本断言(嵌套/浮点 args 两语言即分叉,现调用面恒扁平)。
export function mirrorDigestForTest({ source, probe_class, error_signature, action, args, latest }) {
  return crypto.createHash("sha1").update([source, probe_class, error_signature, action, pyJson(args ?? {}), latest ?? ""].join("\x00"), "utf8").digest("hex").slice(0, 10);
}
// 返回 {outcome: created|reopened|deduped, item, supersedes, echo}。校验全在写前,失败=树零变化。
export function createOpsItem(itemsDir, spec, { echoRoundId = null, dayIso } = {}) {
  const sig = { source: spec.source, probe_class: spec.probe_class, error_signature: spec.error_signature };
  const same = (it) => it.dedup_key && it.dedup_key.source === sig.source && it.dedup_key.probe_class === sig.probe_class && it.dedup_key.error_signature === sig.error_signature;
  const tree = parseItemsTree(itemsDir);
  const sameKey = tree.filter(same);
  const openItem = sameKey.find((it) => it.status === "active" || it.status === "snoozed");
  if (openItem) {
    if (echoRoundId && openItem.round_id === echoRoundId) // 原轮产物回声:回原 outcome 零写(replay 确定性)
      return { outcome: openItem.supersedes ? "reopened" : "created", item: openItem.id, supersedes: openItem.supersedes ?? null, echo: true };
    return { outcome: "deduped", item: openItem.id, supersedes: null, echo: false }; // 同因在飞不双开
  }
  const latest = sameKey.length ? sameKey.reduce((a, b) => (b.mtimeMs > a.mtimeMs ? b : a)).id : null; // mtime 新者即链头(Finding 1)
  const digest = crypto.createHash("sha1").update([sig.source, sig.probe_class, sig.error_signature, spec.action, pyJson(spec.args ?? {}), latest ?? ""].join("\x00"), "utf8").digest("hex").slice(0, 10);
  const stem = `${dayIso}-item-${digest}`;
  const fm = { id: stem, action: spec.action, args: spec.args, evidence: { round_id: spec.round_id, ...spec.evidence },
    impact: spec.impact, rollback: spec.rollback, dedup_key: sig, severity: spec.severity, cause_group: spec.cause_group, status: "active",
    ...(latest ? { supersedes: latest } : {}) };
  validateItem(fm, itemsDir);
  const text = renderItem(fm, spec.summary);
  parseItem(text, `${stem}.md`); // 序列化文本往返解析律(写什么校什么;_render_item 同律)
  const p = path.join(itemsDir, `${stem}.md`);
  if (fs.existsSync(p)) throw Object.assign(new Error(`条目文件已存在,拒绝覆写:${stem}.md`), { code: "verify_failed" }); // 写前防呆(Finding 1)
  fs.mkdirSync(itemsDir, { recursive: true });
  fs.writeFileSync(`${p}.tmp`, text);
  fs.renameSync(`${p}.tmp`, p); // 原子写(_ops_store.atomic_write_text 判例)
  return { outcome: latest ? "reopened" : "created", item: stem, supersedes: latest, echo: false };
}
