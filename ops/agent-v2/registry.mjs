// registry.mjs — v2 应用注册表(票 #225;spec 定案 6:框架调用面收薄适配层,
// 升级 pi-durable 只动 entry/registry/tasks 定义文件)。
//
// ops 红线:不安装内建 CodingTools。pi-durable 的 tools 子入口
// (`createCodingTools()`/read/write/edit/bash 扩展面)不会自动安装,本文件也
// 一概不装——v2 是无人值守运营管线,模型不得获代码执行面。
//
// 扩展面(票 #227 T3 起):
//   "ops"               — 轮次任务(discover-round 等;仅 root/骨架面选装与否无关——
//                          任务不在会话 tools 面,AgentChange.tools 只能过滤扩展工具)
//   "ops-discover-tools"— 发现轮三只只读通道工具(web_read/web_search/rss_parse;
//                          仅发现轮自有会话选装(tasks/discover-round.mjs
//                          createConversationViaTx extensions 白名单);root/骨架
//                          会话不选装=零工具面,tests/scaffold.test.mjs 钉基线。
import { createRegistry, defineExtension } from "@earendil-works/pi-durable";
import { TASKS } from "./tasks/index.mjs";
import { discoveryTools } from "./tools/discovery-tools.mjs";

// 发现轮工具闭集扩展(票 #227;replay 声明见 tools/discovery-tools.mjs)。
// 导出真身:轮启动器(run-discover.mjs)创建轮会话时经 AgentChange.extensions 选中它
// (agent.js selectExtensions:会话未存选装名单时缺省=全部已装——registry 装了本扩展后,
// 任何未显式选装的会话(含 root)都会静默获得发现轮三工具;选装必须显式,见 entry.mjs)。
export const DISCOVER_TOOLS_EXTENSION = defineExtension({ name: "ops-discover-tools", tools: discoveryTools() });

export function buildRegistry() {
  const registry = createRegistry(); // 只含内建三任务(generation/tool/compaction)
  registry.install(defineExtension({ name: "ops", tasks: [...TASKS] }));
  registry.install(DISCOVER_TOOLS_EXTENSION);
  return registry;
}
