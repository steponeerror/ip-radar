// tasks/add-round.mjs — 加源轮 defineTask 化(票 #332 P1;设计真源 docs/superpowers/
// specs/2026-11-11-add-round-reimplementation-bench-design.md §架构 + §相位表 + 定案 2/7/8/9)。
// 运营 agent 第三轮型 add:把已人裁 APPROVE 的候选卡实现进沙箱 worktree 的源代码。
//
// ── 纪律头注(仿 tasks/discover-round.mjs,零复制沿用既有执法面)──
//   一轮 = 自有 conversation(run-add.mjs 创建,agent 面 = add/system.md 提示词 +
//   ADD_TOOLS_EXTENSION 编码工具闭集;任务 ownership={kind:"conversation"} 绑进该会话)。
//   requestId 幂等:round-<roundId>-<phase>,attempt ≥2(结算坏/空文本/形状坏重发)=
//   -a<N> 后缀;崩溃发生在提交后结算前 → 同 key 重放 = pi-durable 恰好一次语义。
//   预算执法(budget-guard 双点,OPS_ADD_* 独立旋钮族):每相位头 stepBoundary(③墙钟);
//   模型相位每次 attempt 提交前 preModelCall(①③)+ 结算后 postModelCall(②④,usage 取
//   会话 UsageDoc 活和)。模型调用计数 = 会话累计 assistant 模型回合数(IMPLEMENT 是
//   工具循环大步,一次 submit 多回合——逐回合计数,attempt 即调用的逐回合推广)。
//   checkpoint 纪律:相位边界提交(modelCalls/usage/dossier/card/sandboxFace);凭证红线
//   env 不入 checkpoint(过程现读);input 只带路径/旋钮/只读配置(python 解释器路径非凭证)。
//
// ── 六相位(§相位表定稿名)──
//   VERIFY    脚本零模型:卡消费(只读 queue.md,只认 status=approved=有 APPROVE 行的
//             PROPOSE 卡;轮无写口改卡状态)+ roster diff(python -m ipdb._registry
//             --roster 对 download_host/子列,同出版方=STOP)+ 鲜活度门(数据内时间戳
//             ≤30d;file-mtime/URL 响应不算;真实面 4 组合探活 GET/HEAD×UA)。faux 面
//             读 fixtures/add/verify.json 罐装读数(与发现轮 MEASURE fixtures 缝同律)。
//   DOSSIER   脚本+模型:薄卡补交接单(实抓样本 3-5 行/格式/auth/cadence/字段路由草案),
//             终答=单条 JSON;形状坏重试 ≤1 再败=终态 model_face。
//             bench 形态(input.bench=true)跳过本相位——交接单预填在 input.dossier
//             (定案 2 开关位接口,P2b 基准接线消费;形与非 bench 同门校验)。
//   IMPLEMENT 模型大步:TDD 硬序(先写 backend/tests/sources/ 测试亲眼红,再写
//             backend/ipdb/_sources/ 源转绿;分类映射落 _classification.py;元数据类属性
//             在源文件内声明)——经编码工具(write_file/run_bash/run_pytest)真执行;
//             G_IMPLEMENT 机检:首跑红末跑绿(转录 run_pytest 种子序)+ 双文件沙箱在场
//             + stem 一致。
//   GATE      脚本零模型:沙箱内命令集(真实面=逐源测试+tests/source_infra/+目录源审计
//             三连;跑法=主检出 venv 解释器绝对路径+cwd=沙箱 backend/,定案 8;faux 面=
//             fixtures/add/gate.json 罐装清单,命令真执行零网络)。任一 rc≠0=门红终态。
//   REPORT    脚本:沙箱 git 提交+分支指针(rev-parse);轮产出=沙箱分支,永不自并入
//             master(定案 8/9 停止点;人裁并入)。
//   CLOSE     bookend:主检出 sandbox_assert 防线 + 台账行(pipeline-add 标签,lib.sh
//             同锁域)+ 09-budget.json(OPS_ADD_* env 面)+ 信封(stdout 末行,ENVELOPE.md)。
//
// ── 错误码 ── 复用 ENVELOPE.md 闭集(bad_round/model_face/empty_text/infra/
//   budget_exceeded/wall_clock_exceeded/sandbox_violation/ledger_failed)+ add 域词
//   (card_missing/card_not_approved/duplicate_publisher/freshness_gate/gate_failed)。
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { defineTask, UsageDoc } from "@earendil-works/pi-durable";
import { elapsedWallS } from "../budget.mjs"; // 零复制 re-export seam(旧管线纯函数单一真源)
import { preModelCall, postModelCall, stepBoundary } from "./budget-guard.mjs"; // 执法面(文案/界值零漂移)
import * as gates from "../../agent/pipeline/gates.mjs"; // 零复制:gates.json 留痕件(appendGate 通用面)
import { addPromptPath } from "../run-add.mjs"; // 提示词路径(run-add 定义面;函数声明循环安全:运行时互引,discover 同律)
import { ensureAddHost } from "../tools/add-tools.mjs"; // 轮级编码宿主(工具面种子登记)

const execFileP = promisify(execFileCb);
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);

export const ADD_TASK_NAME = "ops.add-round";
export const ADD_PHASES = Object.freeze(["verify", "dossier", "implement", "gate", "report", "close"]);
const STAGE_OF = Object.freeze({ verify: "VERIFY", dossier: "DOSSIER", implement: "IMPLEMENT", gate: "GATE", report: "REPORT", close: "CLOSE" });
const GATE_OF = Object.freeze({ verify: "G_VERIFY", dossier: "G_DOSSIER", implement: "G_IMPLEMENT", gate: "G_GATE", report: "G_REPORT", close: "G_CLOSE" });
// 工件名(加源轮自有前缀 a1-a5;09-budget.json 沿 CLOSE 预算快照名)
const ART = Object.freeze({
  VERIFY: "a1-verify.json",
  DOSSIER: "a2-dossier.json", DOSSIER_T: "a2-dossier-transcript.jsonl",
  IMPL: "a3-implement.json", IMPL_T: "a3-implement-transcript.jsonl",
  GATE: "a4-gate.json", REPORT: "a5-report.json", BUDGET: "09-budget.json",
});
// 台账行标签(#332 P1:旧 steps.mjs LEDGER_TAGS 属主零改动红线,add 域词在此单源;
// 消费面 monthSpendOfLedgerText 只读 cost 列,标签词不影响解析)
const ADD_LEDGER_TAG = "pipeline-add";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../.."); // ops/agent-v2/tasks → 仓根
const LIBSH = path.join(REPO_ROOT, "ops", "agent", "lib.sh"); // 台账/sandbox_assert(RETRO 同款 sh 面)
const sh = (fn, args = [], timeoutMs = 600_000, env = process.env) => execFileP("bash",
  ["-c", `. "$0"; ${fn} "$@"`, LIBSH, ...args], { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...env } });

// ── 纯函数面(导出=测试单源面)──────────────────────────────────────────

// 描述名 → 源文件名 stem(house style [a-z0-9_];实现契约:测试/源文件 stem 钉死同值)
export const slugify = (name) =>
  String(name).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "source";

// queue.md 行解析:冻结行形(| 日期 | 轮次 | action | source | predicate | evidence | vetoable |);
// evidence 值面是 JSON 串——引号内的 ";" 不裂(状态机切分),值 JSON.parse 兜底原样。
export function parseQueueRows(text) {
  const rows = [];
  for (const line of String(text ?? "").split("\n")) {
    if (!/^\|\s*\d{4}-\d{2}-\d{2}\s*\|/.test(line)) continue;
    const cells = line.split("|").map((c) => c.trim());
    if (cells.length < 8) continue;
    rows.push({ date: cells[1], round: cells[2], action: cells[3], source: cells[4], predicate: cells[5], evidence: parseEvidenceCell(cells[6]) });
  }
  return rows;
}
function parseEvidenceCell(cell) {
  const map = new Map();
  if (!cell || cell === "—") return map;
  const parts = [];
  let buf = "", inStr = false, esc = false;
  for (const ch of cell) {
    if (esc) { buf += ch; esc = false; continue; }
    if (ch === "\\") { buf += ch; esc = true; continue; }
    if (ch === '"') { buf += ch; inStr = !inStr; continue; }
    if (ch === ";" && !inStr) { parts.push(buf); buf = ""; continue; }
    buf += ch;
  }
  if (buf.trim()) parts.push(buf);
  for (const p of parts) {
    const i = p.indexOf("=");
    if (i <= 0) continue;
    const key = p.slice(0, i).trim();
    const raw = p.slice(i + 1);
    let val = raw;
    try { val = JSON.parse(raw); } catch { /* 裸数/bool 兜底原样(渲染面恒 JSON 串,防御读) */ }
    map.set(key, val);
  }
  return map;
}

// roster 撞卡(add-intel-source 技能 Phase 1 律:候选域名对 download_host+子列;
// dataplane 前例 2026-09-05)。roster 行形 = _registry.roster():name | cat | host | fields [| 子列]。
export function rosterCollisions(candidateHost, rosterLines) {
  const want = String(candidateHost ?? "").toLowerCase();
  if (!want) return [];
  const hits = [];
  for (const line of rosterLines ?? []) {
    const cells = String(line).split("|").map((c) => c.trim());
    if (cells.length < 4) continue;
    const host = (cells[2] ?? "").toLowerCase();
    if (host && host === want) hits.push(host);
    const subs = (cells[4] ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (subs.includes(want)) hits.push(want);
  }
  return [...new Set(hits)];
}

// 鲜活度门(定案 8 VERIFY 行):数据内时间戳 ≤30d 过;无内部时间戳=fail-closed
// (file-mtime/「URL 响应了」不算活性证据——sunset 源冻结文件也 200;发布方活性证据
// 面=GitHub commit/变更对抓,属基准接线后的真实轮深度,P1 不接入不谎报)。
export function freshnessOf(liveness, nowMs = Date.now()) {
  const age = liveness?.age_days;
  if (typeof age === "number" && Number.isFinite(age)) {
    if (age <= 30) return { ok: true, basis: liveness.basis ?? "age_days", age_days: age };
    return { ok: false, basis: liveness.basis ?? "age_days", age_days: age, reason: `数据内部时间戳 age_days=${age}>30(sunset 嫌疑)` };
  }
  return { ok: false, basis: "none", reason: "无内部时间戳(发布方活性证据面未接入;无证据即无话,fail-closed)" };
}

// 交接单形状(定案 2:实抓样本 3-5 行/格式/auth/cadence/字段路由草案)
export function dossierShape(d) {
  const no = (reason) => ({ ok: false, reason });
  if (d == null || typeof d !== "object" || Array.isArray(d)) return no("dossier 须是非数组对象");
  for (const k of ["name", "url", "format", "auth", "cadence"])
    if (typeof d[k] !== "string" || !d[k].trim()) return no(`${k} 缺失或非非空字符串`);
  if (!/^https?:\/\//.test(d.url)) return no("url 须 http(s) 形");
  if (!Array.isArray(d.samples) || d.samples.length < 3 || d.samples.length > 5)
    return no(`samples 须 3-5 行实抓样本(得到 ${Array.isArray(d.samples) ? d.samples.length : "非数组"})`);
  for (const s of d.samples) if (typeof s !== "string" || !s.trim()) return no("samples 行须非空字符串");
  if (!Array.isArray(d.field_routing) || !d.field_routing.length || d.field_routing.some((s) => typeof s !== "string" || !s.trim()))
    return no("field_routing 须非空字符串数组(字段路由草案)");
  return { ok: true, dossier: d };
}

// 实现摘要形状(TDD 硬序自报面;红绿序的机检在 G_IMPLEMENT 转录面,自报+机检双钉)
export function implementSummaryShape(s) {
  const no = (reason) => ({ ok: false, reason });
  if (s == null || typeof s !== "object" || Array.isArray(s)) return no("summary 须是非数组对象");
  for (const k of ["name", "test_file", "source_file"])
    if (typeof s[k] !== "string" || !s[k].trim()) return no(`${k} 缺失或非非空字符串`);
  if (s.red_observed !== true) return no("red_observed 须 true(TDD 硬序:先亲眼红)");
  if (s.green_observed !== true) return no("green_observed 须 true(后转绿)");
  return { ok: true, summary: s };
}

// GATE 命令集:真实面=定案 8 三连(逐源测试+source_infra+目录源审计;解释器由调用方
// 传入=主检出 venv 绝对路径);faux 面=fixtures/add/gate.json 罐装清单(命令真执行,
// 只是最小沙箱树跑不了全仓三连——机制面等价:执行+记录+门红绿)。
export function gateCommandsFor({ stem, modelFace, fixturesDir }) {
  if (modelFace === "faux" && typeof fixturesDir === "string") {
    const p = path.join(fixturesDir, "gate.json");
    let fx = null;
    try { fx = JSON.parse(fs.readFileSync(p, "utf8")); } catch { /* 缺席=fail-closed,同下 */ }
    if (!fx || !Array.isArray(fx.commands) || !fx.commands.length)
      throw Object.assign(new Error(`faux 面缺 gate.json 罐装命令清单:${p}`), { code: "infra" });
    return fx.commands.map((c) => ({ args: [...c.args], cwd: c.cwd ?? "" }));
  }
  return [
    { args: ["-m", "pytest", `tests/sources/test_${stem}.py`, "-q"], cwd: "backend" },
    { args: ["-m", "pytest", "tests/source_infra/", "-q"], cwd: "backend" },
    { args: ["scripts/audit_lmdb_invariants.py"], cwd: "" },
  ];
}

const writeJson = (p, o) => fs.writeFileSync(p, JSON.stringify(o, null, 2) + "\n"); // 旧 steps.mjs writeJson 同形
const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const jsonlOf = (p) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").split("\n").filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean) : []);

function resolveOpsRoot(env = process.env) { // 旧 opsRootOf 同算式(discover-round 同形)
  return path.join(env.DOCS_ROOT ?? path.join(REPO_ROOT, "docs"), "ops");
}

// ── ctx(本文件私有形状:加源轮无旧步零复制面,不挂 ctxShape)──────────────
function buildCtx(input, checkpoint) {
  const env = process.env; // 旧律:env 现读不入档(凭证红线)
  const opsRoot = resolveOpsRoot(env);
  return {
    type: "add",
    roundId: input.roundId,
    source: input.source,
    bench: input.bench === true,
    dir: path.join(opsRoot, "rounds", input.roundId),
    opsRoot,
    queueFile: path.join(opsRoot, "queue.md"),
    env,
    log: (line) => process.stderr.write(`[add:${checkpoint.phase}] ${line}\n`), // stdout 只留末行信封(ENVELOPE.md)
    fixturesDir: input.fixturesDir,
    modelFace: input.modelFace,
    budgetCny: input.budgetCny,
    budgetKnobs: input.knobs,
    sandboxRoot: input.sandboxRoot,
    python: input.python,
    ledgerFile: env.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(opsRoot, "ledger.md"),
    modelCalls: checkpoint.modelCalls,
    usage: { ...checkpoint.usage },
    sandboxFace: checkpoint.sandboxFace ?? null,
    card: checkpoint.card ?? null,
    envelope: null,
    addHost: null,
    state: { // state.json 镜像面(观察面;真源=checkpoint)
      schema: 1, round_id: input.roundId, type: "add", pipeline_mode: "pipeline", status: "running",
      stages: checkpoint.stages.map((r) => r.name),
      budget_cny: input.budgetCny, budget_knobs: input.knobs,
      fixtures_dir: input.fixturesDir, model_face: input.modelFace,
      prompt_hashes: checkpoint.prompt_hashes,
      started_at: checkpoint.startedAtIso, updated_at: new Date().toISOString(),
      resume_count: 0, replay_of: null, monthly_admission: input.admission ?? null,
      source: input.source, sandbox_root: input.sandboxRoot, bench: input.bench === true,
    },
  };
}

// ── 建轮/镜像/推进(discover-round 同律拷形:同 id 守卫+mkdir+state 骨架;镜像尽力)──
function bootstrapRoundDir(ctx, checkpoint) {
  const stateFile = path.join(ctx.dir, "state.json");
  if (checkpoint.stages.length === 0) {
    let prior = null;
    try { prior = JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch { /* 无=全新 */ }
    if (prior && (prior.round_id !== ctx.roundId || (Array.isArray(prior.stages) && prior.stages.length > 0)))
      throw Object.assign(new Error(`rounds/${ctx.roundId} 已存在(同 id 重跑走 replay)`), { code: "bad_round" });
    fs.mkdirSync(ctx.dir, { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(ctx.state, null, 2) + "\n");
    return;
  }
  fs.mkdirSync(ctx.dir, { recursive: true }); // resume:目录必在(防御)
}
function mirrorState(ctx, checkpoint) {
  try {
    ctx.state.stages = checkpoint.stages.map((r) => r.name);
    ctx.state.updated_at = new Date().toISOString();
    fs.writeFileSync(path.join(ctx.dir, "state.json"), JSON.stringify(ctx.state, null, 2) + "\n");
  } catch { /* 镜像失败不阻断相位推进(哲学①:证据在 checkpoint+工件) */ }
}
async function advance(runtime, context, checkpoint, patch = {}, ctx = null) {
  await runtime.commit((tx, cur) => ({
    status: "running",
    checkpoint: { ...cur.checkpoint, ...checkpoint, ...patch },
  }), context);
  if (ctx) mirrorState(ctx, checkpoint);
}
async function finishFailed(runtime, context, error) {
  return runtime.commit(() => ({ status: "terminal", outcome: { status: "failed", error } }), context);
}
async function finishOk(runtime, context, result) {
  return runtime.commit(() => ({ status: "terminal", outcome: { status: "completed", result } }), context);
}

// 崩溃钩子(测试面;env 现读不入档):进入指定相位头即 SIGKILL 自杀(上一相位
// checkpoint 已提交=该相位头进程崩溃;真崩溃恢复路径与测试同一代码路径,零 mock)。
function crashHook(phase) {
  if (process.env.OPS_V2_CRASH_AFTER_PHASE === phase) process.kill(process.pid, "SIGKILL");
}

// 相位推进(bench 形态的 DOSSIER 截断不走本表:dossierPhase 的 bench 分支自身就是
// 开关位接口——写 a2(bench:true)+过门+零 stage 记录直进 implement,定案 2)

// ── 门(表驱动,留痕经旧 gates.appendGate 同件)──────────────────────────
const j = (ctx, name) => readJson(path.join(ctx.dir, name));
const gateFail = (reason, inputs, code) => ({ pass: false, reason, inputs, code });
const gatePass = (reason, inputs) => ({ pass: true, reason, inputs });
function insideSandbox(sandboxRoot, p) {
  const root = path.resolve(sandboxRoot);
  let target;
  try { target = path.resolve(root, p ?? ""); } catch { return null; }
  return target === root || target.startsWith(root + path.sep) ? target : null;
}

export const ADD_GATES = {
  G_VERIFY: (ctx) => {
    const inputs = [ART.VERIFY, "queue.md"];
    const v = j(ctx, ART.VERIFY);
    if (!v) return gateFail(`${ART.VERIFY} 不可解析`, inputs, "infra");
    if (!v.card?.name || !v.card?.url) return gateFail("卡面缺 name/url(PROPOSE 行 evidence)", inputs, "card_missing");
    if ((v.roster?.collisions ?? []).length)
      return gateFail(`同出版方已在库(roster 撞卡:${v.roster.collisions.join(",")})——信号走既有源的面,不按新源立项`, inputs, "duplicate_publisher");
    if (v.freshness?.ok !== true) return gateFail(`鲜活度门:${v.freshness?.reason ?? "证据缺席"}`, inputs, "freshness_gate");
    return gatePass(`卡 ${v.source} APPROVE 读回;roster ${v.roster.rows_n} 行零撞;freshness ${v.freshness.basis} age_days=${v.freshness.age_days}`, inputs);
  },
  G_DOSSIER: (ctx) => {
    const inputs = [ART.DOSSIER, ART.DOSSIER_T];
    const d = j(ctx, ART.DOSSIER);
    if (!d?.dossier) return gateFail(`${ART.DOSSIER} 不可解析/缺 dossier`, inputs, "model_face");
    const r = dossierShape(d.dossier);
    if (!r.ok) return gateFail(`交接单形状:${r.reason}`, inputs, "model_face");
    return gatePass(`交接单过(name=${d.dossier.name} 样本 ${d.dossier.samples.length} 行;${d.bench ? "bench 预填" : "模型补卡"})`, inputs);
  },
  G_IMPLEMENT: (ctx) => {
    const inputs = [ART.IMPL, ART.IMPL_T, "(sandbox)"];
    const a = j(ctx, ART.IMPL);
    if (!a?.summary) return gateFail(`${ART.IMPL} 不可解析/缺 summary`, inputs, "model_face");
    const r = implementSummaryShape(a.summary);
    if (!r.ok) return gateFail(`实现摘要:${r.reason}`, inputs, "model_face");
    if (a.summary.name !== a.stem) return gateFail(`stem 漂移:${a.summary.name}≠${a.stem}(文件名契约钉死)`, inputs, "model_face");
    // 评审修批(#332 评审 P2):路径逐字钉死 stem 契约——任意在场路径即过会让偏航拖到 GATE 才暴露
    const canonical = { test_file: `backend/tests/sources/test_${a.stem}.py`, source_file: `backend/ipdb/_sources/${a.stem}.py` };
    for (const key of ["test_file", "source_file"]) {
      const rel = a.summary[key];
      if (rel !== canonical[key]) return gateFail(`路径契约:${key}=${rel}≠${canonical[key]}(stem 逐字)`, inputs, "model_face");
      const target = insideSandbox(ctx.sandboxRoot, rel);
      if (!target || !fs.existsSync(target)) return gateFail(`声明文件不在沙箱:${rel}`, inputs, "model_face");
    }
    // TDD 硬序机检:转录 run_pytest 种子序首红末绿(自报 red/green_observed 之外的独立回算)
    const pys = jsonlOf(path.join(ctx.dir, ART.IMPL_T)).filter((l) => l.type === "registry_seed" && l.tool === "run_pytest").map((l) => l.sc?.ok === true);
    if (!(pys.length >= 2 && pys[0] === false && pys[pys.length - 1] === true))
      return gateFail(`TDD 硬序未走:run_pytest 种子序须首跑红(模块缺)末跑绿(得到 [${pys.join(",")}])——先写测试亲眼看红,再写源转绿`, inputs, "model_face");
    return gatePass(`摘要过+双文件沙箱在场+TDD 序首红末绿(${pys.length} 跑)`, inputs);
  },
  G_GATE: (ctx) => {
    const inputs = [ART.GATE];
    const g = j(ctx, ART.GATE);
    if (!g || !Array.isArray(g.results) || !g.results.length) return gateFail(`${ART.GATE} 不可解析/零命令`, inputs, "infra");
    const red = g.results.filter((r) => r.rc !== 0);
    if (red.length) return gateFail(`门命令红 ${red.length}/${g.results.length}:${red.map((r) => `${r.label}(rc=${r.rc})`).join(";")}${red[0].tail ? ` 尾部:${String(red[0].tail).slice(0, 200)}` : ""}`, inputs, "gate_failed");
    return gatePass(`${g.results.length} 命令全绿(${g.results.map((r) => `${r.label} ${r.dur_ms}ms`).join(",")})`, inputs);
  },
  G_REPORT: (ctx) => {
    const inputs = [ART.REPORT, "(sandbox git)"];
    const rep = j(ctx, ART.REPORT);
    if (!rep?.sandbox) return gateFail(`${ART.REPORT} 不可解析`, inputs, "infra");
    if (rep.sandbox.repo === false) return gatePass("沙箱非 git 仓:如实记 repo=false(分支指针缺席,人裁面可见)", inputs);
    if (typeof rep.sandbox.sha !== "string" || !rep.sandbox.sha) return gateFail("沙箱 git 仓缺分支指针(sha)", inputs, "infra");
    return gatePass(`分支指针 ${rep.sandbox.sha.slice(0, 12)}(${rep.sandbox.branch}${rep.sandbox.committed ? ",本轮提交" : ",无新提交"})`, inputs);
  },
  G_CLOSE: (ctx) => {
    const inputs = ["(stdout 轮次信封)", ART.BUDGET, "(ledger)"];
    if (!ctx.envelope) return gateFail("信封未组装", inputs, "infra");
    const s = JSON.stringify(ctx.envelope);
    if (s.includes("\n")) return gateFail("信封非单行", inputs, "infra");
    if (JSON.parse(s).ok !== ctx.envelope.ok) return gateFail("信封不可往返解析", inputs, "infra");
    const b = j(ctx, ART.BUDGET); // 预算回声哨(环内已执法;门只对拍读数≤生效帽,防工件漂移——G_CLOSE 旧律)
    if (!b?.env || !b?.readings) return gateFail(`${ART.BUDGET} 缺席/形状坏(env+readings 必在场)`, inputs, "infra");
    if (b.readings.model_calls > b.env.OPS_ADD_MAX_MODEL_CALLS) return gateFail(`回声哨:model_calls=${b.readings.model_calls}>${b.env.OPS_ADD_MAX_MODEL_CALLS}`, inputs, "budget_exceeded");
    if ((b.readings.usage?.cost ?? 0) > b.env.OPS_ADD_SPEND_CAP_CNY) return gateFail(`回声哨:cost=${b.readings.usage.cost}>${b.env.OPS_ADD_SPEND_CAP_CNY}`, inputs, "budget_exceeded");
    if ((b.readings.wall_s ?? 0) > b.env.OPS_ADD_WALL_CLOCK_S) return gateFail(`回声哨:wall_s=${b.readings.wall_s}>${b.env.OPS_ADD_WALL_CLOCK_S}`, inputs, "wall_clock_exceeded");
    const ledger = fs.existsSync(ctx.ledgerFile) ? fs.readFileSync(ctx.ledgerFile, "utf8") : null;
    if (ledger === null || !ledger.includes(`${ADD_LEDGER_TAG}:${ctx.roundId}`)) return gateFail("台账读回缺本轮行(pipeline-add)", inputs, "ledger_failed");
    return gatePass(`信封单行可往返;预算回声 ${b.readings.model_calls} 调用/¥${(b.readings.usage?.cost ?? 0).toFixed(8)}/${b.readings.wall_s}s ≤ 帽;台账行读回`, inputs);
  },
};
function evalGate(phase, ctx) {
  const name = GATE_OF[phase];
  const fn = ADD_GATES[name];
  const t0 = performance.now();
  const r = fn ? fn(ctx) : { pass: false, reason: `未知门 ${name}(定义表漂移)`, inputs: [] };
  return { stage: STAGE_OF[phase], name, pass: !!r.pass, reason: r.reason, dur_ms: Math.round(performance.now() - t0), inputs: r.inputs ?? [], ...(r.code ? { code: r.code } : {}) };
}

// ── 信封(ENVELOPE.md add 节:发现轮 7 键族+add 域两键 source/sandbox;pkg 恒 null、
//    queue_writes 恒空——轮无写口改卡状态,定案 9)──────────────────────────
function composeEnvelope(checkpoint, ctx) {
  return {
    ok: true,
    round: "add",
    pipeline: { round_id: checkpoint.roundId, resumed_from: null, replayed_of: null, stages: checkpoint.stages },
    source: ctx.source,
    sandbox: { root: ctx.sandboxRoot, branch: ctx.sandboxFace?.branch ?? null, sha: ctx.sandboxFace?.sha ?? null },
    pkg: null,
    queue_writes: [],
    usage: { ...ctx.usage },
    verify: { ok: true, cited: 0 },
  };
}

// ── 相位步(脚本面)──────────────────────────────────────────────────────
const hostnameOf = (url) => { try { return new URL(url).hostname; } catch { return null; } };

// VERIFY:卡消费 + roster diff + 鲜活度(证据全落 a1;域错 card_* 先炸——无卡无可记)
async function runVerify(ctx) {
  const text = fs.existsSync(ctx.queueFile) ? fs.readFileSync(ctx.queueFile, "utf8") : "";
  const rows = parseQueueRows(text);
  const approve = rows.find((r) => r.action === "APPROVE" && r.source === ctx.source);
  if (!approve)
    throw Object.assign(new Error(`卡 ${ctx.source} 未 APPROVE(加源轮只消费 status=approved 的卡;APPROVE 写口仅人面,轮不改卡状态)`), { code: "card_not_approved" });
  const cardRow = rows.filter((r) => r.action === "PROPOSE" && r.source === ctx.source).at(-1);
  if (!cardRow)
    throw Object.assign(new Error(`卡 ${ctx.source} 无 PROPOSE 候选行(APPROVE 在场但候选卡缺席——队列崩殘态,人面补卡)`), { code: "card_missing" });
  const card = {
    name: typeof cardRow.evidence.get("candidate:name") === "string" ? cardRow.evidence.get("candidate:name") : ctx.source,
    url: typeof cardRow.evidence.get("candidate:url") === "string" ? cardRow.evidence.get("candidate:url") : null,
    approved_by: cardRow.evidence.get("human:approved_by") ?? approve.evidence.get("human:approved_by") ?? null,
  };
  // roster diff:faux=罐装行;真实面=沙箱内 python -m ipdb._registry --roster(定案 8 跑法)
  let roster;
  let liveness;
  if (ctx.modelFace === "faux" && typeof ctx.fixturesDir === "string") {
    const fx = readJson(path.join(ctx.fixturesDir, "verify.json")) ?? {};
    roster = Array.isArray(fx.roster) ? fx.roster : [];
    liveness = fx.liveness ?? {};
  } else {
    roster = (await execFileP(ctx.python, ["-m", "ipdb._registry", "--roster"],
      { cwd: path.join(ctx.sandboxRoot, "backend"), timeout: 120_000, maxBuffer: 16 * 1024 * 1024 })).stdout.split("\n").filter(Boolean);
    liveness = await probeLiveness(card.url);
  }
  const host = hostnameOf(card.url ?? "");
  const collisions = host ? rosterCollisions(host, roster) : [];
  const freshness = freshnessOf(liveness);
  writeJson(path.join(ctx.dir, ART.VERIFY), {
    round_id: ctx.roundId, source: ctx.source, generated_at: new Date().toISOString(),
    card, roster: { rows_n: roster.length, collisions }, liveness, freshness,
  });
  return { patch: { card } };
}

// 真实面探活(4 组合 GET/HEAD × UA 有无):last-modified 内时间戳=鲜活度证据面;
// 「响应了」不算证据(sunset 冻结文件也 200——技能 Phase 1 鲜活度门同律)。
async function probeLiveness(url) {
  const combos = [];
  if (url) {
    for (const method of ["GET", "HEAD"]) {
      for (const ua of [true, false]) {
        try {
          const res = await fetch(url, {
            method, redirect: "manual", signal: AbortSignal.timeout(15_000),
            headers: ua ? { "user-agent": "ip-radar-add-round/1.0" } : {},
          });
          combos.push({ method, ua, status: res.status, last_modified: res.headers.get("last-modified") });
        } catch (e) {
          combos.push({ method, ua, error: String(e?.cause?.message ?? e?.message ?? e).slice(0, 160) });
        }
      }
    }
  }
  const newest = combos.map((c) => c.last_modified).filter(Boolean).map((s) => new Date(s))
    .filter((d) => !Number.isNaN(d.getTime())).sort((a, b) => b - a)[0] ?? null;
  return {
    combos,
    last_modified: newest?.toISOString() ?? null,
    age_days: newest ? Math.floor((Date.now() - newest.getTime()) / 86_400_000) : undefined,
    basis: newest ? "last_modified" : "none",
  };
}

function phaseAfter(phase) {
  return ADD_PHASES[ADD_PHASES.indexOf(phase) + 1] ?? null;
}

// GATE:命令集执行(真实面三连/faux 罐装;命令真执行零网络,rc 全记录,红=门红留证)
async function runGatePhase(ctx, checkpoint) {
  const dossier = checkpoint.dossier;
  if (!dossier) throw Object.assign(new Error("交接单缺席(dossier 相位未过?)"), { code: "infra" });
  const stem = slugify(dossier.name);
  const commands = gateCommandsFor({ stem, modelFace: ctx.modelFace, fixturesDir: ctx.fixturesDir });
  const results = [];
  for (const c of commands) {
    const cwd = insideSandbox(ctx.sandboxRoot, c.cwd ?? "");
    if (!cwd) throw Object.assign(new Error(`GATE cwd 逃逸沙箱:${c.cwd}`), { code: "infra" });
    const t0 = Date.now();
    let rc = 0, tail = "";
    try {
      const r = await execFileP(ctx.python, c.args, { cwd, timeout: 600_000, maxBuffer: 32 * 1024 * 1024 });
      tail = String(r.stdout ?? "").split("\n").filter(Boolean).slice(-15).join("\n").slice(0, 2000);
    } catch (e) {
      rc = typeof e.code === "number" ? e.code : -1;
      tail = `${String(e.stdout ?? "")}\n${String(e.stderr ?? "")}`.split("\n").filter(Boolean).slice(-15).join("\n").slice(0, 2000);
    }
    results.push({ label: c.args.join(" ").slice(0, 120), cwd: c.cwd ?? "", rc, dur_ms: Date.now() - t0, tail });
  }
  writeJson(path.join(ctx.dir, ART.GATE), { round_id: ctx.roundId, stem, commands: results.map(({ label, cwd }) => ({ label, cwd })), results, passed: results.every((r) => r.rc === 0), generated_at: new Date().toISOString() });
  return {};
}

// REPORT:沙箱 git 提交 + 分支指针(轮产出=沙箱分支;git 身份经 -c 注入,沙箱仓无需配置)
async function runReport(ctx) {
  const sandboxFace = { root: ctx.sandboxRoot, repo: false, branch: null, sha: null, committed: false };
  if (fs.existsSync(path.join(ctx.sandboxRoot, ".git"))) {
    sandboxFace.repo = true;
    const git = (args) => execFileP("git", ["-C", ctx.sandboxRoot, ...args], { timeout: 60_000, maxBuffer: 8 * 1024 * 1024 });
    await git(["add", "-A"]);
    try {
      await git(["-c", "user.email=add-round@ipradar.local", "-c", "user.name=add-round", "commit", "-m", `add-round ${ctx.roundId}: ${ctx.source}`]);
      sandboxFace.committed = true;
    } catch (e) {
      if (!/nothing to commit|no changes added/i.test(`${e.stderr ?? ""}\n${e.message ?? ""}`))
        throw Object.assign(new Error(`沙箱提交败:${e.message}`), { code: "infra" });
    }
    sandboxFace.sha = (await git(["rev-parse", "HEAD"])).stdout.trim();
    sandboxFace.branch = (await git(["rev-parse", "--abbrev-ref", "HEAD"])).stdout.trim();
  }
  const gateArt = j(ctx, ART.GATE);
  writeJson(path.join(ctx.dir, ART.REPORT), {
    round_id: ctx.roundId, source: ctx.source, generated_at: new Date().toISOString(),
    sandbox: sandboxFace,
    gate: { commands: gateArt?.results?.length ?? 0, passed: gateArt?.passed ?? null },
    note: "轮产出=沙箱分支,永不自并入 master(人裁终局;spec 定案 9 停止点)",
  });
  return { patch: { sandboxFace } };
}

// CLOSE:主检出防线 + 台账行 + 09-budget 快照(证据先于信封)
async function runClose(ctx, checkpoint) {
  try { await sh("sandbox_assert", [], 60_000, ctx.env); } // 主检出 backend/frontend 零改动防线(RETRO 同款)
  catch (e) { throw Object.assign(new Error(`sandbox_assert rc≠0(主检出污染):${e.message}`), { code: "sandbox_violation" }); }
  const usage = ctx.usage;
  const usageStr = `in=${usage.input} out=${usage.output} total=${usage.totalTokens} cost=${usage.cost.toFixed(8)}`;
  let ledgerNow = null;
  try { ledgerNow = fs.readFileSync(ctx.ledgerFile, "utf8"); } catch { /* 首轮无台账文件=正常 */ }
  if (!(ledgerNow ?? "").includes(`${ADD_LEDGER_TAG}:${ctx.roundId}`)) // 幂等重入:resume 不双记账
    try { await sh("ledger_append", ["add", ctx.modelFace === "real" ? "pipeline-real" : "faux-pipeline", usageStr, `${ADD_LEDGER_TAG}:${ctx.roundId}`], 120_000, ctx.env); }
    catch (e) { throw Object.assign(new Error(`台账写败:${e.message}`), { code: "ledger_failed" }); }
  const knobs = ctx.budgetKnobs;
  writeJson(path.join(ctx.dir, ART.BUDGET), {
    round_id: ctx.roundId, generated_at: new Date().toISOString(),
    env: { // 生效值(OPS_ADD_* 三旋钮+est+共享月帽;无 token 界——发现轮同律)
      OPS_PIPELINE_BUDGET_CNY: ctx.budgetCny,
      OPS_ADD_MAX_MODEL_CALLS: knobs.maxModelCalls,
      OPS_ADD_WALL_CLOCK_S: knobs.wallClockS,
      OPS_ADD_SPEND_CAP_CNY: knobs.spendCapCny,
      OPS_PIPELINE_MONTHLY_CAP_CNY: knobs.monthlyCapCny,
    },
    readings: {
      usage: { ...usage },
      model_calls: ctx.modelCalls ?? 0,
      wall_s: Number(elapsedWallS(checkpoint.startedAtIso).toFixed(1)),
      monthly: checkpoint.admission ?? null,
    },
  });
  return {};
}

const SCRIPT_STEPS = Object.freeze({ verify: runVerify, gate: runGatePhase, report: runReport, close: runClose });

// ── 脚本相位骨架(预算墙钟头执法 → 步 → 门 → checkpoint)────────────────
async function scriptPhase(task, runtime, context, phase) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook(phase);
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: STAGE_OF[phase] } });
  const ctx = buildCtx(input, cur);
  if (phase === "verify") {
    try { bootstrapRoundDir(ctx, cur); }
    catch (e) { return finishFailed(runtime, context, { message: `${STAGE_OF[phase]}:${e.message}`, detail: { code: e.code ?? "infra", stage: STAGE_OF[phase] } }); }
  }
  const stage = { name: STAGE_OF[phase], status: "done", attempts: 1, dur_ms: 0, usage: null }; // 脚本步恒零模型面(旧律)
  const t0 = Date.now();
  let rec;
  try { rec = await SCRIPT_STEPS[phase](ctx, cur); }
  catch (e) { // 域失败=终态(旧 fail 三元组;工件已写面保留=证据不灭失)
    return finishFailed(runtime, context, { message: `${STAGE_OF[phase]}:${e.message}`, detail: { code: e.code ?? "infra", stage: STAGE_OF[phase] } });
  }
  stage.dur_ms = Date.now() - t0;
  const staged = [...cur.stages, stage];
  if (phase === "close") ctx.envelope = composeEnvelope({ ...cur, stages: staged }, ctx); // G_CLOSE 前置(旧引擎职责位)
  const gateRec = evalGate(phase, ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:${STAGE_OF[phase]}:${gateRec.reason}`, detail: { code: gateRec.code ?? "infra", stage: STAGE_OF[phase] } }); // 门红=终态(fail-closed)
  const next = phaseAfter(phase);
  const checkpoint = { ...cur, ...(next ? { phase: next } : {}), stages: staged, modelCalls: ctx.modelCalls, usage: { ...ctx.usage }, ...(rec?.patch ?? {}) }; // 相位推进=phase 字段前移(缺它=同相位重跑死循环)
  return next
    ? advance(runtime, context, checkpoint, {}, ctx)
    : finishOk(runtime, context, composeEnvelope(checkpoint, ctx)); // close 终态=result=信封
}

// ── 模型相位(DOSSIER/IMPLEMENT 共骨架;一轮一会话两次 submit)───────────
const MODEL_LEGS = Object.freeze({
  dossier: { stage: "DOSSIER", gate: "G_DOSSIER", promptFile: "dossier.md", artifact: ART.DOSSIER, transcript: ART.DOSSIER_T },
  implement: { stage: "IMPLEMENT", gate: "G_IMPLEMENT", promptFile: "implement.md", artifact: ART.IMPL, transcript: ART.IMPL_T },
});

// 会话 UsageDoc 活和(discover-round roundUsage 同形拷形;字段面=旧 ctx.usage 形状)
async function roundUsage(runtime, convId, context) {
  const v = await runtime.snapshot(UsageDoc, convId, context) ?? {};
  let input = 0, output = 0, totalTokens = 0, cost = 0;
  for (const bucket of [v.models, v.tools])
    for (const u of Object.values(bucket ?? {})) {
      input += u?.input ?? 0; output += u?.output ?? 0;
      totalTokens += u?.totalTokens ?? 0; cost += u?.cost?.total ?? 0;
    }
  return { input, output, totalTokens, cost };
}

function buildUserMsg(phase, ctx, checkpoint) {
  const prompt = fs.readFileSync(addPromptPath(MODEL_LEGS[phase].promptFile), "utf8");
  if (phase === "dossier")
    return `${prompt}\n\n---\n\n候选卡(已 APPROVE,只读):\n${JSON.stringify(checkpoint.card ?? { source: ctx.source }, null, 2)}\n\n终答契约:单条 JSON(交接单七键;不得夹其他文本)。`;
  const dossier = checkpoint.dossier ?? {};
  const stem = slugify(dossier.name ?? "");
  return `${prompt}\n\n---\n\n交接单:\n${JSON.stringify(dossier, null, 2)}\n\n源文件名 stem(钉死):${stem}\n期望路径:backend/tests/sources/test_${stem}.py 与 backend/ipdb/_sources/${stem}.py\n沙箱根:${ctx.sandboxRoot}\n沙箱 backend 目录:${path.join(ctx.sandboxRoot, "backend")}\npytest 解释器(绝对路径):${ctx.python}\n\n终答契约:单条 JSON {name,test_file,source_file,red_observed,green_observed,notes}(路径相对沙箱根;不得夹其他文本)。`;
}

function consumeModelText(phase, text) {
  let parsed = null;
  try { parsed = JSON.parse(text); } catch { return { ok: false, reason: `终答非 JSON(须单条 JSON,得到 ${text.slice(0, 80)}…)` }; }
  if (phase === "dossier") {
    const r = dossierShape(parsed);
    return r.ok ? { ok: true, value: { dossier: r.dossier } } : { ok: false, reason: `交接单形状:${r.reason}` };
  }
  const r = implementSummaryShape(parsed);
  return r.ok ? { ok: true, value: { summary: r.summary } } : { ok: false, reason: `实现摘要:${r.reason}` };
}

async function modelLeg(task, runtime, context, phase) {
  const input = task.input;
  const cur = task.state.checkpoint;
  crashHook(phase);
  const leg = MODEL_LEGS[phase];
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso }); // ③
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: leg.stage } });
  const pb = preModelCall({ roundType: "add", knobs: input.knobs, modelCalls: cur.modelCalls, startedAtIso: cur.startedAtIso }); // ①③(每 attempt 提交前)
  if (!pb.ok) return finishFailed(runtime, context, { message: pb.message, detail: { code: pb.code, stage: leg.stage } });

  const ctx = buildCtx(input, cur);
  const conversation = await runtime.conversation(runtime.conversationId, context);
  if (!conversation) return finishFailed(runtime, context, { message: `${leg.stage}:轮会话缺席`, detail: { code: "infra", stage: leg.stage } });
  const host = ensureAddHost(ctx, runtime.conversationId); // 轮级编码宿主(模型面工具;faux=罐装回合驱动真工具)

  const attempt = cur.attempt ?? 1;
  const requestId = attempt <= 1 ? `round-${input.roundId}-${phase}` : `round-${input.roundId}-${phase}-a${attempt}`; // 幂等纪律形;同 attempt 崩溃重放同 key
  const userMsg = buildUserMsg(phase, ctx, cur);
  const t0 = Date.now();
  const submission = await conversation.submit({ type: "input", content: userMsg, requestId }, context);
  const settled = await submission.wait(context); // 恰好一次;同 key 崩溃重放不双花
  const view = await runtime.context(runtime.conversationId, context);
  const messages = view.entries.filter((e) => e.kind === "pi.assistant").flatMap((e) => e.model);
  const modelCallsNow = messages.length; // 会话累计回合数=调用计数(工具循环逐回合计)
  const last = messages[messages.length - 1];
  const text = last?.content?.filter((c) => c.type === "text").map((c) => c.text).join("") ?? "";
  const retryOr = (code, message) => attempt < 2 // 旧 retry≤1 面:结算坏/空文本/形状坏重发新 requestId;失败 attempt 计数同步入账(旧律重试同计)
    ? advance(runtime, context, cur, { attempt: attempt + 1, modelCalls: modelCallsNow }, ctx)
    : finishFailed(runtime, context, { message, detail: { code, stage: leg.stage } });
  if (settled.status !== "done") return retryOr("model_face", `${leg.stage}:submission_${settled.status}`);
  if (!text) return retryOr("empty_text", `${leg.stage}:empty_text`);

  const usageNow = await roundUsage(runtime, runtime.conversationId, context);
  const post = postModelCall({ roundType: "add", knobs: input.knobs, totalTokens: usageNow.totalTokens, costCny: usageNow.cost }); // ②(skip:无 token 界)④
  if (!post.ok) return finishFailed(runtime, context, { message: post.message, detail: { code: post.code, stage: leg.stage } });

  const consumed = consumeModelText(phase, text);
  if (!consumed.ok) return retryOr("model_face", `${leg.stage}:${consumed.reason}`);

  // transcript(input + 本腿种子增量 + 本腿回合增量;行型=旧 faux.mjs:input/registry_seed/message)
  const sys = fs.readFileSync(addPromptPath("system.md"), "utf8"); // 会话 instructions 实际装载面(run-add 创建会话时装入,同源同字)
  const seedBase = host.seedMark ?? 0;
  const lines = [
    JSON.stringify({ type: "input", stage: leg.stage, system_sha: sha(sys), user_sha: sha(userMsg), meta: null }),
    ...host.seeds.slice(seedBase).map((sd) => JSON.stringify({ type: "registry_seed", call_id: sd.call_id, tool: sd.tool, sc: sd.sc })),
    ...messages.slice(cur.modelCalls).map((m) => JSON.stringify({ type: "message", role: m.role, content: m.content, stopReason: m.stopReason ?? null })),
  ];
  fs.appendFileSync(path.join(ctx.dir, leg.transcript), lines.join("\n") + "\n");
  host.seedMark = host.seeds.length;

  // 工件
  if (phase === "dossier") writeJson(path.join(ctx.dir, leg.artifact), { round_id: input.roundId, bench: false, dossier: consumed.value.dossier, generated_at: new Date().toISOString() });
  else writeJson(path.join(ctx.dir, leg.artifact), { round_id: input.roundId, stem: slugify((checkpointDossier(cur, input)?.name) ?? ""), summary: consumed.value.summary, generated_at: new Date().toISOString() });

  const gateRec = evalGate(phase, ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:${leg.stage}:${gateRec.reason}`, detail: { code: gateRec.code ?? "model_face", stage: leg.stage } });

  // 相位步 usage=本腿增量(会话累计差分;usage 求和律:各步之和==信封 usage)
  const usageDelta = { input: usageNow.input - cur.usage.input, output: usageNow.output - cur.usage.output, totalTokens: usageNow.totalTokens - cur.usage.totalTokens, cost: usageNow.cost - cur.usage.cost };
  const next = phaseAfter(phase);
  const checkpoint = {
    ...cur, phase: next, attempt: 1,
    stages: [...cur.stages, { name: leg.stage, status: "done", attempts: attempt, dur_ms: Date.now() - t0, usage: usageDelta }],
    modelCalls: modelCallsNow,
    usage: { ...usageNow },
    prompt_hashes: { ...cur.prompt_hashes, [leg.stage]: sha(`${sys}\n${userMsg}`) },
    ...(phase === "dossier" ? { dossier: consumed.value.dossier } : { implement: consumed.value.summary }),
  };
  return advance(runtime, context, checkpoint, {}, ctx);
}
const checkpointDossier = (cur, input) => cur.dossier ?? input.dossier ?? null;

// DOSSIER 相位:bench 形态跳过(定案 2 开关位;交接单=input.dossier 预填,同门校验,零模型面)
async function dossierPhase(task, runtime, context) {
  const input = task.input;
  if (input.bench !== true) return modelLeg(task, runtime, context, "dossier");
  const cur = task.state.checkpoint;
  crashHook("dossier");
  const b = stepBoundary({ roundType: "add", knobs: input.knobs, startedAtIso: cur.startedAtIso });
  if (!b.ok) return finishFailed(runtime, context, { message: b.message, detail: { code: b.code, stage: "DOSSIER" } });
  const r = dossierShape(input.dossier);
  if (!r.ok) return finishFailed(runtime, context, { message: `DOSSIER:bench 交接单形状坏:${r.reason}`, detail: { code: "model_face", stage: "DOSSIER" } });
  const ctx = buildCtx(input, cur);
  writeJson(path.join(ctx.dir, ART.DOSSIER), { round_id: input.roundId, bench: true, dossier: r.dossier, generated_at: new Date().toISOString() });
  const gateRec = evalGate("dossier", ctx);
  gates.appendGate(ctx.dir, ctx.roundId, gateRec);
  if (!gateRec.pass) return finishFailed(runtime, context, { message: `GATE:DOSSIER:${gateRec.reason}`, detail: { code: gateRec.code ?? "model_face", stage: "DOSSIER" } });
  return advance(runtime, context, { ...cur, phase: "implement", dossier: r.dossier }, {}, ctx); // stages 不记跳过相位(discover bench 截断同律)
}

// ── defineTask ─────────────────────────────────────────────────────────
export const addRoundTask = defineTask({
  name: ADD_TASK_NAME,
  version: 1,
  initial: (input) => ({
    phase: "verify",
    roundId: input.roundId,
    startedAtIso: new Date().toISOString(), // 墙钟真源:initial 一次,恢复不改写(续算)
    modelCalls: 0,
    usage: { input: 0, output: 0, totalTokens: 0, cost: 0 },
    stages: [],
    prompt_hashes: {},
    attempt: 1,
  }),
  phases: {
    verify: (task, runtime, context) => scriptPhase(task, runtime, context, "verify"),
    dossier: (task, runtime, context) => dossierPhase(task, runtime, context),
    implement: (task, runtime, context) => modelLeg(task, runtime, context, "implement"),
    gate: (task, runtime, context) => scriptPhase(task, runtime, context, "gate"),
    report: (task, runtime, context) => scriptPhase(task, runtime, context, "report"),
    close: (task, runtime, context) => scriptPhase(task, runtime, context, "close"),
  },
  abort: async (_task, runtime, context) => { // 中止终态留痕(discover/health mkAbort 同款)
    await runtime.commit(() => ({ status: "terminal", outcome: { status: "aborted" } }), context);
  },
});
