#!/usr/bin/env node
// gen-universe.mjs — 加源重实现基准宇宙构建器(票 #333 P2a;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md
// §重实现基准协议 + §定案 6)。
//
// 考题宇宙 = roster − 免考8(exam-rules.json 单源,判据 download_host='-')− 无 key
// 无法真跑下载的源(keyless-rules.json 名单 + 机械断言)− 无逐源测试的源
// (backend/tests/sources/test_<name>.py 不存在)。劈分沿 #322 的 40/13 形状
// (heldout = round(N×13/53)),类别分层最大余数法分席 + 类内 mulberry32(seed)
// 洗牌取留出——算法与 rrsi-domain/gen-split.mjs 同源(split-lib.mjs 单源)。
//
// 判据偏差记录(票面 vs 代码现实,以 spec 为准):票面无 key 判据写「源文件 __init__
// 读自有 env var 作 auth」;2026-10-17 sources-redesign T1 起 key 统一改使用点读取
// (download()/_url property,__init__ 不再捕获)。spec 只裁「无 key 无法真跑下载的
// 源」——故判据落点 = 源文件任意使用点读自有 auth env var,名单钉死在
// keyless-rules.json,生成器双向机械断言(登记 env 须真被读 + 反扫未登记的
// KEY|TOKEN|AUTH 形 env 读即红),漂移 fail-closed。
//
// 产物 data/universe.jsonl:meta 行 + 每源一行 {split,name,url,category,archetype,
// _why}。名字行是答案键载体:逐行带「禁词引用」豁免标记(leak 闸 + pre-commit
// 钩子同款放行,split.jsonl 同律)。生成器产 frozen=false;入仓冻结 = 人工检查后
// 手改 meta.frozen=true(名单钉死,重生成须先改回 false,禁静默重劈)。
//
// 用法:
//   node gen-universe.mjs [--roster-file PATH] [--meta-file PATH] [--exam-rules PATH]
//                         [--keyless PATH] [--backend DIR] [--out PATH] [--seed N]
//                         [--python BIN]
// 缺省:roster/meta 经 python 机械 dump(解释器缺省主检出 venv 绝对路径 + cwd=
// backend,AGENTS worktree 律;--roster-file/--meta-file 注入则零 python,测试路径)。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { parseRoster } from "../roster.mjs";
import { largestRemainder, mulberry32, shuffled } from "../rrsi-domain/split-lib.mjs";

const DEFAULT_SEED = 20261111;
const EXEMPTION = "禁词引用:#308 判例——加源考题答案键载体行,行级豁免";

// 源模块元数据机械 dump(url 面 + 原型族):url attr(多端点源为空串)+ 模块源文本中
// hostname 与本源 download host 一致的 http(s) 字面量(同 score.mjs DUMP_URLS_SCRIPT
// 判据——多端点源 url="" 真实地址在 _BASE_URL 常量);archetype = MRO 首个
// 命中的原型族名(CsvSource/IpListSource/Source,spec 验收「3 个原型族」同词表)。
const DUMP_META_SCRIPT = `
import inspect, json, re, sys
from urllib.parse import urlparse
from ipdb import _registry
ARCH = ["CsvSource", "IpListSource", "Source"]
out = {}
for s in _registry._sources:
    cls = s if isinstance(s, type) else type(s)
    try:
        src = inspect.getsource(sys.modules[cls.__module__])
    except Exception:
        src = ""
    url = getattr(s, "url", None)
    urls = [url] if isinstance(url, str) and url else []
    host = getattr(s, "download_host", None) or (urlparse(url).hostname if url else None) or "-"
    for lit in re.findall(r"https?://[A-Za-z0-9._~:/?#\\[\\]@!$&'()*+,;=%-]+", src):
        try:
            lh = urlparse(lit).hostname
        except Exception:
            continue
        if lh and lh == host:
            urls.append(lit)
    out[s.name] = {"urls": sorted(set(urls)),
                   "archetype": next((a for a in ARCH if a in [k.__name__ for k in cls.__mro__]), "other")}
print(json.dumps(out))
`;

// heldout 席位换算:沿 #322 的 40/13 形状(13/53 ≈ 24.5%)按考题数 N 缩放。
export function heldoutSeatsFor(n) {
  return Math.round((n * 13) / 53);
}

// ── 无 key 名单断言(双向 fail-closed)──
// 反扫完备性正则:KEY|TOKEN|AUTH 形 env 读,双习语面(os.environ.get 与 os.getenv,
// #333 P2a 评审备忘硬化:习语不同语义同,单扫一形会静默漏新 auth 源;置信度/限额/轮询
// 秒数类旋钮 env 不命中;内部聚合目录 env 不命中且其源本就免考)。 禁词引用:判据引用——各源旋钮 env 名实例
const AUTH_ENV_RE = /\bos\.(?:environ\.get|getenv)\(\s*"([A-Z0-9_]*(?:KEY|TOKEN|AUTH)[A-Z0-9_]*)"/g;

// 登记判据断言:源文件须真被读的 env 名(双习语形,同 AUTH_ENV_RE 面;格式漂移(换行/
// 异形)同样红——名单与代码分叉一律人裁,不猜等价)
const readsEnvVar = (src, env) => src.includes(`environ.get("${env}"`) || src.includes(`getenv("${env}"`);

function assertKeylessRules({ roster, keylessRules, backendDir, examNames }) {
  const entries = keylessRules.keyless ?? [];
  const rosterNames = new Set(roster.map((r) => r.name));
  const byName = new Map(entries.map((e) => [e.name, e]));
  for (const e of entries) {
    if (!e.name || !e.env || !e.reason)
      throw new Error(`keyless-rules 条目形坏(须 {name,env,reason}):${JSON.stringify(e)}`);
    if (!rosterNames.has(e.name)) throw new Error(`keyless 名单源不在 roster:${e.name}`);
    const srcPath = path.join(backendDir, "ipdb", "_sources", `${e.name}.py`);
    const src = fs.readFileSync(srcPath, "utf8");
    // 判据钉死同形(双习语:environ.get/getenv,本仓 7 源实测同形);格式漂移(换行/异形)
    // 同样红——名单与代码分叉一律人裁,不猜等价
    if (!readsEnvVar(src, e.env))
      throw new Error(`keyless 判据漂移:${e.name} 源文件不再读登记 env var ${e.env}(名单与代码分叉,须人裁)`);
  }
  // 反扫:考题候选面内任何 KEY|TOKEN|AUTH 形 env 读必须已登记,否则新 auth 源静默入考题
  for (const name of examNames) {
    if (byName.has(name)) continue;
    const srcPath = path.join(backendDir, "ipdb", "_sources", `${name}.py`);
    if (!fs.existsSync(srcPath)) continue;
    const m = [...fs.readFileSync(srcPath, "utf8").matchAll(AUTH_ENV_RE)].map((x) => x[1]);
    if (m.length)
      throw new Error(`未登记 auth env 读:${name} 读 ${m.join(", ")}(无 key 无法真跑下载,须人裁入 keyless-rules 再生成)`);
  }
  return new Set(entries.map((e) => e.name));
}

// ── 核心构建(纯函数,CLI 与测试共用)──
export function buildUniverse({ rosterText, metaDump, examRules, keylessRules, backendDir, seed = DEFAULT_SEED }) {
  const roster = parseRoster(rosterText);
  // 免考面单源 = exam-rules.json exempt[].name;判据交叉断言(download_host='-',
  // gen-split.mjs 同律)
  const exemptEntries = examRules.exempt ?? [];
  const exemptNames = new Set(exemptEntries.map((e) => e.name));
  for (const r of roster) {
    if (exemptNames.has(r.name) && r.host !== "-")
      throw new Error(`免考判据漂移:${r.name} 在 exam-rules 免考面但 download_host='${r.host}'≠'-'`);
  }
  const afterExempt = roster.filter((r) => !exemptNames.has(r.name));
  // 无 key 名单断言(在免考剔除后的面上做:免考源无下载面,不参与考题)
  const keylessNames = assertKeylessRules({ roster, keylessRules, backendDir, examNames: afterExempt.map((r) => r.name) });
  const afterKeyless = afterExempt.filter((r) => !keylessNames.has(r.name));
  // 无逐源测试剔除:打分钥匙 = 真测试文件装回,无测试即无钥匙,不入考题
  const noTestNames = new Set(afterKeyless.filter((r) => !fs.existsSync(path.join(backendDir, "tests", "sources", `test_${r.name}.py`))).map((r) => r.name));
  const exam = afterKeyless.filter((r) => !noTestNames.has(r.name));
  // meta dump 单源纪律:names 与 roster 全等(禁第二份清单静默漂移,score.mjs 答案表同律)
  const dumpNames = new Set(Object.keys(metaDump));
  for (const r of roster) if (!dumpNames.has(r.name)) throw new Error(`meta dump 缺 roster 源:${r.name}`);
  for (const n of dumpNames) if (!new Set(roster.map((r) => r.name)).has(n)) throw new Error(`meta dump 源不在 roster:${n}`);
  for (const r of exam) {
    const entry = metaDump[r.name];
    if (!entry || !Array.isArray(entry.urls) || !entry.urls.length)
      throw new Error(`考题 url 面缺失:${r.name}(url attr 空 + 同 host 字面量零;交接单预填前提,须人裁)`);
  }
  // 劈分:类别分层最大余数法分席 + 类内 mulberry32 洗牌取留出(类别/名字双字典序
  // 为 RNG 消费序,gen-split.mjs 同律)
  const H = heldoutSeatsFor(exam.length);
  const byCat = new Map();
  for (const r of exam) {
    if (!byCat.has(r.category)) byCat.set(r.category, []);
    byCat.get(r.category).push(r);
  }
  for (const list of byCat.values()) list.sort((x, y) => (x.name < y.name ? -1 : 1));
  const seats = largestRemainder(Object.fromEntries([...byCat].map(([c, l]) => [c, l.length])), H);
  const rng = mulberry32(seed);
  const heldout = new Map();
  for (const cat of [...byCat.keys()].sort()) {
    const picked = shuffled(byCat.get(cat).map((r) => r.name), rng).slice(0, seats.get(cat));
    for (const name of picked) heldout.set(name, cat);
  }
  const rows = [
    ...exam.filter((r) => heldout.has(r.name)).map((r) => ({ split: "heldout", ...r })),
    ...exam.filter((r) => !heldout.has(r.name)).map((r) => ({ split: "evolve", ...r })),
  ].map((r) => ({
    split: r.split,
    name: r.name,
    url: metaDump[r.name].urls[0],
    category: r.category,
    archetype: metaDump[r.name].archetype,
    _why: EXEMPTION,
  }));
  const meta = {
    kind: "ipradar-add-universe",
    version: 1,
    seed,
    rule: "roster − exam-rules 免考 − keyless-rules 无key − 无逐源测试;heldout = round(N×13/53)(沿 #322 40/13 形状);类别分层最大余数法分席(split-lib.largestRemainder)+ 类内 mulberry32(seed) 洗牌取留出;类别/名字双字典序为 RNG 消费序",
    total: exam.length,
    evolve: exam.length - H,
    heldout: H,
    heldoutSeats: Object.fromEntries([...seats.entries()].sort(([a], [b]) => (a < b ? -1 : 1))),
    rosterTotal: roster.length,
    exemptTotal: roster.length - afterExempt.length,
    keylessTotal: afterExempt.length - afterKeyless.length,
    noTestTotal: afterKeyless.length - exam.length,
    frozen: false, // 生成器只产未冻结件;入仓冻结 = 人工检查后手改 true(名单钉死,重生成须重裁)
    ticket: "#333",
  };
  return { meta, rows };
}

export function renderUniverseJsonl({ meta, rows }) {
  return [JSON.stringify(meta), ...rows.map((r) => JSON.stringify(r))].join("\n") + "\n";
}

// ── CLI ──
function parseArgs(argv) {
  const out = { rosterFile: null, metaFile: null, examRules: null, keyless: null, backend: null, out: null, seed: DEFAULT_SEED, python: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--roster-file") out.rosterFile = next();
    else if (a === "--meta-file") out.metaFile = next();
    else if (a === "--exam-rules") out.examRules = next();
    else if (a === "--keyless") out.keyless = next();
    else if (a === "--backend") out.backend = next();
    else if (a === "--out") out.out = next();
    else if (a === "--seed") out.seed = Number(next());
    else if (a === "--python") out.python = next();
    else if (a === "--help" || a === "-h") out.help = true;
    else { console.error(`未知参数:${a}`); process.exit(2); }
  }
  return out;
}

function resolvePython(flagged) {
  if (flagged) return flagged;
  if (process.env.BENCH_PYTHON) return process.env.BENCH_PYTHON;
  // worktree 判例(AGENTS.md;bench/score.mjs resolvePython 同款):worktree 无 venv,
  // 用主检出解释器绝对路径 + cwd=backend
  return "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python";
}

export function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    console.error("用法:node gen-universe.mjs [--roster-file PATH] [--meta-file PATH] [--exam-rules PATH] [--keyless PATH] [--backend DIR] [--out PATH] [--seed N] [--python BIN]");
    return 0;
  }
  const backend = args.backend ?? path.resolve(import.meta.dirname, "..", "..", "..", "..", "backend");
  const python = resolvePython(args.python);
  const rosterText = args.rosterFile
    ? fs.readFileSync(args.rosterFile, "utf8")
    : execFileSync(python, ["-m", "ipdb._registry", "--roster"], { cwd: backend, encoding: "utf8" });
  const metaDump = args.metaFile
    ? JSON.parse(fs.readFileSync(args.metaFile, "utf8"))
    : JSON.parse(execFileSync(python, ["-c", DUMP_META_SCRIPT], { cwd: backend, encoding: "utf8" }));
  const examRules = JSON.parse(fs.readFileSync(args.examRules ?? path.join(import.meta.dirname, "..", "exam-rules.json"), "utf8"));
  const keylessRules = JSON.parse(fs.readFileSync(args.keyless ?? path.join(import.meta.dirname, "keyless-rules.json"), "utf8"));
  const { meta, rows } = buildUniverse({ rosterText, metaDump, examRules, keylessRules, backendDir: backend, seed: args.seed });
  const outPath = args.out ?? path.join(import.meta.dirname, "data", "universe.jsonl");
  // 冻结件拒绝覆盖(#325 F2 同律):名单是答案分发面,已冻结禁被静默重写
  if (fs.existsSync(outPath)) {
    const head = fs.readFileSync(outPath, "utf8").split("\n")[0];
    let frozenHead = false;
    try { frozenHead = JSON.parse(head).frozen === true; } catch { /* 非法首行当未冻结件放行 */ }
    if (frozenHead) {
      console.error(`拒绝覆盖:${outPath} 是已冻结考题名单(frozen=true)。重劈须重走裁决——先手工把 meta.frozen 改回 false 再跑。`);
      process.exit(1);
    }
  }
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, renderUniverseJsonl({ meta, rows }));
  const stat = (s) => {
    const m = new Map();
    for (const r of rows.filter((r) => r.split === s)) m.set(r.category, (m.get(r.category) ?? 0) + 1);
    return [...m.entries()].map(([c, n]) => `${c}:${n}`).join(" ");
  };
  console.log(`考题宇宙 ${meta.total}(roster ${meta.rosterTotal} − 免考 ${meta.exemptTotal} − 无key ${meta.keylessTotal} − 无测试 ${meta.noTestTotal})`);
  console.log(`劈分 evolve ${meta.evolve} [${stat("evolve")}] / heldout ${meta.heldout} [${stat("heldout")}] → ${outPath}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  process.exit(main());
}
