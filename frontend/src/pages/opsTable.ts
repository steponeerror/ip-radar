import type { TFn } from "../i18n";

// opsTable.ts — 运营面表格统一件(票 #148 首创,#149 档案面复用;spec #146
// 「表格统一」)。轮次表与台账表同一套列名与列集(前端中文映射)——台账
// T4 冻结表头(| 日期 | 轮次 | model | 用量 | 备注 |)是契约冻结面(_ops_store
// .LEDGER_HEADER 逐字),UI 措辞与之解耦,前端走 ops.col.* 词条。
// 统一规则:数字列(用量/成本)右对齐(硬规②,类名由组件面施加);时间
// 统一相对时间 + title 完整戳;台账备注 key=value 解析为人话;结果码「—」
// 附 title「台账行不载成败;无证据≠成功」(宁少算哲学的 UI 可读面)。

// 台账基列(两表同集):时间/轮次/模型/用量/成本/备注
export const LEDGER_COL_KEYS = ["time", "round", "model", "usage", "cost", "note"] as const;
// 轮次表追列:结果码/包(台账审计面无此二列:结果码是瞬时内存证据不入
// 审计面;包列属裁决 tab 导航面——#149 裁定不补,两表一致按六基列断言钉死)
export const PAST_EXTRA_COL_KEYS = ["result", "pkg"] as const;

// 统一件表格类(#149 从 OpsCockpit 收编入此:两表同一处施加,右对齐不漂移)
const NUMERIC_COLS = new Set(["usage", "cost"]);
export const thClass = (k: string) =>
  `px-3 py-1.5 font-medium${NUMERIC_COLS.has(k) ? " text-right" : ""}`;
export const tdNumClass = "px-3 py-1.5 text-right";

// 相对时间(词条复用 sources.timeAgo.*——一个概念一个拼写)。dateLike =
// 台账日期(YYYY-MM-DD,精度即日)或包 modified(ISO);title = 证据串
// 原样(完整戳,证据不灭失);不可解析 → 未知(不猜)。
export function relTime(dateLike: string, now: number): {
  key: string;
  vars?: Record<string, string | number>;
  title: string;
} {
  const ms = now - Date.parse(dateLike);
  if (Number.isNaN(ms)) return { key: "sources.timeAgo.unknown", title: dateLike };
  const min = Math.floor(ms / 60000);
  if (min < 1) return { key: "sources.timeAgo.justNow", title: dateLike };
  if (min < 60) return { key: "sources.timeAgo.minutes", vars: { n: min }, title: dateLike };
  const hr = Math.floor(min / 60);
  if (hr < 24) return { key: "sources.timeAgo.hours", vars: { n: hr }, title: dateLike };
  return { key: "sources.timeAgo.days", vars: { n: Math.floor(hr / 24) }, title: dateLike };
}

// 判例文件名日期前缀(#149):判例命名约定 = YYYY-MM-DD-<slug>.md(注入判例
// 与人裁落判例同形,同 OpsPackagesSection.PRECEDENT_REF_RE / 后端 _ops_store
// 命名面)。判例列表 API 只返回文件名(string[],无 size/mtime)——相对时间
// 从文件名日期派生(day 精度,同台账行);无日期前缀名 → null,调用方不显
// 时间(宁少算不猜)。大小无源可得,零后端红线下降级不显(裁 A,2026-10-21)。
export function precDate(name: string): string | null {
  const m = name.match(/^(\d{4}-\d{2}-\d{2})-/);
  return m ? m[1] : null;
}

// 台账备注人话化(票 #148):备注 = lib.sh ledger_append note 参数,写口
// 闭集形状两种——①桥失败面 `spawn error_code=<九词闭集>[; pkg=…/自由消息]`
// (backend _ops_rounds)②agent 收口面 `tools=N[ queue=M] sdk=<id>`
// (agent.mjs)。人话映射;闭集外/未知形状 → null,调用方回原文
// (宁少算:不猜含义,原文即证据)。
export function noteText(t: TFn, note: string): string | null {
  const trimmed = note.trim();
  if (!trimmed) return null;
  const spawn = trimmed.match(/^spawn error_code=([a-z_]+)(?:; (.*))?$/);
  if (spawn) {
    const reasonKey = `ops.note.code.${spawn[1]}`;
    const reason = t(reasonKey);
    if (reason === reasonKey) return null; // error_code 九词闭集外不猜
    const head = t("ops.note.spawnFail", { reason });
    const tail = spawn[2]?.startsWith("pkg=") ? spawn[2].slice(4) : spawn[2];
    return tail ? `${head} · ${tail}` : head;
  }
  const tools = trimmed.match(/^tools=(\d+)(?: queue=(\d+))? sdk=([\w.-]+)$/);
  if (tools) {
    const parts = [t("ops.note.tools", { n: Number(tools[1]) })];
    if (tools[2]) parts.push(t("ops.note.queue", { n: Number(tools[2]) }));
    parts.push(`sdk=${tools[3]}`); // 标识符原样(mono 数据面)
    return parts.join(" · ");
  }
  return null;
}
