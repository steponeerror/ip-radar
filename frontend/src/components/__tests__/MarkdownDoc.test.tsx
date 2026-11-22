import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { renderWithI18n } from "../../test/i18nTestUtils";
import { MarkdownDoc } from "../MarkdownDoc";

// MarkdownDoc(#420):轮报告/档案报告的受控 markdown 渲染件——纯 React 节点输出,
// 零 innerHTML(天然免疫注入);子集=报告面实有形状(标题/表格/列表/围栏代码/加粗/
// 行内 code),不做链接(报告面无 [x](y) 形,YAGNI)。测试从渲染契约出发,不从实现反推。

const md = (text: string, renderInline?: (s: string) => ReactNode) =>
  renderWithI18n(<MarkdownDoc text={text} renderInline={renderInline} />);

describe("MarkdownDoc — 块级", () => {
  it("#/##/### 渲染为 h1/h2/h3 标题", () => {
    md("# 运营轮报告 2026-11-22-1125-health\n\n## 相位\n\n### 小节");
    expect(screen.getByRole("heading", { level: 1, name: /运营轮报告/ })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "相位" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "小节" })).toBeTruthy();
  });

  it("表格:首行表头 + |---| 分隔 → table/thead/th + tbody 行", () => {
    md(["| 相位 | 状态 | 用时 |", "|---|---|---|", "| PROBE | done | 38.9s |", "| VERIFY | done | 1m06s |"].join("\n"));
    const table = screen.getByRole("table");
    expect(screen.getByRole("columnheader", { name: "相位" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "用时" })).toBeTruthy();
    expect(screen.getAllByRole("cell", { name: "done" }).length).toBe(2);
    expect(table.textContent).toContain("1m06s");
  });

  it("无序列表:- 与 * 均渲染;两空格缩进=二层嵌套(发现轮报告「  - 子项」形)", () => {
    md(["- 入队:enqueued=2", "- issue 出口", "  - skip:faux_zero_emit", "* 星号项"].join("\n"));
    const lists = screen.getAllByRole("list");
    expect(lists.length).toBe(2); // 外层 + 嵌套各一
    const outer = lists.find((l) => l.closest("li") === null);
    expect(outer?.querySelectorAll(":scope > li").length).toBe(3);
    const nested = lists.find((l) => l.closest("li") !== null);
    expect(nested?.textContent).toContain("skip:faux_zero_emit");
    // 嵌套项挂在外层第二项之下,不在顶层
    const topItems = Array.from(outer?.querySelectorAll(":scope > li") ?? []);
    expect(topItems[1].textContent).toContain("skip:faux_zero_emit");
    expect(topItems.map((li) => li.childNodes.length === 1 ? "" : "nested")).toEqual(["", "nested", ""]);
  });

  it("有序列表:1. 渲染为 ol/li", () => {
    md(["1. 第一步", "2. 第二步"].join("\n"));
    const items = screen.getAllByRole("listitem");
    expect(items.length).toBe(2);
    expect(items[0].textContent).toBe("第一步");
    expect(screen.getByRole("list").tagName).toBe("OL");
  });

  it("连续非空行=一个段落,行断保留(whitespace-pre-line)", () => {
    const { container } = md(["整体判断:与在案判例一致。", "证据充分,无需动作。"].join("\n"));
    const ps = container.querySelectorAll("p");
    expect(ps.length).toBe(1); // 连续非空行合一段落
    expect(ps[0].className).toContain("whitespace-pre-line");
    expect(ps[0].textContent).toBe("整体判断:与在案判例一致。\n证据充分,无需动作。");
  });

  it("围栏代码块:逐字保留(#/|/** 不再解释),pre>code 形", () => {
    const { container } = md(["```json", '{ "round": "# not heading", "t": "| a | b |" }', "**not bold**", "```"].join("\n"));
    const pre = container.querySelector("pre");
    expect(pre).toBeTruthy();
    expect(pre?.querySelector("code")).toBeTruthy();
    expect(pre?.textContent).toContain("| a | b |");
    expect(pre?.textContent).toContain("**not bold**");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("strong")).toBeNull();
  });
});

describe("MarkdownDoc — 行内", () => {
  it("**bold** → strong;`code` → code", () => {
    md("**结论:全绿,无需动作。** 幸存信号 0,用 `gates.json` 核对");
    expect(screen.getByRole("strong").textContent).toBe("结论:全绿,无需动作。");
    expect(screen.getByRole("code").textContent).toBe("gates.json");
  });

  it("行内钩子:renderInline 只作用于普通文字 run,不进代码围栏", () => {
    const hook = vi.fn((s: string): ReactNode =>
      s.includes("2026-10-18-blocklist-de-legit.md") ? <button type="button">{s}</button> : s);
    md(["## 注入判例", "", "- 判例 2026-10-18-blocklist-de-legit.md 在场", "", "```", "2026-10-18-blocklist-de-legit.md 在围栏里", "```"].join("\n"), hook);
    // 钩子收到的是普通文字 run(含文件名的整段),返回节点原样渲染
    const btn = screen.getByRole("button", { name: /2026-10-18-blocklist-de-legit\.md/ });
    expect(btn.textContent).toContain("在场");
    // 围栏内文件名未成按钮(围栏内不解释),pre 里逐字在场
    expect(screen.queryAllByRole("button").length).toBe(1);
    expect(document.querySelector("pre")?.textContent).toContain("2026-10-18-blocklist-de-legit.md 在围栏里");
    // 钩子收到过纯文字 run
    expect(hook).toHaveBeenCalled();
  });
});
