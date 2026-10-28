// smoke-glm.test.mjs — GLM smoke(票 #225;真实 1 次 glm-5.3-flash 调用,单次 ≈¥0.00004)
// 面:开 SQLite → root conversation → 1 次 GLM 调用 → 断言应答落库(重开 harness 仍在)
// + requestId exactly-once 重放零新调用(T0 notes/smoke.mjs 主链,落在 v2 适配层入口形态)。
// 凭证照 ops/agent 现行链(auth.json → env 兜底),测试只判有无,零密钥入码/入日志。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { readFileSync } from "node:fs";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { openHarness, requestIdFor } from "../entry.mjs";
import { loadModels } from "../models.mjs";

// 凭证在否(布尔判定,不打印值):auth.json(OPS_AUTH 覆盖)有 zai 家 key,或 env 兜底键在。
function hasZaiCredential() {
  const authPath = process.env.OPS_AUTH
    ?? path.join(os.homedir(), ".pi", "agent", "auth.json");
  try {
    const auth = JSON.parse(readFileSync(authPath, "utf8"));
    if (auth?.["zai-coding-cn"]?.key) return true;
  } catch { /* 无 auth.json → 只看 env */ }
  return Boolean(process.env.ZAI_CODING_CN_API_KEY);
}
const SKIP = hasZaiCredential() ? false : "无 zai 凭证(auth.json/ZAI_CODING_CN_API_KEY 均缺)——SKIP(CI 无凭证判例)";

const ANSWER_TOKEN = "V2OK";
const PROMPT = `只回复四个字符:${ANSWER_TOKEN}(不要任何其他内容)`;
const REQUEST_ID = "smoke-glm-v2";

const lastAssistantText = (view) => (view.entries.filter((e) => e.kind === "pi.assistant").at(-1)?.model ?? [])
  .flatMap((m) => m.content ?? []).find((b) => b.type === "text")?.text ?? "";

test("GLM smoke:SQLite+root+1 次调用落库;重开仍在;requestId 重放零新调用", { skip: SKIP }, async () => {
  const { resolve } = await loadModels();
  const m = resolve("health"); // 缺省 flash 档(OPS_MODEL_HEALTH 可覆盖;定案 7 同源)
  const modelRef = { provider: m.provider, modelId: m.id };

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-smoke-glm-"));
  const dbPath = path.join(tmp, "agent-v2.sqlite");
  try {
    // phase A:开库 → root → 1 次 GLM 调用
    const h1 = (await openHarness({ dbPath })).harness;
    const root1 = await h1.root(BACKGROUND_CONTEXT, { agent: { model: modelRef } });
    const sub = await root1.submit(
      { type: "input", content: PROMPT, requestId: REQUEST_ID },
      BACKGROUND_CONTEXT,
    );
    const settled = await sub.wait(BACKGROUND_CONTEXT);
    assert.equal(settled.status, "done");
    assert.match(lastAssistantText(await root1.context(BACKGROUND_CONTEXT)), new RegExp(ANSWER_TOKEN));
    const usageA = await h1.usage(BACKGROUND_CONTEXT);
    await h1.close(BACKGROUND_CONTEXT);

    // phase B:新进程视角重开同库 → transcript 应答仍在(落库断言)
    const h2 = (await openHarness({ dbPath })).harness;
    const root2 = await h2.root(BACKGROUND_CONTEXT, { agent: { model: modelRef } });
    assert.match(lastAssistantText(await root2.context(BACKGROUND_CONTEXT)), new RegExp(ANSWER_TOKEN),
      "重开后 GLM 应答不在 transcript:落库失败");

    // exactly-once:同 requestId 重放 → 既有 submission(同 id),usage 不变(零新调用)
    const again = await root2.submit(
      { type: "input", content: "重复请求", requestId: REQUEST_ID, whenBusy: "reject" },
      BACKGROUND_CONTEXT,
    );
    assert.equal(again.id, sub.id, "同 requestId 重放应返回既有 submission");
    await again.wait(BACKGROUND_CONTEXT).catch(() => undefined); // 已 settle/被拒均可,不新建调用
    assert.deepEqual(await h2.usage(BACKGROUND_CONTEXT), usageA, "重放后 usage 变化:发生新模型调用");
    await h2.close(BACKGROUND_CONTEXT);

    // requestId 形状纪律(t1-notes 风险12):cron 幂等键
    assert.equal(requestIdFor("2026-11-01"), "round-2026-11-01");
    assert.equal(requestIdFor("2026-11-01", "probe"), "round-2026-11-01-probe");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
