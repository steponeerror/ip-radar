// models.mjs — pi-ai 模型装载(ADR 0004;批首三核①复核后的装载路径)
//
// 装载三层 upsert(同 id 覆盖,缺省字段继承下层默认):
//   1. 用户 models.json(~/.pi/agent/models.json;OPS_MODELS 覆盖)——定义形,可缺
//      api/baseUrl 等字段,按 pi-coding-agent ModelConfig→modelFromJson 语义继承;
//   2. models-store.json(~/.pi/agent/models-store.json;OPS_MODELS_STORE 覆盖)——全量 Model 形;
//   3. pi-ai 内置 zai-coding-cn 目录(工厂 zaiCodingCnProvider)。
// 注:pi-ai 自身不读用户 models.json(那是 pi-coding-agent 的 ModelConfig 层,本包不依赖);
// 此处复刻其最小 upsert 语义。2026-10-19 实测修正:pi-ai@1.3.0 内置 zai-coding-cn 目录
// 已含 glm-5.3/glm-5.3-flash(npm 与本地 release 同 md5),但三层装载仍保留——用户层
// price/contextWindow 等配置必须赢过内置目录。
//
// 凭证(修正块①):InMemoryCredentialStore 存 auth.json 的 zai-coding-cn.key(OPS_AUTH
// 覆盖路径;ZAI_CODING_CN_API_KEY env 兜底,由 provider 的 envApiKeyAuth 在请求时解析——
// pi-ai 契约:stored credential owns provider,env 仅在无存储时咨询)。
//
// 轮次模型(九裁决 9):health=glm-5.3-flash / discover=glm-5.3 主力;OPS_MODEL_HEALTH /
// OPS_MODEL_DISCOVER 可覆盖。导出 resolve(round) 供 agent.mjs 取模型。
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  createModels, createProvider, envApiKeyAuth, InMemoryCredentialStore,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { zaiCodingCnProvider } from "@earendil-works/pi-ai/providers/zai-coding-cn";

export const PROVIDER_ID = "zai-coding-cn";
const DEFAULTS = { health: "glm-5.3-flash", discover: "glm-5.3" };

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

// findModelDefaults 语义对齐:同 id → 同 api → openai-completions → 首个 chat。
const findDefaults = (models, id, api) =>
  models.find((m) => m.id === id) ??
  (api ? models.find((m) => m.api === api) : undefined) ??
  models.find((m) => m.api === "openai-completions") ?? models[0];

export async function loadModels(opts = {}) {
  const modelsPath = opts.modelsPath ?? process.env.OPS_MODELS
    ?? path.join(os.homedir(), ".pi/agent/models.json");
  const storePath = opts.storePath ?? process.env.OPS_MODELS_STORE
    ?? path.join(os.homedir(), ".pi/agent/models-store.json");
  const authPath = opts.authPath ?? process.env.OPS_AUTH
    ?? path.join(os.homedir(), ".pi/agent/auth.json");

  const baseProvider = zaiCodingCnProvider();
  let merged = [...(baseProvider.getAllModels?.() ?? baseProvider.getModels())];

  const upsert = (defs, providerConfig, layer) => {
    for (const def of defs) {
      const defaults = findDefaults(merged, def.id, def.api ?? providerConfig.api);
      const model = modelFromDefinition(PROVIDER_ID, def, providerConfig, defaults);
      const i = merged.findIndex((m) => (m.type ?? "chat") === (model.type ?? "chat") && m.id === model.id);
      if (i >= 0) merged[i] = model; else merged.push(model);
    }
    void layer;
  };

  const store = loadJson(storePath); // 形状 { "<providerId>": { models: [...] } }
  if (store?.[PROVIDER_ID]?.models) upsert(store[PROVIDER_ID].models, {}, "store");

  const userCfg = loadJson(modelsPath)?.providers?.[PROVIDER_ID] ?? {};
  const { models: userModelDefs, ...providerConfig } = userCfg; // 顶层 baseUrl/api/compat 作 provider 层
  if (userModelDefs?.length) upsert(userModelDefs, providerConfig, "user");

  // 凭证:auth.json key(env 兜底由 envApiKeyAuth 在请求时解析)
  const credentials = new InMemoryCredentialStore();
  const key = loadJson(authPath)?.[PROVIDER_ID]?.key;
  if (key) await credentials.modify(PROVIDER_ID, async () => ({ type: "api_key", key }));

  const models = createModels({ credentials });
  models.setProvider(createProvider({
    id: baseProvider.id, name: baseProvider.name, baseUrl: baseProvider.baseUrl,
    auth: { apiKey: envApiKeyAuth("Z.AI Coding CN API key", ["ZAI_CODING_CN_API_KEY"]) },
    models: merged, api: openAICompletionsApi(),
  }));

  const resolve = (round) => {
    const id = process.env[`OPS_MODEL_${round.toUpperCase()}`] ?? DEFAULTS[round];
    if (!id) throw new Error(`未知轮次: ${round}`);
    const m = models.getModel(PROVIDER_ID, id);
    if (!m) throw new Error(`模型未装载: ${PROVIDER_ID}/${id}(已装载:${models.getModels(PROVIDER_ID).map((x) => x.id).join(",")})`);
    return m;
  };
  return { models, resolve, credentials, catalog: models.getModels(PROVIDER_ID).map((m) => m.id) };
}
