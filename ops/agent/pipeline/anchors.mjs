// pipeline/anchors.mjs — 锚判例域词表装配层(B 稿 §2.2②,三件之二;P2,票 #164)。
// 宿主从旗标前置读数确定性选锚(零模型:域词 × 旗标 url/source/bucket/error_family 子串命中),
// 模型只补检索词;命中块仍走 lib.sh inject_precedents,HIT_CAP 8 不变(铁律⑦)。
// 消费面 = P3 DISPATCH 逐假设 bundle 判例命中(≤3 条)与 SYNTH 注入(P3 提示词层接管时接线,
// 本文件先落接口:load/anchorSelect 纯函数,selftest 可验)。锚→判例库闭包校验(锚指向缺件 =
// 编造路径)由 build-index.mjs --check 对真判例库执行,不在此重复(单一事实源)。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const HIT_CAP = 8; // 同 agent.mjs 铁律⑦(注入上限;锚命中并入后仍不越此线)

const ANCHORS_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "anchors-health.json");

export function loadAnchors(file = ANCHORS_FILE) { // 形状校验(域词/判例非空;库级闭包在 build-index --check)
  const raw = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!raw || !Array.isArray(raw.anchors)) throw new Error(`锚表形状坏:缺 anchors 数组(${file})`);
  for (const a of raw.anchors) {
    if (!a.domain || !Array.isArray(a.keywords) || !a.keywords.length
      || !Array.isArray(a.precedents) || !a.precedents.length)
      throw new Error(`锚条目形状坏(需 domain/keywords≥1/precedents≥1):${JSON.stringify(a).slice(0, 80)}`);
  }
  return { file, version: typeof raw.version === "number" ? raw.version : 0, anchors: raw.anchors };
}

// 纯函数选锚:域词命中任一旗标字段(url/source/error_family/bucket 子串,latin 忽略大小写)
// → 该域 precedents 入选;旗标集为空 → 空锚(静轮不注入,宁少算)。同判例多域只取一次,截 HIT_CAP。
export function anchorSelect(anchors, flags) {
  const hay = (flags ?? []).flatMap((f) => [f.url ?? "", f.source ?? "", f.error_family ?? "", f.bucket ?? ""])
    .map((s) => s.toLowerCase());
  const picked = [], seen = new Set();
  for (const a of anchors ?? []) {
    const hit = (a.keywords ?? []).some((k) => hay.some((h) => h.includes(k.toLowerCase())));
    if (!hit) continue;
    for (const p of a.precedents ?? []) {
      if (seen.has(p)) continue;
      seen.add(p);
      if (picked.length < HIT_CAP) picked.push(p);
    }
  }
  return picked;
}
