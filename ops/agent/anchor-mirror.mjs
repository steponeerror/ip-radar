// anchor-mirror.mjs — #182 锚集/锚行形状 JS 单源镜像(#194 C3-2 合一)。
// 锚集真源=backend/ipdb/_eval/anchors.py 的 ANCHORS(扩员只改 python 一处);
// 此前 run-golden.mjs GOLDEN_SWEEP_ANCHORS 与 selftest-pipeline.mjs SWEEP_ANCHORS
// 两份手抄互不同步——anchors.py 扩员而 stub 不改→门只验工件自洽仍全绿(评审D
// 漂移面)。本模块是唯一 JS 定义点:selftest.sh §14 对拍哨只对拍此一处;
// selftest-pipeline 另有镜像测试钉「两消费文件源文本零手抄副本」。
// 约束:GOLDEN_SWEEP_ANCHORS/ANCHOR_ROW_KEYS 保持数组字面量形态(哨用正则抽
// 取,禁改成计算表达式);本模块纯常量+纯函数,env 零依赖——消费方可在 env
// 落位前静态 import(与 tools.mjs 面「env 先于 import」纪律不冲突)。
export const GOLDEN_SWEEP_ANCHORS = [["8.8.8.8", "clean"], ["8.8.4.4", "clean"], ["1.1.1.1", "clean"], ["1.0.0.1", "clean"],
  ["9.9.9.9", "clean"], ["208.67.222.222", "clean"], ["114.114.114.114", "clean"], ["223.5.5.5", "clean"],
  ["9.9.9.4", "clean"], ["10.0.0.1", "reserved"], ["127.0.0.1", "reserved"], ["192.168.1.1", "reserved"],
  ["172.16.0.1", "reserved"], ["185.220.101.1", "tor"], ["171.25.193.78", "tor"], ["185.220.101.34", "tor"],
  ["52.95.116.115", "hosting"], ["20.36.253.52", "hosting"], ["34.64.121.1", "hosting"]];
// 锚巡检工件行键集(=anchors.py anchor_sweep results.append 行键的 JS 侧声明;
// §14 形状哨 py↔JS 集合对拍,C3-4)。G_ANCHOR_SWEEP 门逐字段机检以此为准的同词面。
export const ANCHOR_ROW_KEYS = ["ip", "expect", "ok", "reason", "verdict", "confidence", "accusers", "conflict"];
// 罐装行构造器:键集钉死——多写/漏写字段即 throw(防罐装面新行键静默漂移)。
// 基行=clean 形(ok:true/reason:null/verdict:benign/confidence:0/accusers:[]/conflict:false),
// 覆盖参数按需传(事故形 sweepIncident 等)。
export function anchorRow(fields) {
  const row = { ip: fields.ip, expect: fields.expect, ok: fields.ok ?? true, reason: fields.reason ?? null,
    verdict: fields.verdict ?? "benign", confidence: fields.confidence ?? 0, accusers: fields.accusers ?? [],
    conflict: fields.conflict ?? false };
  const extra = Object.keys(fields).filter((k) => !(k in row));
  if (extra.length) throw new Error(`anchorRow 键集漂移:未知字段 ${extra.join(",")}(允许=${ANCHOR_ROW_KEYS.join(",")})`);
  const got = Object.keys(row).sort().join(",");
  const want = [...ANCHOR_ROW_KEYS].sort().join(",");
  if (got !== want) throw new Error(`anchorRow 键集漂移:${got}≠${want}`);
  return row;
}
