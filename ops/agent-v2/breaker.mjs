// breaker.mjs — v2 熔断面零复制 re-export(票 #228;spec 定案 4:breaker.json 随迁,
// 五通道熔断读写逻辑原样接进 v2 对应相位,自有文件不 hook/memo 化,与 budget.mjs 同款
// 零复制 import 优先)。
// 零复制可行性已核:旧管线 ops/agent/tools/breaker.mjs 只 import node 内建(fs/path)
// + lib.sh(仅写侧 ledger 留痕用;读侧 snapshot 零依赖)→ 直接 re-export,单一真源,
// 执法/快照语义一字不改(五通道闭集/counted codes/阈值冷却旋钮/原子写/fail-closed
// reset/events ring ≤20 全在旧文件,升级/对拍都以它为准)。若将来旧文件长出内部耦合
// 致无法直 import,才允许整文件拷贝并在文件头注 why+出处,票面须写明(未触发)。
//
// 【T3 接口契约(票 #228 定案;T3 通道工具须按此对接,勿另起炉灶)】本 seam re-export 面:
//   BREAKER_CHANNELS(五通道闭集:fetch_url/gh_search/rss_parse/web_read/web_search)
//   BREAKER_COUNTED_CODES(channel_auth/channel_missing/quota)
//   BREAKER_STATE_VOCAB、readBreakerKnobs(env)(OPS_BREAKER_THRESHOLD/OPS_BREAKER_COOLDOWN_S)
//   emptyBreakerState、parseBreakerState、verdictFor、grantProbe、applyResult
//   breakerSnapshot、mkBreaker({file,env,round,ledgerFile,knobs,log})
//     → { file, knobs, verdict(name), record(name,{ok,code}), snapshot() }
// 状态文件 = breakerFileOf(ctx)(discovery-host.mjs 单源)= DOCS_ROOT/ops/breaker.json,
// 原子 tmp+rename、fail-closed、events ring ≤20。写侧(verdict/record)=T3 通道工具
// (fetch_url/web_read/…)按通道名结算时调用;读侧 snapshot()=健康轮 CLOSE 相位 09-budget.json
// 观察面(只读零写,回声律:不造文件——票 #228 测试钉死)。
// 旧管线文件属主:ops/agent/ 零改动红线(票 #225/#226/#228)——本文件只 re-export,不 fork。
export * from "../agent/tools/breaker.mjs";
