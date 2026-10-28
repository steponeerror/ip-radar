// .e2e-env.mjs — health-e2e 的 env 先行件(票 #228 修复⑥)。
// 为什么必须是「首个 import」的副作用模块:EVAL_PY 是 shared.mjs 模块加载期常量
// (ops/agent/tools/shared.mjs:43 `process.env.OPS_EVAL_PY ?? <真 venv python>`),
// seedWorld 在测试体内设 env 时模块树早已求值——首跑曾因此跑真 backend python
// 锚巡检(非 hermetic,断言降级面也失真)。ESM 按源序求值依赖,把本模块放在
// import 列表首位,后续经 OPS_HEALTH_ROUND → steps → shared 的链条读到的即是 stub。
// stub=永败 py(裸失败:stderr 一行+exit 1)→ anchorSweepCli 走 infra 信封
// → ANCHOR_SWEEP 降级旁路(旧 selftest-pipeline ⑫「stub 无旗标分发→sweep 面同死」
// 同契约)。每跑重建,旧进程残留不复活。
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const dir = path.join(os.tmpdir(), "v2-health-e2e-stubs");
fs.rmSync(dir, { recursive: true, force: true });
fs.mkdirSync(dir, { recursive: true });
const stub = path.join(dir, "py-fail");
fs.writeFileSync(stub, "#!/usr/bin/env bash\necho 'e2e stub: anchor/matrix face dead' >&2\nexit 1\n");
fs.chmodSync(stub, 0o755);
process.env.OPS_EVAL_PY = stub;
