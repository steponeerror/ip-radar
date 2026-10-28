// registry.mjs — v2 应用注册表(票 #225;spec 定案 6:框架调用面收薄适配层,
// 升级 pi-durable 只动 entry/registry/tasks 定义文件)。
//
// ops 红线:不安装内建 CodingTools。pi-durable 的 tools 子入口
// (`createCodingTools()`/read/write/edit/bash 扩展面)不会自动安装,本文件也
// 一概不装——v2 是无人值守运营管线,模型不得获代码执行面;领域工具
// (fetch_url/gh_search/判例检索等,T3/T4)以 defineTool 定义、挂在下方同一
// "ops" 扩展进入。tests/scaffold.test.mjs 钉死「工具面为空」基线。
import { createRegistry, defineExtension } from "@earendil-works/pi-durable";
import { TASKS } from "./tasks/index.mjs";

export function buildRegistry() {
  const registry = createRegistry(); // 只含内建三任务(generation/tool/compaction)
  registry.install(defineExtension({ name: "ops", tasks: [...TASKS] }));
  return registry;
}
