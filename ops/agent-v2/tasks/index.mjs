// tasks/index.mjs — 各轮次 defineTask 落位聚合点(票 #225 立骨架;票 #227 T3 落第一只)。
// 每轮次一个文件,export 进本数组,registry.mjs 统一装进 "ops" 扩展。
// 并行注意(T4 #228 同批在飞):本聚合点只追加各自任务文件的 import+展开,
// 冲突面=本文件单行,留给 merger;任务文件之间互不 import。
import { discoverRoundTask } from "./discover-round.mjs"; // 票 #227 T3:发现轮(旧六步语义逐相位映射)

export const TASKS = [
  discoverRoundTask,
];
