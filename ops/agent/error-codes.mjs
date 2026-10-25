// error-codes.mjs — 轮次信封失败面 error.code 闭集九词(规格 §4)单一真源。
// 2026-10-24 从 agent.mjs 拆出:pipeline.mjs 曾静态 import agent.mjs 取此常量,而
// agent.mjs main 的 OPS_PIPELINE=pipeline 委派路径(灰度开关)动态 import pipeline.mjs
// ——agent.mjs 顶层 `await main(...)` 未决时 pipeline.mjs 开始求值、其静态依赖回头等
// agent.mjs 模块完成 → ESM 顶层 await 死锁:事件循环空转,Node 报
// "unsettled top-level await" 退出 13、stdout 无信封。灰度切换后首个 cron 健康轮
// 即此形态(rc=13,spawn 契约违背);e2e 不设 OPS_PIPELINE(tests/test_ops_rounds_e2e.py
// 注释),该路径 CI 从未走过。断环 = 常量下沉本模块,pipeline.mjs 改自此导入,
// agent.mjs re-export 保导出面契约(selftest-contract「ERROR_CODES 导出面」)。
// 事故与裁决:2026-10-24 判例 2026-10-24-discover-dual-channel-dead 同日;
// 回归测试 = selftest-contract「委派可落定」spawn 探针(usage 前置 throw,零网)。
// 闭集 13 词(#199 交付A 9→13:budget_exceeded/wall_clock_exceeded=A1 四界,budget_monthly
// =A2 月度准入,repeat_storm=A4 同参拦;通道开断 channel_open 属交付B 不在此)。
export const ERROR_CODES = ["bad_round", "model_face", "empty_text", "foreign_tool", "closure_check",
  "ledger_failed", "verify_failed", "sandbox_violation", "infra",
  "budget_exceeded", "wall_clock_exceeded", "budget_monthly", "repeat_storm"];
