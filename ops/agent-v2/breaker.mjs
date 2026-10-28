// breaker.mjs — v2 熔断面零复制 re-export(票 #227;2026-10-28 主会话 steer:
// breaker.json 五通道**写侧**随迁归 T3——发现轮工具 defineTool 化后,通道调用照旧律
// record verdict(成功/失败计通道计数,阈值触发熔断);T4 #228 只接 CLOSE 相位快照
// **读面**,写侧不归它。两票 seam 接口=ops/agent/tools/breaker.mjs 现导出,不自造包装)。
// 零复制判例同 budget.mjs(票 #226):旧文件只依赖 node 内建,直接 re-export,单一真源;
// 写侧执法的实际接线在 tools/discovery-tools.mjs(mkDiscoveryHost 适配器 finish 内
// breaker.record——host 零复制 import 旧管线,record 链随迁即零复制),本 seam 供 v2
// 侧消费方(tasks/golden/tests)与「v2 不 fork 熔断逻辑」的防漂移钉子。
// 旧管线文件属主:ops/agent/ 零改动红线——本文件只 re-export,不 fork。
export * from "../agent/tools/breaker.mjs";
