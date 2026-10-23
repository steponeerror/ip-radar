import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import OpsReviewSection from "../OpsReviewSection";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { getOpsItems, readOpsItem, postOpsReview } from "../../api";

// P1 T4 审阅面(票 #156,spec #152 §4;ADR 0006):条目列表(后端已排序,
// 前端不重排)+ 每行四键(同意·后果/修改/忽略·必填原因/稍后)。夹具字段
// 取自 T1/T2 产条真实形状(十字段冻结;独立真源 = spec #152 §1 与
// _ops_detectors 产条字面),不从被测组件反推。
vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    getOpsItems: vi.fn(),
    readOpsItem: vi.fn(),
    postOpsReview: vi.fn(),
  };
});

const NOW = Date.parse("2026-10-23T06:00:00Z");

// 夹具:序 = 故意不给前端任何「看似该排」的序(medium 在 high 前、
// 集外在可逆前)——列表序真源 = 后端 list_items,前端重排即失败。
const ITEMS = [
  {
    id: "2026-10-23-item-aaaa000001", action: "refresh_source",
    args: { source: "feodo_tracker" },
    evidence: { content_age_h: 96.2, refresh_period_h: 24 },
    impact: "feodo_tracker 内容超龄,数据新鲜度与覆盖受损",
    rollback: "刷新成功即自愈;无不可逆变更",
    dedup_key: { source: "feodo_tracker", probe_class: "staleness", error_signature: "age_gt_2x_refresh" },
    severity: "medium", cause_group: "staleness", status: "active",
    supersedes: null, modified: "2026-10-23T05:00:00Z",
  },
  {
    id: "2026-10-23-item-bbbb000002", action: "retry_download",
    args: { source: "spamhaus_drop" },
    evidence: { consecutive_failures: 3, error_code: "HTTP 403" },
    impact: "spamhaus_drop 数据停更,威胁覆盖面收缩",
    rollback: "重新触发下载即可恢复;无不可逆变更",
    dedup_key: { source: "spamhaus_drop", probe_class: "download", error_signature: "http_403_anonymous" },
    severity: "high", cause_group: "download_failure", status: "active",
    supersedes: null, modified: "2026-10-23T05:30:00Z",
  },
  {
    id: "2026-10-22-item-cccc000003", action: "retry_download",
    args: { source: "done_src" },
    evidence: { consecutive_failures: 3 },
    impact: "done_src 数据停更(已处置)",
    rollback: "重新触发下载即可恢复",
    dedup_key: { source: "done_src", probe_class: "download", error_signature: "x" },
    severity: "medium", cause_group: "download_failure", status: "done",
    supersedes: null, modified: "2026-10-22T05:30:00Z",
  },
];

const ITEM_TEXT = [
  "---",
  "id: 2026-10-23-item-bbbb000002",
  "action: retry_download",
  "status: active",
  "---",
  "# 待审:源 spamhaus_drop 下载失败(连续 3 轮)",
  "",
  "末次错误(HTTP 403/http_403_anonymous):Anonymous connections not permitted",
].join("\n");

function renderSection() {
  return renderWithI18n(<OpsReviewSection onUnauthorized={vi.fn()} />);
}

// 行展开开关 = li 内唯一带 aria-expanded 的按钮(行为断言走 aria,不断类名)
const toggleOf = (li: HTMLElement): HTMLElement => {
  const btn = within(li).getAllByRole("button").find((b) => b.hasAttribute("aria-expanded"));
  if (!btn) throw new Error("row toggle (aria-expanded) not found");
  return btn;
};
// 按行内容片段取行(动作/源名)
const rowOf = async (frag: string) => {
  const rows = await screen.findAllByRole("listitem");
  const li = rows.find((r) => r.textContent?.includes(frag));
  if (!li) throw new Error(`row not found: ${frag}`);
  return li;
};

beforeEach(() => {
  vi.clearAllMocks();
  // 只伪 Date(相对时间/稍后 wake_at 计算确定性),定时器保真——
  // testing-library 的 waitFor 依赖真定时器,全量伪时会卡死异步查询
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  vi.mocked(getOpsItems).mockResolvedValue(ITEMS);
  vi.mocked(readOpsItem).mockResolvedValue(ITEM_TEXT);
});

afterEach(() => {
  vi.useRealTimers();
});

// ── 列表面:序 = 后端响应序,行信息齐全 ─────────────────────────────

describe("OpsReviewSection — 列表(票 #156)", () => {
  it("渲染序 = 后端响应序(medium 先于 high、集外先于可逆)——前端不重排", async () => {
    renderSection();
    const rows = await screen.findAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("refresh_source");
    expect(rows[1].textContent).toContain("retry_download");
    expect(rows[1].textContent).toContain("spamhaus_drop");
    expect(rows[2].textContent).toContain("Resolved"); // 终态 chip
  });

  it("行信息:严重度点(title=High)/动作/源/根因组/摘要(impact)/相对时间(title=ISO 原文)", async () => {
    renderSection();
    const rows = await screen.findAllByRole("listitem");
    const high = within(rows[1]);
    expect(high.getByTitle("High")).toBeTruthy();        // 严重度点(aria-label 同名)
    expect(high.getByTitle("2026-10-23T05:30:00Z")).toBeTruthy(); // 时间 title=完整戳
    expect(rows[1].textContent).toContain("download_failure");    // 根因组
    expect(rows[1].textContent).toContain("spamhaus_drop 数据停更,威胁覆盖面收缩"); // 摘要
  });

  it("空态:基准「暂无」式居中提示 + 计数如实 (0)", async () => {
    vi.mocked(getOpsItems).mockResolvedValue([]);
    renderSection();
    expect(await screen.findByRole("heading", { name: "Pending review items (0)" })).toBeTruthy();
    expect(await screen.findByText(/No pending items/i)).toBeTruthy();
  });

  it("展开行 → 详情 = 条目全文逐字(readOpsItem 惰性取)", async () => {
    renderSection();
    await screen.findAllByRole("listitem");
    const li = await rowOf("spamhaus_drop");
    fireEvent.click(within(li).getByRole("button", { name: /retry_download/ }));
    await waitFor(() => expect(vi.mocked(readOpsItem)).toHaveBeenCalledWith(
      "2026-10-23-item-bbbb000002"));
    expect(await screen.findByText(/# 待审:源 spamhaus_drop 下载失败/)).toBeTruthy();
  });
});

// ── 四键:可见文案写后果 / 无默认选中(NN/g)────────────────────────

describe("OpsReviewSection — 四键可见文案(票 #156)", () => {
  it("可逆闭集动作:同意按钮写执行后果(「同意·执行:重试下载」面)", async () => {
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    expect(await screen.findByRole("button", { name: "Agree · execute: retry download" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Modify…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ignore…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Snooze · tomorrow" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Snooze · next week" })).toBeTruthy();
  });

  it("集外动作:同意按钮写「同意·立项」(读后端可逆闭集,不前端自造)", async () => {
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("feodo_tracker")));
    expect(await screen.findByRole("button", { name: "Agree · file as proposal" })).toBeTruthy();
  });

  it("终态条目(done):无四键(后端 422 拒审,不送明知必拒的请求),详情仍可展开", async () => {
    renderSection();
    const rows = await screen.findAllByRole("listitem");
    const done = within(rows[2]);
    expect(done.getByText("Resolved")).toBeTruthy(); // 状态 chip
    fireEvent.click(toggleOf(rows[2]));
    await waitFor(() => expect(vi.mocked(readOpsItem)).toHaveBeenCalledWith(
      "2026-10-22-item-cccc000003"));
    expect(screen.queryByRole("button", { name: /Agree/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Modify…" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ignore…" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Snooze/i })).toBeNull();
  });
});

// ── 同意:提交载荷 + 成功回执 + 列表重拉 ───────────────────────────

describe("OpsReviewSection — 同意", () => {
  it("agree → postOpsReview(id,'agree');已执行回执含后果与规则名;列表重拉", async () => {
    vi.mocked(postOpsReview).mockResolvedValue({
      item: "2026-10-23-item-bbbb000002", verdict: "agree", status: "done",
      executed: true, proposal_only: false,
      precedent: "2026-10-23-ruling-abc123def0.md", created: true,
      superseded: null, queue_appended: false, wake_at: null,
    });
    renderSection();
    expect(await screen.findAllByRole("listitem")).toHaveLength(3);
    const callsBefore = vi.mocked(getOpsItems).mock.calls.length;
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Agree · execute: retry download" }));
    await waitFor(() => expect(vi.mocked(postOpsReview)).toHaveBeenCalledWith(
      "2026-10-23-item-bbbb000002", "agree", undefined));
    // 成功回执:已执行 + 规则名(executed/proposal_only 读后端响应,不重推导)
    expect(await screen.findByText(
      /Executed: retry download; rule 2026-10-23-ruling-abc123def0\.md/)).toBeTruthy();
    // 操作反馈:成功后列表重拉
    await waitFor(() => expect(vi.mocked(getOpsItems).mock.calls.length)
      .toBeGreaterThan(callsBefore));
  });

  it("集外 agree → 回执「仅立项」(proposal_only=True 读响应)", async () => {
    vi.mocked(postOpsReview).mockResolvedValue({
      item: "2026-10-23-item-aaaa000001", verdict: "agree", status: "done",
      executed: false, proposal_only: true,
      precedent: "2026-10-23-ruling-1111111111.md", created: true,
      superseded: null, queue_appended: false, wake_at: null,
    });
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("feodo_tracker")));
    fireEvent.click(await screen.findByRole("button", { name: "Agree · file as proposal" }));
    expect(await screen.findByText(/Proposal only — action outside the executable set/))
      .toBeTruthy();
  });

  it("失败面:500 信封 → opsErrorText 人话化,不裸抛 code", async () => {
    vi.mocked(postOpsReview).mockRejectedValue(Object.assign(
      new Error("动作执行失败(retry_download …): unknown source"),
      { status: 500, code: "internal" },
    ));
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Agree · execute: retry download" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toMatch(/server error/i);
  });
});

// ── 修改:args 编辑(JSON 文本域)与提交载荷 ─────────────────────────

describe("OpsReviewSection — 修改", () => {
  it("编辑器预填条目现值;改后提交 {verdict:'modify', args} 载荷逐字", async () => {
    vi.mocked(postOpsReview).mockResolvedValue({
      item: "2026-10-23-item-bbbb000002", verdict: "modify", status: "done",
      executed: true, proposal_only: false,
      precedent: "2026-10-23-ruling-2222222222.md", created: true,
      superseded: null, queue_appended: false, wake_at: null,
    });
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Modify…" }));
    const editor = await screen.findByRole("textbox", { name: /Item args/i });
    // 预填 = 条目现值(JSON 文本域;数据非选项,不属 NN/g 默认选中面)
    expect((editor as HTMLTextAreaElement).value).toBe('{\n  "source": "spamhaus_drop"\n}');
    fireEvent.change(editor, { target: { value: '{"source": "spamhaus_drop", "force": true}' } });
    fireEvent.click(screen.getByRole("button", { name: "Submit modified args" }));
    await waitFor(() => expect(vi.mocked(postOpsReview)).toHaveBeenCalledWith(
      "2026-10-23-item-bbbb000002", "modify",
      { args: { source: "spamhaus_drop", force: true } }));
  });

  it("非法 JSON:提交禁用 + 提示(后端 422 之前先拦)", async () => {
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Modify…" }));
    const editor = await screen.findByRole("textbox", { name: /Item args/i });
    fireEvent.change(editor, { target: { value: "{not json" } });
    expect(screen.getByRole("button", { name: "Submit modified args" })).toBeDisabled();
    expect(screen.getByText(/not a valid JSON object/i)).toBeTruthy();
  });
});

// ── 忽略:原因必填(空禁提交)──────────────────────────────────────

describe("OpsReviewSection — 忽略", () => {
  it("空原因禁提交;填后提交 {verdict:'ignore', reason};回执含规则名", async () => {
    vi.mocked(postOpsReview).mockResolvedValue({
      item: "2026-10-23-item-bbbb000002", verdict: "ignore", status: "dismissed",
      executed: false, proposal_only: false,
      precedent: "2026-10-23-ruling-3333333333.md", created: true,
      superseded: null, queue_appended: false, wake_at: null,
    });
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Ignore…" }));
    const input = screen.getByRole("textbox", { name: /Ignore reason/i });
    // 忽略原因初始为空(NN/g:无预填/无默认选中),空禁提交
    expect((input as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Submit ignore" })).toBeDisabled();
    expect(input).toHaveAttribute("placeholder", expect.stringMatching(/probe noise/i));
    fireEvent.change(input, { target: { value: "探测噪音·数据面 48h 零失败" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit ignore" }));
    await waitFor(() => expect(vi.mocked(postOpsReview)).toHaveBeenCalledWith(
      "2026-10-23-item-bbbb000002", "ignore",
      { reason: "探测噪音·数据面 48h 零失败" }));
    expect(await screen.findByText(/Ignored — rule 2026-10-23-ruling-3333333333\.md/))
      .toBeTruthy();
  });
});

// ── 稍后:预设选项(明天/下周)直发,无默认选中 ─────────────────────

describe("OpsReviewSection — 稍后", () => {
  it("明天 → wake_at = +24h(ISO 带时区,未来时);下周 → +7d", async () => {
    vi.mocked(postOpsReview).mockResolvedValue({
      item: "2026-10-23-item-bbbb000002", verdict: "snooze", status: "snoozed",
      executed: false, proposal_only: false,
      precedent: null, created: null, superseded: null,
      queue_appended: null, wake_at: "2026-10-24T06:00:00Z",
    });
    renderSection();
    await screen.findAllByRole("listitem");
    fireEvent.click(toggleOf(await rowOf("spamhaus_drop")));
    fireEvent.click(await screen.findByRole("button", { name: "Snooze · tomorrow" }));
    await waitFor(() => expect(vi.mocked(postOpsReview)).toHaveBeenCalledTimes(1));
    const [id, verdict, extra] = vi.mocked(postOpsReview).mock.calls[0];
    expect(id).toBe("2026-10-23-item-bbbb000002");
    expect(verdict).toBe("snooze");
    expect(Date.parse(extra?.wakeAt ?? "")).toBe(NOW + 24 * 3600_000); // 明天(未来时)
    // 回执:稍后至 {when}(响应 wake_at 归一 UTC;fmtLocal 走本地时区)
    expect(await screen.findByText(/Snoozed until 2026-10-2[34]/)).toBeTruthy();
    // 下周 → +7d
    fireEvent.click(screen.getByRole("button", { name: "Snooze · next week" }));
    await waitFor(() => expect(vi.mocked(postOpsReview)).toHaveBeenCalledTimes(2));
    const extra2 = vi.mocked(postOpsReview).mock.calls[1][2];
    expect(Date.parse(extra2?.wakeAt ?? "")).toBe(NOW + 7 * 24 * 3600_000);
  });
});
