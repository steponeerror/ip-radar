import type { ReactNode } from "react";

// MarkdownDoc(#420):轮报告/档案报告(packages/*.md)的受控 markdown 渲染件。
// Why:档案详情此前用 <pre> 逐字展示,# 与 |---| 原样可见(用户判例:可读性太差)。
// 纪律:纯 React 节点输出,严禁 innerHTML/dangerouslySetInnerHTML(报告文含上游
// 数据,受控渲染=天然免疫注入);零新依赖;子集=报告面实有形状——块级 #/##/###、
// 表格(首行表头+|---| 分隔)、无序/有序列表(两空格缩进=二层嵌套,发现轮报告
// 「  - 子项」形)、围栏代码(逐字,不解释)、连续非空行=段落(行断保留);
// 行内 **bold** 与 `code`。不做 [x](y) 链接:报告面无此形,YAGNI——真要链出时
// 走 renderInline 钩子(调用方自定义交互,不进本组件)。
// renderInline:对普通文字 run(围栏代码内不调)应用,供调用方挂交互——
// OpsPackagesSection 用它沿用 PRECEDENT_REF_RE 判例文件名→可点按钮(票 #156 行为)。

type Block =
  | { kind: "code"; lang: string; lines: string[] }
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "list"; ordered: boolean; items: { nested: boolean; text: string }[] }
  | { kind: "para"; lines: string[] };

const HEADING_RE = /^(#{1,3})\s+(.*)$/;
const UL_RE = /^(\s*)[-*]\s+(.*)$/;
const OL_RE = /^(\s*)\d+[.]\s+(.*)$/;
// 表格分隔行:仅 |、:、-、空白组成且含 - 与 |(报告面 |---|---| 形)
const TABLE_SEP_RE = /^[|:\s-]+$/;

const isTableSep = (line: string) => TABLE_SEP_RE.test(line) && line.includes("-") && line.includes("|");

const splitRow = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

// 行内切分:**bold** 与 `code` 两形(报告面实有;链接不做见头注)
const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function parseInline(text: string, renderInline?: (s: string) => ReactNode): ReactNode[] {
  const out: ReactNode[] = [];
  const parts = text.split(INLINE_RE);
  parts.forEach((p, i) => {
    if (!p) return;
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) {
      out.push(<strong key={i} className="font-semibold text-zinc-100">{p.slice(2, -2)}</strong>);
    } else if (p.startsWith("`") && p.endsWith("`") && p.length > 2) {
      out.push(<code key={i} className="rounded bg-zinc-900 px-1 py-0.5 font-mono text-emerald-400">{p.slice(1, -1)}</code>);
    } else {
      out.push(<span key={i}>{renderInline ? renderInline(p) : p}</span>);
    }
  });
  return out;
}

function parseBlocks(text: string): Block[] {
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let para: string[] | null = null;
  let list: Extract<Block, { kind: "list" }> | null = null;
  const flushPara = () => { if (para && para.length) { blocks.push({ kind: "para", lines: para }); } para = null; };
  const flushList = () => { if (list && list.items.length) blocks.push(list); list = null; };
  const flushAll = () => { flushPara(); flushList(); };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^```/.exec(line.trim());
    if (fence) {
      flushAll();
      const lang = line.trim().slice(3).trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { body.push(lines[i]); i++; }
      blocks.push({ kind: "code", lang, lines: body });
      continue;
    }
    if (!line.trim()) { flushAll(); continue; }
    const h = HEADING_RE.exec(line);
    if (h) { flushAll(); blocks.push({ kind: "heading", level: h[1].length as 1 | 2 | 3, text: h[2].trim() }); continue; }
    // 表格:当前行含 | 且下一行是分隔行
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushAll();
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(splitRow(lines[i])); i++; }
      i--;
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const ul = UL_RE.exec(line);
    const ol = ul ? null : OL_RE.exec(line);
    if (ul || ol) {
      flushPara();
      const ordered = !!ol;
      const nested = (ul ?? ol)![1].length > 0; // 有缩进=二层(「  - 子项」)
      const itemText = (ul ?? ol)![2];
      if (!list || list.ordered !== ordered) { flushList(); list = { kind: "list", ordered, items: [] }; }
      list.items.push({ nested, text: itemText });
      continue;
    }
    flushList();
    (para ??= []).push(line.trim());
  }
  flushAll();
  return blocks;
}

function renderList(items: { nested: boolean; text: string }[], ordered: boolean, renderInline?: (s: string) => ReactNode): ReactNode {
  // 嵌套项(两空格缩进)挂到最近一个顶层项之下:一层缩进两层嵌套,报告面深度闭集
  const top: { text: string; children: string[] }[] = [];
  for (const it of items) {
    if (it.nested && top.length) top[top.length - 1].children.push(it.text);
    else top.push({ text: it.text, children: [] });
  }
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag className={ordered ? "list-decimal pl-5 space-y-0.5" : "list-disc pl-5 space-y-0.5"}>
      {top.map((it, idx) => (
        <li key={idx}>
          {parseInline(it.text, renderInline)}
          {it.children.length > 0 && (
            <ul className="mt-0.5 list-disc pl-4">{it.children.map((c, j) => <li key={j}>{parseInline(c, renderInline)}</li>)}</ul>
          )}
        </li>
      ))}
    </Tag>
  );
}

export function MarkdownDoc({ text, renderInline }: {
  text: string;
  renderInline?: (text: string) => ReactNode;
}) {
  const blocks = parseBlocks(text);
  return (
    <div className="max-h-[28rem] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300 space-y-2">
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "code":
            return (
              <pre key={i} className="overflow-x-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed whitespace-pre text-zinc-300">
                <code>{b.lines.join("\n")}</code>
              </pre>
            );
          case "heading": {
            const cls = b.level === 1 ? "text-sm font-semibold text-zinc-100"
              : b.level === 2 ? "text-sm font-semibold text-zinc-200"
                : "text-xs font-semibold text-zinc-300";
            const Tag = (`h${b.level}` as "h1" | "h2" | "h3");
            return <Tag key={i} className={cls}>{parseInline(b.text, renderInline)}</Tag>;
          }
          case "table":
            return (
              <table key={i} className="w-full border-collapse text-left text-xs">
                <thead className="bg-zinc-900 font-mono text-[11px] text-zinc-500">
                  <tr>{b.header.map((c, j) => <th key={j} scope="col" className="border border-zinc-800 px-2 py-1">{parseInline(c, renderInline)}</th>)}</tr>
                </thead>
                <tbody className="text-zinc-400">
                  {b.rows.map((row, r) => (
                    <tr key={r}>{row.map((c, j) => <td key={j} className="border border-zinc-800 px-2 py-1">{parseInline(c, renderInline)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            );
          case "list":
            return <div key={i}>{renderList(b.items, b.ordered, renderInline)}</div>;
          case "para":
            return <p key={i} className="whitespace-pre-line">{b.lines.map((l, j) => <span key={j}>{parseInline(l, renderInline)}{j < b.lines.length - 1 ? "\n" : null}</span>)}</p>;
        }
      })}
    </div>
  );
}
