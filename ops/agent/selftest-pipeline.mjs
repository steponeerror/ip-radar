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
fs.writeFileSync(path.join(STUBS, "curl"), `#!/usr/bin/env bash\n# selftest stub:curl 传输层替身(golden stubCurl 同型);三冻结锚点+其余新鲜\nurl="\${@: -1}"\nd=30\ncase "$url" in\n  *cinsscore*) d=220 ;;\n  *binarydefense*) d=210 ;;\n  *dshield*) d=200 ;;\nesac\nprintf 'HTTP/1.1 200 OK\\r\\nLast-Modified: %s\\r\\nContent-Length: 4\\r\\n\\r\\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - d * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"\nexit 0\n`);
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
printf '%s\\n' '${JSON.stringify(MATRIX_CANNED).replace(/'/g, "'\\''")}'
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
  const r = await runPipeline({ roundId: "2026-10-23-2341-health", ...io });
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

await t("VERIFY 分区穷尽(旗标3=survivors2+suppressed1,R1 抑制 dshield)+G_DEEP 证据逐字回引", async () => {
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
  const conf = v.verdicts.find((x) => /cinsscore/.test(x.hid));
  const refu = v.verdicts.find((x) => /binarydefense/.test(x.hid));
  assert.equal(conf.verdict, "confirmed");
  assert.equal(conf.evidence[0].value, 220, "confirmed 证据值=登记表 seed 值");
  assert.equal(refu.verdict, "refuted");
});

await t("ITEMIZE 判例:confirmed→review_freeze 原级;refuted 恒 low 消化条目(附带三小裁②)", async () => {
  const d = roundDir(R1);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.reopened, m.deduped, m.suppressed], [2, 0, 0, 1]);
  const items = fs.readdirSync(path.join(d, "items")).map((f) => j(path.join(d, "items", f)));
  const c = items.find((i) => i.source === "ciarm"); // 标源名(#164),URL=cinsscore.com
  const b = items.find((i) => i.source === "binarydefense");
  assert.equal(c.suggested_action, "review_freeze");
  assert.equal(c.severity, "high");
  assert.equal(b.suggested_action, "digest_ignore");
  assert.equal(b.severity, "low", "refuted 消化条目恒 low");
  assert.ok(items.every((i) => i.round_id === R1 && typeof i.dedup_key === "string" && i.dedup_key.length > 0));
});

await t("预算降级:0.03¥ 截尾 1 条标 unresolved(budget),DISPATCH degraded,轮仍 ok=true", async () => {
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2342-health", env: { ...process.env, OPS_PIPELINE_BUDGET_CNY: "0.03" }, ...io });
  assert.equal(r.ok, true, "降级不是失败(信封 ok=true+stages 标 degraded)");
  const dp = stageOf(r.envelope, "DISPATCH");
  assert.equal(dp.status, "degraded");
  const d = roundDir("2026-10-23-2342-health");
  const bun = j(path.join(d, "04-dispatch-bundles.json"));
  assert.equal(bun.bundles.length, 1);
  assert.equal(bun.truncated.length, 1);
  assert.equal(bun.truncated[0].reason, "unresolved(budget)");
  assert.match(bun.truncated[0].hid, /binarydefense/, "低 severity 先截");
  const v = j(path.join(d, "05-deep-verdicts.json"));
  assert.equal(v.verdicts.length, 1);
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.equal(m.created, 2, "截尾假设转 human_ruling 条目,证据不灭失");
});

await t("失败面:坏 TRIAGE fixture → model_face 终态(attempts=2),01/02 工件保留(证据不灭失),code∈九词", async () => {
  const badFx = path.join(TMP, "fixtures-bad");
  fs.mkdirSync(badFx, { recursive: true });
  for (const f of ["synth.json"]) fs.copyFileSync(path.join(AGENT, "fixtures/pipeline", f), path.join(badFx, f));
  fs.cpSync(path.join(AGENT, "fixtures/pipeline/deep"), path.join(badFx, "deep"), { recursive: true });
  fs.writeFileSync(path.join(badFx, "triage.json"), JSON.stringify({ turns: [{ role: "assistant", content: [{ type: "text", text: "不是 JSON(schema 违例负例)" }], stopReason: "stop" }] }));
  const io = mkIo();
  const r = await runPipeline({ roundId: "2026-10-23-2343-health", fixturesDir: badFx, ...io });
  assert.equal(r.ok, false);
  const env = r.envelope;
  assert.equal(env.error.code, "model_face");
  assert.ok(ERROR_CODES.includes(env.error.code), "错误码 ∈ 九词闭集零新词");
  const tr = stageOf(env, "TRIAGE");
  assert.equal(tr.status, "failed");
  assert.equal(tr.attempts, 2, "schema 违例重试≤1 后终态");
  const d = roundDir("2026-10-23-2343-health");
  assert.ok(fs.existsSync(path.join(d, "01-probe-summary.json")) && fs.existsSync(path.join(d, "02-verify-survivors.json")), "工件保留");
  assert.equal(j(path.join(d, "state.json")).status, "failed");
  assert.match(io.buf.stderr, /\[stage\] TRIAGE fail gate=- code=model_face reason=/, "fail 行语法");
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

await t("在飞真读 ops/items(active 在飞不重问+done 不算在飞)+R7 annotate 全链:CLI 轮绿,gates 含真在飞源重算", async () => {
  const DOCS2 = path.join(TMP, "docs2");
  fs.mkdirSync(path.join(DOCS2, "ops", "precedents"), { recursive: true });
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", PREC), path.join(DOCS2, "ops", "precedents", PREC));
  fs.copyFileSync(path.join(DOCS, "ops", "precedents", "_schema.md"), path.join(DOCS2, "ops", "precedents", "_schema.md"));
  fs.mkdirSync(path.join(DOCS2, "ops", "rules"), { recursive: true });
  fs.writeFileSync(path.join(DOCS2, "ops", "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
    { id: "R7", adopted: "2026-10-23", adopted_via: "判例 2026-10-23-ruling-0db230187f.md(裁决包 2026-10-23-health-1209.md)",
      match: { bucket: "unreachable", error_family: "http_429" },
      action: "annotate", note: "限流:降 severity 不抑制", review_at: "2027-01-21" } ] }, null, 2) + "\n");
  fs.mkdirSync(path.join(DOCS2, "ops", "items"), { recursive: true });
  // 真形 _ops_items 条目(十字段冻结面):bruteforce 在飞(active)→ 冻结旗不重问;ciarm 终态(done)→ 仍幸存
  fs.writeFileSync(path.join(DOCS2, "ops", "items", "2026-10-24-item-aaaa000001.md"), `---\nid: 2026-10-24-item-aaaa000001\naction: retry_download\nargs:\n  source: bruteforce\nevidence:\n  consecutive_failures: 2\nimpact: bruteforce 数据停更,威胁覆盖面收缩\nrollback: 重新触发下载即可恢复\ndedup_key:\n  source: bruteforce\n  probe_class: download\n  error_signature: http_4xx\nseverity: medium\ncause_group: download_failure\nstatus: active\n---\n\nselftest fixture(真形 _ops_items 条目;status active = 在飞)。\n`);
  fs.writeFileSync(path.join(DOCS2, "ops", "items", "2026-10-24-item-bbbb000002.md"), `---\nid: 2026-10-24-item-bbbb000002\naction: retry_download\nargs:\n  source: ciarm\nevidence:\n  consecutive_failures: 1\nimpact: ciarm 数据停更\nrollback: 重新触发下载即可恢复\ndedup_key:\n  source: ciarm\n  probe_class: download\n  error_signature: http_4xx\nseverity: medium\ncause_group: download_failure\nstatus: done\n---\n\nselftest fixture(终态 done 不算在飞,同源新旗仍应幸存)。\n`);
  const STUBS2 = path.join(TMP, "stubs2");
  fs.mkdirSync(STUBS2);
  // curl 替身:cinsscore 冻结 220(binarydefense 改 429 不可达 → R7 annotate);danger.rulez.sk 冻结 250(→ 在飞抑制);其余新鲜
  fs.writeFileSync(path.join(STUBS2, "curl"), `#!/usr/bin/env bash\nurl="\${@: -1}"\nd=30\ncase "$url" in\n  *cinsscore*) d=220 ;;\n  *binarydefense*) printf 'HTTP/1.1 429 Too Many Requests\\r\\n\\r\\n'; exit 0 ;;\n  *danger.rulez.sk*) d=250 ;;\nesac\nprintf 'HTTP/1.1 200 OK\\r\\nLast-Modified: %s\\r\\nContent-Length: 4\\r\\n\\r\\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - d * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"\nexit 0\n`);
  fs.chmodSync(path.join(STUBS2, "curl"), 0o755);
  fs.copyFileSync(path.join(STUBS, "py-matrix"), path.join(STUBS2, "py-matrix"));
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0100-health"],
    { PATH: `${STUBS2}:${process.env.PATH}`, DOCS_ROOT: DOCS2, PRECEDENTS_DIR: path.join(DOCS2, "ops", "precedents"),
      LEDGER_FILE: path.join(DOCS2, "ops", "ledger.md") });
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-400)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true);
  const d = path.join(DOCS2, "ops", "rounds", "2026-10-24-0100-health"); // 本例轮次落 DOCS2(专用 DOCS 树)
  const s = j(path.join(d, "01-probe-summary.json"));
  assert.equal(s.buckets.unreachable, 1);
  assert.equal(s.flags.find((f) => /binarydefense/.test(f.url)).error_family, "http_429", "四列 error_family 进旗标");
  const sv = j(path.join(d, "02-verify-survivors.json"));
  const sp = j(path.join(d, "02-verify-suppressed.json"));
  assert.equal(sv.survivors.length, 2, "canned 链守恒:ciarm(done 不算在飞)+binarydefense(R7 annotate)");
  assert.equal(sv.survivors.find((x) => x.source === "binarydefense").annotated_rule, "R7");
  assert.ok(sv.survivors.some((x) => x.source === "ciarm"), "done 条目不抑制同源新旗(在飞=active|snoozed)");
  assert.equal(sp.suppressed.length, 1);
  assert.equal(sp.suppressed[0].rule_id, "in_flight");
  assert.equal(sp.suppressed[0].source, "bruteforce");
  assert.deepEqual(sp.suppressed[0].in_flight_items, ["2026-10-24-item-aaaa000001"], "溯源到真条目 id");
  const g = j(path.join(d, "gates.json"));
  assert.ok(g.records.every((x) => x.pass), "门全绿(G_VERIFY 真在飞面重算)");
  const m = j(path.join(d, "06-itemize-manifest.json"));
  assert.deepEqual([m.created, m.suppressed], [2, 1], "canned synth 计数链守恒");
});

await t("matrix 裸失败负例(#163 review P2-1):信封件落 01-probe-matrix.json,summary.matrix.ok=false,轮仍 ok=true 不阻轮", async () => {
  const STUBS3 = path.join(TMP, "stubs3");
  fs.mkdirSync(STUBS3);
  fs.writeFileSync(path.join(STUBS3, "py-matrix-fail"), `#!/usr/bin/env bash\necho 'boom: matrix stub bare failure' >&2\nexit 1\n`);
  fs.chmodSync(path.join(STUBS3, "py-matrix-fail"), 0o755);
  const r = await spawnPipe(["health", "--round-id", "2026-10-24-0101-health"], { OPS_EVAL_PY: path.join(STUBS3, "py-matrix-fail") });
  assert.equal(r.rc, 0, `rc=${r.rc} stderr=${r.stderr.slice(-400)}`);
  const env = JSON.parse(r.stdout.trim().split("\n").pop());
  assert.equal(env.ok, true, "matrix 失败=嵌套信封不阻轮(C稿 §2.2;证据不灭失落件)");
  const d = roundDir("2026-10-24-0101-health");
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
  const pipe = await runPipeline({ roundId: "2026-10-23-2344-health", ...io });
  assert.equal(pipe.ok, true);
  const d = roundDir("2026-10-23-2344-health");
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
  assert.ok(fs.existsSync(path.join(d, "07-synth-report.md")) && fs.existsSync(path.join(d, "items")), "段内产物再生");
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

fs.rmSync(TMP, { recursive: true, force: true });
console.log(`pipeline-selftest: PASS=${pass} FAIL=${fail}`);
process.exit(fail ? 1 : 0);
