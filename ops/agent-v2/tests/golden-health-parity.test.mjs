// golden-health-parity.test.mjs — golden 对拍补齐(票 #232;ops/agent/golden/cases.json
// 健康轮管线例 pipeline_health_full_faux):旧引擎(ops/agent/pipeline.mjs runPipeline,
// in-proc)vs 新任务面(ops/agent-v2 run-health.mjs 全链 PROBE→CLOSE,子进程)逐工件
// 位等价对拍。与 golden-discover-parity.test.mjs(#227 T3)合成「管线面 golden 2/2」。
// 世界=f run-golden.mjs runCase 同构(fixture 判例树 + curl/OPS_EVAL_PY stub + 抑制规则
// fixture,出处:run-golden.mjs writePrecedents/stubCurl/stubPy;用例数据单源=cases.json
// 运行时读,不手抄)。归一化=shadow-diff.mjs normalizeText(导出面,#232 复用勿 fork)
// + 票面窄面叠层(usage 三计数/wall_s:ENVELOPE.md §usage 计量边界合法差,cost 逐字)。
// 口径裁决(父会话 2026-10-28,A+C):管线面=位等价对拍;判断器 8 例=legacy 面回归钉
// (golden-judge-regression.test.mjs),不在此文件。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { GOLDEN_SWEEP_ANCHORS, anchorRow } from "../../agent/anchor-mirror.mjs"; // #194 C3-2 单源(run-golden.mjs stubPy 同引)
import { normalizeText } from "../shadow-diff.mjs";

const execFile = promisify(execFileCb);
const V2 = path.resolve(import.meta.dirname, "..");
const CASE = JSON.parse(fs.readFileSync(path.resolve(V2, "..", "agent", "golden", "cases.json"), "utf8"))
  .cases.find((c) => c.id === "pipeline_health_full_faux");
const ROUND = "2026-06-01-0400-health"; // run-golden.mjs roundType 分支同字面(#208 T2:健康例原字面)
const FIXTURES = path.resolve(V2, "..", "agent", "fixtures", "pipeline");

// fixture 判例树(run-golden.mjs writePrecedents 逐字副本:A 命中 health+discover 检索词;
// B 在库不命中任何管线例检索词——闭集负例载体,tree 同构保金样世界零漂移)
const PREC_A = "2026-06-01-golden-aggregator.md";
const PREC_B = "2026-06-02-golden-matrix-nolayer.md";
const writePrecedents = (dir) => {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, PREC_A),
    `---\nid: 2026-06-01-golden-aggregator\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信,\n  排他率必须实测(冻结门线外另议)。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`);
  fs.writeFileSync(path.join(dir, PREC_B),
    `---\nid: 2026-06-02-golden-matrix-nolayer\ndate: 2026-06-02\nsubject: fixture — 语义矩阵 NO-LAYER 层读数约定\ncontext: >\n  truth 层无取样资产时读数记 NO-LAYER,\n  摘要员如实提及不计入异常。\nhuman_ruling: >\n  认可约定。\nreward:\n  hard_gates: {}\n  ruling_agreement: agreed\n---\n\n正文:语义矩阵 NO-LAYER 层读数约定(零检索词命中样本)。\n`);
  fs.writeFileSync(path.join(dir, "_schema.md"), "schema 说明(注入排除面)。\n");
};

// stub 脚本(run-golden.mjs stubCurl/stubPy 同型:CLI 边界替身,工具实现层全真;零网络)
const stubCurl = (rules) => `#!/usr/bin/env bash
url="${'${@: -1}'}"
d=180; s=0
case "$url" in
${rules.map((r) => `  *${r.match}*) d=${r.days ?? 180}; s=${r.status ?? 0} ;;`).join("\n")}
esac
if (( s >= 400 )); then
  printf 'HTTP/1.1 %s stub\\r\\nContent-Length: 0\\r\\n\\r\\n' "$s"
  exit 0
fi
printf 'HTTP/1.1 200 OK\\r\\nLast-Modified: %s\\r\\nContent-Length: 4\\r\\n\\r\\n' \\
  "$(date -u -d "@$(( $(date +%s) - d * 86400 - 600 ))" '+%a, %d %b %Y %H:%M:%S GMT')"
exit 0
`;
const stubPy = (matrix) => `#!/usr/bin/env bash
SWEEP_OK='${JSON.stringify({ kind: "anchor_sweep", anchors: GOLDEN_SWEEP_ANCHORS, n_total: GOLDEN_SWEEP_ANCHORS.length, n_fail: 0, failures: [],
  results: GOLDEN_SWEEP_ANCHORS.map(([ip, expect]) => anchorRow({ ip, expect })) }).replace(/'/g, "'\\''")}'
case " $* " in
  *--anchor-sweep*) printf '%s\\n' "$SWEEP_OK" ;;
  *) printf '%s\\n' '${JSON.stringify(matrix).replace(/'/g, "'\\''")}' ;;
esac
`;

// 世界置备(双侧同构:tmp/docs + 判例树 + stub + 抑制规则 fixture[cases.json 单源])
function seedSide(tag) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), `v2-hpar-${tag}-`));
  const docsRoot = path.join(tmp, "docs");
  const ops = path.join(docsRoot, "ops");
  writePrecedents(path.join(ops, "precedents"));
  fs.mkdirSync(path.join(ops, "rules"), { recursive: true });
  fs.writeFileSync(path.join(ops, "rules", "suppressions.json"), JSON.stringify(CASE.pipeline.rules, null, 2) + "\n");
  const stubDir = path.join(tmp, "stubs");
  fs.mkdirSync(stubDir, { recursive: true });
  const writeStub = (name, text) => { const p = path.join(stubDir, name); fs.writeFileSync(p, text); fs.chmodSync(p, 0o755); return p; };
  writeStub("curl", stubCurl(CASE.stubs.curl_age_days));
  const py = writeStub("py-matrix", stubPy(CASE.stubs.matrix));
  const env = {
    ...process.env,
    DOCS_ROOT: docsRoot, PRECEDENTS_DIR: path.join(ops, "precedents"), LEDGER_FILE: path.join(ops, "ledger.md"),
    PATH: `${stubDir}:${process.env.PATH}`, OPS_EVAL_PY: py, OPS_SWEEP_DRY_RUN: "1",
  };
  return { tmp, docsRoot, ops, env };
}

// 可比工件闭集(shadow-diff COMPARABLE 同源 + 01/02/09:全链双侧均在——shadow 载具停笔
// RETRO 才排除 09,本对拍双侧跑全链到 CLOSE,09-budget 双侧落件)。NEW 侧白名单
// .v2-claim.json(跨库撞轮认领件,shadow-diff isUndeclaredNewFile 同声明)。
const COMPARABLE = ["01-", "02-", "03-", "04-", "05-", "06-", "07-", "08-", "09-budget.json", "gates.json"];

test("golden 对拍 pipeline_health_full_faux:旧 runPipeline 全链 vs v2 run-health 全链,工件闭集位等价", async () => {
  const old = seedSide("old");
  const neu = seedSide("new");
  try {
    // —— 旧侧:in-proc runPipeline(run-golden.mjs pipeline 分支同调法;env 先于 import)——
    const saved = { DOCS_ROOT: process.env.DOCS_ROOT, PRECEDENTS_DIR: process.env.PRECEDENTS_DIR, LEDGER_FILE: process.env.LEDGER_FILE, OPS_EVAL_PY: process.env.OPS_EVAL_PY, OPS_SWEEP_DRY_RUN: process.env.OPS_SWEEP_DRY_RUN, PATH: process.env.PATH };
    Object.assign(process.env, old.env);
    let oldEnv = null;
    try {
      const { runPipeline, DEFAULT_FIXTURES_DIR } = await import("../../agent/pipeline.mjs");
      const r = await runPipeline({ type: "health", roundId: ROUND, fixturesDir: DEFAULT_FIXTURES_DIR,
        stdout: { write: () => true }, stderr: { write: () => true } });
      oldEnv = r?.envelope ?? null;
    } finally {
      for (const k of Object.keys(saved)) {
        if (saved[k] === undefined) delete process.env[k];
        else process.env[k] = saved[k];
      }
    }
    assert.ok(oldEnv?.ok, `旧引擎例应跑出 ok 信封:${JSON.stringify(oldEnv)?.slice(0, 300)}`);

    // —— 新侧:子进程 run-health.mjs 全链(PROBE→CLOSE 缺省;faux fixtures 缺省)——
    const { stdout } = await execFile(process.execPath, [path.join(V2, "run-health.mjs"), ROUND,
      "--fixtures", FIXTURES, "--db", path.join(neu.tmp, "v2.sqlite")], { env: neu.env, maxBuffer: 32 * 1024 * 1024 });
    const newR = JSON.parse(stdout.trim().split("\n").filter((l) => l.startsWith("{")).pop());
    assert.equal(newR.ok, true, `v2 例应终态 ok(失败面可读):${JSON.stringify(newR.error ?? newR).slice(0, 300)}`);

    // —— 逐工件位等价(归一化窄面:TS/dur_ms/tmp/-rN=shadow-diff 单源;usage 三计数/
    // wall_s=票面合法差叠层;cost 逐字)——
    const base = { oldTmp: old.tmp, newTmp: neu.tmp, roundId: ROUND };
    const norm = (t) => normalizeText(t, base)
      .replace(/"(input|output|totalTokens)":\s*\d+/g, '"$1": N')
      .replace(/"wall_s":\s*[\d.]+/g, '"wall_s": 0')
      .replace(/\d+ 字节/g, "N 字节") // G_CLOSE reason 信封字节数=usage 数位下游(golden-discover-parity 同规则;shadow-diff 停笔 RETRO 不遇此面)
      .replace(/(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT/g, "<HTTP-DATE>"); // stub curl Last-Modified 毫秒漂移(金样自身 600s 余量同设计;语义面=age_days/分桶,逐字比不变)
    const dirA = path.join(old.ops, "rounds", ROUND);
    const dirB = path.join(neu.ops, "rounds", ROUND);
    const filesOf = (d) => fs.existsSync(d) ? fs.readdirSync(d).filter((f) => !fs.statSync(path.join(d, f)).isDirectory()) : [];
    const oldFiles = filesOf(dirA).filter((f) => f !== "state.json"); // OLD=磁盘状态机;NEW 无(state 面=checkpoint,shadow-diff 同排除)
    const newFiles = filesOf(dirB).filter((f) => f !== "state.json" && f !== ".v2-claim.json"); // NEW 白名单(认领件,shadow-diff 同声明)
    const rows = [];
    for (const f of [...new Set([...oldFiles, ...newFiles])].sort()) {
      const inComparable = COMPARABLE.some((p) => f.startsWith(p));
      const o = oldFiles.includes(f), n = newFiles.includes(f);
      if (!inComparable) { rows.push(`SKIP ${f}(闭集外${o && !n ? ",旧侧" : ""})`); continue; } // 结构性差异面(如 -rN 镜像)不假 SAME 不计 DIFF
      if (o && !n) { rows.push(`ONLY-OLD ${f}`); }
      else if (!o && n) { rows.push(`ONLY-NEW ${f}`); }
      else {
        const a = norm(fs.readFileSync(path.join(dirA, f), "utf8"));
        const b = norm(fs.readFileSync(path.join(dirB, f), "utf8"));
        rows.push(`${a === b ? "SAME" : "DIFF"} ${f}`);
        if (a !== b) {
          const la = a.split("\n"), lb = b.split("\n");
          const i = la.findIndex((l, k) => l !== lb[k]);
          rows.push(`  L${i + 1}: OLD=${(la[i] ?? "").slice(0, 160)} | NEW=${(lb[i] ?? "").slice(0, 160)}`);
        }
      }
    }
    const bad = rows.filter((r) => /^(DIFF|ONLY-)/.test(r));
    // 信封相位序列/状态(旧 runPipeline 信封 vs v2;resumed/usage 已知差异面不入)
    assert.deepEqual(newR.pipeline.stages.map((s) => [s.name, s.status]), oldEnv.pipeline.stages.map((s) => [s.name, s.status]), "相位序列/状态不等价");
    // 台账行(RETRO 写面;usage 计数归一,cost 逐字——shadow-diff normLedger 同法)
    const normLedger = (t) => normalizeText(t, base).replace(/in=\d+ out=\d+ total=\d+/g, "in=<N> out=<N> total=<N>");
    const ledA = normLedger(fs.readFileSync(path.join(old.ops, "ledger.md"), "utf8")).trim();
    const ledB = normLedger(fs.readFileSync(path.join(neu.ops, "ledger.md"), "utf8")).trim();
    assert.equal(ledB, ledA, "台账新旧不等价(归一化后)");
    // 双侧可比集非空(空集=闸门失败,shadow-diff P1-1 同判据)
    assert.ok(rows.some((r) => r.startsWith("SAME")), `可比工件集为空或全异:\n${rows.join("\n")}`);
    assert.deepEqual(bad, [], `golden pipeline_health_full_faux 位等价破口:\n${rows.join("\n")}`);
    console.log(`[golden-parity] pipeline_health_full_faux 逐件清单:\n  ${rows.join("\n  ")}`);
  } finally {
    fs.rmSync(old.tmp, { recursive: true, force: true });
    fs.rmSync(neu.tmp, { recursive: true, force: true });
  }
});
