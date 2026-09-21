import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import SourcesPage from "../SourcesPage";
import { renderWithI18n } from "../../test/i18nTestUtils";
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
});
