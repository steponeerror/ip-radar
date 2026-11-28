// test_dockerfile_needs_copy.mjs — #528:Dockerfile COPY NEEDS.md 行钉子。
// 发现轮 SCAN 步(ops/pipeline-core/pipeline/steps.mjs)经 repoRoot=AGENT_DIR/../.. 读
// /app/NEEDS.md;镜像缺该文件时 needs 面恒空,步只能留 needs_file: missing 留痕——
// 证据面不能缺。docker build 不在本地门内(纪律:不 docker),故钉 Dockerfile 文本行 +
// .dockerignore 不排除 NEEDS.md;build 层验证留主会话部署时看(hadolint/docker build --check
// 均不在工具面,报告里写明没验证)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("Dockerfile:NEEDS.md COPY 行在场(#528 发现轮 needs 面)", () => {
  const df = fs.readFileSync(path.join(ROOT, "Dockerfile"), "utf8");
  assert.match(df, /^COPY NEEDS\.md \.\/NEEDS\.md$/m, "Dockerfile 缺 `COPY NEEDS.md ./NEEDS.md` 行(SCAN 读 /app/NEEDS.md 会静默落空)");
});

test(".dockerignore:NEEDS.md 未被排除(排除=COPY 静默拷空,build 上下文律)", () => {
  const ig = path.join(ROOT, ".dockerignore");
  assert.ok(fs.existsSync(ig), ".dockerignore 缺席(现状应有)");
  const lines = fs.readFileSync(ig, "utf8").split("\n").map((l) => l.trim());
  assert.ok(!lines.includes("NEEDS.md"), ".dockerignore 不得排除 NEEDS.md(排除=COPY 拷不到,build 不报错)");
});
