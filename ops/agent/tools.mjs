// tools.mjs — 融合领域工具面门面+注册编排(票 #195 C6:单体按面分层至 tools/*.mjs,
// 行为零变化)。本文件=ToolHost 宿主(注册表/预算/写前语义门/收口);具体工具实现与
// 闭集常量单源在各面文件,公共 API 面(29 名)经本门面 re-export 逐名不变
// (selftest-t4 C6-1 钉死)。11 工具 = discover 10 + health 1;PR3a 发现通道三件并入,
// 2026-10-24 裁定;融合必保 6 条 = tool-critic-1/2 并集;铁律①-⑦ 见各面文件注释。
//
// 结构性红线(铁律⑥):零内建工具——本面只注册下列领域工具,agent 无 bash/write/edit;
// 唯一写口 = queue_action(append-only,恒 vetoable,幂等去重),包/台账/判例写回全在 host。
// 警察函数(校验/沙箱/台账)不注册为工具(被审计者不持审计工具)。
//
// 失败面统一(铁律②):一切失败 = 结构化信封 {ok:false,code,reason},不抛裸栈、不静默;
// 信封禁止入 evidence(语义门拒绝),降级人裁区。硬门数字只认 structuredContent,
// 测量工具恒带 trace{cmd,rc,artifact}(铁律③)。
import path from "node:path";
import { B, DOCS_ROOT, FROZEN_DAYS } from "./tools/shared.mjs";
import { PREDICATES, MEASUREMENT_TOOLS, resolveField, ResultRegistry, registryMethods } from "./tools/registry.mjs";
import { precedentsMethods } from "./tools/precedents.mjs";
import { measurementMethods } from "./tools/measurement.mjs";
import { discoveryMethods } from "./tools/discovery.mjs";

export class ToolHost {
  constructor(round, opts = {}) {
    this.round = round;
    this.registry = new ResultRegistry();
    this.searchHits = new Set();        // search_precedents 命中(闭集成员来源之二)
    this.artifacts = [];                // 本轮落盘工件(host 收口进包脚注)
    this.queueWrites = [];              // 本轮 queue_action 结果(脚注+台账备注)
    this.spent = {};                    // 每轮预算计数
    this.budgets = round === "discover"
      ? { fetch_url: B.fetchPerRound, gh_search: B.ghPerRound, queue_action: B.queuePerRound,
          web_read: B.webReadPerRound, web_search: B.webSearchPerRound, rss_parse: B.rssParsePerRound }
      : { health_snapshot: 2 };
    this.queueFile = opts.queueFile ?? path.join(DOCS_ROOT, "ops/queue.md");
    this.artifactDir = opts.artifactDir ?? path.join(DOCS_ROOT, "ops/artifacts");
    this.tools = round === "health" ? [this.healthSnapshot()] : [
      this.searchPrecedents(), this.readFile(), this.fetchUrl(), this.ghSearch(),
      this.exclusiveProbe(), this.matrixScanSummary(), this.queueAction(),
      this.webRead(), this.webSearch(), this.rssParse(), // 发现通道三件(PR3a;不进 MEASUREMENT_TOOLS)
    ];
  }

  budgetSpend(name) { this.spent[name] = (this.spent[name] ?? 0) + 1; }
  async beforeToolCall({ toolCall, args }) {
    const max = this.budgets[toolCall.name];
    if (max !== undefined && (this.spent[toolCall.name] ?? 0) >= max) {
      return { block: true, reason: `预算超限:${toolCall.name} 每轮上限 ${max} 次已用满;升级人裁区` };
    }
    if (toolCall.name === "queue_action") return this.semanticGate(args);
    return undefined;
  }
  // 写前语义门:host 从本会话 structuredContent 重算谓词,不信 rationale/evidence 复述。
  semanticGate(args) {
    const block = (reason) => ({ block: true, reason });
    if (args?.action === "REJECT" && !PREDICATES.includes(args.predicate)) {
      return block(`REJECT 谓词必须在闭集内:${PREDICATES.join("/")}(缺谓词或不在闭集)`);
    }
    const evs = args?.evidence ?? [];
    if (!evs.length) return block("无 evidence:无实测依据不得入队/拒绝(铁律①;失败信封也不算数)");
    const resolved = [];
    for (const ev of evs) {
      const rec = this.registry.get(ev.call_id);
      if (!rec) return block(`evidence 引用未知调用 ${ev.call_id}:证据只认本会话已完成的测量工具调用,编造即拦`);
      if (!MEASUREMENT_TOOLS.has(rec.tool)) {
        return block(`evidence 引用非测量工具(${rec.tool});测量面 = ${[...MEASUREMENT_TOOLS].join("/")}`);
      }
      if (rec.sc?.ok === false) {
        return block(`evidence ${ev.call_id} 是失败信封(ok:false, code=${rec.sc.code});失败信封禁止入 evidence,降级人裁区(铁律②)`);
      }
      if (!rec.sc || resolveField(rec.sc, ev.field) === undefined) return block(`evidence 字段 ${ev.field} 不在 ${ev.call_id}(${rec.tool})的结构化返回(支持点路径如 results.0.size_kb)`);
      const reg = resolveField(rec.sc, ev.field);
      if (typeof reg !== typeof ev.value || reg !== ev.value) {
        return block(`evidence 值不符:${ev.call_id}.${ev.field} 实测=${JSON.stringify(reg)} 复述=${JSON.stringify(ev.value)}(不信复述,逐字比对)`);
      }
      resolved.push({ ev, rec });
    }
    if (args.action === "ENQUEUE") { // 自动入队条件 = 实测 rate≥0.25 且对照闸过
      const ok = resolved.some(({ rec }) => rec.tool === "exclusive_probe"
        && rec.sc.control_pass === true && typeof rec.sc.exclusive_rate === "number" && rec.sc.exclusive_rate >= 0.25);
      return ok ? undefined : block("ENQUEUE 谓词不成立:无本会话 exclusive_probe 实测 exclusive_rate≥0.25 且对照闸过(自动入队条件)");
    }
    if (args.action === "REJECT") {
      if (args.predicate === "mirror_echo") {
        const probes = resolved.filter(({ rec }) => rec.tool === "exclusive_probe");
        if (!probes.length) return block("overlap-REJECT 无 exclusive_probe 实测一律阻断(判例:无实测不得拒,最多 FLAG)");
        if (!probes.some(({ rec }) => typeof rec.sc.exclusive_rate === "number" && rec.sc.exclusive_rate < 0.25)) {
          return block("overlap-REJECT 与实测矛盾:引用探针排他率均 ≥0.25(高排他非回声,见 threatview/CPS 判例)");
        }
        return undefined;
      }
      if (args.predicate === "sunset_frozen") {
        const fets = resolved.filter(({ rec }) => rec.tool === "fetch_url");
        if (!fets.length) return block("sunset-REJECT 须引用本会话 fetch_url 的 age_days 实测");
        for (const { rec } of fets) {
          if (typeof rec.sc.age_days !== "number") return block("sunset-REJECT:引用中存在无 age_days 的读数(缺 Last-Modified 或不可达);冻结须有数,不可达≠死键");
          if (rec.sc.age_days < FROZEN_DAYS) return block(`sunset-REJECT 与实测矛盾:引用 URL age_days=${rec.sc.age_days} < ${FROZEN_DAYS} 活跃(任一 URL 活跃即不命中)`);
        }
        return undefined;
      }
      if (args.predicate === "zero_asset") {
        const ghs = resolved.filter(({ rec }) => rec.tool === "gh_search");
        if (!ghs.length) return block("zero_asset-REJECT 须引用本会话 gh_search 实测");
        const hit = ghs.some(({ rec }) => rec.sc.kind === "code" && rec.sc.results?.length === 0)
          || ghs.some(({ rec }) => rec.sc.kind === "repos" && rec.sc.results?.length > 0
            && rec.sc.results.every((r) => typeof r.size_kb === "number" && r.size_kb <= B.zeroAssetKb));
        return hit ? undefined : block("zero_asset-REJECT 与实测矛盾:引用 gh_search 无零资产读数(仓体积>${B.zeroAssetKb}KB 或代码检索有命中)");
      }
    }
    return block("action 必须在闭集内:ENQUEUE/REJECT");
  }
  // 工具返回统一走这里:登记 structuredContent(信封也登记——被引时门内识别 ok:false)
  // + 预算计数 + 工件记录。content 前缀 call_id:实测(2026-10-19 discover 重放)模型
  // 看不到运行时生成的调用 id,evidence{call_id} 无从逐字回引——必须把 id 上翻给模型。
  finish(callId, name, structured, contentText, details = {}) {
    this.registry.register(callId, name, structured);
    if (structured?.artifact) this.artifacts.push(structured.artifact);
    if (structured?.artifacts) this.artifacts.push(...structured.artifacts);
    this.budgetSpend(name);
    return { content: [{ type: "text", text: `[call_id=${callId}] ${contentText}` }], details, structuredContent: structured };
  }
}

// 各面工具方法挂 prototype(实现零改动;宿主态 this.finish/registry/artifacts/spent/
// searchHits/round/queueFile/artifactDir 经 this 跨面共享——面文件不互相导入):
Object.assign(ToolHost.prototype, measurementMethods, discoveryMethods, precedentsMethods, registryMethods);

// 公共 API 面 re-export(拆分前 29 名逐名不变,bde7f061 冻结字面;C6-1 钉死):
export { ROOT, DOCS_ROOT, FROZEN_DAYS, RSS_FRESH_DAYS, checkPrivateIp, pinnedLookup, safeFetch } from "./tools/shared.mjs";
export { classifyChannelError, classifyWebStatus, classifyMcpSearchError } from "./tools/envelope.mjs";
export { GH_WRITE_SUBCOMMANDS, checkReadablePath, resolveField, closureCheck, ResultRegistry } from "./tools/registry.mjs";
export { RG_TIMEOUT_MS, resolvePrecedentsDir, fmField, searchPrecedentsCore } from "./tools/precedents.mjs";
export { matrixScanCli, matrixArtifactText, anchorSweepCli, ghIssueCreate, countFeedKeys } from "./tools/measurement.mjs";
export { normalizeJinaRead, parseSerp, parseRss, parseMcpSearchText } from "./tools/discovery.mjs";
