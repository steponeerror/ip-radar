// models.mjs — v2 模型装载薄适配(票 #225;spec 定案 7:模型面不动,配置与旧管线同源)。
// 零复制:直接只读 re-export 旧管线 ops/pipeline-core/models.mjs 的 loadModels——其内部
// `@earendil-works/pi-ai` 解析自 ops/node_modules(#412 单包合并后 v1/v2 子树共用
// 包根唯一 node_modules,旧「双实例同版断言」闸改钉单实例唯一物理路径,防再分叉;
// T0 api-map.md §0)。凭证链原样:auth.json(OPS_AUTH)→ InMemoryCredentialStore;
// env 兜底 ZAI_CODING_CN_API_KEY;凭证零入码零入日志。
//
// 旧管线文件属主:ops/pipeline-core/ 零改动红线(票 #225)——本文件只 re-export,不 fork。
export { loadModels, parseModelRef, PROVIDER_ID } from "../pipeline-core/models.mjs";
