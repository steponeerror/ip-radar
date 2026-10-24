#!/usr/bin/env node
// agent.mjs — pi-agent-core 宿主(计划书 Task 4 终稿;ADR 0004)。
// 用法: node ops/agent/agent.mjs <health|discover> "<本轮输入>" [追加判例检索词...]
//
// 架构(计划书 Task 4 节):装载模型(models.mjs,用户 models.json 优先三层 upsert)
// → new Agent({initialState:{systemPrompt=轮次系统提示文件, model=健康 glm-5.3-flash/
// discover glm-5.3 主力, tools=轮次工具集}, streamFn, beforeToolCall=写前语义门})
// → prompt(预注入判例块≤8 条+输入)→ subscribe 累计 assistant message_end usage(回合求和)
// → host 收口四件:裁决包 + 台账(轮次汇总行)+ 判例引用闭合校验[∈预注入∪本会话命中]
// + sandbox_assert。任一失败 = 轮次失败非零退出。
// 结构性红线:零内建工具(tools 仅 ToolHost 领域面);agent 永不写数据面/查询路径。
// opts(T6 金轨迹缝,缺省=生产行为不变):opts.models={models,resolve} 注入 faux provider
// 模型(pi-ai faux;不花 API);opts.registrySeed=[{id,tool,sc}] 预登记测量腿结构化返回——
// 排他 24.9/25.0 边界用例的 exclusive_probe 需真网络+数据面,离线金轨迹钉其冻结契约
// (tools.mjs outputSchema 形状),门仍从登记表真算。返回值 registry=登记表快照(断言面)。
// spawn 契约(2026-10-20 契约深化批,T4「CLI 契约冻结」后首次修约——消费方 P2 未现,修约非违约):
// stdout=轮次信封(单行 JSON,成功/失败同形,main 序列化处);此前 stdout 上的人读散文(完成
// 横幅/verify 消息)与进度行全走 stderr——P2 将 tee stderr 做 SSE 进度;用法错
// (argv 缺参)=纯 stderr + exit 2,不发 JSON。env 面 = SPAWN_CONTRACT_ENV(下方,唯一详述点)。
// stderr 进度行语法(票 #142 修约,第二次修约——驾驶舱消费方已现):
//   [turn N] stopReason=<r> usage(in=<i> out=<o>)            回合结束,累计前 provider 实报
//   [tool] <name>(<callId>) <参数一行摘要>                     起跑行;摘要=工具闭集逐一的人读
//                                                              关键位(零参工具无摘要段)
//   [tool-result] <name>(<callId>) ok <关键读数>               完成行;读数从 structuredContent
//                                                              摘取(如 rate=0.44 control_pass=true)
//   [tool-result] <name>(<callId>) fail code=<code>            失败信封行;code=铁律②信封 code
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { Agent } from "@earendil-works/pi-agent-core";
import { loadModels } from "./models.mjs";
import { ToolHost, DOCS_ROOT, closureCheck, searchPrecedentsCore } from "./tools.mjs";

const execFileP = promisify(execFileCb);
const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGES_DIR = path.join(DOCS_ROOT, "ops/packages");
const KWS = {
  health: ["冻结", "死键", "不可达", "违例"],
  discover: ["排他率", "聚合器", "许可", "体量", "冻结", "sunset"],
};
const HIT_CAP = 8; // 铁律⑦

// ── spawn 契约 env 表(本表 = spawn 契约 env 面唯一详述点;P2 Python 桥/P5 runbook 从此读)──
// phase:import-time=模块装载期读一次(spawn 时注入即冻结,进程内改无效);call-time=调用期逐次读。
// 双向对拍钉死(selftest-contract.mjs):表内每项真被读(GH_TOKEN 豁免——gh CLI 自读);每个
// OPS_*|ZAI_*|DOCS_ROOT|PRECEDENTS_DIR|LEDGER_FILE 读取 ∈ 表。PI_BIN/RUN_PI_RAW_OUT 是已退役
// 死引擎的 selftest fixture 面(2026-10-20 T3 删尽,名在活代码已不存在);禁入表断言保留
// 作防复活绊线。
export const SPAWN_CONTRACT_ENV = [
  { name: "DOCS_ROOT", default: "<worktree 根>/docs", consumer: "tools.mjs 模块顶(docs 根,派生包/队列/工件落位)+ lib.sh 落位", phase: "import-time" },
  { name: "PRECEDENTS_DIR", default: "<DOCS_ROOT>/ops/precedents", consumer: "tools.mjs searchPrecedentsCore(判例检索单源,PR #177)+lib.sh(inject_precedents/verify_cited_precedents)", phase: "call-time" },
  { name: "LEDGER_FILE", default: "<DOCS_ROOT>/ops/ledger.md", consumer: "lib.sh(ledger_append)", phase: "call-time" },
  { name: "OPS_MODELS", default: "~/.pi/agent/models.json", consumer: "models.mjs loadModels(用户 models.json 路径)", phase: "call-time" },
  { name: "OPS_MODELS_STORE", default: "~/.pi/agent/models-store.json", consumer: "models.mjs loadModels(models-store 路径)", phase: "call-time" },
  { name: "OPS_AUTH", default: "~/.pi/agent/auth.json", consumer: "models.mjs loadModels(auth.json 路径)", phase: "call-time" },
  { name: "ZAI_CODING_CN_API_KEY", default: "(无存储凭证时的兜底 key)", consumer: "models.mjs envApiKeyAuth(请求期解析;stored credential 优先)", phase: "call-time" },
  { name: "OPS_MODEL_HEALTH", default: "glm-5.3-flash", consumer: "models.mjs resolve(health 轮模型;pipeline TRIAGE/SYNTH 真面同键,#170)", phase: "call-time" },
  { name: "OPS_MODEL_DISCOVER", default: "glm-5.3", consumer: "models.mjs resolve(discover 轮模型;pipeline DEEP 真面同键,#170)", phase: "call-time" },
  { name: "OPS_EVAL_PY", default: "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python", consumer: "tools.mjs(exclusive_probe/matrix 求值 CLI)", phase: "import-time" },
  { name: "OPS_DATA_DIR", default: "/home/huxiao/dev/pi-ip-lookup-tool/backend/data", consumer: "tools.mjs(经 IP_RADAR_DATA_DIR 传导给 _eval)", phase: "import-time" },
  { name: "OPS_FETCH_MAX_BYTES", default: "524288", consumer: "tools.mjs(fetch_url 响应上限)", phase: "import-time" },
  { name: "OPS_PROBE_MAX_BYTES", default: "268435456", consumer: "tools.mjs(探针下载上限)", phase: "import-time" },
  // OPS_PROBE_MAX_KEYS:任务书规格 §7 清单漏列,tools.mjs B.probeMaxKeys 实读——对拍不变式
  // (每个 OPS_* 读取 ∈ 表)要求闭包补入,随本任务 commit 记偏离待 review。
  { name: "OPS_PROBE_MAX_KEYS", default: "1000000", consumer: "tools.mjs(探针键量上限;bitwire OOM 判例)", phase: "import-time" },
  { name: "OPS_PROBE_CLI_TIMEOUT_MS", default: "1800000", consumer: "tools.mjs(探针 CLI 超时)", phase: "import-time" },
  { name: "OPS_MATRIX_TIMEOUT_MS", default: "1200000", consumer: "tools.mjs(matrix 扫描超时)", phase: "import-time" },
  { name: "OPS_ANCHOR_SWEEP_TIMEOUT_MS", default: "300000", consumer: "tools.mjs anchorSweepCli(锚巡检 CLI 超时,#182;19 锚直调 lookup 远轻于 matrix 全扫)", phase: "import-time" },
  // P2 P0 增量(spec #161 §5.2;agent.mjs 本体零行为变化,仅契约面):pipeline.mjs 轮次状态机宿主的 2 名。
  // OPS_PIPELINE=迁移/回滚开关:legacy(缺省)=现状 agent.mjs 单轮路径;pipeline=状态机路径。
  // P2 起 _ops_rounds 桥消费它选路径;P0 未接线,pipeline.mjs 仅校验值闭集并记入 state.json。
  { name: "OPS_PIPELINE", default: "legacy", consumer: "pipeline.mjs mkCtx(值闭集校验+state.json 记录;P2 起为桥的路径开关)", phase: "call-time" },
  { name: "OPS_PIPELINE_BUDGET_CNY", default: "0.05", consumer: "pipeline.mjs(DISPATCH 轮内预算门,G_DISPATCH 合计上限;月度累计门=P5 IDLE)", phase: "call-time" },
  { name: "GH_TOKEN", default: "(gh CLI 自身凭证链)", consumer: "gh CLI(外部自读;tools.mjs 不读,对拍豁免)", phase: "call-time" },
  // PR3a 发现通道 web_search 引擎 = pi-web-access MCP(2026-10-24 用户令;pin 0.44.0):
  // 两名均外部自读(包/子进程,tools.mjs 不读,同 GH_TOKEN 豁免型)。
  { name: "JINA_API_KEY", default: "(无:未配则 jina 不入回退链,duckduckgo 起步)", consumer: "pi-web-access 包(外部自读;jina provider 可用性门)", phase: "call-time" },
  { name: "PI_CODING_AGENT_DIR", default: "~/.pi/agent", consumer: "pi-web-access 包(外部自读;web-search.json 路由配置指路,_round_env 物化进 ops 树)", phase: "call-time" },
];

// 轮次信封失败面 error.code 闭集九词(规格 §4):已知 throw 点挂 err.code,main 边界对
// 无 code/闭集外 code(如 fs 的 ENOENT)归 infra——信封面九词恒闭。
// 2026-10-24 下沉 error-codes.mjs 单一真源并 re-export:pipeline.mjs 原静态 import 本文件
// 取此常量,而 main 的 OPS_PIPELINE=pipeline 委派路径动态 import pipeline.mjs——ESM 顶层
// await 死锁(本文件尾顶层 await 未决 → pipeline 静态依赖等本文件完成 → 环),事件循环
// 空转,Node 报 unsettled top-level await 退出 13、stdout 无信封。详见 error-codes.mjs 头注。
import { ERROR_CODES } from "./error-codes.mjs";
export { ERROR_CODES };

// bash 复用 lib.sh(verify_cited_precedents/ledger_append/sandbox_assert;inject_precedents
// 已退役为 pipeline/steps.mjs 专用,agent 面判例预注入走 tools.mjs searchPrecedentsCore 同源);
// env 参数 = main 注入的 io.env(缺省 process.env),fixture/契约 env 经此传导给 lib.sh 子进程
const runLib = (fn, args = [], timeoutMs = 120_000, env = process.env) => execFileP("bash",
  ["-c", `. "$0"; ${fn} "$@"`, path.join(AGENT_DIR, "lib.sh"), ...args],
  { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...env } });

// ── stderr 进度行工具面摘要表(票 #142;闭集 8 工具逐一,未列名=零摘要「宁少算」)──
// 参数摘要回答「在查什么」;完成行读数回答「查到什么」。只做呈现摘取,不裁决不缩料。
const urlHost = (u) => { try { return new URL(u).hostname; } catch { return u; } };
const TOOL_ARG_SUMMARY = {
  health_snapshot: () => "",
  search_precedents: (a) => (a.keywords ?? []).join(" "),
  read_file: (a) => [a.path, a.pattern ? `pattern=${a.pattern}` : ""].filter(Boolean).join(" "),
  fetch_url: (a) => `${a.method ?? "HEAD"} ${a.url}`,
  gh_search: (a) => `${a.kind} "${a.query}"${a.limit ? ` limit=${a.limit}` : ""}`,
  exclusive_probe: (a) => [urlHost(a.url), a.seed != null ? `seed=${a.seed}` : ""].filter(Boolean).join(" "),
  matrix_scan_summary: () => "",
  queue_action: (a) => `${a.action} ${a.source}`,
};
const TOOL_RESULT_SUMMARY = {
  health_snapshot: (sc) => `frozen=${sc.frozen_n} unreachable=${sc.unreachable_n} matrix_exit=${sc.matrix_exit_code}`,
  search_precedents: (sc) => `hits=${sc.hit_n}${sc.truncated ? "+" : ""}`,
  read_file: (sc) => `lines=${sc.lines_n} bytes=${sc.bytes_n}`,
  fetch_url: (sc) => `status=${sc.status} age_days=${sc.age_days ?? "null"}`,
  gh_search: (sc) => `total=${sc.total}`,
  exclusive_probe: (sc) => `rate=${sc.exclusive_rate} control_pass=${sc.control_pass}`,
  matrix_scan_summary: (sc) => `exit_code=${sc.exit_code} violation=${sc.violation_n}`,
  queue_action: (sc) => `${sc.action} ${sc.source}${sc.dedup ? " dedup" : ""}`,
};

export async function runRound(round, input, extraKws = [], opts = {}) {
  if (!(round in KWS)) throw Object.assign(new Error(`轮次必须是 health|discover,得到:${round}`), { code: "bad_round" });
  const childEnv = opts.env ?? process.env; // main io.env 注入(契约 env 面 → lib.sh 子进程)
  // stderr 进度行入契约:语法见模块头 spawn 契约段([turn]/[tool]+参数摘要/[tool-result])。
  const log = (...a) => (opts.stderr ?? process.stderr).write(a.join(" ") + "\n");
  const host = new ToolHost(round);
  const { models, resolve } = opts.models ?? await loadModels();
  for (const seed of opts.registrySeed ?? []) host.registry.register(seed.id, seed.tool, seed.sc);
  const model = resolve(round);
  const systemPrompt = fs.readFileSync(path.join(AGENT_DIR, "prompts", `${round}-system.md`), "utf8");

  // 判例预注入(rg 词法);PR #177 起与 search_precedents 工具同源 = tools.mjs
  // searchPrecedentsCore(单源;两路输出 golden 字节等价由 selftest-t4 钉死;失败面
  // 分类信封 channel_missing/transient/rg_infra 而非 lib.sh 吞 stderr 形);命中>8
  // 截前 8(铁律⑦),全部进闭集
  const kws = [...KWS[round], ...extraKws];
  const inj = await searchPrecedentsCore(kws, { env: childEnv });
  const hitNames = inj.files.map((f) => path.basename(f));
  const truncated = hitNames.length > HIT_CAP;
  const injected = hitNames.slice(0, HIT_CAP);
  const injectBlock = truncated
    ? inj.block.split("\n").filter((l) => !/^- 202/.test(l) || injected.includes(l.slice(2).trim())).join("\n")
      + `\n(命中 ${hitNames.length} 条,注入前 ${HIT_CAP} 条——铁律⑦检索深度上限)`
    : inj.block;

  const agent = new Agent({
    initialState: { systemPrompt, model, tools: host.tools },
    streamFn: models.streamSimple.bind(models),
    beforeToolCall: (ctx) => host.beforeToolCall(ctx),
  });

  const usage = { input: 0, output: 0, totalTokens: 0, cost: 0, turns: 0 };
  const toolCalls = [];
  agent.subscribe((event) => {
    if (event.type === "message_end" && event.message?.role === "assistant") {
      const u = event.message.usage ?? {};
      usage.input += u.input ?? 0; usage.output += u.output ?? 0;
      usage.totalTokens += u.totalTokens ?? 0; usage.cost += u.cost?.total ?? 0;
      usage.turns += 1;
      log(`[turn ${usage.turns}] stopReason=${event.message.stopReason ?? "?"} usage(in=${u.input ?? 0} out=${u.output ?? 0})`);
    } else if (event.type === "tool_execution_start") {
      toolCalls.push(event.toolName);
      const sum = TOOL_ARG_SUMMARY[event.toolName]?.(event.args ?? {});
      log(`[tool] ${event.toolName}(${event.toolCallId})${sum ? ` ${sum}` : ""}`);
    } else if (event.type === "tool_execution_end") {
      // 完成行(票 #142):失败信封(ok:false)带 code,成功带关键读数;读数缺字段如实缺省
      const sc = event.result?.structuredContent;
      if (sc && sc.ok === false) {
        log(`[tool-result] ${event.toolName}(${event.toolCallId}) fail code=${sc.code ?? "unknown"}`);
      } else {
        const read = sc ? TOOL_RESULT_SUMMARY[event.toolName]?.(sc) : undefined;
        log(`[tool-result] ${event.toolName}(${event.toolCallId}) ok${read ? ` ${read}` : ""}`);
      }
    }
  });

  const userMsg = `${injectBlock.trim()}

# 本轮输入

${input}`;
  await agent.prompt(userMsg);

  // 最终文本 + 失败面(stopReason error/aborted / 空文本 = 轮次失败,不产包)
  const assistant = [...agent.state.messages].reverse().find((m) => m.role === "assistant");
  if (!assistant) throw Object.assign(new Error("事件流无 assistant 消息"), { code: "empty_text" });
  if (assistant.stopReason === "error" || assistant.stopReason === "aborted") {
    throw Object.assign(new Error(`模型失败面 stopReason=${assistant.stopReason}:${assistant.errorMessage ?? ""}`), { code: "model_face" });
  }
  const finalText = (assistant.content ?? []).filter((c) => c.type === "text").map((c) => c.text).join("\n").trim();
  if (!finalText) throw Object.assign(new Error("最终文本为空"), { code: "empty_text" });

  // 零内建工具证明:全部工具调用 ∈ 本轮领域工具面
  const domainNames = new Set(host.tools.map((t) => t.name));
  const foreign = [...new Set(toolCalls.filter((n) => !domainNames.has(n)))];
  if (foreign.length) throw Object.assign(new Error(`越界工具调用(结构性红线破口):${foreign.join(",")}`), { code: "foreign_tool" });

  // ── host 收口四件 ──
  const stamp = new Date();
  const p2 = (x) => String(x).padStart(2, "0");
  const pkgName = `${stamp.getFullYear()}-${p2(stamp.getMonth() + 1)}-${p2(stamp.getDate())}-${round}-${p2(stamp.getHours())}${p2(stamp.getMinutes())}.md`;
  fs.mkdirSync(PACKAGES_DIR, { recursive: true });
  const pkg = path.join(PACKAGES_DIR, pkgName);
  const toolCounts = Object.entries(toolCalls.reduce((a, n) => ({ ...a, [n]: (a[n] ?? 0) + 1 }), {}));
  const footer = `
---

## 轮次宿主记录(host 追加,不经模型)

- round: ${round} / model: ${model.id}
- usage: in=${usage.input} out=${usage.output} total=${usage.totalTokens} cost=${usage.cost.toFixed(8)}(assistant ${usage.turns} 回合求和,provider 实报)
- tool calls: ${toolCounts.map(([n, c]) => `${n}×${c}`).join(" ") || "(无)"}
- 零内建工具证明: 本轮全部工具调用 ∈ 领域工具面 {${[...domainNames].join(",")}}
- 判例闭集: 预注入 ${injected.length}${truncated ? `(截自命中 ${hitNames.length})` : ""} ∪ 检索命中 ${host.searchHits.size}
- 工件: ${host.artifacts.join(" ") || "(无)"}
- 队列动作: ${host.queueWrites.length ? host.queueWrites.map((q) => `${q.action}:${q.source}${q.dedup ? "(去重)" : ""}`).join(" ") : "无"}
`;
  fs.writeFileSync(pkg, `${finalText}\n${footer}`);

  // 台账先于校验(九裁决 9 每轮记账:校验失败的轮次也花真钱,用量必须入账;序承 T2 轮次 runner,史档 git 历史)
  const usageStr = `in=${usage.input} out=${usage.output} total=${usage.totalTokens} cost=${usage.cost.toFixed(8)}`;
  const note = `tools=${toolCalls.length}${host.queueWrites.length ? ` queue=${host.queueWrites.length}` : ""} sdk=pi-agent-core`;
  let verifyOut = "";
  // 落盘后收口(规格 §3:轮次失败≠工件灭失):此处任何失败在错误上带 pkg,失败信封仅此条件回传工件
  try {
    try {
      await runLib("ledger_append", [round, model.id, usageStr, note], 120_000, childEnv);
    } catch (e) { throw Object.assign(e, { code: "ledger_failed" }); }

    let verify;
    try {
      verify = await runLib("verify_cited_precedents", [pkg], 120_000, childEnv); // 存在性(lib.sh)
    } catch (e) { throw Object.assign(e, { code: "verify_failed" }); }
    verifyOut = verify.stdout.trim();

    // 闭集活时并集(评审 P1 修正):host.searchHits 由轮中 search_precedents execute 填充,
    // agent.prompt() 前必空——并集必须在收口时重建,否则轮中合法命中引用在包+台账落盘后被误杀。
    // 两侧同形(basename):预注入名(lib.sh 输出 basename)basename 化,searchHits 即 basename。
    try {
      closureCheck(finalText, new Set([...hitNames.map((h) => path.basename(h)), ...host.searchHits])); // 闭集成员(铁律④);违 = 抛错轮次失败
    } catch (e) { throw Object.assign(e, { code: "closure_check" }); }

    try {
      await runLib("sandbox_assert", [], 60_000, childEnv);
    } catch (e) { throw Object.assign(e, { code: "sandbox_violation" }); }
  } catch (e) {
    if (e && typeof e === "object" && e.pkg === undefined) e.pkg = pkg;
    throw e;
  }

  // verify_cited:从 verify_cited_precedents 的 stdout 消息解析条数(规格 §2;「无判例」通过时无消息=0)
  const verifyCited = Number((verifyOut.match(/(\d+) 条判例路径全部存在/) ?? [])[1] ?? 0);
  return { pkg, usage: usageStr,
    usage_num: { input: usage.input, output: usage.output, totalTokens: usage.totalTokens, cost: +usage.cost.toFixed(8) },
    toolCalls, queueWrites: host.queueWrites, verify: verifyOut, verify_cited: verifyCited,
    registry: [...host.registry.byCall].map(([id, r]) => ({ id, tool: r.tool, sc: r.sc })) };
}

// ── 轮次信封序列化(GLOSSARY「轮次信封」锚点;成功/失败同形,stdout 单行 JSON+末尾换行)──
function successEnvelope(round, r) {
  return {
    ok: true, round, pkg: r.pkg, usage: r.usage_num,
    queue_writes: r.queueWrites.map((q) => ({ action: q.action, source: q.source, dedup: q.dedup })), // 完整信封裁三字段(规格 §2)
    verify: { ok: true, cited: r.verify_cited },
  };
}
function failureEnvelope(round, e) {
  const code = e && typeof e === "object" && ERROR_CODES.includes(e.code) ? e.code : "infra"; // 无 code/闭集外归兜底
  const envelope = { ok: false, round, error: { code, message: e?.message ?? String(e) } }; // message 保持原文,不裁不改
  if (e && typeof e === "object" && typeof e.pkg === "string") envelope.pkg = e.pkg; // 仅当包已落盘(轮次失败≠工件灭失)
  return envelope;
}

// main(argv, io) — 可测入口(规格 §5):io={env,stdout,stderr,models} 缺省绑 process;
// io.models = runRound 的 opts.models(golden faux 同型);返回退出码 0/1/2(不自己 exit,bin adapter 负责)。
export async function main(argv, io = {}) {
  const env = io.env ?? process.env;
  const stdout = io.stdout ?? process.stdout;
  const stderr = io.stderr ?? process.stderr;
  const log = (...a) => stderr.write(a.join(" ") + "\n");
  const [round, input, ...extra] = argv;
  // OPS_PIPELINE=pipeline 灰度开关(P5 #167 终检;agent.mjs SPAWN_CONTRACT_ENV 表同名项的
  // 消费点):health 轮委派 pipeline.mjs 状态机路径;缺省/legacy=本文件现状路径零变化;
  // discover 恒走 legacy(其自有管线表未立项,C稿 §5.2)。argv 透传 <round> <input>
  // (pipeline.mjs 忽略 input——其轮次自持输入面);退出码/信封契约两路同形。
  if ((env.OPS_PIPELINE ?? "legacy") === "pipeline" && round === "health") {
    const { main: pipelineMain } = await import("./pipeline.mjs");
    return pipelineMain([round, input, ...extra], { env, stdout, stderr });
  }
  if (!round || input === undefined) { // 用法错:纯 stderr + exit 2,不发 JSON(机器契约只覆盖真轮次)
    log('用法: node ops/agent/agent.mjs <health|discover> "<本轮输入>" [追加判例检索词...]');
    return 2;
  }
  let r;
  try {
    r = await runRound(round, input, extra, { models: io.models, env, stderr });
  } catch (e) {
    log(`round 失败:${e.message}`);
    stdout.write(JSON.stringify(failureEnvelope(round, e)) + "\n");
    return 1;
  }
  log(`round: ${round} 完成 → ${r.pkg}`); // 此前的 stdout 散文全移 stderr,格式逐字保持(规格 §6)
  log(`usage: ${r.usage}`);
  log(r.verify);
  stdout.write(JSON.stringify(successEnvelope(round, r)) + "\n");
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // 薄 adapter(规格 §5):绑 process 面。用 exitCode 而非 process.exit——管道下 stdout 单行
  // JSON 是异步写,process.exit 会截断在飞数据(机器契约必须完整落管,P2 从管道读)。
  process.exitCode = await main(process.argv.slice(2));
}
