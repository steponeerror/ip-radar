import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { ReactElement } from "react";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import OpsPage from "../OpsPage";
import { TasksContext, type TasksCtxValue } from "../../tasks/useTasks";
import type { TaskState } from "../../api";
import { renderWithI18n } from "../../test/i18nTestUtils";
import {
  startOpsRound, readOpsLedger, listOpsPrecedents, readOpsPrecedent, exportOpsPrecedents,
  getOpsAgentConfig, putOpsAgentConfig, listOpsPackages,
} from "../../api";

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
  it("默认子 tab=轮次:驾驶舱+触发面+过去轮次在场;裁决/档案/设置内容不在 DOM", () => {
    renderOps();
    expect(screen.getByRole("heading", { name: "Cockpit" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Rounds" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Past rounds" })).toBeTruthy();
    // 非活动子 tab 不渲染(顶 tab 同款范式)
    expect(screen.queryByRole("heading", { name: "Ruling packages" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Ledger (read-only)" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Precedents (read-only)" })).toBeNull();
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

  it("切「档案」→ 台账只读表 + 判例库 + 导出(原 section 逻辑原样搬迁)", async () => {
    renderOps();
    goSubTab("Archive");
    expect(await screen.findByRole("heading", { name: "Ledger (read-only)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Precedents (read-only)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export precedents (.zip)" })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("cell", { name: "2026-10-20" })).toBeTruthy());
    expect(screen.getByRole("cell", { name: "discover" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "轮次" })).toBeTruthy();
  });

  it("切「设置」→ agent 配置面(#140 ConfigSection 移入)", async () => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue({
      model_health: "glm-5.3-flash", model_discover: "glm-5.3",
      zai_api_key: { configured: false, tail4: null }, allowed_models: ["glm-5.3"],
    });
    renderOps();
    goSubTab("Settings");
    expect(await screen.findByRole("combobox", { name: /health-round model/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  it("裁⑦ 仅立项横幅恒挂(子 tab 重组不撤横幅)", () => {
    renderOps();
    expect(screen.getByText(/Proposals only/i)).toBeTruthy();
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

  it("轮结束(failed):摘要卡 = 可读失败文案 + 原始消息,不裸抛 code", () => {
    const failed = { ...opsTask("failed"), error: "模型失败面 stopReason=error", error_code: "model_face" } as TaskState;
    renderOps({ tasks: [failed], logs: { t1: ["round 失败:模型失败面 stopReason=error"] } });
    expect(screen.getByText(/Model provider failed/i)).toBeTruthy();
    expect(screen.getByText(/模型失败面 stopReason=error/)).toBeTruthy();
    expect(screen.queryByText(/model_face/)).toBeNull();
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
    await waitFor(() => expect(screen.getByRole("cell", { name: "2026-10-20" })).toBeTruthy());
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
    await waitFor(() => expect(screen.getByRole("cell", { name: "2026-10-20" })).toBeTruthy());
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

// ── 票 #140:agent 配置子区(选模型 + 填 key)── 闭集下拉由后端 GET
// allowed_models 驱动(单一真相源,实测 pi-ai 装载目录五值);key write-only
// 不回显,状态只显 configured+tail4(沿 token 面先例);保存后下一轮即生效。
// 票 #142 起该面移入「设置」子 tab(逻辑原样搬迁)。
const CFG_MOCK = {
  model_health: "glm-5.3-flash",
  model_discover: "glm-5.3",
  zai_api_key: { configured: true, tail4: "9988" },
  allowed_models: ["glm-4.6v", "glm-5.3", "glm-5.3-flash", "glm-5.3-highspeed", "glm-5.3-flashx"],
};

describe("OpsPage — agent config section (票 #140,「设置」子 tab)", () => {
  beforeEach(() => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue(CFG_MOCK);
  });

  it("renders backend-driven closed-set dropdowns + configured key status", async () => {
    renderOps();
    goSubTab("Settings");
    const health = await screen.findByRole("combobox", { name: /health-round model/i });
    const discover = screen.getByRole("combobox", { name: /discover-round model/i });
    for (const sel of [health, discover]) {
      expect([...sel.querySelectorAll("option")].map((o) => o.value)).toEqual(CFG_MOCK.allowed_models);
    }
    expect((health as HTMLSelectElement).value).toBe("glm-5.3-flash");
    expect((discover as HTMLSelectElement).value).toBe("glm-5.3");
    expect(screen.getByText(/Configured \(•••• 9988\)/)).toBeTruthy();
  });

  it("shows the not-configured key status text when no key", async () => {
    vi.mocked(getOpsAgentConfig).mockResolvedValue({
      ...CFG_MOCK, zai_api_key: { configured: false, tail4: null },
    });
    renderOps();
    goSubTab("Settings");
    expect(await screen.findByText(/No key configured/i)).toBeTruthy();
  });

  it("save sends models + typed key, clears the write-only input, refreshes status", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue({
      ...CFG_MOCK,
      model_health: "glm-4.6v",
      model_discover: "glm-5.3-highspeed",
      zai_api_key: { configured: true, tail4: "4321" },
    });
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("combobox", { name: /health-round model/i }), {
      target: { value: "glm-4.6v" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: /discover-round model/i }), {
      target: { value: "glm-5.3-highspeed" },
    });
    fireEvent.change(screen.getByLabelText(/Z\.AI API key/i), {
      target: { value: "sk-typed-4321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "glm-4.6v", model_discover: "glm-5.3-highspeed", zai_api_key: "sk-typed-4321",
    }));
    expect(await screen.findByText(/Saved — the next round picks it up/i)).toBeTruthy();
    expect(screen.getByText(/Configured \(•••• 4321\)/)).toBeTruthy();
    expect((screen.getByLabelText(/Z\.AI API key/i) as HTMLInputElement).value).toBe("");
  });

  it("blank key input omits zai_api_key from the payload (保持不改)", async () => {
    vi.mocked(putOpsAgentConfig).mockResolvedValue(CFG_MOCK);
    renderOps();
    goSubTab("Settings");
    fireEvent.change(await screen.findByRole("combobox", { name: /discover-round model/i }), {
      target: { value: "glm-5.3-flashx" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(vi.mocked(putOpsAgentConfig)).toHaveBeenCalledWith({
      model_health: "glm-5.3-flash", model_discover: "glm-5.3-flashx",
    }));
  });

  it("save failure shows readable text, never the raw code", async () => {
    vi.mocked(putOpsAgentConfig).mockRejectedValue(Object.assign(new Error("model_health 必须在闭集内"), {
      status: 422, code: "validation_error",
    }));
    renderOps();
    goSubTab("Settings");
    fireEvent.click(await screen.findByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText(/必须在闭集内/)).toBeTruthy());
    expect(screen.queryByText(/validation_error/)).toBeNull();
  });
});

// ── 档案子 tab:判例检索/详情/导出(原 PrecedentsSection 行为搬迁)──────

describe("OpsPage — archive: precedents & export", () => {
  it("precedent list renders names; search box drives kws query; detail opens read-only", async () => {
    vi.mocked(readOpsPrecedent).mockResolvedValue("# 判例:人裁同意\n\nfrontmatter…\n");
    renderOps();
    goSubTab("Archive");
    const item = await screen.findByRole("button", { name: "2026-10-18-a-case.md" });
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
