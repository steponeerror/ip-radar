// models.mjs — pi-ai 模型装载(ADR 0004;批首三核①复核后的装载路径;
// 票 #143 多供应商化:builtin 全家 + 三层 upsert 按 provider 作用域化)。
//
// 装载基座 = pi-ai builtinModels()(providers/all,builtin provider 全注册;
// 工厂只带目录+懒 API wrapper,SDK 在首请求才进 chunk——README「Providers and
// Models/All Built-in Providers」)。三层 upsert 语义(同 id 覆盖,缺省字段继承
// 下层默认)逐字保持,但作用域从「单 zai 列表」扩为「逐 provider」:
//   1. 用户 models.json(~/.pi/agent/models.json;OPS_MODELS 覆盖)——定义形,可缺
//      api/baseUrl 等字段,按 pi-coding-agent ModelConfig→modelFromJson 语义继承;
//   2. models-store.json(~/.pi/agent/models-store.json;OPS_MODELS_STORE 覆盖)——全量 Model 形;
//   3. pi-ai 内置目录(builtin 全家;zai-coding-cn 同 #140 时期行为)。
// 两层文件可引用非 builtin provider(如 lmstudio):从 provider 层 baseUrl/api 构造
// createProvider,provider 层 apiKey 字面量入凭证店;缺 baseUrl/api、api 名不在
// 已知 chat api 闭集 = 显式报错不静默。注:pi-ai 自身不读用户 models.json(那是
// pi-coding-agent 的 ModelConfig 层,本包不依赖);此处复刻其最小 upsert 语义。
// 2026-10-19 实测:pi-ai@1.3.0 内置 zai-coding-cn 目录已含 glm-5.3/glm-5.3-flash;
// 三层装载仍保留——用户层 price/contextWindow 等配置必须赢过内置目录。
//
// 凭证:auth.json(OPS_AUTH 覆盖路径)逐家入 InMemoryCredentialStore——形状
// { "<providerId>": { type: "api_key", key } }(pi auth.json 同形;桥侧 #143 起
// 每次 spawn 物化合并 auth.json 落 ops 树)。stored credential owns provider:pi-ai
// 契约 env 仅在无存储时咨询——各家 env 兜底(ANTHROPIC_API_KEY 等)由 builtin
// 工厂自带的 envApiKeyAuth 在请求期解析,env 名归 pi-ai 所有(node_modules 内读,
// 非 SPAWN_CONTRACT_ENV 面;桥经 env 继承透传)。
//
// 轮次模型(九裁决 9;#143 值文法扩面):OPS_MODEL_HEALTH / OPS_MODEL_DISCOVER
// 值 = qualified "provider/model"(首个 "/" 前为 provider id——provider id 不含
// "/",模型 id 可含,如 openrouter "black-forest-labs/flux.2-pro");裸值无 "/"
// = 缺省 provider zai-coding-cn(#140 既有配置/env 向后兼容)。缺省
// health=glm-5.3-flash / discover=glm-5.3(zai 不变)。导出 resolve(round) 供
// agent.mjs 取模型。离线约束:builtin 目录全静态,refresh() 零调用(动态家目录
// 不在本面——llamacpp 形经用户层 models.json 接入)。
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  createProvider, envApiKeyAuth, InMemoryCredentialStore,
} from "@earendil-works/pi-ai";
import { builtinModels } from "@earendil-works/pi-ai/providers/all";

export const PROVIDER_ID = "zai-coding-cn"; // 缺省 provider(裸模型 id 的归属家)
const DEFAULTS = { health: "glm-5.3-flash", discover: "glm-5.3" };

// 非 builtin provider 构造用的 api 名→lazy 工厂导出名闭集(builtin 目录实测
// 10 家 chat api,2026-10-20;provider-composer 语义:用户层 api 是名不是模块)。
const API_FACTORY_EXPORT = {
  "anthropic-messages": "anthropicMessagesApi",
  "azure-openai-responses": "azureOpenAIResponsesApi",
  "bedrock-converse-stream": "bedrockConverseStreamApi",
  "google-generative-ai": "googleGenerativeAIApi",
  "google-vertex": "googleVertexApi",
  "mistral-conversations": "mistralConversationsApi",
  "openai-codex-responses": "openAICodexResponsesApi",
  "openai-completions": "openAICompletionsApi",
  "openai-responses": "openAIResponsesApi",
  "pi-messages": "piMessagesApi",
};

const apiWrapper = async (name) => {
  const exportName = API_FACTORY_EXPORT[name];
  if (!exportName) {
    throw new Error(`api 名不在已知 chat api 闭集: ${name}(已知:${Object.keys(API_FACTORY_EXPORT).join(",")})`);
  }
  const mod = await import(`@earendil-works/pi-ai/api/${name}.lazy`);
  return mod[exportName]();
};

const loadJson = (p) => { try { return JSON.parse(readFileSync(p, "utf8")); } catch { return undefined; } };

// mergeCompat / modelFromDefinition 语义逐字对齐 pi-coding-agent provider-composer.js
// (compat 浅合并字段级;缺省 name/reasoning/input/cost/contextWindow/maxTokens 继承 defaults)。
const mergeCompat = (base, override) => (!override ? base : { ...base, ...override });

function modelFromDefinition(providerId, def, providerConfig, defaults) {
  const api = def.api ?? providerConfig.api ?? defaults?.api;
  if (!api) throw new Error(`${providerId}/${def.id}: 无 api 且无下层默认`);
  const baseUrl = def.baseUrl ?? providerConfig.baseUrl ?? defaults?.baseUrl;
  if (!baseUrl) throw new Error(`${providerId}/${def.id}: 无 baseUrl 且无下层默认`);
  return {
    id: def.id, name: def.name ?? def.id, api, provider: providerId, baseUrl,
    reasoning: def.reasoning ?? false,
    thinkingLevelMap: def.thinkingLevelMap ?? defaults?.thinkingLevelMap,
    input: def.input ?? ["text"], inputLimits: def.inputLimits,
    cost: def.cost ?? { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    promptCache: def.promptCache, contextWindow: def.contextWindow ?? 128000,
    maxTokens: def.maxTokens ?? 16384, samplingParams: def.samplingParams,
    headers: undefined, type: "chat",
    compat: mergeCompat(mergeCompat(defaults?.compat, providerConfig.compat), def.compat),
  };
}

// findDefaults 语义对齐:同 id → 同 api → openai-completions → 首个。
// #143 起作用域 = 该 provider 自己的合并列表(单家时代全局找等价;多家跨家找
// 会继承别家 baseUrl——错误继承,须按家隔离)。
const findDefaults = (models, id, api) =>
  models.find((m) => m.id === id) ??
  (api ? models.find((m) => m.api === api) : undefined) ??
  models.find((m) => m.api === "openai-completions") ?? models[0];

// qualified 值解析:首个 "/" 前是 provider id;裸值 = 缺省 provider。
export function parseModelRef(v) {
  const i = v.indexOf("/");
  return i < 0 ? { provider: PROVIDER_ID, model: v }
    : { provider: v.slice(0, i), model: v.slice(i + 1) };
}

export async function loadModels(opts = {}) {
  const modelsPath = opts.modelsPath ?? process.env.OPS_MODELS
    ?? path.join(os.homedir(), ".pi/agent/models.json");
  const storePath = opts.storePath ?? process.env.OPS_MODELS_STORE
    ?? path.join(os.homedir(), ".pi/agent/models-store.json");
  const authPath = opts.authPath ?? process.env.OPS_AUTH
    ?? path.join(os.homedir(), ".pi/agent/auth.json");

  // 凭证店:auth.json 逐家(builtin 工厂 env 兜底链归 pi-ai;stored owns provider)
  const credentials = new InMemoryCredentialStore();
  for (const [pid, cred] of Object.entries(loadJson(authPath) ?? {})) {
    if (cred && typeof cred === "object" && typeof cred.key === "string" && cred.key) {
      await credentials.modify(pid, async () => ({ type: "api_key", key: cred.key }));
    }
  }

  const models = builtinModels({ credentials });
  // 逐 provider 合并列表(builtin 底座;chat+非 chat 全收,upsert 保持原形)。
  // 只重建被两层文件碰过的家(spread 保 auth/stream/api 派发——mixed-API 家如
  // github-copilot 不能单 api 重建,只覆写模型读取面)。
  const byProvider = new Map();
  for (const p of models.getProviders()) {
    byProvider.set(p.id, [...(p.getAllModels?.() ?? p.getModels())]);
  }
  const touched = new Set();

  const upsert = (pid, defs, providerConfig) => {
    const merged = byProvider.get(pid) ?? [];
    for (const def of defs) {
      const defaults = findDefaults(merged, def.id, def.api ?? providerConfig.api);
      const model = modelFromDefinition(pid, def, providerConfig, defaults);
      const i = merged.findIndex((m) => (m.type ?? "chat") === (model.type ?? "chat") && m.id === model.id);
      if (i >= 0) merged[i] = model; else merged.push(model);
    }
    byProvider.set(pid, merged);
    touched.add(pid);
  };

  // 两层文件按 provider 展开(store: {pid:{models,...}};user: providers.{pid});
  // provider 层 apiKey 字面量 = 固定 key(lmstudio "lm-studio" 形)入凭证店。
  // applyLayer 是 async(apiWrapper 懒加载),故 loadModels 保持 async。
  const applyLayer = async (file, layer) => {
    for (const [pid, raw] of Object.entries(file ?? {})) {
      if (!raw || typeof raw !== "object" || !Array.isArray(raw.models)) continue;
      const { models: defs, apiKey, ...providerConfig } = raw;
      if (apiKey) await credentials.modify(pid, async () => ({ type: "api_key", key: apiKey }));
      if (!defs.length) continue;
      if (!models.getProvider(pid) && !byProvider.has(pid)) {
        if (!providerConfig.api || !providerConfig.baseUrl) {
          throw new Error(`${pid}: 用户层 provider 无 api/baseUrl,无法注册(文件:${layer})`);
        }
        models.setProvider(createProvider({
          id: pid, name: providerConfig.name ?? pid,
          baseUrl: providerConfig.baseUrl,
          api: await apiWrapper(providerConfig.api), models: [],
        }));
      }
      upsert(pid, defs, providerConfig);
    }
  };
  await applyLayer(loadJson(storePath), "models-store.json");
  await applyLayer(loadJson(modelsPath)?.providers, "models.json");

  for (const pid of touched) {
    const base = models.getProvider(pid);
    const merged = byProvider.get(pid);
    models.setProvider({
      ...base,
      getModels: () => merged.filter((m) => (m.type ?? "chat") === "chat"),
      getAllModels: () => merged,
    });
  }
  // zai env 兜底链显式重申(builtin 工厂本就带同款 envApiKeyAuth;此处显式留
  // 读点使 ZAI_CODING_CN_API_KEY 归 SPAWN_CONTRACT_ENV 对拍面,契约表不漂)
  const zaiBase = models.getProvider(PROVIDER_ID);
  models.setProvider({
    ...zaiBase,
    auth: { apiKey: envApiKeyAuth("Z.AI Coding CN API key", ["ZAI_CODING_CN_API_KEY"]) },
    ...(touched.has(PROVIDER_ID)
      ? {
        getModels: () => byProvider.get(PROVIDER_ID).filter((m) => (m.type ?? "chat") === "chat"),
        getAllModels: () => byProvider.get(PROVIDER_ID),
      }
      : {}),
  });

  const resolve = (round) => {
    const raw = process.env[`OPS_MODEL_${round.toUpperCase()}`] ?? DEFAULTS[round];
    if (!raw) throw new Error(`未知轮次: ${round}`);
    const { provider, model: id } = parseModelRef(raw);
    const m = models.getModel(provider, id);
    if (!m) {
      const own = models.getModels(provider);
      const ownIds = own.length
        ? own.slice(0, 8).map((x) => x.id).join(",") + (own.length > 8 ? `,…共${own.length}型` : "")
        : "(该 provider 未装载任何 chat 模型)";
      throw new Error(
        `模型未装载: ${provider}/${id}(${ownIds};已注册 provider ${models.getProviders().length} 家,目录 dump: node ops/agent/catalog.mjs)`);
    }
    return m;
  };
  return {
    models, resolve, credentials,
    catalog: Object.fromEntries(models.getProviders()
      .map((p) => [p.id, models.getModels(p.id).map((m) => m.id)])
      .filter(([, ids]) => ids.length > 0)),
  };
}
