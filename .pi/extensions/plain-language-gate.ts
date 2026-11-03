/**
 * plain-language-gate — 助手消息发出前的「说人话」扫描挂钩。
 *
 * 为什么存在:用户多次纠正 agent 回复里的自造压缩词;全局扫描器
 * ~/.pi/agent/scripts/check_plain_language.py 只靠 agent 记得跑、会漏
 * (2026-11-03 诊断结论:提醒拗不过语料且无检查门)。本扩展把同一套
 * 词表语义移植成 pi 扩展的自动挂钩,不依赖记忆。
 *
 * 拦截点:message_end + role==assistant,返回 { message } 在消息尾部
 * 追加一个简短警示块(列命中词,不改原内容)。实证依据(1.5.0 源码):
 * dist/core/agent-session.js 的 _handleAgentEvent 对每种模式统一执行
 *   await this._emitExtensionEvent(event);   // 扩展先行,message_end
 *                                            // 的 replacement 在此原
 *                                            // 地改写同一个 message 对象
 *   this._emit(event);                       // 之后才通知公开监听者
 *   this.sessionManager.appendMessage(...);  // 之后才落盘
 * 即替换发生在消息送达客户端(JSON/print/RPC/TUI)之前,headless 下成立。
 *
 * 词表语义 = check_plain_language.py 忠实移植:
 *   [BANNED] 词逐行子串命中即红;
 *   [EXPLAIN] 词命中但同行没有解释提示词(即|就是|指|意思是|相当于|
 *             换句话说|大白话|——)才红;
 *   以 > 或 # 开头的行(去前导空白后)豁免——引证据不算造词。
 * 词表每次从全局路径现读(热更新);文件缺失/不可读 → 静默放行。
 *
 * 边界:只警示、不拦工具调用、不改词表;所有逻辑 try/catch 包死,
 * 扩展任何异常都不得弄崩会话(pi 侧对 handler 异常也只是记日志,
 * 这里再兜一层)。激活:本文件位于仓内 .pi/extensions/,项目被信任
 * 即自动加载;全局激活(所有项目)= 人工拷贝/链接到
 * ~/.pi/agent/extensions/,本任务不做。
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const LEXICON_PATH = join(homedir(), ".pi", "agent", "scripts", "plain_lexicon.txt");

// check_plain_language.py 的 EXPLAIN_HINT 同款(顺序无关,纯子串/分支匹配)
const EXPLAIN_HINT = /即|就是|指|意思是|相当于|换句话说|大白话|——/;

// 幂等标记:警示块前缀;再次见到含此标记的文本直接放行(防自我重复追加以
// 及模型复述警示块时的重复计数)
const MARKER = "[plain-language-gate]";

export interface Lexicon {
	banned: string[];
	explain: string[];
}

export interface ScanHit {
	kind: "BANNED" | "EXPLAIN-bare";
	term: string;
	/** 命中行号(1 起)= 豁免后剩余行中的序号,与 python 版 enumerate(lines,1) 同语义 */
	line: number;
}

/** 移植 check_plain_language.py 的 load_lexicon:分区头切换,空行/`#` 注释行跳过 */
export function parseLexicon(text: string): Lexicon {
	const banned: string[] = [];
	const explain: string[] = [];
	let cur: string[] | null = null;
	for (const raw of text.split("\n")) {
		const s = raw.trim();
		if (s === "[BANNED]") {
			cur = banned;
		} else if (s === "[EXPLAIN]") {
			cur = explain;
		} else if (s && !s.startsWith("#") && cur !== null) {
			cur.push(s);
		}
	}
	return { banned, explain };
}

/** 移植 scan():先剥引用/标题行,再逐词逐行子串匹配;EXPLAIN 裸奔才红
 * 行切分与空白集对齐 python splitlines()/lstrip():CRLF/孤立 CR 也切行,
 * 前导空白含 NBSP/NEL/LS/PS(评审 P2-1,与 check_plain_language.py 对齐) */
export function scanText(text: string, lexicon: Lexicon): ScanHit[] {
	const lines = text.split(/\r\n|\r|\n/).filter((ln) => {
		const stripped = ln.replace(/^[\s\xA0\x85\u2028\u2029]+/, "");
		return !(stripped.startsWith(">") || stripped.startsWith("#"));
	});
	const hits: ScanHit[] = [];
	for (const term of lexicon.banned) {
		for (let i = 0; i < lines.length; i++) {
			if (lines[i].includes(term)) {
				hits.push({ kind: "BANNED", term, line: i + 1 });
			}
		}
	}
	for (const term of lexicon.explain) {
		for (let i = 0; i < lines.length; i++) {
			if (lines[i].includes(term) && !EXPLAIN_HINT.test(lines[i])) {
				hits.push({ kind: "EXPLAIN-bare", term, line: i + 1 });
			}
		}
	}
	return hits;
}

/** 汇总成一句短警示:列去重后的命中词,不列行号(警示块要短) */
export function formatWarning(hits: ScanHit[]): string {
	const banned = [...new Set(hits.filter((h) => h.kind === "BANNED").map((h) => h.term))];
	const bare = [...new Set(hits.filter((h) => h.kind === "EXPLAIN-bare").map((h) => h.term))];
	const parts: string[] = [];
	if (banned.length > 0) parts.push(`禁词:「${banned.join("」「")}」`);
	if (bare.length > 0) parts.push(`需同段配大白话解释的词:「${bare.join("」「")}」`);
	return `${MARKER} 说人话检查:本条回复命中自造压缩词(${parts.join(";")})。下一条回复请改用大白话表述,禁词换说法,解释词同段补一句人话。`;
}

type TextBlock = { type: "text"; text: string };

function isTextBlock(block: unknown): block is TextBlock {
	if (typeof block !== "object" || block === null) return false;
	const b = block as { type?: unknown; text?: unknown };
	return b.type === "text" && typeof b.text === "string";
}

/** 取消息全部 text 块拼成待扫文本(块间换行,保持行结构) */
export function extractText(content: unknown): string {
	if (!Array.isArray(content)) return "";
	return content.filter(isTextBlock).map((b) => b.text).join("\n");
}

/**
 * 对一条 assistant 形状的消息执行门逻辑,命中时返回在头部插入警示 text 块的
 * 新消息对象(同 role,原 content 不动)。放头部不放尾部:2026-11-03 实弹判例,
 * 子代理工作流捕获输出时只取最后一段 text,警示块放尾部会把正文从捕获里顶掉
 * (终审报告因此丢了一次);放头部则正文仍是末块,捕获与 TUI 阅读都不受损。
 * 未命中/无文本/已含幂等标记返回 undefined(= 不替换)。
 */
export function gateAssistantMessage(
	message: { role: string; content: unknown },
	lexicon: Lexicon,
): { role: string; content: unknown[] } | undefined {
	if (message.role !== "assistant") return undefined;
	if (!Array.isArray(message.content)) return undefined;
	const text = extractText(message.content);
	if (!text.trim()) return undefined;
	if (text.includes(MARKER)) return undefined;
	const hits = scanText(text, lexicon);
	if (hits.length === 0) return undefined;
	return {
		...message,
		content: [{ type: "text", text: formatWarning(hits) } satisfies TextBlock, ...message.content],
	};
}

/** 每次现读全局词表(热更新);任何读失败 → null = 静默放行 */
function loadLexiconFresh(): Lexicon | null {
	try {
		return parseLexicon(readFileSync(LEXICON_PATH, "utf-8"));
	} catch {
		return null;
	}
}

export default function plainLanguageGate(pi: ExtensionAPI): void {
	pi.on("message_end", async (event, ctx) => {
		try {
			const lexicon = loadLexiconFresh();
			if (!lexicon) return; // 词表缺失/不可读 → 静默放行
			const gated = gateAssistantMessage(event.message, lexicon);
			if (!gated) return;
			if (ctx.hasUI) {
				try {
					ctx.ui.notify(
						`plain-language-gate:助手回复命中自造压缩词,已在消息尾部加警示(${gated.content.length} 块)`,
						"warning",
					);
				} catch {
					// UI 通知失败不影响门本身
				}
			}
			return { message: gated };
		} catch {
			return; // 扩展任何异常都不得弄崩会话
		}
	});
}
