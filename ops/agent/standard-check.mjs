#!/usr/bin/env node
// standard-check.mjs — STANDARD.md 门挂点核对器(#181;黄金标准四层之「门挂点层」机检面)。
// 语义(票 #181/ADR 0008):挂不上验证手段的条目只能称建议,不得称标准——
//   条文(#### X-n)必须带门挂点且指向的文件/测试真实存在,否则非零退出;
//   「建议」类无门挂点,必须显式标「类:建议」;组合不出原语的条目=伪条目。
// 零依赖纯 node(容器/CI 自带 node 即可跑);真源=ops/agent/STANDARD.md;
// 本核对器自身挂 selftest 链(selftest.sh §13)。挂点路径一律主仓相对——
// 嵌套 docs 仓文件不可作门挂点(CI checkout 无 docs/,判例=test_precedent_schema.py skip 形)。

import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));

// 节名关键词 → 节种类(## 标题行含关键词即认;数字前缀「一、」等不敏感)
const SECTION_KEYS = [
  ["primitives", "原语层"],
  ["articles", "条文层"],
  ["gates", "门挂点层"],
  ["goldens", "金标层"],
  ["advice", "建议区"],
];
const REQUIRED_SECTIONS = SECTION_KEYS.map(([, kw]) => kw);
const STATUS_VOCAB = new Set(["已有", "半缺", "缺"]);
const ARTICLE_FIELDS = ["主张", "原语组成", "门挂点", "判例链"];

const stripTicks = (s) => s.replace(/`/g, "").trim();

// ---- 解析:节 → 原语表行 / 条文块 / 建议条目 ----
export function parseStandard(text) {
  const lines = text.split(/\r?\n/);
  const sections = []; // {kind, title, lineStart}
  const articles = []; // {id, prefix, num, sectionKind, sectionTitle, title, fields}
  const advice = []; // {line, text}

  let cur = { kind: null, title: "" };
  sections.push(cur);
  let curArticle = null;

  for (const line of lines) {
    const h2 = /^##\s+(?!#)(.*)$/.exec(line);
    if (h2) {
      curArticle = null;
      const title = h2[1].trim();
      const hit = SECTION_KEYS.find(([, kw]) => title.includes(kw));
      cur = { kind: hit ? hit[0] : null, title };
      sections.push(cur);
      continue;
    }
    const h = /^#{1,4}\s/.test(line); // ##/###/#### 一律终结上一块
    const art = /^####\s+([A-Z]+)-(\d+)\s*(.*)$/.exec(line);
    if (art) {
      curArticle = {
        id: `${art[1]}-${art[2]}`,
        prefix: art[1],
        num: Number(art[2]),
        sectionKind: cur.kind,
        sectionTitle: cur.title,
        title: art[3].trim(),
        fields: {},
      };
      articles.push(curArticle);
      continue;
    }
    if (h) {
      curArticle = null;
      continue;
    }
    if (curArticle) {
      const f = /^-\s*(主张|原语组成|门挂点|判例链)\s*[:：]\s*(.*)$/.exec(line);
      if (f) curArticle.fields[f[1]] = f[2].trim();
      continue;
    }
    if (cur.kind === "advice" && /^-\s+/.test(line)) {
      advice.push({ text: line.replace(/^-\s+/, "").trim() });
    }
  }
  return { sections, articles, advice };
}

// ---- 核对:解析结果 × 文件系统(DI)→ results/counts/exitCode ----
export function checkStandard(text, opts = {}) {
  const exists = opts.exists ?? existsSync;
  const readFileRaw = opts.readFile ?? ((p) => (existsSync(p) ? readFileSync(p, "utf8") : null));
  const readFile = (p) => {
    try {
      return readFileRaw(p);
    } catch {
      return null;
    }
  };
  const wantPrimitives = opts.primitiveCount ?? 22;

  const results = [];
  const fail = (code, msg) => results.push({ ok: false, code, msg });
  const okr = (code, msg) => results.push({ ok: true, code, msg });

  const { sections, articles, advice } = parseStandard(text);

  // ① 必备四层+建议区节在场(静默删节=违规)
  const presentKinds = new Set(sections.filter((s) => s.kind).map((s) => s.kind));
  const kindByName = Object.fromEntries(SECTION_KEYS.map(([k, w]) => [w, k])); // 关键词→节种类
  for (const kw of REQUIRED_SECTIONS) {
    if (presentKinds.has(kindByName[kw])) okr("section", `节在场:${kw}`);
    else fail("section", `必备节缺失:${kw}(四层+建议区不得静默消失)`);
  }

  // ② 原语层:表行 = 名称|2026出处|内部状态(+内部锚);闭集计数/状态词表/重名
  const primSection = sections.find((s) => s.kind === "primitives");
  const primitives = [];
  if (primSection) {
    // 节界精确扫描:原语层 ## 起行 → 下一 ## 止行(表行只在本节内认)
    const lineIdx = text.split(/\r?\n/);
    const secStarts = sections.map((s) =>
      lineIdx.findIndex((l) => l.startsWith("## ") && l.slice(3).trim() === s.title));
    const start = sections.indexOf(primSection);
    const pStart = secStarts[start] ?? 0;
    const pEnd = start + 1 < sections.length ? (secStarts[start + 1] ?? lineIdx.length) : lineIdx.length;
    const seen = new Set();
    for (let i = pStart; i < pEnd; i += 1) {
      const line = lineIdx[i];
      if (!/^\|/.test(line.trim())) continue;
      if (/^\|[\s:|-]+\|?$/.test(line.trim())) continue; // 表头分隔行
      const cells = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const [id, name, source, status] = cells;
      if (!/^P\d+$/.test(id || "")) continue; // 表头行(| # | 原语 |…)非数据行
      primitives.push({ id, name, source: source || "", status: status || "" });
      if (!name) fail("primitive", `原语 ${id} 名称为空`);
      if (seen.has(name)) fail("primitive", `原语重名:${name}(${id})——一词一义`);
      seen.add(name);
      if (!STATUS_VOCAB.has(status)) {
        fail("primitive", `原语 ${id}(${name || "?"}) 状态『${status}』在词表(已有/半缺/缺)之外`);
      }
    }
    if (primitives.length !== wantPrimitives) {
      fail("primitive-count", `原语计数 ${primitives.length} ≠ 闭集 ${wantPrimitives}(v0 冻结;增删原语=STANDARD 版本变更)`);
    } else {
      okr("primitive-count", `原语闭集 ${wantPrimitives} 词齐`);
    }
  }
  const primNames = new Set(primitives.map((p) => p.name));
  const statusCount = { 已有: 0, 半缺: 0, 缺: 0 };
  for (const p of primitives) statusCount[p.status] = (statusCount[p.status] ?? 0) + 1;

  // ③ 条文(含金标 G-):字段齐备 + 原语闭包 + 门挂点存在
  let mountTotal = 0;
  let nArticles = 0;
  let nGoldens = 0;
  const articleIds = new Set();
  for (const a of articles) {
    if (a.sectionKind !== "articles" && a.sectionKind !== "goldens") {
      fail("article-section", `条文体 ${a.id} 出现在「${a.sectionTitle || a.sectionKind || "未知节"}」——挂不上门挂点不得称条文,建议区条目须以「类:建议」bullet 呈现`);
      continue;
    }
    if (articleIds.has(a.id)) fail("article", `条文编号重复:${a.id}`);
    articleIds.add(a.id);
    nArticles += 1; // 条文体计数含金标 G- 门挂点同律
    if (a.sectionKind === "goldens") nGoldens += 1;

    for (const f of ARTICLE_FIELDS) {
      if (!(f in a.fields)) {
        fail("field", `${a.id} 缺${f}字段${f === "门挂点" ? "(条文五件套不全=伪标准形态)" : ""}`);
      } else if (!a.fields[f]) {
        if (f === "门挂点") fail("mount-empty", `${a.id} 门挂点为空(空挂点=无验证手段,只能称建议)`);
        else fail("field", `${a.id} ${f}为空`);
      }
    }

    // 原语闭包:组合不出原语=伪条目
    if (a.fields["原语组成"]) {
      for (const tok of a.fields["原语组成"].split(";")) {
        const t = stripTicks(tok);
        if (!t) continue;
        if (!primNames.has(t)) fail("pseudo", `${a.id} 原语组成『${t}』不在原语表——组合不出原语=伪条目`);
      }
    }

    // 门挂点:路径存在 + fragment 在文件内 + 不进嵌套 docs 仓
    if (a.fields["门挂点"]) {
      for (const raw of a.fields["门挂点"].split(";")) {
        const entry = stripTicks(raw);
        if (!entry) {
          fail("mount-empty", `${a.id} 门挂点含空条目(空挂点=无验证手段)`);
          continue;
        }
        mountTotal += 1;
        const hashAt = entry.indexOf("#");
        const p = (hashAt === -1 ? entry : entry.slice(0, hashAt)).trim();
        const frag = hashAt === -1 ? null : entry.slice(hashAt + 1).trim();
        if (p.startsWith("docs/") || p.startsWith("/docs/")) {
          fail("mount-nested-docs", `${a.id} 门挂点 ${p} 属嵌套 docs 仓——CI checkout 无 docs/,不得作门挂点`);
          continue;
        }
        if (path.isAbsolute(p) || p.split("/").includes("..")) {
          fail("mount-path", `${a.id} 门挂点 ${p} 非主仓相对路径`);
          continue;
        }
        if (!exists(p)) {
          fail("mount-dead", `死锚:${a.id} 挂点 ${p} 不存在`);
          continue;
        }
        if (frag) {
          const body = readFile(p);
          if (body === null || !body.includes(frag)) {
            fail("mount-fragment", `死锚fragment:${a.id} 挂点 ${p} 内无锚词「${frag}」(测试/符号被删或漂移)`);
            continue;
          }
        }
        okr("mount", `${a.id} 挂点 ${entry} 在场`);
      }
    }
  }

  // ④ 建议区:无门挂点条目必须显式标类
  for (const adv of advice) {
    if (adv.text.includes("类:建议")) okr("advice", `建议条目显式标类:${adv.text.slice(0, 30)}…`);
    else fail("advice", `建议区条目未显式标「类:建议」:${adv.text.slice(0, 40)}…(无门挂点必须标类)`);
  }

  const fails = results.filter((r) => !r.ok).length;
  return {
    results,
    counts: {
      primitives: primitives.length,
      statusCount,
      articles: nArticles,
      goldens: nGoldens,
      advice: advice.length,
      mounts: mountTotal,
    },
    exitCode: fails > 0 ? 1 : 0,
  };
}

// ---- CLI:核对真源 STANDARD.md ----
function main() {
  const argv = process.argv.slice(2);
  const fileArg = argv.includes("--file") ? argv[argv.indexOf("--file") + 1] : path.join(SCRIPT_DIR, "STANDARD.md");
  const rootArg = argv.includes("--root") ? argv[argv.indexOf("--root") + 1] : path.resolve(SCRIPT_DIR, "..", "..");
  if (!existsSync(fileArg)) {
    console.error(`STDCHK FAIL 典章文件不存在:${fileArg}`);
    process.exit(1);
  }
  const text = readFileSync(fileArg, "utf8");
  const r = checkStandard(text, {
    exists: (p) => existsSync(path.join(rootArg, p)),
    readFile: (p) => {
      const abs = path.join(rootArg, p);
      return existsSync(abs) ? readFileSync(abs, "utf8") : null;
    },
  });
  for (const res of r.results) {
    console.log(`${res.ok ? "STDCHK OK  " : "STDCHK FAIL"} [${res.code}] ${res.msg}`);
  }
  const { articles, goldens, advice, mounts, primitives, statusCount } = r.counts;
  console.log(
    `standard-check: OK=${r.results.length - r.results.filter((x) => !x.ok).length} FAIL=${r.results.filter((x) => !x.ok).length} ` +
      `条文=${articles} 金标=${goldens} 建议=${advice} 挂点=${mounts} 原语=${primitives}(已有${statusCount["已有"] ?? 0}/半缺${statusCount["半缺"] ?? 0}/缺${statusCount["缺"] ?? 0})`,
  );
  process.exit(r.exitCode);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
