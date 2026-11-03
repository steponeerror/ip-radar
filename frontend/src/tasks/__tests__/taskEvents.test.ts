import { describe, it, expect } from "vitest";
import { applyEvent, applyResync, beginResync, initialTaskEventsState, LOG_KEEP_LINES, seedLogs } from "../taskEvents";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { TaskState } from "../../api";

// 票 #292:TaskProvider.tsx:58-87 的事件归并本体(applyEvent)抽成不依赖
// React 的纯函数 reduce(态, 事件)→新态。本文件只测纯函数;React 壳的
// 回归基线 = TaskProvider.test/ops/demo(零改动跑绿)。
// 契约真源 = backend/ipdb/_tasks.py(Task.to_dict/Batch.to_dict)+ api.ts
// 的 TaskEvent 联合类型;期望值逐条对拍既有 TaskProvider 测试。

function task(over: Partial<TaskState> & { id: string }): TaskState {
  return { source: "feodo", host: null, state: "queued", error: null, batch_id: null, ...over };
}

describe("task_progress / task_log(增量面,不携带快照会过期的状态)", () => {
  it("task_progress 只改已存在任务:received/total 换新,其余字段与表内其他任务原样", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "downloading" }) });
    s = applyEvent(s, { type: "task", task: task({ id: "t2", state: "loading" }) });
    s = applyEvent(s, { type: "task_progress", task_id: "t1", received: 40, total: 100 });
    expect(s.tasks.t1).toMatchObject({ state: "downloading", received: 40, total: 100 });
    expect(s.tasks.t2).not.toHaveProperty("received");
  });

  it("task_progress 未知任务 id → 整个状态原样返回(引用相等,不新建表)", () => {
    const s0 = applyEvent(initialTaskEventsState(), { type: "task", task: task({ id: "t1" }) });
    expect(applyEvent(s0, { type: "task_progress", task_id: "nope", received: 1, total: 2 })).toBe(s0);
  });

  it("task_log 按任务追加并截留末 LOG_KEEP_LINES 行(205 行 → 200,首 5 行丢弃)", () => {
    let s = initialTaskEventsState();
    for (let i = 0; i < 205; i++) {
      s = applyEvent(s, { type: "task_log", task_id: "t1", line: `line-${i}` });
    }
    expect(s.logs.t1).toHaveLength(200);
    expect(s.logs.t1[0]).toBe("line-5");
    expect(s.logs.t1[199]).toBe("line-204");
  });

  it("task_log 缺 line 视作空串追加", () => {
    const s0 = applyEvent(initialTaskEventsState(), { type: "task_log", task_id: "t1" });
    expect(s0.logs.t1).toEqual([""]);
  });

  it("progress/log 刻意不置 sseSaw;状态事件(snapshot/task/batch/done)置位", () => {
    // 下载洪峰期 progress tick ~0.15s 一次;若也置位,resync 快照几乎总被
    // 丢弃(SSE 溢出丢掉 done 事件时,UI 中的 batch 会永远卡在 running)。
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task_progress", task_id: "t1", received: 1, total: 2 });
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "l" });
    expect(s.sseSaw).toBe(false);
    s = applyEvent(s, { type: "task", task: task({ id: "t1" }) });
    expect(s.sseSaw).toBe(true);
    // 守卫命不中的状态事件同样置位(原实现置位先于窄化守卫)
    s = applyEvent(s, { type: "snapshot" }); // 无 data
    expect(s.sseSaw).toBe(true);
    const s2 = applyEvent(initialTaskEventsState(), { type: "batch" }); // 无 payload
    expect(s2.sseSaw).toBe(true);
  });

  it("仅 sseSaw 翻转时也返回新状态(tasks/logs 子引用复用不变)", () => {
    const s0 = initialTaskEventsState();
    const s1 = applyEvent(s0, { type: "done" }); // 无 payload:只翻 sseSaw + batch 保持 null
    expect(s1).not.toBe(s0);
    expect(s1.sseSaw).toBe(true);
    expect(s1.tasks).toBe(s0.tasks);
    expect(s1.logs).toBe(s0.logs);
  });
});

describe("竞态① 快照后到:慢 resync 快照被新 SSE 状态事件作废", () => {
  it("beginResync 清零 sseSaw;fetch 途中插进状态事件 → applyResync 丢弃快照(引用相等)", () => {
    let s = initialTaskEventsState();
    s = beginResync(s); // fetch 开始:本次 fetch 取胜,除非 SSE 插队
    expect(s.sseSaw).toBe(false);
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "done" }) }); // SSE 插队
    const discarded = applyResync(s, {
      tasks: [task({ id: "stale", state: "queued" })],
      batch: { id: "zz", state: "done", done: 9, total: 9 },
    });
    expect(discarded).toBe(s); // 更旧的快照整体作废,t1 保留
    expect(discarded.tasks.stale).toBeUndefined();
  });

  it("fetch 途中只有 progress/log 刻意不作废快照(F5 场景)", () => {
    let s = initialTaskEventsState();
    s = beginResync(s);
    s = applyEvent(s, { type: "task_progress", task_id: "x", received: 1, total: 2 });
    s = applyEvent(s, { type: "task_log", task_id: "x", line: "l" });
    const next = applyResync(s, { tasks: [task({ id: "s1", state: "done" })], batch: null });
    expect(next).not.toBe(s);
    expect(Object.keys(next.tasks)).toEqual(["s1"]); // 快照整表生效
  });

  it("applyResync 整表替换 tasks、batch,播种 logs(尾更长才换)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "l0" });
    s = beginResync(s);
    const next = applyResync(s, {
      tasks: [task({ id: "t1", state: "running", source: "ops" })],
      batch: { id: "b1", state: "running", done: 0, total: 1 },
      logs: { t1: ["l0", "l1"] }, // 尾更长 → 替换
    });
    expect(Object.keys(next.tasks)).toEqual(["t1"]);
    expect(next.batch).toEqual({ id: "b1", state: "running", done: 0, total: 1 });
    expect(next.logs.t1).toEqual(["l0", "l1"]);
  });
});

describe("竞态② done 丢失:onopen 重连 resync 救回卡死的 running batch", () => {
  it("done 事件直接落位 batch;done 后重连 resync 能换新(sseSaw 已清)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "batch", batch: { id: "b1", state: "running", done: 0, total: 2 } });
    s = applyEvent(s, { type: "done", batch: { id: "b1", state: "done", done: 2, total: 2 } });
    expect(s.batch?.state).toBe("done");
    // 反向:SSE 溢出丢了 done(卡 running)→ 重连 onopen → resync 救回
    let stuck = initialTaskEventsState();
    stuck = applyEvent(stuck, { type: "batch", batch: { id: "b1", state: "running", done: 0, total: 2 } });
    stuck = beginResync(stuck); // onopen 重拉快照:清零 saw,本次 fetch 取胜
    const rescued = applyResync(stuck, {
      tasks: [],
      batch: { id: "b1", state: "done", done: 2, total: 2 },
    });
    expect(rescued.batch?.state).toBe("done");
  });
});

describe("竞态③ 日志播种合并律:尾长才换、短旧快照不缩水", () => {
  it("seedLogs 纯函数:undefined 原样返回;更长尾替换;更短尾不缩水", () => {
    const base = { t1: ["l0", "l1", "l2"] };
    expect(seedLogs(base)).toBe(base); // 无 incoming
    expect(seedLogs(base, { t1: ["only-one-stale-line"] })).toBe(base); // 不缩水
    expect(seedLogs(base, { t1: ["l0", "l1", "l2", "l3"] })).toEqual({ t1: ["l0", "l1", "l2", "l3"] });
    expect(seedLogs({}, { t2: ["n"] })).toEqual({ t2: ["n"] }); // 新 task 播种
  });

  it("seedLogs 跳过空数组/非数组行(事件面尽力而为,容缺不炸)", () => {
    const base = { t1: ["l0"] };
    expect(seedLogs(base, { t1: [] })).toBe(base);
    expect(seedLogs(base, { t1: "not-array" as unknown as string[] })).toBe(base);
  });

  it("fetch/SSE 竞态回放:更短旧快照尾再来 → 已收行不缩水(2026-10-26 修)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, {
      type: "snapshot",
      data: { tasks: [task({ id: "t1", source: "ops", state: "running" })], batch: null, logs: { t1: ["only-one-stale-line"] } },
    });
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "l0" });
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "l1" });
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "l2" });
    // 竞态回放:更短的旧快照尾再来 → 已收 3 行不缩水
    s = applyEvent(s, {
      type: "snapshot",
      data: { tasks: [task({ id: "t1", source: "ops", state: "running" })], batch: null, logs: { t1: ["stale-again"] } },
    });
    expect(s.logs.t1).toEqual(["only-one-stale-line", "l0", "l1", "l2"]);
  });

  it("播种后后续 task_log 照常追加在尾之后(同一条 append-only 流)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, {
      type: "snapshot",
      data: { tasks: [task({ id: "t1", source: "ops", state: "running" })], batch: null, logs: { t1: ["[stage] PROBE start", "[stage] TRIAGE start"] } },
    });
    s = applyEvent(s, { type: "task_log", task_id: "t1", line: "[stage] TRIAGE done gate=PASS" });
    expect(s.logs.t1).toEqual(["[stage] PROBE start", "[stage] TRIAGE start", "[stage] TRIAGE done gate=PASS"]);
  });
});

describe("竞态④ 终态冻结分数 frozenFrac(前端专有,后端不产)", () => {
  it("failed 冻结最后非终态分数:downloading 40/100 → frozenFrac=0.2", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "downloading" }) });
    s = applyEvent(s, { type: "task_progress", task_id: "t1", received: 40, total: 100 });
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "failed", error: "x", received: 40, total: 100 }) });
    expect(s.tasks.t1.frozenFrac).toBe(0.2); // stagedFrac(downloading 0.4) = 0.5*0.4
  });

  it("cancelled 同样冻结(loading 50/100 → 0.75);done 不冻结(=1 由公式给出)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task", task: task({ id: "t2", state: "loading" }) });
    s = applyEvent(s, { type: "task_progress", task_id: "t2", received: 50, total: 100 });
    s = applyEvent(s, { type: "task", task: task({ id: "t2", state: "cancelled" }) });
    expect(s.tasks.t2.frozenFrac).toBe(0.75); // 0.5 + 0.5*0.5
    s = applyEvent(s, { type: "task", task: task({ id: "t2", state: "done" }) });
    expect(s.tasks.t2.frozenFrac).toBeUndefined();
  });

  it("首见即终态(无前态)不冻结", () => {
    const s = applyEvent(initialTaskEventsState(), {
      type: "task",
      task: task({ id: "t1", state: "failed", error: "boot-fail" }),
    });
    expect(s.tasks.t1.frozenFrac).toBeUndefined();
  });

  it("不改入参事件本体(纯函数:冻结分数落在拷贝上)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "downloading" }) });
    const ev = { type: "task" as const, task: task({ id: "t1", state: "failed", error: "x" }) };
    applyEvent(s, ev);
    expect(ev.task.frozenFrac).toBeUndefined(); // 入参未被写入
  });
});

describe("LOG_KEEP_LINES 两端单源(机读对拍 backend/ipdb/_tasks.py)", () => {
  it("前端常数 === 后端 _OPS_LOG_KEEP(正则抽数,后端另一半钉子=test_ops_rounds.py:949)", () => {
    // 注:不可用 new URL(rel, import.meta.url) —— Vite 会静态改写该模式为
    // dev-server URL(http://localhost/@fs/...),fileURLToPath 拒收。
    const pyPath = join(
      dirname(fileURLToPath(import.meta.url)),
      "../../../../backend/ipdb/_tasks.py",
    );
    const m = readFileSync(pyPath, "utf8").match(/_OPS_LOG_KEEP\s*=\s*(\d+)/);
    expect(m).not.toBeNull();
    expect(LOG_KEEP_LINES).toBe(Number(m![1]));
  });
});

describe("applyEvent 归并律(自 TaskProvider 抽出)", () => {
  it("snapshot 事件整表替换 tasks/batch 并播种 logs", () => {
    const s = applyEvent(initialTaskEventsState(), {
      type: "snapshot",
      data: {
        tasks: [
          task({ id: "a", state: "done", batch_id: "b1" }),
          task({ id: "b", source: "tor", state: "downloading", batch_id: "b1" }),
        ],
        batch: { id: "b1", state: "running", done: 1, total: 2 },
        logs: { b: ["[stage] start"] },
      },
    });
    expect(Object.keys(s.tasks)).toEqual(["a", "b"]); // 数组序即插入序
    expect(s.batch).toEqual({ id: "b1", state: "running", done: 1, total: 2 });
    expect(s.logs).toEqual({ b: ["[stage] start"] });
  });

  it("snapshot 缺 batch 字段 → batch=null(线上畸形载荷容缺,类型面 batch 必填)", () => {
    const s = applyEvent(initialTaskEventsState(), {
      type: "snapshot",
      data: { tasks: [task({ id: "a" })] },
    } as Parameters<typeof applyEvent>[1]);
    expect(s.batch).toBeNull();
  });

  it("task 事件按 id upsert:存在替换、新 id 追加(既有键保位)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "queued" }) });
    s = applyEvent(s, { type: "task", task: task({ id: "t2", source: "tor" }) });
    s = applyEvent(s, { type: "task", task: task({ id: "t1", state: "done" }) });
    expect(Object.keys(s.tasks)).toEqual(["t1", "t2"]); // t1 原位更新,不挪尾
    expect(s.tasks.t1.state).toBe("done");
  });

  it("batch 事件直接换 batch;done 事件用 payload(batch ?? null)", () => {
    let s = initialTaskEventsState();
    s = applyEvent(s, { type: "batch", batch: { id: "b1", state: "running", done: 0, total: 3 } });
    expect(s.batch).toEqual({ id: "b1", state: "running", done: 0, total: 3 });
    s = applyEvent(s, { type: "done", batch: { id: "b1", state: "done", done: 3, total: 3 } });
    expect(s.batch?.state).toBe("done");
    s = applyEvent(s, { type: "done" }); // 无 payload → null
    expect(s.batch).toBeNull();
  });

  it("守卫命不中的事件不换引用:task_progress/task_log 缺 task_id 原样返回", () => {
    const s0 = initialTaskEventsState();
    expect(applyEvent(s0, { type: "task_progress", received: 1, total: 2 })).toBe(s0);
    expect(applyEvent(s0, { type: "task_log", line: "x" })).toBe(s0);
  });
});
