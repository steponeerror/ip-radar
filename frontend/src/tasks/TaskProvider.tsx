import { useEffect, useRef, useState, type ReactNode } from "react";
import { getTasks, subscribeTasks, type TaskEvent, type TaskState, type BatchState } from "../api";
import {
  enqueueBatch as apiEnqueueBatch, enqueueSingle as apiEnqueueSingle,
  cancelTask as apiCancelTask, cancelBatch as apiCancelBatch, pauseBatch, resumeBatch,
} from "../api";
import { TasksContext, type TasksCtxValue, type TaskConnection } from "./useTasks";
import { stagedFrac } from "./progress";

const SAW_EVENTS = new Set(["snapshot", "task", "batch", "done"]);

export function TaskProvider({ children, onUnauthorized }: {
  children: ReactNode;
  onUnauthorized?: () => void;
}) {
  const [tasks, setTasks] = useState<TaskState[]>([]);
  const [batch, setBatch] = useState<BatchState | null>(null);
  // U8:SSE 流连接态。onerror → reconnecting,恢复(onopen)→ connected;
  // 初始 connected(宁少算:首连失败也会先经 onerror 置位,不预支连接中文案)。
  const [connection, setConnection] = useState<TaskConnection>("connected");
  const tasksRef = useRef<Record<string, TaskState>>({});
  // True while a getTasks() fetch is in flight AND an SSE event has since
  // arrived. Prevents a slow getTasks() snapshot (e.g. cold-start first load)
  // from overwriting a fresher SSE event with stale state. Reset at every
  // fetch start so reconnect-time resyncs still apply when no SSE interleaves.
  const sseSawRef = useRef(false);

  // 仅状态事件使能 saw(这类事件会取代快照);task_progress 只携带字节
  // 计数、不含快照会过期的状态 — 下载洪峰期 ~0.15s 一次的 progress tick
  // 若也置位,resync 快照将几乎总被丢弃(SSE 溢出丢掉 done 事件时,UI
  // 中的 batch 会永远卡在 running)。

  const applyEvent = (e: TaskEvent) => {
    if (SAW_EVENTS.has(e.type)) sseSawRef.current = true;
    if (e.type === "snapshot" && e.data) {
      tasksRef.current = Object.fromEntries(e.data.tasks.map((t) => [t.id, t]));
      setTasks(Object.values(tasksRef.current));
      setBatch(e.data.batch ?? null);
    } else if (e.type === "task" && e.task) {
      const prev = tasksRef.current[e.task.id];
      if (prev && (e.task.state === "failed" || e.task.state === "cancelled")) {
        // 终态丢失死亡相位,冻结最后非终态分数供 stagedFrac 读取
        e.task.frozenFrac = stagedFrac(prev);
      }
      tasksRef.current[e.task.id] = e.task;
      setTasks(Object.values(tasksRef.current));
    } else if (e.type === "task_progress" && e.task_id) {
      const ex = tasksRef.current[e.task_id];
      if (ex) {
        tasksRef.current[e.task_id] = { ...ex, received: e.received, total: e.total };
        setTasks(Object.values(tasksRef.current));
      }
    } else if (e.type === "batch" && e.batch) {
      setBatch(e.batch);
    } else if (e.type === "done") {
      setBatch(e.batch ?? null);
    }
  };

  useEffect(() => {
    let alive = true;
    const resync = async () => {
      sseSawRef.current = false; // this fetch wins unless SSE interleaves
      try {
        const snap = await getTasks();
        if (!alive) return;
        if (sseSawRef.current) return; // an SSE event landed mid-fetch — it's fresher
        tasksRef.current = Object.fromEntries(snap.tasks.map((t) => [t.id, t]));
        setTasks(Object.values(tasksRef.current));
        setBatch(snap.batch);
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
      applyEvent,
      () => { setConnection("connected"); resync(); },
      onUnauthorized,
      () => setConnection("reconnecting"),
    );
    return () => { alive = false; unsub(); };
  }, []);

  const value: TasksCtxValue = {
    tasks, batch, connection,
    enqueueSingle: apiEnqueueSingle,
    enqueueBatch: apiEnqueueBatch,
    cancelTask: apiCancelTask,
    cancelBatch: apiCancelBatch,
    pause: pauseBatch,
    resume: resumeBatch,
  };

  return <TasksContext.Provider value={value}>{children}</TasksContext.Provider>;
}
