import type { TaskEvent, TaskState, BatchState, TasksSnapshot } from "../api";
import { stagedFrac } from "./progress";

// 票 #292:任务事件归并本体,自 TaskProvider.tsx 抽成不依赖 React 的纯函数
// reduce(态, 事件)→新态。TaskProvider 只持 ref 壳并把新态镜像进 useState。
// 契约真源 = backend/ipdb/_tasks.py(Task.to_dict/Batch.to_dict)+ api.ts
// 的 TaskEvent 联合类型(可选字段容缺,各分支守卫自行窄化)。

// task_log 保留末 N 行/任务(ops 轮进度流;源任务无此事件)。有界防内存
// 无限增长——证据本体在包/台账,这里只是即时进度面。单源常数:与
// backend/ipdb/_tasks.py 的 _OPS_LOG_KEEP 同值(两端窗口一致防播种面反复
// 增缩);机读对拍钉子 = __tests__/taskEvents.test.ts(后端另一半钉子在
// backend/tests/test_ops_rounds.py:949)。
export const LOG_KEEP_LINES = 200;

// 仅状态事件使能 sseSaw(这类事件会取代快照);task_progress/task_log 刻意
// 不入:进度 tick ~0.15s 一次,若也置位,resync 快照几乎总被丢弃(SSE 溢出
// 丢掉 done 事件时,UI 中的 batch 会永远卡在 running)。
const SAW_EVENTS = new Set(["snapshot", "task", "batch", "done"]);

// 归并态。sseSaw = 本次 getTasks fetch 开始后 SSE 是否已见过状态事件
// (true → 慢 fetch 的快照更旧,落地时应作废;见 beginResync/applyResync)。
export type TaskEventsState = {
  tasks: Record<string, TaskState>;
  batch: BatchState | null;
  logs: Record<string, string[]>;
  sseSaw: boolean;
};

export function initialTaskEventsState(): TaskEventsState {
  return { tasks: {}, batch: null, logs: {}, sseSaw: false };
}

// 快照日志尾播种(2026-10-26 修,backend snapshot "logs" 面):中途开页/
// SSE 重连恢复订阅前已发的 task_log 行。合并律 = 尾更长才替换:同 task 的
// append-only 流,后端尾 ⊇ 订阅前收到的行前缀;更短的旧快照(fetch/SSE
// 竞态)不得缩水已收行。尽力而为面,不追加合并防重。
export function seedLogs(
  logs: Record<string, string[]>,
  incoming?: Record<string, string[]>,
): Record<string, string[]> {
  if (!incoming) return logs;
  let changed = false;
  const next = { ...logs };
  for (const [tid, lines] of Object.entries(incoming)) {
    if (!Array.isArray(lines) || lines.length === 0) continue;
    if (!next[tid] || lines.length > next[tid].length) {
      next[tid] = lines;
      changed = true;
    }
  }
  return changed ? next : logs;
}

export function applyEvent(state: TaskEventsState, e: TaskEvent): TaskEventsState {
  const sseSaw = SAW_EVENTS.has(e.type) || state.sseSaw; // 置位先于窄化守卫
  let { tasks, batch, logs } = state;
  let changed = sseSaw !== state.sseSaw;

  if (e.type === "snapshot" && e.data) {
    tasks = Object.fromEntries(e.data.tasks.map((t) => [t.id, t]));
    batch = e.data.batch ?? null;
    logs = seedLogs(state.logs, e.data.logs);
    changed = true;
  } else if (e.type === "task" && e.task) {
    const prev = state.tasks[e.task.id];
    const t = { ...e.task }; // 不改入参事件本体,保持纯函数
    if (prev && (t.state === "failed" || t.state === "cancelled")) {
      // 终态丢失死亡相位,冻结最后非终态分数供 stagedFrac 读取
      t.frozenFrac = stagedFrac(prev);
    }
    tasks = { ...state.tasks, [t.id]: t };
    changed = true;
  } else if (e.type === "task_progress" && e.task_id) {
    const ex = state.tasks[e.task_id];
    if (ex) {
      tasks = { ...state.tasks, [e.task_id]: { ...ex, received: e.received, total: e.total } };
      changed = true;
    }
  } else if (e.type === "task_log" && e.task_id) {
    // 不入 SAW_EVENTS:task_log 不携带快照会过期的任务状态,不抢 resync。
    const next = [...(state.logs[e.task_id] ?? []), e.line ?? ""].slice(-LOG_KEEP_LINES);
    logs = { ...state.logs, [e.task_id]: next };
    changed = true;
  } else if (e.type === "batch" && e.batch) {
    batch = e.batch;
    changed = true;
  } else if (e.type === "done") {
    batch = e.batch ?? null;
    changed = true;
  }

  return changed ? { tasks, batch, logs, sseSaw } : state;
}

// resync 开始(getTasks fetch 发出前):清零 sseSaw —— 本次 fetch 取胜,
// 除非 SSE 在 fetch 途中又插了状态事件(那它更鲜)。
export function beginResync(state: TaskEventsState): TaskEventsState {
  return state.sseSaw ? { ...state, sseSaw: false } : state;
}

// resync 快照落地:fetch 期间 SSE 已见状态事件 → 快照更旧,整体作废;
// 否则与 snapshot 事件同构整表替换 + 播种日志。
export function applyResync(state: TaskEventsState, snap: TasksSnapshot): TaskEventsState {
  if (state.sseSaw) return state; // an SSE event landed mid-fetch — it's fresher
  return {
    tasks: Object.fromEntries(snap.tasks.map((t) => [t.id, t])),
    // batch 归一:快照缺批字段时落 null(React 态口径;旧内联两处
    // 一处可能留 undefined,统一由这里归一)。
    batch: snap.batch ?? null,
    logs: seedLogs(state.logs, snap.logs),
    sseSaw: state.sseSaw,
  };
}
