import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import OpsPackagesSection from "../OpsPackagesSection";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { listOpsPackages, readOpsPackage, readOpsPrecedent, postOpsRuling } from "../../api";

// P4 裁决包区(票 #136):列表→详情(建议/证据 call_id+field+value/trace/
// 判例引用可点开全文)→人裁三动作(同意/否决/修正)。建议行只从包文本解析
// (逐字纪律:suggestion = 包内原文,不允许自由输入发明建议);全部建议恒标
// 「仅立项」(裁⑦)。包/判例正文形状 = ops/agent/prompts 输出契约(固定节)
// ——此处 fixture 取自该契约,不从实现反推。
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
const SUGGESTION_ENQUEUE =
  "ENQUEUE threatview_c2 — CPS 镜像 cobaltstrike_ips 排他 57.0%(171/300),建议单独立项直连";
const SUGGESTION_HUMAN = "人裁 语义矩阵槽位冲突(example),证据不足";

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
  `- ${SUGGESTION_ENQUEUE}`,
  `- ${SUGGESTION_HUMAN}`,
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
  it("lists packages (newest first metadata); empty state without a round", async () => {
    vi.mocked(listOpsPackages).mockResolvedValueOnce([]);
    renderSection();
    expect(await screen.findByText(/No ruling packages yet/i)).toBeTruthy();
    expect(listOpsPackages).toHaveBeenCalledTimes(1);
  });

  it("detail shows the package verbatim (evidence call_id+field=value / trace) with precedent refs clickable", async () => {
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

// ── 票 #149:裁决包列表行元数据(大小+相对时间)+ 节头计数 ──

describe("OpsPackagesSection — 列表行元数据与计数(票 #149)", () => {
  it("行元数据:大小 KB + 相对时间(title=ISO 原文,证据不灭失);节头计数 N 个", async () => {
    renderSection(); // beforeEach 夹具:1 包,4096B,modified=2026-10-20T10:30:00+00:00
    expect(await screen.findByRole("heading", { name: "Ruling packages (1)" })).toBeTruthy();
    expect(screen.getByText("4.0 KB")).toBeTruthy();
    const timed = screen.getByTitle("2026-10-20T10:30:00+00:00");
    expect(timed.textContent ?? "").toMatch(/ago$|^just now/);
  });

  it("空列表:计数如实显 (0)(视觉门 2026-10-21 微5)+ 基准「暂无」式空态入容器(不留纯空白)", async () => {
    vi.mocked(listOpsPackages).mockResolvedValueOnce([]);
    renderSection();
    await screen.findByText(/No ruling packages yet/i);
    expect(screen.getByRole("heading", { name: "Ruling packages (0)" })).toBeTruthy();
  });

  it("详情态节头不带计数(计数属列表面;详情无行集可数)", async () => {
    renderSection();
    await openDetail();
    expect(screen.getByRole("heading", { name: "Ruling packages" })).toBeTruthy();
  });
});

describe("OpsPackagesSection — 裁⑦ 仅立项 + 人裁三动作", () => {
  it("every parsed suggestion row carries the proposal-only badge", async () => {
    renderSection();
    await openDetail();
    const badges = screen.getAllByText(/proposal only/i);
    expect(badges.length).toBe(2);
  });

  it("agree posts {package, suggestion verbatim, verdict:'agreed'}; result names the created precedent", async () => {
    vi.mocked(postOpsRuling).mockResolvedValue({
      created: true, precedent: "2026-10-20-ruling-abc123def0.md",
      superseded: null, queue_appended: true,
    });
    renderSection();
    await openDetail();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTION_ENQUEUE.slice(0, 20)) }));
    fireEvent.click(screen.getByRole("button", { name: "Agree" }));
    await waitFor(() => expect(vi.mocked(postOpsRuling)).toHaveBeenCalledWith(
      PKG_NAME, SUGGESTION_ENQUEUE, "agreed", undefined,
    ));
    expect(await screen.findByText(/2026-10-20-ruling-abc123def0\.md/)).toBeTruthy();
    expect(screen.getByText(/approved-for-integration/i)).toBeTruthy();
  });

  it("overrule posts verdict 'overruled'", async () => {
    vi.mocked(postOpsRuling).mockResolvedValue({
      created: true, precedent: "2026-10-20-ruling-1111111111.md",
      superseded: null, queue_appended: false,
    });
    renderSection();
    await openDetail();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTION_HUMAN.slice(0, 6)) }));
    fireEvent.click(screen.getByRole("button", { name: "Overrule" }));
    await waitFor(() => expect(vi.mocked(postOpsRuling)).toHaveBeenCalledWith(
      PKG_NAME, SUGGESTION_HUMAN, "overruled", undefined,
    ));
  });

  it("amend requires verbatim amendment text and posts it; superseded + idempotent results rendered", async () => {
    vi.mocked(postOpsRuling).mockResolvedValueOnce({
      created: true, precedent: "2026-10-20-ruling-aaaaaaaaaa.md",
      superseded: "2026-10-18-ruling-bbbbbbbbbb.md", queue_appended: false,
    }).mockResolvedValueOnce({
      created: false, precedent: "2026-10-20-ruling-aaaaaaaaaa.md",
      superseded: null, queue_appended: false,
    });
    renderSection();
    await openDetail();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTION_ENQUEUE.slice(0, 20)) }));
    fireEvent.click(screen.getByRole("button", { name: "Amend" }));
    // 空修正案不可提交(后端 422;前端先拦)
    expect(screen.getByRole("button", { name: "Submit amended ruling" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: /amendment/i }), {
      target: { value: "修正案:排他门按头部/尾部分档,逐字留痕" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit amended ruling" }));
    await waitFor(() => expect(vi.mocked(postOpsRuling)).toHaveBeenCalledWith(
      PKG_NAME, SUGGESTION_ENQUEUE, "amended", "修正案:排他门按头部/尾部分档,逐字留痕",
    ));
    expect(await screen.findByText(/Superseded earlier entry: 2026-10-18-ruling-bbbbbbbbbb\.md/)).toBeTruthy();
    // 重复同裁:created=false → 幂等文案
    fireEvent.click(screen.getByRole("button", { name: "Agree" }));
    await waitFor(() => expect(screen.getByText(/already on record/i)).toBeTruthy());
  });

  it("ruling failure shows the readable envelope text, not the raw code", async () => {
    vi.mocked(postOpsRuling).mockRejectedValue(Object.assign(new Error("裁决包不存在: x.md"), {
      status: 404, code: "not_found",
    }));
    renderSection();
    await openDetail();
    fireEvent.click(screen.getByRole("button", { name: new RegExp(SUGGESTION_ENQUEUE.slice(0, 20)) }));
    fireEvent.click(screen.getByRole("button", { name: "Agree" }));
    await waitFor(() => expect(screen.getByText(/does not exist/i)).toBeTruthy());
    expect(screen.queryByText(/not_found/)).toBeNull();
  });

  it("no selectable suggestion → three actions disabled (verbatim discipline, no free-text invention)", async () => {
    vi.mocked(readOpsPackage).mockResolvedValueOnce("# 裁决包\n\n## 摘要\n\n无建议行。\n");
    renderSection();
    await openDetail();
    expect(screen.getByText(/Select a suggestion/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Agree" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Overrule" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Amend" })).toBeDisabled();
  });
});
