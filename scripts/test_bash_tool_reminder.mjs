/**
 * scripts/test_bash_tool_reminder.mjs — bash-tool-reminder 纯函数门测试(#305)。
 *
 * 覆盖:.pi/extensions/bash-tool-reminder.ts 的关键词匹配(curl/wget 外链
 * + 内网白名单 / apt / npm 全局 / pip venv 判别)、变形容错(大小写/引号/
 * 复合命令)与结果块插投(头部插入/原块保留/幂等)。
 *
 * 运行:node --test scripts/test_bash_tool_reminder.mjs
 * (node ≥22.18 直接 import .ts;本仓 CI/本地 node v22.23.2)
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
	isInternalHost,
	matchBashReminders,
	buildReminderBlock,
	remindBashResult,
} from "../.pi/extensions/bash-tool-reminder.ts";

const kinds = (cmd) => matchBashReminders(cmd).map((h) => h.kind);
const evidences = (cmd) => matchBashReminders(cmd).map((h) => h.evidence);

// ---- curl/wget 抓外网 ----

test("curl 抓公网 https → web-fetch,证据=URL", () => {
	const hits = matchBashReminders("curl -sL https://example.com/article -o page.html");
	assert.deepEqual(kinds("curl -sL https://example.com/article -o page.html"), ["web-fetch"]);
	assert.equal(hits[0].evidence, "https://example.com/article");
});

test("wget 抓公网 http → web-fetch", () => {
	assert.deepEqual(kinds("wget -q -O - http://ipinfo.io/8.8.8.8"), ["web-fetch"]);
});

test("管道安装句式(curl 外链 | sh)→ web-fetch", () => {
	assert.deepEqual(kinds("curl -fsSL https://get.docker.com | sh"), ["web-fetch"]);
});

test("复合命令里的 curl 外链照命中(cd && curl)", () => {
	assert.deepEqual(kinds("cd /tmp && curl -s https://api.github.com/repos/x/y > r.json"), ["web-fetch"]);
});

test("同 URL 重复出现只计一次(去重)", () => {
	assert.equal(matchBashReminders("curl https://a.com https://a.com").length, 1);
});

test("多个不同外链 = 多条命中", () => {
	assert.equal(matchBashReminders("curl https://a.com https://b.com").length, 2);
});

test("无 fetcher 只有 URL → 不命中(echo 一个网址不算抓)", () => {
	assert.deepEqual(matchBashReminders('echo "see https://example.com/docs"'), []);
});

test("curl 无 URL(--version 等)→ 不命中", () => {
	assert.deepEqual(matchBashReminders("curl --version"), []);
});

// ---- 内网/localhost 白名单 ----

test("localhost / 127.x / ::1 不算外链", () => {
	assert.deepEqual(matchBashReminders("curl -s http://localhost:8000/api/version"), []);
	assert.deepEqual(matchBashReminders("curl -s http://127.0.0.1:8000/api/version"), []);
	assert.deepEqual(matchBashReminders("curl -s http://[::1]:8000/api/version"), []);
});

test("RFC1918 与链路本地不算外链", () => {
	assert.deepEqual(matchBashReminders("curl -s http://10.0.0.5:9200/_cluster/health"), []);
	assert.deepEqual(matchBashReminders("curl -s http://192.168.1.10/api"), []);
	assert.deepEqual(matchBashReminders("curl -s http://172.20.0.3/api"), []);
	assert.deepEqual(matchBashReminders("curl -s http://169.254.169.254/latest/meta-data"), []);
});

test("172.16-31 边界:172.15/172.32 是公网要命中,172.16-31 不命中", () => {
	assert.equal(matchBashReminders("curl http://172.15.0.1/").length, 1);
	assert.equal(matchBashReminders("curl http://172.31.255.1/").length, 0);
	assert.equal(matchBashReminders("curl http://172.32.0.1/").length, 1);
});

test("无点单标签主机(compose 服务名判例 http://api:8000)不算外链", () => {
	assert.deepEqual(matchBashReminders("curl -s http://api:8000/health"), []);
	assert.deepEqual(matchBashReminders("curl -s http://ipradar:8000/api/version"), []);
});

test("isInternalHost:*.localhost 域与 IPv6 链路本地算内网,公网 v6 不算", () => {
	assert.equal(isInternalHost("foo.localhost"), true);
	assert.equal(isInternalHost("fe80::1"), true);
	assert.equal(isInternalHost("2001:db8::1"), false);
	assert.equal(isInternalHost("example.com"), false);
});

// ---- 装包类 ----

test("apt install / apt-get install / sudo 前缀 → package-install", () => {
	assert.deepEqual(kinds("apt install jq"), ["package-install"]);
	assert.deepEqual(kinds("sudo apt-get install -y ripgrep"), ["package-install"]);
	assert.equal(evidences("apt-get install -y jq")[0], "apt-get install");
});

test("apt update / apt-cache 不命中", () => {
	assert.deepEqual(matchBashReminders("sudo apt update"), []);
	assert.deepEqual(matchBashReminders("apt-cache search ripgrep"), []);
});

test("npm install -g / npm i -g / --global / 复合命令 → package-install", () => {
	assert.deepEqual(kinds("npm install -g typescript"), ["package-install"]);
	assert.deepEqual(kinds("npm i -g @anthropic-ai/claude-code"), ["package-install"]);
	assert.deepEqual(kinds("npm install --global yarn"), ["package-install"]);
	assert.deepEqual(kinds("cd /tmp && npm install -g cowsay"), ["package-install"]);
});

test("npm 本地安装 / npm ci / npm test 不命中", () => {
	assert.deepEqual(matchBashReminders("npm install"), []);
	assert.deepEqual(matchBashReminders("npm ci"), []);
	assert.deepEqual(matchBashReminders("npm test -- --runInBand"), []);
});

test("pip install --user → 恒命中(装进用户 site-packages)", () => {
	assert.deepEqual(kinds("pip install --user httpie"), ["package-install"]);
	// venv 信号在场也不例外:--user 就是要写用户目录
	assert.deepEqual(kinds("backend/.venv/bin/pip install --user httpie"), ["package-install"]);
});

test("无 venv 信号的 pip install / pip3 / python -m pip install → 命中", () => {
	assert.deepEqual(kinds("pip install requests"), ["package-install"]);
	assert.deepEqual(kinds("pip3 install requests"), ["package-install"]);
	assert.deepEqual(kinds("python3 -m pip install requests"), ["package-install"]);
	assert.deepEqual(kinds("sudo pip install requests"), ["package-install"]);
});

test("venv 信号(.venv/ 路径、venv/bin、source activate、VIRTUAL_ENV=)→ pip 不命中", () => {
	assert.deepEqual(matchBashReminders("backend/.venv/bin/pip install pytest"), []);
	assert.deepEqual(matchBashReminders("backend/.venv/bin/python -m pip install pytest"), []);
	assert.deepEqual(matchBashReminders("/opt/x/venv/bin/pip install pytest"), []);
	assert.deepEqual(matchBashReminders("source .venv/bin/activate && pip install pytest"), []);
	assert.deepEqual(matchBashReminders("VIRTUAL_ENV=/x/.venv pip install pytest"), []);
});

test("pip 非安装子命令不命中", () => {
	assert.deepEqual(matchBashReminders("pip list --outdated"), []);
	assert.deepEqual(matchBashReminders("pip download requests"), []);
});

// ---- 变形容错 ----

test("大小写变形:URL 主机大写照命中(curl/wget 与 URL 统一小写归一)", () => {
	assert.deepEqual(kinds('curl -sL "HTTPS://EXAMPLE.com/x"'), ["web-fetch"]);
	assert.deepEqual(kinds("wget HTTP://Example.com/x"), ["web-fetch"]);
});

test("引号包裹的 URL 照命中", () => {
	assert.deepEqual(kinds("curl -s 'https://example.com/a'"), ["web-fetch"]);
	assert.deepEqual(kinds('wget -O - "http://example.com/a?b=1" | head'), ["web-fetch"]);
});

test("带 userinfo 的 URL 剥出主机判内网(jenkins@10.0.0.5)", () => {
	assert.deepEqual(matchBashReminders("curl -u admin:pw http://jenkins@10.0.0.5:8080/job/x"), []);
});

// ---- 混合与零命中 ----

test("抓外链 + 装包同现 → 两类命中并存", () => {
	const hits = matchBashReminders("curl -s https://example.com/install.sh | sudo apt install -y jq");
	assert.deepEqual(hits.map((h) => h.kind), ["web-fetch", "package-install"]);
});

test("干净命令零命中", () => {
	for (const cmd of ["ls -la", "git status -sb", "node --test scripts/test_bash_tool_reminder.mjs", "docker compose ps"]) {
		assert.deepEqual(matchBashReminders(cmd), [], cmd);
	}
});

test("空串/非串输入零命中", () => {
	assert.deepEqual(matchBashReminders(""), []);
});

// ---- 提醒块与结果插投 ----

test("buildReminderBlock:带标记前缀,两类提示文案各就位", () => {
	const block = buildReminderBlock([
		{ kind: "web-fetch", evidence: "https://example.com" },
		{ kind: "package-install", evidence: "apt install" },
	]);
	assert.ok(block.startsWith("[bash-tool-reminder] "));
	assert.ok(block.includes("读网页优先用 web-read"));
	assert.ok(block.includes("禁擅自装包"));
	assert.ok(block.includes("https://example.com"));
	assert.ok(block.includes("apt install"));
});

test("remindBashResult:头部插提醒块,原块原样保留在尾部", () => {
	const original = [{ type: "text", text: "HTTP/2 200\ncontent-length: 12" }];
	const reminded = remindBashResult("curl -sI https://example.com", original);
	assert.ok(reminded);
	assert.equal(reminded.length, 2);
	assert.equal(reminded[0].type, "text");
	assert.ok(reminded[0].text.startsWith("[bash-tool-reminder] "));
	assert.deepEqual(reminded[1], original[0]); // 原始输出仍是末块(工作流取末段)
	assert.deepEqual(original, [{ type: "text", text: "HTTP/2 200\ncontent-length: 12" }]); // 原对象不被改
});

test("remindBashResult:多块 content 全保留(非 text 块不动)", () => {
	const original = [
		{ type: "image", source: { data: "x" } },
		{ type: "text", text: "stdout tail" },
	];
	const reminded = remindBashResult("wget -q http://example.com/a.png", original);
	assert.ok(reminded);
	assert.equal(reminded.length, 3);
	assert.deepEqual(reminded[1], original[0]);
	assert.deepEqual(reminded[2], original[1]);
});

test("remindBashResult:幂等——已含标记不再叠加", () => {
	const once = remindBashResult("curl -s https://example.com", [{ type: "text", text: "ok" }]);
	assert.ok(once);
	assert.equal(remindBashResult("curl -s https://example.com", once), undefined);
});

test("remindBashResult:未命中 / 非数组 content → undefined(不硬改形状)", () => {
	assert.equal(remindBashResult("ls -la", [{ type: "text", text: "ok" }]), undefined);
	assert.equal(remindBashResult("curl -s https://example.com", "raw string"), undefined);
	assert.equal(remindBashResult("curl -s http://localhost:8000/x", [{ type: "text", text: "ok" }]), undefined);
});
