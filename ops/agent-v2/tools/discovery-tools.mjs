// tools/discovery-tools.mjs — 发现轮 web 三工具 defineTool 化(票 #227;#217 T3.5 接线面
// 的 v2 承接;spec docs/superpowers/specs/2026-10-28-ops-agent-pidurable-migration-design.md
// 定案 6 薄适配层)。
// 零复制律:工具实现/守卫链/熔断写侧/种子登记全部经旧管线 discovery-host.mjs 的
// mkDiscoveryHost 复用——真网络/解析/信封(dup→breaker→cap 同序同义)、breaker.record
// (五通道写侧,2026-10-28 steer:写侧随迁归 T3)、channelCounts、seeds 一概不 fork。
// 本文件只做两件事:①轮级宿主按 conversation 缓存(同轮 SHORTLIST 模型面与 MEASURE
// 宿主补发共用同一守卫链同配额面——旧 ctx.discoverHost 单例律的 v2 等价);②把宿主
// 工具适配成 pi-durable ToolRegistration(defineTool),挂 "ops-discover-tools" 扩展
// 进 registry(registry.mjs;仅发现轮会话选装,root/健康轮面不选——见 tasks/discover-round.mjs)。
//
// replay 声明逐工具裁(t1-notes 风险13;缺省 unsafe 是安全侧,逐个升格):
//   web_read  = "safe"  纯读 GET(r.jina.ai 无鉴权无计费,实测 2026-10-24 裸调用可用);
//                        崩溃重放至多补发一次,守卫链在重放路径同样执行(每轮帽+dup 拦截兜);
//                        重放读数=新鲜证据,无副作用面。
//   web_search= "unsafe" 重查询烧 provider 配额(duckduckgo/jina 回退链限速;ADR 0010:
//                        配额是发现侧第一现实约束),且结果非确定——崩溃交 interrupted
//                        结构化错误信封(铁律②),宁少算不重烧。
//   rss_parse = "safe"  纯读 GET 原始 feed + 本地零依赖解析,无副作用,同 web_read 律。
// (fetch_url/gh_search 属旧 legacy discover 聊天面通道,不在发现轮管线工具闭集
//  (discovery-host.mjs DISCOVERY_TOOLS;gh_search 留 legacy 面=spec T3 明示),T3 不装;
//  若后续票接它们进 v2,同一 mkBreaker seam 照用,写侧律不变。)
//
// registry 红线(票 #225 判例):不装内建 CodingTools——本扩展只含上述三只自有领域工具,
// 全只读(annotations.readOnlyHint),模型无 bash/write/edit 面。
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "@earendil-works/pi-ai";
import fs from "node:fs";
import path from "node:path";
import {
  DISCOVERY_TOOLS,
  ensureDiscoverHost,
  fixtureDiscoveryMethods,
} from "../../agent/pipeline/discovery-host.mjs"; // 零复制真源(实现+守卫链+熔断写侧+种子)
import { parseRss } from "../../agent/tools/discovery.mjs"; // 形状钉子:parameters schema 与旧面同构(见下)

// replay 声明单源(报告清单与 tests/discover-round.test.mjs 断言同源引用本表)
export const DISCOVERY_REPLAY = Object.freeze({ web_read: "safe", web_search: "unsafe", rss_parse: "safe" });

// 轮级宿主缓存:key=conversationId(=发现轮自有会话,一轮一会话——月轮↔conversation
// 粒度决策见 tasks/discover-round.mjs 头注)。进程内缓存;崩溃 resume 后宿主缺席=常态
// (旧管线同律:dupRegistry/已用配额从零计,宁少算;CLOSE 读数走工件回放)。
export const roundHosts = new Map();
// 轮级 dup 登记表缓存(同键):旧 ctx.dupRegistry 轮内单例律的 v2 等价——相位问 ctx 每
// 次重建,登记表必须跨相位同对象(CLOSE dup_top3 读数才不空;旧 mkCtx 同律)。
export const roundDupRegistries = new Map();

// 取/建轮级发现宿主:首轮(SHORTLIST 相位)创建并写回 ctx.discoverHost——旧
// ensureDiscoverHost 见 ctx.discoverHost 在场即原样返回,MEASURE(runStage 驱动旧步)
// 因此与模型面共用同一实例/守卫链/配额。faux 面=罐装方法(measure.json web_reads 表,
// 零网络律);真面=discoveryMethods 真网络。breaker 写侧:mkDiscoveryHost 适配器 finish
// 内 breaker.record(ops/breaker.json,breakerFileOf(ctx) 同文件)——零复制随迁。
export function ensureRoundHost(ctx, conversationId) {
  ctx.dupRegistry = roundDupRegistries.get(conversationId) ?? (roundDupRegistries.set(conversationId, new Map()).get(conversationId)); // 先立同轮登记表(host 守卫链捕获同对象)
  if (roundHosts.has(conversationId)) {
    ctx.discoverHost = roundHosts.get(conversationId);
    return ctx.discoverHost;
  }
  const fauxFace = ctx.modelFace === "faux" && typeof ctx.fixturesDir === "string";
  const host = ensureDiscoverHost(ctx, fauxFace
    ? { methods: fixtureDiscoveryMethods(readFixtureMeasure(ctx.fixturesDir)) }
    : {});
  roundHosts.set(conversationId, host);
  return host;
}

function readFixtureMeasure(fixturesDir) { // faux 罐装读数(缺件=空表→全 io_error 未罐装,同旧 MEASURE 缝)
  try { return JSON.parse(fs.readFileSync(path.join(fixturesDir, "measure.json"), "utf8")); } catch { return {}; }
}

// 宿主工具直调核(defineTool execute 与测试共用;callId 上翻=宿主 content 前缀同旧律:
// 模型看不到运行时 id,evidence 回引靠 [call_id=…] 前缀)。守卫链/登记/熔断写侧全在
// 宿主 wrap 内(零复制),本核不做任何拦截。
export async function executeDiscoveryTool(host, name, callId, args) {
  const tool = host.tools.find((t) => t.name === name);
  if (!tool) throw new Error(`未知工具 ${name}(发现宿主闭集:${DISCOVERY_TOOLS.join("/")})`);
  const r = await tool.execute(callId, args);
  return r; // {content:[{type:"text",text}], structuredContent}——旧信封形状原样
}

// 三只 defineTool(挂 registry "ops-discover-tools" 扩展;仅发现轮会话选装)。
// parameters/annotations/description 元数据与旧宿主工具同构(闭集三只,形状漂移=对拍红)。
export function discoveryTools() {
  const proto = DISCOVERY_TOOLS.map((n) => ({ name: n })); // 顺序=DISCOVERY_TOOLS 闭集序
  return proto.map(({ name }) => defineTool({
    name,
    label: `ops 发现轮 ${name}`,
    description: `发现轮只读通道工具 ${name}(实现零复制自旧管线 ops/agent/tools/discovery.mjs;同参重复拦截/通道熔断/每轮上限守卫链;失败=结构化信封 {ok:false,code,reason},非 isError——信封即契约读数)`,
    annotations: { readOnlyHint: true, idempotentHint: name !== "web_search", openWorldHint: true },
    parameters: Type.Object({ url: Type.Optional(Type.String({ pattern: "^https?://", maxLength: 500 })), query: Type.Optional(Type.String({ maxLength: 500 })) }),
    replay: DISCOVERY_REPLAY[name], // 逐工具声明(头注裁语);缺省本就是 unsafe,显式写出=报告与断言可对拍
    execute: async (args, api, context) => {
      const host = roundHosts.get(api.conversationId);
      // stderr 进度行(票 #142 语法,T5 冻结;ENVELOPE.md 契约面):[tool] 参数摘要 + [tool-result] 完成行
      const argSum = [args.url, args.query].filter(Boolean).join(" ").slice(0, 120);
      process.stderr.write(`[tool] ${name}(${api.callId}) ${argSum}\n`);
      if (!host) {
        process.stderr.write(`[tool-result] ${name}(${api.callId}) fail code=channel_open\n`);
        return { output: [{ type: "text", text: `[call_id=${api.callId}] 拒绝信封(code=channel_open):发现宿主未就绪(会话 ${api.conversationId} 无轮级宿主——SHORTLIST 相位先建宿主再提交)` }], structuredContent: { ok: false, code: "channel_open", reason: "发现宿主未就绪" } };
      }
      const r = await executeDiscoveryTool(host, name, api.callId, args);
      const sc = r.structuredContent ?? {};
      const okSum = name === "web_search" ? `total=${sc.total ?? "?"}` : name === "rss_parse" ? `entries=${sc.entries_n ?? sc.n ?? "?"}` : `bytes=${sc.bytes ?? "?"}`;
      process.stderr.write(sc.ok === false
        ? `[tool-result] ${name}(${api.callId}) fail code=${sc.code}\n`
        : `[tool-result] ${name}(${api.callId}) ok ${okSum}\n`);
      return { output: r.content, structuredOutput: r.structuredContent };
    },
  }));
}

// 形状哨(测试消费):rss_parse 依赖的解析核与旧面同引用(防 v2 侧私 fork 漂移)。
export { parseRss };
