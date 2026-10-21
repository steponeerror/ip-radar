import { describe, it, expect } from "vitest";
import { ledgerRows } from "../opsLedger";

// 票 #148:台账解析小件纯函数单测——「冻结表头行被跳过」钉死。伪表头 bug
// 根因:过往轮次表取「末 N 行」时把解析结果首行(T4 冻结表头
// | 日期 | 轮次 | model | 用量 | 备注 |)一并切入表体。台账表头是 lib.sh
// ledger_append 唯一写口的契约冻结面(_ops_store.LEDGER_HEADER 逐字),前端
// 解析跳过它,行数组只含数据行。
const LEDGER_MD = [
  "# 运营轮次台账",
  "",
  "| 日期 | 轮次 | model | 用量 | 备注 |",
  "|---|---|---|---|---|",
  "| 2026-10-19 | health | glm-5.3-flash | in=10 out=2 total=12 cost=0.00000012 | tools=1 sdk=pi-agent-core |",
  "| 2026-10-20 | discover | glm-4.7 | in=1 out=2 total=3 cost=0.00000045 | tools=2 sdk=pi-agent-core |",
].join("\n");

describe("ledgerRows — 冻结表头行被跳过(票 #148 伪表头修复)", () => {
  it("表头行不出现在解析结果:行数组只含数据行", () => {
    const rows = ledgerRows(LEDGER_MD);
    expect(rows).toHaveLength(2);
    // 表头行(逐字 T4 冻结串)不得混入任何位置
    expect(rows).not.toContainEqual(["日期", "轮次", "model", "用量", "备注"]);
    expect(rows[0]).toEqual([
      "2026-10-19", "health", "glm-5.3-flash",
      "in=10 out=2 total=12 cost=0.00000012", "tools=1 sdk=pi-agent-core",
    ]);
  });

  it("仅表头(空台账首建态)→ 零数据行;分隔行/表外行恒不渲染", () => {
    expect(ledgerRows("| 日期 | 轮次 | model | 用量 | 备注 |\n|---|---|---|---|---|\n")).toEqual([]);
    expect(ledgerRows("# 运营轮次台账\n\n正文行不带管道符\n")).toEqual([]);
  });
});
