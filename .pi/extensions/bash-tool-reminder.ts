/**
 * bash-tool-reminder — bash 工具调用的「抓网页 / 装包」软提醒挂钩(#305)。
 *
 * 为什么存在:工具选择被主人纠正 4 次(该用 web-read 却用 curl 抓网页、
 * 擅自装包;2026-11-03 retro,docs/notes/retro-claude-mem-patterns-2026-11-03.md
 * 第 10 条)。同簇先例 codegraph-gate(全局,~/.pi/agent/extensions/
 * codegraph-gate.ts.disabled)立后该类零新增纠正,本扩展照抄「机检提示」
 * 模式;但 #305 裁决为软提示:命中不 block,命令照常执行,只提醒。
 *
 * 命中面(命令字符串小写归一后做词边界匹配,纯文本尽力、非沙箱判定):
 *   1. curl/wget + 公网 http(s) URL → 提醒「读网页优先用 web-read;下载
 *      数据文件等 web-read 干不了的活继续即可」。内网白名单不算:
 *      localhost(.localhost)/127.x/::1/RFC1918(10./172.16-31./192.168.)/
 *      169.254. 链路本地/无点单标签主机(docker compose 服务名判例:
 *      http://api:8000、http://ipradar:8000)。
 *   2. 系统装包 → 提醒「禁擅自装包,先问」:
 *      apt(-get) install;npm (i|install|add) -g|--global;pip install
 *      --user,或无 venv 信号的 pip/python -m pip install。venv 信号 =
 *      命令文本里的 .venv/、venv/bin/、source …/activate、VIRTUAL_ENV=
 *      (shell 已激活态从命令文本探不到,尽力而为;软提示误报无害)。
 *
 * 提示投递(两条腿,各自独立 try/catch,互不依赖):
 *   - tool_call:ctx.hasUI 时 ctx.ui.notify 即时给人看(headless 的
 *     JSON/print 模式 hasUI=false,自动跳过);
 *   - tool_result:在结果 content 头部插一个提醒 text 块给模型看——这是
 *     主通道,子代理/headless 下模型也能收到。放头部不放尾部:子代理工作流
 *     捕获输出时只取末段 text,放尾部会把命令原始输出从捕获里顶掉
 *     (plain-language-gate 2026-11-03 实弹判例);原 content 块原样保留,
 *     证据不灭失。
 *
 * 幂等/兜底:结果已含标记不再叠加;任何异常静默吞(扩展挂了不能弄崩
 * 会话,pi 侧对 handler 异常也只记日志,这里再兜一层);无会话级状态,
 * 纯函数匹配,同命令重算同答案。激活:本文件在仓内 .pi/extensions/,
 * 项目被信任即自动加载。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MARKER = "[bash-tool-reminder]";

// ---- 纯匹配逻辑(全部可导出单测;词边界防 mycurl/aptx 类前缀误命中) ----

const FETCHER_RE = /\b(?:curl|wget)\b/;
const URL_RE = /https?:\/\/[^\s'"`<>]+/g;
const APT_INSTALL_RE = /\bapt(?:-get)?\s+install\b/;
const NPM_TOKEN_RE = /\bnpm\b/;
const NPM_INSTALL_WORD_RE = /\b(?:install|i|add)\b/;
const GLOBAL_FLAG_RE = /(?:^|\s)(?:-g|--global)\b/;
const PIP_INSTALL_RE = /\bpip3?\s+install\b/;
const PY_PIP_INSTALL_RE = /\bpython3?\s+-m\s+pip3?\s+install\b/;
const USER_FLAG_RE = /(?:^|\s)--user\b/;
/** venv 信号:命令文本里可见的「这次 pip 在虚拟环境里」线索(大小写敏感,
 *  VIRTUAL_ENV= 与路径段本身就是字面量;匹配用原始命令,不吃小写归一) */
const VENV_HINT_RE = /\.venv\/|venv\/bin\/|(?:^|\s)source\s+\S*\/activate\b|VIRTUAL_ENV=/;

export type BashReminderKind = "web-fetch" | "package-install";

export interface BashReminderHit {
	kind: BashReminderKind;
	/** 命中证据:外链 URL 或装包子命令片段(供提示定位,不截断原命令) */
	evidence: string;
}

const MESSAGES: Record<BashReminderKind, string> = {
	"web-fetch": "读网页优先用 web-read 工具;若是下载数据文件等 web-read 干不了的活,继续即可",
	"package-install": "禁擅自装包,先问主人;若本次已装包,回复时主动说明",
};

/** 从 URL 里剥出主机名(去协议/userinfo/端口;IPv6 字面量去方括号),小写 */
function hostOfUrl(url: string): string | null {
	const rest = url.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
	const authority = rest.split(/[/?#]/, 1)[0];
	if (!authority) return null;
	const noUser = authority.includes("@") ? authority.slice(authority.lastIndexOf("@") + 1) : authority;
	if (noUser.startsWith("[")) {
		const end = noUser.indexOf("]");
		return end === -1 ? null : noUser.slice(1, end).toLowerCase();
	}
	const host = noUser.split(":", 1)[0].toLowerCase();
	return host || null;
}

/** 内网/本机白名单:curl 打这些不算「抓外网网页」(见文件头注释第 1 条) */
export function isInternalHost(host: string): boolean {
	if (host === "localhost" || host.endsWith(".localhost")) return true;
	if (host.includes(":")) {
		// IPv6 字面量:仅环回/未指定/链路本地算内网
		return host === "::1" || host === "::" || host.startsWith("fe80:");
	}
	if (host.startsWith("127.")) {
		// 点分缩写环回(127.1 = 127.0.0.1):进不了四段正则但绝不公网,
		// 须在四段判定前短路(评审 R1-P2-2),否则被当外链误提醒
		return true;
	}
	const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
	if (v4) {
		// v4[0] 是整串匹配,数字只取捕获组,否则首元变 NaN 全白名单失效
		const parts = v4.slice(1).map(Number);
		if (parts.some((n) => n > 255)) return false; // 不是合法 IPv4,不当内网处理
		const [a, b] = parts;
		return (
			a === 127 || // 环回
			a === 10 || // RFC1918
			(a === 192 && b === 168) || // RFC1918
			(a === 172 && b >= 16 && b <= 31) || // RFC1918
			(a === 169 && b === 254) // 链路本地
		);
	}
	// 无点单标签主机:docker compose 服务名 / /etc/hosts 内网别名
	return !host.includes(".");
}

/** 装包类命中(apt / npm 全局 / pip);raw = 原命令(venv 信号用),lower = 小写归一 */
function matchPackageInstalls(raw: string, lower: string): BashReminderHit[] {
	const hits: BashReminderHit[] = [];
	const apt = APT_INSTALL_RE.exec(lower);
	if (apt) hits.push({ kind: "package-install", evidence: apt[0] });
	if (NPM_TOKEN_RE.test(lower) && NPM_INSTALL_WORD_RE.test(lower) && GLOBAL_FLAG_RE.test(lower)) {
		const word = NPM_INSTALL_WORD_RE.exec(lower)?.[0] ?? "install";
		const flag = GLOBAL_FLAG_RE.exec(lower)?.[0]?.trim() ?? "-g";
		hits.push({ kind: "package-install", evidence: `npm ${word} ${flag}` });
	}
	const pip = PIP_INSTALL_RE.exec(lower) || PY_PIP_INSTALL_RE.exec(lower);
	if (pip) {
		// --user 装进用户 site-packages,恒提醒;普通装包仅当无 venv 信号才提醒
		if (USER_FLAG_RE.test(lower) || !VENV_HINT_RE.test(raw)) {
			hits.push({ kind: "package-install", evidence: pip[0] });
		}
	}
	return hits;
}

/** 纯函数:命令 → 去重后的提醒命中列表(空 = 零提示) */
export function matchBashReminders(command: string): BashReminderHit[] {
	if (typeof command !== "string" || command.length === 0) return [];
	const lower = command.toLowerCase();
	const hits: BashReminderHit[] = [];
	if (FETCHER_RE.test(lower)) {
		for (const m of lower.matchAll(URL_RE)) {
			const host = hostOfUrl(m[0]);
			if (host !== null && !isInternalHost(host)) {
				hits.push({ kind: "web-fetch", evidence: m[0] });
			}
		}
	}
	hits.push(...matchPackageInstalls(command, lower));
	const seen = new Set<string>();
	return hits.filter((h) => {
		const key = `${h.kind}|${h.evidence}`;
		if (seen.has(key)) return false;
		seen.add(key);
		return true;
	});
}

/** 汇总命中成提醒文本块(带 MARKER 前缀,一行一命中) */
export function buildReminderBlock(hits: BashReminderHit[]): string {
	const lines = hits.map((h) => `- ${MESSAGES[h.kind]}(命中:${h.evidence})`);
	return `${MARKER} 软提醒(不拦执行,按需采纳):\n${lines.join("\n")}`;
}

type TextBlock = { type: "text"; text: string };

function isTextBlock(block: unknown): block is TextBlock {
	if (typeof block !== "object" || block === null) return false;
	const b = block as { type?: unknown; text?: unknown };
	return b.type === "text" && typeof b.text === "string";
}

/**
 * 纯函数:命中时返回在 content 头部插提醒块的新数组(原块原样保留引用,
 * 证据不灭失);未命中 / content 形状不对 / 已含幂等标记 → undefined。
 */
export function remindBashResult(command: string, content: unknown): TextBlock[] | undefined {
	const hits = matchBashReminders(command);
	if (hits.length === 0) return undefined;
	if (!Array.isArray(content)) return undefined;
	if (content.some((b) => isTextBlock(b) && b.text.includes(MARKER))) return undefined;
	return [{ type: "text", text: buildReminderBlock(hits) }, ...content];
}

/** notify 按类拼句(R1-P2-1):只装包命中不带 web-read 句,只抓网页不带装包句 */
const NOTIFY_SENTENCE: Record<BashReminderKind, string> = {
	"web-fetch": "读网页优先 web-read",
	"package-install": "禁擅自装包先问",
};

export function notifyText(hits: BashReminderHit[]): string {
	const kinds = [...new Set(hits.map((h) => h.kind))];
	const tips = kinds.map((k) => NOTIFY_SENTENCE[k]).join(";");
	return `${MARKER} bash 命中软提醒(${kinds.join("+")}):${tips}。详见工具结果头部,命令未被拦。`;
}

function bashCommandOf(input: unknown): string | undefined {
	if (typeof input !== "object" || input === null) return undefined;
	const command = (input as { command?: unknown }).command;
	return typeof command === "string" ? command : undefined;
}

export default function bashToolReminder(pi: ExtensionAPI): void {
	// 腿 1:命中当下给人一条即时通知(headless 无 UI 自动跳过;不拦执行)
	pi.on("tool_call", async (event, ctx) => {
		try {
			if (event.toolName !== "bash") return;
			const command = bashCommandOf(event.input);
			if (command === undefined) return;
			const hits = matchBashReminders(command);
			if (hits.length === 0) return;
			if (ctx.hasUI) {
				try {
					ctx.ui.notify(notifyText(hits), "warning");
				} catch {
					// UI 通知失败不影响命令执行与结果腿
				}
			}
		} catch {
			return; // 扩展任何异常都不得弄崩会话
		}
	});

	// 腿 2(主通道):执行完在结果头部插提醒块给模型看;structuredContent
	// 存在时原样带回(只换 content 会丢它,pi 1.5.0 语义)
	pi.on("tool_result", async (event) => {
		try {
			if (event.toolName !== "bash") return;
			const command = bashCommandOf(event.input);
			if (command === undefined) return;
			const reminded = remindBashResult(command, event.content);
			if (!reminded) return;
			return event.structuredContent !== undefined
				? { content: reminded, structuredContent: event.structuredContent }
				: { content: reminded };
		} catch {
			return; // 同上:静默兜底
		}
	});
}
