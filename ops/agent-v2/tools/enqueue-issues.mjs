// tools/enqueue-issues.mjs — 发现轮 ENQUEUE 出口改 GH issue(票 #384;半自动时代入口)。
// 背景:fleet 封存(2026-11-21,#375/#389)后加源走半自动——发现轮达标候选开 GitHub issue
// (label=needs-triage,人裁终局)→ 手动 SDD 实现(ops/agent-v2 add 轮 + add-lift.mjs)。
// 旧出口=queue.md PROPOSE 行(APPROVE 语义是给退役舰队驱动吃的,无人消费)→ #384 起
// **PROPOSE 行停写**;信封 queue_writes 字段保留恒空数组(回放兼容,不删字段)。
//
// 复用通道:ops/pipeline-core/tools/measurement.mjs ghIssueCreate(#184 出口件;#348 修法 A
// repo 定向)——gh CLI 面,GH_TOKEN 鉴权经容器 env 继承(v1 C4 白名单,#364 切流律;
// 生产实证:anchor-sweep finding 自动开票 #381/#391/#393 三轮全成功),目标仓=env
// OPS_GH_REPO(#348:容器快照仓无 remote 须显式定向;空=gh 从 cwd remote 推导)。
//
// 纪律(票面钉死):
//   · fail-soft:issue 出口任何失败/异常(无 token、gh 缺席、gh 非零)**不得把轮打成
//     fail**——轮主体健康=ok;每条 rc+错误摘要落轮目录 enqueue-issues.json(成功也落,
//     审计面;原子写沿 _ops_store 判例)。d4-enqueue.json 写败仍 fail-closed(证据不灭失
//     优先于轮成功,同 v1 ENQUEUE 旧律)。
//   · faux 零外发:modelFace=faux(--fixtures 罐装轮)一律 skip 留痕,零网络零花费
//     (faux provider 同律;OPS_SWEEP_DRY_RUN 影子零外发同精神)。
//   · emit 守卫(resume 防重开,finding-exit.mjs #184 同律):工件先记 phase=emitting
//     再外发、终记 emitted;同轮重入见 emitting/emitted 一律不重开(崩溃窗内外发状态
//     不可知,宁少算交人工核对——issue 重复开可人关,漏开可下轮补);守卫触发不重写
//     工件(已开全稿存活=证据不灭失)。
//   · 判据分类单源:classifyEnqueue 自 v1 steps.mjs import(三判据=代码常量,模型无权改;
//     d4-enqueue.json 写面与 v1 ENQUEUE 逐字段同形——golden 对拍核心工件面不变)。
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { ghIssueCreate } from "../../pipeline-core/tools/measurement.mjs"; // #184/#348 既有 issue 通道(REST 新造面=禁)
import { ARTIFACTS as A } from "../../pipeline-core/artifacts.mjs"; // 工件名表单源(#202 C1:写出/读面禁手抄)
import { classifyEnqueue, ENQUEUE_EXCLUSIVITY_GATE } from "../../pipeline-core/pipeline/steps.mjs"; // #384 提取:三判据分类单源

const execFileP = promisify(execFileCb);
export const ENQUEUE_ISSUES_ARTIFACT = "enqueue-issues.json"; // v2 侧新工件名单源(本模块;daily-digest 经轮目录路径读)

const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const writeJson = (p, obj) => fs.writeFileSync(p, JSON.stringify(obj, null, 2) + "\n"); // v1 steps.mjs writeJson 同形(pretty 2 空格+尾换行)

// issue 草稿(纯函数,测试直钉;finding-exit.mjs findingIssueDraft 同式)。字段只取
// d2/d3 工件实有面——无证据即无话,不虚构「预估行数」等管线不存在的读数。
export function candidateIssueDraft({ roundId, row, c = null, m = null } = {}) {
  const flagged = Array.isArray(row?.reasons) && row.reasons.length === 1 && row.reasons[0] === "exclusivity"; // #358 FLAG 面(排他率单项不过+质量案声明)
  const title = `[source] ${row?.candidate ?? "?"} 发现轮候选(${roundId})`;
  const body = [
    "## 来源步",
    `ENQUEUE(发现轮达标候选出口;#384 半自动时代:开 issue 人裁 → 手动 SDD 加源。判据=证据存在性/排他率≥${ENQUEUE_EXCLUSIVITY_GATE}/阳性对照可执行三过${flagged ? "——本条为 FLAG 面:排他率单项不过但 notes 声明同维度质量案(#358 同维度不拒收律,人裁终局)" : ""};判据在代码不在 prompt,模型无权改)`,
    "",
    "## 候选",
    `- 名称:${c?.name ?? row?.name ?? "?"}`,
    `- URL:${c?.url ?? "(无)"}`,
    `- 渠道:${c?.source_channel ?? "?"}`,
    `- 排他率估值:${m?.exclusivity_estimate ?? c?.exclusivity_estimate ?? "?"}(SHORTLIST 估值,MEASURE 无改估权;门槛≥${ENQUEUE_EXCLUSIVITY_GATE})`,
    `- 逐字引用:${c?.quote ?? "(无)"}`,
    `- 证据指针:${c?.evidence_ptr ?? "?"}`,
    `- 理由:${c?.notes ?? "(无)"}`,
    "",
    "## 证据指针",
    `- 短表工件:ops/rounds/${roundId}/${A.DISCOVER_SHORTLIST}`,
    `- 测量工件:ops/rounds/${roundId}/${A.DISCOVER_MEASURE}(证据存在性=${m?.evidence_local_ok ?? "?"};阳性对照=${m?.control_executable ?? "?"})`,
    `- 入队工件:ops/rounds/${roundId}/${A.DISCOVER_ENQUEUE}`,
    `- 出口记录:ops/rounds/${roundId}/${ENQUEUE_ISSUES_ARTIFACT}`,
    "",
    "处置:needs-triage 人裁终局;通过后人手走加源流程(ops/agent-v2 add 轮 + add-lift.mjs 手动 lift)。出口面禁自动接源。",
  ].join("\n");
  return { title, body, labels: ["needs-triage"] };
}

// ENQUEUE 相位步(v2 变体;benchScan 先例):分类(d4 与 v1 逐字段同形)→ issue 出口
// (fail-soft)。返回 { issues_opened, issues_failed, status, ... } 供 scriptPhase 记
// checkpoint(信封 issues_opened)——永不因 issue 出口抛(轮主体健康=ok)。
export async function enqueueStageIssueExit(ctx) {
  const shortlist = j(path.join(ctx.dir, A.DISCOVER_SHORTLIST)) ?? { candidates: [] };
  const measure = j(path.join(ctx.dir, A.DISCOVER_MEASURE)) ?? { results: [] };
  const { enqueued, skipped, flagged } = classifyEnqueue(shortlist, measure);
  // d4 写面与 v1 ENQUEUE 逐字段同形(键序含;golden 对拍核心工件);写败=fail-closed infra
  writeJson(path.join(ctx.dir, A.DISCOVER_ENQUEUE), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
    gate_exclusivity: ENQUEUE_EXCLUSIVITY_GATE, enqueued, skipped, flagged, n_enqueued: enqueued.length, n_skipped: skipped.length, n_flagged: flagged.length });
  const rows = [...enqueued, ...flagged]; // 现状会写 PROPOSE 行的全部面:主路径+#358 FLAG 面
  try {
    return await runEnqueueIssueExit({ roundId: ctx.roundId, dir: ctx.dir, rows, shortlist, measure,
      modelFace: ctx.modelFace, env: ctx.env ?? process.env });
  } catch (e) { // fail-soft 兜底(理论不可达=防御面;#384 票面「issue 出口任何异常不得把轮打成 fail」)
    return { status: "error", reason: String(e?.message ?? e).slice(0, 200), issues_opened: 0, issues_failed: rows.length, issues: [] };
  }
}

// issue 出口编排(永不抛;三 skip 面+emit 守卫+逐条外发)。返回记录同时是 enqueue-issues.json 体。
export async function runEnqueueIssueExit({ roundId, dir, rows = [], shortlist = null, measure = null,
  modelFace = "real", env = process.env, exec = execFileP } = {}) {
  const artifactPath = dir ? path.join(dir, ENQUEUE_ISSUES_ARTIFACT) : null;
  const record = { round_id: roundId, model_face: modelFace, status: null, reason: null, issues_opened: 0, issues_failed: 0, issues: [] };
  const writeArtifact = (extra = {}) => { if (!artifactPath) return;
    fs.writeFileSync(`${artifactPath}.tmp`, JSON.stringify({ ...record, ...extra }, null, 2) + "\n");
    fs.renameSync(`${artifactPath}.tmp`, artifactPath); }; // 原子写(沿 _ops_store 判例)
  const skip = (reason) => { record.status = "skip"; record.reason = reason; writeArtifact({ phase: "skip" }); return record; };
  if (!rows.length) return skip("candidates=0(无达标候选,出口不触发)");
  if (modelFace === "faux") return skip("faux_zero_emit(--fixtures 罐装轮零网络零外发;real 面才开票,#384)");
  // emit 守卫:同轮出口工件已记 emitting/emitted → 不重开(崩溃窗内外发状态不可知,宁少算
  // 交人工核对);不重写工件(已开全稿存活=证据不灭失,finding-exit M4 同律)。
  if (artifactPath) {
    try {
      const prev = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
      if (prev?.round_id === roundId && (prev.phase === "emitting" || prev.phase === "emitted"))
        return { ...record, status: "skip", reason: `emit_guard(出口工件已记 phase=${prev.phase};resume 防重开,不自动重开——人工核对,漏开下轮补)`,
          issues_opened: prev.issues_opened ?? 0, issues_failed: prev.issues_failed ?? 0, issues: [] };
    } catch { /* 无工件=首程,照发 */ }
  }
  const token = String(env.GH_TOKEN ?? env.GITHUB_TOKEN ?? "").trim(); // gh 面两键同收(gh CLI 自身鉴权序);生产=GH_TOKEN 容器 env 继承
  if (!token) return skip("no_token(GH_TOKEN 缺席=降级留痕不炸轮;生产=容器 env 继承 v1 C4 白名单,#364 切流律)");
  record.status = "emit";
  const ghRepo = String(env.OPS_GH_REPO ?? "").trim(); // #348 修法 A:容器快照仓无 remote 须显式定向;空=gh 从 cwd remote 推导(本地开发零变化)
  writeArtifact({ phase: "emitting" }); // 先记意图再外发(emit 守卫的崩溃窗依据)
  const shBy = new Map((shortlist?.candidates ?? []).map((c) => [String(c?.name ?? "").toLowerCase(), c]));
  const mBy = new Map((measure?.results ?? []).map((r) => [String(r?.candidate ?? ""), r]));
  for (const row of rows) {
    const draft = candidateIssueDraft({ roundId, row, c: shBy.get(String(row?.name ?? "").toLowerCase()), m: mBy.get(String(row?.candidate ?? "")) });
    const r = await ghIssueCreate(draft, { exec, repo: ghRepo }); // 分类信封,永不抛(#184 律)
    if (r.ok) {
      record.issues.push({ candidate: row.candidate, status: "created", title: draft.title, ...(r.issue_url ? { issue_url: r.issue_url } : {}) });
      record.issues_opened += 1;
    } else {
      record.issues.push({ candidate: row.candidate, status: "failed", title: draft.title, code: r.error?.code ?? "?", reason: String(r.error?.reason ?? "").slice(0, 200) });
      record.issues_failed += 1;
    }
  }
  record.status = record.issues_failed ? "partial" : "emitted";
  writeArtifact({ phase: "emitted" });
  return record;
}
