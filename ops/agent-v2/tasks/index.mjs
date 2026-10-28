// tasks/index.mjs — 各轮次 defineTask 落位聚合点(票 #225 只立骨架;T3/T4 填充)。
// 每轮次一个文件(HEALTH/DISCOVERY/…),export 进本数组,registry.mjs 统一装进
// "ops" 扩展。当前为空:骨架期 root conversation 走内建 GenerationTask(纯模型
// 回合),领域任务相位化(probe/verify/triage/… 十状态 → phases)是 T3/T4 的票面。
export const TASKS = [];
