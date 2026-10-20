// opsLedger.ts — 台账 markdown 表解析与轮次关联小件(票 #142)。
// 台账行 = | 日期 | 轮次 | model | 用量 | 备注 |(lib.sh ledger_append 唯一写口);
// 裁决包名 = YYYY-MM-DD-<round>-HHMM.md(agent.mjs 收口时间戳)。两者按
// 「日期+轮型前缀」关联——同日同型多轮不可再细分,宁少算:各自挂列不并错行。

export type LedgerRow = string[];

// 台账 markdown 表(| 日期 | 轮次 | model | 用量 | 备注 |)→ 行数组;
// 分隔行(|---|)跳过;表外行(标题等)不渲染(节标题已在面内)。
export function ledgerRows(text: string): LedgerRow[] {
  return text
    .split("\n")
    .filter((l) => l.trim().startsWith("|"))
    .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
    .filter((cells) => !cells.every((c) => /^:?-{3,}:?$/.test(c)));
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
