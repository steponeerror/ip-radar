// faux-face.mjs — faux 面分派接线(票 #228 修复 ⑥;审查 P2-4 最小接面:只接 faux
// provider 分派,不动 T5 台账兼容面)。旧真源 = ops/agent/pipeline/faux.mjs(零改动
// 红线;loadFixture/transcriptName/fauxProvider 装配是私有面不 export → 本文件按旧源
// 逐字重实现,行型/路径/判例位等价,出处逐处标注):
//   fixture 路径/缺件判例      = 旧 faux.mjs loadFixture(faux.mjs:69-79)
//   provider 装配 + 罐装回合   = 旧 runFauxStep(faux.mjs:76-79;models id 同式
//     `faux-${def.model 斜杠转横线}`);v2 偏差:provider 名加轮次/步/假设唯一后缀——
//     旧每步 new Agent 自带 Responses 队列,v2 多子任务并行共用一个 harness Models 实例,
//     不加唯一名则 setProvider 同名互覆、罐装回合串台(偏差理由,行型不受影响)。
//   registry_seed 行(call_id=sd.id)= 旧 runFauxStep transcript 行(faux.mjs:91);
//     真面 call_id=sd.call_id(faux.mjs:137)归 model-round 直读宿主,不在本文件。
//   transcript 文件名          = 旧 faux.mjs transcriptName(faux.mjs:59-62;工件名常量
//     单源 artifacts.mjs,deep 族 deepTranscriptName 同源)。
import fs from "node:fs";
import path from "node:path";
import { fauxProvider } from "@earendil-works/pi-ai";
import { hidSlug } from "../agent/pipeline/steps.mjs";
import { ARTIFACTS as A, deepTranscriptName } from "../agent/artifacts.mjs";

// 旧 faux.mjs loadFixture 逐字副本(v2 面:fixturesDir 直传非 ctx;缺席=infra 配置面
// 失败,与旧同判例——faux 面 fixture 是必件不是可选件)。
export function loadFauxFixture(def, fixturesDir, item) {
  if (typeof fixturesDir !== "string")
    throw Object.assign(new Error(`模型步 fixture 缺:fixturesDir 未设置(${def.name})`), { code: "infra" });
  const p = def.name === "DEEP" ? path.join(fixturesDir, "deep", `${hidSlug(item.hid)}.json`)
    : path.join(fixturesDir, `${def.name.toLowerCase()}.json`);
  let fx;
  try { fx = JSON.parse(fs.readFileSync(p, "utf8")); }
  catch { throw Object.assign(new Error(`模型步 fixture 缺:${p}`), { code: "infra" }); }
  if (!Array.isArray(fx.turns)) throw Object.assign(new Error(`模型步 fixture 缺 turns:${p}`), { code: "infra" });
  return fx;
}

// 旧 runFauxStep registry_seed 行源(faux.mjs:91):fx.seeds 优先,fx.seed 单腿向后
// 兼容;faux 面 call_id 键=sd.id(真面=sd.call_id,归 model-round)。
export const fauxFixtureSeeds = (fx) =>
  (fx.seeds ?? (fx.seed ? [fx.seed] : [])).map((sd) => ({ call_id: sd.id, tool: sd.tool, sc: sd.sc }));

// 旧 runFauxStep provider 装配(faux.mjs:76-79)+ v2 唯一名(见头注);返回 modelRef
// (configure 面 {provider,modelId};真源=faux.getModel()——其 .provider 即唯一名字串,
// 勿用 faux.provider(那是 provider 对象非 id 字串)。
export function mkFauxFace(def, { roundId, stage, hid = null }) {
  const faux = fauxProvider({
    provider: `faux-${hidSlug(`${roundId}-${stage}${hid != null ? `-${hid}` : ""}`)}`,
    models: [{ id: `faux-${def.model.replace(/\//g, "-")}` }],
  });
  const m = faux.getModel();
  return { faux, modelRef: { provider: m.provider, modelId: m.id } };
}

// 旧 faux.mjs transcriptName 逐字副本(健康轮三步;SHORTLIST=发现轮面不在本票范围,
// 恒 null 由调用方按闭集拒)。
export const transcriptFile = (def, item) =>
  def.name === "TRIAGE" ? A.TRIAGE_TRANSCRIPT
  : def.name === "DEEP" ? deepTranscriptName(hidSlug(item.hid))
  : def.name === "SYNTH" ? A.SYNTH_TRANSCRIPT
  : null;
