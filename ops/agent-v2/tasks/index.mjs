// tasks/index.mjs — 各轮次 defineTask 落位聚合点(票 #225 骨架;T4 填充)。
// 每轮次一个文件(HEALTH/DISCOVERY/…),export 进本数组,registry.mjs 统一装进
// "ops" 扩展。T4(#228):ops-model-round(单模型步,stage∈TRIAGE/DEEP/SYNTH)+
// ops-health-round(健康轮十态相位机)。T3 发现轮(discover 四态)同面接入——
// 冲突预期内留给 merger(票 #228 任务书注记)。
import { OPS_MODEL_ROUND } from "./model-round.mjs";
import { OPS_HEALTH_ROUND } from "./health-round.mjs";

export const TASKS = [OPS_MODEL_ROUND, OPS_HEALTH_ROUND];
