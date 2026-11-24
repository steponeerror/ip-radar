#!/usr/bin/env node
// add-lift.mjs — 手动加源 lift 工具链(半自动时代首件;#375 封存:原 run-fleet.mjs 的
// lift 侧提取,函数体逐字节搬入未重构;fleet 定时驱动器 run-fleet.mjs 随本提交退役移除)。
//
// 语义(用户裁决 2026-11-21 #375:自动化件移出仓;Q4 手动流程保留 runLift+三门):
//   lift(全在沙箱分支上,一次 commit):
//      文档三件(README 源表行+源数+1 双语、MANUAL 计数双语、CHANGELOG feed-add 条目,
//      数据取轮 a2-dossier.json)→ 基准重冻(11-18 判例 b9f9dc19 正路:gen-universe.mjs
//      与 rrsi gen-split.mjs 解冻→重生成→复冻,种子不变;测试钉同步)→ roster 钉同步
//      (test_metadata_derivation.py 快照行 + 发现冒烟计数,mirage #359 同步面)→
//      门三连(backend 全量 pytest / ops selftest / agent-v2 node --test)→
//      push + gh pr create --draft(标题 add/<source>,正文含轮四行数)。
//   与原 run-fleet ③ 的唯一差异=入口:队列轮询/沙箱构建/状态机/lark 告警随驱动器退役,
//   沙箱与轮目录由人给定(--sandbox + --round-id|--round-dir);合并人裁不变。
//
// 路径锚:docs 根缺省=env DOCS_ROOT ?? <主检出>/docs(嵌套 docs 仓只在主检出物化;
// git-common-dir 推导同 leak-check.mjs mainCheckoutRoot;工具检出=主检出时算式退化为
// 自身,原 run-fleet 路径锚律同)。dev/fleet 同锚(PR 正文落件)。
//
// 用法:node add-lift.mjs --sandbox <dir> --source <slug> (--round-id <id> | --round-dir <dir>)
//        [--docs-root DIR] [--dev-root DIR]
// 退出码:0=lift 成功;1=lift 失败/门红;2=用法错;3=运行期异常。
// stdout 末行=单行 JSON lift 信封(ENVELOPE.md 律:进度走 stderr)。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { resolveAddPython } from "./run-add.mjs"; // 沙箱测试解释器推导(worktree 律单源);加载序锚:先拉 run-add 侧再拉 tasks/add-round(环从 run-add 面解,gen-exam-cards 同律——倒序在 tasks/index.mjs 撞 addRoundTask TDZ)
import { mainCheckoutRoot } from "./bench/leak-check.mjs"; // 主检出锚单源(git-common-dir)
import { parseRoster } from "./bench/roster.mjs"; // roster dump 行解析单源
import { heldoutSeatsFor } from "./bench/add-domain/gen-universe.mjs"; // heldout=round(N×13/53) 形状律单源

const execFileP = promisify(execFileCb);
export const ROOT = path.resolve(import.meta.dirname, "..", ".."); // ops/agent-v2 → 工具所在检出仓根
export const SOURCE_SHAPE = /^[a-z0-9_]{1,32}$/; // run-add --source 同形(输入域单源注释)
const ROUND_ID_RE = /^\d{4}-\d{2}-\d{2}-\d{4}-add(-r\d+)?$/; // run-add 轮 id 形状律
// ── lift 文本变换(全部「恰一命中」fail-closed:钉面漂移=红,不静默)──
const sub1 = (text, re, build, what) => {
  const g = new RegExp(re.source, re.flags.includes("g") ? re.flags : `${re.flags}g`); // matchAll 须 g(计数与替换同集)
  const hits = [...String(text).matchAll(g)];
  if (hits.length !== 1) throw new Error(`钉面漂移:${what} 期望恰 1 处命中,实 ${hits.length}(frost 面改版须同步本变换)`);
  return String(text).replace(g, (...a) => build(...a));
};

export function bumpReadmeCount(text) {
  return sub1(text, /(Pull )(\d+)( public sources)/, (m, a, n, b) => `${a}${Number(n) + 1}${b}`, "README 源数口径行");
}
export function bumpReadmeZhCount(text) {
  return sub1(text, /(把 )(\d+)( 个公开情报源搬回家)/, (m, a, n, b) => `${a}${Number(n) + 1}${b}`, "README.zh 源数口径行");
}
export function bumpManualCounts(text, { keyless }) {
  return sub1(text, /(keyless feed \()(\d+)( of the )(\d+)( sources\))/,
    (m, a, n1, b, n2, c) => `${a}${Number(n1) + (keyless ? 1 : 0)}${b}${Number(n2) + 1}${c}`, "MANUAL 首启计数");
}
export function bumpManualImageAlt(text) {
  return sub1(text, /(\d+)( sources \()(\d+)( public \+ 1 private honeypot\))/,
    (m, n1, a, n2, b) => `${Number(n1) + 1}${a}${Number(n2) + 1}${b}`, "MANUAL 截图 alt 计数");
}
export function bumpManualZhCounts(text, { keyless }) {
  const t = sub1(text, /(（)(\d+)( 个源中的 )(\d+)( 个）)/,
    (m, a, n1, b, n2, c) => `${a}${Number(n1) + 1}${b}${Number(n2) + (keyless ? 1 : 0)}${c}`, "MANUAL.zh 首启计数");
  return sub1(t, /(\d+)( 源（)(\d+)( 公开 \+ 1 私有蜜罐）)/,
    // 括号全角:frost 面改版(e6e2ac96 文档同步)把 MANUAL.zh-CN 截图 alt 的计数括号从
    // 半角「源(70 公开 + 1 私有蜜罐)」改成全角「源（70 公开 + 1 私有蜜罐）」,钉随全角
    (m, n1, a, n2, b) => `${Number(n1) + 1}${a}${Number(n2) + 1}${b}`, "MANUAL.zh 截图 alt 计数");
}

// README 源表行:插进 category 对应节的表尾(节内最后一行 | 行之后;节缺席=红)
export const README_SECTION_OF = Object.freeze({ threat: "Threat Reputation", geo_asn: "Geo & ASN", asset: "Network Assets" });
export const README_ZH_SECTION_OF = Object.freeze({ threat: "威胁信誉", geo_asn: "地理与 ASN", asset: "网络资产" });
export function insertReadmeRow(text, sectionTitle, row) {
  const lines = String(text).split("\n");
  const h = lines.findIndex((l) => l.trim() === `### ${sectionTitle}`);
  if (h < 0) throw new Error(`README 节缺席:### ${sectionTitle}`);
  let last = -1;
  for (let i = h + 1; i < lines.length; i++) {
    if (lines[i].startsWith("###")) break;
    if (lines[i].startsWith("|")) last = i;
  }
  if (last < 0) throw new Error(`README 节 ### ${sectionTitle} 无表格行`);
  lines.splice(last + 1, 0, row);
  return lines.join("\n");
}

// rrsi 劈分测试钉同步(b9f9dc19 判例的机械面:数字钉+注记追加)
// 注记措辞=中性「<tag> 再冻结」(#425):「fleet」词已随 #375 驱动器退役,模板再带它=下次手动
// lift 把退役词写回钉注。三条注记正则保留原注记、只在其后追加「<tag> 再冻结」(#437:原先整段
// 重写,下次 lift 会把 #414 留在钉注里的出处——撤源/进源明细——换成一句「<日期> 再冻结」)。
// 追加形=原注记 + ";" + 「<tag> 再冻结」;原注记空(钉面被手改)则只写新注记,不留「;;」。
// 正则两组:组 1=原注记(不含消息自己的右括号),组 2=该右括号——接受面与原整段重写款相同。
const appendNote = (note, tag) => `${note ? `${note};` : ""}${tag} 再冻结`;
export function syncRrsiSplitPins(text, { evolve, heldout, total, rosterTotal, exempt, tag }) {
  let t = String(text);
  t = sub1(t, /结构不变式:\d+ 演化 \+ \d+ 留出/, () => `结构不变式:${evolve} 演化 + ${heldout} 留出`, "rrsi-split 测试标题钉");
  t = sub1(t, /assert\.equal\(meta\.evolve, \d+\);/, () => `assert.equal(meta.evolve, ${evolve});`, "meta.evolve 钉");
  t = sub1(t, /assert\.equal\(meta\.heldout, \d+\);/, () => `assert.equal(meta.heldout, ${heldout});`, "meta.heldout 钉");
  t = sub1(t, /assert\.equal\(rows\.length, \d+, "考题总数 = \d+\(\d+ 源 − \d+ 免考;([^"]*)(\))"\);/,
    (m, note, close) => `assert.equal(rows.length, ${total}, "考题总数 = ${total}(${rosterTotal} 源 − ${exempt} 免考;${appendNote(note, tag)}${close}");`, "rows.length 钉");
  t = sub1(t, /assert\.equal\(evolve\.length, \d+\);/, () => `assert.equal(evolve.length, ${evolve});`, "evolve.length 钉");
  t = sub1(t, /assert\.equal\(heldout\.length, \d+\);/, () => `assert.equal(heldout.length, ${heldout});`, "heldout.length 钉");
  t = sub1(t, /assert\.equal\(new Set\(names\)\.size, \d+, "无重复"\);/, () => `assert.equal(new Set(names).size, ${total}, "无重复");`, "names 去重钉");
  // 右括号写成 [)] 而非 \):V8 正则字面量里「\) + 反引号」连写会报 Unterminated group(2026-11-24 实测 Node v22.23.2,#437)
  t = sub1(t, /assert\.equal\(exam\.length, \d+, `真 roster 考题数漂移:\$\{exam\.length\} ≠ \d+——冻结名单须重裁\(([^`]*)([)])`\);/,
    (m, note, close) => "assert.equal(exam.length, " + total + ", `真 roster 考题数漂移:${exam.length} ≠ " + total + "——冻结名单须重裁(" + appendNote(note, tag) + close + "`);", "exam.length 钉");
  return t;
}
export function syncRrsiDomainPin(text, { total, tag }) {
  return sub1(String(text), /assert\.equal\(criticProbe\.total, \d+, "每考题一行一针\(\d+ 行;([^"]*)(\))"\);/,
    (m, note, close) => `assert.equal(criticProbe.total, ${total}, "每考题一行一针(${total} 行;${appendNote(note, tag)}${close}");`, "critic 针数钉");
}

// 发现冒烟计数钉(test_b_family_url_filename_guard.py;mirage #359「roster 钉同步」同面)
export function bumpDiscoverySmokePin(text, { total, source, tag }) {
  return sub1(String(text), /^(.*assert len\(sources\) == )(\d+)(\s*#\s*本票时点 roster;增删源时同步\()([^)]*)(\))$/m,
    (m, a, n, c, note) => `${a}${total}${c}${note} + ${tag} 手动 lift ${source} 接入 ${n}→${total})`, "发现冒烟计数钉");
}

// roster 快照行插入(test_metadata_derivation.py OLD_CATEGORIES/OLD_RELIABILITY;已在=幂等跳过)
export function insertSnapshotRow(text, dictName, line) {
  const t = String(text);
  const start = t.indexOf(`${dictName} = {`);
  if (start < 0) throw new Error(`快照块缺席:${dictName}`);
  const end = t.indexOf("\n}", start);
  if (end < 0) throw new Error(`快照块不闭合:${dictName}`);
  if (t.slice(start, end).includes(`"${line.match(/"([a-z0-9_]+)":/)[1]}"`)) return t; // 已在(轮 IMPLEMENT 可能已同步)=幂等
  return `${t.slice(0, end)}\n${line}${t.slice(end)}`;
}

// 裁剪:长字段进 CHANGELOG/PR 的可读上界
export const clip = (s, n = 160) => { const t = String(s ?? "").replace(/\s+/g, " ").trim(); return t.length > n ? `${t.slice(0, n)}…` : t; };

// CHANGELOG feed-add 条目(双语对;数据全取轮 a2-dossier.json;措辞如实=手动 lift:#375 起 fleet 驱动器
// 退役,由人跑 add-lift.mjs;条目由脚本生成,合并前可润色。措辞=用户裁定 2026-11-24 #437)
export function changelogEntries({ source, dossier, roundId, stats, prNumber }) {
  const zh = `  - **威胁源接入:${source}(${dossier.name};手动 lift,加源轮 ${roundId}${prNumber ? `,draft PR #${prNumber}` : ""})**:加源轮全相位绿后手动 lift(#375 起 fleet 驱动器退役,由人跑 add-lift.mjs)——格式:${clip(dossier.format)};鉴权:${clip(dossier.auth, 100)};节奏:${clip(dossier.cadence, 100)};字段路由草案:${clip((dossier.field_routing ?? []).join(";"), 160)};样本 ${Array.isArray(dossier.samples) ? dossier.samples.length : 0} 行(实抓,见轮工件)。轮四行数:模型调用 ${stats.model_calls} / 总 tokens ${stats.totalTokens} / 花费 ¥${stats.cost.toFixed(8)} / 墙钟 ${stats.wall_s.toFixed(1)}s。门:backend 全量 pytest + ops selftest + agent-v2 node --test 三绿(沙箱分支);合并人裁(加源轮产出永不自并入 master)。本条目由脚本生成,合并前人面可润色。`;
  const en = `  - **Threat-feed add: ${source} (${dossier.name}; manual lift, add-round ${roundId}${prNumber ? `, draft PR #${prNumber}` : ""})**: lifted manually after a fully green add-round (the fleet driver was retired in #375; a human runs add-lift.mjs) — format: ${clip(dossier.format)}; auth: ${clip(dossier.auth, 100)}; cadence: ${clip(dossier.cadence, 100)}; field-routing draft: ${clip((dossier.field_routing ?? []).join("; "), 160)}; ${Array.isArray(dossier.samples) ? dossier.samples.length : 0} sample rows (live-captured, see round artifacts). Round four numbers: model calls ${stats.model_calls} / total tokens ${stats.totalTokens} / cost ¥${stats.cost.toFixed(8)} / wall ${stats.wall_s.toFixed(1)}s. Gates: full backend pytest + ops selftest + agent-v2 node --test all green (sandbox branch); merge is a human ruling (add-round output never self-merges into master). This entry is script-generated; polish before merging is welcome.`;
  return { zh, en };
}

export function composePrBody({ source, card = null, roundId, dossier, stats, gates, rosterTotal, universe, split, seats }) {
  return [
    `# add/${source} — 手动 lift(加源轮 ${roundId};#375 起 fleet 驱动器退役,由人跑 add-lift.mjs)`,
    "",
    `- **轮**:\`${roundId}\`(加源轮 VERIFY→DOSSIER→IMPLEMENT→GATE→REPORT→CLOSE 全绿;沙箱 TDD 先红后绿)`,
    `- **队列卡**:\`${card ?? source}\`(docs/ops/queue.md APPROVE 行;卡 id 与 registry 名可不同,${card && card !== source ? `本例卡 ${card} → registry ${source}` : "本例同名"})`,
    `- **源**:${dossier.name} — ${dossier.url}`,
    `- **格式**:${clip(dossier.format, 200)}`,
    `- **样本**:${(dossier.samples ?? []).slice(0, 3).join(" / ")}`,
    "",
    `**轮四行数**:模型调用 ${stats.model_calls} / 总 tokens ${stats.totalTokens} / 花费 ¥${stats.cost.toFixed(8)} / 墙钟 ${stats.wall_s.toFixed(1)}s`,
    "",
    "**lift 内容**(沙箱分支一次 commit):README 源表行+源数+1(双语)、MANUAL 计数(双语)、",
    `CHANGELOG feed-add 条目;add-domain 基准解冻→重生成→复冻(universe ${universe.before}→${universe.after},种子不变);`,
    `rrsi 劈分同法(${split.before}→${split.after},heldout 席位 round(N×13/53)=${seats});roster 钉同步`,
    "(test_metadata_derivation 快照行 + 发现冒烟计数);roster 总数 " + `${rosterTotal.before}→${rosterTotal.after}。`,
    "",
    `**门三连**:${gates.map((g) => `${g.name} ${g.pass ? "✅" : "❌"}`).join(" / ")}`,
    "",
    "合并人裁(加源轮产出永不自并入 master;#366 语义)。轮工件:`docs/ops/rounds/${roundId}/`(嵌套 docs 仓)。",
    "",
    `_本 PR 由人跑 add-lift.mjs 手动开出;CHANGELOG 条目由脚本生成,合并前可润色。_`,
  ].join("\n");
}

// ── 小工具 ──
function readJsonIf(p) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } }

async function git(cwd, args, opts = {}) {
  try {
    const { stdout } = await execFileP("git", ["-C", cwd, ...args], { timeout: opts.timeoutMs ?? 120_000, maxBuffer: 32 * 1024 * 1024 });
    return String(stdout ?? "").trim();
  } catch (e) {
    throw Object.assign(new Error(`git ${args.join(" ")} 红:${String(e.stderr ?? e.message).slice(0, 300)}`), { code: "infra" });
  }
}
const tailOf = (s, n = 60) => String(s ?? "").trimEnd().split("\n").slice(-n).join("\n");

// 冻结位翻转(jsonl 首行 meta 的 frozen 布尔)。两形态都认:入仓手改形 `"frozen": true`(带空格)
// 与生成器产出形 `"frozen":false`(紧凑;gen-universe.mjs:189 生成器只产未冻结件)。写回统一带空格形
// (仓内风格)。幂等:目标值已在=无操作;首行缺键时 value=false 无操作、value=true 在尾}前插键。
export function setFrozenFlag(jsonlPath, value) {
  const text = fs.readFileSync(jsonlPath, "utf8");
  const nl = text.indexOf("\n");
  const first = nl < 0 ? text : text.slice(0, nl);
  const rest = nl < 0 ? "" : text.slice(nl);
  const hits = [...first.matchAll(/"frozen":\s*(true|false)/g)];
  if (hits.length > 1) throw new Error(`冻结位翻转失败:${jsonlPath} 首 meta frozen 键命中 ${hits.length} 处(期望恰 1)`);
  const to = value ? '"frozen": true' : '"frozen": false';
  let outFirst;
  if (hits.length === 0) {
    if (!value) return; // 无键=本就未冻结
    if (!first.trimEnd().endsWith("}")) throw new Error(`冻结位翻转失败:${jsonlPath} 首 meta 无 frozen 键且非 JSON 对象尾,无法插键`);
    outFirst = `${first.trimEnd().slice(0, -1)},"frozen": true}`; // 冻结但缺键(罕见面):插键
  } else {
    if ((hits[0][1] === "true") === value) return; // 幂等
    outFirst = first.replace(/"frozen":\s*(true|false)/, to);
  }
  fs.writeFileSync(jsonlPath, outFirst + rest);
}
const readJsonlMeta = (p) => JSON.parse(fs.readFileSync(p, "utf8").split("\n")[0]);

// 轮产 stem 真源:a3-implement.json 的 stem(add-round 门钉 summary.name===stem,
// slugify(dossier.name) 派生)。队列卡 id(如 sgb_blocklist)与 registry 名(如
// gorkemgun_sgb_blocklist,slugify("gorkemgun/sgb-blocklist"))可不同——lift 一切
// registry 面(README 行/快照行/钉注记/PR 标题)以 stem 为准,卡 id 只作追溯面。
export function roundStemOf(roundDir, io = { readJsonIf }) {
  const a3 = io.readJsonIf(path.join(roundDir, "a3-implement.json"));
  const stem = typeof a3?.stem === "string" ? a3.stem : "";
  return SOURCE_SHAPE.test(stem) ? stem : null;
}

class LiftError extends Error {
  constructor(step, message) { super(message); this.step = step; }
}

// ── lift 主链(沙箱分支上;每步 throw LiftError → 失败路径)──
export async function runLift({ sandbox, roundDir, fleetRoot, devRoot, python, source, roundId, log, exec = execFileP, now = new Date() }) {
  const tag = `${now.toISOString().slice(0, 10)}`;
  // 1. 交接单(数据真源)
  const dossier = readJsonIf(path.join(roundDir, "a2-dossier.json"))?.dossier;
  if (!dossier?.name || !dossier?.url) throw new LiftError("dossier", "a2-dossier.json 缺席或形状坏(dossier.name/url 缺)");
  const stats9 = readJsonIf(path.join(roundDir, "09-budget.json"))?.readings;
  const stem = roundStemOf(roundDir);
  if (!stem) throw new LiftError("dossier", "a3-implement.json 缺 stem 或形状坏(registry 名真源;卡 id≠registry 名时不可用卡 id 代替)");
  // 2. roster diff:沙箱相对基线(fleet 检出=origin/master 内容)恰增一源(=轮 stem)
  const rosterDump = async (backendDir) => (await exec(python, ["-m", "ipdb._registry", "--roster"], { cwd: backendDir, timeout: 120_000, maxBuffer: 16 * 1024 * 1024 })).stdout;
  const baseRows = parseRoster(await rosterDump(path.join(fleetRoot, "backend")));
  const newRows = parseRoster(await rosterDump(path.join(sandbox, "backend")));
  const baseNames = new Set(baseRows.map((r) => r.name));
  const added = newRows.filter((r) => !baseNames.has(r.name));
  if (added.length !== 1 || added[0].name !== stem)
    throw new LiftError("roster-diff", `沙箱 roster 增员异常:期望恰轮 stem [${stem}](卡 ${source}),实 [${added.map((r) => r.name).join(",")}]`);
  const rosterTotal = { before: baseRows.length, after: newRows.length };
  // 新源 category/reliability(快照行与 README 节数据源)
  const meta = JSON.parse((await exec(python, ["-c",
    "import json,ipdb._registry as r,ipdb._merge as m;print(json.dumps({'category':r.SOURCE_CATEGORIES.get('%s'),'reliability':m.SOURCE_RELIABILITY.get('%s')}))".replace(/%s/g, stem)],
    { cwd: path.join(sandbox, "backend"), timeout: 60_000, maxBuffer: 1024 * 1024 })).stdout);
  if (meta.category == null || meta.reliability == null)
    throw new LiftError("roster-diff", `新源 ${stem} 缺 category/reliability 声明(SOURCE_CATEGORIES/SOURCE_RELIABILITY)`);
  const keyed = JSON.parse(fs.readFileSync(path.join(sandbox, "ops", "agent-v2", "bench", "add-domain", "keyless-rules.json"), "utf8"))
    .keyless.some((e) => e.name === stem);
  // 3. 文档三件
  const edit = (rel, fn, what) => {
    const p = path.join(sandbox, rel);
    fs.writeFileSync(p, fn(fs.readFileSync(p, "utf8")));
    log(`[lift] ${what}: ${rel}`);
  };
  const contributes = clip(dossier.format, 90); // 只写格式,与其他行一致(#437:原来源尾注带退役词「fleet-lifted」,手动 lift 没有可写的来源标签)
  const provider = dossier.name;
  const row = `| ${stem} | [${provider}](${dossier.url}) | ${contributes} | |`;
  edit("README.md", (t) => insertReadmeRow(bumpReadmeCount(t), README_SECTION_OF[added[0].category] ?? "Threat Reputation", row), "README 计数+源表行");
  edit("README.zh-CN.md", (t) => insertReadmeRow(bumpReadmeZhCount(t), README_ZH_SECTION_OF[added[0].category] ?? "威胁信誉", row), "README.zh 计数+源表行");
  edit("MANUAL.md", (t) => bumpManualImageAlt(bumpManualCounts(t, { keyless: !keyed })), "MANUAL 计数");
  edit("MANUAL.zh-CN.md", (t) => bumpManualZhCounts(t, { keyless: !keyed }), "MANUAL.zh 计数");
  const entries = changelogEntries({ source: stem, dossier, roundId, stats: { model_calls: stats9?.model_calls ?? 0, totalTokens: envelopeUsage(roundDir).totalTokens, cost: envelopeUsage(roundDir).cost, wall_s: stats9?.wall_s ?? 0 } });
  edit("CHANGELOG.md", (t) => {
    const i = t.indexOf("### 新增 Added");
    if (i < 0) throw new LiftError("docs", "CHANGELOG 缺 ### 新增 Added 节");
    const j = t.indexOf("\n", i) + 1;
    return `${t.slice(0, j)}\n${entries.zh}\n${entries.en}\n${t.slice(j)}`;
  }, "CHANGELOG feed-add 条目");
  // 4. 基准重冻(11-18 判例正路:解冻→重生成→复冻,种子不变)
  const uniPath = path.join(sandbox, "ops", "agent-v2", "bench", "add-domain", "data", "universe.jsonl");
  const uniBefore = readJsonlMeta(uniPath);
  setFrozenFlag(uniPath, false);
  await exec("node", ["bench/add-domain/gen-universe.mjs", "--python", python], { cwd: path.join(sandbox, "ops", "agent-v2"), timeout: 180_000, maxBuffer: 8 * 1024 * 1024 });
  setFrozenFlag(uniPath, true);
  const uniAfter = readJsonlMeta(uniPath);
  if (uniAfter.rosterTotal !== rosterTotal.after) throw new LiftError("refreeze", `universe meta rosterTotal ${uniAfter.rosterTotal} ≠ 沙箱 roster ${rosterTotal.after}`);
  const splitPath = path.join(sandbox, "ops", "agent-v2", "bench", "rrsi-domain", "data", "split.jsonl");
  const dumpFile = path.join(sandbox, "ops", "agent-v2", "bench", "rrsi-domain", "data", ".fleet-roster-dump.txt");
  fs.writeFileSync(dumpFile, await rosterDump(path.join(sandbox, "backend")));
  const exempt = JSON.parse(fs.readFileSync(path.join(sandbox, "ops", "agent-v2", "bench", "exam-rules.json"), "utf8"))
    .exempt.map((e) => e.name);
  const examN = newRows.length - exempt.length;
  const seats = heldoutSeatsFor(examN);
  const splitBefore = readJsonlMeta(splitPath);
  setFrozenFlag(splitPath, false);
  await exec("node", ["bench/rrsi-domain/gen-split.mjs", "--roster-file", dumpFile, "--evolve", String(examN - seats), "--heldout", String(seats)],
    { cwd: path.join(sandbox, "ops", "agent-v2"), timeout: 120_000, maxBuffer: 8 * 1024 * 1024 });
  setFrozenFlag(splitPath, true);
  fs.rmSync(dumpFile, { force: true });
  const splitAfter = readJsonlMeta(splitPath);
  // 5. 测试钉 + roster 快照同步
  edit("ops/agent-v2/tests/rrsi-split.test.mjs", (t) => syncRrsiSplitPins(t, { evolve: splitAfter.evolve, heldout: splitAfter.heldout, total: splitAfter.total, rosterTotal: splitAfter.rosterTotal, exempt: splitAfter.exemptTotal, tag }), "rrsi-split 钉同步");
  edit("ops/agent-v2/tests/rrsi-domain.test.mjs", (t) => syncRrsiDomainPin(t, { total: splitAfter.total, tag }), "rrsi-domain 针数钉");
  edit("backend/tests/sources/test_b_family_url_filename_guard.py", (t) => bumpDiscoverySmokePin(t, { total: rosterTotal.after, source: stem, tag }), "发现冒烟计数钉");
  edit("backend/tests/core/test_metadata_derivation.py", (t) => insertSnapshotRow(insertSnapshotRow(t, "OLD_CATEGORIES",
    `    "${stem}": "${meta.category}",   # ${tag} 手动 lift`) , "OLD_RELIABILITY",
    `    "${stem}": ${meta.reliability},   # ${tag} 手动 lift`), "metadata 快照行");
  // 6. lift commit。提交人=执行者自己的 git 身份(#437:原先用 -c 项写死驱动器身份的 user.email / user.name,
  // 手动 lift 由人跑,没有驱动器身份可冒——执行者 git 未配身份时 git 在此报错=如实,不代填)
  await git(sandbox, ["add", "-A"]);
  await git(sandbox, ["-c", "commit.gpgsign=false",
    "commit", "-m", `lift(#366): 文档三件+基准重冻+roster 钉同步(${stem};卡 ${source};加源轮 ${roundId})`]);
  // 7. 门三连
  const gates = [
    { name: "backend 全量 pytest", cmd: [python, "-m", "pytest", "-q", "--durations=15"], cwd: path.join(sandbox, "backend"), timeoutMs: 30 * 60_000 },
    { name: "ops selftest", cmd: ["bash", path.join(sandbox, "ops", "pipeline-core", "selftest.sh")], cwd: sandbox, timeoutMs: 15 * 60_000 },
    { name: "agent-v2 node --test", cmd: ["npm", "test"], cwd: path.join(sandbox, "ops"), timeoutMs: 15 * 60_000 }, // #412 单包:npm test 自 ops/ 包根跑(agent-v2/tests/ 相对包根)
  ];
  const gateResults = [];
  // 判例 2026-11-21(过夜五败根因):timer 单元为 lark 告警配了 IP_RADAR_ALERT_URLS,
  // 门进程继承后 ops selftest 的 finding-出口两案例红(它们钉「未配置=降级跳过」行为面)。
  // 门环境必须确定性:剥离该变量(实锤:unset 下 PASS=119/FAIL=0,配了 PASS=118/FAIL=1)。
  const gateEnv = { ...process.env };
  delete gateEnv.IP_RADAR_ALERT_URLS;
  for (const g of gates) {
    log(`[lift] 门:${g.name} …`);
    try {
      const r = await exec(g.cmd[0], g.cmd.slice(1), { cwd: g.cwd, timeout: g.timeoutMs, maxBuffer: 64 * 1024 * 1024, env: gateEnv });
      gateResults.push({ name: g.name, pass: true, tail: tailOf(r.stdout) });
    } catch (e) {
      gateResults.push({ name: g.name, pass: false, tail: tailOf(`${e.stdout ?? ""}\n${e.stderr ?? ""}\n${e.message}`) });
      throw new LiftError(`gate:${g.name}`, `${g.name} 红(尾 60 行已留档):\n${gateResults.at(-1).tail}`);
    }
    log(`[lift] 门:${g.name} 绿`);
  }
  // 8. push + draft PR(合并人裁)
  const branch = await git(sandbox, ["rev-parse", "--abbrev-ref", "HEAD"]);
  await git(sandbox, ["push", "-u", "origin", branch], { timeoutMs: 300_000 });
  const stats = { model_calls: stats9?.model_calls ?? 0, ...envelopeUsage(roundDir), wall_s: stats9?.wall_s ?? 0 };
  const body = composePrBody({ source: stem, card: source, roundId, dossier, stats, gates: gateResults.map((g) => ({ name: g.name, pass: g.pass })), rosterTotal, universe: { before: uniBefore.total, after: uniAfter.total }, split: { before: splitBefore.total, after: splitAfter.total }, seats });
  const bodyFile = path.join(devRoot, `${roundId}-pr-body.md`);
  fs.mkdirSync(path.dirname(bodyFile), { recursive: true });
  fs.writeFileSync(bodyFile, body);
  const prUrl = await exec("gh", ["pr", "create", "--draft", "--repo", "steponeerror/ip-radar", "--base", "master", "--head", branch,
    "--title", `add/${stem}`, "--body-file", bodyFile], { timeout: 120_000, maxBuffer: 1024 * 1024 });
  const prNumber = (prUrl.stdout.trim().match(/\/pull\/(\d+)/) ?? [])[1] ?? null;
  return { pr: prUrl.stdout.trim(), prNumber, branch, rosterTotal, universe: { before: uniBefore.total, after: uniAfter.total }, split: { before: splitBefore.total, after: splitAfter.total }, gates: gateResults, stats, dossier };
}

function envelopeUsage(roundDir) {
  const b = readJsonIf(path.join(roundDir, "09-budget.json"))?.readings?.usage;
  return { totalTokens: b?.totalTokens ?? 0, cost: b?.cost ?? 0 };
}

// ── CLI(手动入口;#375 半自动时代:沙箱与轮目录由人给定,无队列轮询/状态机)──
function usage() {
  process.stderr.write(`用法:node add-lift.mjs --sandbox <dir> --source <slug> (--round-id <id> | --round-dir <dir>) [--docs-root DIR] [--dev-root DIR]\n`);
}
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--sandbox") out.sandbox = next();
    else if (a === "--source") out.source = next();
    else if (a === "--round-id") out.roundId = next();
    else if (a === "--round-dir") out.roundDir = next();
    else if (a === "--docs-root") out.docsRoot = next();
    else if (a === "--dev-root") out.devRoot = next();
    else if (a === "--help" || a === "-h") out.help = true;
    else { process.stderr.write(`未知参数:${a}\n`); out.bad = true; }
  }
  return out;
}

export async function main(argv = process.argv.slice(2), io = {}) {
  const args = parseArgs(argv);
  if (args.help || args.bad) { usage(); return 2; }
  if (!args.sandbox || !args.source || !(args.roundDir ?? args.roundId)) { usage(); process.stderr.write("--sandbox/--source 与 --round-id(或 --round-dir)必填\n"); return 2; }
  if (!SOURCE_SHAPE.test(args.source)) { usage(); process.stderr.write(`--source 形状坏(run-add 同形 [a-z0-9_]{1,32}):${args.source}\n`); return 2; }
  if (args.roundId && !ROUND_ID_RE.test(args.roundId)) { usage(); process.stderr.write(`--round-id 形状坏(run-add 轮 id 形状律 YYYY-MM-DD-HHMM-add):${args.roundId}\n`); return 2; }
  const log = io.log ?? ((l) => process.stderr.write(`${l}\n`));
  const env = io.env ?? process.env;
  const exec = io.exec ?? execFileP;
  const anchor = mainCheckoutRoot(ROOT) ?? ROOT; // 主检出锚(docs 嵌套仓/dev 物化地;主检出自身退化形,原 run-fleet 同律)
  const docsRoot = path.resolve(args.docsRoot ?? env.DOCS_ROOT ?? path.join(anchor, "docs"));
  const roundDir = args.roundDir ? path.resolve(args.roundDir) : path.resolve(docsRoot, "ops", "rounds", args.roundId);
  const devRoot = path.resolve(args.devRoot ?? env.FLEET_DEV_ROOT ?? path.join(anchor, "dev", "fleet"));
  const roundId = args.roundId ?? path.basename(roundDir);
  const sandboxRoot = path.resolve(args.sandbox);
  try {
    const lift = await runLift({ sandbox: sandboxRoot, roundDir, fleetRoot: ROOT, devRoot, python: resolveAddPython(env), source: args.source, roundId, log, exec });
    process.stdout.write(`${JSON.stringify({ ok: true, cmd: "add-lift", source: args.source, round_id: roundId, sandbox: sandboxRoot, branch: lift.branch, pr: lift.pr, pr_number: lift.prNumber, roster_total: lift.rosterTotal, universe: lift.universe, split: lift.split, gates: lift.gates.map((g) => ({ name: g.name, pass: g.pass })), usage: { model_calls: lift.stats.model_calls, totalTokens: lift.stats.totalTokens, cost: lift.stats.cost, wall_s: lift.stats.wall_s } })}\n`);
    return 0;
  } catch (e) {
    const code = e instanceof LiftError ? `lift:${e.step}` : "lift:infra"; // 原 run-fleet 失败面同映射(LiftError→lift:步名,其余→lift:infra)
    process.stdout.write(`${JSON.stringify({ ok: false, cmd: "add-lift", source: args.source, round_id: roundId, error: { code, message: String(e.message).slice(0, 300) } })}\n`);
    return 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await main(); }
  catch (e) {
    process.stderr.write(`${e.stack ?? e}\n`);
    process.stdout.write(`${JSON.stringify({ ok: false, cmd: "add-lift", error: { code: "infra", message: String(e.message).slice(0, 300) } })}\n`);
    process.exitCode = 3;
  }
}
