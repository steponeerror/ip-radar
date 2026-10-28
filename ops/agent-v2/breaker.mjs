// breaker.mjs — v2 熔断面零复制 re-export(票 #227/#228 并批;两票 seam 同源不同面):
// T3(#227)持写侧——发现轮通道工具 defineTool 化后,通道调用照旧律 record verdict
// (成功/失败计通道计数,阈值触发熔断;实际接线=tools/discovery-tools.mjs
// mkDiscoveryHost 适配器 finish 内 breaker.record,host 零复制 import 旧管线);
// T4(#228)只接 CLOSE 相位快照**读面**(readBreakerKnobs→09-budget.json 观察面,
// 只读零写,回声律:不造文件),写侧不归它。
// 零复制判例同 budget.mjs(票 #226):旧文件只依赖 node 内建,直接 re-export,单一真源,
// 执法/快照语义一字不改(五通道闭集/counted codes/阈值冷却旋钮/原子写/fail-closed
// reset/events ring ≤20 全在旧文件,升级/对拍都以它为准)。
// 本 seam re-export 面(两票接口契约,勿另起炉灶):
//   BREAKER_CHANNELS(五通道闭集:fetch_url/gh_search/rss_parse/web_read/web_search)
//   BREAKER_COUNTED_CODES(channel_auth/channel_missing/quota)
//   BREAKER_STATE_VOCAB、readBreakerKnobs(env)(OPS_BREAKER_THRESHOLD/OPS_BREAKER_COOLDOWN_S)
//   emptyBreakerState、parseBreakerState、verdictFor、grantProbe、applyResult
//   breakerSnapshot、mkBreaker({file,env,round,ledgerFile,knobs,log})
//     → { file, knobs, verdict(name), record(name,{ok,code}), snapshot() }
// 状态文件 = breakerFileOf(ctx)(discovery-host.mjs 单源)= DOCS_ROOT/ops/breaker.json。
// 旧管线文件属主:ops/agent/ 零改动红线(票 #225/#226/#228)——本文件只 re-export,不 fork。
export * from "../agent/tools/breaker.mjs";
