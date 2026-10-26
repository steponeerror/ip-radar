// tools/queue-lock.mjs — queue.md 跨进程互斥基建(#139 挂账②;被 registry.mjs
// 面单向消费,不入门面 re-export——C6 29 名导出面不动;零仓依赖自含:临界段
// 子进程不require node_modules,python 侧混语互操测试可直接调起)。
//
// 为什么锁:queue_action(本侧,node agent 轮次中)与 POST /api/ops/ruling 的
// python append_queue(backend/ipdb/_ops_store.py)是同容器两进程对同一
// queue.md 的「读-判重-写」——互窗存在,后写覆盖前写丢行(修前实证:python 两
// 子进程 2×40 并发丢行近半)。原判「单边修是假修」,双边闭环。
//
// 取舍(两案择一,裁定 = spawn util-linux flock(1)):
// - O_EXCL 原子建锁 + 重试退避 + stale 判龄(>30s 强接):被否——python 侧已裁
//   fcntl.flock(内核管锁生死,进程死即释),O_EXCL 协议与 flock 不互锁(python
//   O_CREAT 建锁文件后 node O_EXCL 创建永假),自造 stale 判龄还有「强接误杀
//   活锁」竞态;协议两侧同构才能互认,所以本侧必须同入 flock(2) 锁域。
// - spawn util-linux flock(1):采纳——node 无内置 flock,零新依赖红线排除
//   with-lockfile 等包;flock(1) 与 fcntl.flock 同一 flock(2) 锁域,跨语言
//   互认互斥;python:3.12-slim 生产镜像实测 /usr/bin/flock 2.41.5 在位
//   (util-linux 属 Debian Essential),dev 机/CI 亦在位。
// 代价:父进程无 flock fd 可持,临界段(读-判重-写)必须整体跑在 flock 包装
// 的子进程里(= 本文件 --append 模式),stdout 单行 JSON 回传结果。
//
// 锁路径契约(queue.md 同目录同名 + .lock):与 python QUEUE_LOCK_NAME 对称;
// 两侧各自从自家 queue.md 落位推导(本侧 queueFile 即 host 的 DOCS_ROOT/ops/
// queue.md,tools.mjs:33;python 侧 ops_root()/queue.md),生产形态 P2 桥
// _ops_rounds._round_env 注入 DOCS_ROOT=ops_root().parent 使两落位同址同文件。
// 路径漂移防线 = selftest-contract.mjs「锁路径对拍」哨。
//
// 失败面 fail-closed(铁律②):锁不可得/临界段崩 → 结构化信封 {ok:false,
// code:"io_error"},绝不无锁写——无锁写 = 重开本票要关的竞态窗。

import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFile);
const SELF = fileURLToPath(import.meta.url);

// 锁后缀(与 python QUEUE_LOCK_NAME="queue.md.lock" 同语义:queueFile + ".lock")
export const QUEUE_LOCK_SUFFIX = ".lock";
// flock -w 等待上限:临界段毫秒级,30s = 异常兜底(持锁方僵死时快速失败进
// 人裁信封,不无限挂轮次),非正常等待面
export const LOCK_WAIT_S = 30;

export function queueLockPath(queueFile) {
  return queueFile + QUEUE_LOCK_SUFFIX;
}

// 表头(T4 冻结列面;首行句 #217 T3.5 翻正:原「queue_action 唯一写口」随发现轮
// 两新写口(ENQUEUE 候选行/appendCandidateCard 候选卡,均 PROPOSE)不再真——三写口
// 如实描述;与 python _ops_store.QUEUE_HEADER 跨语言双抄,§14 形制对拍哨钉死不漂移)
const QUEUE_HEADER =
  "# 源生命周期动作队列(三写口:ops 轮 queue_action · 发现轮 ENQUEUE 候选行 · 发现轮候选卡 appendCandidateCard;后两路 action=PROPOSE 一词一拼;行由 host 模板渲染,rationale 只落工件)\n\n"
  + "| 日期 | 轮次 | action | source | predicate | evidence | vetoable |\n"
  + "|---|---|---|---|---|---|---|\n";

// 临界段本体(只在 flock 包装下跑;导出供单测直测,生产消费面恒走
// appendQueueRowLocked):读 queue.md → action+source 判重 → 表头惰性首建 →
// append 行。行模板/去重判式 = T4 冻结形状,与 python append_queue 同构。
export function appendQueueRowCore(payload) {
  let existing = "";
  try { existing = fs.readFileSync(payload.queueFile, "utf8"); } catch { /* 首建 */ }
  const dedupRe = new RegExp(
    `\\| \\d{4}-\\d{2}-\\d{2} \\| [^|]+ \\| ${payload.action} \\| ${payload.source} \\|`);
  const dedup = dedupRe.test(existing);
  if (!dedup) {
    if (!existing) {
      fs.mkdirSync(path.dirname(payload.queueFile), { recursive: true });
      fs.writeFileSync(payload.queueFile, QUEUE_HEADER);
    }
    const ev = payload.evidence
      .map((e) => `${e.call_id}:${e.field}=${JSON.stringify(e.value)}`).join(";");
    const row = `| ${new Date().toISOString().slice(0, 10)} | ${payload.round} `
      + `| ${payload.action} | ${payload.source} | ${payload.predicate ?? "—"} | ${ev} `
      + `| 是(否决=删除本行) |`;
    fs.appendFileSync(payload.queueFile, `${row}\n`);
  }
  return { ok: true, appended: !dedup, dedup };
}

// 生产消费面(registry.mjs queueAction 唯一):临界段经 flock(1) 子进程执行,
// 锁文件 = queueLockPath(payload.queueFile);失败 = fail-closed 信封不写。
export async function appendQueueRowLocked(payload, opts = {}) {
  let r;
  try {
    r = await execFileP(
      "flock",
      ["-w", String(LOCK_WAIT_S), queueLockPath(payload.queueFile),
        process.execPath, SELF, "--append", JSON.stringify(payload)],
      { timeout: (LOCK_WAIT_S + 30) * 1000, maxBuffer: 64 * 1024, env: opts.env });
  } catch (e) {
    const reason = e.code === "ENOENT"
      ? "flock(1) 不可用(镜像须含 util-linux;#139 挂账②锁契约)"
      : e.killed || e.code === "ETIMEDOUT"
        ? `锁等待超时 >${LOCK_WAIT_S}s(持锁方僵死,人裁区排查 queue.md.lock)`
        : `临界段子进程失败 rc=${e.code ?? "?"}:${String(e.stderr ?? e.message).slice(0, 200)}`;
    return { ok: false, code: "io_error", reason };
  }
  const line = r.stdout.trim().split("\n").pop() || "";
  try {
    return JSON.parse(line);
  } catch {
    return { ok: false, code: "io_error", reason: `临界段回传非 JSON:${line.slice(0, 200)}` };
  }
}

// CLI 临界段模式(只经 flock(1) 调起,不作公共 API):结果恒走 stdout 单行
// JSON + rc 0(传输面与业务面分离,父进程统一解析;崩溃也是信封不是裸栈)。
const invokedAsCli = process.argv[1] && path.resolve(process.argv[1]) === SELF;
if (invokedAsCli && process.argv[2] === "--append") {
  let res;
  try {
    res = appendQueueRowCore(JSON.parse(process.argv[3]));
  } catch (e) {
    res = { ok: false, code: "io_error", reason: String(e?.message ?? e).slice(0, 200) };
  }
  process.stdout.write(`${JSON.stringify(res)}\n`);
}
