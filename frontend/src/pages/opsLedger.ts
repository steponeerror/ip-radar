// opsLedger.ts — 台账 markdown 表解析与轮次关联小件(票 #142)。
// 台账行 = | 日期 | 轮次 | model | 用量 | 备注 |(lib.sh ledger_append 唯一写口);
// 裁决包名 = YYYY-MM-DD-<round>-HHMM.md(agent.mjs 收口时间戳)。两者按
// 「日期+轮型前缀」关联——同日同型多轮不可再细分,宁少算:各自挂列不并错行。

export type LedgerRow = string[];

// 台账 markdown 表(| 日期 | 轮次 | model | 用量 | 备注 |)→ 数据行数组;
// 分隔行(|---|)与 T4 冻结表头行(逐字 lib.sh ledger_append 唯一写口,
// _ops_store.LEDGER_HEADER)都跳过——表头是契约冻结面非数据,解析结果
// 切入表体会成「伪表头」数据行(票 #148 修复);表外行(标题等)不渲染。
// 表头跳过按首表行位置判:文件首条管道行与冻结表头逐字相等即表头;写口
// 幂等保证表头只出现一次(重追加不重建,backend test_ops_store 同口径)。
const FROZEN_HEADER = ["日期", "轮次", "model", "用量", "备注"];

export function ledgerRows(text: string): LedgerRow[] {
  const rows = text
    .split("\n")
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-{3,}:?$/.test(c)));
  if (rows.length > 0 && rows[0].join("|") === FROZEN_HEADER.join("|")) {
    rows.shift();
  }
  return rows;
}

// 用量串 in=1 out=2 total=3 cost=0.00000045 → usage(前三段)/cost(独立段);
// cost 缺段 = null(台账历史行恒有;容缺不伪造)。
export function splitUsage(usage: string): { usage: string; cost: string | null } {
  const m = usage.match(/^(.*?)\s*cost=([\d.]+)$/);
  return m ? { usage: m[1].trim(), cost: m[2] } : { usage, cost: null };
}

// 包名是否挂在该台账行上(日期+轮型前缀匹配;ledger_append 与包时间戳同刻落盘)
export function pkgMatchesRow(pkgName: string, date: string, round: string): boolean {
  return pkgName.startsWith(`${date}-${round}-`);
}
