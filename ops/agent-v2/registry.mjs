// registry.mjs — v2 应用注册表(票 #225;spec 定案 6:框架调用面收薄适配层,
// 升级 pi-durable 只动 entry/registry/tasks 定义文件)。
//
// ops 红线:不安装内建 CodingTools。pi-durable 的 tools 子入口
// (`createCodingTools()`/read/write/edit/bash 扩展面)不会自动安装,本文件也
// 一概不装——v2 是无人值守运营管线,模型不得获代码执行面;领域工具闭集=
// T4(#228)微探针三只(reprobe_get/reprobe_ua/upstream_check,均 replay:unsafe),
// T3 通道工具(fetch_url/gh_search/…)后续同扩展接入。tests/scaffold 钉死闭集。
import { createRegistry, defineExtension } from "@earendil-works/pi-durable";
import { TASKS } from "./tasks/index.mjs";
import { OPS_PROBE_TOOLS } from "./tools/probes.mjs";

export function buildRegistry() {
  const registry = createRegistry(); // 只含内建三任务(generation/tool/compaction)
  registry.install(defineExtension({ name: "ops", tasks: [...TASKS], tools: [...OPS_PROBE_TOOLS] }));
  return registry;
}
