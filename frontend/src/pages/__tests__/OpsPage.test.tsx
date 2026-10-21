import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { ReactElement } from "react";
import { screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import OpsPage from "../OpsPage";
import { TasksContext, type TasksCtxValue } from "../../tasks/useTasks";
import type { TaskState } from "../../api";
import { renderWithI18n } from "../../test/i18nTestUtils";
import {
  startOpsRound, readOpsLedger, listOpsPrecedents, readOpsPrecedent, exportOpsPrecedents,
  getOpsAgentConfig, putOpsAgentConfig, listOpsPackages,
} from "../../api";
import en from "../../i18n/locales/en.json";
import zhCN from "../../i18n/locales/zh-CN.json";

// P4 admin 第四 tab「运营」(票 #136):渲染面 + 轮次触发 + 台账/判例只读 +
// 导出 + 错误信封可读呈现(不裸抛 code)。裁决包区交互面见
// OpsPackagesSection.test.tsx。任务链面(tasks/logs)经 TasksContext 直供
// ——SSE 装配归 TaskProvider 自有测试。
// 票 #142:二级子 tab 重组(轮次/裁决/档案/设置)+ 驾驶舱卡(状态/耗时/
// 最后一行/可折叠日志/上一轮摘要)+ 过去轮次(台账末 N 行+包目录合并)。
vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    startOpsRound: vi.fn(),
    listOpsPackages: vi.fn().mockResolvedValue([]),
    readOpsPackage: vi.fn(),
    readOpsLedger: vi.fn().mockResolvedValue(""),
    listOpsPrecedents: vi.fn().mockResolvedValue([]),
    readOpsPrecedent: vi.fn(),
    postOpsRuling: vi.fn(),
    exportOpsPrecedents: vi.fn(),
    getOpsAgentConfig: vi.fn(),
    putOpsAgentConfig: vi.fn(),
  };
});

const LEDGER_MD = [
  "# 运营轮次台账",
  "",
  "| 日期 | 轮次 | model | 用量 | 备注 |",
  "|---|---|---|---|---|",
  "| 2026-10-19 | health | glm-5.3-flash | in=10 out=2 total=12 cost=0.00000012 | tools=1 sdk=pi-agent-core |",
  "| 2026-10-20 | discover | glm-4.7 | in=1 out=2 total=3 cost=0.00000045 | tools=2 sdk=pi-agent-core |",
].join("\n");

function wrapCtx(overrides: Partial<TasksCtxValue>, ui: ReactElement): ReactElement {
  const ctx: TasksCtxValue = {
    tasks: [], batch: null, connection: "connected",
    enqueueSingle: vi.fn(), enqueueBatch: vi.fn(), cancelTask: vi.fn(),
    cancelBatch: vi.fn(), pause: vi.fn(), resume: vi.fn(),
    logs: {}, ...overrides,
  };
  return <TasksContext.Provider value={ctx}>{ui}</TasksContext.Provider>;
}

function renderOps(overrides: Partial<TasksCtxValue> = {}) {
  const { rerender, ...rest } = renderWithI18n(
    wrapCtx(overrides, <OpsPage onUnauthorized={vi.fn()} />),
  );
  return {
    ...rest,
    rerenderOps: (next: Partial<TasksCtxValue>) =>
      rerender(wrapCtx(next, <OpsPage onUnauthorized={vi.fn()} />)),
  };
}

const opsTask = (state: TaskState["state"]): TaskState => ({
  id: "t1", source: "ops", host: null, state, error: null, batch_id: null,
});

// 子 tab 切换助手(轮次内二级 tab,role=tab 与壳层顶 tab 同范式)
const goSubTab = (name: string | RegExp) =>
  fireEvent.click(screen.getByRole("tab", { name }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(readOpsLedger).mockResolvedValue(LEDGER_MD);
  vi.mocked(listOpsPrecedents).mockResolvedValue(["2026-10-18-a-case.md"]);
});

// ── 票 #142:二级子 tab 重组 ─────────────────────────────────────────────

describe("OpsPage — 子 tab 重组(票 #142)", () => {
  it("默认子 tab=轮次:驾驶舱+过去轮次在场;裁决/档案/设置内容不在 DOM", () => {
    renderOps();
    expect(screen.getByRole("heading", { name: "Cockpit" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Past rounds" })).toBeTruthy();
    // 票 #148:触发动作入驾驶舱单卡,独立「轮次」节头撤除
    expect(screen.queryByRole("heading", { name: "Rounds" })).toBeNull();
    // 非活动子 tab 不渲染(顶 tab 同款范式;#149 标题去「(只读)」限定词)
    expect(screen.queryByRole("heading", { name: "Ruling packages" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Ledger" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Precedents" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /health-round model/i })).toBeNull();
    // 四个子 tab 在场,默认选中轮次
    const rounds = screen.getByRole("tab", { name: "Rounds" });
    expect(rounds).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Rulings" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Archive" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Settings" })).toBeTruthy();
  });

  it("切「裁决」→ 裁决包区让位其余子 tab 面板", async () => {
    renderOps();
    goSubTab("Rulings");
    expect(await screen.findByRole("heading", { name: "Ruling packages" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Cockpit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run health round" })).toBeNull();
  });

  it("切「档案」→ 台账只读表 + 判例库 + 导出(原 section 逻辑原样搬迁;#149 标题去「(只读)」)", async () => {
    renderOps();
    goSubTab("Archive");
    expect(await screen.findByRole("heading", { name: /^Ledger( \(\d+\))?$/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /^Precedents( \(\d+\))?$/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export precedents (.zip)" })).toBeTruthy();
    // 票 #148:台账表统一件列名(与轮次表同集 ops.col.*)+ 相对时间 title 完整戳
    expect(await screen.findByRole("columnheader", { name: "Round" })).toBeTruthy();
    for (const h of ["Time", "Model", "Usage", "Cost", "Note"]) {
      expect(screen.getByRole("columnheader", { name: h })).toBeTruthy();
    }
    expect(screen.getByTitle("2026-10-20")).toBeTruthy();
    expect(screen.getByRole("cell", { name: "discover" })).toBeTruthy();
  });

  it("切「设置」→ 配置面(#140 ConfigSection 移入,票 #143 多供应商形状;#150 保存全部)", async () => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue({
      model_health: "zai-coding-cn/glm-5.3", model_discover: "zai-coding-cn/glm-5.3",
      api_keys: {},
      catalog: { "zai-coding-cn": [{ id: "glm-5.3", name: "GLM-5.3", cost: null }] },
      catalog_source: "dynamic" as const,
    });
    renderOps();
    goSubTab("Settings");
    expect(await screen.findByRole("combobox", { name: /health-round model/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save all" })).toBeTruthy();
  });

  it("裁⑦ 仅立项横幅恒挂(子 tab 重组不撤横幅)", () => {
    renderOps();
    expect(screen.getByText(/Proposals only/i)).toBeTruthy();
  });
});

// ── 票 #147:壳层视觉修约(underline 子 tab / 注记降级 / 节头行规范)──────

describe("OpsPage — 壳层视觉修约(票 #147)", () => {
  beforeEach(() => {
    // 恒挂/aria 用例会切到「设置」:最小目录配置防 cfg=undefined 崩面
    vi.mocked(getOpsAgentConfig).mockResolvedValue({
      model_health: "zai-coding-cn/glm-5.3-flash",
      model_discover: "zai-coding-cn/glm-5.3-flash",
      api_keys: {},
      catalog: { "zai-coding-cn": [{ id: "glm-5.3-flash", name: "GLM-5.3-Flash", cost: null }] },
      catalog_source: "fallback" as const,
    });
  });

  it("注记降级不撤除:「仅立项」一行注记恒挂于全部四个子 tab(裁⑦ 语义不变)", () => {
    renderOps();
    for (const name of ["Rounds", "Rulings", "Archive", "Settings"] as const) {
      if (name !== "Rounds") goSubTab(name);
      expect(screen.getByText(/Proposals only/i)).toBeTruthy();
    }
  });

  it("underline 子 tab:切换后 aria-selected 仅激活项为 true(role=tab 语义不弱化)", () => {
    renderOps();
    const names = ["Rounds", "Rulings", "Archive", "Settings"] as const;
    for (const active of names) {
      if (active !== "Rounds") goSubTab(active);
      for (const name of names) {
        expect(screen.getByRole("tab", { name })).toHaveAttribute(
          "aria-selected",
          name === active ? "true" : "false",
        );
      }
    }
  });

  it("节头计数:过往轮次头显渲染行数(台账行+孤儿包);无数据不显计数", async () => {
    vi.mocked(listOpsPackages).mockResolvedValue([
      { name: "2026-10-21-health-0800.md", size: 512, modified: "2026-10-21T08:00:00Z" },
    ]);
    const withData = renderOps();
    // 2 台账数据行 + 1 孤儿包 = 3(#148 修伪表头后冻结表头行不再切入表体,
    // 计数随解析修正从 4 收敛为 3)
    expect(await withData.findByRole("heading", { name: /Past rounds \(3\)/ })).toBeTruthy();
    withData.unmount();
    // 无数据(台账空+包空):计数不显——「有数据时」才计数,空表不谎报
    vi.mocked(readOpsLedger).mockResolvedValue("");
    vi.mocked(listOpsPackages).mockResolvedValue([]);
    const empty = renderOps();
    expect(await empty.findByText(/No rounds recorded/i)).toBeTruthy();
    expect(empty.getByRole("heading", { name: "Past rounds" })).toBeTruthy();
  });
});

// ── 票 #148:驾驶舱单卡 + 伪表头修复落地 + 表格统一件 ──────────────

describe("OpsPage — 驾驶舱单卡(票 #148)", () => {
  it("状态 chip 内联节头(标题同排)+ 健康/发现触发动作与上一轮结果同卡", () => {
    renderOps({ tasks: [], logs: {} });
    const cockpit = screen.getByRole("region", { name: "Cockpit" });
    // 状态 chip 在节头左簇:chip 所在容器含「驾驶舱」标题
    const chip = within(cockpit).getByText("Idle");
    expect(chip.closest("div")).toContainElement(
      within(cockpit).getByRole("heading", { name: "Cockpit" }));
    // 触发动作入卡(单卡:状态/上一轮结果/触发同卡)
    expect(within(cockpit).getByRole("button", { name: "Run health round" })).toBeTruthy();
    expect(within(cockpit).getByRole("button", { name: "Run discover round" })).toBeTruthy();
    expect(within(cockpit).getByRole("searchbox", { name: /discover input/i })).toBeTruthy();
  });
});

describe("OpsPage — 伪表头修复与表格统一件(票 #148)", () => {
  it("台账夹具(含表头行)渲染后表体零表头行:表 = 列头 + 2 数据行", async () => {
    renderOps();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).queryByText("日期")).toBeNull();
    expect(within(table).queryByText("model")).toBeNull();
  });

  it("备注人话化 + 时间相对且 title 完整戳 + 结果码「—」附宁少算 title", async () => {
    vi.mocked(readOpsLedger).mockResolvedValue([
      "# 运营轮次台账", "",
      "| 日期 | 轮次 | model | 用量 | 备注 |",
      "|---|---|---|---|---|",
      "| 2026-10-21 | health | — | — | spawn error_code=model_face |",
    ].join("\n"));
    renderOps();
    // spawn error_code=model_face → 人话;title = 台账原文(证据不灭失)
    expect(await screen.findByRole("cell", { name: "Start failed: model provider" })).toBeTruthy();
    expect(screen.getByTitle("spawn error_code=model_face")).toBeTruthy();
    // 时间相对 + title 完整戳(台账行精度即日期)
    const timeCell = screen.getByTitle("2026-10-21");
    expect(timeCell.textContent ?? "").toMatch(/ago$|^just now/);
    // 结果码「—」:台账行不载成败;无证据≠成功
    expect(
      screen.getAllByTitle("Ledger rows carry no outcome — absence of evidence is not success").length,
    ).toBeGreaterThan(0);
  });
});

// ── 票 #149:档案+裁决列表修约(列头逐字一致/计数/空态/标题收尾/行元数据)──

describe("OpsPage — 档案面修约(票 #149)", () => {
  it("台账表与轮次表列头逐字一致:共享基列(6)文本相等,追列仅轮次表(审计面不补结果码/包列)", async () => {
    renderOps();
    const roundsTable = await screen.findByRole("table");
    const roundsHeads = within(roundsTable)
      .getAllByRole("columnheader").map((th) => th.textContent);
    expect(roundsHeads).toHaveLength(8); // 基列6 + 追列2(结果码/包)
    goSubTab("Archive");
    const ledgerTable = await screen.findByRole("table");
    const ledgerHeads = within(ledgerTable)
      .getAllByRole("columnheader").map((th) => th.textContent);
    expect(ledgerHeads).toHaveLength(6);
    // 逐字一致断言:台账列头 = 轮次表前 6 列列头(同一套 ops.col.* 词条)
    expect(ledgerHeads).toEqual(roundsHeads.slice(0, 6));
  });

  it("节头计数:台账 N 行/判例 N 篇(非零显计数;空不显)", async () => {
    renderOps(); // LEDGER_MD 2 行;beforeEach 判例 1 篇
    goSubTab("Archive");
    expect(await screen.findByRole("heading", { name: "Ledger (2)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Precedents (1)" })).toBeTruthy();
  });

  it("空列表显基准「暂无」式空态(台账空/判例空),不留纯空白", async () => {
    vi.mocked(readOpsLedger).mockResolvedValue("# 运营轮次台账\n");
    vi.mocked(listOpsPrecedents).mockResolvedValue([]);
    renderOps();
    goSubTab("Archive");
    expect(await screen.findByText("No ledger entries yet")).toBeTruthy();
    expect(await screen.findByText("No precedents yet")).toBeTruthy();
    // 空表不谎报计数:标题无计数尾巴
    expect(screen.getByRole("heading", { name: "Ledger" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Precedents" })).toBeTruthy();
  });

  it("「(只读)」限定词移出标题:标题无括号限定词,只读声明入档案面副注(一次,不逐节重复)", async () => {
    renderOps();
    goSubTab("Archive");
    expect(await screen.findByRole("heading", { name: "Ledger (2)" })).toBeTruthy();
    // 副注一次覆盖两节(反噪音纪律,同 #150 占位说明只现一次)
    expect(screen.getAllByText(/read-only audit face/i)).toHaveLength(1);
    expect(screen.queryByText(/\(read-only\)/)).toBeNull();
  });

  it("判例行元数据:文件名日期派生相对时间(title=日期原文,证据不灭失);无日期名不显时间(零大小 = API 降级,零后端红线)", async () => {
    vi.mocked(listOpsPrecedents).mockResolvedValue([
      "2026-10-17-a-case.md",
      "notes-plain.md",
    ]);
    renderOps();
    goSubTab("Archive");
    const list = await screen.findByRole("list");
    const timed = within(list).getByTitle("2026-10-17");
    expect(timed.textContent ?? "").toMatch(/ago$|^just now/);
    // 无日期前缀名:行内无相对时间元素(宁少算不猜)
    const plain = within(list).getByRole("button", { name: /notes-plain\.md/ });
    expect(within(plain).queryByTitle(/\d{4}-\d{2}-\d{2}/)).toBeNull();
  });
});

// ── 票 #142:驾驶舱卡(状态徽章/耗时走字/最后一行/可折叠日志/上一轮摘要)──

describe("OpsPage — 驾驶舱卡(票 #142)", () => {
  it("空闲:空闲徽章 + 台账兜底的上一轮摘要(无内存面时 readOpsLedger 兜底)", async () => {
    renderOps({ tasks: [], logs: {} });
    expect(screen.getByText("Idle")).toBeTruthy();
    // 台账末行(discover/glm-4.7/cost)兜底呈现,不留白
    expect(await screen.findAllByText("discover")).not.toHaveLength(0);
    expect(await screen.findAllByText("glm-4.7")).not.toHaveLength(0);
    expect(await screen.findAllByText(/0\.00000045/)).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Open rulings" })).toBeTruthy();
  });

  it("空闲且台账空:显式「尚无已完成轮次」占位,不留白", async () => {
    vi.mocked(readOpsLedger).mockResolvedValue("");
    renderOps({ tasks: [], logs: {} });
    expect(await screen.findByText(/No completed round yet/i)).toBeTruthy();
  });

  it("在飞:进行中徽章 + 耗时走字(每秒前进)+ 最后一行活动", async () => {
    vi.useFakeTimers();
    try {
      renderOps({
        tasks: [opsTask("running")],
        logs: { t1: ["[turn 1] stopReason=toolUse usage(in=100 out=20)", "[tool] search_precedents(call_sp1) 排他率", "[tool-result] search_precedents(call_sp1) ok hits=1"] },
      });
      expect(screen.getByText("Running")).toBeTruthy();
      // 耗时走字:初始 00:00,前进 2 秒 → 00:02(自本页首见该轮起计)
      expect(screen.getByText("00:00")).toBeTruthy();
      act(() => { vi.advanceTimersByTime(2000); });
      expect(screen.getByText("00:02")).toBeTruthy();
      // 最后一行活动 = 日志末行(票 #142 修约后的完成行原样可见)
      expect(screen.getByText("[tool-result] search_precedents(call_sp1) ok hits=1")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("在飞:可折叠全量日志(展开见早先行,收起只见末行)", () => {
    renderOps({
      tasks: [opsTask("running")],
      logs: { t1: ["[turn 1] stopReason=toolUse usage(in=100 out=20)", "[tool-result] search_precedents(call_sp1) ok hits=1"] },
    });
    // 收起:只显末行,早先行不在
    expect(screen.queryByText("[turn 1] stopReason=toolUse usage(in=100 out=20)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /show full log/i }));
    expect(screen.getByText("[turn 1] stopReason=toolUse usage(in=100 out=20)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /collapse log/i }));
    expect(screen.queryByText("[turn 1] stopReason=toolUse usage(in=100 out=20)")).toBeNull();
  });

  it("轮结束(done,内存日志优先):摘要卡 = 包名 + usage/cost + 跳「裁决」", () => {
    const done = opsTask("done");
    renderOps({
      tasks: [done],
      logs: {
        t1: [
          "[turn 2] stopReason=end usage(in=3076 out=854)",
          "round: discover 完成 → /app/data/ops/packages/2026-10-20-discover-1126.md",
          "usage: in=3076 out=854 total=3930 cost=0.00095",
        ],
      },
    });
    expect(screen.getAllByText("2026-10-20-discover-1126.md").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/in=3076 out=854/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/cost=0\.00095/).length).toBeGreaterThan(0);
    // 包名跳「裁决」:点击切子 tab,裁决包区在场
    fireEvent.click(screen.getByRole("button", { name: "Open rulings" }));
    expect(screen.getByRole("heading", { name: "Ruling packages" })).toBeTruthy();
  });

  it("轮结束(failed):人话化错误短语 + 可展开原始信封(证据不灭失),不裸抛 code", () => {
    const failed = {
      ...opsTask("failed"),
      error: '模型失败面 stopReason=error:401 {"code":"401","message":"令牌已过期或验证不正确"}',
      error_code: "model_face",
    } as TaskState;
    renderOps({ tasks: [failed], logs: { t1: ["round 失败:模型失败面 stopReason=error:401"] } });
    // 人话主行(票 #148):上游令牌过期(401),不再裸奔原始 JSON
    expect(screen.getByText("Upstream token expired (401)")).toBeTruthy();
    expect(screen.queryByText(/model_face/)).toBeNull();
    // 原始信封可展开:完整原始 message 原样在场(证据不灭失)
    expect(screen.getByText("Raw envelope")).toBeTruthy();
    expect(screen.getByText(/stopReason=error:401/)).toBeTruthy();
  });

  it("轮结束(failed,信封不可人话化):回退可读 code 名,信封仍可展开", () => {
    const failed = {
      ...opsTask("failed"),
      error: "stopReason=aborted", error_code: "infra",
    } as TaskState;
    renderOps({ tasks: [failed], logs: { t1: [] } });
    expect(screen.getByText(/Infrastructure error/i)).toBeTruthy();
    expect(screen.getByText("Raw envelope")).toBeTruthy();
    expect(screen.getByText("stopReason=aborted")).toBeTruthy();
  });

  it("轮结束(cancelled):摘要卡显已取消", () => {
    renderOps({ tasks: [opsTask("cancelled")], logs: {} });
    expect(screen.getByText("Cancelled")).toBeTruthy();
  });
});

// ── 票 #142:过去轮次(台账末 N 行 + 包目录合并,零新后端存储)───────────

describe("OpsPage — 过去轮次(票 #142)", () => {
  it("台账行渲染(时间/轮次/model/usage/cost 拆列)+ 同日同型包挂跳包按钮", async () => {
    vi.mocked(listOpsPackages).mockResolvedValue([
      { name: "2026-10-20-discover-1126.md", size: 2048, modified: "2026-10-20T11:26:00Z" },
      { name: "2026-10-18-health-0912.md", size: 1024, modified: "2026-10-18T09:12:00Z" },
    ]);
    renderOps();
    await waitFor(() => expect(screen.getByTitle("2026-10-20")).toBeTruthy());
    // usage 与 cost 拆列呈现(台账用量串 cost= 段独立成列)
    expect(screen.getByRole("cell", { name: "in=1 out=2 total=3" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "0.00000045" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "glm-4.7" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Result" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Package" })).toBeTruthy();
    // 匹配包(日期+轮型前缀)挂为跳包按钮且与该台账行同列;异日包不入该行(孤行)
    const discBtn = screen.getByRole("button", { name: "2026-10-20-discover-1126.md" });
    expect(discBtn.closest("tr")?.textContent).toContain("glm-4.7");
    const healthBtn = screen.getByRole("button", { name: "2026-10-18-health-0912.md" });
    expect(healthBtn.closest("tr")?.textContent).not.toContain("glm-4.7");
    fireEvent.click(discBtn);
    expect(screen.getByRole("heading", { name: "Ruling packages" })).toBeTruthy();
  });

  it("无台账行的包(失败先于记账等)不灭失:并入列表,缺列显 —", async () => {
    vi.mocked(listOpsPackages).mockResolvedValue([
      { name: "2026-10-21-health-0800.md", size: 512, modified: "2026-10-21T08:00:00Z" },
    ]);
    renderOps();
    const orphan = await screen.findByRole("button", { name: "2026-10-21-health-0800.md" });
    expect(orphan).toBeTruthy();
  });

  it("结果码列:仅最新行在有内存证据(ok 且包名日期+轮型对上)时标 ok,其余 —", async () => {
    vi.mocked(listOpsPackages).mockResolvedValue([
      { name: "2026-10-20-discover-1126.md", size: 2048, modified: "2026-10-20T11:26:00Z" },
    ]);
    const done = opsTask("done");
    renderOps({
      tasks: [done],
      logs: {
        t1: [
          "round: discover 完成 → /app/data/ops/packages/2026-10-20-discover-1126.md",
          "usage: in=1 out=2 total=3 cost=0.00000045",
        ],
      },
    });
    await waitFor(() => expect(screen.getByTitle("2026-10-20")).toBeTruthy());
    // 最新行(discover 2026-10-20)与摘要卡包名对上 → ok;旧行(health 2026-10-19)无证据 → —
    expect(screen.getByRole("cell", { name: "ok" })).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("台账空:显式空态文案", async () => {
    vi.mocked(readOpsLedger).mockResolvedValue("");
    renderOps();
    expect(await screen.findByText(/No rounds recorded/i)).toBeTruthy();
  });
});

// ── 轮次触发面(票 #136 原行为,票 #142 后仍驻「轮次」子 tab)───────────

describe("OpsPage — round trigger panel", () => {
  it("health is one click → startOpsRound('health', non-empty input)", async () => {
    vi.mocked(startOpsRound).mockResolvedValue({ task_id: "t1" });
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run health round" }));
    await waitFor(() => expect(vi.mocked(startOpsRound)).toHaveBeenCalledWith("health", expect.any(String)));
    const input = vi.mocked(startOpsRound).mock.calls[0][1];
    expect(input.trim().length).toBeGreaterThan(0);
  });

  it("discover sends the typed input; empty input → readable hint, no call", async () => {
    vi.mocked(startOpsRound).mockResolvedValue({ task_id: "t2" });
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run discover round" }));
    expect(screen.getByText(/Round input must not be empty/i)).toBeTruthy();
    expect(vi.mocked(startOpsRound)).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("searchbox", { name: /discover input/i }), {
      target: { value: "threatview_c2 直连候选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run discover round" }));
    await waitFor(() => expect(vi.mocked(startOpsRound)).toHaveBeenCalledWith("discover", "threatview_c2 直连候选"));
  });

  it("409 eval_busy envelope → readable lane-busy text, raw code never shown", async () => {
    vi.mocked(startOpsRound).mockRejectedValue(Object.assign(new Error("an ops round is already in flight"), {
      status: 409, code: "eval_busy",
    }));
    renderOps();
    fireEvent.click(screen.getByRole("button", { name: "Run health round" }));
    await waitFor(() => expect(screen.getByText(/serial lane is busy/i)).toBeTruthy());
    expect(screen.queryByText(/eval_busy/)).toBeNull();
  });
});

// ── 票 #140 立:agent 配置子区;票 #143 多供应商形状(双下拉 + 逐家 key)──
// 目录由后端 GET catalog 驱动(单一真相源:node 子调用 dump,失败兜底闭集,
// catalog_source 显式不伪装);qualified "provider/model" 现值驱动选中;key
// write-only 不回显,状态只显 configured+tail4;保存后下一轮即生效(后端每次
// spawn 现读)。票 #142 起该面驻「设置」子 tab。
const CFG_MOCK = {
  model_health: "zai-coding-cn/glm-5.3-flash",
  model_discover: "zai-coding-cn/glm-5.3",
  api_keys: { "zai-coding-cn": { configured: true, tail4: "9988" } },
  catalog: {
    "zai-coding-cn": [
      { id: "glm-4.6v", name: "GLM-4.6V", cost: null },
      { id: "glm-5.3", name: "GLM-5.3", cost: { input: 1.4, output: 4.4, cacheRead: 0.26, cacheWrite: 0 } },
      { id: "glm-5.3-flash", name: "GLM-5.3-Flash", cost: null },
      { id: "glm-5.3-highspeed", name: "GLM-5.3-Highspeed", cost: null },
      { id: "glm-5.3-flashx", name: "GLM-5.3-FlashX", cost: null },
    ],
    "fake-prov": [
      { id: "fake-7b", name: "Fake 7B", cost: { input: 0.1, output: 0.2, cacheRead: 0, cacheWrite: 0 } },
      { id: "glm-5.3", name: "同名家", cost: null },
    ],
  },
  catalog_source: "dynamic" as const,
};

describe("OpsPage — agent config section (票 #143,「设置」子 tab)", () => {
  beforeEach(() => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue(CFG_MOCK);
  });

  it("renders dual dropdowns driven by the backend catalog + configured key status", async () => {
    renderOps();
    goSubTab("Settings");
    const healthProvider = await screen.findByRole("combobox", { name: /health-round provider/i });
    const health = screen.getByRole("combobox", { name: /health-round model/i });
    const discover = screen.getByRole("combobox", { name: /discover-round model/i });
    // provider 下拉两家齐(qualified 现值驱动选中)
    expect([...healthProvider.querySelectorAll("option")].map((o) => o.value))
      .toEqual(["zai-coding-cn", "fake-prov"]);
    expect((healthProvider as HTMLSelectElement).value).toBe("zai-coding-cn");
    // model 下拉 = 现选中 provider 的目录(id 单拼写)
    expect([...health.querySelectorAll("option")].map((o) => o.value))
      .toEqual(["glm-4.6v", "glm-5.3", "glm-5.3-flash", "glm-5.3-highspeed", "glm-5.3-flashx"]);
    expect((health as HTMLSelectElement).value).toBe("glm-5.3-flash");
    expect((discover as HTMLSelectElement).value).toBe("glm-5.3");
    expect(screen.getByText(/Configured \(•••• 9988\)/)).toBeTruthy();
  });

  it("switching provider cascades the model list and saves a qualified value", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue(CFG_MOCK);
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("combobox", { name: /health-round provider/i }), {
      target: { value: "fake-prov" },
    });
    const health = screen.getByRole("combobox", { name: /health-round model/i });
    expect([...health.querySelectorAll("option")].map((o) => o.value))
      .toEqual(["fake-7b", "glm-5.3"]); // 跨家同名模型按 provider 作用域
    expect((health as HTMLSelectElement).value).toBe("fake-7b"); // 级联落首家
    fireEvent.click(screen.getByRole("button", { name: "Save all" }));
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "fake-prov/fake-7b",
      model_discover: "zai-coding-cn/glm-5.3",
    }));
  });

  it("providers without a key are marked in the dropdown (零硬闸:只标注不阻断)", async () => {
    renderOps();
    goSubTab("Settings");
    const provider = await screen.findByRole("combobox", { name: /health-round provider/i });
    const fakeOpt = [...provider.querySelectorAll("option")].find((o) => o.value === "fake-prov");
    expect(fakeOpt?.textContent).toMatch(/needs key first/i);
    const zaiOpt = [...provider.querySelectorAll("option")].find((o) => o.value === "zai-coding-cn");
    expect(zaiOpt?.textContent).not.toMatch(/needs key first/i);
    // #150 key 面:默认仅已配置家;未配置家按搜索唤出后显「No key configured」
    expect(screen.queryByLabelText("fake-prov")).toBeNull();
    fireEvent.change(screen.getByRole("searchbox", { name: /search providers/i }), {
      target: { value: "fake" },
    });
    expect(await screen.findByText(/No key configured/i)).toBeTruthy();
  });

  it("cost hint shows for models with cost data and hides when null (目录可得才显)", async () => {
    renderOps();
    goSubTab("Settings");
    const health = await screen.findByRole("combobox", { name: /health-round model/i });
    const healthWrap = health.closest("label") as HTMLElement;
    expect(within(healthWrap).queryByText(/Reference cost/i)).toBeNull(); // glm-5.3-flash cost=null
    fireEvent.change(health, { target: { value: "glm-5.3" } });
    const hint = within(healthWrap).getByText(/Reference cost/i);
    expect(hint.textContent).toMatch(/1\.4/);
    expect(hint.textContent).toMatch(/4\.4/);
  });

  it("per-provider key inputs send api_keys, write-only cleared after save", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue({
      ...CFG_MOCK,
      api_keys: {
        "zai-coding-cn": { configured: true, tail4: "9988" },
        "fake-prov": { configured: true, tail4: "4321" },
      },
    });
    renderOps();
    goSubTab("Settings");
    // #150:未配置家默认不渲染,搜索唤出后可填
    fireEvent.change(await screen.findByRole("searchbox", { name: /search providers/i }), {
      target: { value: "fake" },
    });
    fireEvent.change(await screen.findByLabelText("fake-prov"), { target: { value: "sk-ant-4321" } });
    fireEvent.click(screen.getByRole("button", { name: "Save all" }));
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "zai-coding-cn/glm-5.3-flash",
      model_discover: "zai-coding-cn/glm-5.3",
      api_keys: { "fake-prov": "sk-ant-4321" },
    }));
    expect(await screen.findByText(/Saved — the next round picks it up/i)).toBeTruthy();
    expect((screen.getByLabelText("fake-prov") as HTMLInputElement).value).toBe(""); // write-only
    expect(screen.getByText(/Configured \(•••• 4321\)/)).toBeTruthy();
  });

  it("blank key inputs omit api_keys from the payload (保持不改)", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue(CFG_MOCK);
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("combobox", { name: /discover-round model/i }), {
      target: { value: "glm-5.3-flashx" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save all" }));
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "zai-coding-cn/glm-5.3-flash", model_discover: "zai-coding-cn/glm-5.3-flashx",
    }));
  });

  it("save failure shows readable text, never the raw code", async () => {
    vi.mocked(putOpsAgentConfig).mockRejectedValue(Object.assign(
      new Error("model_health 未在 zai-coding-cn 装载目录内(glm-4.6v/…): zai-coding-cn/gpt-4o"),
      { status: 422, code: "validation_error" },
    ));
    renderOps();
    goSubTab("Settings");
    fireEvent.click(await screen.findByRole("button", { name: "Save all" }));
    await waitFor(() => expect(screen.getByText(/未在 zai-coding-cn 装载目录内/)).toBeTruthy());
    expect(screen.queryByText(/validation_error/)).toBeNull();
  });

  it("catalog fallback is surfaced, not disguised (catalog_source=fallback)", async () => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue({
      model_health: "zai-coding-cn/glm-5.3", model_discover: "zai-coding-cn/glm-5.3",
      api_keys: {},
      catalog: { "zai-coding-cn": [{ id: "glm-5.3", name: "GLM-5.3", cost: null }] },
      catalog_source: "fallback" as const,
    });
    renderOps();
    goSubTab("Settings");
    expect(await screen.findByText(/fell back/i)).toBeTruthy();
  });
});

// ── 票 #150:设置子 tab 视觉修约(表单基线/保存全部/key 搜索置顶/术语)──

describe("OpsPage — settings 视觉修约(票 #150)", () => {
  beforeEach(() => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue(CFG_MOCK);
  });

  it("表单基线:四字段同属单一基线容器;成本帮助行在控件下方(纵向节奏一致)", async () => {
    renderOps();
    goSubTab("Settings");
    const healthProv = await screen.findByRole("combobox", { name: /health-round provider/i });
    const healthModel = screen.getByRole("combobox", { name: /health-round model/i });
    const discProv = screen.getByRole("combobox", { name: /discover-round provider/i });
    const discModel = screen.getByRole("combobox", { name: /discover-round model/i });
    // 四控件同一基线容器(旧 renderRound=每轮各自包裹,模型组成本行抬高标签 → 两级错落)
    const row = healthProv.closest("div");
    expect(healthModel.closest("div")).toBe(row);
    expect(discProv.closest("div")).toBe(row);
    expect(discModel.closest("div")).toBe(row);
    // 帮助行在控件下方:选中带价模型后,成本提示位于同字段 select 之后(不抬标签)
    fireEvent.change(healthModel, { target: { value: "glm-5.3" } });
    const hint = within(healthModel.closest("label") as HTMLElement).getByText(/Reference cost/i);
    expect(hint.compareDocumentPosition(healthModel) & Node.DOCUMENT_POSITION_PRECEDING)
      .toBeTruthy();
  });

  it("保存全部上移节头:与节标题同排 + 一行说明;契约不变 = 单次 PUT 同交模型与 key", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue(CFG_MOCK);
    renderOps();
    goSubTab("Settings");
    const saveAll = await screen.findByRole("button", { name: "Save all" });
    // 节头行:按钮的容器行同排着节标题 h2(不再是表单下随行按钮)
    const headRow = saveAll.closest("div")?.parentElement;
    expect(headRow?.querySelector("h2")?.textContent).toMatch(/model config/i);
    // 一行说明:同时提交模型与 key(单次提交)
    expect(screen.getByText(/in one request/i)).toBeTruthy();
    // 契约不变:填 key 后单次 PUT 同交 model_* 与 api_keys(ADR 0005 面)
    fireEvent.change(screen.getByRole("searchbox", { name: /search providers/i }), {
      target: { value: "fake" },
    });
    fireEvent.change(await screen.findByLabelText("fake-prov"), { target: { value: "sk-1" } });
    fireEvent.click(saveAll);
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledTimes(1));
    expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "zai-coding-cn/glm-5.3-flash",
      model_discover: "zai-coding-cn/glm-5.3",
      api_keys: { "fake-prov": "sk-1" },
    });
  });

  it("API 密钥面:默认仅已配置家;搜索唤出其余且已配置置顶;无匹配空态", async () => {
    renderOps();
    goSubTab("Settings");
    // 默认:已配置家在场(现值只显尾 4),未配置家不渲染(配 1 家不滚 40 格)
    expect(await screen.findByText(/Configured \(•••• 9988\)/)).toBeTruthy();
    expect(screen.queryByLabelText("fake-prov")).toBeNull();
    // 搜索唤出:命中的未配置家出现,已配置家仍置顶(文档序在前)
    fireEvent.change(screen.getByRole("searchbox", { name: /search providers/i }), {
      target: { value: "o" },
    });
    const zai = await screen.findByLabelText("zai-coding-cn");
    const fake = screen.getByLabelText("fake-prov");
    expect(zai.compareDocumentPosition(fake) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // 无匹配:基准「暂无」式空态(硬规⑥)
    fireEvent.change(screen.getByRole("searchbox", { name: /search providers/i }), {
      target: { value: "nonexistent" },
    });
    expect(await screen.findByText(/no matching providers/i)).toBeTruthy();
  });

  it("API 密钥面:零已配置时默认显「暂无」式空态(硬规⑥)", async () => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue({ ...CFG_MOCK, api_keys: {} });
    renderOps();
    goSubTab("Settings");
    expect(await screen.findByText(/no api keys configured yet/i)).toBeTruthy();
  });

  it("「只写不回显」说明仅节头一次;输入框不再各挂占位文案(噪音清零)", async () => {
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("searchbox", { name: /search providers/i }), {
      target: { value: "o" },
    });
    const zai = screen.getByLabelText("zai-coding-cn") as HTMLInputElement;
    const fake = screen.getByLabelText("fake-prov") as HTMLInputElement;
    expect(zai.placeholder).toBe("");
    expect(fake.placeholder).toBe("");
    expect(screen.getAllByText(/write-only/i)).toHaveLength(1);
  });

  it("keys 面搜索态在场 + 节标题与 keys tab 同词(样式类名不断言,视觉规走复评门)", async () => {
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("searchbox", { name: /search providers/i }), {
      target: { value: "o" },
    });
    // 等宽通栏容器/描边面板属样式面(硬规①)——DOM 测试不断样式类名
    // (spec #146 Testing Decisions),视觉合规由截屏复评门验证;
    // 此处只断行为:搜索唤出的未配置家输入框在场 + 两节标题。
    expect(await screen.findByLabelText("zai-coding-cn")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "API Keys" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Model config" })).toBeTruthy();
  });

  it("术语同词(两 locale):ops keys 节标题 = admin keys tab 词条", () => {
    expect(en["ops.cfg.keysTitle"]).toBe(en["admin.tab.keys"]);
    expect(zhCN["ops.cfg.keysTitle"]).toBe(zhCN["admin.tab.keys"]);
  });

  it("zh-CN:节标题纯中文(「模型配置」「API 密钥」)+「保存全部」", async () => {
    renderWithI18n(wrapCtx({}, <OpsPage onUnauthorized={vi.fn()} />), { locale: "zh-CN" });
    fireEvent.click(screen.getByRole("tab", { name: "设置" }));
    expect(await screen.findByRole("heading", { name: "模型配置" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "API 密钥" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存全部" })).toBeTruthy();
  });
});

// ── 档案子 tab:判例检索/详情/导出(原 PrecedentsSection 行为搬迁)──────

describe("OpsPage — archive: precedents & export", () => {
  it("precedent list renders names; search box drives kws query; detail opens read-only", async () => {
    vi.mocked(readOpsPrecedent).mockResolvedValue("# 判例:人裁同意\n\nfrontmatter…\n");
    renderOps();
    goSubTab("Archive");
    // #149:行含文件名日期派生相对时间 → 可访问名为「文件名 + N days ago」,
    // 按含文件名匹配(行为断言不变:点名开全文)
    const item = await screen.findByRole("button", { name: /2026-10-18-a-case\.md/ });
    fireEvent.click(item);
    expect(vi.mocked(readOpsPrecedent)).toHaveBeenCalledWith("2026-10-18-a-case.md");
    expect(await screen.findByText(/# 判例:人裁同意/)).toBeTruthy();
    // 关弹窗(Base UI 对话框会把背景置 inert,不关则背景不可查)
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    // 检索:kws 输入 → listOpsPrecedents(kws)
    fireEvent.change(screen.getByRole("searchbox", { name: /keywords/i }), {
      target: { value: "sunset mirror" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(vi.mocked(listOpsPrecedents)).toHaveBeenCalledWith("sunset mirror"));
  });

  it("export button downloads the zip blob", async () => {
    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    vi.mocked(exportOpsPrecedents).mockResolvedValue(new Blob(["zip"]));
    renderOps();
    goSubTab("Archive");
    fireEvent.click(await screen.findByRole("button", { name: "Export precedents (.zip)" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(vi.mocked(exportOpsPrecedents)).toHaveBeenCalled();
  });
});

afterEach(() => {
  vi.useRealTimers();
});
