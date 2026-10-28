// golden-smoke-gated.test.mjs — golden smoke 例 2 例的凭证门面(票 #232;口径裁决 A+C:
// smoke 例驱动 legacy agent.mjs runRound 真模型面,NEW 面 N/A=spec T3 不迁;有凭证时只跑
// OLD 面)。默认零网络零凭证全绿:
//   ① 无凭证面(恒跑,零 API 零网络):runner 选层门——tier=smoke 缺 --smoke 旗标即拒
//      (run-golden.mjs runCase 判例「smoke 层花 API,须 --smoke 显式手跑」);缺省层恒 faux
//      (修正③),smoke 永不误进 CI。
//   ② 凭证面(creds ∧ OPS_GOLDEN_SMOKE=1 双门才跑):OLD 面 run-golden.mjs --smoke --case
//      逐例 GOLDENPASS。比 smoke-glm.test.mjs 多一道显式 env 旗标:golden smoke_health=
//      全源真探测 + 整轮真模型(≈50+ URL 真网络,非单次 ¥0.00004 调用),仅凭证在即自动烧
//      违「默认零网络」——故双门,手跑面与 runner --smoke 语义同构(显式手跑才花 API)。
//      凭证判定布尔零打印(密钥零入日志/报告,任务书纪律)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);
const V2 = path.resolve(import.meta.dirname, "..");
const RUNNER = path.resolve(V2, "..", "agent", "golden", "run-golden.mjs");
const SMOKE_IDS = ["smoke_health", "smoke_discover_threatview_replay"];

// 凭证在否(smoke-glm.test.mjs hasZaiCredential 同型:布尔判定不打印值)
function hasZaiCredential() {
  const authPath = process.env.OPS_AUTH ?? path.join(os.homedir(), ".pi", "agent", "auth.json");
  try {
    const auth = JSON.parse(fs.readFileSync(authPath, "utf8"));
    if (auth?.["zai-coding-cn"]?.key) return true;
  } catch { /* 无 auth.json → 只看 env */ }
  return Boolean(process.env.ZAI_CODING_CN_API_KEY);
}
const OPT_IN = process.env.OPS_GOLDEN_SMOKE === "1";
const SKIP = !hasZaiCredential()
  ? "无 zai 凭证(auth.json/ZAI_CODING_CN_API_KEY 均缺)——SKIP(CI 无凭证判例)"
  : !OPT_IN
    ? "凭证在但未显式 OPS_GOLDEN_SMOKE=1——SKIP(真 API+真网络整轮,显式手跑面)"
    : false;

test("选层门:tier=smoke 缺 --smoke 旗标即拒(缺省层恒 faux;smoke 永不误进 CI)", async () => {
  for (const id of SMOKE_IDS) {
    const r = await execFile(process.execPath, [RUNNER, "--case", id], { timeout: 60_000 }) // 拒面=rc 1,拒值捕为断言面
      .then((o) => ({ code: 0, stdout: o.stdout }), (e) => ({ code: e.code, stdout: e.stdout ?? "" }));
    assert.equal(r.code, 1, `${id} 应 rc=1(实得 ${r.code})`);
    assert.match(r.stdout, new RegExp(`^GOLDENFAIL ${id}: smoke 层花 API,须 --smoke 显式手跑$`, "m"), `选层门文案漂移:\n${r.stdout.slice(0, 400)}`);
  }
});

test("OLD 面 smoke 2 例(真模型;NEW=N/A spec T3 不迁)", { skip: SKIP }, async () => {
  for (const id of SMOKE_IDS) {
    const { stdout } = await execFile(process.execPath, [RUNNER, "--case", id, "--smoke"], { timeout: 300_000, maxBuffer: 32 * 1024 * 1024 });
    assert.match(stdout, new RegExp(`^GOLDENPASS ${id}( fixture=.*)?$`, "m"), `smoke 例 ${id} 未过:\n${stdout.slice(0, 800)}`); // 修正④:smoke 保全 fixture 树,行尾带路径
  }
});
