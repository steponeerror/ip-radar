// budget.mjs — v2 预算面零复制 re-export(票 #226;spec 定案 3:budget.mjs **原样**搬进 v2 入口
// 调用,不改 extension/hook 化;跑稳后另议)。
// 零复制可行性已核:旧管线 ops/agent/pipeline/budget.mjs 只 import node 内建
// (fs/path/child_process/util/url/crypto),零旧管线内部耦合 → 直接 re-export,
// 与 models.mjs(定案 7)同一模式,单一真源;执法语义一字不改(拒跑文案/容差/宁少算口径
// 全在旧文件,升级/对拍都以它为准)。若将来旧文件长出内部耦合致无法直 import,才允许
// 整文件拷贝并在文件头注 why+出处,票面须写明(本票未触发该兜底)。
// 接线(budget-guard.mjs/entry.mjs,定案 3 双点):步前准入(月度 kill switch)+ 环内
// 检查(四界 attempt 前/结算后/步边界)——不 hook/memo 化,与旧管线 pipeline.mjs 检查点
// 同构;同参哈希面(dupKey/dupRecord)由此 seam 供 T3/T4 工具宿主注入(同旧 tools.mjs 面)。
// 旧管线文件属主:ops/agent/ 零改动红线(票 #225/#226)——本文件只 re-export,不 fork。
export * from "../agent/pipeline/budget.mjs";
