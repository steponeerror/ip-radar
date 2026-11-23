// round-state.mjs — v2 轮终态回写单源(工单 #408;#415 扩到全部终态出口)。
// Why:v2 轮(discover/health/add)真源=checkpoint(SQLite),rounds/<id>/state.json 只是
// 进度镜像;但 CLOSE 后 discover 镜像停在 running、health 干脆无件(#408 时 add 尚未
// 接线,#415 补)——轮实际已结束,状态文件在说谎(读面:boot 扫描
// backend/ipdb/_ops_rounds.py、UI 轮次徽章链 #407)。
// #408:CLOSE 相位与 writeRoundReport 同接线点被调(#403 判例同位),把终态写回镜像。
// #415:终态不止 CLOSE 一条路——轮中途失败/中止/停笔的任务终态出口同样经本模块写镜像
// (三任务每个 terminal commit 之前;例外=health 认领守卫的异主 bad_round 出口,不属主不写;
// 各出口处带 #415 注记)。
// 纪律:
//  - 状态词沿用管线既有 status 流(v1 pipeline.mjs finishClose/failStage):done/failed
//    (+health 面 stage 书挡 CLOSE/FAILED);不发明第二套状态词(票面明令)。
//    #415 中止出口取任务 outcome 同词 aborted(v1 无中止面;旧读面 scan_inflight_rounds
//    只认 in_flight,aborted 不入在飞扫描=与 done/failed 同属「轮已结束」)。
//  - 属主判(writeOwnedRoundState):终态镜像只写本任务的轮目录——未建轮/异物树/同 id
//    旧轮终态件不写(写了=把别轮终态改判,discover bad_round 判例同病)。
//  - 失败镜像宁少算:stages 只留 checkpoint 已提交相位,未成相位不造记录/名字
//    (close 未成不造 CLOSE 名;discover/add 镜像无 stage 键=字段集稳定不加键)。
//  - 幂等:updated_at 取盘上已有件的值(缺席=入参 ctx.state 的值),不写新时钟——
//    崩溃落在终态写与终态 commit 之间重入时重写字节级不变(报告件「无时钟入文」
//    同标准,round-report.mjs 头注)。
//  - 尽力写不掷错:终态镜像写败只注记不炸轮。与报告件 fail-loud(#403)反向的根由:
//    v1 的 state.json 是真源(写败=真失败,fail loud);v2 真源=checkpoint 且终态 commit
//    在镜像写之后——镜像写败把已成功的轮改判 failed 才是真话反转,镜像降级为 stderr
//    注记(waitModel 留痕读败同律)。
//    #415 中止面加一层:abort handler 里连 ctx 重建一起包(writeAbortRoundState)——
//    abort handler 裸抛=任务判 faulted、aborted outcome 丢失(该函数头注有实测)。
import fs from "node:fs";
import path from "node:path";

const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };

// 终态镜像写:rounds/<id>/state.json ← {...盘上件(缺席=ctx.state), status[, stage][, stages]}。
// - 盘上件优先为底:discover 镜像自 bootstrap 起在场,patch 只改字段值不加字段(镜像
//   字段集稳定);health 首写以 ctx.state 全形起底(rebuildRoundCtx 已终态化)。
// - 原子写(tmp+rename,round-report.mjs 判例同形);返回布尔,不掷错(见头注)。
export function writeTerminalRoundState(ctx, { status, stage = null, stages = null }) {
  const file = path.join(ctx.dir, "state.json");
  try {
    const base = readJson(file) ?? { ...ctx.state };
    const next = { ...base, status };
    if (stage != null) next.stage = stage;
    if (stages != null) next.stages = stages;
    fs.writeFileSync(`${file}.tmp`, JSON.stringify(next, null, 2) + "\n");
    fs.renameSync(`${file}.tmp`, file);
    return true;
  } catch (e) {
    ctx.log?.(`[state] 终态镜像写败(status=${status}):${e?.message ?? e}`);
    return false;
  }
}

// discover/add 属主判(#415):终态镜像只写本任务的轮目录。判据=建轮守卫
// (discover-round/add-round bootstrapRoundDir)同律,二选一:
//  ① checkpoint 已提交过相位(ctx.state.stages 非空)——必已过守卫;
//  ② 盘上镜像=本轮自家的建轮骨架(round_id 同轮且 stages 空:bootstrap 已写骨架、
//     首相位尚未提交——首相位步抛/门红即此形)。
// 两者皆否=未建轮(无件,不凭空造轮目录)/异物树/同 id 旧轮终态件 → 不写。
// health 轮不走本判(轮中无进度镜像,属主=认领件 .v2-claim.json,claimGuard 已核)。
function ownsRoundDir(ctx) {
  if (ctx.state.stages.length > 0) return true;
  const prior = readJson(path.join(ctx.dir, "state.json"));
  return prior?.round_id === ctx.roundId && Array.isArray(prior.stages) && prior.stages.length === 0;
}

// discover/add 失败/中止出口的镜像写(#415):ctx=由 checkpoint 重建的旧 ctx
// (ctx.state.stages=已提交相位名单,discover-round/add-round buildCtx 同形)。
// 属主判过才写,不过=不写;写败不掷错(writeTerminalRoundState 同律)。
export function writeOwnedRoundState(ctx, status) {
  if (ownsRoundDir(ctx)) writeTerminalRoundState(ctx, { status });
}

// 中止出口包装(#415):abort handler 里的镜像写(含 ctx 重建/属主判)整体尽力不掷错。
// Why 单独成函数:abort handler 是任务终态 commit 前的最后一笔代码——它裸抛时框架把任务
// 判 faulted、aborted outcome 丢失且不重试(pi-durable 1.4.0 实测:outcome={status:"faulted"},
// handler 只跑一次),等于把 P2-⑧「中止无终态」病请回来。相位出口里 ctx 重建在写函数之外,
// 那里抛=相位 fault,属既有行为不动;abort 面的 ctx 重建是 #415 新增代码,不得引入这条
// 回退,故连同 ctx 重建一起包住。写败只 stderr 注记(此时可能还没有 ctx,走不到 ctx.log)。
export function writeAbortRoundState(write) {
  try { write(); } catch (e) { process.stderr.write(`[state] 中止镜像写败:${e?.message ?? e}\n`); }
}
