#!/usr/bin/env node
// selftest-pipeline.mjs — P0 轮次状态机自测(spec #161 P0 验收门;零 API 零网络;P1 增⑦位等价门,#163;
// P2 增⑧-⑪ #164:规则库判例转写命中(R12 形/R7 形)+闭集负例+在飞真读 ops/items+matrix 裸失败负例)。
// 面:①全 faux 轮跑通到 CLOSE(信封 ok+gates.json 落盘+state 终态+stderr 阶段行+stdout 末行单行 JSON)
//    ②工件清单/分区穷尽/消化条目判例(refuted 恒 low)③预算降级(截尾非失败)④失败面(坏 fixture→
//    model_face 终态+工件保留)⑤replay:--dry 全程可跑+段重放,原件 md5 不变 ⑥CLI 契约(exit 0/1/2)
//    ⑦位等价门(P1,#163):同 stub 下 legacy health 轮(agent.mjs runRound→tools.mjs
//    health_snapshot 产 TSV+matrix 工件)与管线 PROBE 工件逐字节 diff 为空+计数两口径对拍。
// fixture:golden 同型(DOCS_ROOT/precedents 指 tmp+curl stub 前置 PATH);canned 模型回合=仓内
// fixtures/pipeline(README 配对契约)。输出 PIPEPASS/PIPEFAIL,任一 FAIL 退出非零。
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFileCb);
const AGENT = path.dirname(fileURLToPath(import.meta.url));
let pass = 0, fail = 0;
const ok = (name) => { pass++; console.log(`PIPEPASS ${name}`); };
const bad = (name, err) => { fail++; console.log(`PIPEFAIL ${name}: ${err}`); };
async function t(name, fn) { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } }

// ── fixture(env 先于 pipeline.mjs/tools.mjs import;golden writePrecedents/stubCurl 同型)──
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "pipeline-selftest-"));
const DOCS = path.join(TMP, "docs");
const PREC = "2026-06-01-golden-aggregator.md"; // 与 fixtures/pipeline/synth.json 的引用配对(README 契约)
fs.mkdirSync(path.join(DOCS, "ops", "precedents"), { recursive: true });
fs.writeFileSync(path.join(DOCS, "ops", "precedents", PREC),
  `---\nid: 2026-06-01-golden-aggregator\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`);
fs.writeFileSync(path.join(DOCS, "ops", "precedents", "_schema.md"), "schema 说明(注入排除面)。\n");
fs.mkdirSync(path.join(DOCS, "ops", "rules"), { recursive: true });
fs.writeFileSync(path.join(DOCS, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
  { id: "R1", adopted: "2026-10-24", adopted_via: "item-fixture", match: { bucket: "frozen", url_shape: "*dshield.org*" },
    action: "suppress", note: "fixture:dshield 冻结读数为已知探测伪迹", review_at: "2027-01-24" } ] }, null, 2) + "\n");
const STUBS = path.join(TMP, "stubs");
fs.mkdirSync(STUBS);
fs.writeFileSync(path.join(STUBS, "curl"), `#!/usr/bin/env bash\n# selftest stub:curl 传输层替身(golden stubCurl 同型);三冻结锚点+其余新鲜\nurl="\${@: -1}"\nd=30\ncase "$url" in\n  *cinsscore*) d=220 ;;\n  *binarydefense*) d=210 ;;\n  *dshield*) d=200 ;;\nesac\nprintf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - d * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"\nexit 0\n`);
fs.chmodSync(path.join(STUBS, "curl"), 0o755);
// matrix stub:OPS_EVAL_PY 替身(golden stubPy 同型);位等价两腿(legacy health_snapshot 腿与
// 管线 PROBE 腿)共用同一罐装矩阵 JSON。curl stub 时间确定性=UTC 日界截断(#163 位等价判例):
// 同 UTC 日内 Last-Modified 字符串恒定且 age_days 恒=d(日内秒数<86400),两腿先后跑字节稳定;
// 跨日界仅两腿间隙窗口(秒级)理论可达。
const MATRIX_CANNED = { exit_code: 0, counts: { violation: 0, pending: 0, agreement: 4 },
  layers: { truth: { status: "OK", members: 4, sampled: 4, notes: [] }, infra: { status: "OK", members: 8, sampled: 8, notes: [] } },
  buckets: { violation: [], pending: [], agreement: [] } };
fs.writeFileSync(path.join(STUBS, "py-matrix"), `#!/usr/bin/env bash
# selftest stub:OPS_EVAL_PY 替身(golden stubPy 同型);吐罐装矩阵 JSON
printf '%s\n' '${JSON.stringify(MATRIX_CANNED).replace(/'/g, "'\\''")}'
`);
fs.chmodSync(path.join(STUBS, "py-matrix"), 0o755);
process.env.DOCS_ROOT = DOCS;
process.env.PRECEDENTS_DIR = path.join(DOCS, "ops", "precedents");
process.env.LEDGER_FILE = path.join(DOCS, "ops", "ledger.md");
process.env.OPS_EVAL_PY = path.join(STUBS, "py-matrix"); // import-time 面:先于 tools.mjs 装载生效
process.env.PATH = `${STUBS}:${process.env.PATH}`;

const { runPipeline, HEALTH_PIPELINE } = await import("./pipeline.mjs");
const { ERROR_CODES } = await import("./agent.mjs");
const steps = await import("./pipeline/steps.mjs"); // P2 #164 直调 VERIFY 步(规则库/在飞面单元例)
const R1 = "2026-10-23-2340-health";
const mkIo = () => { const buf = { stdout: "", stderr: "" };
  return { stdout: { write: (s) => { buf.stdout += s; return true; } }, stderr: { write: (s) => { buf.stderr += s; return true; } }, buf }; };
const j = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const roundDir = (id) => path.join(DOCS, "ops", "rounds", id);
const stageOf = (env, name) => env.pipeline.stages.find((s) => s.name === name);
const treeMd5 = (dir) => [...fs.readdirSync(dir).sort().map((f) => {
  const p = path.join(dir, f);
  return fs.statSync(p).isDirectory() ? `${f}/:${treeMd5(p)}` : `${f}:${fs.readFileSync(p).toString("base64").slice(0, 9999)}`;
})].join("|");
const spawnPipe = (args, env = {}) => execFileP(process.execPath, [path.join(AGENT, "pipeline.mjs"), ...args],
  { timeout: 300_000, maxBuffer: 32 * 1024 * 1024, env: { ...process.env, ...env } })
  .then((r) => ({ rc: 0, ...r })).catch((e) => ({ rc: typeof e.code === "number" ? e.code : -1, stdout: e.stdout ?? "", stderr: e.stderr ?? "" }));

// P4 #166:逐轮独立 DOCS 树——条目库真写 ops/items,轮间在飞面须隔离(R1 轮的条目不能抑制
// 后续轮的 VERIFY;每轮一棵树=每轮一个干净世界)。fixtures 克隆+synth 补丁件同批上移。
const cloneFixtures = (name) => { const fx = path.join(TMP, name); fs.mkdirSync(fx, { recursive: true });
  fs.copyFileSync(path.join(AGENT, "fixtures/pipeline/triage.json"), path.join(fx, "triage.json"));
  fs.cpSync(path.join(AGENT, "fixtures/pipeline/deep"), path.join(fx, "deep"), { recursive: true });
  return fx; };
const writeSynthFx = (fx, reportText) => fs.writeFileSync(path.join(fx, "synth.json"),
  JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: reportText }], stopReason: "stop" }] }));


const mkTree = (name) => { // 逐轮独立 DOCS 树(P4 #166):precedents/rules 同 R1 fixture,轮间零污染
  const root = path.join(TMP, name);
  fs.mkdirSync(path.join(root, "ops", "precedents"), { recursive: true });
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", PREC), path.join(root, "ops", "precedents", PREC));
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", "_schema.md"), path.join(root, "ops", "precedents", "_schema.md"));
  fs.mkdirSync(path.join(root, "ops", "rules"), { recursive: true });
  fs.copyFileSync(path.join(DOCS, "ops", "rules", "suppressions.json"), path.join(root, "ops", "rules", "suppressions.json"));
  return { root, env: { ...process.env, DOCS_ROOT: root, PRECEDENTS_DIR: path.join(root, "ops", "precedents"), LEDGER_FILE: path.join(root, "ops", "ledger.md") } };
};
let run1;
await t("全 faux 轮:九执行态到 CLOSE,信封 ok+形状只增 pipeline 扩展,顶层 usage=模型步之和", async () => {
  const io = mkIo();
  run1 = await runPipeline({ roundId: R1, ...io });
  assert.equal(run1.ok, true);
  const env = run1.envelope;
  assert.equal(env.ok, true);
  assert.equal(env.round, "health");
  assert.deepEqual(Object.keys(env).sort(), ["ok", "pipeline", "pkg", "queue_writes", "round", "usage", "verify"]);
  assert.equal(env.pipeline.round_id, R1);
  assert.equal(env.pipeline.replayed_of, null);
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), HEALTH_PIPELINE.filter((d) => d.kind !== "terminal").map((d) => d.name));
  assert.ok(env.pipeline.stages.every((s) => ["done", "skipped", "degraded"].includes(s.status)), "成功轮 stage 状态闭集");
  const sum = { input: 0, output: 0, totalTokens: 0, cost: 0 };
  for (const s of env.pipeline.stages) { // 脚本步 usage=null;模型步数字;顶层=模型步之和
    if (s.usage === null) continue;
    for (const k of Object.keys(sum)) { assert.equal(typeof s.usage[k], "number", `${s.name}.${k}`); sum[k] += s.usage[k]; }
  }
  assert.equal(env.pipeline.stages.filter((s) => s.usage !== null).length, 3, "恰三个模型步带 usage");
  const deepStage = stageOf(env, "DEEP");
  assert.equal(deepStage.status, "done", "DEEP 真开启 P4 #166(逐假设单发,零降级)");
  assert.equal(deepStage.attempts, 2, "两假设各一发");
  assert.deepEqual(env.usage, sum);
  assert.ok(fs.existsSync(env.pkg), "pkg(07-synth-report.md)存在");
  assert.deepEqual(env.queue_writes, []);
  assert.equal(env.verify.ok, true);
  assert.equal(env.verify.cited, 1, "canned 报告引 1 fixture 判例");
});

await t("工件清单全落盘+gates.json 九记录全 PASS+state.json 终态 done/CLOSE+原子写无 .tmp 残留", async () => {
  const d = roundDir(R1);
  for (const f of ["01-probe-freshness.tsv", "01-probe-matrix.json", "01-probe-summary.json", "02-verify-survivors.json",
    "02-verify-suppressed.json", "03-triage-hypotheses.json", "03-triage-transcript.jsonl", "04-dispatch-bundles.json",
    "05-deep-verdicts.json", "06-itemize-manifest.json", "07-synth-report.md", "07-synth-transcript.jsonl", "gates.json", "state.json"])
    assert.ok(fs.existsSync(path.join(d, f)), `工件缺:${f}`);
  assert.ok(fs.readdirSync(d).some((f) => /^05-deep-.*\.json$/.test(f) && f !== "05-deep-verdicts.json"), "逐假设工件");
  assert.ok(fs.readdirSync(d).some((f) => /^05-deep-.*-transcript\.jsonl$/.test(f)), "逐假设 transcript");
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.round_id, R1);
  assert.equal(g.records.length, 9, "8 可跑步门+G_CLOSE");
  assert.ok(g.records.every((r) => r.pass === true), `门败:${g.records.filter((r) => !r.pass).map((r) => r.name).join(",")}`);
  assert.ok(g.records.every((r) => typeof r.reason === "string" && /\d/.test(r.reason)), "reason 带数字可回算");
  assert.deepEqual(g.records.map((r) => r.name), ["G_PROBE", "G_VERIFY", "G_TRIAGE", "G_DISPATCH", "G_DEEP", "G_ITEMIZE", "G_SYNTH", "G_RETRO", "G_CLOSE"]);
  const st = j(path.join(d, "state.json"));
  assert.equal(st.status, "done");
  assert.equal(st.stage, "CLOSE");
  assert.equal(st.schema, 1);
  assert.ok(Object.keys(st.prompt_hashes).length >= 3, "模型步 prompt hash 入 state(replay 审计面)");
  const walk = (p) => fs.readdirSync(p).flatMap((f) => { const q = path.join(p, f); return fs.statSync(q).isDirectory() ? walk(q) : [q]; });
  assert.ok(!walk(d).some((p) => p.endsWith(".tmp")), "原子写无 .tmp 残留");
  assert.ok(fs.existsSync(path.join(DOCS, "ops", "retro", `${R1}.json`)), "retro 工件(ops/retro/)");
});

await t("stderr 阶段行语法+stdout 末行=信封单行 JSON(恰一行)", async () => {
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2341-health", env: mkTree("tree-2341").env, ...io });
  assert.equal(r.ok, true);
  const se = io.buf.stderr;
  assert.match(se, /\[stage\] PROBE start\n/, "start 行");
  assert.match(se, /\[stage\] PROBE done gate=PASS dur=\d+s artifact=01-probe-summary\.json\n/, "done 行(gate/dur/artifact)");
  assert.match(se, /\[stage\] CLOSE done gate=PASS dur=\d+s artifact=\(envelope\)\n/, "CLOSE done 行");
  const lines = io.buf.stdout.split("\n");
  assert.equal(lines.length, 2, "stdout 恰一行+末尾换行");
  assert.equal(lines[1], "");
  assert.deepEqual(JSON.parse(lines[0]), r.envelope, "stdout 末行=返回信封逐字");
});

await t("VERIFY 分区穷尽(旗标3=survivors2+suppressed1,R1 抑制 dshield)+DEEP 真开启(A 一律回填)", async () => {
  const d = roundDir(R1);
  const s = j(path.join(d, "01-probe-summary.json"));
  assert.ok(s.urls_n >= 30, `urls_n=${s.urls_n}`);
  assert.equal(s.flags.length, 3);
  assert.equal(s.buckets.frozen, 3);
  assert.equal(s.flags.find((f) => /cinsscore/.test(f.url)).source, "ciarm", "标源名=清单 # 首词(非 host;#164)");
  assert.ok(s.flags.every((f) => !f.error_family), "冻结旗标无 error_family(仅不可达行携带)");
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sv.survivors.length, 2);
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "R1");
  assert.match(sp.suppressed[0].url, /dshield/);
  assert.ok(sv.known_noise_digest.some((r) => r.id === "R1"), "已知误判模式 digest 入幸存工件(C稿 §3.5)");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 2);
  const c = v.verdicts.find((x) => /cinsscore/.test(x.hid));
  const bd = v.verdicts.find((x) => /binarydefense/.test(x.hid));
  assert.equal(c.verdict, "confirmed", "cinsscore 深验确证");
  assert.equal(bd.verdict, "refuted", "binarydefense 深验证伪");
  assert.deepEqual(c.evidence, [{ call_id: "c-cins", field: "age_days", value: 220 }], "A 一律:模型只交选择对,value=宿主回填登记表(220)");
  assert.deepEqual(bd.evidence, [{ call_id: "c-bd", field: "age_days", value: 5 }], "回填 5 ≠ TRIAGE 读数 210——证据腿只认本步实测");
  assert.deepEqual(v.golden_track, [], "真 bundle 轮无金轨迹(不混轮)");
  const bun = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(bun.bundles.length, 2);
  assert.ok(bun.bundles.every((x) => Array.isArray(x.prompt_pkg.precedent_hits) && x.prompt_pkg.precedent_hits.length <= 3), "bundle 带 ≤3 判例命中(C稿 §3.5)");
  assert.ok(bun.bundles.every((x) => typeof x.budget_cny === "number" && x.budget_cny > 0), "bundle 带预算余额");
});

await t("ITEMIZE 真条目(十字段查表零模型):verdict→动作查表+refuted 恒 low 消化+全签 dedup_key+真树落盘", async () => {
  const d = roundDir(R1);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [2, 0, 0, 1]);
  assert.equal(m.rows.length, 2, "一行一假设(verdicts 全量入清单)");
  const itemsDir = path.join(DOCS, "ops", "items");
  const files = fs.readdirSync(itemsDir).filter((f) => f.endsWith(".md"));
  assert.equal(files.length, 2, "真条目落 ops/items 树(接 _ops_items)");
  const parse = (f) => { const t = fs.readFileSync(path.join(itemsDir, f), "utf8");
    const row = m.rows.find((r) => r.item_id === f.replace(/\.md$/, ""));
    return { t, row }; };
  const ciarmRow = m.rows.find((r) => r.source === "ciarm");
  const bdRow = m.rows.find((r) => r.source === "binarydefense");
  assert.equal(ciarmRow.suggested_action, "human_ruling", "confirmed→human_ruling 建议复核(P4 #166 裁,人裁终局)");
  assert.equal(ciarmRow.severity, "high", "confirmed 承 TRIAGE 原级");
  assert.equal(bdRow.suggested_action, "digest_ignore", "refuted→低危消化条目(三小裁②)");
  assert.equal(bdRow.severity, "low", "refuted 恒 low 默认折叠");
  assert.deepEqual(ciarmRow.dedup_key, { source: "ciarm", probe_class: "staleness", error_signature: "age_gt_2x_refresh" }, "全签与 P1 探测器同空间");
  assert.deepEqual(bdRow.dedup_key, { source: "binarydefense", probe_class: "staleness", error_signature: "age_gt_2x_refresh" });
  for (const f of files) { // 十字段冻结面真形
    const { t, row } = parse(f);
    for (const k of ["id:", "action:", "args:", "evidence:", "impact:", "rollback:", "dedup_key:", "severity:", "cause_group:", "status:"])
      assert.ok(t.includes(`
${k}`) || t.startsWith(`---
id:`), `条目 ${f} 缺字段 ${k}`);
    assert.match(t, /status: "?active"?/, "产条恒 active");
    assert.ok(t.includes(`round_id: "${R1}"`), "evidence.round_id 在场(replay 回声/溯源面)");
    assert.ok(row && row.item_id === f.replace(/\.md$/, ""), "manifest 行 ↔ 树文件对号");
  }
  const ciarmFile = fs.readFileSync(path.join(itemsDir, `${ciarmRow.item_id}.md`), "utf8");
  assert.match(ciarmFile, /action: "?human_ruling"?/, "树面 action=查表值");
  assert.match(ciarmFile, /cause_group: "?staleness"?/, "frozen→staleness 组(_ops_detectors.CAUSE_GROUPS 词表)");
  assert.ok(ciarmFile.includes("deep_evidence:") && ciarmFile.includes('"c-cins"'), "深验证据腿入条目 evidence(证据不灭失)");
});

await t("预算硬拦:0.03¥ 截尾 1 条标 unresolved(budget),DISPATCH degraded,轮仍 ok=true", async () => {
  const fx = cloneFixtures("fixtures-budget");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n- binarydefense:预算截尾 unresolved · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=0 unresolved=1;预算门 0.03¥ 硬拦截尾 1 条");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2342-health", fixturesDir: fx, env: { ...mkTree("tree-2342").env, OPS_PIPELINE_BUDGET_CNY: "0.03" }, ...io });
  assert.equal(r.ok, true, "降级不是失败(信封 ok=true+stages 标 degraded)");
  const dp = stageOf(r.envelope, "DISPATCH");
  assert.equal(dp.status, "degraded");
  const d = path.join(mkTree("tree-2342").root, "ops", "rounds", "2026-10-23-2342-health");
  const bun = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(bun.bundles.length, 1);
  assert.equal(bun.truncated.length, 1);
  assert.equal(bun.truncated[0].reason, "unresolved(budget)");
  assert.match(bun.truncated[0].hid, /binarydefense/, "低 severity 先截");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 1, "DEEP 只跑幸存 bundle");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.equal(m.created, 2, "截尾假设转 human_ruling 条目,证据不灭失");
  assert.equal(m.rows.find((x) => /binarydefense/.test(x.hid)).verdict, "unresolved");
});

await t("失败面:坏 TRIAGE fixture → model_face 终态(attempts=2),01/02 工件保留(证据不灭失),code∈九词", async () => {
  const badFx = path.join(TMP, "fixtures-bad");
  fs.mkdirSync(badFx, { recursive: true });
  for (const f of ["synth.json"]) fs.copyFileSync(path.join(AGENT, "fixtures/pipeline", f), path.join(badFx, f));
  fs.cpSync(path.join(AGENT, "fixtures/pipeline/deep"), path.join(badFx, "deep"), { recursive: true });
  fs.writeFileSync(path.join(badFx, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: "不是 JSON(schema 违例负例)" }], stopReason: "stop" }] }));
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2343-health", fixturesDir: badFx, env: mkTree("tree-2343").env, ...io });
  assert.equal(r.ok, false);
  const env = r.envelope;
  assert.equal(env.error.code, "model_face");
  assert.ok(ERROR_CODES.includes(env.error.code), "错误码 ∈ 九词闭集零新词");
  const tr = stageOf(env, "TRIAGE");
  assert.equal(tr.status, "failed");
  assert.equal(tr.attempts, 2, "schema 违例重试≤1 后终态");
  const d = path.join(mkTree("tree-2343").root, "ops", "rounds", "2026-10-23-2343-health");
  assert.ok(fs.existsSync(path.join(d, "01-probe-summary.json")) && fs.existsSync(path.join(d, "02-verify-survivors.json")), "工件保留");
  assert.equal(j(path.join(d, "state.json")).status, "failed");
  assert.match(io.buf.stderr, /\[stage\] TRIAGE fail gate=- code=model_face reason=/, "fail 行语法");
});

// ── P3 #165 新例:①空转金轨迹轮(#162 审 P2-2 裁定①)②SYNTH 判例闭合违例负例
// ③G_SYNTH 深验三计数抽检负例(#162 审 P2-5)④G_DEEP A 一律单元例(直构工件,不依赖 faux 回合)──
await t("空转金轨迹轮(#162 审 P2-2 裁定①):零 need_deep → DISPATCH skipped,DEEP 仍跑 canned faux 回路留痕 golden_track", async () => {
  const fx = cloneFixtures("fixtures-golden");
  fs.writeFileSync(path.join(fx, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", stopReason: "stop",
    text: "{\"hypotheses\":[{\"signal_id\":\"https://cinsscore.com/list/ci-badguys.txt\",\"cause_class\":\"frozen_feed\",\"hypothesis\":\"若冻结读数为探测伪迹,则换 GET 复测可见新鲜 Last-Modified\",\"need_deep\":false,\"probe_hint\":\"none\",\"severity\":\"low\",\"one_line\":\"cinsscore 冻结读数入观察名单\"},{\"signal_id\":\"https://www.binarydefense.com/banlist.txt\",\"cause_class\":\"frozen_feed\",\"hypothesis\":\"若冻结读数为探测伪迹,则换 GET 复测可见新鲜 Last-Modified\",\"need_deep\":false,\"probe_hint\":\"none\",\"severity\":\"low\",\"one_line\":\"binarydefense 冻结读数入观察名单\"}],\"digest\":\"金轨迹轮:2 幸存均入观察,零深验子集。\"}" }] }] }));
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:冻结读数入观察(watch)· severity=low · 建议 watch\n- binarydefense:冻结读数入观察(watch)· severity=low · 建议 watch\n\n抑制 1 条(规则 R1×1——明细见工件)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=0 refuted=0 unresolved=0;零 need_deep,深验未派单\n- 空转金轨迹轮:DEEP 桩仍跑 canned 回路保活性(#162 审 P2-2 裁定①)。");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0102-health", fixturesDir: fx, env: mkTree("tree-0102").env, ...io });
  assert.equal(r.ok, true);
  const env = r.envelope;
  assert.equal(stageOf(env, "DISPATCH").status, "skipped", "零 need_deep → DISPATCH skip(转移图 TRIAGE→ITEMIZE)");
  const deep = stageOf(env, "DEEP");
  assert.equal(deep.status, "done", "金轨迹回路真跑(DEEP 真开启后金轨迹也走真装配)");
  assert.equal(deep.attempts, 1, "金轨迹回路跑了一条 canned 假设");
  assert.notEqual(deep.usage, null, "模型步 usage 在场(faux 零成本)");
  const d = path.join(mkTree("tree-0102").root, "ops", "rounds", "2026-10-24-0102-health");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.deepEqual(v.verdicts, [], "金轨迹 hid 不入 verdicts(不污染条目面)");
  assert.equal(v.golden_track.length, 1);
  assert.equal(v.golden_track[0].hid, "golden-track-canned");
  assert.equal(v.golden_track[0].verdict, "unresolved");
  assert.ok(fs.existsSync(path.join(d, "05-deep-golden-track-canned.json"))
    && fs.existsSync(path.join(d, "05-deep-golden-track-canned-transcript.jsonl")), "金轨迹工件+transcript 留痕");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [2, 0, 0, 1], "watch 条目 2 + 抑制 1(P4:真树落盘)");
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.records.length, 8, "skipped 步无门记录(PROBE..CLOSE 除 DISPATCH)");
  assert.ok(g.records.every((x) => x.pass), "G_DEEP 机检金轨迹在场面");
  assert.ok(g.records.find((x) => x.name === "G_DEEP").reason.includes("golden=1"), "门 reason 带数字可回算");
});

await t("SYNTH 判例闭合违例负例:报告引未注入判例 → 重试≤1 后终态 closure_check,条目已落库不回滚", async () => {
  const fx = cloneFixtures("fixtures-closure");
  writeSynthFx(fx, "## 注入判例\n- 2020-01-01-fabricated-precedent.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0103-health", fixturesDir: fx, env: mkTree("tree-0103").env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "closure_check", "门指定终态码(九词闭集零新词,C稿 §4.4 映射)");
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.status, "failed");
  assert.equal(sy.attempts, 2, "契约违例重试≤1(同提示词重发)");
  const d = path.join(mkTree("tree-0103").root, "ops", "rounds", "2026-10-24-0103-health");
  assert.ok(fs.existsSync(path.join(d, "06-itemize-manifest.json")), "条目已落库不回滚(证据不灭失)");
  const g = j(path.join(d, "gates.json"));
  const synthGates = g.records.filter((x) => x.name === "G_SYNTH");
  assert.equal(synthGates.length, 2, "门重试圈每评留痕(可审计)");
  assert.ok(synthGates.every((x) => x.pass === false && /闭合违例/.test(x.reason)));
  assert.match(io.buf.stderr, /\[stage\] SYNTH fail gate=G_SYNTH code=closure_check/, "fail 行门名随错误带回");
});

await t("G_SYNTH 深验三计数抽检负例(#162 审 P2-5):unresolved=1 ≠ 回算 2(verdicts∪degraded∪truncated)→ 终态 empty_text", async () => {
  const fx = cloneFixtures("fixtures-verdict");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=1");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0104-health", fixturesDir: fx, env: mkTree("tree-0104").env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "empty_text", "计数契约违例=SYNTH 缺省终态码(闭集)");
  const sy = stageOf(r.envelope, "SYNTH");
  assert.equal(sy.attempts, 2);
  const g = j(path.join(mkTree("tree-0104").root, "ops", "rounds", "2026-10-24-0104-health", "gates.json"));
  assert.match(g.records.filter((x) => x.name === "G_SYNTH")[0].reason, /深验计数不符工件:unresolved/);
});

await t("G_DEEP A 一律单元例(直构工件):选择对回填/复述漂移/未知 call_id/缺证据腿/失败信封/微探针超限/金轨迹混轮 均门败", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "gdeep-unit-"));
  fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, bundles: [{ hid: "https://x/f.txt", budget_cny: 0.016 }] }));
  const seed = { type: "registry_seed", call_id: "c9", tool: "reprobe_get", sc: { ok: true, age_days: 220 } };
  const writeVerdicts = (ev, extra = {}) => fs.writeFileSync(path.join(d, "05-deep-verdicts.json"),
    JSON.stringify({ verdicts: [{ hid: "https://x/f.txt", verdict: "confirmed", evidence: ev, one_line: "u" }], degraded: [], golden_track: [], ...extra }));
  const writeTranscript = (lines) => fs.writeFileSync(path.join(d, "05-deep-x-f-txt-transcript.jsonl"), lines.map((l) => JSON.stringify(l)).join("\n") + "\n");
  writeTranscript([seed]);
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 220 }]);
  assert.equal(GATES.G_DEEP({ dir: d }).pass, true, "宿主回填三元组逐字回引=过");
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 999 }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /回引不符/, "复述漂移(伪造值)=门败(A 一律结构性消灭)");
  writeVerdicts([{ call_id: "c9", field: "age_days" }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /三元组缺值/, "宿主回填缺席/字段不在返回=门败");
  writeVerdicts([{ call_id: "c404", field: "age_days", value: 220 }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /未知 call_id/);
  writeVerdicts([]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /无证据腿/, "confirmed 必带 evidence");
  // 失败信封禁入 evidence:ok:false 是测量故障非读数,引用即门败(shared/envelope.md 纪律)
  writeTranscript([{ type: "registry_seed", call_id: "cf", tool: "reprobe_get", sc: { ok: false, code: "net_fail", reason: "canned" } }, seed]);
  writeVerdicts([{ call_id: "cf", field: "code", value: "net_fail" }]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /失败信封禁入 evidence/);
  // 微探针 ≤3/假设(deep.md 预算段机检面):4 seed 行=门败
  writeTranscript([0, 1, 2, 3].map((i) => ({ type: "registry_seed", call_id: `c${i}`, tool: "reprobe_get", sc: { ok: true, i } })));
  writeVerdicts([]);
  assert.match(GATES.G_DEEP({ dir: d }).reason, /微探针超 3/, "探针预算段超限=门败");
  // 金轨迹与真假设同轮(#165 落单向门,本例补不混轮负例):need>0 且 golden_track>0=门败
  writeTranscript([seed]);
  writeVerdicts([{ call_id: "c9", field: "age_days", value: 220 }], { golden_track: [{ hid: "golden-track-canned", verdict: "unresolved", evidence: [], one_line: "g" }] });
  assert.match(GATES.G_DEEP({ dir: d }).reason, /金轨迹与真假设同轮/);
  fs.rmSync(d, { recursive: true, force: true });
});

await t("DISPATCH 上限截尾单元例(#166):4 need_deep→bundles 3+truncated 1(unresolved(dispatch_cap));0.02¥ 再截 2(unresolved(budget))", async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "dispatch-unit-"));
  const mkHyp = (id, sev) => ({ signal_id: id, cause_class: "frozen_feed", hypothesis: "若 X 则 Y", need_deep: true, probe_hint: "reprobe_get", severity: sev, one_line: "行" });
  fs.writeFileSync(path.join(d, "03-triage-hypotheses.json"), JSON.stringify({ hypotheses: [mkHyp("h-high", "high"), mkHyp("h-med", "medium"), mkHyp("h-low1", "low"), mkHyp("h-low2", "low")] }));
  fs.writeFileSync(path.join(d, "02-verify-survivors.json"), JSON.stringify({ survivors: [] })); // 锚选零命中面(旗标缺席=零注入,宁少算)
  await steps.runStage({ name: "DISPATCH" }, { dir: d, budgetCny: 0.05, env: process.env });
  let b = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(b.bundles.length, 3, "上限 3(#166:severity 排序保 high/medium/low1)");
  assert.deepEqual(b.truncated, [{ hid: "h-low2", severity: "low", reason: "unresolved(dispatch_cap)" }], "截尾留痕");
  assert.equal(b.degraded, true);
  await steps.runStage({ name: "DISPATCH" }, { dir: d, budgetCny: 0.02, env: process.env });
  b = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(b.bundles.length, 1, "0.02¥ 只容 1 假设(0.016×1≤0.02<0.032)");
  assert.equal(b.truncated.length, 3);
  assert.equal(b.truncated[0].reason, "unresolved(dispatch_cap)", "第 4 条归因上限");
  assert.ok(b.truncated.slice(1).every((t) => t.reason === "unresolved(budget)"), "其余归因预算门");
  assert.match(b.bundles[0].hid, /h-high/, "高 severity 幸存");
  fs.rmSync(d, { recursive: true, force: true });
});

// ── P2 #164 新例:①规则库判例转写真命中(R12 形/R7 形,直调 VERIFY)②在飞真读 + R7 annotate 全链 ──
// ③规则库闭集负例 ④matrix 裸失败负例(#163 review P2-1 顺手件)
await t("规则命中(R12/R7 判例转写形,直调 VERIFY):404 重定向形 suppress+429 annotate 传幸存+review_at 缺省采纳+90天", async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "verify-unit-"));
  const rulesFile = path.join(d, "rules.json");
  // 首批规则同形(docs 仓 docs/ops/rules/suppressions.json;R12 缺 review_at 验缺省,R7 带显式)
  fs.writeFileSync(rulesFile, JSON.stringify({ version: 1, rules: [
    { id: "R12", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-bbe1ad6f0c.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", url_shape: "https://github.com/*/releases/latest/download/", error_family: "http_404" },
      action: "suppress", note: "GitHub releases/latest/download 截断重定向形:HEAD 恒 404 而 GET 实活(GeoLite 假红,2026-10-23 判例)" },
    { id: "R7", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", error_family: "http_429" },
      action: "annotate", note: "限流:降 severity 不抑制", review_at: "2027-01-21" } ] }, null, 2));
  const itemsDir = path.join(d, "items");
  fs.mkdirSync(itemsDir);
  fs.writeFileSync(path.join(d, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: "unit", urls_n: 3, attempted_n: 3,
    buckets: { fresh: 0, frozen: 1, unreachable: 2, token_required: 0, no_lm: 0 },
    flags: [
      { signal_id: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", bucket: "unreachable", source: "geolite_city", error_family: "http_404" },
      { signal_id: "https://raw.githubusercontent.com/duggytuxy/Data-Shield_IPv4_Blocklist/main/prod.txt", url: "https://raw.githubusercontent.com/duggytuxy/Data-Shield_IPv4_Blocklist/main/prod.txt", bucket: "unreachable", source: "data_shield", error_family: "http_429" },
      { signal_id: "https://feeds.dshield.org/block.txt", url: "https://feeds.dshield.org/block.txt", bucket: "frozen", source: "dshield", age_days: 200 } ] }));
  await steps.runStage({ name: "VERIFY" }, { dir: d, rulesFile, itemsDir, roundId: "unit" });
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "R12", "截断重定向 404 形被 R12 压(零 token 花费,C稿 §2.4-2)");
  assert.equal(sp.suppressed[0].error_family, "http_404");
  assert.equal(sv.survivors.length, 2);
  const rl = sv.survivors.find((x) => x.source === "data_shield");
  assert.equal(rl.annotated_rule, "R7", "429 限流形 annotate 传递幸存(降 severity 不抑制)");
  const r12 = sv.known_noise_digest.find((r) => r.id === "R12");
  assert.equal(r12.review_at, "2027-01-21", "review_at 缺省=采纳+90 天(2026-10-23+90)");
  assert.equal(sv.known_noise_digest.find((r) => r.id === "R7").review_at, "2027-01-21");
  // 反面:全 URL 形(带文件名)不落入 R12 截断形——真 404 仍幸存交人
  fs.writeFileSync(path.join(d, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: "unit2", urls_n: 1, attempted_n: 1,
    buckets: { fresh: 0, frozen: 0, unreachable: 1, token_required: 0, no_lm: 0 },
    flags: [{ signal_id: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb", url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb", bucket: "unreachable", source: "geolite_city", error_family: "http_404" }] }));
  await steps.runStage({ name: "VERIFY" }, { dir: d, rulesFile, itemsDir, roundId: "unit2" });
  assert.equal(j(path.join(d, "02-verify-survivors.json")).survivors.length, 1, "全资产 URL 404=真信号,不入 R12 截断形");
  assert.equal(j(path.join(d, "02-verify-suppressed.json")).suppressed.length, 0);
  fs.rmSync(d, { recursive: true, force: true });
});

await t("规则库闭集负例:谓词闭集外/动作闭集外/review_at 异形/id 重复/坏 JSON 均以 infra 拒(规则文件坏=终态面)", async () => {
  const base = { id: "RX", adopted: "2026-10-23", adopted_via: "判例 fixture", match: { bucket: "frozen" }, action: "suppress", note: "n" };
  const bad = (r) => assert.throws(() => steps.normalizeRules(r), (e) => e.code === "infra");
  bad({ version: 1, rules: [{ ...base, match: { path: "/x" } }] }, "谓词闭集外");
  bad({ version: 1, rules: [{ ...base, action: "delete" }] }, "动作闭集外");
  bad({ version: 1, rules: [{ ...base, review_at: "2027/01/21" }] }, "review_at 形状");
  bad({ version: 1, rules: [{ ...base, match: {} }] }, "match 空");
  bad({ version: 1, rules: [{ ...base }, { ...base }] }, "id 重复");
  bad(null, "非对象");
  assert.doesNotThrow(() => steps.normalizeRules({ version: 1, rules: [{ ...base }] }), "合规形过");
});

await t("在飞全签不双开+终态重开全链(CLI 轮):bruteforce 同签在飞压制;ciarm 同签终态→重开链指;R7 annotate 幸存", async () => {
  const DOCS2 = mkTree("docs2"); // 独立树:规则只留 R7(429 annotate)
  fs.writeFileSync(path.join(DOCS2.root, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
    { id: "R7", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", error_family: "http_429" },
      action: "annotate", note: "限流:降 severity 不抑制", review_at: "2027-01-21" } ] }, null, 2) + "\n");
  // 真形 _ops_items 预置件(Python safe_dump 裸串形,桥解析兼容面):bruteforce 在飞同签(危险页 404 旗标应压制);
  // ciarm 同签终态 done(冻结旗标应重开链指,非就地复活)
  fs.mkdirSync(path.join(DOCS2.root, "ops", "items"), { recursive: true });
  fs.writeFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-aaaa000001.md"), `---
id: 2026-10-20-item-aaaa000001
action: retry_download
args:
  source: bruteforce
evidence:
  consecutive_failures: 2
impact: bruteforce 数据停更,威胁覆盖面收缩
rollback: 重新触发下载即可恢复
dedup_key:
  source: bruteforce
  probe_class: download
  error_signature: http_4xx
severity: medium
cause_group: download_failure
status: active
---

selftest fixture(在飞:同签 download/http_4xx 不双开)。
`);
  fs.writeFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-bbbb000002.md"), `---
id: 2026-10-20-item-bbbb000002
action: refresh_source
args:
  source: ciarm
evidence:
  content_age_h: 5280
impact: ciarm 内容超龄
rollback: 刷新成功即自愈
dedup_key:
  source: ciarm
  probe_class: staleness
  error_signature: age_gt_2x_refresh
severity: medium
cause_group: staleness
status: done
---

selftest fixture(终态 done:同签冻结旗标=复开新条目链指,原条目永不删)。
`);
  // curl 替身:cinsscore 冻结 220;binarydefense 429(R7 annotate);danger.rulez.sk 404(不可达→bruteforce 同签在飞压制);其余新鲜
  const STUBS2 = path.join(TMP, "stubs2");
  fs.mkdirSync(STUBS2, { recursive: true });
  fs.writeFileSync(path.join(STUBS2, "curl"), `#!/usr/bin/env bash
url="\${@: -1}"
case "$url" in
  *cinsscore*) printf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - 220 * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"; exit 0 ;;
  *binarydefense*) printf 'HTTP/1.1 429 Too Many Requests\\r\n\\r\n'; exit 0 ;;
  *danger.rulez.sk*) printf 'HTTP/1.1 404 Not Found\\r\n\\r\n'; exit 0 ;;
esac
printf 'HTTP/1.1 200 OK\\r\nLast-Modified: %s\\r\nContent-Length: 4\\r\n\\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - 30 * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"
exit 0
`);
  fs.chmodSync(path.join(STUBS2, "curl"), 0o755);
  // 计数链定制 synth:ciarm 重开(created=1 reopened=1)+ binarydefense 新建;深验 confirmed=1 refuted=1
  const fx = cloneFixtures("fixtures-casea");
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:冻结深验 confirmed(重开条目,前条已人裁)· 建议 human_ruling\n- binarydefense:429 限流形 R7 annotate,深验 refuted · 建议 digest_ignore\n\n抑制 1 条(in_flight×1——明细见工件)。\n\n## 摘要\n- 计数: created=1 reopened=1 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=1 unresolved=0");
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0100-health", "--fixtures", fx],
    { ...DOCS2.env, PATH: `${STUBS2}:${process.env.PATH}` });
  assert.equal(r.rc, 0, `rc=${r.rc} stdout=${JSON.stringify((r.stdout||'').slice(-400))} stderr=${JSON.stringify((r.stderr||'').slice(-200))}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  const d = path.join(DOCS2.root, "ops", "rounds", "2026-10-24-0100-health");
  const s2 = j(path.join(d, "01-probe-summary.json"));
  assert.equal(s2.buckets.unreachable, 2, "binarydefense 429 + danger.rulez.sk 404");
  assert.equal(s2.buckets.frozen, 1);
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sv.survivors.length, 2, "ciarm(终态不算在飞)+binarydefense(R7 annotate)");
  assert.equal(sv.survivors.find((x) => x.source === "binarydefense").annotated_rule, "R7");
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "in_flight");
  assert.equal(sp.suppressed[0].dedup_key, "bruteforce|download|http_4xx", "全签同因(源级→P4 全签,#164 偏离②收口)");
  assert.deepEqual(sp.suppressed[0].in_flight_items, ["2026-10-20-item-aaaa000001"], "溯源到真条目 id");
  const g = j(path.join(d, "gates.json"));
  assert.ok(g.records.every((x) => x.pass), "门全绿(G_VERIFY 真在飞面全签重算)");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [1, 1, 0, 1], "ciarm 重开+binarydefense 新建");
  const ciarmRow = m.rows.find((x) => x.source === "ciarm");
  assert.equal(ciarmRow.outcome, "reopened");
  assert.equal(ciarmRow.supersedes, "2026-10-20-item-bbbb000002", "复开链指最近旧条");
  const newFile = fs.readFileSync(path.join(DOCS2.root, "ops", "items", `${ciarmRow.item_id}.md`), "utf8");
  assert.match(newFile, /supersedes: "?2026-10-20-item-bbbb000002"?/, "链指字段在树面");
  assert.match(newFile, /status: "?active"?/, "复开新条 active");
  const oldFile = fs.readFileSync(path.join(DOCS2.root, "ops", "items", "2026-10-20-item-bbbb000002.md"), "utf8");
  assert.match(oldFile, /status: "?done"?/, "原条目永不改写(证据不灭失)");
  const bdRow = m.rows.find((x) => x.source === "binarydefense");
  assert.deepEqual(bdRow.dedup_key, { source: "binarydefense", probe_class: "download", error_signature: "http_4xx" }, "429→折叠族 http_4xx(#164 偏离①映射)");
});

await t("matrix 裸失败负例(#163 review P2-1):信封件落 01-probe-matrix.json,summary.matrix.ok=false,轮仍 ok=true 不阻轮", async () => {
  const STUBS3 = path.join(TMP, "stubs3");
  fs.mkdirSync(STUBS3);
  fs.writeFileSync(path.join(STUBS3, "py-matrix-fail"), `#!/usr/bin/env bash\necho 'boom: matrix stub bare failure' >&2\nexit 1\n`);
  fs.chmodSync(path.join(STUBS3, "py-matrix-fail"), 0o755);
  const t0101 = mkTree("tree-0101");
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0101-health"], { ...t0101.env, OPS_EVAL_PY: path.join(STUBS3, "py-matrix-fail") });
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-400)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true, "matrix 失败=嵌套信封不阻轮(C稿 §2.2;证据不灭失落件)");
  const d = path.join(t0101.root, "ops", "rounds", "2026-10-24-0101-health");
  const mfile = j(path.join(d, "01-probe-matrix.json"));
  assert.equal(mfile.ok, false, "工件=失败信封件非读数");
  assert.equal(mfile.code, "matrix_failed");
  assert.match(mfile.reason, /boom/);
  const s = j(path.join(d, "01-probe-summary.json"));
  assert.equal(s.matrix.ok, false);
  assert.equal(s.matrix.exit_code, null);
  assert.equal(s.matrix.violation_n, null);
  const g = j(path.join(d, "gates.json"));
  assert.equal(g.records.length, 9);
  assert.ok(g.records.every((x) => x.pass), "门不受 matrix 裸失败牵连(legacy 失败只回嵌套信封,不阻轮语义两侧一致)");
});

await t("A 一律违例负例(全 faux 轮):深验 fixture 复述伪造值 999 → G_DEEP 回引不符 → model_face 终态工件保留", async () => {
  const fx = cloneFixtures("fixtures-arule");
  const bad = JSON.parse(fs.readFileSync(path.join(fx, "deep", "https-cinsscore.com-list-ci-badguys.txt.json"), "utf8"));
  bad.turns[0].content[0].text = bad.turns[0].content[0].text.replace('"evidence":[{"call_id":"c-cins","field":"age_days"}]',
    '"evidence":[{"call_id":"c-cins","field":"age_days","value":999}]'); // 模型复述伪造值(违 A 一律)
  fs.writeFileSync(path.join(fx, "deep", "https-cinsscore.com-list-ci-badguys.txt.json"), JSON.stringify(bad, null, 1));
  const tree = mkTree("tree-arule");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0105-health", fixturesDir: fx, env: tree.env, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "model_face", "写前语义门败→DEEP 缺省终态码(九词闭集)");
  const d = path.join(tree.root, "ops", "rounds", "2026-10-24-0105-health");
  const g = j(path.join(d, "gates.json"));
  assert.match(g.records.find((x) => x.name === "G_DEEP").reason, /回引不符/, "门 reason 可回算");
  const cFile = j(path.join(d, "05-deep-https-cinsscore.com-list-ci-badguys.txt.json"));
  assert.equal(cFile.evidence[0].value, 999, "伪造值原样透传留痕(宿主不静默纠正,交门裁决)");
  assert.equal(j(path.join(d, "state.json")).status, "failed");
  assert.ok(!fs.existsSync(path.join(d, "06-itemize-manifest.json")), "门败即止:坏证据不得成条(无证据即无话)");
});

await t("DEEP perItem 降级直测(#165 审 P2 遗留):坏 fixture 重试尽→degraded unresolved 折入 ITEMIZE→G_DEEP/G_SYNTH 回算一致", async () => {
  const fx = cloneFixtures("fixtures-degrade");
  fs.writeFileSync(path.join(fx, "deep", "https-www.binarydefense.com-banlist.txt.json"),
    JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: "不是 JSON(model_face 负例)" }], stopReason: "stop" }] }));
  writeSynthFx(fx, "## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- ciarm:深验 confirmed · 建议 human_ruling\n- binarydefense:重试尽降级 unresolved · 建议 human_ruling\n\n抑制 1 条(规则 R1×1)。\n\n## 摘要\n- 计数: created=2 reopened=0 deduped=0 suppressed=1\n- 深验: confirmed=1 refuted=0 unresolved=1(1 条重试尽降级)");
  const tree = mkTree("tree-degrade");
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-24-0106-health", fixturesDir: fx, env: tree.env, ...io });
  assert.equal(r.ok, true, "单假设降级不终态(证据不灭失)");
  const deep = stageOf(r.envelope, "DEEP");
  assert.equal(deep.status, "degraded", "DEEP stages 标降级");
  assert.equal(deep.attempts, 3, "cinsscore 1 发 + binarydefense 重试 2 发");
  const d = path.join(tree.root, "ops", "rounds", "2026-10-24-0106-health");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 1);
  assert.equal(v.degraded.length, 1);
  assert.match(v.degraded[0].one_line, /重试尽降级 unresolved/);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.equal(m.created, 2, "降级行折入条目(human_ruling 交人)");
  const bdRow = m.rows.find((x) => /binarydefense/.test(x.hid));
  assert.equal(bdRow.verdict, "unresolved");
  assert.equal(bdRow.suggested_action, "human_ruling");
  const g = j(path.join(d, "gates.json"));
  assert.ok(g.records.every((x) => x.pass), "G_DEEP 穷尽(verdicts∪degraded)与 G_SYNTH 回算(confirmed=1 unresolved=1)一致全绿");
});

// ── B 三件装配层(并 #164):_INDEX 生成器/锚域词表/升格检测器 — 单元面(快,不跑整轮)──
await t("B① _INDEX 召回地板:概念判例一行一件、留痕/下划线件排除、再生字节一致、尾部档案汇总", async () => {
  const { buildIndexText, parsePrecedentFm } = await import("./build-index.mjs");
  const pdir = path.join(TMP, "prec-b");
  fs.mkdirSync(pdir, { recursive: true });
  const mk = (name, subject, ctx = "") => fs.writeFileSync(path.join(pdir, name),
    `---\nid: ${name.replace(/\.md$/, "")}\ndate: 2026-10-24\nsubject: ${subject}\ncontext: >\n  ${ctx}\nsuperseded_by: null\n---\n\n正文。\n`);
  mk("2026-10-01-alpha-sunset.md", "源候选判死 — sunset 硬门(URL Last-Modified 冻结)", "threatview.io 冻结 240 天");
  mk("2026-10-02-beta-aggregator.md", "聚合器误判 — 实测排他率立证 ziyadnz");
  fs.writeFileSync(path.join(pdir, "2026-10-24-ruling-deadbeef.md"), "---\nid: r\nsuperseded_by: null\n---\n留痕\n");
  fs.writeFileSync(path.join(pdir, "_schema.md"), "schema\n");
  const files = fs.readdirSync(pdir).filter((f) => f.endsWith(".md") && !f.startsWith("_")).sort()
    .map((name) => ({ name, fm: parsePrecedentFm(fs.readFileSync(path.join(pdir, name), "utf8")) }));
  const concepts = files.filter((f) => !/[\d-]+-ruling-/.test(f.name));
  const text = buildIndexText(concepts);
  assert.equal(concepts.length, 2, "ruling 不进索引(留痕非记忆面)");
  assert.match(text, /2026-10-01-alpha-sunset\.md \| 源候选判死 \|/);
  assert.match(text, /2026-10-02-beta-aggregator\.md.*ziyadnz/);
  assert.doesNotMatch(text, /ruling-deadbeef|_schema/);
  assert.match(text, /superseded: 0 条/);
  assert.equal(buildIndexText(concepts), text, "同库再生字节一致(派生缓存)");
});

await t("B② 锚域词表:闭包校验拒缺件锚;选锚纯函数(域词×旗标命中/空旗标零注入/HIT_CAP)", async () => {
  const anchors = await import("./pipeline/anchors.mjs");
  const { validateAnchors } = await import("./build-index.mjs");
  const loaded = anchors.loadAnchors(path.join(AGENT, "anchors-health.json"));
  assert.ok(loaded.anchors.length >= 5, `锚域 ≥5(${loaded.anchors.length})`);
  const real = ["2026-10-23-ruling-bbe1ad6f0c.md", "2026-10-19-threatview-sunset-dead-feed.md"];
  assert.throws(() => validateAnchors(loaded, real), /锚指向缺件/, "闭包:锚指不在库中的判例 = 编造路径,拒");
  const flags = [{ url: "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/", source: "geolite_city", bucket: "unreachable", error_family: "http_404" },
    { url: "https://x/f.txt", source: "dshield", bucket: "frozen" }];
  const picked = anchors.anchorSelect(loaded.anchors, flags);
  assert.ok(picked.includes("2026-10-23-ruling-bbe1ad6f0c.md"), "GitHub 重定向 404 旗标选 GeoLite 判例锚");
  assert.equal(anchors.anchorSelect(loaded.anchors, []).length, 0, "空旗标零注入(宁少算)");
  assert.equal(anchors.anchorSelect(loaded.anchors, flags).length <= anchors.HIT_CAP, true, "铁律⑦ HIT_CAP");
});

await t("B③ 升格检测器:同源留痕≥2 且一致→候选(三门槛 pending);不一致/superseded/单条不立项;候选件幂等", async () => {
  const pd = await import("./promote-detect.mjs");
  const mk = (name, rec, agr, sup = null) => ({ name, recommendation: rec, ruling_agreement: agr, superseded_by: sup });
  const r = [
    mk("r1.md", "retry_download — urlhaus 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-aaa)", "agreed"),
    mk("r2.md", "不可达·建议复核: https://urlhaus.abuse.ch/downloads/csv_online/", "agreed"),
    mk("r3.md", "retry_download — threatfox 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-bbb)", "amended"),
    mk("r4.md", "retry_download — threatfox 数据停更,威胁覆盖面收缩(待审条目 2026-10-23-item-ccc);忽略理由:410 已确诊", "overruled"),
    mk("r5.md", "同文但已被取代(留痕不计数)", "agreed", "r6.md"),
  ];
  const cands = pd.detectCandidates(r);
  assert.equal(cands.length, 1, "urlhaus 同源一致成组;threatfox 裁决不一致不立项;superseded 不计数");
  assert.equal(cands[0].cause_key, "同源:urlhaus");
  assert.deepEqual(cands[0].rulings, ["r1.md", "r2.md"]);
  const text = pd.candidateText(cands[0], "2026-10-24T00:00:00Z");
  const obj = JSON.parse(text);
  assert.equal(obj.status, "proposed");
  assert.deepEqual(obj.gates.map((g) => g.id), ["machine_checkable", "falsifiable", "non_env_specific"]);
  assert.ok(obj.gates.every((g) => g.verdict === "pending"), "三门槛 pending 起步,人裁逐项核");
});

await t("位等价门(#163):同 stub 下 legacy health 轮工件 = 管线 PROBE 工件,逐字节 diff 空+计数两口径对拍", async () => {
  // 腿一(legacy)= agent.mjs runRound 真 Agent 循环(golden health 例同型):faux 模型点
  // health_snapshot → lib.sh feed_freshness + tools.mjs runMatrixScan 真路径,产出 ts-slug 工件;
  // 腿二(管线)= pipeline.mjs PROBE(同 lib.sh 同 matrixScanCli 单源)。两腿同 curl/OPS_EVAL_PY stub,
  // 同清单(ops/agent/feeds.txt 101 URL 固定 fixture),先后背靠背跑(同 UTC 日,curl stub 日界截断)。
  const { runRound } = await import("./agent.mjs");
  const { fauxProvider, fauxAssistantMessage, fauxToolCall, fauxText, createModels } = await import("@earendil-works/pi-ai");
  const faux = fauxProvider({ models: [{ id: "faux-eq" }] });
  const models = createModels();
  models.setProvider(faux.provider);
  faux.setResponses([
    fauxAssistantMessage([fauxToolCall("health_snapshot", {}, { id: "call_eq1" })], { stopReason: "toolUse" }),
    fauxAssistantMessage([fauxText("## 注入判例\n- 2026-06-01-golden-aggregator.md\n\n## 异常清单\n- 位等价 fixture 轮:冻结读数 3 条(cinsscore/binarydefense/dshield),其余新鲜;全量逐行读数见工件 TSV。\n\n## 摘要\n位等价门例:本腿(legacy agent.mjs health)工件即管线 PROBE 工件的字节基线;计数与矩阵读数两腿一致。")]),
  ]);
  const legacy = await runRound("health", "位等价门:legacy 腿 health 轮(全量读数落工件)。", [],
    { models: { models, resolve: () => faux.getModel() }, registrySeed: [] });
  const sc = legacy.registry.find((r) => r.tool === "health_snapshot").sc;
  assert.equal(sc.ok, true, `legacy health_snapshot 信封:${sc.code}`);
  const legacyTsv = sc.artifacts.find((a) => a.endsWith("health-freshness.tsv"));
  const legacyMatrix = sc.artifacts.find((a) => a.endsWith("matrix-scan.json"));
  assert.ok(legacyTsv && legacyMatrix, `legacy 工件缺:${sc.artifacts.join(",")}`);
  const io = mkIo();
  const pipe = await runPipeline({ roundId: "2026-10-23-2344-health", env: mkTree("tree-2344").env, ...io });
  assert.equal(pipe.ok, true);
  const d = path.join(mkTree("tree-2344").root, "ops", "rounds", "2026-10-23-2344-health");
  const tsvA = fs.readFileSync(legacyTsv), tsvB = fs.readFileSync(path.join(d, "01-probe-freshness.tsv"));
  assert.ok(Buffer.compare(tsvA, tsvB) === 0, `TSV 位等价破口:legacy ${tsvA.length}B vs 管线 ${tsvB.length}B`);
  const mA = fs.readFileSync(legacyMatrix), mB = fs.readFileSync(path.join(d, "01-probe-matrix.json"));
  assert.ok(Buffer.compare(mA, mB) === 0, `matrix 位等价破口:legacy ${mA.length}B vs 管线 ${mB.length}B`);
  // 清单事实层钉住:101 URL 固定 fixture(清单变更须同步本例,feedfix #168 基线)
  const manifestN = +(await execFileP("bash", ["-c", `. "${path.join(AGENT, "lib.sh")}"; extract_feed_urls | wc -l`])).stdout.trim();
  assert.equal(manifestN, 101, `feeds.txt 清单 URL 数=${manifestN}(固定 fixture,变更须同步本例)`);
  const summary = j(path.join(d, "01-probe-summary.json"));
  assert.equal(summary.urls_n, manifestN);
  assert.equal(tsvB.toString().trimEnd().split("\n").length, manifestN, "TSV 行数=清单 URL 数");
  // 计数两口径对拍:legacy sc(frozen/near/unreachable/no_lm/token_required)↔ 管线 buckets+matrix
  assert.deepEqual(
    { urls_n: sc.urls_n, frozen: sc.frozen_n, unreachable: sc.unreachable_n, no_lm: sc.no_lm_n, token_required: sc.token_required_n },
    { urls_n: summary.urls_n, frozen: summary.buckets.frozen, unreachable: summary.buckets.unreachable,
      no_lm: summary.buckets.no_lm, token_required: summary.buckets.token_required });
  assert.equal(sc.matrix_ok, summary.matrix.ok);
  assert.equal(sc.matrix_exit_code, summary.matrix.exit_code);
  assert.equal(summary.matrix.exit_code, 0);
});

await t("replay --dry 全程可跑(CLI 子进程):门全重算 PASS,产物写 -r1/,原件逐字不变", async () => {
  const before = treeMd5(roundDir(R1));
  const r = await spawnPipe(["replay", R1, "--dry"]);
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-300)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  assert.equal(env.pipeline.replayed_of, R1);
  assert.equal(env.pipeline.round_id, `${R1}-r1`);
  assert.equal(env.pipeline.stages.length, 8, "dry 段=PROBE..RETRO(CLOSE 不入重放)");
  assert.ok(env.pipeline.stages.every((s) => s.status === "dry"), "dry 状态词");
  const g = j(path.join(roundDir(`${R1}-r1`), "gates.json"));
  assert.equal(g.records.length, 8);
  assert.ok(g.records.every((x) => x.pass), "原件工件上全门重算 PASS(自愈:以工件+门为准)");
  assert.equal(treeMd5(roundDir(R1)), before, "原件零改写");
});

await t("replay 段重放(VERIFY..SYNTH,非 dry):前置工件复制+段内再生,原件不变", async () => {
  const before = treeMd5(roundDir(R1));
  const r = await spawnPipe(["replay", R1, "--from", "VERIFY", "--to", "SYNTH"]);
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-300)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  assert.deepEqual(env.pipeline.stages.map((s) => s.name), ["VERIFY", "TRIAGE", "DISPATCH", "DEEP", "ITEMIZE", "SYNTH"]);
  const d = roundDir(`${R1}-r2`);
  assert.ok(fs.existsSync(path.join(d, "01-probe-summary.json")), "前置工件(PROBE 01-*)复制");
  assert.ok(fs.existsSync(path.join(d, "07-synth-report.md")) && fs.existsSync(path.join(d, "06-itemize-manifest.json")), "段内产物再生(P4:manifest=条目面工件)");
  const itemsAfter = fs.readdirSync(path.join(DOCS, "ops", "items")).filter((f) => f.endsWith(".md")).length;
  assert.equal(itemsAfter, 2, "replay 回声零写:生产条目树不增项(审计重放不改条目面)");
  const rm2 = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([rm2.created, rm2.reopened, rm2.deduped], [2, 0, 0], "manifest 回声原轮 outcome");
  assert.ok(rm2.rows.every((x) => x.echo === true), "行级 echo 标记");
  assert.ok(fs.existsSync(path.join(d, "gates.json")));
  assert.equal(treeMd5(roundDir(R1)), before, "原件零改写");
});

await t("CLI 契约:用法错/坏 OPS_PIPELINE/replay 不存在轮/--to CLOSE 均 exit 2 纯 stderr 不发 JSON", async () => {
  const noArgs = await spawnPipe([]);
  assert.equal(noArgs.rc, 2);
  assert.equal(noArgs.stdout, "");
  assert.match(noArgs.stderr, /用法:/);
  const badMode = await spawnPipe(["health"], { OPS_PIPELINE: "bogus" });
  assert.equal(badMode.rc, 2);
  assert.match(badMode.stderr, /OPS_PIPELINE 须 legacy\|pipeline/);
  const noRound = await spawnPipe(["replay", "2020-01-01-0000-health", "--dry"]);
  assert.equal(noRound.rc, 2);
  assert.match(noRound.stderr, /无 state\.json/);
  const toClose = await spawnPipe(["replay", R1, "--to", "CLOSE", "--dry"]);
  assert.equal(toClose.rc, 2);
  assert.match(toClose.stderr, /CLOSE 属原轮时序不入重放/);
});

await t("同 id 重跑拒绝(bad_round 信封)——轮次目录不覆盖(证据不灭失)", async () => {
  const io = mkIo();
  const r = await runPipeline({ roundId: R1, ...io });
  assert.equal(r.ok, false);
  assert.equal(r.envelope.error.code, "bad_round");
});

// 审后修 P1 负例:注入块展示面=闭合集(anchored≥2 且 anchored∪hits>8 时,块外命中行必须滤除)
await t("SYNTH 注入块=闭合集(命中 10/锚 2:块内仅 ∈injected 的 6 命中+锚补行,块外行必滤)", async () => {
  const { synthInjectionBlock } = await import(path.join(AGENT, "pipeline", "steps.mjs"));
  const hits = Array.from({ length: 10 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}-hit-${i}.md`);
  const anchored = ["2026-02-01-anch-a.md", "2026-02-02-anch-b.md"];
  const injected = [...anchored, ...hits].slice(0, 8); // 锚选在前恒⊆injected
  const stdout = hits.map((n) => `- ${n}`).join("\n");
  const extra = anchored.map((n) => `- ${n}\n  - 锚域 test: gist`);
  const block = synthInjectionBlock(stdout, extra, hits, injected);
  for (const n of hits.slice(6)) assert.ok(!block.includes(n), `块外命中行必须滤除(旧实现整块直出=审 P1): ${n}`);
  for (const n of hits.slice(0, 6)) assert.ok(block.includes(n), `∈injected 命中保留: ${n}`);
  for (const n of anchored) assert.ok(block.includes(n), "锚补行恒保留(锚选⊆injected)");
});

// 审后补 P2:装载对拍持久化(transcript system_sha === 提示词文件 sha;文件缺失/装载漂移即红,取代一次性手验)
await t("模型步装载对拍:TRIAGE/SYNTH transcript system_sha=提示词文件 sha 逐字", async () => {
  const { createHash } = await import("node:crypto");
  const sha = (s) => createHash("sha256").update(s).digest("hex").slice(0, 16);
  const deepTf = fs.readdirSync(run1.dir).find((f) => /^05-deep-.*-transcript\.jsonl$/.test(f));
  for (const [tf, pf] of [["03-triage-transcript.jsonl", "triage"], [deepTf, "deep"], ["07-synth-transcript.jsonl", "synth"]]) {
    const head = fs.readFileSync(path.join(run1.dir, tf), "utf8").split("\n")[0];
    const rec = JSON.parse(head);
    assert.equal(rec.type, "input");
    assert.equal(rec.system_sha, sha(fs.readFileSync(path.join(AGENT, "prompts", "health", `${pf}.md`), "utf8")), `${pf} 装载漂移`);
  }
});

await t("DISPATCH 3-bundle 稳态预算回归(审 P1-1):floor 拆分合计≤轮预算过门;toFixed 形必红", async () => {
  const { GATES } = await import("./pipeline/gates.mjs");
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "p4-gdispatch-"));
  const mk = (per) => {
    fs.writeFileSync(path.join(d, "03-triage-hypotheses.json"), JSON.stringify({ hypotheses: [1, 2, 3].map((i) => ({ signal_id: `https://x/${i}.txt`, need_deep: true, severity: "high", cause_class: "unknown", hypothesis: `h${i}`, probe_hint: "reprobe_get", one_line: `l${i}` })), digest: "d" }));
    fs.writeFileSync(path.join(d, "04-dispatch-bundles.json"), JSON.stringify({ budget_cny: 0.05, bundles: [1, 2, 3].map((i) => ({ hid: `https://x/${i}.txt`, budget_cny: per })), truncated: [] }));
  };
  mk(0.0166); // floor(0.05/3×1e4)/1e4
  assert.equal(GATES.G_DISPATCH({ dir: d, budgetCny: 0.05 }).pass, true, "floor 拆分合计 0.0498≤0.05 必过");
  mk(0.0167); // 旧 toFixed 四舍五入形
  assert.match(GATES.G_DISPATCH({ dir: d, budgetCny: 0.05 }).reason, /预算合计/, "toFixed 形合计 0.0501>0.05 必红(原 P1-1 缺陷钉死)");
  fs.rmSync(d, { recursive: true, force: true });
});

// 审后修 P1-2:跨语言镜像钉子——ops-items digest 与 _ops_items.py 语义对拍(backend/.venv Python 预计算金常量;
// pyJson 仅对扁平 {source:str}/空 args 与 Python json.dumps(sort_keys,ensure_ascii=False) 字节同——嵌套/浮点即分叉,
// 现调用面恒扁平(steps.mjs dispatch);Python 侧改拼接收=本断言红,防两语言镜像静默回声)。
await t("条目摘要镜像钉:ops-items digest=Python 侧金常量(flat a052743a5d/empty 1772523325)", async () => {
  const { mirrorDigestForTest } = await import("./pipeline/ops-items.mjs");
  assert.equal(mirrorDigestForTest({ source: "ciarm", probe_class: "staleness", error_signature: "age_gt_2x_refresh", action: "human_ruling", args: { source: "ciarm" }, latest: "" }), "a052743a5d");
  assert.equal(mirrorDigestForTest({ source: "dshield", probe_class: "unreachable", error_signature: "net_fail", action: "human_ruling", args: {}, latest: "" }), "1772523325");
});

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`pipeline-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
