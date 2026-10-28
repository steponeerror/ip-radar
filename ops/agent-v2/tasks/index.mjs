// tasks/index.mjs — 各轮次 defineTask 落位聚合点(票 #225 骨架;票 #227 T3 落发现轮、
// 票 #228 T4 填健康轮)。每轮次一个文件,export 进本数组,registry.mjs 统一装进
// "ops" 扩展。并批合并(#228 收口时 T3+T4 并飞):本聚合点按并集解——T3 发现轮
// (discover 六相位)+ T4 单模型步/健康轮(ops-model-round/ops-health-round);
// 任务文件之间互不 import,后续轮次继续只追加行。
import { discoverRoundTask } from "./discover-round.mjs"; // 票 #227 T3:发现轮(旧六步语义逐相位映射)
import { OPS_MODEL_ROUND } from "./model-round.mjs"; // 票 #228 T4:单模型步(stage∈TRIAGE/DEEP/SYNTH)
import { OPS_HEALTH_ROUND } from "./health-round.mjs"; // 票 #228 T4:健康轮十态相位机

export const TASKS = [discoverRoundTask, OPS_MODEL_ROUND, OPS_HEALTH_ROUND];
