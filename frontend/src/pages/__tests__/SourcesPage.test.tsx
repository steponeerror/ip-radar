import { describe, it, expect, vi, type Mock } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import SourcesPage from "../SourcesPage";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { translate } from "../../i18n/translate";
import {
  enqueueSingle,
  enqueueBatch,
  fetchEvalModel,
  getSources,
  setSourceEnabled,
} from "../../api";
import type { TaskState, BatchState } from "../../api";

// Task 9:useTasks() 移出 SourcesPage —— 任务/批量态由 AdminPage 在其
// TaskProvider 内取好下传;公开页(<SourcesPage /> 无 props)纯只读。

vi.mock("../../api", async () => {
  const real = await vi.importActual<any>("../../api");
  return {
    ...real,
    getSources: vi.fn().mockResolvedValue([
      {
        name: "feodo",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["ip"],
        reliability: 0.5,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "feodo",
          loaded: true,
          record_count: 10,
          covered_ips: 10,
          last_updated: null,
          is_stale: true,
          error: null,
        },
      },
    ]),
    fetchEvalModel: vi.fn().mockResolvedValue(null),
    enqueueSingle: vi.fn().mockResolvedValue({ task_id: "t1" }),
    enqueueBatch: vi.fn().mockResolvedValue({ batch_id: "b1" }),
    setSourceEnabled: vi.fn(),
  };
});

const TK = (over: Partial<TaskState>): TaskState => ({
  id: "t1", source: "feodo", host: null, state: "done",
  error: null, batch_id: null, ...over,
});

describe("SourcesPage public view (no manage prop)", () => {
  it("renders source rows read-only: no Toggle / Update / Refresh-all", async () => {
    renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByRole("button", { name: /Update/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Refresh all/i })).toBeNull();
    // 只读信息仍在:状态徽标 + 覆盖数
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });
});

describe("SourcesPage manage mode (admin)", () => {
  it("renders Update buttons and Toggle switches", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    expect(await screen.findByRole("button", { name: /Update/i })).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("Update button enqueues single-source task", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    const btn = await screen.findByRole("button", { name: /Update/i });
    fireEvent.click(btn);
    await waitFor(() => expect(enqueueSingle).toHaveBeenCalledWith("feodo"));
  });

  it("Refresh all enqueues batch", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    const btn = await screen.findByRole("button", { name: /Refresh all/i });
    // loading 期间按钮 disabled, click 被吞 — 等可用再点 (CI 慢机竞态)
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);
    await waitFor(() => expect(enqueueBatch).toHaveBeenCalled());
  });

  it("Toggle switch PATCHes the source and rolls back on failure", async () => {
    (setSourceEnabled as any).mockRejectedValueOnce(new Error("403"));
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    const sw = await screen.findByRole("switch");
    expect(sw).toHaveAttribute("aria-checked", "true");
    fireEvent.click(sw);
    await waitFor(() => expect(setSourceEnabled).toHaveBeenCalledWith("feodo", false));
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true")); // rollback
  });

  it("debounce-refetches sources when a passed-down task reaches done", async () => {
    const { rerender } = renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    await screen.findByText("feodo");
    const initialCalls = (getSources as any).mock.calls.length;
    // doneCount 0 → 1(AdminPage 下传的任务完成)触发 500ms 去抖重拉
    rerender(
      <SourcesPage manage tasks={[TK({ state: "done" })]} batch={null} />,
    );
    await waitFor(
      () => expect((getSources as any).mock.calls.length).toBeGreaterThan(initialCalls),
      { timeout: 2000 },
    );
  });

  it("shows progress from the latest task when a source has stale history", async () => {
    // Regression: tasks arrive oldest-first and a source accumulates terminal
    // tasks across batches. Picking the first match masked the current phase,
    // so re-updating a previously-updated source showed "Update" instead of
    // "Downloading". The latest task per source must win.
    renderWithI18n(
      <SourcesPage
        manage
        tasks={[
          TK({ id: "t-old", state: "done" }),
          TK({ id: "t-new", state: "downloading" }),
        ]}
        batch={null}
      />,
    );
    expect(await screen.findByRole("button", { name: /Downloading/i })).toBeInTheDocument();
  });

  it("treats a throttled task as busy: Update disabled and labeled Queued", async () => {
    // throttled(限流排队)在旧代码不算 busy → 按钮可点、文案仍是 Update,
    // 而后端 _enqueue_one 对四态幂等,排队期间再点完全无感("点了没反应"困惑)。
    renderWithI18n(
      <SourcesPage manage tasks={[TK({ id: "t-th", state: "throttled" })]} batch={null} />,
    );
    const btn = await screen.findByRole("button", { name: "Queued" });
    expect(btn).toBeDisabled();
  });

  it("shows loading percentage from received/total (100/200 → 50%)", async () => {
    renderWithI18n(
      <SourcesPage
        manage
        tasks={[TK({ id: "t-load", state: "loading", received: 100, total: 200 })]}
        batch={null}
      />,
    );
    expect(
      await screen.findByRole("button", { name: /Loading… 50%/ }),
    ).toBeInTheDocument();
  });

  it("clamps loading percentage at 100% when received exceeds total (250/200)", async () => {
    // 终审 P2:对齐 progress.ts stagedFrac 的 Math.min(1,…) 既有规范,
    // 异常数据 received>total 不得显出 >100%。
    renderWithI18n(
      <SourcesPage
        manage
        tasks={[TK({ id: "t-load2", state: "loading", received: 250, total: 200 })]}
        batch={null}
      />,
    );
    expect(
      await screen.findByRole("button", { name: /Loading… 100%/ }),
    ).toBeInTheDocument();
  });

  it("disables Refresh-all while a batch is running (batch prop)", async () => {
    const batch: BatchState = { id: "b1", state: "running", done: 0, total: 3 };
    renderWithI18n(<SourcesPage manage tasks={[]} batch={batch} />);
    const btn = await screen.findByRole("button", { name: /Refreshing all/i });
    expect(btn).toBeDisabled();
  });
});

describe("SourcesPage read-only info (both modes)", () => {
  it("timeAgo shows 'no data' (not 'on-demand') for an offline source missing its raw file", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "abuseipdb",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["is_malicious"],
        reliability: 0.75,
        authoritative_for: ["is_malicious"],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "abuseipdb",
          loaded: false,
          record_count: 0,
          covered_ips: 0,
          last_updated: null,
          is_stale: true,
          error: null,
        },
      },
    ]);
    renderWithI18n(<SourcesPage />);
    await screen.findByText("abuseipdb");
    // Regression: offline + no last_update must show "no data" (an offline
    // source with a missing raw file has nothing on disk).
    expect(screen.getByText("no data")).toBeInTheDocument();
  });

  it("renders covered_ips with a B tier for geo-scale sources", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "ipinfo_lite",
        enabled: true,
        category: "geo_asn",
        archetype: "offline",
        fields: ["country_code"],
        reliability: 0.9,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "ipinfo_lite",
          loaded: true,
          record_count: 3600000,
          covered_ips: 3_700_000_000,
          last_updated: null,
          is_stale: false,
          error: null,
        },
      },
    ]);
    renderWithI18n(<SourcesPage />);
    expect(await screen.findByText("3.7B")).toBeInTheDocument();
  });

  it("renders eval verdict badge when source has an eval result", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "spamhaus",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["is_malicious"],
        reliability: 0.9,
        authoritative_for: ["is_malicious"],
        classification_type: "blacklist",
        url: "https://www.spamhaus.org/drop/",
        stale_days: 1,
        eval: { verdict: "POSITIVE-VERIFIED", at: "2026-08-28" },
        health: {
          name: "spamhaus",
          loaded: true,
          record_count: 1000,
          covered_ips: 1000,
          last_updated: null,
          is_stale: false,
          error: null,
        },
      },
    ]);
    renderWithI18n(<SourcesPage />);
    await screen.findByText("spamhaus");
    const badge = screen.getByText("verified");
    expect(badge).toHaveAttribute("title", "2026-08-28");
  });

  it("renders NO-DATA badge: gray base, red text, collapse tooltip instead of date (W4)", async () => {
    // W4 verdict.py 钉死精确串 "NO-DATA"(reason empty/collapsed)—— 徽章消费
    // 该精确串,渲染为灰底红字 + 说明性 title(不是评估日期)。
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "deadfeed",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["ip"],
        reliability: 0.7,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: { verdict: "NO-DATA", at: "2026-09-28" },
        health: {
          name: "deadfeed",
          loaded: true,
          record_count: 0,
          covered_ips: 0,
          last_updated: "2026-09-27T00:00:00Z",
          is_stale: true,
          error: null,
        },
      },
    ]);
    renderWithI18n(<SourcesPage />);
    // verdict → i18n key sources.eval.no_data("no-data",连字符,与 timeAgo 的
    // "no data" 空格串可区分)
    const badge = await screen.findByText("no-data");
    // 灰底红字:红字 + 灰底(NOT NEGATIVE 的全红边框)
    expect(badge).toHaveClass("text-red-400");
    expect(badge).toHaveClass("bg-zinc-800/50");
    expect(badge).not.toHaveClass("border-red-400/30");
    // title 是坍塌说明而非评估日期
    expect(screen.getByTitle(/did not contribute/i)).toBeInTheDocument();
    expect(screen.queryByTitle("2026-09-28")).toBeNull();
  });

  it("renders '-' when source has no eval result", async () => {
    renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows measured theta beside declared reliability (A2 dual-track)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "spamhaus",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["is_malicious"],
        reliability: 0.9,
        authoritative_for: ["is_malicious"],
        classification_type: "blacklist",
        url: null,
        stale_days: 1,
        eval: null,
        health: {
          name: "spamhaus",
          loaded: true,
          record_count: 1000,
          covered_ips: 1000,
          last_updated: null,
          is_stale: false,
          error: null,
        },
      },
      {
        name: "feodo",
        enabled: true,
        category: "threat",
        archetype: "offline",
        fields: ["ip"],
        reliability: 0.5,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "feodo",
          loaded: true,
          record_count: 10,
          covered_ips: 10,
          last_updated: null,
          is_stale: true,
          error: null,
        },
      },
    ]);
    vi.mocked(fetchEvalModel).mockResolvedValueOnce({
      scores: [
        { source: "spamhaus", theta: 0.61, ci_lo: 0.55, ci_hi: 0.68, declared_r: 0.9 },
      ],
    } as any);
    renderWithI18n(<SourcesPage />);
    // measured θ track (waits for the eval-model fetch to land)
    const theta = await screen.findByText(/θ 0\.61/);
    expect(theta.textContent).toContain("[0.55–0.68]");
    // tooltip carries the corroboration red-line wording
    expect(screen.getByTitle(/corroboration/i)).toBeInTheDocument();
    // declared r stays visible beside it (dual track)
    expect(screen.getByText(/r 0\.90/)).toBeInTheDocument();
    // unscored source renders — in the θ cell
    expect(screen.getByText("—")).toBeInTheDocument();
    // footnote: advisory semantics, declared r authoritative
    expect(screen.getByText(/production weight/i)).toBeInTheDocument();
  });

  it("401 on load kicks to login via onUnauthorized when manage-wired (spec §9)", async () => {
    const err = Object.assign(new Error("Not authenticated"), { status: 401 });
    (getSources as unknown as Mock).mockRejectedValueOnce(err);
    const onUnauthorized = vi.fn();
    renderWithI18n(<SourcesPage manage onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
  });
});

// Task:grid 化 + 全局表头 + 响应式藏列(R1–R8)。默认 mock(feodo,threat,
// eval:null,无 θ)驱动:表头/模板/hidden 断点/公开页无操作列/geo_asn 改名。
describe("SourcesPage grid + header (R1–R8)", () => {
  it("manage: renders all 9 column headers above groups, in track order", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    await screen.findByText("feodo");
    // 表头已无 role(P2a):以首列标签定位表头容器
    const header = screen.getByText("Name").parentElement!;
    // DOM 顺序 = 轨道顺序(eval 于 status/r 之间,θ 于 r/操作之间):grid 按
    // DOM 序放置,hidden 单元格不占轨道,故顺序错位即布局错位。
    expect(header.textContent).toBe("NameFieldCovered IPsUpdatedStatusEvalrθActions");
  });

  it("header row shares the exact 3-tier grid template with data rows (manage)", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    await screen.findByRole("listitem");
    const header = screen.getByText("Name").parentElement!;
    const li = screen.getByRole("listitem");
    for (const el of [header, li]) {
      expect(el).toHaveClass("grid");
      expect(el).toHaveClass("grid-cols-[8rem_4rem_4rem_6rem_6rem_4rem_1fr]");
      expect(el).toHaveClass("lg:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_1fr]");
      expect(el).toHaveClass("xl:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_9rem_1fr]");
    }
  });

  it("eval/θ breakpoints: header cells and data cells hidden in lockstep (R2)", async () => {
    renderWithI18n(<SourcesPage manage tasks={[]} batch={null} />);
    await screen.findByText("feodo");
    // 表头:Eval hidden→lg:block,θ hidden→xl:block(P2a 后无 role,按文本定位)
    expect(screen.getByText("Eval")).toHaveClass("hidden", "lg:block");
    expect(screen.getByText("θ")).toHaveClass("hidden", "xl:block");
    // 同 mock 下数据单元格:eval 占位 - (lg:block),θ 占位 — (xl:block)
    expect(screen.getByText("-")).toHaveClass("hidden", "lg:block");
    expect(screen.getByText("—")).toHaveClass("hidden", "xl:block");
  });

  it("public page: same header minus the action column; template one track shorter (R3)", async () => {
    renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    expect(screen.queryByText("Actions")).toBeNull();
    const header = screen.getByText("Name").parentElement!;
    expect(header.textContent).toBe("NameFieldCovered IPsUpdatedStatusEvalrθ");
    expect(header).toHaveClass("grid-cols-[8rem_4rem_4rem_6rem_6rem_4rem]");
    expect(header).toHaveClass("lg:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem]");
    expect(header).toHaveClass("xl:grid-cols-[8rem_4rem_4rem_6rem_6rem_7rem_4rem_9rem]");
    const li = screen.getByRole("listitem");
    expect(li.className).not.toContain("1fr");
  });

  it("geo_asn group header renamed (R6): en on page, zh-CN verbatim in locale", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "ipinfo_lite",
        enabled: true,
        category: "geo_asn",
        archetype: "offline",
        fields: ["country_code"],
        reliability: 0.9,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "ipinfo_lite",
          loaded: true,
          record_count: 1,
          covered_ips: 1,
          last_updated: null,
          is_stale: false,
          error: null,
        },
      },
    ]);
    renderWithI18n(<SourcesPage />);
    expect(await screen.findByText("Geo & ASN data")).toBeInTheDocument();
    // zh-CN 逐字裁决值(无 OpenCC 运行时依赖,直接校 locale 表)
    expect(translate("zh-CN", "sources.cat.geo_asn")).toBe("地理 / ASN 数据");
  });

  it("single outer scroller wraps header + all groups; ul no longer scrolls alone (R7 fix)", async () => {
    renderWithI18n(<SourcesPage />);
    await screen.findByRole("listitem");
    const list = screen.getByRole("list");
    // 逐分组 overflow-x-auto 已移除(不再各自滚动、不再双横滚条)
    expect(list).not.toHaveClass("overflow-x-auto");
    // 表头与分组 ul 同处一个外层滚动容器 → 锁步横滚
    const scroller = list.closest(".overflow-x-auto");
    expect(scroller).not.toBeNull();
    expect(screen.getByText("Name").closest(".overflow-x-auto")).toBe(scroller);
    // 内层 min-w-max:窄视口下表头/卡片随行内容整体取宽(圆角不回归)
    expect(scroller!.firstElementChild).toHaveClass("min-w-max");
  });
});
