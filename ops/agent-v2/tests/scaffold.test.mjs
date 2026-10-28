// scaffold.test.mjs — v2 骨架结构面断言(零网络零模型调用;票 #225)
// 面:①registry 红线(零工具/零自有任务;不装内建 CodingTools)②compaction 默认关
// ③SQLite journal=WAL(t1-notes「进程崩溃 commit 安全」的落库前提)④pi-ai 单实例@1.4.0
// (t1-notes 风险2 双实例陷阱)⑤db 落位推导。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import { createRegistry } from "@earendil-works/pi-durable";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { buildRegistry } from "../registry.mjs";
import { HARNESS_SETTINGS, resolveDbPath, ROOT } from "../entry.mjs";

const V2_DIR = path.resolve(import.meta.dirname, ".."); // ops/agent-v2

test("registry 红线:零工具、仅 ops 扩展、零自有任务(不装内建 CodingTools)", () => {
  const snapshot = buildRegistry().snapshot();
  // ops 红线(spec 背景节 + t1-notes §1.2):v2 不安装任何内建 coding 工具面;
  // T3/T4 的领域工具(defineTool)经 tasks/ 同扩展接入,当前骨架必须为空。
  assert.deepEqual(snapshot.tools(), [], "工具面必须为空:CodingTools/read/write/edit/bash 一概不装");
  assert.deepEqual(snapshot.installed().map((e) => e.name), ["ops"]);
  // 自有任务零:与裸 createRegistry() 的内建任务集完全一致(内建 generation/tool/compaction 三任务保留)。
  const names = (s) => s.tasks().map((t) => `${t.definition.name}@${t.definition.version}`).sort();
  assert.deepEqual(names(snapshot), names(createRegistry().snapshot()));
});

test("compaction 默认关(t1-notes 风险5:自动摘要改写上下文,shadow 对拍期禁用)", () => {
  assert.equal(HARNESS_SETTINGS.compaction.enabled, false);
});

test("SQLite 落库 journal=WAL(chord 适配器缺省;断电面按 t1-notes 风险另计)", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "v2-scaffold-"));
  const dbPath = path.join(tmp, "wal.sqlite");
  const storage = await openNodeSqliteStorage(dbPath);
  await storage.close(BACKGROUND_CONTEXT);
  const ro = new DatabaseSync(dbPath, { readOnly: true });
  try {
    assert.equal(ro.prepare("PRAGMA journal_mode").get().journal_mode, "wal");
  } finally {
    ro.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("pi-ai 单实例且 =1.4.0;跨目录(ops/agent)同版(t1-notes 风险2 双实例陷阱)", () => {
  // v2 树内:npm ls --parseable 每个 pi-ai 物理路径必须唯一
  const out = execFileSync(
    "npm", ["ls", "@earendil-works/pi-ai", "--all", "--parseable"],
    { cwd: V2_DIR, encoding: "utf8" },
  ).trim();
  const paths = out.split("\n").map((l) => l.trim()).filter(Boolean);
  assert.ok(paths.length >= 1, `npm ls 无输出:${out}`);
  assert.equal(new Set(paths).size, 1, `pi-ai 多物理实例:${paths.join(" | ")}`);
  assert.match(paths[0], /node_modules[/]@earendil-works[/]pi-ai$/);
  const v2Version = JSON.parse(fs.readFileSync(path.join(paths[0], "package.json"), "utf8")).version;
  assert.equal(v2Version, "1.4.0");
  // 跨目录:models.mjs 只读 import 自 ops/agent,其 pi-ai 解析自 ops/agent/node_modules,
  // 两份物理拷贝必须同版(否则两套凭证店/目录互不相识,api-map §0)。
  const agentPkg = path.join(ROOT, "ops", "agent", "node_modules", "@earendil-works", "pi-ai", "package.json");
  assert.ok(fs.existsSync(agentPkg), `ops/agent 未 npm ci(缺 ${agentPkg})`);
  assert.equal(JSON.parse(fs.readFileSync(agentPkg, "utf8")).version, v2Version, "ops/agent pi-ai 版本漂移");
});

test("db 落位:OPS_V2_DB > DOCS_ROOT/ops/agent-v2.sqlite > <仓根>/docs/ops/agent-v2.sqlite(t1-notes 建议3)", () => {
  assert.equal(resolveDbPath({ OPS_V2_DB: "/tmp/x.sqlite" }), "/tmp/x.sqlite");
  assert.equal(resolveDbPath({ DOCS_ROOT: "/d" }), path.join("/d", "ops", "agent-v2.sqlite"));
  assert.equal(resolveDbPath({}), path.join(ROOT, "docs", "ops", "agent-v2.sqlite"));
});
