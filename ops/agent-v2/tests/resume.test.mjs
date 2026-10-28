// resume.test.mjs — kill+resume 复跑变体(票 #225;参考 T0 notes/smoke.mjs,落在 v2 入口形态)
// 流程:子进程 `node entry.mjs <roundId> --crash-after-submit`(submit 承认即 SIGKILL,
// 模型请求在飞/未回,拟小机 OOM)→ 新「进程」(同进程内 runRound,同库同 requestId)
// resume 续跑至 done → 再跑一遍同 requestId:信封一致、usage 不变(幂等零新调用)。
// 真实 GLM 调用 ≤2 次(flash 档,合计 ≈¥0.0001,远低于 ¥1 上限)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { runRound, requestIdFor } from "../entry.mjs";

const V2_DIR = path.resolve(import.meta.dirname, "..");
const ENTRY = path.join(V2_DIR, "entry.mjs");

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

const ANSWER_TOKEN = "V2RES";
const PROMPT = `只回复五个字符:${ANSWER_TOKEN}(不要任何其他内容)`;
const ROUND_ID = `smoke-resume-${new Date().toISOString().slice(0, 10)}`;

function runChild(args) {
  return new Promise((resolveChild) => {
    const child = spawn(process.execPath, [ENTRY, ...args], {
      cwd: V2_DIR,
      env: { ...process.env },
    });
    let out = ""; let err = "";
    child.stdout.on("data", (d) => { out += d; });
    child.stderr.on("data", (d) => { err += d; });
    child.on("exit", (code, signal) => resolveChild({ code, signal, out, err }));
  });
}

test("kill -9 后 entry 复跑:同 requestId 续跑完成;再复跑幂等零新调用", { skip: SKIP }, async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-resume-"));
  const dbPath = path.join(tmp, "agent-v2.sqlite");
  try {
    // phase 1:子进程跑到 submit 承认即自杀(SIGKILL;信封必未产出)
    const crashed = await runChild([ROUND_ID, "--db", dbPath, "--content", PROMPT, "--crash-after-submit"]);
    assert.equal(crashed.signal, "SIGKILL", `崩溃相不对:code=${crashed.code} signal=${crashed.signal} err=${crashed.err}`);

    // phase 2:复跑(同库同 requestId)→ resume 续跑完成
    const env1 = await runRound({ roundId: ROUND_ID, content: PROMPT, dbPath });
    assert.equal(env1.status, "done");
    assert.equal(env1.requestId, requestIdFor(ROUND_ID));
    assert.match(env1.answer, new RegExp(ANSWER_TOKEN));
    assert.ok(env1.usage && Object.keys(env1.usage.models ?? {}).length >= 1, "信封缺 usage.models");

    // phase 3:再复跑同 requestId → 幂等:信封状态/应答一致,usage 零变化
    const env2 = await runRound({ roundId: ROUND_ID, content: PROMPT, dbPath });
    assert.equal(env2.status, "done");
    assert.match(env2.answer, new RegExp(ANSWER_TOKEN));
    assert.deepEqual(env2.usage, env1.usage, "同 requestId 复跑 usage 变化:发生新模型调用");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
