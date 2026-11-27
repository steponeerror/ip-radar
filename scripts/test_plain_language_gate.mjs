/**
 * scripts/test_plain_language_gate.mjs — plain-language-gate 纯函数门测试。
 *
 * 覆盖:.pi/extensions/plain-language-gate.ts 的词表解析与扫描语义
 * (check_plain_language.py 忠实移植)+ 消息门(命中在头部插警示块/放行)。
 * fixture 词表内联,不依赖机器上的全局词表(CI 可跑)。
 *
 * 运行:node --test scripts/test_plain_language_gate.mjs
 * (node ≥22.18 直接 import .ts;本仓 CI/本地 node v22.23.2)
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
	parseLexicon,
	scanText,
	formatWarning,
	extractText,
	gateAssistantMessage,
	loadLexiconFrom,
} from "../.pi/extensions/plain-language-gate.ts";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// fixture 词表:两区 + 注释 + 空行,覆盖解析分支
const FIXTURE_LEXICON_TEXT = `
# fixture:说人话词表(测试用,与全局词表同格式)
[BANNED]
收官
票①
fresh implementer
[EXPLAIN]
挂点
入池
`;

const FIXTURE_LEXICON = parseLexicon(FIXTURE_LEXICON_TEXT);

test("parseLexicon:分区收集,注释/空行剔除", () => {
	assert.deepEqual(FIXTURE_LEXICON, {
		banned: ["收官", "票①", "fresh implementer"],
		explain: ["挂点", "入池"],
	});
});

test("parseLexicon:空文本 = 空词表(读得到但没有词 = 静默放行)", () => {
	assert.deepEqual(parseLexicon(""), { banned: [], explain: [] });
});

test("BANNED 词子串命中即红", () => {
	const hits = scanText("这批活已经全部收官了。", FIXTURE_LEXICON);
	assert.equal(hits.length, 1);
	assert.equal(hits[0].kind, "BANNED");
	assert.equal(hits[0].term, "收官");
	assert.equal(hits[0].line, 1);
});

test("BANNED 多行多命中分别计数,行号为豁免后序号", () => {
	const text = "第一行正常。\n第二行提到票①。\n> 引用:票① 不算\n第三行 fresh implementer 上岗。";
	const hits = scanText(text, FIXTURE_LEXICON);
	// 票① @豁免后第2行;fresh implementer @豁免后第3行(引用行被剥,序号顺延)
	assert.deepEqual(
		hits.map((h) => [h.kind, h.term, h.line]),
		[
			["BANNED", "票①", 2],
			["BANNED", "fresh implementer", 3],
		],
	);
});

test("EXPLAIN 词命中且同行带解释提示词 → 放行", () => {
	const hints = [
		"挂点,即文档里标注必须真实存在的文件",
		"挂点就是主仓里被机检的文件",
		"挂点指 STANDARD.md 里的条目",
		"挂点,意思是必须真实存在的文件",
		"挂点相当于一份白名单",
		"挂点,换句话说就是必检文件",
		"挂点要用大白话解释",
		"挂点——必检文件列表",
	];
	for (const line of hints) {
		assert.deepEqual(scanText(line, FIXTURE_LEXICON), [], `应放行: ${line}`);
	}
});

test("EXPLAIN 词裸奔(无解释提示词)→ 红", () => {
	const hits = scanText("把这个词加进挂点列表。", FIXTURE_LEXICON);
	assert.deepEqual(
		hits.map((h) => [h.kind, h.term]),
		[["EXPLAIN-bare", "挂点"]],
	);
});

test("引用行(>)与标题行(#)豁免,含前导空白", () => {
	assert.deepEqual(scanText("> 引用前文:收官、票①", FIXTURE_LEXICON), []);
	assert.deepEqual(scanText("## 标题里的挂点", FIXTURE_LEXICON), []);
	assert.deepEqual(scanText("   > 带缩进的引用:入池", FIXTURE_LEXICON), []);
});

test("extractText:只取 text 块,块间换行", () => {
	const content = [
		{ type: "thinking", thinking: "收官(思考块不扫)" },
		{ type: "text", text: "第一段含票①" },
		{ type: "image", source: {} },
		{ type: "text", text: "第二段正常" },
	];
	assert.equal(extractText(content), "第一段含票①\n第二段正常");
});

test("gateAssistantMessage:BANNED 命中 → 头部插入警示块,原内容不动", () => {
	const original = [{ type: "text", text: "这批活收官了。" }];
	const gated = gateAssistantMessage({ role: "assistant", content: original }, FIXTURE_LEXICON);
	assert.ok(gated);
	assert.equal(gated.role, "assistant");
	assert.equal(gated.content.length, 2); // 警示块 + 原块
	assert.deepEqual(gated.content[1], original[0]); // 原块不改且仍在末尾(工作流捕获取末段)
	const warning = gated.content[0];
	assert.equal(warning.type, "text");
	assert.ok(warning.text.startsWith("[plain-language-gate] "), warning.text);
	assert.ok(warning.text.includes("收官"), "警示列命中词");
	assert.deepEqual(original, [{ type: "text", text: "这批活收官了。" }]); // 原消息对象不被改
});

test("gateAssistantMessage:EXPLAIN 裸奔也警示,禁词/解释词分列", () => {
	const gated = gateAssistantMessage(
		{ role: "assistant", content: [{ type: "text", text: "加进挂点,然后收官。" }] },
		FIXTURE_LEXICON,
	);
	assert.ok(gated);
	const warning = gated.content[0].text;
	assert.ok(warning.includes("禁词:「收官」"), warning);
	assert.ok(warning.includes("解释的词:「挂点」"), warning);
});

test("gateAssistantMessage:干净文本 → undefined(放行)", () => {
	assert.equal(
		gateAssistantMessage({ role: "assistant", content: [{ type: "text", text: "这批活已经全部做完了。" }] }, FIXTURE_LEXICON),
		undefined,
	);
});

test("gateAssistantMessage:非 assistant / 非数组 content / 空文本 → undefined", () => {
	assert.equal(gateAssistantMessage({ role: "user", content: "收官" }, FIXTURE_LEXICON), undefined);
	assert.equal(gateAssistantMessage({ role: "assistant", content: "收官" }, FIXTURE_LEXICON), undefined);
	assert.equal(
		gateAssistantMessage({ role: "assistant", content: [{ type: "toolCall", id: "t", operation: {} }] }, FIXTURE_LEXICON),
		undefined,
	);
});

test("gateAssistantMessage:已含幂等标记 → 不再追加", () => {
	const content = [
		{ type: "text", text: "这批活收官了。" },
		{ type: "text", text: "[plain-language-gate] 说人话检查:……" },
	];
	assert.equal(gateAssistantMessage({ role: "assistant", content }, FIXTURE_LEXICON), undefined);
});

test("gateAssistantMessage:空词表(读得到但没有词)→ 恒放行", () => {
	const empty = { banned: [], explain: [] };
	assert.equal(
		gateAssistantMessage({ role: "assistant", content: [{ type: "text", text: "收官 票① 挂点" }] }, empty),
		undefined,
	);
});

test("formatWarning:去重列词", () => {
	const warning = formatWarning([
		{ kind: "BANNED", term: "收官", line: 1 },
		{ kind: "BANNED", term: "收官", line: 2 },
		{ kind: "EXPLAIN-bare", term: "挂点", line: 1 },
	]);
	assert.ok(warning.startsWith("[plain-language-gate] "));
	assert.equal([...warning.matchAll(/收官/g)].length, 1, "禁词只列一次");
	assert.ok(warning.includes("挂点"));
});

// 评审 P2-1:行切分/空白集与 python splitlines()/lstrip() 对齐的边界
// (评审 P2-3:补 parseLexicon 的 CRLF 词表解析路径断言)
test("CRLF 与孤立 CR 文本照常逐行扫(词表与文本两路)", () => {
	const lex = { banned: ["前沿"], explain: [] };
	const hits = scanText("第一行\r\n第二行 前沿\r第三行", lex);
	assert.equal(hits.length, 1);
	assert.equal(hits[0].term, "前沿");
	const crlfLex = parseLexicon("[BANNED]\r\n前沿\r\n");
	assert.deepEqual(crlfLex, lex, "CRLF 词表行解析不残留 \\r");
});
test("NBSP 前缀的引用行同样豁免(python lstrip 含 \\xa0)", () => {
	const lex = { banned: ["前沿"], explain: [] };
	assert.equal(scanText("\u00A0> 引用里的 前沿", lex).length, 0);
	assert.equal(scanText("\u2028# 标题里的 前沿", lex).length, 0);
});

// #511:词表缺失从「静默放行」改「出声放行」——回退行为保留,但 stderr 必须点名。
// 全局 LEXICON_PATH 在测试里不可指(homedir 真实路径,存在与否随机器),
// 走导出的 loadLexiconFrom 用可控路径验同一语义。
test("词表路径不存在 → 放行(null)且 stderr 有一行提示;词表可读时不吵", () => {
	const orig = process.stderr.write;
	const chunks = [];
	process.stderr.write = (chunk) => { chunks.push(String(chunk)); return true; };
	const dir = mkdtempSync(join(tmpdir(), "plg-lex-"));
	try {
		const missing = "/nonexistent/ipradar-plg-test/plain_lexicon.txt";
		assert.equal(loadLexiconFrom(missing), null, "缺失 → null = 放行,消息不被拦");
		const line = chunks.join("");
		assert.ok(line.includes("说人话词表缺失或不可读,本次不检查"), `stderr 要有这行提示: ${line}`);
		assert.ok(line.includes(missing), `提示要带路径: ${line}`);
		assert.equal(chunks.length, 1, "提示恰好一行");
		// 可读词表 → 正常解析且零提示(防「永远出声」式的懒变异);fixture 词
		// 刻意避开全局禁词表里的词,防提交门(pre-commit 同一套词表)拦新增行
		const lexPath = join(dir, "plain_lexicon.txt");
		writeFileSync(lexPath, "[BANNED]\n紫电清霜\n", "utf-8");
		chunks.length = 0;
		assert.deepEqual(loadLexiconFrom(lexPath), { banned: ["紫电清霜"], explain: [] });
		assert.equal(chunks.join(""), "", "词表可读 → 无 stderr 提示");
	} finally {
		process.stderr.write = orig;
		rmSync(dir, { recursive: true, force: true });
	}
});
