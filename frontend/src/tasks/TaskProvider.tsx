import { useEffect, useRef, useState, type ReactNode } from "react";
import { getTasks, subscribeTasks, type TaskEvent, type TaskState, type BatchState } from "../api";
import {
  enqueueBatch as apiEnqueueBatch, enqueueSingle as apiEnqueueSingle,
  cancelTask as apiCancelTask, cancelBatch as apiCancelBatch, pauseBatch, resumeBatch,
} from "../api";
import { TasksContext, type TasksCtxValue, type TaskConnection } from "./useTasks";
import {
  applyEvent, applyResync, beginResync, initialTaskEventsState, type TaskEventsState,
} from "./taskEvents";

// 事件归并本体(applyEvent/seedLogs/SAW_EVENTS 竞态律/LOG_KEEP_LINES)是
// ./taskEvents.ts 的纯函数(票 #292);本组件只剩 React 壳:ref 持单份归并
// 态、新态镜像进 useState、resync/subscribe 生命周期、401/onUnauthorized、
// context value 组装。归并律的行为基线 = __tests__/taskEvents.test.ts +
// 本目录四个 TaskProvider/progress 测试(零改动跑绿)。

export function TaskProvider({ children, onUnauthorized }: {
  children: ReactNode;
  onUnauthorized?: () => void;
}) {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [batch, setBatch] = useState<BatchState | null>(null);
  // ops 轮 task_log 行(task_id → 末 LOG_KEEP_LINES 行);快照不含此面(SSE
  // 即时流)。
  const [logs, setLogs] = useState<Record<string, string[]>>({});
  // U8:SSE 流连接态。onerror → reconnecting,恢复(onopen)→ connected;
  // 初始 connected(宁少算:首连失败也会先经 onerror 置位,不预支连接中文案)。
  const [connection, setConnection] = useState<TaskConnection>("connected");
  // 归并态壳:tasks 字典/batch/logs/sseSaw 单份(sseSaw 非 React 面,纯函数
  // 状态里带着,竞态语义见 taskEvents.ts)。
  const stateRef = useRef<TaskEventsState>(initialTaskEventsState());

  // 把纯函数新态镜像进 React:子引用没变的面不 setState —— 与原实现逐分支
  // setTasks/setBatch/setLogs 的调用面等价(如 task_log 只碰 logs)。
  const commit = (prev: TaskEventsState, next: TaskEventsState) => {
    stateRef.current = next;
    if (next.tasks !== prev.tasks) setTasks(Object.values(next.tasks));
    if (next.batch !== prev.batch) setBatch(next.batch);
    if (next.logs !== prev.logs) setLogs(next.logs);
  };

  const apply = (e: TaskEvent) => {
    const prev = stateRef.current;
    const next = applyEvent(prev, e);
    if (next !== prev) commit(prev, next);
  };

  useEffect(() => {
    let alive = true;
    const resync = async () => {
      const prev = stateRef.current;
      const begun = beginResync(prev); // this fetch wins unless SSE interleaves
      stateRef.current = begun; // 只可能清 sseSaw(非 React 面,无需镜像)
      try {
        const snap = await getTasks();
        if (!alive) return;
        const cur = stateRef.current;
        // fetch 期间 SSE 落过状态事件 → sseSaw=true → applyResync 原样返回
        // (快照更旧,整体作废,fresher wins)。
        const next = applyResync(cur, snap);
        if (next !== cur) commit(cur, next);
      } catch (e) {
        // 会话中 401:踢回登录页(卸壳即断 SSE 重连);其余错误吞下 —
        // 之前这里是未处理 rejection。
        if ((e as { status?: number }).status === 401) {
          onUnauthorized?.();
          return;
        }
      }
    };
    // 无条件订阅:本 provider 只在 AdminPage 登录后挂载,挂载即已验证 admin
    // 会话,无匿名访客面;demo 闸(/api/version 的 public_demo 只认 ADMIN_IPS
    // peer、不认 admin cookie)会误闸非白名单 IP 的管理员。会话中途死亡由
    // subscribeTasks 的 onerror → adminMe 探测兜底(onUnauthorized 踢回登录,
    // 卸壳即断流)。
    resync();
    // onopen = (重)连接成功:先清 U8 断线态再重拉快照(初始连接同经此路径);
    // 第四参 onerror = 流断开、浏览器原生重连中 → 置 reconnecting。
    const unsub = subscribeTasks(
      apply,
      () => { setConnection("connected"); resync(); },
      onUnauthorized,
      () => setConnection("reconnecting"),
    );
    return () => { alive = false; unsub(); };
  }, []);

  const value: TasksCtxValue = {
    tasks, batch, connection, logs,
    enqueueSingle: apiEnqueueSingle,
    enqueueBatch: apiEnqueueBatch,
    cancelTask: apiCancelTask,
    cancelBatch: apiCancelBatch,
    pause: pauseBatch,
    resume: resumeBatch,
  };

  return <TasksContext.Provider value={value}>{children}</TasksContext.Provider>;
}
