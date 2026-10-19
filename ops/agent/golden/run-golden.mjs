#!/usr/bin/env node
// run-golden.mjs — 金轨迹集 runner(Task 6 Step 2/3)。
// 用法: node ops/agent/golden/run-golden.mjs [--only <id>] [--smoke] [--list]   ← 父进程(逐例派生子进程)
//       node ops/agent/golden/run-golden.mjs --case <id> [--smoke]             ← 子进程(单例)
// faux 层(pi-ai fauxProvider)跑真实 agent.mjs runRound 回路:真 Agent 循环 + 真写前语义门
// + 真收口四件(包/台账/闭合校验/沙箱断言),零 API 花费;判据全布尔(计划书:无 1-5 打分)。
// 隔离:每例一子进程,fixture DOCS_ROOT(判例树/队列/台账/包全落 tmp)——真实 docs 树零触碰;
// DOCS_ROOT/PRECEDENTS_DIR/LEDGER_FILE 经 lib.sh 落位默认值传导(env 先于 import)。
// smoke 层(真模型)= --smoke 显式手跑,花 API,不进 selftest/CI。
import { execFile as execFileCb } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(fs.readFileSync(path.join(HERE, "cases.json"), "utf8")).cases;

// fixture 判例树(cases.json $comment 契约):A 命中 health+discover 检索词;B 在库但零命中(负例③)
const PREC_A = "2026-06-01-golden-aggregator.md";
const PREC_B = "2026-06-02-golden-matrix-nolayer.md";
const writePrecedents = (dir) => {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, PREC_A),
    `---\nid: ${PREC_A.replace(/\.md$/, "")}\ndate: 2026-06-01\nsubject: fixture — 聚合器候选必须实测排他率\ncontext: >\n  聚合器形状候选,上游映射推断重叠不可信,\n  排他率必须实测(冻结门线外另议)。\nhuman_ruling: >\n  实测排他率 50.0%,推翻 REJECT,立项。\nreward:\n  hard_gates:\n    exclusive_rate: "50.0%"\n  ruling_agreement: overruled\n---\n\n正文检索词:聚合器 排他率 回声 冻结 违例。\n`);
  fs.writeFileSync(path.join(dir, PREC_B),
    `---\nid: ${PREC_B.replace(/\.md$/, "")}\ndate: 2026-06-02\nsubject: fixture — 语义矩阵 NO-LAYER 层读数约定\ncontext: >\n  truth 层无取样资产时读数记 NO-LAYER,\n  摘要员如实提及不计入异常。\nhuman_ruling: >\n  认可约定。\nreward:\n  hard_gates: {}\n  ruling_agreement: agreed\n---\n\n正文:语义矩阵 NO-LAYER 层读数约定(零检索词命中样本)。\n`);
  fs.writeFileSync(path.join(dir, "_schema.md"), "schema 说明(注入排除面)。\n");
};

// stub 脚本(判例:PI_BIN stub 同型——CLI 边界替身,工具实现层全真)
const stubCurl = (rules) => `#!/usr/bin/env bash
# golden stub: curl 传输层替身(health 例)。末参=URL;按 cases.json curl_age_days 规则回
# Last-Modified(600s 余量防跨天抖动);HTTP/行与头形对齐 lib.sh _ff_probe/_ff_code 解析。
url="${'${@: -1}'}"
d=180
case "$url" in
${rules.map((r) => `  *${r.match}*) d=${r.days} ;;`).join("\n")}
esac
printf 'HTTP/1.1 200 OK\\r\\nLast-Modified: %s\\r\\nContent-Length: 4\\r\\n\\r\\n' \\
  "$(date -u -d "@$(( $(date +%s) - d * 86400 - 600 ))" '+%a, %d %b %Y %H:%M:%S GMT')"
exit 0
`;
const stubGh = (repos) => `#!/usr/bin/env bash
# golden stub: gh search 边界替身(discover 例);repos 检索回 cases.json 罐装行,其余空数组。
for a in "$@"; do [[ "$a" == "repos" ]] && { printf '%s\\n' '${JSON.stringify(repos)}'; exit 0; }; done
printf '[]\\n'
`;
const stubPy = (matrix) => `#!/usr/bin/env bash
# golden stub: OPS_EVAL_PY 替身(matrix 例);吐罐装矩阵 JSON(runMatrixScan/matrixFromResult 真路径)。
printf '%s\\n' '${JSON.stringify(matrix).replace(/'/g, "'\\''")}'
`;

async function runCase(c, allowSmoke) {
  if (c.tier === "smoke" && !allowSmoke) throw new Error("smoke 层花 API,须 --smoke 显式手跑");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), `golden-${c.id}-`));
  const docsRoot = path.join(tmp, "docs");
  writePrecedents(path.join(docsRoot, "ops", "precedents"));
  const stubDir = path.join(tmp, "stubs");
  fs.mkdirSync(stubDir, { recursive: true });
  const writeStub = (name, text) => { const p = path.join(stubDir, name); fs.writeFileSync(p, text); fs.chmodSync(p, 0o755); return p; };

  process.env.DOCS_ROOT = docsRoot;          // 先于 tools/agent/lib.sh import 与子进程传导
  // 显式钉 fixture 路径:父进程(如 selftest.sh)可能已导出 PRECEDENTS_DIR/LEDGER_FILE
  // 指向自己的 fixture——不钉则 lib.sh 默认值被继承值压过,verify/台账读写错库
  process.env.PRECEDENTS_DIR = path.join(docsRoot, "ops", "precedents");
  process.env.LEDGER_FILE = path.join(docsRoot, "ops", "ledger.md");
  if (c.stubs.curl_age_days) process.env.PATH = `${stubDir}:${process.env.PATH}`, writeStub("curl", stubCurl(c.stubs.curl_age_days));
  if (c.stubs.gh) writeStub("gh", stubGh(c.stubs.gh.repos)), process.env.PATH = `${stubDir}:${process.env.PATH}`;
  if (c.stubs.matrix) process.env.OPS_EVAL_PY = writeStub("py-matrix", stubPy(c.stubs.matrix));

  const { runRound } = await import("../agent.mjs");
  const { resolveField } = await import("../tools.mjs");
  let result = null, err = null;
  if (c.tier === "faux") {
    const { Agent } = await import("@earendil-works/pi-agent-core");
    const { fauxProvider, fauxAssistantMessage, fauxToolCall, fauxText, createModels } = await import("@earendil-works/pi-ai");
    const faux = fauxProvider({ models: [{ id: "faux-golden" }] });
    const models = createModels();
    models.setProvider(faux.provider);
    faux.setResponses(c.turns.map((t) => t.toolCall
      ? fauxAssistantMessage([fauxToolCall(t.toolCall.name, t.toolCall.args ?? {}, { id: t.toolCall.id })], { stopReason: "toolUse" })
      : fauxAssistantMessage([fauxText(t.text)])));
    try {
      result = await runRound(c.round, c.input, [], {
        models: { models, resolve: () => faux.getModel() },
        registrySeed: c.registrySeed,
      });
    } catch (e) { err = e; }
  } else {
    try { result = await runRound(c.round, c.input); } catch (e) { err = e; }
  }

  const queueFile = path.join(docsRoot, "ops", "queue.md");
  const ledgerFile = path.join(docsRoot, "ops", "ledger.md");
  const packagesDir = path.join(docsRoot, "ops", "packages");
  const newestPkg = () => fs.readdirSync(packagesDir).map((f) => path.join(packagesDir, f))
    .filter((p) => p.endsWith(".md")).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  const pkgText = (result?.pkg ?? newestPkg()) ? fs.readFileSync(result?.pkg ?? newestPkg(), "utf8") : null;
  const fails = [];
  const fail = (a, msg) => fails.push(`${a.kind} ${a.path ?? ""}${a.id ? `(${a.id})` : ""}: ${msg}`);
  for (const a of c.assertions) {
    switch (a.kind) {
      case "round_ok": {
        const ok = a.expected === false ? !!err : !err;
        if (!ok) fail(a, `expected=${a.expected ?? true} 实得 ${err ? `抛错:${err.message}` : "成功"}`);
        break;
      }
      case "error_matches":
        if (!(err && new RegExp(a.pattern).test(err.message))) fail(a, `err=${err?.message ?? "(无)"}`);
        break;
      case "tool_calls": {
        const got = result?.toolCalls ?? [];
        if (JSON.stringify(got) !== JSON.stringify(a.equals)) fail(a, `实得 ${JSON.stringify(got)}`);
        break;
      }
      case "registry": {
        const rec = (result?.registry ?? []).find((r) => r.id === a.id);
        if (!rec) { fail(a, "登记表无此 call_id"); break; }
        const v = resolveField(rec, a.path);
        if ("equals" in a && v !== a.equals) fail(a, `${a.path}=${JSON.stringify(v)} ≠ ${JSON.stringify(a.equals)}`);
        if ("matches" in a && !new RegExp(a.matches).test(String(v))) fail(a, `${a.path}=${JSON.stringify(v)} 不匹配 /${a.matches}/`);
        if ("at_least" in a && !(typeof v === "number" && v >= a.at_least)) fail(a, `${a.path}=${v} < ${a.at_least}`);
        if (a.equals_field_minus) {
          const base = resolveField(rec, a.equals_field_minus[0]);
          if (!(v === base - a.equals_field_minus[1])) fail(a, `${a.path}=${v} ≠ ${a.equals_field_minus[0]}-${a.equals_field_minus[1]}=${base - a.equals_field_minus[1]}`);
        }
        break;
      }
      case "queue_writes": {
        const w = result?.queueWrites ?? [];
        if (w.length !== a.count) fail(a, `实得 ${w.length}(${w.map((x) => x.action).join(",")})`);
        if (a.actions && JSON.stringify(w.map((x) => x.action)) !== JSON.stringify(a.actions)) fail(a, "action 序列不符");
        break;
      }
      case "queue_file": {
        const txt = fs.existsSync(queueFile) ? fs.readFileSync(queueFile, "utf8") : null;
        if (a.state === "absent" && txt) fail(a, "队列文件不应存在却已写");
        if (a.state === "row" && !(txt && new RegExp(a.pattern).test(txt))) fail(a, `队列行缺失 /${a.pattern}/`);
        break;
      }
      case "ledger": {
        if (!fs.existsSync(ledgerFile)) { fail(a, "台账文件缺失"); break; }
        const rows = fs.readFileSync(ledgerFile, "utf8").split("\n").filter((l) => /^\| \d{4}-\d{2}-\d{2} \|/.test(l));
        if (rows.length < a.min_rows) fail(a, `行数 ${rows.length} < ${a.min_rows}`);
        if (a.last_matches && !new RegExp(a.last_matches).test(rows[rows.length - 1] ?? "")) fail(a, `末行不匹配:${rows[rows.length - 1]}`);
        break;
      }
      case "package": {
        if (a.exists && !pkgText) { fail(a, "包文件缺失"); break; }
        if (pkgText) {
          for (const re of a.matches ?? []) if (!new RegExp(re).test(pkgText)) fail(a, `包不匹配 /${re}/`);
          for (const re of a.not_matches ?? []) if (new RegExp(re).test(pkgText)) fail(a, `包不应匹配 /${re}/`);
        }
        break;
      }
      default: fail(a, `未知断言种类(${a.kind})——用例集词汇表外`);
    }
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  return fails;
}

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };

if (args.includes("--list")) {
  for (const c of CASES) console.log(`${c.tier}\t${c.id}\t${c.tags.join(",")}\t${c.desc.slice(0, 60)}`);
  process.exit(0);
}

if (args.includes("--case")) { // 子进程:单例
  const c = CASES.find((x) => x.id === flag("--case"));
  if (!c) { console.error(`GOLDENFAIL ${flag("--case")}: 用例集无此 id`); process.exit(1); }
  try {
    const fails = await runCase(c, args.includes("--smoke"));
    if (fails.length) {
      console.log(`GOLDENFAIL ${c.id}`);
      for (const f of fails) console.log(`  ${f}`);
      process.exit(1);
    }
    console.log(`GOLDENPASS ${c.id}`);
    process.exit(0);
  } catch (e) {
    console.log(`GOLDENFAIL ${c.id}: ${e.message}`);
    process.exit(1);
  }
}

// 父进程:逐例派生子进程(隔离 DOCS_ROOT/PATH env;子进程内 env 先于 import 生效)
const smoke = args.includes("--smoke");
const only = flag("--only");
const todo = CASES.filter((c) => (only ? c.id === only : c.tier === "faux"));
if (!todo.length) { console.error("无可跑用例(--only 未命中或非 smoke 模式)"); process.exit(1); }
if (smoke) console.error("SMOKE 模式:真模型用例,花 API(冒烟层,不进 selftest/CI)");
let pass = 0, failN = 0;
for (const c of todo) {
  const out = await new Promise((res) => execFileCb(process.execPath, [fileURLToPath(import.meta.url), "--case", c.id, ...(smoke ? ["--smoke"] : [])],
    { timeout: 300_000, maxBuffer: 32 * 1024 * 1024, cwd: HERE },
    (e, stdout, stderr) => res({ rc: e?.code ?? 0, stdout, stderr })));
  process.stdout.write(out.stdout);
  if (/^GOLDENPASS /m.test(out.stdout) && out.rc === 0) pass++;
  else {
    failN++;
    if (out.stderr.trim()) process.stderr.write(out.stderr.split("\n").map((l) => `  | ${l}`).join("\n") + "\n");
  }
}
console.log(`golden: PASS=${pass} FAIL=${failN}`);
process.exit(failN ? 1 : 0);
