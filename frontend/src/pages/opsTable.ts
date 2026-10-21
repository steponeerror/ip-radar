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

// 台账行 cells 命名索引(终审 standards 重构):裸位序取值(cells[4] 等)改
// 命名,防列漂移。由 LEDGER_COL_KEYS 派生:UI 六基列对 markdown 台账五列
// (T4 冻结表头「日期|轮次|model|用量|备注」),usage 与 cost 同居「用量」
// 列位(splitUsage 拆串),故 cost 之后各列的 cells 位序比基列位序前移一位
// (time/round/model/usage/cost/note → 0/1/2/3/3/4)。重排 LEDGER_COL_KEYS
// 时此处自动跟随,不再靠人手同步两处魔数。
export const LEDGER_CELL: Record<(typeof LEDGER_COL_KEYS)[number], number> = (() => {
  const idx = {} as Record<(typeof LEDGER_COL_KEYS)[number], number>;
  let shift = 0;
  LEDGER_COL_KEYS.forEach((k, i) => {
    if (k === "cost") shift = 1; // cost 与 usage 同列位(「用量」串拆两 UI 列)
    idx[k] = i - shift;
  });
  return Object.freeze(idx);
})();

// 统一件表格类(#149 从 OpsCockpit 收编入此:两表同一处施加,右对齐不漂移)。
// 视觉门 2026-10-21(低3):表头一律不折行(「结果码」两字折行/时间单元格
// 「6小时前」折行凸行)——列宽不足时由宽内容列(备注/包)内部换行吸收,
// 表头与窄内容零折行;表容器自有 overflow-auto 横滚兑底。
const NUMERIC_COLS = new Set(["usage", "cost"]);
export const thClass = (k: string) =>
  `px-3 py-1.5 font-medium whitespace-nowrap${NUMERIC_COLS.has(k) ? " text-right" : ""}`;
export const tdNumClass = "px-3 py-1.5 text-right";
// 时间单元格:相对时间短语(「6小时前」)不折行(title 挂完整戳由调用方施加)
export const tdTimeClass = "px-3 py-1.5 whitespace-nowrap";

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

// 用量人话化(视觉门 2026-10-21 低2):台账用量串裸 key=value
// 「in=3076 out=854 total=3930」→「in 3076 · out 854 · 计 3930」(表体
// font-mono 轨);原始串由调用方挂 title(证据不灭失)。未知形状回原文
// (宁少算:不猜,原文即证据;失败行「—」等非形状原样透传)。
export function usageText(t: TFn, raw: string): string {
  const m = raw.match(/^in=(\d+) out=(\d+) total=(\d+)$/);
  return m ? t("ops.usage.fmt", { in: m[1], out: m[2], total: m[3] }) : raw;
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
