// shadow-health-parity.test.mjs — shadow 对拍闸门(票 #229 T5 任务书③:健康轮 faux 位等价)。
// 跑 shadow-diff.mjs CLI 全程:OLD=旧管线 replay(罐装世界断点进,零网络),NEW=run-health
// --from-phase TRIAGE --to-phase RETRO;断言 VERDICT SAME(可比工件闭集+台账行,归一化窄面
// 见 shadow-diff.mjs 头注)。运行期异常/任一面失败=测试红(exit 3 语义透传)。
// 这是 spec 定案 2 安全轨的自动闸门:shadow 期每轮 cron 后人工跑一次同面;切流前本测+全量
// 测试套必须绿(SHADOW-RUNBOOK §切流门槛)。
import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { isUndeclaredNewFile } from "../shadow-diff.mjs";

const execFileP = promisify(execFile);
const HERE = import.meta.dirname;

test("残余哨判定(复核 P2-2 正例):闭集/白名单放行,未声明新面捕获", () => {
  for (const ok of ["03-triage-hypotheses.json", "05-deep-verdicts.json", "gates.json", "01-probe-summary.json", "02-verify-survivors.json", "09-budget.json", ".v2-claim.json"])
    assert.equal(isUndeclaredNewFile(ok), false, `${ok} 应放行`);
  for (const bad of ["10-anything.json", "retro-note.md", "state2.json"])
    assert.equal(isUndeclaredNewFile(bad), true, `${bad} 应捕获为未声明新面`);
});

test("shadow 对拍:旧 replay vs v2 checkpoint 任务,可比面全 SAME(位等价闸门)", async () => {
  const d = new Date();
  // 旧轮 id 形状律硬约束 YYYY-MM-DD-HHMM-health(bad_round 判例):秒位不可入 id;
  // 世界各自隔离 tmp,同分钟重跑无冲突。
  const id = `${d.toISOString().slice(0, 10)}-${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}-health`;
  const r = await execFileP("node", [path.join(HERE, "..", "shadow-diff.mjs"), id], { cwd: path.resolve(HERE, "..", ".."), maxBuffer: 8 * 1024 * 1024 });
  assert.match(r.stdout, /VERDICT SAME\(old\.exit=0 new\.exit=0\)/, `对拍非全 SAME:\n${r.stdout}`);
  for (const f of ["03-triage-transcript.jsonl", "05-deep-verdicts.json", "07-synth-report.md", "08-anchor-sweep.json", "gates.json", "ledger.md"])
    assert.ok(new RegExp(`^SAME\\s+${f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`, "m").test(r.stdout), `关键工件须 SAME:${f}`);
}, { timeout: 240_000 });
