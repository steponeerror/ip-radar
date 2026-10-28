#!/usr/bin/env node
// shadow-diff.mjs — shadow 对拍 harness(票 #229 T5;spec 定案 2 安全轨的执行面)。
// 双面同种子同罐装世界、停笔面同构(均止于 RETRO):OLD = 旧管线 pipeline.mjs replay
// --from TRIAGE(旧 replay 契约缺省 --to RETRO;新开 -rN 目录,原件零改写);NEW =
// run-health.mjs --from-phase TRIAGE --to-phase RETRO(toPhase=旧 --to 镜像)。
// 载具判例:全链载具不可行——旧 PROBE 天生联网(extract_feed_urls→feed_freshness 真网,
// golden 亦从罐装断点进),shadow 恒零网络红线 → 只能断点进。CLOSE 面不入载具(旧
// replay 不入 CLOSE),其同构由 launcher 测试钉(run-health 全链信封/G_CLOSE)。
// 对拍面 = 可比工件闭集 + 台账行;归一化只抹时间/时长/tmp 路径、replay -rN 后缀与台账
// usage 计数(两套 harness 计量边界不同:in/out/total 合法差;cost 细胞逐字比,faux 恒 0;
// 台账语义面=行存在+日期/轮次/model/备注轮 id);语义字段一律逐字比(位等价闸门,收口
// T3 遗留「归一化宽缝」)。
// 结构性白名单(声明面,非归一化):两侧 state.json 各为实现细节(OLD=磁盘状态机,
// NEW=checkpoint 镜像)不入对拍面;NEW 09-budget.json 只在 CLOSE 落件=载具停笔前不存在,
// 不在闭集。SHADOW-RUNBOOK §已知差异面。
// 用法:node shadow-diff.mjs <roundId> [--fixtures DIR](缺省 ops/agent/fixtures/pipeline)
//        [--keep](保留双世界目录供人工 diff)
// 退出:0=可比面全 SAME;1=存在 DIFF;2=用法错;3=任一面运行失败。
import { execFile as execFileCb, spawn } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFileCb);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const AGENT = path.resolve(HERE, "..", "agent"); // ops/agent(旧真源)
const FIXTURES = path.join(AGENT, "fixtures", "pipeline");
const PREC = "2026-06-01-golden-aggregator.md";
const CINS = "https://cinsscore.com/list/ci-badguys.txt";
const BDEF = "https://www.binarydefense.com/banlist.txt";
const CINS_SLUG = "https-cinsscore.com-list-ci-badguys.txt";

// 可比工件闭集(前缀级;05-deep-* 双侧展开)。09-budget/state.json/envelope 不入(上方声明)。
const COMPARABLE = ["03-", "04-", "05-", "06-", "07-", "08-", "gates.json"]; // 01/02=罐装种子面;09-budget=NEW CLOSE 落件,载具停笔前不存在,不入

// —— 世界种子(health-e2e.test.mjs seedWorld 同契约:判例+规则+01/02 前置工件+永败 eval stub;
// 导出面=cron-launchers 测试复用同世界形状)——
export function seedWorld(roundId) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), `v2-shadow-${roundId}-`));
  const docs = path.join(tmp, "docs");
  const ops = path.join(docs, "ops");
  const roundDir = path.join(ops, "rounds", roundId);
  for (const d of [path.join(ops, "precedents"), path.join(ops, "rules"), path.join(ops, "items"), roundDir, path.join(ops, "retro")]) fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(ops, "precedents", PREC), `---\nid: 2026-06-01-golden-aggregator\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`);
  fs.writeFileSync(path.join(ops, "precedents", "_schema.md"), "schema 说明(注入排除面)。\n");
  fs.writeFileSync(path.join(ops, "rules", "suppressions.json"), JSON.stringify({ version: 1, rules: [
    { id: "R1", adopted: "2026-10-24", adopted_via: "item-fixture", match: { bucket: "frozen", url_shape: "*dshield.org*" },
      action: "suppress", note: "fixture:dshield 冻结读数为已知探测伪迹", review_at: "2027-01-24" } ] }, null, 2) + "\n");
  // 01/02 前置工件(fromPhase=TRIAGE;E2E ⑫ 同面):2 冻结幸存+1 抑制
  fs.writeFileSync(path.join(roundDir, "01-probe-summary.json"), JSON.stringify({ ok: true, round_id: roundId, urls_n: 3, attempted_n: 3,
    buckets: { fresh: 0, frozen: 3, unreachable: 0, token_required: 0, no_lm: 0 },
    flags: [
      { signal_id: CINS, url: CINS, bucket: "frozen", source: "cinsscore", age_days: 220, last_modified: "canned-220d" },
      { signal_id: BDEF, url: BDEF, bucket: "frozen", source: "binarydefense", age_days: 210, last_modified: "canned-210d" },
      { signal_id: "https://lists.dshield.org/block.txt", url: "https://lists.dshield.org/block.txt", bucket: "frozen", source: "dshield", age_days: 200, last_modified: "canned-200d" },
    ], matrix: { ok: true, exit_code: 0, violation_n: 0 } }, null, 2) + "\n");
  fs.writeFileSync(path.join(roundDir, "02-verify-survivors.json"), JSON.stringify({ survivors: [
    { signal_id: CINS, source: "cinsscore", bucket: "frozen", age_days: 220, url: CINS },
    { signal_id: BDEF, source: "binarydefense", bucket: "frozen", age_days: 210, url: BDEF },
  ], known_noise_digest: [{ id: "R1", action: "suppress", match: { bucket: "frozen", url_shape: "*dshield.org*" }, note: "fixture", review_at: "2027-01-24" }], rules_version: 1, in_flight_n: 0 }, null, 2) + "\n");
  fs.writeFileSync(path.join(roundDir, "02-verify-suppressed.json"), JSON.stringify({ suppressed: [
    { signal_id: "https://lists.dshield.org/block.txt", source: "dshield", bucket: "frozen", age_days: 200, url: "https://lists.dshield.org/block.txt", rule_id: "R1" },
  ], rules_version: 1 }, null, 2) + "\n");
  // 永败 eval stub(锚巡检双面同降级)+ dry-run 双保险
  const stub = path.join(tmp, "stub-eval.py");
  fs.writeFileSync(stub, "#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n");
  fs.chmodSync(stub, 0o755);
  const env = {
    ...process.env,
    DOCS_ROOT: docs, PRECEDENTS_DIR: path.join(ops, "precedents"), LEDGER_FILE: path.join(ops, "ledger.md"),
    OPS_EVAL_PY: `python3 ${stub}`, OPS_SWEEP_DRY_RUN: "1",
  };
  return { tmp, docs, ops, roundDir, env };
}

// —— 子进程运行器(stdout 末行信封收集;两 launcher/旧 CLI 均单行 JSON 契约)——
async function runSide(cmd, args, env, label) {
  const r = await new Promise((resolve) => {
    const p = spawn(cmd, args, { env, cwd: path.resolve(HERE, "..", "..") });
    let out = "", err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("close", (code) => resolve({ code, out, err }));
  });
  const lines = r.out.trimEnd().split("\n");
  let envelope = null;
  try { envelope = lines.length ? JSON.parse(lines.at(-1)) : null; } catch { envelope = null; } // P2-6:末行非 JSON=信封缺失,不炸诊断
  if (r.code === 3) throw new Error(`${label} 运行期异常(exit 3):\n${r.err.split("\n").slice(-6).join("\n")}`);
  if (r.code !== 0) process.stderr.write(`[${label}] exit=${r.code} envelope=${JSON.stringify(envelope)}\n[${label}] stderr 尾:\n${r.err.split("\n").filter(Boolean).slice(-8).join("\n")}\n`);
  return { code: r.code, envelope, stderr: r.err };
}

// —— 归一化(窄面:时间/时长/tmp 路径;语义字段零归一)——
function normalizeText(t, base) {
  return t
    .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/g, "<TS>")
    .replace(/"generated_at":\s*"<TS>"/g, '"generated_at":"<TS>"')
    .replace(/"updated_at":\s*"<TS>"/g, '"updated_at":"<TS>"')
    .replace(/"started_at":\s*"<TS>"/g, '"started_at":"<TS>"')
    .replace(/"dur_ms":\s*\d+/g, '"dur_ms":0')
    .replaceAll(base.oldTmp, "<TMP>").replaceAll(base.newTmp, "<TMP>")
    .replace(new RegExp(base.roundId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "-r\\d+", "g"), base.roundId) // replay -rN 后缀(轮 id/台账备注/gates inputs/artifacts 内 round_id)
    ;
}
function filesOf(dir) { return fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => !fs.statSync(path.join(dir, f)).isDirectory()) : []; }

export async function shadowDiff(opts = {}) {
  const roundId = opts.roundId ?? `2026-10-28-1700-health`;
  const fixtures = opts.fixturesDir ?? FIXTURES;
  const old = seedWorld(roundId);
  const neu = seedWorld(roundId);
  const base = { oldTmp: old.tmp, newTmp: neu.tmp, roundId };
  // OLD:旧 replay(需先落 state.json 供 replay 读——in_flight 于 VERIFY 断点形;PROBE/VERIFY
  // 两 rec 由罐装 01/02 面代理,与旧 selftest-pipeline ⑫ 同法)
  fs.writeFileSync(path.join(old.roundDir, "state.json"), JSON.stringify({ schema: 1, round_id: roundId, type: "health", pipeline_mode: "pipeline",
    status: "in_flight", stage: "VERIFY", stages: [{ name: "PROBE", status: "done", attempts: 1, dur_ms: 0, usage: null }, { name: "VERIFY", status: "done", attempts: 1, dur_ms: 0, usage: null }],
    budget_knobs: null, fixtures_dir: fixtures, model_face: "faux", prompt_hashes: {}, updated_at: new Date().toISOString(), started_at: new Date().toISOString() }, null, 2) + "\n");
  const oldR = await runSide("node", [path.join(AGENT, "pipeline.mjs"), "replay", roundId, "--from", "TRIAGE", "--fixtures", fixtures], old.env, "OLD");
  const newR = await runSide("node", [path.join(HERE, "run-health.mjs"), roundId, "--from-phase", "TRIAGE", "--to-phase", "RETRO", "--fixtures", fixtures, "--db", path.join(neu.tmp, "s.sqlite")], neu.env, "NEW");
  // 双面目录:OLD=rounds/<id>-rN(replay 新目录);NEW=rounds/<id>(任务原目录)
  const rounds = path.join(old.ops, "rounds");
  const oldReplayDir = fs.readdirSync(rounds).filter((f) => new RegExp(`${roundId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-r\\d+$`).test(f)).sort().at(-1);
  const oldDir = path.join(rounds, oldReplayDir ?? `${roundId}-rX`);
  const newDir = path.join(neu.ops, "rounds", roundId);
  const report = { roundId, sides: { old: { code: oldR.code, envelope: oldR.envelope }, new: { code: newR.code, envelope: newR.envelope } }, files: [], verdict: "SAME" };
  // P1-1:双面皆败(或任一面信封非 ok)=闸门失败,不得假 SAME;可比集空/台账行缺同理。
  // 实证:双面同因败(如共享 steps 回归)可比集空 → 旧版 VERDICT SAME exit 0。
  const sideOk = (s) => s.envelope?.ok === true;
  if (!sideOk(oldR) || !sideOk(newR)) {
    report.verdict = "DIFF";
    report.files.push({ file: "(envelope)", verdict: "SIDE-FAILED", hint: `old.ok=${oldR.envelope?.ok}(${oldR.envelope?.error?.code ?? "?"}) new.ok=${newR.envelope?.ok}(${newR.envelope?.error?.code ?? "?"})` });
  }
  const oldFiles = filesOf(oldDir).filter((f) => f !== "state.json");
  const newFiles = filesOf(newDir).filter((f) => f !== "state.json");
  const names = [...new Set([...oldFiles, ...newFiles])].filter((f) => COMPARABLE.some((p) => f.startsWith(p)));
  for (const f of names.sort()) {
    const o = oldFiles.includes(f), n = newFiles.includes(f);
    if (o && !n) { report.files.push({ file: f, verdict: "ONLY-OLD" }); report.verdict = "DIFF"; continue; }
    if (!o && n) { report.files.push({ file: f, verdict: "ONLY-NEW" }); report.verdict = "DIFF"; continue; }
    const a = normalizeText(fs.readFileSync(path.join(oldDir, f), "utf8"), base);
    const b = normalizeText(fs.readFileSync(path.join(newDir, f), "utf8"), base);
    report.files.push({ file: f, verdict: a === b ? "SAME" : "DIFF", ...(a === b ? {} : { hint: firstDiff(a, b) }) });
    if (a !== b) report.verdict = "DIFF";
  }
  // P2-⑪ NEW 侧残余文件哨:白名单(state.json 已滤+01-/02- 罐装种子+09-budget.json CLOSE
  // 落件声明+.v2-claim.json 健康轮轮目录认领件(健康轮跨库撞轮守卫的落件,ENVELOPE/RUNBOOK
  // 已声明))之外、又不在 COMPARABLE 闭集的文件 = 未声明新面 → DIFF 记 ONLY-NEW-EXTRA。
  // 防「闭集外新面盲」:COMPARABLE 只防已知面漂移,新落件若无此哨则静默漏过。
  for (const f of newFiles)
    if (!COMPARABLE.some((p) => f.startsWith(p)) && !/^0[12]-/.test(f) && f !== "09-budget.json" && f !== ".v2-claim.json") {
      report.files.push({ file: f, verdict: "ONLY-NEW-EXTRA", hint: "闭集外未声明新面" });
      report.verdict = "DIFF";
    }
  const artifactN = report.files.length; // 可比工件条目数(不含后续台账行;P1-1 空集判据)
  // 台账行(RETRO 写面;行形 | 日期 | 轮次 | model | 用量 | 备注 |)。语义面=行存在+
  // 日期/轮次/model/备注轮 id;usage 计数细胞归一(两套 harness 计量边界合法差),
  // cost 细胞逐字比(faux 恒 0;生产 shadow 期 cost 差即真 DIFF——月度准入只吃 cost)。
  const normLedger = (t) => normalizeText(t, base).replace(/in=\d+ out=\d+ total=\d+/g, "in=<N> out=<N> total=<N>");
  const oldLed = fs.existsSync(path.join(old.ops, "ledger.md")) ? fs.readFileSync(path.join(old.ops, "ledger.md"), "utf8") : "";
  const newLed = fs.existsSync(path.join(neu.ops, "ledger.md")) ? fs.readFileSync(path.join(neu.ops, "ledger.md"), "utf8") : "";
  const ledSame = normLedger(oldLed).trim() === normLedger(newLed).trim();
  report.files.push({ file: "ledger.md", verdict: ledSame ? "SAME" : "DIFF", ...(ledSame ? {} : { hint: `OLD:[${oldLed.trim().split("\n").at(-1)}] NEW:[${newLed.trim().split("\n").at(-1)}]` }) });
  if (!ledSame) report.verdict = "DIFF";
  if (sideOk(oldR) && sideOk(newR) && artifactN === 0) {
    report.verdict = "DIFF"; // P1-1:双面 ok 但可比集空=闸门失败(种子/闭集漂移),不假 SAME
    report.files.push({ file: "(comparable-set)", verdict: "EMPTY", hint: "双面 ok 但可比工件集为空" });
  }
  if (opts.keep) report.keepDirs = { old: old.tmp, new: neu.tmp };
  else { fs.rmSync(old.tmp, { recursive: true, force: true }); fs.rmSync(neu.tmp, { recursive: true, force: true }); }
  return report;
}
function firstDiff(a, b) {
  const la = a.split("\n"), lb = b.split("\n");
  for (let i = 0; i < Math.max(la.length, lb.length); i++)
    if (la[i] !== lb[i]) return `L${i + 1}: OLD=${(la[i] ?? "").slice(0, 120)} | NEW=${(lb[i] ?? "").slice(0, 120)}`;
  return "length";
}

// ── CLI ──
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const flag = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
  const roundId = args[0] && !args[0].startsWith("--") ? args[0] : undefined // 位置首参=roundId(终审修复:flag 先于位置参时原 find 会把 flag 值误当 id);
  if (!roundId) { process.stderr.write("用法:node shadow-diff.mjs <roundId> [--fixtures DIR] [--keep]\n"); process.exitCode = 2; } // exitCode 而非 exit:stdout 写入异步落管,process.exit 可截断报告行(旧 pipeline.mjs:547 判例)
  else {
    let r;
    try {
      r = await shadowDiff({ roundId, fixturesDir: flag("fixtures") ? path.resolve(flag("fixtures")) : undefined, keep: args.includes("--keep") });
    } catch (e) { // P1-2:运行期异常 exit 3(与 DIFF 的 1 分码)
      process.stderr.write(`${e.stack ?? e}\n`);
      process.exitCode = 3;
    }
    if (r) {
      for (const f of r.files) process.stdout.write(`${f.verdict.padEnd(9)} ${f.file}${f.hint ? `  ${f.hint}` : ""}\n`);
      if (!r.sides.old.envelope?.ok) process.stdout.write(`OLD envelope: ${JSON.stringify(r.sides.old.envelope)}\n`);
      if (!r.sides.new.envelope?.ok) process.stdout.write(`NEW envelope: ${JSON.stringify(r.sides.new.envelope)}\n`);
      process.stdout.write(`VERDICT ${r.verdict}(old.exit=${r.sides.old.code} new.exit=${r.sides.new.code})\n`);
      process.exitCode = r.verdict === "SAME" ? 0 : 1;
    }
  }
}
