// models.mjs — v2 模型装载薄适配(票 #225;spec 定案 7:模型面不动,配置与旧管线同源)。
// 零复制:直接只读 re-export 旧管线 ops/agent/models.mjs 的 loadModels——其内部
// `@earendil-works/pi-ai` 解析自 ops/agent/node_modules(lock 实装 1.4.0,与本包
// 钉死的 1.4.0 同版;tests/scaffold.test.mjs 断言两份同版,防双实例凭证店分裂,
// T0 api-map.md §0)。凭证链原样:auth.json(OPS_AUTH)→ InMemoryCredentialStore;
// env 兜底 ZAI_CODING_CN_API_KEY;凭证零入码零入日志。
//
// 旧管线文件属主:ops/agent/ 零改动红线(票 #225)——本文件只 re-export,不 fork。
export { loadModels, parseModelRef, PROVIDER_ID } from "../agent/models.mjs";
