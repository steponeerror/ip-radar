#!/usr/bin/env node
// run-fleet.mjs — M5 fleet 加源舰队驱动器(票 #366;队列轮询→自动跑轮→自动 lift 出 draft PR)
//
// 语义(票面 6 条 + 用户裁决 2026-11-20 Q2a:笔记本 timer 驱动,自动跑轮+自动 lift
// 出 draft PR,合并人裁):
//   ⓪ 轮询 docs/ops/queue.md:APPROVE 行且 docs/ops/rounds/ 无该源的完成轮
//      (完成判据=轮 gates.json G_CLOSE pass 或 state.json status=completed)→ 取队首一源。
//      已有「开放轮」(未 CLOSE 且无 in_flight 续跑面)的源跳过不双花;fleet 状态
//      (dev/fleet/state.json)in_flight 优先于队首——崩溃续跑同 roundId(run-add 幂等)。
//   ① 沙箱:git worktree add <主检出>/.worktrees/add-<source> -b add/<source> <base>
//      (试点 2026-11-18-2250-add 判例:沙箱落主检出 .worktrees/;轮只消费不建,fleet 是
//      调用方=建沙箱方)+ scripts/worktree-prep.sh 拷双 node_modules(AGENTS 2026-11-15 判例)。
//   ② 跑轮:spawn run-add.mjs(旋钮=OPS_ADD_* 缺省即试点值 60 调用/7200s/¥5,月帽
//      OPS_PIPELINE_MONTHLY_CAP_CNY=30 共享;env DOCS_ROOT 指 docs 根=queue/轮目录/台账面)。
//   ③ 轮 ok → lift(全在沙箱分支上,一次 commit):
//      文档三件(README 源表行+源数+1 双语、MANUAL 计数双语、CHANGELOG feed-add 条目,
//      数据取轮 a2-dossier.json)→ 基准重冻(11-18 判例 b9f9dc19 正路:gen-universe.mjs
//      与 rrsi gen-split.mjs 解冻→重生成→复冻,种子不变;测试钉同步)→ roster 钉同步
//      (test_metadata_derivation.py 快照行 + 发现冒烟计数,mirage #359 同步面)→
//      门三连(backend 全量 pytest / ops selftest / agent-v2 node --test)→
//      push + gh pr create --draft(标题 add/<source>,正文含轮四行数)。
//   ④ 失败/门红:不重试,信封留档(rounds/<id>/fleet-run.json)+ lark 推送
//      (apprise --body 参数数组形,#368 判例;env IP_RADAR_ALERT_URLS,缺省静音);
//      同源连续 2 次失败=跳过+告警(一次性,skip_alerted 防每拍重发)。
//      月帽拒启(run-add refused budget_monthly)=lark+exit 1,不计失败(未起跑)。
//   ⑤ 一次一源(--once 显式声明,缺省同形);无源=exit 0 零模型调用(fleet 自身零模型面)。
//   ⑥ 轮产出永不自并入 master;合并后 champion 重锚由父会话人工做(票面定案,不在本件)。
//
// 路径锚:docs 根缺省=env DOCS_ROOT ?? <主检出>/docs(嵌套 docs 仓只在主检出物化;
// git-common-dir 推导同 leak-check.mjs mainCheckoutRoot;生产装机时驱动器检出=主检出,
// 算式退化为自身)。dev/fleet 与 .worktrees 同锚。
//
// 用法:node run-fleet.mjs [--once] [--model provider/modelId] [--queue PATH]
//        [--docs-root DIR] [--rounds DIR] [--dev-root DIR] [--sandbox-home DIR]
//        [--base REF] [--dry-run-exits]
// 退出码:0=无源空转/全链成功;1=refused/failed/门红;2=用法错;3=运行期异常。
// stdout 末行=单行 JSON fleet 信封(ENVELOPE.md 律:进度走 stderr)。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { resolveAddPython } from "./run-add.mjs"; // 沙箱测试解释器推导(worktree 律单源);加载序锚:先拉 run-add 侧再拉 tasks/add-round(环从 run-add 面解,gen-exam-cards 同律——倒序在 tasks/index.mjs 撞 addRoundTask TDZ)
import { parseQueueRows } from "./tasks/add-round.mjs"; // 队列行解析单源(轮 VERIFY 同面)
import { mainCheckoutRoot } from "./bench/leak-check.mjs"; // 主检出锚单源(git-common-dir)
import { parseRoster } from "./bench/roster.mjs"; // roster dump 行解析单源
import { heldoutSeatsFor } from "./bench/add-domain/gen-universe.mjs"; // heldout=round(N×13/53) 形状律单源
import { pushAnomalyLark } from "./bench/evolution/exits.mjs"; // lark 通道契约单源(apprise --body 参数数组形)

const execFileP = promisify(execFileCb);
export const ROOT = path.resolve(import.meta.dirname, "..", ".."); // ops/agent-v2 → 驱动器所在检出仓根
export const FLEET_SKIP_FAILURES = 2; // 同源连续失败跳过线(票面「连续 2 次」)
export const SOURCE_SHAPE = /^[a-z0-9_]{1,32}$/; // run-add --source 同形(输入域单源注释)
const ROUND_ID_RE = /^\d{4}-\d{2}-\d{2}-\d{4}-add(-r\d+)?$/; // run-add 轮 id 形状律

// ── 纯函数面(导出=测试单源)──────────────────────────────────────────────

// fleet 轮 id 铸形:YYYY-MM-DD-HHMM-add(本地钟;run-add 形状律,-rN 后缀留给撞名去重)
export function mintFleetRoundId(now = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}-add`;
}

// 完成判据(票面①):轮 CLOSE 过 = gates.json G_CLOSE pass(state.json status=completed
// 为等价终态面;pilot 2250 实测 status 停在 running 而 G_CLOSE pass=true——gates 是主判据)
export function roundClosedFace(state, gates) {
  if (state?.status === "completed") return true;
  return Array.isArray(gates?.records) && gates.records.some((r) => r?.name === "G_CLOSE" && r?.pass === true);
}

// rounds 目录扫描:add 型轮按 source 归档 closed/open(closed 优先——同源一败一成仍算完成)
export function scanAddRoundSources(roundsRoot, io = { existsSync: fs.existsSync, readdirSync: fs.readdirSync, readJsonIf }) {
  const closed = new Set(), open = new Set();
  if (!io.existsSync(roundsRoot)) return { closed, open };
  for (const name of io.readdirSync(roundsRoot).sort()) {
    const state = io.readJsonIf(path.join(roundsRoot, name, "state.json"));
    if (!state || state.type !== "add" || typeof state.source !== "string") continue;
    const gates = io.readJsonIf(path.join(roundsRoot, name, "gates.json"));
    if (roundClosedFace(state, gates)) closed.add(state.source);
    else open.add(state.source);
  }
  for (const s of closed) open.delete(s); // closed 优先
  return { closed, open };
}

// 队首目标:文件序首个 APPROVE 行的源(去重取首见),跳过已关闭/已屏蔽/开放轮在身/id 形状坏
export function pickFleetTarget({ queueText, closedSources = new Set(), blockedSources = new Set(), openSources = new Set() }) {
  const seen = new Set();
  const skipped = [];
  for (const row of parseQueueRows(queueText)) {
    if (row.action !== "APPROVE") continue;
    const source = row.source;
    if (!SOURCE_SHAPE.test(source ?? "")) { skipped.push(`${source}(id 形状坏)`); continue; }
    if (seen.has(source)) continue;
    seen.add(source);
    if (closedSources.has(source)) { skipped.push(`${source}(已有完成轮)`); continue; }
    if (openSources.has(source)) { skipped.push(`${source}(开放轮在身,禁双花)`); continue; }
    if (blockedSources.has(source)) { skipped.push(`${source}(连续 ${FLEET_SKIP_FAILURES} 败跳过)`); continue; }
    return { source, approve: { date: row.date, round: row.round }, skipped };
  }
  return null;
}

// fleet 状态推进:失败计数/跳过告警一次性标记;ok 清零。in_flight 由调用方管理。
export function applyFleetOutcome(state, source, ok, at = new Date().toISOString()) {
  const failures = { ...(state?.failures ?? {}) };
  const skipAlerted = { ...(state?.skip_alerted ?? {}) };
  if (ok) { delete failures[source]; delete skipAlerted[source]; }
  else {
    failures[source] = (failures[source] ?? 0) + 1;
    if (failures[source] >= FLEET_SKIP_FAILURES) skipAlerted[source] = at; // 首达跳过线记时(告警一次性判据)
  }
  return { ...state, schema: 1, failures, skip_alerted: skipAlerted };
}

// 屏蔽名单=失败计数达线(选择面;告警时机由主流程在「首次因此跳过」时发)
export function blockedSourcesOf(state) {
  return new Set(Object.entries(state?.failures ?? {}).filter(([, n]) => n >= FLEET_SKIP_FAILURES).map(([s]) => s));
}

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
  return sub1(t, /(\d+)( 源\()(\d+)( 公开 \+ 1 私有蜜罐\))/,
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

// rrsi 劈分测试钉同步(b9f9dc19 判例的机械面:数字钉+注记重写)
export function syncRrsiSplitPins(text, { evolve, heldout, total, rosterTotal, exempt, tag }) {
  let t = String(text);
  t = sub1(t, /结构不变式:\d+ 演化 \+ \d+ 留出/, () => `结构不变式:${evolve} 演化 + ${heldout} 留出`, "rrsi-split 测试标题钉");
  t = sub1(t, /assert\.equal\(meta\.evolve, \d+\);/, () => `assert.equal(meta.evolve, ${evolve});`, "meta.evolve 钉");
  t = sub1(t, /assert\.equal\(meta\.heldout, \d+\);/, () => `assert.equal(meta.heldout, ${heldout});`, "meta.heldout 钉");
  t = sub1(t, /assert\.equal\(rows\.length, \d+, "考题总数 = \d+\(\d+ 源 − \d+ 免考;[^"]*"\);/,
    () => `assert.equal(rows.length, ${total}, "考题总数 = ${total}(${rosterTotal} 源 − ${exempt} 免考;${tag} fleet 再冻结)");`, "rows.length 钉");
  t = sub1(t, /assert\.equal\(evolve\.length, \d+\);/, () => `assert.equal(evolve.length, ${evolve});`, "evolve.length 钉");
  t = sub1(t, /assert\.equal\(heldout\.length, \d+\);/, () => `assert.equal(heldout.length, ${heldout});`, "heldout.length 钉");
  t = sub1(t, /assert\.equal\(new Set\(names\)\.size, \d+, "无重复"\);/, () => `assert.equal(new Set(names).size, ${total}, "无重复");`, "names 去重钉");
  t = sub1(t, /assert\.equal\(exam\.length, \d+, `真 roster 考题数漂移:\$\{exam\.length\} ≠ \d+——冻结名单须重裁\([^`]*\)`\);/,
    () => "assert.equal(exam.length, " + total + ", `真 roster 考题数漂移:${exam.length} ≠ " + total + "——冻结名单须重裁(" + tag + " fleet 再冻结)`);", "exam.length 钉");
  return t;
}
export function syncRrsiDomainPin(text, { total, tag }) {
  return sub1(String(text), /assert\.equal\(criticProbe\.total, \d+, "每考题一行一针\(\d+ 行;[^"]*"\);/,
    () => `assert.equal(criticProbe.total, ${total}, "每考题一行一针(${total} 行;${tag} fleet 再冻结)");`, "critic 针数钉");
}

// 发现冒烟计数钉(test_b_family_url_filename_guard.py;mirage #359「roster 钉同步」同面)
export function bumpDiscoverySmokePin(text, { total, source, tag }) {
  return sub1(String(text), /^(.*assert len\(sources\) == )(\d+)(\s*#\s*本票时点 roster;增删源时同步\()([^)]*)(\))$/m,
    (m, a, n, c, note) => `${a}${total}${c}${note} + ${tag} fleet #366 lift ${source} 接入 ${n}→${total})`, "发现冒烟计数钉");
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

// CHANGELOG feed-add 条目(双语对;数据全取轮 a2-dossier.json,措辞如实标注 fleet 自动生成)
export function changelogEntries({ source, dossier, roundId, stats, prNumber }) {
  const zh = `  - **威胁源接入:${source}(${dossier.name};fleet 自动 lift #366,轮 ${roundId}${prNumber ? `,draft PR #${prNumber}` : ""})**:加源轮全相位绿后由 M5 fleet 驱动器自动 lift——格式:${clip(dossier.format)};鉴权:${clip(dossier.auth, 100)};节奏:${clip(dossier.cadence, 100)};字段路由草案:${clip((dossier.field_routing ?? []).join(";"), 160)};样本 ${Array.isArray(dossier.samples) ? dossier.samples.length : 0} 行(实抓,见轮工件)。轮四行数:模型调用 ${stats.model_calls} / 总 tokens ${stats.totalTokens} / 花费 ¥${stats.cost.toFixed(8)} / 墙钟 ${stats.wall_s.toFixed(1)}s。门:backend 全量 pytest + ops selftest + agent-v2 node --test 三绿(沙箱分支);合并人裁(fleet 轮产出永不自并入 master)。本条目为 fleet 机械生成,合并前人面可润色。`;
  const en = `  - **Threat-feed add: ${source} (${dossier.name}; fleet auto-lift #366, round ${roundId}${prNumber ? `, draft PR #${prNumber}` : ""})**: lifted automatically by the M5 fleet driver after a fully green add-round — format: ${clip(dossier.format)}; auth: ${clip(dossier.auth, 100)}; cadence: ${clip(dossier.cadence, 100)}; field-routing draft: ${clip((dossier.field_routing ?? []).join("; "), 160)}; ${Array.isArray(dossier.samples) ? dossier.samples.length : 0} sample rows (live-captured, see round artifacts). Round four numbers: model calls ${stats.model_calls} / total tokens ${stats.totalTokens} / cost ¥${stats.cost.toFixed(8)} / wall ${stats.wall_s.toFixed(1)}s. Gates: full backend pytest + ops selftest + agent-v2 node --test all green (sandbox branch); merge is a human ruling (fleet round output never self-merges into master). This entry is fleet-generated; polish before merging is welcome.`;
  return { zh, en };
}

export function composePrBody({ source, card = null, roundId, dossier, stats, gates, rosterTotal, universe, split, seats }) {
  return [
    `# add/${source} — M5 fleet 自动 lift(#366)`,
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
    "合并人裁(fleet 轮产出永不自并入 master;#366 语义)。轮工件:`docs/ops/rounds/${roundId}/`(嵌套 docs 仓)。",
    "",
    `_本 PR 由 fleet 驱动器自动开出;CHANGELOG 条目为机械生成,合并前可润色。_`,
  ].join("\n");
}

// ── 小工具 ──
function readJsonIf(p) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } }
const writeJsonAtomic = (p, j) => {
  fs.mkdirSync(path.dirname(path.resolve(p)), { recursive: true });
  fs.writeFileSync(`${p}.tmp`, JSON.stringify(j, null, 2) + "\n");
  fs.renameSync(`${p}.tmp`, p);
};
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
    log(`[fleet-lift] ${what}: ${rel}`);
  };
  const contributes = `${clip(dossier.format, 90)} (fleet-lifted #366)`;
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
    `    "${stem}": "${meta.category}",   # ${tag} fleet lift(#366)`) , "OLD_RELIABILITY",
    `    "${stem}": ${meta.reliability},   # ${tag} fleet lift(#366)`), "metadata 快照行");
  // 6. lift commit
  await git(sandbox, ["add", "-A"]);
  await git(sandbox, ["-c", "user.email=fleet@ipradar.local", "-c", "user.name=fleet-driver", "-c", "commit.gpgsign=false",
    "commit", "-m", `lift(#366): 文档三件+基准重冻+roster 钉同步(${stem};卡 ${source};fleet ${roundId})`]);
  // 7. 门三连
  const gates = [
    { name: "backend 全量 pytest", cmd: [python, "-m", "pytest", "-q", "--durations=15"], cwd: path.join(sandbox, "backend"), timeoutMs: 30 * 60_000 },
    { name: "ops selftest", cmd: ["bash", path.join(sandbox, "ops", "agent", "selftest.sh")], cwd: sandbox, timeoutMs: 15 * 60_000 },
    { name: "agent-v2 node --test", cmd: ["npm", "test"], cwd: path.join(sandbox, "ops", "agent-v2"), timeoutMs: 15 * 60_000 },
  ];
  const gateResults = [];
  for (const g of gates) {
    log(`[fleet-lift] 门:${g.name} …`);
    try {
      const r = await exec(g.cmd[0], g.cmd.slice(1), { cwd: g.cwd, timeout: g.timeoutMs, maxBuffer: 64 * 1024 * 1024 });
      gateResults.push({ name: g.name, pass: true, tail: tailOf(r.stdout) });
    } catch (e) {
      gateResults.push({ name: g.name, pass: false, tail: tailOf(`${e.stdout ?? ""}\n${e.stderr ?? ""}\n${e.message}`) });
      throw new LiftError(`gate:${g.name}`, `${g.name} 红(尾 60 行已留档):\n${gateResults.at(-1).tail}`);
    }
    log(`[fleet-lift] 门:${g.name} 绿`);
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

// ── CLI ──
function usage() {
  process.stderr.write(`用法:node run-fleet.mjs [--once] [--model provider/modelId] [--queue PATH] [--docs-root DIR] [--rounds DIR] [--dev-root DIR] [--sandbox-home DIR] [--base REF] [--dry-run-exits]\n`);
}
function parseArgs(argv) {
  const out = { once: false, dryRunExits: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--once") out.once = true;
    else if (a === "--dry-run-exits") out.dryRunExits = true;
    else if (a === "--model") out.model = next();
    else if (a === "--queue") out.queue = next();
    else if (a === "--docs-root") out.docsRoot = next();
    else if (a === "--rounds") out.rounds = next();
    else if (a === "--dev-root") out.devRoot = next();
    else if (a === "--sandbox-home") out.sandboxHome = next();
    else if (a === "--base") out.base = next();
    else if (a === "--help" || a === "-h") out.help = true;
    else { process.stderr.write(`未知参数:${a}\n`); out.bad = true; }
  }
  return out;
}

export async function main(argv = process.argv.slice(2), io = {}) {
  const args = parseArgs(argv);
  if (args.help || args.bad) { usage(); return 2; }
  const log = io.log ?? ((l) => process.stderr.write(`${l}\n`));
  const env = io.env ?? process.env;
  const exec = io.exec ?? execFileP;
  const anchor = mainCheckoutRoot(ROOT) ?? ROOT; // 主检出锚(docs 嵌套仓/dev/.worktrees 物化地;主检出自身退化形)
  const docsRoot = path.resolve(args.docsRoot ?? env.DOCS_ROOT ?? path.join(anchor, "docs"));
  const roundsRoot = path.resolve(args.rounds ?? path.join(docsRoot, "ops", "rounds"));
  const queueFile = path.resolve(args.queue ?? path.join(docsRoot, "ops", "queue.md"));
  const devRoot = path.resolve(args.devRoot ?? env.FLEET_DEV_ROOT ?? path.join(anchor, "dev", "fleet"));
  const sandboxHome = path.resolve(args.sandboxHome ?? path.join(anchor, ".worktrees"));
  const baseRef = args.base ?? "origin/master";
  const statePath = path.join(devRoot, "state.json");
  const readState = () => readJsonIf(statePath) ?? { schema: 1 };
  const writeState = (s) => writeJsonAtomic(statePath, s);
  const dryRun = args.dryRunExits || String(env.FLEET_DRY_RUN ?? "") === "1";
  const body = async (title, text) => pushAnomalyLark({ title, body: text, env, dryRun, exec });

  // ⓪ 队列轮询
  let queueText;
  try { queueText = fs.readFileSync(queueFile, "utf8"); }
  catch { process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", error: { code: "infra", message: `队列文件缺席:${queueFile}(docs 根须指向嵌套 docs 仓;--queue/--docs-root 可覆盖)` } })}\n`); return 3; }
  const { closed, open } = scanAddRoundSources(roundsRoot);
  let state = readState();
  // in_flight 续跑优先(崩溃恢复:同 roundId 重放=run-add 幂等面)
  let resume = state.in_flight && SOURCE_SHAPE.test(state.in_flight.source ?? "") ? state.in_flight : null;
  const target = resume
    ? { source: resume.source, approve: { date: null, round: "in_flight" } }
    : pickFleetTarget({ queueText, closedSources: closed, blockedSources: blockedSourcesOf(state), openSources: open });
  if (!target) {
    log(`[fleet] 无可跑源(closed=${[...closed].join(",") || "无"};blocked=${[...blockedSourcesOf(state)].join(",") || "无"};open=${[...open].join(",") || "无"})——空转退出,零模型调用`);
    process.stdout.write(`${JSON.stringify({ ok: true, round: "fleet", idle: true, picked: null })}\n`);
    return 0;
  }
  const source = target.source;
  log(`[fleet] 取源 ${source}(APPROVE ${target.approve.date ?? "in_flight 续跑"});closed=${[...closed].length} open=${[...open].length}`);

  // 模型面(真跑必填;faux 面不经 fleet——测试直接打 runAddRound)
  const modelArg = args.model ?? env.OPS_MODEL_FLEET;
  if (!modelArg || !modelArg.includes("/") || modelArg.indexOf("/") === 0 || modelArg.endsWith("/")) { usage(); process.stderr.write(`--model/OPS_MODEL_FLEET 须 provider/modelId,得到:${modelArg}\n`); return 2; }
  const model = { provider: modelArg.slice(0, modelArg.indexOf("/")), modelId: modelArg.slice(modelArg.indexOf("/") + 1) };

  // ① 沙箱(fresh 建;resume 复用/重挂)
  let roundId, sandboxRoot;
  if (resume) {
    roundId = resume.roundId; sandboxRoot = path.resolve(resume.sandbox);
    if (!ROUND_ID_RE.test(roundId ?? "")) { process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", source, error: { code: "infra", message: `in_flight 轮 id 形状坏:${roundId}` } })}\n`); return 3; }
    if (!fs.existsSync(sandboxRoot)) {
      try { await git(anchor, ["worktree", "add", sandboxRoot, `add/${source}`]); await exec("bash", [path.join(ROOT, "scripts", "worktree-prep.sh"), sandboxRoot], { timeout: 600_000 }); }
      catch (e) { process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", source, error: { code: "infra", message: `in_flight 沙箱重挂败:${e.message}` } })}\n`); return 3; }
      log(`[fleet] in_flight 沙箱重挂:${sandboxRoot}`);
    }
    log(`[fleet] 续跑 in_flight 轮 ${roundId}(run-add 幂等重放)`);
  } else {
    roundId = mintFleetRoundId();
    for (let n = 1; fs.existsSync(path.join(roundsRoot, roundId)); n++) roundId = `${mintFleetRoundId()}-r${n}`;
    sandboxRoot = path.join(sandboxHome, `add-${source}`);
    if (fs.existsSync(sandboxRoot)) { process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", source, error: { code: "infra", message: `沙箱路径已在:${sandboxRoot}(旧轮残留;人面清后重试)` } })}\n`); return 3; }
    try { await exec("git", ["-C", anchor, "fetch", "origin", "master"], { timeout: 120_000 }).catch(() => log("[fleet] fetch origin master 败(继续用本地 origin/master)")); } catch { /* 旧 node 兜底 */ }
    try {
      await git(anchor, ["worktree", "add", sandboxRoot, "-b", `add/${source}`, baseRef]);
      await exec("bash", [path.join(ROOT, "scripts", "worktree-prep.sh"), sandboxRoot], { timeout: 600_000 });
    } catch (e) {
      process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", source, error: { code: "infra", message: `沙箱构建败:${e.message}` } })}\n`);
      return 3;
    }
    state = { ...state, in_flight: { source, roundId, sandbox: sandboxRoot, at: new Date().toISOString() } };
    writeState(state);
    log(`[fleet] 沙箱就绪:${sandboxRoot}(基 ${baseRef},分支 add/${source});轮 ${roundId}`);
  }

  const roundDir = path.join(roundsRoot, roundId);
  // 失败/拒启出口(单源内闭包:信封留档+lark+失败计数;countFailure=false=拒启未起跑不计)
  const fail = async (phase, message, { countFailure = true, envelope = null, extra = null } = {}) => {
    const text = [`fleet #366 ${phase} 红`, `源:${source}`, `轮:${roundId}`, String(message).slice(0, 400)].join("\n");
    const larkRes = await body(`ipradar-fleet ${phase} 红`, text);
    if (countFailure) {
      state = applyFleetOutcome(state, source, false);
      state.in_flight = null;
      writeState(state);
      if (blockedSourcesOf(state).has(source))
        await body(`ipradar-fleet 跳过 ${source}`, `连续 ${FLEET_SKIP_FAILURES} 次失败,后续拍跳过该源(队列 APPROVE 行仍在;人面复盘后删 dev/fleet/state.json failures 条目可复跑)`);
    }
    writeJsonAtomic(path.join(roundDir, "fleet-run.json"), { ok: false, round_id: roundId, source, phase, message: String(message).slice(0, 2000), envelope, extra, lark: larkRes, at: new Date().toISOString() });
    process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", source, round_id: roundId, error: { code: phase, message: String(message).slice(0, 300) } })}\n`);
    return 1;
  };

  // ② 跑轮(spawn 隔离:崩溃面不拖驱动器;stdout 末行=轮信封)
  log(`[fleet] 跑轮 ${roundId}(model ${model.provider}/${model.modelId})`);
  let roundRc = 0, roundOut = "", roundErr = "";
  try {
    const r = await exec("node", [path.join(ROOT, "ops", "agent-v2", "run-add.mjs"), roundId, "--source", source, "--sandbox", sandboxRoot, "--model", `${model.provider}/${model.modelId}`],
      { cwd: path.join(ROOT, "ops", "agent-v2"), env: { ...env, DOCS_ROOT: docsRoot }, timeout: 7800_000, maxBuffer: 32 * 1024 * 1024 });
    roundOut = r.stdout;
  } catch (e) {
    roundRc = typeof e.code === "number" ? e.code : 1;
    roundOut = String(e.stdout ?? "");
    roundErr = String(e.stderr ?? e.message ?? "");
    log(`[fleet] run-add 退出码 ${roundRc}`);
  }
  const envelopeLine = roundOut.trimEnd().split("\n").filter(Boolean).at(-1);
  let envelope = null;
  try { envelope = JSON.parse(envelopeLine); } catch { /* 缺席走 infra */ }
  if (roundRc !== 0) {
    if (envelope?.error?.code === "budget_monthly")
      return fail("refused", `月帽拒启(${envelope.error.message})——不计失败,下拍自查`, { countFailure: false, envelope });
    if (!envelope) return fail("round:infra", `run-add 无信封退出(rc=${roundRc});stderr 尾:\n${tailOf(roundErr, 15)}`);
    return fail(`round:${envelope.error?.code ?? "failed"}`, envelope.error?.message ?? "轮失败", { envelope });
  }
  log(`[fleet] 轮 ${roundId} ok(信封 usage cost=${envelope?.usage?.cost})`);

  // ③ lift
  let lift;
  try {
    lift = await runLift({ sandbox: sandboxRoot, roundDir, fleetRoot: ROOT, devRoot, python: resolveAddPython(env), source, roundId, log, exec });
  } catch (e) {
    return fail(e instanceof LiftError ? `lift:${e.step}` : "lift:infra", e.message, { envelope });
  }
  log(`[fleet] lift ok:PR ${lift.pr}(universe ${lift.universe.before}→${lift.universe.after},split ${lift.split.before}→${lift.split.after})`);

  state = applyFleetOutcome(state, source, true);
  state.in_flight = null;
  state.done = { ...(state.done ?? {}), [source]: { round_id: roundId, pr: lift.pr, at: new Date().toISOString() } };
  writeState(state);
  writeJsonAtomic(path.join(roundDir, "fleet-run.json"), { ok: true, round_id: roundId, source, pr: lift.pr, lift, at: new Date().toISOString() });
  process.stdout.write(`${JSON.stringify({ ok: true, round: "fleet", source, round_id: roundId, sandbox: { root: sandboxRoot, branch: lift.branch }, pr: lift.pr, usage: { model_calls: lift.stats.model_calls, totalTokens: lift.stats.totalTokens, cost: lift.stats.cost, wall_s: lift.stats.wall_s } })}\n`);
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await main(); }
  catch (e) {
    process.stderr.write(`${e.stack ?? e}\n`);
    process.stdout.write(`${JSON.stringify({ ok: false, round: "fleet", error: { code: e.code === "infra" ? "infra" : "infra", message: String(e.message).slice(0, 300) } })}\n`);
    process.exitCode = 3;
  }
}
