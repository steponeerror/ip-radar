import type { BatchState, TaskState } from "../api";

// 分段加权模型(spec §3):下载 0→0.5,重建 0.5→1;未知 total 取段内锚点
// (downloading 0.25 / loading 0.5,后者为段起点 — 保证相位边界无下跳)。
export function stagedFrac(t: TaskState): number {
  if (t.state === "done") return 1;
  if (t.state === "failed" || t.state === "cancelled") return t.frozenFrac ?? 0;
  const known = (t.total ?? 0) > 0;
  const frac = known ? Math.min(1, (t.received ?? 0) / (t.total as number)) : null;
  if (t.state === "downloading") return frac !== null ? 0.5 * frac : 0.25;
  if (t.state === "loading") return frac !== null ? 0.5 + 0.5 * frac : 0.5;
  return 0; // queued / throttled / 未知状态兜底
}

export function isIndeterminate(t: TaskState): boolean {
  return (t.state === "downloading" || t.state === "loading") && !(t.total ?? 0);
}

// 批量整体百分比(#486 收编:此前 BatchPanel/BatchMiniBar 各抄一份
// 「各任务 stagedFrac 均值×100」)= 该 batch 各任务的 stagedFrac 均值。
// batchless(单源更新,batch 为 null)取活动任务均值(BatchPanel 原行为);
// batch 在但无可见任务退 batch 维度 done/total(MiniBar 原回退,BatchPanel
// 原退 0 —— 两处统一取更有信息的 done/total,见 impl 报告行为差异注记);
// 两者皆空 → 0。
export function batchOverallPct(
  tasks: TaskState[],
  batch: BatchState | null | undefined,
): number {
  const visible = batch
    ? tasks.filter((t) => t.batch_id === batch.id)
    : tasks.filter(isTaskActive);
  if (visible.length === 0) {
    return batch && batch.total > 0 ? Math.round((batch.done / batch.total) * 100) : 0;
  }
  return Math.round((visible.reduce((s, t) => s + stagedFrac(t), 0) / visible.length) * 100);
}

// ——— 任务状态谓词(#245 收编;此前 SourcesPage/BatchPanel/BatchMiniBar 三处内联散推)———

// 终态(done/failed/cancelled):SourcesPage 防抖重拉计数用。
const TERMINAL_TASK_STATES: readonly TaskState["state"][] = ["done", "failed", "cancelled"];

// 活动(忙碌)任务态 = 四个幂等入队相位(backend _enqueue_one:throttled 期间
// 重复点击为静默 no-op,故 throttled 必须读作忙碌)——收编自 BatchPanel 私有
// ACTIVE_TASK_STATES,与 SourcesPage 行内 busy 同集;不含 ops 轮 running 相位
// (source="ops",轮次不阻查询门)。
const ACTIVE_TASK_STATES: readonly TaskState["state"][] = ["queued", "throttled", "downloading", "loading"];

export function isTaskTerminal(t: TaskState): boolean {
  return TERMINAL_TASK_STATES.includes(t.state);
}

export function isTaskActive(t: TaskState): boolean {
  return ACTIVE_TASK_STATES.includes(t.state);
}

// batch live(运行/暂停):BatchMiniBar 常驻判据;done 不 live(冷加载
// done batch 不庆祝,同 BatchPanel recentlyDone 语义)。
export function isBatchLive(b: BatchState | null | undefined): boolean {
  return b != null && (b.state === "running" || b.state === "paused");
}
