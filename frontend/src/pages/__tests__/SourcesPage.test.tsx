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
          // T6:非空诊断对 → 默认 mock 驱动的公开/管理/grid 测试也路过值渲染路径
          content_age_h: 26,
          observed_interval_h: 172.8,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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
          content_age_h: null,
          observed_interval_h: null,
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

// T5(cloud_ranges 融合):多 feed 源 health.feeds —— 名称列源名下方渲染
// provider 芯片行(stale→红/fresh→灰,字号小于源名,纯展示零交互)。单 feed
// 源后端经 _omit_null_feeds 省略 feeds 键(响应形状零变化红线),前端类型
// 必须可选,且该源行不得渲染任何 [data-feed] 节点。
describe("SourcesPage feed chips (T5 multi-feed sources)", () => {
  it("renders per-provider chips under the name: stale red, fresh zinc, smaller font", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      {
        name: "cloud_ranges",
        enabled: true,
        category: "asset",
        archetype: "offline",
        fields: ["service", "is_hosting"],
        reliability: 0.95,
        authoritative_for: [],
        classification_type: null,
        url: null,
        stale_days: null,
        eval: null,
        health: {
          name: "cloud_ranges",
          loaded: true,
          record_count: 100,
          covered_ips: 100,
          last_updated: null,
          is_stale: true,
          error: null,
          content_age_h: null,
          observed_interval_h: null,
          feeds: [
            { name: "AWS", last_updated: "2026-10-01T00:00:00Z", is_stale: false },
            { name: "Azure", last_updated: null, is_stale: true },
          ],
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
          content_age_h: null,
          observed_interval_h: null,
        },
      },
    ]);
    const { container } = renderWithI18n(<SourcesPage />);
    await screen.findByText("cloud_ranges");
    // fresh 芯片:data-feed+data-stale=false,zinc 灰
    const aws = container.querySelector('[data-feed="AWS"]');
    expect(aws).not.toBeNull();
    expect(aws).toHaveAttribute("data-stale", "false");
    expect(aws).toHaveClass("text-zinc-400");
    expect(aws).not.toHaveClass("text-red-400");
    // stale 芯片:data-stale=true,红
    const azure = container.querySelector('[data-feed="Azure"]');
    expect(azure).not.toBeNull();
    expect(azure).toHaveAttribute("data-stale", "true");
    expect(azure).toHaveClass("text-red-400");
    // 字号小于源名(源名 text-sm,芯片 text-xs)
    expect(aws).toHaveClass("text-xs");
    expect(
      container.querySelector('[title="cloud_ranges"]')!,
    ).toHaveClass("text-sm");
    // 无 feeds 源(键被后端省略)不渲染任何 [data-feed] 节点:全页恰好两枚
    expect(container.querySelectorAll("[data-feed]")).toHaveLength(2);
    // 芯片行位于源名下方同一名称单元格内(flex-col 栈序)
    expect(aws!.compareDocumentPosition(
      container.querySelector('[title="cloud_ranges"]')!,
    ) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });
});

// T6(源活性告警):health 增 content_age_h/observed_interval_h —— 更新单元格
// 第二行展示"内容年龄 · 实测节奏"。档位与后端推送 _fmt_hours 同规
// (<48h → ceil 整数 + "h";≥48h → 一位小数 + "d");cadence 套 i18n 模板
// (zh "{v}/次" / en "every {v}");null(无文件/事件<5 条)→ "—";负值
// (时钟回拨,终审 P2-1)clamp 0;完整 i18n 标签入 title(值可见,6rem 固定
// 轨道容不下双语长标签,循 θ 单元格 tooltip 模式)。
describe("SourcesPage health diagnostics (T6 content age / measured cadence)", () => {
  const src = (name: string, contentAge: number | null, observed: number | null) => ({
    name,
    enabled: true,
    category: "threat" as const,
    archetype: "offline" as const,
    fields: ["ip"],
    reliability: 0.5,
    authoritative_for: [],
    classification_type: null,
    url: null,
    stale_days: null,
    eval: null,
    health: {
      name,
      loaded: true,
      record_count: 10,
      covered_ips: 10,
      last_updated: null,
      is_stale: false,
      error: null,
      content_age_h: contentAge,
      observed_interval_h: observed,
    },
  });

  it("renders age + cadence in the updated cell: h tier below 48h, d tier above", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("feodo", 26, 172.8)]);
    const { container } = renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    // <48h → 裸数 26h;≥48h → 一位小数 d 档(172.8h → 7.2d)+ cadence 模板
    const line = container.querySelector('[data-age="26h"]');
    expect(line).not.toBeNull();
    expect(line).toHaveAttribute("data-cadence", "every 7.2d");
    expect(line!.textContent).toBe("26h · every 7.2d");
  });

  it("carries the full i18n labels on hover (values visible, labels in title)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("feodo", 26, 172.8)]);
    renderWithI18n(<SourcesPage />);
    const line = await screen.findByTitle(/content age/i);
    expect(line).toHaveAttribute(
      "title",
      "Content age 26h · Measured cadence every 7.2d",
    );
    // zh-CN 逐字裁决值(循 geo_asn 测试惯例直校 locale 表)
    expect(translate("zh-CN", "sources.health.contentAge")).toBe("内容年龄");
    expect(translate("zh-CN", "sources.health.observed")).toBe("实测节奏");
    expect(translate("zh-CN", "sources.health.cadence", { v: "7.2d" })).toBe("7.2d/次");
  });

  it("renders — for null age/cadence (no file / <5 events), never 'every —'", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("feodo", null, null)]);
    const { container } = renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    const line = container.querySelector("[data-age]");
    expect(line!.getAttribute("data-age")).toBe("—");
    expect(line!.getAttribute("data-cadence")).toBe("—");
    expect(line!.textContent).toBe("— · —");
    expect(screen.queryByText(/every/i)).toBeNull();
  });

  it("clamps negative age/cadence to 0h (clock-skew guard, review P2-1)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("feodo", -3, -0.4)]);
    const { container } = renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    const line = container.querySelector("[data-age]");
    // 不渲染负时长:-3 → 0h;-0.4 → clamp 0 → "every 0h"(非 every -0.4h)
    expect(line!.getAttribute("data-age")).toBe("0h");
    expect(line!.getAttribute("data-cadence")).toBe("every 0h");
  });

  it("rounds sub-hour values up to the nearest hour (mirrors backend ceil)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("feodo", 0.2, 47.9)]);
    const { container } = renderWithI18n(<SourcesPage />);
    await screen.findByText("feodo");
    const line = container.querySelector("[data-age]");
    // ceil 语义:0.2 → 1h;47.9 < 48 仍在 h 档 → 48h(非 2.0d),与后端一致
    expect(line!.getAttribute("data-age")).toBe("1h");
    expect(line!.getAttribute("data-cadence")).toBe("every 48h");
  });
});
