#!/usr/bin/env node
// mine-failures.mjs — 加源域失败矿掘器(票 #346 分析师工件;提案者第一输入,
// SKILL.md 工作循环第 1 步的落件)。
//
// 语义:输入一个 sweep 工件目录(dev/add-bench/sweeps/<名>/,主会话跑批件
// dev/add-bench/sweep.mjs 的落件,untracked 本地件),扫描布局 <题>/r<k>/<题>/
// trial.json(run-trial.mjs 单题信封),把失败面归到三层位 + 兜底,数出分题失败
// 测试函数计数与跨题 Top——给提案者看的「哪些题死在哪一层、哪些断言函数反复红」。
//
// 三失败层位(#346 票面,与 SKILL.md 心法同一张表;层位序有先验,不可互换):
//   ① verify-gate    轮 failed + freshness 门面(error.detail.code=freshness_gate
//                     或 message GATE:VERIFY)——证据基问题,门是裁判面禁改,提案者
//                     无刀,报人面裁(#345 证据基扩展先例)。层位序最高:VERIFY 红轮
//                     的沙箱剥净=确定性 0,摘要里的模块缺席/断言红是门的下游后果,
//                     归 ① 不归 ②③(graded-baseline-2 判例:结构死题轮照打分)。
//   ② collection-error 摘要含 ModuleNotFoundError/ImportError/cannot import——
//                     导入/类名层(模块名或类名对不上钥匙),提示词/交接面的刀。
//   ③ behavior       摘要 FAILED 行——实现深度层(逐源特异行为断言),实现提示词的刀。
//   兜底:pass(trial ok 全绿)/ leak(泄漏闸红,候选作废面)/ other(其余:
//   trial.json 缺席或不可解析=轮崩溃面、轮 failed 非 freshness 等)——宁红勿漏,
//   失败不静默丢格。
//
// 输入只读:矿掘器不改工件、不跑模型、零网络(读盘分析件);考题名只从工件透传
// 到 stdout 报告(答案面工件,不入仓——文件放置规范;本文件自身零考题名)。
//
// 用法:node mine-failures.mjs <sweepDir> [--json]
//   <sweepDir> = dev/add-bench/sweeps/<名>/(绝对或相对);--json 出机器面 JSON。
// 退出码:0=矿掘完成(矿掘是分析不是闸,失败面照常出报告);2=用法/目录不存在。
import fs from "node:fs";
import path from "node:path";

// 展示序(层位语义序 ①②③ 在前,绿/作废/兜底在后);JSON 面字段名同款。
export const LAYERS = Object.freeze(["verify-gate", "collection-error", "behavior", "pass", "leak", "other"]);

// FAILED 行解析:取 pytest 短摘要行「FAILED <id>(- 原因)?」的函数 id;同摘要重复
// (短摘要与全文两现)去重——宁少算勿多算,同一断言不数两遍。
export function parseFailedFns(summary) {
  const ids = [];
  for (const m of String(summary ?? "").matchAll(/^FAILED[ \t]+(\S+)/gm)) {
    if (!ids.includes(m[1])) ids.push(m[1]);
  }
  return ids;
}

const IMPORT_ERR_RE = /ModuleNotFoundError|ImportError|cannot import/;

// 摘要里第一行导入错原文(截尾)——collection-error 层的刀口证据。
function importErrLine(summary) {
  const line = String(summary ?? "").split("\n").find((l) => IMPORT_ERR_RE.test(l));
  return line ? line.trim().replace(/^E\s+/, "").slice(0, 160) : "导入错(行不可寻)";
}

// 单 trial 归层(纯函数;层位序 = pass → verify-gate → collection-error → behavior
// → leak → other,注释见头注)。failedFns 照记各层(verify-gate 的缺席面是下游
// 后果,计数不入分但留证据)。
export function classifyTrial(trial) {
  const round = trial?.round ?? {};
  const err = round?.error ?? {};
  const summary = trial?.score?.summary ?? "";
  const failedFns = parseFailedFns(summary);
  if (trial?.ok === true)
    return { layer: "pass", reason: "全绿(轮 completed ∧ leak 绿 ∧ score_pass=1)", failedFns, importSignal: false };
  const code = err?.detail?.code ?? "";
  if (round?.status === "failed" && (code === "freshness_gate" || /GATE:VERIFY/.test(String(err?.message ?? ""))))
    return { layer: "verify-gate", reason: code || "verify_red", failedFns, importSignal: IMPORT_ERR_RE.test(summary) };
  if (IMPORT_ERR_RE.test(summary))
    return { layer: "collection-error", reason: importErrLine(summary), failedFns, importSignal: true };
  if (failedFns.length)
    return { layer: "behavior", reason: `${failedFns.length} 个行为断言红`, failedFns, importSignal: false };
  if (trial?.leak?.ok === false)
    return { layer: "leak", reason: `泄漏闸红(${trial.leak?.hits?.length ?? "?"} 命中,候选作废面)`, failedFns, importSignal: false };
  return {
    layer: "other",
    reason: round?.status === "failed" ? `轮 failed:${String(err?.message ?? "无错误信息").slice(0, 120)}` : "无失败信号",
    failedFns, importSignal: false,
  };
}

// sweep 目录矿掘:布局 <题>/r<k>/<题>/trial.json;无 r<k> 子目录的目录不入题面
// (sweep 目录里的手工工件/笔记,非 run 布局)。分题 + 跨题两层数。
export function mineSweepDir(sweepDir) {
  const abs = path.resolve(sweepDir);
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) throw new Error(`sweep 目录不存在:${sweepDir}`);
  const layerTotals = {};
  const fnTotals = new Map(); // fn → {count, questions:Set}(跨题聚合)
  const perQuestion = [];
  let runsTotal = 0;
  for (const ent of fs.readdirSync(abs, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (!ent.isDirectory()) continue;
    const qDir = path.join(abs, ent.name);
    const runs = fs.readdirSync(qDir, { withFileTypes: true })
      .filter((e) => e.isDirectory() && /^r\d+$/.test(e.name)).map((e) => e.name).sort();
    if (!runs.length) continue;
    const q = { name: ent.name, runs: [], layerCounts: {}, failedFnCounts: [], meanFrac: null, passes: 0 };
    const qFns = new Map(); // fn → count(题内聚合)
    const fracs = [];
    for (const rn of runs) {
      const tf = path.join(qDir, rn, ent.name, "trial.json");
      let rec;
      if (!fs.existsSync(tf)) {
        rec = { run: rn, layer: "other", reason: "trial.json 缺席(轮崩溃/中断面)", failedFns: [], importSignal: false };
      } else {
        try {
          const t = JSON.parse(fs.readFileSync(tf, "utf8"));
          rec = {
            run: rn,
            roundStatus: t?.round?.status ?? null,
            leakOk: t?.leak?.ok ?? null,
            scorePass: t?.score?.pass ?? null,
            frac: typeof t?.score?.frac === "number" && Number.isFinite(t.score.frac) ? t.score.frac : null,
            ...classifyTrial(t),
          };
          if (t?.score?.pass === 1) q.passes += 1;
          if (typeof rec.frac === "number") fracs.push(rec.frac);
        } catch (e) {
          rec = { run: rn, layer: "other", reason: `trial.json 不可解析:${e.message}`, failedFns: [], importSignal: false };
        }
      }
      q.runs.push(rec);
      runsTotal += 1;
      layerTotals[rec.layer] = (layerTotals[rec.layer] ?? 0) + 1;
      for (const fn of rec.failedFns) {
        const l = qFns.get(fn) ?? 0;
        qFns.set(fn, l + 1);
        const g = fnTotals.get(fn) ?? { count: 0, questions: new Set() };
        g.count += 1;
        g.questions.add(ent.name);
        fnTotals.set(fn, g);
      }
    }
    q.layerCounts = Object.fromEntries(LAYERS.filter((l) => q.runs.some((r) => r.layer === l)).map((l) => [l, q.runs.filter((r) => r.layer === l).length]));
    q.failedFnCounts = [...qFns.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    q.meanFrac = fracs.length ? fracs.reduce((a, b) => a + b, 0) / fracs.length : null;
    perQuestion.push(q);
  }
  const topFailedFns = [...fnTotals.entries()]
    .map(([fn, v]) => [fn, v.count, [...v.questions].sort()])
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 15);
  return {
    sweep: path.basename(abs),
    questions: perQuestion.length,
    runs: runsTotal,
    layerTotals: Object.fromEntries(LAYERS.filter((l) => layerTotals[l]).map((l) => [l, layerTotals[l]])),
    topFailedFns,
    perQuestion,
  };
}

// 文本报告(人读面;--json 出机器面)
export function renderReport(r) {
  const lines = [];
  lines.push(`矿掘 ${r.sweep}:${r.questions} 题 ${r.runs} trial`);
  lines.push(`层位:${LAYERS.filter((l) => r.layerTotals[l]).map((l) => `${l} ${r.layerTotals[l]}`).join(" · ")}`);
  if (r.topFailedFns.length) {
    lines.push("跨题 Top 失败函数(计次=出现 trial 数;题=归属题):");
    for (const [fn, n, qs] of r.topFailedFns) lines.push(`  ${n}× ${fn}  [${qs.join(", ")}]`);
  } else {
    lines.push("跨题 Top 失败函数:无 FAILED 行(失败全在导入/门面)");
  }
  lines.push("分题:");
  for (const q of r.perQuestion) {
    lines.push(`${q.name}  frac=${q.meanFrac === null ? "?" : q.meanFrac.toFixed(4)}  pass=${q.passes}/${q.runs.length}  层位{${LAYERS.filter((l) => q.layerCounts[l]).map((l) => `${l}:${q.layerCounts[l]}`).join(", ")}}`);
    for (const run of q.runs) {
      const fns = run.failedFns.length ? ` → ${run.failedFns.map((f) => f.split("::").pop()).join(", ")}` : "";
      lines.push(`  ${run.run} ${run.layer}:${run.reason}${fns}`);
    }
  }
  return lines.join("\n");
}

export function main(argv = process.argv.slice(2)) {
  const asJson = argv.includes("--json");
  const args = argv.filter((a) => !a.startsWith("--"));
  if (args.length !== 1) {
    console.error("用法:node mine-failures.mjs <sweepDir> [--json](sweep 目录 = dev/add-bench/sweeps/<名>/)");
    return 2;
  }
  let r;
  try {
    r = mineSweepDir(args[0]);
  } catch (e) {
    console.error(e.message);
    return 2;
  }
  console.log(asJson ? JSON.stringify(r, null, 1) : renderReport(r));
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  process.exit(main());
}
