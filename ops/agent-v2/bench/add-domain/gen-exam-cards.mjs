#!/usr/bin/env node
// gen-exam-cards.mjs — 加源重实现基准考题卡预填生成器(票 #334 交付面 2;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议「考题卡预填生成」)。
//
// 语义:从宇宙行 + 真源实抓样本生成交接单形考题卡(name/url/samples 3-5 行/format/
// auth/cadence/field_routing)——样本在**构建考题时抓一次冻结进卡**,trial 内不联网
// 抓样本(spec 原话);卡的形状门 = dossierShape(tasks/add-round.mjs 单源,与轮
// DOSSIER 相位同门,禁第二份形状清单);卡名 = 宇宙行名(stem 契约:slugify(name)
// ===题名,打分器 test_<name>.py 钥匙面才对得上)。
//
// 端点覆写表(#331 已记人裁点,生成器不替用户裁):宇宙行内多端点源(url 为仓库/
// 目录前缀形)的真实端点在源文件 _BASE 常量——P3 真跑前用户裁「补端点 or 起点
// 语义」。故 url 解析做成可配:--endpoints JSON({题名: url})优先;未覆写时前缀形
// (尾斜杠)→ endpoint_pending=true 点名进 _provenance,照常出卡,裁决留给 P3。
//
// 产物 = 答案面工件(含考题名+URL):落 --out-dir(缺省 <仓根>/dev/bench-add-domain/
// cards,dev/ 不入仓,文件放置规范);每题一件 <name>.json。roster 取数 = loadRosterText
// 单源(leak-check 同面);meta dump = gen-universe DUMP_META_SCRIPT 单源(stale_days
// 供 cadence 派生)。
//
// 用法:
//   node gen-exam-cards.mjs [--universe PATH] [--roster-file PATH] [--meta-file PATH]
//                           [--endpoints PATH] [--only 名,名,...] [--out-dir DIR]
//                           [--python BIN] [--timeout-ms 30000]
// 退出码:0=全绿;1=有题失败(部分卡已落盘保真,逐题报错);2=用法/取数失败。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseRoster } from "../roster.mjs";
import { loadRosterText } from "../leak-check.mjs";
import { DUMP_META_SCRIPT } from "./gen-universe.mjs";
import { loadUniverse } from "./score.mjs";
// 加载序锚(循环导入面纪律,同 tests/add-round.test.mjs 导入序):tasks/add-round.mjs
// ↔ run-add.mjs ↔ registry.mjs ↔ tasks/index.mjs 有环;先拉 run-add 侧再拉 add-round,
// 环从 run-add 面解(与 P1 测试/启动器同序)。倒序会在 index.mjs 聚合表撞 addRoundTask TDZ。
import "../../run-add.mjs";
import { dossierShape, slugify } from "../../tasks/add-round.mjs";

const ROOT = path.resolve(import.meta.dirname, "..", "..", "..", ".."); // add-domain → 仓根(4 层)
const SAMPLE_LINE_CAP = 300; // 卡内样本行封顶(交接单可读性;嗅探在截断前做)

// ── 纯函数面(导出=测试单源面)──────────────────────────────────────────

// 实抓样本取行:非空行取前 5(封顶);注释行(# / ; / //)优先跳——交接单样本要展示
// 数据面形状,纯注释前 5 行对实现无用;非注释行不足 3 时回退含注释原始行(宁可如实
// 也不造);仍不足 3 返回空集(调用方红——无样本即无卡)。
export function pickSamples(text) {
  const lines = String(text ?? "").split("\n").map((l) => l.replace(/\r$/, "").trim()).filter(Boolean);
  const data = lines.filter((l) => !/^[#;]|^\/\//.test(l));
  const pick = data.length >= 3 ? data : lines;
  return pick.length >= 3 ? pick.slice(0, 5) : [];
}

// 格式嗅探(草案级,交接单 format 面;判定序:json → ip 列表 → tsv → csv → 空白分列 → text)
// #341 ① 借列形:csv 首行全名列形+后续数据形=表头面入 format(列名供路由同名列匹配);
// 空白双列 ip+计数形入 format 预告计数语义。列结构判据单源 = splitColumns。
export function sniffFormat(lines) {
  const ls = (lines ?? []).filter(Boolean);
  if (!ls.length) return "text";
  if (/^\s*[[{]/.test(ls[0])) return "json";
  const ipRe = /^\d{1,3}(\.\d{1,3}){3}(\/\d{1,2})?$/;
  if (ls.every((l) => ipRe.test(l.trim()))) return "plain-ip-list";
  const cols = splitColumns(ls);
  if (cols?.delim === "tab") return "tsv";
  if (cols?.delim === "comma") return cols.header ? "csv(表头)" : "csv";
  if (cols?.delim === "space") return "text(空白分列)";
  return "text";
}

// cadence 派生(源元数据 stale_days → 人话档位;无声明=如实未知,不编)
export function cadenceOf(staleDays) {
  if (typeof staleDays !== "number" || !Number.isFinite(staleDays)) return "未知(源元数据无 stale_days 声明)";
  if (staleDays <= 1) return `daily(源元数据 stale_days=${staleDays})`;
  if (staleDays <= 7) return `weekly 级(源元数据 stale_days=${staleDays})`;
  return `低频/静态(源元数据 stale_days=${staleDays})`;
}

// 字段路由草案(roster fields 面 → 路由行草案;ip 面 → rebuild 键,语义字段 →
// 分类/属性面;子列信号并入草案行——生产里这是人写的草案,生成器产机械可核的等价物)
export function routingDraftOf(fields, category) {
  const f = (fields ?? []).filter(Boolean);
  const lines = [];
  if (f.includes("ip") || !f.length) lines.push("行内 IP/CIDR → rebuild 键(cidr)");
  for (const x of f.filter((y) => y !== "ip")) lines.push(`${x} → ${category} 字段/分类词汇面(草案)`);
  if (!lines.length) lines.push("样本行语义 → 路由草案(交接单人裁)");
  return lines;
}

// 端点面解析(覆写表优先;前缀形未覆写=pending 点名,不替人裁)。pending 判据 = 尾斜杠
// 前缀形(仓库/目录页,不可直接下载)——#331 人裁点正是这一面;完整端点的多 URL 源
// 不 pending(卡钉宇宙行 URL 即可考,无需裁决)。真仓实测前缀面 = 10 题(spec 勘误
// 段列 6,机械判据面更宽,以判据为准)。
// ── #341 ① 兄弟源惯例面(答案无关:沙箱内既有源同名列/同形列→Evidence 槽位惯例表)──
// 背景(#331 优化环数据裁决,2026-11-12):bench 卡 field_routing 是机械嗅探草案,而生产
// 交接单由发现轮 Phase 1 调研生成、带惯例研究成果——输入面增厚=答案无关、全体考题
// 均匀受益。机械推导面:①同名列——考题样本表头列名(json 键同形)与兄弟源在用的槽位
// 名归一相等;②同形列——样本列值形(两位国码/AS 前缀名/计数/邮箱/时间戳/占位符)匹配
// 兄弟源在用槽位的语义面。宁少算纪律:无兄弟源在用的槽只出草案行,不冒称惯例;混合
// 列/单值列不判形。答案无关纪律=只读 backend/ipdb/_sources/<兄弟名>.py 既有源文件,
// **排除考题自身源文件**(它就是答案)与 _ 前缀基建件,永不读任何答案测试。

// 单个兄弟源机械抽取:fields 声明元组、Evidence( kwargs(括号平衡段)、parse_row
// 返回字典键(内部 _ 键排除)、「-」占位符转换面在场。草案面机械近似,不求 AST 精确。
export function parseSiblingUsage(name, text) {
  const src = String(text ?? "");
  const fields = [];
  const fm = src.match(/^\s*fields\s*=\s*\(([\s\S]*?)\)/m);
  if (fm) for (const m of fm[1].matchAll(/"([^"]+)"|'([^']+)'/g)) fields.push(m[1] ?? m[2]);
  const slots = new Set();
  for (const m of src.matchAll(/Evidence\s*\(/g)) {
    // 括号平衡段内收 kwargs(防串到邻函数赋值面)
    let depth = 1, end = m.index + m[0].length;
    for (let i = end; i < src.length && depth > 0; i++) {
      if (src[i] === "(") depth += 1;
      else if (src[i] === ")") depth -= 1;
      if (depth === 0) { end = i; break; }
      if (i - m.index > 2000) break; // 病态未闭合面保险丝
    }
    const seg = src.slice(m.index + m[0].length, end);
    for (const k of seg.matchAll(/([a-z_][a-z0-9_]*)\s*=/g)) slots.add(k[1]);
  }
  for (const m of src.matchAll(/def parse_row[\s\S]{0,2000}/g))
    for (const k of m[0].matchAll(/"([a-z_][a-z0-9_]*)"\s*:/g)) if (!k[1].startsWith("_")) slots.add(k[1]);
  const placeholderDash = /!=\s*"-"|==\s*"-"|!=\s*'-'|==\s*'-'/.test(src);
  return { name, fields, slots: [...slots], placeholderDash };
}

// 惯例表:槽位/字段 → 兄弟源名(插入序确定);excludeName=考题自身源(答案无关纪律,
// 沙箱内该文件已被剥——表内同样不得出现);_ 前缀文件(_base/_download/_lmdb 等基建
// 面)不入表。
export function buildSiblingIndex(files, excludeName) {
  const slots = new Map();
  const fields = new Map();
  const placeholderDash = [];
  const add = (map, key, name) => {
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(name);
  };
  let scanned = 0;
  for (const f of files ?? []) {
    if (!f?.name || f.name === excludeName || f.name.startsWith("_")) continue;
    const u = parseSiblingUsage(f.name, f.text);
    scanned += 1;
    for (const k of u.slots) add(slots, k, f.name);
    for (const x of u.fields) add(fields, x, f.name);
    if (u.placeholderDash) placeholderDash.push(f.name);
  }
  return { slots, fields, placeholderDash, scanned, excluded: excludeName ?? null };
}

// 列形判据(机械):ip/cidr/ip-cidr、AS 前缀名、邮箱、时间戳、两位国码、纯整数、全占位。
// 「-」占位值不破形(其惯例另行成行);混合列/有效值<2=null(宁少算,不过拟合)。
const IP_RE_ = /^\d{1,3}(\.\d{1,3}){3}$/;
const CIDR_RE_ = /^\d{1,3}(\.\d{1,3}){3}\/\d{1,3}$/;
const TS_RE_ = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?Z?)?$|^(19|20)\d{6}$/;
export function columnShapeOf(rawValues) {
  const raw = (rawValues ?? []).map((v) => String(v ?? "").trim()).filter(Boolean);
  const vs = raw.filter((v) => v !== "-");
  if (!vs.length) return raw.filter((v) => v === "-").length >= 2 ? "dash" : null;
  if (vs.length < 2) return null;
  const every = (m) => vs.every((v) => (typeof m === "function" ? m(v) : m.test(v)));
  if (every(IP_RE_)) return "ip";
  if (every(CIDR_RE_)) return "cidr";
  if (every((v) => IP_RE_.test(v) || CIDR_RE_.test(v))) return "ip-cidr";
  if (every(/^AS\d+(\s|$)/i)) return "asn-name";
  if (every(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) return "email";
  if (every(TS_RE_)) return "timestamp";
  if (every(/^[A-Z]{2}$/)) return "cc";
  if (every(/^\d+$/)) return "int";
  return null;
}

// 列结构判据(单源,sniffFormat 与路由共用):tab / 逗号(表头识别)/ 空白分列(首列须
// ip 形);列数不一致或单列=null。表头判据=首行全名列形 + 后续行有数据形值。
export function splitColumns(lines) {
  const ls = (lines ?? []).map((l) => String(l ?? "")).filter((l) => l.trim());
  if (ls.length < 2) return null;
  const same = (rows) => rows.every((r) => r.length === rows[0].length && r.length >= 2);
  const tabRows = ls.map((l) => l.split("\t"));
  if (same(tabRows)) return { delim: "tab", rows: tabRows, header: null };
  const commaRows = ls.map((l) => l.split(","));
  if (same(commaRows)) {
    const nameish = (c) => /^[A-Za-z][A-Za-z0-9 _./-]*$/.test(c.trim());
    const dataish = (c) => IP_RE_.test(c.trim()) || CIDR_RE_.test(c.trim()) || /^\d+$/.test(c.trim()) || /^[A-Z]{2}$/.test(c.trim());
    if (commaRows[0].every(nameish) && commaRows.slice(1).some((r) => r.some(dataish)))
      return { delim: "comma", rows: commaRows.slice(1), header: commaRows[0].map((c) => c.trim()) };
    return { delim: "comma", rows: commaRows, header: null };
  }
  const wsRows = ls.map((l) => l.trim().split(/\s+/));
  if (same(wsRows) && columnShapeOf(wsRows.map((r) => r[0])) === "ip")
    return { delim: "space", rows: wsRows, header: null };
  return null;
}

// 惯例路由行(#341 ① 主交付面):样本列 → 槽位惯例行(同名列优先,同形列次之),
// 后接 roster 字段面(有兄弟源同名字段=惯例化,否则原草案行)。无列结构/解析失败=
// 原 routingDraftOf 草案面不变(向后兼容)。产出保证非空(dossierShape 门)。
export function routingLines({ sampleLines, format, rosterFields, category, index }) {
  const norm = (x) => String(x).toLowerCase().replace(/[^a-z0-9_]/g, "");
  const slotNames = (slot) => index?.slots?.get(slot) ?? [];
  const cite = (names) => `${names.slice(0, 3).join("、")}${names.length > 3 ? ` 等 ${names.length} 源` : ""}`;
  const normSlot = (rawName) => {
    if (!rawName) return null;
    const n = norm(rawName);
    for (const k of index?.slots?.keys() ?? []) if (norm(k) === n) return k;
    return null;
  };
  const nameLine = (label, rawName, slot) =>
    `列${label}「${rawName}」→ Evidence ${slot} 槽位(兄弟源同名列惯例:${cite(slotNames(slot))} 在用)`;
  const faceLines = [];
  const cols = splitColumns(sampleLines);
  if ((format ?? "").startsWith("json")) {
    const first = String((sampleLines ?? []).find(Boolean) ?? "");
    let obj = null;
    try { const j = JSON.parse(first); obj = Array.isArray(j) ? j[0] : j; } catch { try { const j = JSON.parse((sampleLines ?? []).join("\n")); obj = Array.isArray(j) ? j[0] : j; } catch { obj = null; } }
    if (obj && typeof obj === "object") {
      for (const [k] of Object.entries(obj)) {
        const slot = normSlot(k);
        // ip 键是 rebuild 键不是 Evidence 槽位(#341 评审 P2-1:同名列分支会吞 ip 列)
        if (slot && slot !== "ip") faceLines.push(nameLine(1, k, slot)); // json 无列序面,列号统一记 1(键名才是路由面)
      }
    }
  } else if (cols) {
    const nCols = cols.rows[0].length;
    const shapes = Array.from({ length: nCols }, (_, i) => columnShapeOf(cols.rows.map((r) => r[i])));
    const valuesOf = (i) => cols.rows.map((r) => r[i]);
    const ipish = (sh) => sh === "ip" || sh === "cidr" || sh === "ip-cidr";
    let ipLineDone = false;
    for (let i = 0; i < nCols; i++) {
      const label = i + 1;
      const shape = shapes[i];
      const slot = normSlot(cols.header?.[i]);
      // 同名列惯例优先;但 ip 形列是 rebuild 键,不让同名分支吞掉(#341 评审 P2-1)
      if (slot && !ipish(shape)) { faceLines.push(nameLine(label, cols.header[i], slot)); continue; }
      if (ipish(shape)) {
        // start+prefix 三联(区块清单馈送形):ip、ip、8-32 整数 → 合成 cidr 键,消费三列
        const prefixVals = valuesOf(i + 2);
        if (shape === "ip" && shapes[i + 1] === "ip" && shapes[i + 2] === "int"
          && prefixVals.every((v) => { const n = Number(v); return n >= 8 && n <= 32; })) {
          faceLines.push(`列${label}+列${i + 3}(IP 起点+前缀长记法)→ rebuild 键(cidr:合成 start/prefix;中间 end 列冗余)`);
          i += 2;
          continue;
        }
        if (!ipLineDone) { faceLines.push(`列${label}(IP${shape === "ip" ? "" : "/CIDR"} 形)→ rebuild 键(cidr/ip)`); ipLineDone = true; }
        continue;
      }
      if (shape === "asn-name")
        faceLines.push(slotNames("as_name").length
          ? `列${label}(AS 前缀名形)→ as_name 槽位(保留原文含空格;兄弟源同形惯例:${cite(slotNames("as_name"))} 在用)`
          : `列${label}(AS 前缀名形)→ as_name 候选(草案;兄弟源无 as_name 在用)`);
      else if (shape === "cc")
        faceLines.push(slotNames("country_code").length
          ? `列${label}(两位国码形)→ country_code 槽位(兄弟源同形惯例:${cite(slotNames("country_code"))} 在用)`
          : `列${label}(两位国码形)→ country_code 候选(草案;兄弟源无 country_code 在用)`);
      else if (shape === "email")
        faceLines.push(slotNames("abuse_contact").length
          ? `列${label}(邮箱形)→ abuse_contact 槽位(兄弟源同形惯例:${cite(slotNames("abuse_contact"))} 在用)`
          : `列${label}(邮箱形)→ abuse_contact 候选(草案;兄弟源无 abuse_contact 在用)`);
      else if (shape === "timestamp")
        faceLines.push(slotNames("first_seen").length || slotNames("last_seen").length
          ? `列${label}(时间戳形)→ first_seen/last_seen 槽位(列序惯例:首见列在前末见列在后;兄弟源在用:${cite([...new Set([...slotNames("first_seen"), ...slotNames("last_seen")])])}`
          : `列${label}(时间戳形)→ 时间戳槽位候选(草案)`);
      else if (shape === "int")
        faceLines.push(slotNames("reporter_count").length
          ? `列${label}(计数形)→ reporter_count 槽位(兄弟源同形惯例:${cite(slotNames("reporter_count"))} 在用)`
          : `列${label}(计数形)→ 计数语义候选(草案;兄弟源无 reporter_count 在用)`);
    }
    // 占位符「-」惯例行(任列在场即提;国码/AS 名列混占位常态,单列不触发 dash 形)
    const dashCols = cols.rows[0].map((_, i) => i).filter((i) => valuesOf(i).some((v) => String(v).trim() === "-"));
    if (dashCols.length && (index?.placeholderDash ?? []).length)
      faceLines.push(`占位符「-」在场(列${dashCols.map((i) => i + 1).join("、")})→ 兄弟源惯例:占位值转 None 不入槽(${cite(index.placeholderDash)} 在用)`);
  }
  // 无列面(裸 ip 列表/json 解析失败)=原草案行为逐字不变(向后兼容;列面馈送才走增厚)
  if (!faceLines.length) return routingDraftOf(rosterFields, category);
  const lines = [...faceLines];
  // roster 字段面:同名字段惯例化,否则原草案行(routingDraftOf 同词)
  for (const f of (rosterFields ?? []).filter(Boolean).filter((x) => x !== "ip")) {
    const users = index?.fields?.get(f) ?? [];
    lines.push(users.length
      ? `${f} → ${category} 轴语义字段(兄弟源同名字段 ${users.length} 源在用;分类面=classification_type/verdict)`
      : `${f} → ${category} 字段/分类词汇面(草案)`);
  }
  return lines;
}

export function endpointFace({ row, metaEntry, endpoints }) {
  void metaEntry; // 判据单源 = 尾斜杠前缀形;meta urls 多端面不参与 pending 判定
  const override = endpoints?.[row.name];
  if (typeof override === "string" && override.trim())
    return { url: override.trim(), endpoint_pending: false, endpoint_note: `端点已覆写:endpoints 表(${row.name})` };
  if (/\/$/.test(row.url ?? ""))
    return {
      url: row.url,
      endpoint_pending: true,
      endpoint_note: "前缀 URL(仓库/目录页)未覆写——P3 真跑前须人裁「补端点 or 起点语义」(#331 记账)",
    };
  return { url: row.url, endpoint_pending: false, endpoint_note: null };
}

// 单卡构建:宇宙行 + roster 面 + meta 面 + 实抓文本 → 交接单形卡(+_provenance 冻结面)
// siblingIndex 可选(#341 ① 惯例面;null=零惯例,卡回退草案面,形状不受影响)
export function buildCard({ row, rosterEntry, metaEntry, sampleText, endpoints, fetchedAt, siblingIndex = null }) {
  if (!row?.name) throw new Error("宇宙行缺 name");
  if (slugify(row.name) !== row.name)
    throw new Error(`stem 契约红:宇宙行名 ${row.name} 非 slug 形(slugify≠自身;打分器钥匙面 test_<name>.py 对不上)`);
  if (!rosterEntry) throw new Error(`${row.name}:roster 缺行(宇宙与 roster 分叉,须人裁)`);
  if (!metaEntry) throw new Error(`${row.name}:meta dump 缺行(dump 单源纪律,须人裁)`);
  const raw = pickSamples(sampleText);
  if (!raw.length) throw new Error(`${row.name}:样本不足 3 行实抓(无样本即无卡,fail-closed)`);
  const ep = endpointFace({ row, metaEntry, endpoints });
  const fmt = sniffFormat(raw);
  const card = {
    name: row.name,
    url: ep.url,
    samples: raw.map((l) => (l.length > SAMPLE_LINE_CAP ? `${l.slice(0, SAMPLE_LINE_CAP)}…` : l)),
    format: fmt,
    auth: "none", // 宇宙面无 auth env 读(gen-universe keyless 反扫钉死;有 key 源不入宇宙)
    cadence: cadenceOf(metaEntry.stale_days),
    field_routing: routingLines({ sampleLines: raw, format: fmt, rosterFields: rosterEntry.fields, category: rosterEntry.category, index: siblingIndex }),
    _provenance: {
      fetched_at: fetchedAt,
      endpoint_override: endpoints?.[row.name] !== undefined,
      endpoint_pending: ep.endpoint_pending,
      endpoint_note: ep.endpoint_note,
      universe_split: row.split,
      source_stale_days: metaEntry.stale_days ?? null,
      roster_fields: rosterEntry.fields,
      siblings_scanned: siblingIndex?.scanned ?? 0, // #341 ① 惯例面扫描数(排考题自身;0=零惯例回退草案)
      note: "样本构建考题时抓一次冻结进卡;trial 内不联网抓样本(spec §重实现基准协议)",
    },
  };
  const shape = dossierShape(card); // 与轮 DOSSIER 相位同门(单源形状律)
  if (!shape.ok) throw new Error(`${row.name}:生成卡形状坏:${shape.reason}`);
  return card;
}

// ── 程序面(CLI 与测试共用)────────────────────────────────────────────
// fetchImpl 缝:测试注入 stub(零网络);缺省 = 真 fetch(构建考题时抓一次,非 trial 面)。
// 兄弟源装载(#341 ①):缺省读 <仓根>/backend/ipdb/_sources 非 _ 前缀 .py(_ 前缀=基建
// 面);目录缺席=零惯例面 fail-open(卡回退草案,答案无关面不受影响)。答案无关纪律:
// 逐卡 buildSiblingIndex(…, row.name) 排除考题自身源文件,永不读任何答案测试。
function loadDefaultSiblings(dir) {
  const d = dir ?? path.join(ROOT, "backend", "ipdb", "_sources");
  try {
    return fs.readdirSync(d)
      .filter((f) => f.endsWith(".py") && !f.startsWith("_"))
      .map((f) => ({ name: f.replace(/\.py$/, ""), text: fs.readFileSync(path.join(d, f), "utf8") }));
  } catch {
    return [];
  }
}

export async function genExamCards({ universePath, rosterText, metaDump, endpoints = {}, fetchImpl, outDir, only = [], timeoutMs = 30000, nowIso, siblingFiles, sourcesDir }) {
  const rows = loadUniverse(universePath); // frozen 闸 + 行序(沙箱/打分器同律)
  const roster = parseRoster(rosterText);
  const fetchText = fetchImpl ?? (async (url) => {
    const res = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(timeoutMs), headers: { "user-agent": "ipradar-add-bench/1.0" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}(fetch ${url})`);
    return res.text();
  });
  fs.mkdirSync(outDir, { recursive: true });
  const sibFiles = siblingFiles ?? loadDefaultSiblings(sourcesDir); // 一次装载,逐卡排除自身
  const written = [];
  const failed = [];
  const fetchedAt = nowIso ?? new Date().toISOString();
  for (const row of rows) {
    if (only.length && !only.includes(row.name)) continue;
    try {
      const card = buildCard({
        row,
        rosterEntry: roster.find((r) => r.name === row.name) ?? null,
        metaEntry: metaDump[row.name] ?? null,
        sampleText: await fetchText(row && (endpoints?.[row.name] ?? row.url)),
        endpoints,
        fetchedAt,
        siblingIndex: buildSiblingIndex(sibFiles, row.name), // 考题自身排除(答案无关纪律)
      });
      fs.writeFileSync(path.join(outDir, `${row.name}.json`), JSON.stringify(card, null, 2) + "\n");
      written.push(row.name);
    } catch (e) {
      failed.push({ name: row.name, error: String(e?.message ?? e) }); // 逐题红记账:好卡照写,坏题留名
    }
  }
  return { written, failed, outDir };
}

// ── CLI ──
function parseArgs(argv) {
  const out = { universe: null, rosterFile: null, metaFile: null, endpoints: null, only: null, outDir: null, python: null, timeoutMs: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--universe") out.universe = next();
    else if (a === "--roster-file") out.rosterFile = next();
    else if (a === "--meta-file") out.metaFile = next();
    else if (a === "--endpoints") out.endpoints = next();
    else if (a === "--only") out.only = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--out-dir") out.outDir = next();
    else if (a === "--python") out.python = next();
    else if (a === "--timeout-ms") out.timeoutMs = Number(next());
    else if (a === "--help" || a === "-h") out.help = true;
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  return out;
}

function resolvePython(flagged) {
  if (flagged) return flagged;
  if (process.env.BENCH_PYTHON) return process.env.BENCH_PYTHON;
  return "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python"; // worktree 律(AGENTS.md;build-sandbox 同款)
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    console.error("用法:node gen-exam-cards.mjs [--universe PATH] [--roster-file PATH] [--meta-file PATH] [--endpoints PATH] [--only 名,名,...] [--out-dir DIR] [--python BIN] [--timeout-ms 30000]");
    return 0;
  }
  const python = resolvePython(args.python);
  const backend = path.join(ROOT, "backend");
  const rosterText = args.rosterFile
    ? fs.readFileSync(path.resolve(args.rosterFile), "utf8")
    : loadRosterText({ pythonBin: python });
  const metaDump = args.metaFile
    ? JSON.parse(fs.readFileSync(path.resolve(args.metaFile), "utf8"))
    : JSON.parse(execFileSync(python, ["-c", DUMP_META_SCRIPT], { cwd: backend, encoding: "utf8" }));
  const endpoints = args.endpoints ? JSON.parse(fs.readFileSync(path.resolve(args.endpoints), "utf8")) : {};
  const universePath = args.universe ?? path.join(import.meta.dirname, "data", "universe.jsonl");
  const outDir = args.outDir ? path.resolve(args.outDir) : path.join(ROOT, "dev", "bench-add-domain", "cards");
  const r = await genExamCards({
    universePath, rosterText, metaDump, endpoints, outDir,
    only: args.only ?? [], timeoutMs: args.timeoutMs ?? 30000,
  });
  for (const f of r.failed) console.error(`✋ ${f.name}: ${f.error}`);
  console.log(`考题卡:写 ${r.written.length} 件 → ${r.outDir}${r.failed.length ? `;失败 ${r.failed.length} 件(见上)` : ""}`);
  return r.failed.length ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  process.exit(await main());
}
