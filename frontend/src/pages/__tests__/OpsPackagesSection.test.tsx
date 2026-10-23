import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import OpsPackagesSection from "../OpsPackagesSection";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { listOpsPackages, readOpsPackage, readOpsPrecedent, postOpsRuling } from "../../api";

// 旧包报告档案(P1 T4,票 #156,ADR 0006):markdown 包降级为条目集的只读
// 渲染视图——列表 → 详情(报告文逐字:证据 call_id+field+value/trace/判例
// 引用可点开全文),不再承载审阅。人裁交互面(逐字选建议行 + 三动作)
// 已移除:四键审阅在「审阅」子 tab(OpsReviewSection.test.tsx)。报告正文
// 形状 = ops/agent/prompts 输出契约(固定节)——fixture 取自该契约,不从
// 实现反推。
vi.mock("../../api", async () => {
  const real = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...real,
    listOpsPackages: vi.fn(),
    readOpsPackage: vi.fn(),
    readOpsPrecedent: vi.fn(),
    postOpsRuling: vi.fn(),
  };
});

const PKG_NAME = "2026-10-20-discover-1030.md";

const PKG_TEXT = [
  "# 裁决包",
  "",
  "## 注入判例",
  "",
  "- 2026-10-18-blocklist-de-legit.md",
  "",
  "## 候选表",
  "",
  "| URL | 出版方 | 覆盖轴 |",
  "|---|---|---|",
  "| https://example.com/list.csv | Example | threat |",
  "",
  "## 硬门数字",
  "",
  "- call_12:exclusive_rate=0.587",
  "- call_13:repo_kb=821",
  "",
  "## 建议",
  "",
  "- ENQUEUE threatview_c2 — CPS 镜像 cobaltstrike_ips 排他 57.0%(171/300),建议单独立项直连",
  "- 人裁 语义矩阵槽位冲突(example),证据不足",
  "",
  "## 自动执行区",
  "",
  "无",
  "",
  "## 人裁区",
  "",
  "无",
  "",
  "## 摘要",
  "",
  "整体判断:与在案判例一致。",
].join("\n");

function renderSection(roundTick = 0) {
  return renderWithI18n(
    <OpsPackagesSection onUnauthorized={vi.fn()} roundTick={roundTick} />,
  );
}

async function openDetail() {
  await screen.findByRole("button", { name: new RegExp(PKG_NAME) });
  fireEvent.click(screen.getByRole("button", { name: new RegExp(PKG_NAME) }));
  await waitFor(() => expect(vi.mocked(readOpsPackage)).toHaveBeenCalledWith(PKG_NAME));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listOpsPackages).mockResolvedValue([
    { name: PKG_NAME, size: 4096, modified: "2026-10-20T10:30:00+00:00" },
  ]);
  vi.mocked(readOpsPackage).mockResolvedValue(PKG_TEXT);
});

describe("OpsPackagesSection — list → detail", () => {
  it("lists reports (newest first metadata); empty state without a round", async () => {
    vi.mocked(listOpsPackages).mockResolvedValueOnce([]);
    renderSection();
    expect(await screen.findByText(/No reports yet/i)).toBeTruthy();
    expect(listOpsPackages).toHaveBeenCalledTimes(1);
  });

  it("detail shows the report verbatim (evidence call_id+field=value / trace) with precedent refs clickable", async () => {
    vi.mocked(readOpsPrecedent).mockResolvedValue("# 判例:blocklist-de-legit\n\nid: 2026-10-18-blocklist-de-legit\n");
    renderSection();
    await openDetail();
    // 证据三元组(call_id:field=value)与 trace 全文在场(逐字)
    expect(screen.getByText(/call_12:exclusive_rate=0.587/)).toBeTruthy();
    expect(screen.getByText(/整体判断:与在案判例一致/)).toBeTruthy();
    // 判例引用可点开全文
    fireEvent.click(screen.getByRole("button", { name: "2026-10-18-blocklist-de-legit.md" }));
    expect(vi.mocked(readOpsPrecedent)).toHaveBeenCalledWith("2026-10-18-blocklist-de-legit.md");
    expect(await screen.findByText(/# 判例:blocklist-de-legit/)).toBeTruthy();
  });

  it("re-fetches the list when a round settles (roundTick bump)", async () => {
    const onUnauthorized = vi.fn(); // 稳定引用:rerender 不因回调换身份而重拉
    const { rerender } = renderWithI18n(
      <OpsPackagesSection onUnauthorized={onUnauthorized} roundTick={0} />,
    );
    await screen.findByRole("button", { name: new RegExp(PKG_NAME) });
    expect(listOpsPackages).toHaveBeenCalledTimes(1);
    rerender(<OpsPackagesSection onUnauthorized={onUnauthorized} roundTick={1} />);
    await waitFor(() => expect(listOpsPackages).toHaveBeenCalledTimes(2));
  });
});

// ── 票 #149:报告列表行元数据(大小+相对时间)+ 节头计数 ──

describe("OpsPackagesSection — 列表行元数据与计数(票 #149)", () => {
  it("行元数据:大小 KB + 相对时间(title=ISO 原文,证据不灭失);节头计数 N 个", async () => {
    renderSection(); // beforeEach 夹具:1 包,4096B,modified=2026-10-20T10:30:00+00:00
    expect(await screen.findByRole("heading", { name: "Reports (1)" })).toBeTruthy();
    expect(screen.getByText("4.0 KB")).toBeTruthy();
    const timed = screen.getByTitle("2026-10-20T10:30:00+00:00");
    expect(timed.textContent ?? "").toMatch(/ago$|^just now/);
  });

  it("空列表:计数如实显 (0)(视觉门 2026-10-21 微5)+ 基准「暂无」式空态入容器(不留纯空白)", async () => {
    vi.mocked(listOpsPackages).mockResolvedValueOnce([]);
    renderSection();
    await screen.findByText(/No reports yet/i);
    expect(screen.getByRole("heading", { name: "Reports (0)" })).toBeTruthy();
  });

  it("详情态节头不带计数(计数属列表面;详情无行集可数)", async () => {
    renderSection();
    await openDetail();
    expect(screen.getByRole("heading", { name: "Reports" })).toBeTruthy();
  });
});

// ── 票 #156:旧包档案化——纯只读渲染,人裁交互移除 ──

describe("OpsPackagesSection — 旧包档案化(票 #156,只读)", () => {
  it("详情零裁决交互:无建议选行/无三动作按钮/无「仅立项」徽标——审阅面在「审阅」子 tab", async () => {
    renderSection();
    await openDetail();
    // 三动作按钮不在场(票 #136 旧面:Agree/Overrule/Amend)
    expect(screen.queryByRole("button", { name: "Agree" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Overrule" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Amend" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Submit amended ruling/i })).toBeNull();
    // 建议行不带选择态/「仅立项」徽标(逐字建议文本仍在报告全文里,但不可选)
    expect(screen.queryByText(/proposal only/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /^ENQUEUE threatview_c2/ })).toBeNull();
    // 报告全文逐字在场(「## 建议」节原样可见,不可交互)
    expect(screen.getByText(/ENQUEUE threatview_c2/)).toBeTruthy();
  });

  it("零写路径:postOpsRuling 永不被调(报告面无任何写动作)", async () => {
    renderSection();
    await openDetail();
    fireEvent.click(screen.getByRole("button", { name: "2026-10-18-blocklist-de-legit.md" }));
    await screen.findByText(/# 判例:blocklist-de-legit/);
    expect(vi.mocked(postOpsRuling)).not.toHaveBeenCalled();
  });
});
