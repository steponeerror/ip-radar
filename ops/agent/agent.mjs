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
import fs from "node:fs";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { Agent } from "@earendil-works/pi-agent-core";
import { loadModels } from "./models.mjs";
import { ToolHost, DOCS_ROOT, closureCheck } from "./tools.mjs";

const execFileP = promisify(execFileCb);
const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PACKAGES_DIR = path.join(DOCS_ROOT, "ops/packages");
const KWS = {
  health: ["冻结", "死键", "不可达", "违例"],
  discover: ["排他率", "聚合器", "许可", "体量", "冻结", "sunset"],
};
const HIT_CAP = 8; // 铁律⑦

const log = (...a) => process.stderr.write(a.join(" ") + "\n");
// bash 复用 lib.sh(inject_precedents/verify_cited_precedents/ledger_append/sandbox_assert)
const runLib = (fn, args = [], timeoutMs = 120_000) => execFileP("bash",
  ["-c", `. "$0"; ${fn} "$@"`, path.join(AGENT_DIR, "lib.sh"), ...args],
  { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...process.env } });

export async function runRound(round, input, extraKws = [], opts = {}) {
  if (!(round in KWS)) throw new Error(`轮次必须是 health|discover,得到:${round}`);
  const host = new ToolHost(round);
  const { models, resolve } = opts.models ?? await loadModels();
  for (const seed of opts.registrySeed ?? []) host.registry.register(seed.id, seed.tool, seed.sc);
  const model = resolve(round);
  const systemPrompt = fs.readFileSync(path.join(AGENT_DIR, "prompts", `${round}-system.md`), "utf8");

  // 判例预注入(rg 词法,lib.sh 复用);命中>8 截前 8(铁律⑦),全部进闭集
  const kws = [...KWS[round], ...extraKws];
  const inj = await runLib("inject_precedents", kws);
  const hitNames = [...inj.stdout.matchAll(/^- ([0-9]{4}-[0-9]{2}-[0-9]{2}-[^\s]+\.md)\s*$/gm)].map((m) => m[1]);
  const truncated = hitNames.length > HIT_CAP;
  const injected = hitNames.slice(0, HIT_CAP);
  const allowed = new Set([...hitNames.map((h) => path.basename(h)), ...host.searchHits]);
  const injectBlock = truncated
    ? inj.stdout.split("\n").filter((l) => !/^- 202/.test(l) || injected.includes(l.slice(2).trim())).join("\n")
      + `\n(命中 ${hitNames.length} 条,注入前 ${HIT_CAP} 条——铁律⑦检索深度上限)`
    : inj.stdout;

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
      log(`[tool] ${event.toolName}(${event.toolCallId})`);
    }
  });

  const userMsg = `${injectBlock.trim()}

# 本轮输入

${input}`;
  await agent.prompt(userMsg);

  // 最终文本 + 失败面(stopReason error/aborted / 空文本 = 轮次失败,不产包)
  const assistant = [...agent.state.messages].reverse().find((m) => m.role === "assistant");
  if (!assistant) throw new Error("事件流无 assistant 消息");
  if (assistant.stopReason === "error" || assistant.stopReason === "aborted") {
    throw new Error(`模型失败面 stopReason=${assistant.stopReason}:${assistant.errorMessage ?? ""}`);
  }
  const finalText = (assistant.content ?? []).filter((c) => c.type === "text").map((c) => c.text).join("\n").trim();
  if (!finalText) throw new Error("最终文本为空");

  // 零内建工具证明:全部工具调用 ∈ 本轮领域工具面
  const domainNames = new Set(host.tools.map((t) => t.name));
  const foreign = [...new Set(toolCalls.filter((n) => !domainNames.has(n)))];
  if (foreign.length) throw new Error(`越界工具调用(结构性红线破口):${foreign.join(",")}`);

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

  // 台账先于校验(九裁决 9 每轮记账:校验失败的轮次也花真钱,用量必须入账;T2 round.sh 同序)
  const usageStr = `in=${usage.input} out=${usage.output} total=${usage.totalTokens} cost=${usage.cost.toFixed(8)}`;
  const note = `tools=${toolCalls.length}${host.queueWrites.length ? ` queue=${host.queueWrites.length}` : ""} sdk=pi-agent-core`;
  await runLib("ledger_append", [round, model.id, usageStr, note]);

  const verify = await runLib("verify_cited_precedents", [pkg]); // 存在性(lib.sh)
  closureCheck(finalText, allowed); // 闭集成员(铁律④);违 = 抛错轮次失败
  await runLib("sandbox_assert", [], 60_000);
  return { pkg, usage: usageStr, toolCalls, queueWrites: host.queueWrites, verify: verify.stdout.trim(),
    registry: [...host.registry.byCall].map(([id, r]) => ({ id, tool: r.tool, sc: r.sc })) };
}

async function main() {
  const [round, input, ...extra] = process.argv.slice(2);
  if (!round || input === undefined) {
    console.error('用法: node ops/agent/agent.mjs <health|discover> "<本轮输入>" [追加判例检索词...]');
    process.exit(2);
  }
  try {
    const r = await runRound(round, input, extra);
    console.log(`round: ${round} 完成 → ${r.pkg}`);
    console.log(`usage: ${r.usage}`);
    console.log(`${r.verify}`);
  } catch (e) {
    console.error(`round 失败:${e.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
