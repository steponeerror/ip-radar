#!/usr/bin/env node
// catalog.mjs — 运营 agent 可装载模型目录 dump(票 #143 动态目录;后端子调用面)。
//
// 用法:node ops/agent/catalog.mjs → stdout 单 JSON:{"<providerId>":
//   [{id,name,cost:{input,output,cacheRead,cacheWrite}|null},…](按 id 排序)},
//   只含有 chat 模型的 provider;exit 0。任何失败 = stderr 一行 + exit 1(不吐
//   半截 JSON,后端整体兜底,绝不静默)。
//
// 契约定位:本脚本不是 spawn 面(SPAWN_CONTRACT_ENV 不辖;桥不 spawn 它,后端
// _ops_config 子调用)。离线铁律:零网络零 API 零 key 消耗——builtin 目录全静态
// (pi-ai README「Dynamic Providers」:静态家 refresh() 无操作),本脚本零
// refresh() 调用;getAuth 也不调(OAuth 家会触网刷新)。
// cost 字段单位 = $/1M tokens(pi-ai Model.cost 原样,README 无单位换算说明,
// 从 zai glm-5.3 input=1.4 实测账单对得上);缺 cost 字段 = null(UI 显「未知」)。
// function-calling 支持标注:pi-ai@1.3.0 模型定义无逐模型 tools 字段(实测
// 2026-10-20 全目录无此键)→ 辨不了,不滤不标,UI 自由选(票面:辨不了就不滤)。
import { loadModels } from "./models.mjs";

try {
  const { models } = await loadModels();
  const dump = {};
  for (const p of models.getProviders()) {
    const entries = models.getModels(p.id) // chat 面(agent 可跑的型)
      .map((m) => ({ id: m.id, name: m.name ?? m.id, cost: m.cost ?? null }))
      .sort((a, b) => a.id.localeCompare(b.id));
    if (entries.length) dump[p.id] = entries;
  }
  process.stdout.write(JSON.stringify(dump));
} catch (e) {
  process.stderr.write(`catalog dump 失败: ${e?.message ?? e}\n`);
  process.exit(1);
}
