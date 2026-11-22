// round-state.mjs — v2 轮终态回写单源(工单 #408;#405 遗留 A)。
// Why:v2 轮(discover/health)真源=checkpoint(SQLite),rounds/<id>/state.json 只是
// 进度镜像;但 CLOSE 后 discover 镜像停在 running、health 干脆无件——轮实际已结束,
// 状态文件在说谎(读面:boot 扫描 backend/ipdb/_ops_rounds.py、UI 轮次徽章链 #407)。
// 本模块在 CLOSE 相位与 writeRoundReport 同接线点被调(#403 判例同位),把终态写回镜像。
// 纪律:
//  - 状态词沿用管线既有 status 流(v1 pipeline.mjs finishClose/failStage):done/failed
//    (+health 面 stage 书挡 CLOSE/FAILED);不发明第二套状态词(票面明令)。
//  - 幂等:updated_at 取盘上已有件的值(缺席=入参 ctx.state 的值),不写新时钟——
//    崩溃落在终态写与终态 commit 之间重入 CLOSE 时重写字节级不变(报告件「无时钟入文」
//    同标准,round-report.mjs 头注)。
//  - 尽力写不掷错:终态镜像写败只注记不炸轮。与报告件 fail-loud(#403)反向的根由:
//    v1 的 state.json 是真源(写败=真失败,fail loud);v2 真源=checkpoint 且终态 commit
//    在镜像写之后——镜像写败把已成功的轮改判 failed 才是真话反转,镜像降级为 stderr
//    注记(waitModel 留痕读败同律)。
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
