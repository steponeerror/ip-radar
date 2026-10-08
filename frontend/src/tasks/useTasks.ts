import { createContext, useContext } from "react";
import {
  enqueueBatch as apiEnqueueBatch, enqueueSingle as apiEnqueueSingle,
  cancelTask as apiCancelTask, cancelBatch as apiCancelBatch, pauseBatch, resumeBatch,
  type TaskState, type BatchState,
} from "../api";

export type TasksCtxValue = {
  tasks: TaskState[];
  batch: BatchState | null;
  enqueueSingle: typeof apiEnqueueSingle;
  enqueueBatch: typeof apiEnqueueBatch;
  cancelTask: typeof apiCancelTask;
  cancelBatch: typeof apiCancelBatch;
  pause: typeof pauseBatch;
  resume: typeof resumeBatch;
};

// 组件(TaskProvider)拆在 ./TaskProvider.tsx:本文件只留 context + hook,
// 避免 react-refresh/only-export-components(组件与 hook 混导出)。
export const TasksContext = createContext<TasksCtxValue | null>(null);

export function useTasks(): TasksCtxValue {
  const c = useContext(TasksContext);
  if (!c) throw new Error("useTasks must be used within TaskProvider");
  return c;
}
