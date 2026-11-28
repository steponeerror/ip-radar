// db-lock.mjs — 引擎开库独占锁 + 拒跑诊断(票 #579;裁决=事实包 §2.3 候选1+2:锁为主,
// 查库只作拒跑时的诊断报告,不单独立守卫)。
//
// 为什么锁:pi-durable 1.4.0 无任何跨进程互斥(无租约/心跳/owner 列/条件领取,
// storage.js:588-592 领取=无条件 upsert),且第二个进程 Harness.open 会把库里全部
// running 任务改回 pending 并 restarts+1(scheduler.js:190-198,崩溃恢复语义=「开库
// 即抢」)——cron 在跑时手触开库=两边同时跑同一轮(事实包-480-558撞窗 §2.1)。框架
// 层无解,守卫做在 ops 层:同一库同一时刻只许一个引擎进程,锁住整个进程生命周期
// (进程死锁即释,无残锁协议面)。
//
// 做法(spawn util-linux flock(1);queue-lock.mjs 同款先例:node 无内置 flock,零新
// 依赖红线排除锁包,flock(1) 与 fcntl.flock 同一 flock(2) 锁域,生产镜像 util-linux
// 在位):入口进程第一件事调 withDbLock()——env 无 DB_LOCK_HELD 标记 → 本进程只当
// 代理,spawn `flock [-n|-w 秒] <db>.lock node <原 argv>` 重拉自己(stdio 透传、退出
// 码透传、execArgv 透传保 --max-old-space-size 面),env 给子进程打 DB_LOCK_HELD
// 标记;flock 进程活着=锁在手,业务子进程跑完 flock 才退。
//   -E 16 把「锁冲突」与「业务退出码」分离:flock 缺省冲突 rc=1,与信封 failed
//   rc=1 撞面——代理循环会把业务失败误判成可重试冲突,反复重拉整轮。-E(util-linux
//   ≥2.23,2013 起)使冲突恒 16,与业务码 0/1/2/3 零交集。
//
// 手动/cron 判别=DB_LOCK_WAIT_ENV 旋钮(环境变量;票面授权「用环境变量写明」):
//   缺省(手动)等 0 秒=当场拒(flock -n);cron 侧由 deploy/ops-cron-v2*.sh 出口
//   900(票面「缺省 900 秒」落在 cron 脚本侧),冲突时每 DB_LOCK_POLL_S 秒一步重试
//   (flock -w 步长,不一次性挂满 900——每步重估剩余额,超限即拒)。旋钮非法值按 0
//   处理(拒跑方向安全;旋钮面只来自 cron 脚本/运维,不值得 usage 错面)。
//
// 拒跑出口:stderr 一句话(含只读查得的在飞任务;查不到=写「查不到」,不猜——哲学②
// 无证据即无话),退出码 EXIT_DB_LOCKED=16(固定非零;ENVELOPE.md 码表新行;stdout
// 零信封——拒跑发生在轮次开始之前,属 launcher 层,与用法错 exit 2 不发 JSON 同族)。
//
// 锁面自身故障 ≠ 锁冲突(#579 返工建议3/7):flock 二进制起不来、锁文件打不开都退出
// 3(ENVELOPE 运行期异常),不当 16——16 是「有锁、别人持有」的语义,fail-closed 也
// 要报对原因;且 flock 缺席时不再按 16 空转等待额(cron 侧 900s 白等)。
//
// 标记只活一代(#579 返工建议6):held 进程 spawn 的子进程不带 DB_LOCK_HELD 标记,
// 否则孙子进程会自认已持锁、裸开库。
//
// 循环引用面:本模块 import resolveDbPath 自 entry.mjs(entry 又 import withDbLock
// 自本模块)——两侧都只在函数体内取用(函数声明提升,模块体求值期不触),与既有
// entry↔run-add↔tasks 循环(见 entry.mjs 分派表注)同款安全类。

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { resolveDbPath } from "./entry.mjs"; // 库落位单源(#579 任务书:锁文件与 resolveDbPath 同源)

// env 键名:「已持锁」标记(flock 包装的业务子进程由此识别自己,不再代理)与
// 「cron 侧等锁上限秒数」旋钮(缺省缺席=手动侧等 0 秒当场拒)。
export const DB_LOCK_HELD_ENV = "OPS_V2_DB_LOCK_HELD";
export const DB_LOCK_WAIT_ENV = "OPS_V2_DB_LOCK_WAIT_S";
// cron 侧重试步长(秒):每步 flock -w 一步,超限即拒(票面「每 15 秒试一次」)
export const DB_LOCK_POLL_S = 15;
// 锁冲突退出码(固定非零;错误码表闭集词=DB_LOCKED_CODE,error-codes.mjs 15→16)
export const EXIT_DB_LOCKED = 16;
export const DB_LOCKED_CODE = "db_locked";
// 锁文件后缀(<dbPath>.lock;queue-lock.mjs QUEUE_LOCK_SUFFIX 同形)
export const DB_LOCK_SUFFIX = ".lock";

// 在飞状态闭集:pi-durable LIVE_STATUSES 原样(scheduler.js:10;open 扫描面
// scheduler.js:184-187 同集)——诊断口径与「开库即抢」的改写面一字不差。漏一个词,
// 拒跑消息就少报一类在飞任务(变异③靶)。
export const LIVE_TASK_STATUSES = ["pending", "running", "waiting", "sleeping", "completing"];

export function dbLockPath(dbPath) {
  return `${dbPath}${DB_LOCK_SUFFIX}`;
}

// 锁目标库落位:CLI 显式 --db 优先(四入口共有的旗标面,与各 launcher flag("db")
// 同语义:首个 --db 取值),否则走 resolveDbPath(env)(OPS_V2_DB > DOCS_ROOT/ops/
// agent-v2.sqlite > 仓根 docs——与业务开库完全同一条推导链,锁和库不许漂)。
export function dbPathFromArgv(argv = process.argv, env = process.env) {
  const i = argv.indexOf("--db");
  const explicit = i >= 0 ? argv[i + 1] : undefined;
  return explicit ?? resolveDbPath(env);
}

// 拒跑诊断:只读打开库(file:…?mode=ro URI,node:sqlite 原生支持,node 22.23 实测;
// WAL 库只读打开不与写方抢锁)查在飞任务,返回 [{id,kind,status,round,startedAt}]
// (round=record.input.roundId,startedAt=record.state.startedAt——事务层在首次转
// running 时写,transaction.js:730-742)。任何查不了的形态(库不存在、被锁、表缺席、
// record 非 JSON)= null/字段留空,写「查不到在飞任务」,不猜。
export function liveTasksReport(dbPath) {
  if (!fs.existsSync(dbPath)) return null; // 库缺席:首个引擎还没建库,无从查起
  let db;
  try {
    db = new DatabaseSync(`${pathToFileURL(dbPath).href}?mode=ro`);
  } catch {
    return null; // 打不开(被写方长事务锁死等):不猜
  }
  try {
    const ph = LIVE_TASK_STATUSES.map(() => "?").join(",");
    const rows = db.prepare(
      `SELECT id, kind, status, record FROM tasks WHERE status IN (${ph}) ORDER BY id`
    ).all(...LIVE_TASK_STATUSES);
    return rows.map((r) => {
      let round, startedAt, kind = r.kind;
      try {
        const rec = JSON.parse(r.record);
        round = rec?.input?.roundId ?? null;
        startedAt = rec?.state?.startedAt ?? null;
      } catch { /* record 非 JSON:字段留空,不猜 */ }
      try { kind = JSON.parse(r.kind); } catch { /* kind 非 JSON 编码:原样(pi-durable 列面=encodeIndexedString,storage.js:10) */ }
      return { id: r.id, kind, status: r.status, round, startedAt };
    });
  } catch {
    return null; // 表缺席(空库/半建)等 schema 面:不猜
  } finally {
    try { db.close(); } catch { /* 已关 */ }
  }
}

// 一跳代理:spawn `flock [-E 16] [-n|-w 秒] <lock> node [execArgv] <argv>`,stdio
// 透传。resolve 值 {rc, error}:flock 进程退出码(锁冲突=EXIT_DB_LOCKED;业务退出码
// 原样;信号死=本进程重拉同信号,flock(1) 对信号死子进程的同款判定,实测 rc=137
// 判例);spawn 自身失败(flock 不在 PATH 等)= rc:-1 + error(与锁冲突分道,返工建议3)。
function spawnFlock({ lockPath, argv, env, waitS }) {
  return new Promise((resolve) => {
    const args = [
      "-E", String(EXIT_DB_LOCKED),
      ...(waitS > 0 ? ["-w", String(waitS)] : ["-n"]),
      lockPath,
      process.execPath,
      ...process.execArgv, // node 启动旗标透传(cron 面 --max-old-space-size=256 不许在代理跳丢失)
      ...argv,
    ];
    const child = spawn("flock", args, {
      stdio: "inherit",
      env: { ...env, [DB_LOCK_HELD_ENV]: "1" }, // 标记:子进程直接跑业务,不再代理
    });
    let spawnErr = null;
    child.on("error", (e) => { spawnErr = e; resolve({ rc: -1, error: e }); }); // flock 起不来(ENOENT 等)=锁面自身故障,单独出口(返工建议3),不当 16
    child.on("close", (code, signal) => {
      if (signal) process.kill(process.pid, signal); // 信号死透传(SIGKILL 崩溃缝面:外层观察者仍见信号;锁随 flock 进程死已释放)
      resolve({ rc: code ?? EXIT_DB_LOCKED, error: spawnErr });
    });
  });
}

function waitSecondsFromEnv(env) {
  const n = Number(env[DB_LOCK_WAIT_ENV] ?? "");
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

// 入口助手(所有引擎入口第一件事调它):见文件头注。返回
//   {status:"held", result}  —— 已在 flock 业务子进程内,result=run() 的返回值(调用方
//                              通常不需要:退出码由业务体自己经 process.exitCode 置)
//   {status:"proxied", code} —— 业务子进程跑完,退出码已透传到本进程
//   {status:"refused", code, message, live} —— 拿不到锁,stderr 已写、退出码已置 16
export async function withDbLock(run, opts = {}) {
  const env = opts.env ?? process.env;
  if (env[DB_LOCK_HELD_ENV] === "1") {
    // 标记只活一代(返工建议6):held 进程再 spawn 的子进程不许继承标记,否则孙子进程
    // 会自认已持锁、裸开库(评审指认:env 参数隔离的测试面不受影响——非 process.env
    // 时删不着也不该删)。
    if (env === process.env) delete process.env[DB_LOCK_HELD_ENV];
    return { status: "held", result: await run() }; // 锁由 flock 进程持有到其退出(=引擎进程全生命周期),直接跑业务
  }
  const argv = opts.argv ?? process.argv.slice(1); // 脚本路径+参数(flock 后原样重放面)
  const dbPath = opts.dbPath ?? dbPathFromArgv(opts.fullArgv ?? process.argv, env);
  const lockPath = dbLockPath(dbPath);
  const waitS = opts.waitS ?? waitSecondsFromEnv(env);
  const deadline = Date.now() + waitS * 1000;
  fs.mkdirSync(path.dirname(lockPath), { recursive: true }); // 锁文件父目录惰性首建(flock O_CREAT 需父目录在场;queue-lock appendQueueRowCore 同判例)
  try {
    fs.closeSync(fs.openSync(lockPath, "a")); // 锁文件预开检查(返工建议7):flock O_CREAT 打不开(权限/盘满等)会以自身 rc=1 退出、与业务失败撞面——先探测,单独出口
  } catch (e) {
    const msg = `锁文件打不开:${lockPath}:${e?.message ?? e}`;
    process.stderr.write(`[v2-db-lock] ${msg}\n`);
    process.exitCode = 3; // ENVELOPE 运行期异常:锁面自身故障,非锁冲突
    return { status: "refused", code: "lock_file_unopenable", message: msg };
  }
  for (;;) {
    const remainingS = Math.ceil((deadline - Date.now()) / 1000);
    const chunkS = remainingS <= 0 ? 0 : Math.min(DB_LOCK_POLL_S, remainingS);
    const { rc, error } = await spawnFlock({ lockPath, argv, env, waitS: chunkS });
    if (rc === -1) {
      // flock 起不来(返工建议3):锁面自身故障,立刻退出 3,不当锁冲突 16 空转等待额
      const msg = `锁工具 flock 起不来:${error?.message ?? error}`;
      process.stderr.write(`[v2-db-lock] ${msg}\n`);
      process.exitCode = 3;
      return { status: "refused", code: "flock_unavailable", message: msg };
    }
    if (rc !== EXIT_DB_LOCKED) {
      process.exitCode = rc; // 业务/信号面退出码透传(0=completed;1/2/3=ENVELOPE 码表;137=被杀)
      return { status: "proxied", code: rc };
    }
    if (remainingS <= 0) {
      const live = liveTasksReport(dbPath);
      const lines = (live ?? []).map((t) =>
        `id=${t.id} kind=${t.kind} status=${t.status} round=${t.round ?? "?"} startedAt=${t.startedAt ?? "?"}`);
      const msg = `拒绝跑轮:另一引擎进程持有库锁(${lockPath},等了 ${waitS} 秒没等到)`
        + (live === null
          ? ";在飞任务:查不到(库缺席或只读打不开),不猜"
          : live.length
            ? `;在飞任务:${lines.join(" | ")}`
            : ";在飞任务:无 live 记录(持锁方可能正处在开库间隙)");
      process.stderr.write(`[v2-db-lock] ${msg}\n`);
      process.exitCode = EXIT_DB_LOCKED;
      return { status: "refused", code: DB_LOCKED_CODE, message: msg, live };
    }
    // 冲突但还有等待额:DB_LOCK_POLL_S 步长后再试(cron 侧;手动侧 waitS=0 恒走 -n 即拒)
  }
}
