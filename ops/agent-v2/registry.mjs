// registry.mjs — v2 应用注册表(票 #225;spec 定案 6:框架调用面收薄适配层,
// 升级 pi-durable 只动 entry/registry/tasks 定义文件)。
//
// ops 红线:不安装内建 CodingTools。pi-durable 的 tools 子入口
// (`createCodingTools()`/read/write/edit/bash 扩展面)不会自动安装,本文件也
// 一概不装——v2 是无人值守运营管线,模型不得获代码执行面。
//
// 扩展面(T3 #227 + T4 #228 并批合并,并集解):
//   "ops"               — 轮次任务(T3 发现轮 + T4 健康轮)+ T4 微探针三只
//                          (reprobe_get/reprobe_ua/upstream_check,均 replay:unsafe;
//                          仅健康轮真 DEEP 面经 AgentChange.modelTools 选装——
//                          会话未存选装名单时缺省=全部已装,选装必须显式)
//   "ops-discover-tools"— 发现轮三只只读通道工具(web_read/web_search/rss_parse;
//                          仅发现轮自有会话选装(tasks/discover-round.mjs
//                          createConversationViaTx extensions 白名单);root/骨架
//                          会话不选装=零工具面,tests/scaffold.test.mjs 钉基线。
//                          会话未存选装名单时缺省=全部已装(agent.js selectExtensions),
//                          选装必须显式,见 entry.mjs)。
import { createRegistry, defineExtension } from "@earendil-works/pi-durable";
import { TASKS } from "./tasks/index.mjs";
import { OPS_PROBE_TOOLS } from "./tools/probes.mjs";
import { discoveryTools } from "./tools/discovery-tools.mjs";

// 发现轮工具闭集扩展(票 #227;replay 声明见 tools/discovery-tools.mjs)。
// 导出真身:轮启动器(run-discover.mjs)创建轮会话时经 AgentChange.extensions 选中它。
export const DISCOVER_TOOLS_EXTENSION = defineExtension({ name: "ops-discover-tools", tools: discoveryTools() });

export function buildRegistry() {
  const registry = createRegistry(); // 只含内建三任务(generation/tool/compaction)
  registry.install(defineExtension({ name: "ops", tasks: [...TASKS], tools: [...OPS_PROBE_TOOLS] })); // T4:微探针闭集随 ops 扩展(仅真 DEEP 面选装)
  registry.install(DISCOVER_TOOLS_EXTENSION); // T3:发现轮通道工具独立扩展(会话选装面)
  return registry;
}
