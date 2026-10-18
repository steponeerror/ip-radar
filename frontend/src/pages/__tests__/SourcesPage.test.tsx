import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import SourcesPage from "../SourcesPage";
import type { SourcesPageProps } from "../SourcesPage";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { translate } from "../../i18n/translate";
import {
  clearAdminToken,
  enqueueSingle,
  enqueueBatch,
  fetchEvalModel,
  getAdminTokens,
  getSources,
  putAdminToken,
  setSourceEnabled,
} from "../../api";
import type { TokenStatus } from "../../api";
import type { TaskState, BatchState, SourceInfo, SourceHealth } from "../../api";

// 源页重设计(2026-10-17 grill 裁决):三级扫读结构 —— 组头(可收起
// button + aria-expanded)→ 主行(单行 6 元素:状态点/源名/字段/覆盖/更新/
// 操作)→ 详情层(点行非控件区展开的 role=region)。manage=false 公开变体
// 已删:唯一调用方 AdminPage 恒传 tasks/batch/onUnauthorized。

vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
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
          content_age_h: 26,
          observed_interval_h: 172.8,
          refresh_period_h: 172.8,
        },
      },
    ]),
    fetchEvalModel: vi.fn().mockResolvedValue(null),
    enqueueSingle: vi.fn().mockResolvedValue({ task_id: "t1" }),
    enqueueBatch: vi.fn().mockResolvedValue({ batch_id: "b1" }),
    setSourceEnabled: vi.fn(),
    getAdminTokens: vi.fn().mockResolvedValue([]),
    putAdminToken: vi.fn().mockResolvedValue(undefined),
    clearAdminToken: vi.fn().mockResolvedValue(undefined),
  };
});

const TK = (over: Partial<TaskState>): TaskState => ({
  id: "t1", source: "feodo", host: null, state: "done",
  error: null, batch_id: null, ...over,
});

// 测试源构造器:缺省 = threat / fresh / loaded / 无 eval;health 覆盖经第三参。
const src = (name: string, over: Partial<SourceInfo> = {}, h: Partial<SourceHealth> = {}): SourceInfo => ({
  name,
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
    name,
    loaded: true,
    record_count: 10,
    covered_ips: 10,
    last_updated: null,
    is_stale: false,
    error: null,
    content_age_h: null,
    observed_interval_h: null,
    ...h,
  },
  ...over,
});

const renderPage = (props: Partial<SourcesPageProps> = {}) =>
  renderWithI18n(
    <SourcesPage tasks={[]} batch={null} onUnauthorized={() => {}} {...props} />,
  );

// 组默认全收起 → 需要行的用例先点组头展开
const expandGroup = async (name: RegExp | string = /threat intel/i) => {
  const btn = await screen.findByRole("button", { name });
  fireEvent.click(btn);
  return btn;
};

const openDetail = (name: string) => {
  fireEvent.click(screen.getByRole("button", { name: `Toggle details for ${name}` }));
};

beforeEach(() => {
  localStorage.clear();
});

describe("SourcesPage group collapse (three-tier structure)", () => {
  it("defaults all groups collapsed; expanding flips aria-expanded and persists to localStorage", async () => {
    const { container } = renderPage();
    const header = await screen.findByRole("button", { name: /threat intel/i });
    expect(header).toHaveAttribute("aria-expanded", "false");
    // 收起态:行不渲染,localStorage 未写
    expect(screen.queryByText("feodo")).toBeNull();
    expect(localStorage.getItem("ipradar.sources.groups")).toBeNull();
    fireEvent.click(header);
    expect(await screen.findByText("feodo")).toBeInTheDocument();
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(localStorage.getItem("ipradar.sources.groups")).toBe('{"threat":true}');
    // 更新列单行仅 timeAgo:诊断对(age · period)不再出现在主行,只待详情层
    expect(container.querySelector("[data-age]")).toBeNull();
    expect(screen.queryByText(/every/i)).toBeNull();
  });

  it("restores expanded groups from localStorage on mount", async () => {
    localStorage.setItem("ipradar.sources.groups", '{"threat":true}');
    renderPage();
    expect(await screen.findByText("feodo")).toBeInTheDocument();
  });

  it("collapsing persists false back to localStorage", async () => {
    renderPage();
    const header = await expandGroup();
    expect(await screen.findByText("feodo")).toBeInTheDocument();
    fireEvent.click(header);
    expect(screen.queryByText("feodo")).toBeNull();
    expect(localStorage.getItem("ipradar.sources.groups")).toBe('{"threat":false}');
  });
});

describe("SourcesPage group header anomaly count", () => {
  it("shows '· N anomalous' in amber when only stale/notLoaded/off anomalies", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("afeodo", {}, { is_stale: true }),
      src("zgood"),
    ]);
    renderPage();
    await screen.findByRole("button", { name: /threat intel/i });
    const seg = screen.getByText(/1 anomalous/);
    expect(seg).toHaveClass("text-amber-400");
    expect(seg).not.toHaveClass("text-red-400");
    expect(screen.getByText(/2 sources/)).toBeInTheDocument();
  });

  it("colors the anomaly count red when an error source is present", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("broken", {}, { error: "boom" }),
    ]);
    renderPage();
    await screen.findByRole("button", { name: /threat intel/i });
    expect(screen.getByText(/1 anomalous/)).toHaveClass("text-red-400");
  });

  it("renders no anomaly segment for an all-fresh group", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("onlygood")]);
    renderPage();
    await screen.findByRole("button", { name: /threat intel/i });
    expect(screen.queryByText(/anomalous/)).toBeNull();
  });
});

describe("SourcesPage in-group ordering", () => {
  it("puts anomalies first (error > stale/notLoaded > off), healthy alphabetical", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("zfresh"),
      src("astale", {}, { is_stale: true }),
      src("boff", { enabled: false }),
      src("cerror", {}, { error: "x" }),
    ]);
    renderPage();
    await expandGroup();
    const labels = (await screen.findAllByRole("button", { name: /^Toggle details for/ }))
      .map((b) => b.getAttribute("aria-label"));
    expect(labels).toEqual([
      "Toggle details for cerror",
      "Toggle details for astale",
      "Toggle details for boff",
      "Toggle details for zfresh",
    ]);
  });
});

describe("SourcesPage main row (single line, 6 elements)", () => {
  it("status dot per state; fresh row badge-free with near-invisible dot and no tint", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("cerror", {}, { error: "x" }),
      src("astale", {}, { is_stale: true }),
      src("boff", { enabled: false }),
      src("zfresh"),
    ]);
    const { container } = renderPage();
    await expandGroup();
    await screen.findByText("zfresh");
    // 状态徽章列已删:任何状态文本不出现在主行(仅存于点 title)
    expect(screen.queryByText("error")).toBeNull();
    expect(screen.queryByText("stale")).toBeNull();
    expect(container.querySelector('[data-status="error"]')).toHaveClass("bg-red-400");
    expect(container.querySelector('[data-status="stale"]')).toHaveClass("bg-amber-400");
    expect(container.querySelector('[data-status="off"]')).toHaveClass("bg-sky-700");
    // fresh 近隐形点 + 无轻微底色
    expect(container.querySelector('[data-status="fresh"]')).toHaveClass("bg-zinc-800");
    const freshLi = screen.getByRole("button", { name: "Toggle details for zfresh" }).closest("li")!;
    expect(freshLi.className).not.toMatch(/bg-(red|amber|sky)-/);
    // 异常行轻微底色
    const errLi = screen.getByRole("button", { name: "Toggle details for cerror" }).closest("li")!;
    expect(errLi).toHaveClass("bg-red-400/5");
  });

  it("renders covered_ips with a B tier, right-aligned tabular", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("ipinfo_lite", { category: "geo_asn", fields: ["country_code"] }, {
        loaded: true, record_count: 3_600_000, covered_ips: 3_700_000_000,
      }),
    ]);
    renderPage();
    await expandGroup(/geo & asn/i);
    const covered = await screen.findByText("3.7B");
    expect(covered).toHaveClass("text-right", "tabular-nums");
  });

  it("timeAgo shows 'no data' (not 'on-demand') for an offline source missing its raw file", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("abuseipdb", { fields: ["is_malicious"] }, { loaded: false, covered_ips: 0, is_stale: true }),
    ]);
    renderPage();
    await expandGroup();
    expect(await screen.findByText("no data")).toBeInTheDocument();
  });

  it("row click toggles detail without firing the action controls", async () => {
    renderPage();
    await expandGroup();
    openDetail("feodo");
    expect(screen.getByRole("region")).toBeInTheDocument();
    expect(enqueueSingle).not.toHaveBeenCalled();
    expect(setSourceEnabled).not.toHaveBeenCalled();
  });
});

describe("SourcesPage detail layer (expanded region)", () => {
  it("shows r / θ+CI / eval verdict / age·period / feeds / last error; collapses on second click", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("spamhaus", {
        fields: ["is_malicious"],
        reliability: 0.9,
        eval: { verdict: "POSITIVE-VERIFIED", at: "2026-08-28" },
      }, {
        error: "download failed: 403",
        content_age_h: 26,
        refresh_period_h: 172.8,
        feeds: [
          { name: "AWS", last_updated: "2026-10-01T00:00:00Z", is_stale: false },
          { name: "Azure", last_updated: null, is_stale: true },
        ],
      }),
    ]);
    vi.mocked(fetchEvalModel).mockResolvedValueOnce({
      scores: [
        { source: "spamhaus", theta: 0.61, ci_lo: 0.55, ci_hi: 0.68, declared_r: 0.9 },
      ],
    });
    const { container } = renderPage();
    await expandGroup();
    openDetail("spamhaus");
    const region = screen.getByRole("region");
    // region 由行按钮标注(aria-labelledby)
    const rowBtn = screen.getByRole("button", { name: "Toggle details for spamhaus" });
    expect(region.getAttribute("aria-labelledby")).toBe(rowBtn.id);
    // 声明 r(生产权重)+ 实测 θ+CI
    expect(container.querySelector('[data-detail="r"]')!.textContent).toBe("r 0.90");
    const theta = container.querySelector('[data-detail="theta"]')!;
    expect(theta.textContent).toBe("θ 0.61 [0.55–0.68]");
    expect(theta.getAttribute("title")).toMatch(/corroboration/i);
    // 评估 verdict(带日期 title)
    const verdict = screen.getByText("verified");
    expect(verdict).toHaveAttribute("title", "2026-08-28");
    // 内容年龄 · 刷新周期
    expect(container.querySelector('[data-detail="age"]')!.textContent).toBe("26h");
    expect(container.querySelector('[data-detail="period"]')!.textContent).toBe("every 7.2d");
    // feeds 芯片:fresh 灰 / stale 红
    const aws = container.querySelector('[data-feed="AWS"]');
    const azure = container.querySelector('[data-feed="Azure"]');
    expect(aws).toHaveAttribute("data-stale", "false");
    expect(aws).toHaveClass("text-zinc-400");
    expect(azure).toHaveAttribute("data-stale", "true");
    expect(azure).toHaveClass("text-red-400");
    // 最近错误
    expect(screen.getByText("download failed: 403")).toHaveClass("text-red-400");
    // 再点收起
    openDetail("spamhaus");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("keeps several rows expanded at once (same group)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("alpha"), src("beta")]);
    renderPage();
    await expandGroup();
    openDetail("alpha");
    openDetail("beta");
    expect(screen.getAllByRole("region")).toHaveLength(2);
  });

  it("no eval → 'No eval report'; unscored θ → '—'; age/period render detail values", async () => {
    const { container } = renderPage();
    await expandGroup();
    openDetail("feodo");
    expect(container.querySelector('[data-detail="eval"]')!.textContent).toBe("No eval report");
    expect(container.querySelector('[data-detail="theta"]')!.textContent).toBe("—");
    // 默认 mock:content_age 26h / period 172.8h(null → — 的情况见 fmtHours 档位用例)
    expect(container.querySelector('[data-detail="age"]')!.textContent).toBe("26h");
    expect(container.querySelector('[data-detail="period"]')!.textContent).toBe("every 7.2d");
  });

  it("renders 'never' for age/period ≥1000d, zh-CN verbatim '从不'", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("ancient", {}, { content_age_h: 30_000, refresh_period_h: 26_280 }),
    ]);
    const { container } = renderPage();
    await expandGroup();
    openDetail("ancient");
    expect(container.querySelector('[data-detail="age"]')!.textContent).toBe("never");
    expect(container.querySelector('[data-detail="period"]')!.textContent).toBe("never");
    expect(screen.queryByText(/1250\.0d/)).toBeNull();
    expect(translate("zh-CN", "sources.detail.never")).toBe("从不");
  });

  it("renders NO-DATA verdict with collapse tooltip instead of date (W4)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("deadfeed", { eval: { verdict: "NO-DATA", at: "2026-09-28" } }),
    ]);
    renderPage();
    await expandGroup();
    openDetail("deadfeed");
    expect(await screen.findByText("no-data")).toBeInTheDocument();
    expect(screen.getByTitle(/did not contribute/i)).toBeInTheDocument();
    expect(screen.queryByTitle("2026-09-28")).toBeNull();
  });

  it("fmtHours tiers in detail: null → —, negative clamps to 0h, sub-hour ceils up", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("clampy", {}, { content_age_h: -3 }),
      src("ceily", {}, { content_age_h: 0.2, refresh_period_h: 47.9 }),
      src("nully"),
    ]);
    const { container } = renderPage();
    await expandGroup();
    // 健康源字母序:ceily < clampy < nully;47.9 < 48 仍在 h 档 → 48h(非 2.0d)
    openDetail("ceily");
    openDetail("clampy");
    openDetail("nully");
    const ages = Array.from(container.querySelectorAll('[data-detail="age"]'))
      .map((el) => el.textContent);
    const periods = Array.from(container.querySelectorAll('[data-detail="period"]'))
      .map((el) => el.textContent);
    expect(ages).toEqual(["1h", "0h", "—"]);
    expect(periods).toEqual(["every 48h", "—", "—"]);
  });
});

describe("SourcesPage manage behaviors (kept pins, new structure)", () => {
  it("renders Toggle switches and Update buttons (public variant deleted)", async () => {
    renderPage();
    await expandGroup();
    expect(await screen.findByRole("button", { name: /Update/i })).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("Update button enqueues single-source task", async () => {
    renderPage();
    await expandGroup();
    const btn = await screen.findByRole("button", { name: /Update/i });
    fireEvent.click(btn);
    await waitFor(() => expect(enqueueSingle).toHaveBeenCalledWith("feodo"));
  });

  it("Toggle switch PATCHes the source and rolls back on failure", async () => {
    vi.mocked(setSourceEnabled).mockRejectedValueOnce(new Error("403"));
    renderPage();
    await expandGroup();
    const sw = await screen.findByRole("switch");
    expect(sw).toHaveAttribute("aria-checked", "true");
    fireEvent.click(sw);
    await waitFor(() => expect(setSourceEnabled).toHaveBeenCalledWith("feodo", false));
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true")); // rollback
  });

  it("Refresh all enqueues batch", async () => {
    renderPage();
    const btn = await screen.findByRole("button", { name: /Refresh all/i });
    // loading 期间按钮 disabled, click 被吞 — 等可用再点 (CI 慢机竞态)
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);
    await waitFor(() => expect(enqueueBatch).toHaveBeenCalled());
  });

  it("disables Refresh-all while a batch is running (batch prop)", async () => {
    const batch: BatchState = { id: "b1", state: "running", done: 0, total: 3 };
    renderPage({ batch });
    const btn = await screen.findByRole("button", { name: /Refreshing all/i });
    expect(btn).toBeDisabled();
  });

  it("debounce-refetches sources when a passed-down task reaches done", async () => {
    const { rerender } = renderWithI18n(
      <SourcesPage tasks={[]} batch={null} onUnauthorized={() => {}} />,
    );
    await screen.findByRole("button", { name: /threat intel/i });
    const initialCalls = vi.mocked(getSources).mock.calls.length;
    // doneCount 0 → 1(AdminPage 下传的任务完成)触发 500ms 去抖重拉
    rerender(<SourcesPage tasks={[TK({ state: "done" })]} batch={null} onUnauthorized={() => {}} />);
    await waitFor(
      () => expect(vi.mocked(getSources).mock.calls.length).toBeGreaterThan(initialCalls),
      { timeout: 2000 },
    );
  });

  it("shows progress from the latest task when a source has stale history", async () => {
    // Regression: tasks arrive oldest-first; the latest task per source must win.
    renderPage({
      tasks: [
        TK({ id: "t-old", state: "done" }),
        TK({ id: "t-new", state: "downloading" }),
      ],
    });
    await expandGroup();
    expect(await screen.findByRole("button", { name: /Downloading/i })).toBeInTheDocument();
  });

  it("treats a throttled task as busy: Update disabled and labeled Queued", async () => {
    renderPage({ tasks: [TK({ id: "t-th", state: "throttled" })] });
    await expandGroup();
    const btn = await screen.findByRole("button", { name: "Queued" });
    expect(btn).toBeDisabled();
  });

  it("shows loading percentage from received/total (100/200 → 50%)", async () => {
    renderPage({
      tasks: [TK({ id: "t-load", state: "loading", received: 100, total: 200 })],
    });
    await expandGroup();
    expect(await screen.findByRole("button", { name: /Loading… 50%/ })).toBeInTheDocument();
  });

  it("clamps loading percentage at 100% when received exceeds total (250/200)", async () => {
    renderPage({
      tasks: [TK({ id: "t-load2", state: "loading", received: 250, total: 200 })],
    });
    await expandGroup();
    expect(await screen.findByRole("button", { name: /Loading… 100%/ })).toBeInTheDocument();
  });

  it("401 on load kicks to login via onUnauthorized (spec §9)", async () => {
    const err = Object.assign(new Error("Not authenticated"), { status: 401 });
    (getSources as unknown as Mock).mockRejectedValueOnce(err);
    const onUnauthorized = vi.fn();
    renderPage({ onUnauthorized });
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
  });
});

describe("SourcesPage group labels (i18n)", () => {
  it("geo_asn group header renamed (R6): en on page, zh-CN verbatim in locale", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([
      src("ipinfo_lite", { category: "geo_asn", fields: ["country_code"] }),
    ]);
    renderPage();
    expect(await screen.findByRole("button", { name: /Geo & ASN data/i })).toBeInTheDocument();
    expect(translate("zh-CN", "sources.cat.geo_asn")).toBe("地理 / ASN 数据");
  });

  it("zh-CN verbatim values for the new group/detail keys", () => {
    expect(translate("zh-CN", "sources.group.sourcesUnit")).toBe("源");
    expect(translate("zh-CN", "sources.group.anomalyUnit")).toBe("异常");
    expect(translate("zh-CN", "sources.detail.evalNone")).toBe("无评估报告");
    expect(translate("zh-CN", "sources.row.expandAria", { name: "feodo" })).toBe("展开 feodo 详情");
  });
});

// ── token 界面接线(T3;grill 裁决冻结:未配置出「填 token」琥珀入口,密码型
// 输入不回显既有值,成功即关;详情层「已配置 ····{tail4} · [清除]」;拉取失败
// 静默 → 全视为已配置入口全隐;OTX 一 key 双源同状态)──
describe("SourcesPage token wiring (T3)", () => {
  const tokenRow = (over: Partial<TokenStatus> = {}): TokenStatus => ({
    env_var: "ABUSEIPDB_API_KEY",
    sources: ["abuseipdb"],
    configured: false,
    tail4: null,
    ...over,
  });

  it("unconfigured token source shows the amber 'Set token' entry in the main row", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("abuseipdb", { fields: ["is_malicious"] })]);
    vi.mocked(getAdminTokens).mockResolvedValueOnce([tokenRow()]);
    renderPage();
    await expandGroup();
    const btn = await screen.findByRole("button", { name: "Set token for abuseipdb" });
    expect(btn).toHaveClass("border-amber-400/40");
    expect(btn).toHaveTextContent("Set token");
  });

  it("configured token source hides the entry; detail layer shows 'Configured ····{tail4}' with Clear → DELETE", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("abuseipdb", { fields: ["is_malicious"] })]);
    vi.mocked(getAdminTokens).mockResolvedValueOnce([tokenRow({ configured: true, tail4: "9f8e" })]);
    const { container } = renderPage();
    await expandGroup();
    await screen.findByText("abuseipdb");
    expect(screen.queryByRole("button", { name: "Set token for abuseipdb" })).toBeNull();
    openDetail("abuseipdb");
    expect(container.querySelector('[data-detail="token"]')!.textContent).toContain("····9f8e");
    expect(container.querySelector('[data-detail="token"]')!.textContent).toContain("Configured");
    fireEvent.click(screen.getByRole("button", { name: "Clear ABUSEIPDB_API_KEY" }));
    await waitFor(() => expect(clearAdminToken).toHaveBeenCalledWith("ABUSEIPDB_API_KEY"));
  });

  it("tokens fetch failure is silent: every entry hidden (all treated as configured)", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("abuseipdb", { fields: ["is_malicious"] })]);
    vi.mocked(getAdminTokens).mockRejectedValueOnce(new Error("boom"));
    renderPage();
    await expandGroup();
    expect(await screen.findByText("abuseipdb")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Set token/ })).toBeNull();
    expect(screen.queryByText(/Failed to/)).toBeNull(); // 静默:无错误横幅
  });

  it("save dialog: password input, empty on open (never echoes), PUT on submit, closes on success", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("abuseipdb", { fields: ["is_malicious"] })]);
    vi.mocked(getAdminTokens).mockResolvedValueOnce([tokenRow()]);
    renderPage();
    await expandGroup();
    fireEvent.click(await screen.findByRole("button", { name: "Set token for abuseipdb" }));
    const input = screen.getByLabelText("Token value");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveValue(""); // 硬约束:不回显既有值(API 也不出值)
    fireEvent.change(input, { target: { value: "secret-key-9999" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() =>
      expect(putAdminToken).toHaveBeenCalledWith("ABUSEIPDB_API_KEY", "secret-key-9999"),
    );
    await waitFor(() => expect(screen.queryByLabelText("Token value")).toBeNull());
    // 本地态已翻 configured:入口消失,详情层立即见尾 4 位
    expect(screen.queryByRole("button", { name: "Set token for abuseipdb" })).toBeNull();
    openDetail("abuseipdb");
    expect(screen.getByText(/····9999/)).toBeInTheDocument();
  });

  it("otx and otx_subscribed share OTX_API_KEY: both entries vanish after one save", async () => {
    vi.mocked(getSources).mockResolvedValueOnce([src("otx"), src("otx_subscribed")]);
    vi.mocked(getAdminTokens).mockResolvedValueOnce([
      { env_var: "OTX_API_KEY", sources: ["otx", "otx_subscribed"], configured: false, tail4: null },
    ]);
    renderPage();
    await expandGroup();
    expect(await screen.findByRole("button", { name: "Set token for otx" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set token for otx_subscribed" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Set token for otx" }));
    fireEvent.change(screen.getByLabelText("Token value"), { target: { value: "otxkey-1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(putAdminToken).toHaveBeenCalledWith("OTX_API_KEY", "otxkey-1234"));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Set token for otx" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Set token for otx_subscribed" })).toBeNull();
    });
  });

  it("zh-CN verbatim token wording (grill-frozen 「填 token」)", () => {
    expect(translate("zh-CN", "sources.token.fill")).toBe("填 token");
    expect(translate("zh-CN", "sources.token.configured")).toBe("已配置");
    expect(translate("zh-CN", "sources.token.clear")).toBe("清除");
  });
});
