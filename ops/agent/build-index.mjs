#!/usr/bin/env node
// build-index.mjs — 判例库 _INDEX.md 召回地板生成器(B 稿 §2.2① 装配层三件之一;P2,票 #164)。
// 派生物:判例文件是唯一真源,本索引是可再生缓存(同库状态字节一致;判例永不改写,索引随时可重建——
// 「索引是地图不是存储」GLOSSARY/ADR 0007)。留痕判例(ruling-*)不进索引:档案非记忆面,rg 全文可检
// (B 稿 §5);锚表(anchors-health.json)闭包校验在本件 --check 面(锚判例域词表,B 稿 §2.2②)。
// 用法:node ops/agent/build-index.mjs [--docs-root DIR] [--check]
//   判例目录缺省 = $PRECEDENTS_DIR ?? <docs-root>/ops/precedents(DOCS_ROOT 缺省=仓根 docs 符号链接)。
//   --check:只校验锚表闭包与索引新度,不写盘(CI/自测面;锚指缺件/索引陈旧 = exit 1)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(AGENT_DIR, "..", "..");

// 判例 frontmatter 极简确定性解析(只取索引要的字段;机器 schema 真源仍是 _ops_store 判例校验)
export function parsePrecedentFm(text) {
  const fm = text.split(/^---\s*$/m)[1] ?? "";
  const val = (k) => { const m = fm.match(new RegExp(`^${k}:[ \\t]*(.*)$`, "m")); return m ? m[1].trim().replace(/^["']|["']$/g, "") : null; };
  const ctxBlock = (fm.match(/^context:[ \t]*>?\s*\n((?:[ \t]+.*\n?)*)/m) ?? [])[1] ?? "";
  return { subject: val("subject"), concept: val("concept"), superseded_by: val("superseded_by"), context: ctxBlock };
}
// 关键词:frontmatter(subject+context)确定性提取 latin token(≥3 字符,剥日期/URL;防 gist 漂移:不人写)
export function deriveKeywords(subject, context) {
  const toks = `${subject ?? ""} ${context ?? ""}`
    .replace(/https?:\/\/\S+/g, " ")
    .match(/[a-z0-9][a-z0-9.-]{2,}/gi) ?? [];
  return [...new Set(toks.map((t) => t.toLowerCase().replace(/[.-]+$/, "")))]
    .filter((t) => !/^\d{4}-\d{2}-\d{2}$/.test(t) && !/^(https?|www|com|org|net)$/.test(t)).slice(0, 8);
}
const clip = (s, n) => { s = s.trim(); return s.length > n ? `${s.slice(0, n - 1)}…` : s; };
// 概念词:concept 字段优先;旧文件从 subject 首句确定性截取(脚本规则不人写,B 稿 §3.1)
const conceptOf = (fm) => fm.concept ?? clip(String(fm.subject ?? "").split(/[—:((]/)[0], 16);

export function buildIndexText(files) { // files = [{name, fm}] 已按文件名序
  const rows = files.map(({ name, fm }) =>
    `| ${name} | ${clip(conceptOf(fm), 16)} | ${clip(String(fm.subject ?? ""), 48).replace(/\|/g, "\\|")} | ${deriveKeywords(fm.subject, fm.context).join(" ") || "—"} | ${fm.superseded_by && fm.superseded_by !== "null" ? "superseded" : "active"} |`);
  const sup = rows.filter((r) => r.endsWith("superseded |")).length;
  return [
    "<!-- 派生物可再生:判例文件是唯一真源,本文件由 scripts 重生成,勿手改(「索引是地图不是存储」,ADR 0007)。",
    "     rebuild: node ops/agent/build-index.mjs [--docs-root DIR](B 稿 §2.2①:spawn 前再生;同库状态字节一致)",
    "     留痕判例(ruling-*)不进索引:档案非记忆面,rg 全文可检(B 稿 §5)。 -->",
    "# 判例库索引(召回地板:库内任何概念至少一行 gist 在场,按名可读全文)",
    "",
    "| 文件名 | 概念词 | 一行主张 | 关键词 | 状态 |",
    "|---|---|---|---|---|",
    ...rows,
    "",
    `superseded: ${sup} 条(沿革见各文件 superseded_by)`,
  ].join("\n") + "\n";
}

// 锚判例域词表闭包校验(B 稿 §2.2②;结构与 _INDEX 同源=锚条目必须能落在真判例文件上,禁编造路径)
export function validateAnchors(anchors, fileNames) {
  if (!anchors || !Array.isArray(anchors.anchors)) throw new Error("anchors-health.json 形状坏:缺 anchors 数组");
  const exist = new Set(fileNames);
  for (const a of anchors.anchors) {
    if (!a.domain || !Array.isArray(a.keywords) || !a.keywords.length || !Array.isArray(a.precedents) || !a.precedents.length)
      throw new Error(`锚条目形状坏(需 domain/keywords≥1/precedents≥1):${JSON.stringify(a).slice(0, 80)}`);
    for (const p of a.precedents) if (!exist.has(p)) throw new Error(`锚指向缺件:${p}(域 ${a.domain};禁止编造路径)`);
  }
  return anchors.anchors.length;
}

function main() {
  const args = process.argv.slice(2);
  const flag = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
  const docsRoot = path.resolve(flag("--docs-root") ?? process.env.DOCS_ROOT ?? path.join(ROOT, "docs"));
  const precDir = process.env.PRECEDENTS_DIR ?? path.join(docsRoot, "ops", "precedents");
  const check = args.includes("--check");
  if (!fs.existsSync(precDir)) { console.error(`判例目录缺:${precDir}`); process.exit(2); }
  const all = fs.readdirSync(precDir).filter((f) => f.endsWith(".md") && !f.startsWith("_")).sort();
  const files = all.map((name) => ({ name, fm: parsePrecedentFm(fs.readFileSync(path.join(precDir, name), "utf8")) }));
  const concepts = files.filter((f) => !/^[\d-]+-ruling-/.test(f.name));
  const text = buildIndexText(concepts);
  const outPath = path.join(precDir, "_INDEX.md");
  // 锚表闭包(ops/agent/anchors-health.json,锚判例域词表;可指概念判例亦可指留痕判例——10-23 两假异常今日只有留痕面)
  let anchorsN = 0;
  const anchorsFile = path.join(AGENT_DIR, "anchors-health.json");
  if (fs.existsSync(anchorsFile)) {
    try { anchorsN = validateAnchors(JSON.parse(fs.readFileSync(anchorsFile, "utf8")), all); }
    catch (e) { console.error(`锚表校验败:${e.message}`); process.exit(1); }
  }
  if (check) {
    const stale = !fs.existsSync(outPath) || fs.readFileSync(outPath, "utf8") !== text;
    console.log(`INDEX-CHECK ${stale ? "STALE(可再生:node ops/agent/build-index.mjs)" : "FRESH"} 概念判例 ${concepts.length} 行,档案留痕 ${files.length - concepts.length} 条,锚域 ${anchorsN}`);
    if (stale) process.exit(1);
    return;
  }
  fs.writeFileSync(`${outPath}.tmp`, text);
  fs.renameSync(`${outPath}.tmp`, outPath); // 原子写(沿 _ops_store.atomic_write_text 判例)
  console.log(`INDEX-WROTE ${outPath} 概念判例 ${concepts.length} 行,档案留痕 ${files.length - concepts.length} 条,锚域 ${anchorsN}`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
