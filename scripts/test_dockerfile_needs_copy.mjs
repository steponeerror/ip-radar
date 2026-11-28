// test_dockerfile_needs_copy.mjs — #528:Dockerfile COPY NEEDS.md 行钉子。
// 发现轮 SCAN 步(ops/pipeline-core/pipeline/steps.mjs)经 repoRoot=AGENT_DIR/../.. 读
// /app/NEEDS.md;镜像缺该文件时 needs 面恒空,步只能留 needs_file: missing 留痕——
// 证据面不能缺。docker build 不在本地门内(纪律:不 docker),故钉 Dockerfile 文本行 +
// .dockerignore 不排除 NEEDS.md;build 层验证留主会话部署时看(hadolint/docker build --check
// 均不在工具面,报告里写明没验证)。
// #528 返工(评审建议 6)补两盲区:①行必须在最后一个 FROM 之后的最终阶段、且在
// WORKDIR /app 之后(挪进 opsagent 阶段=文件不在 /app,文本钉子照样绿);②.dockerignore
// 逐行做简单通配匹配(*=任意段),*.md / NEEDS* 这类前缀模式也拦。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("Dockerfile:NEEDS.md COPY 行在场且在最终阶段 /app(#528 发现轮 needs 面)", () => {
  const lines = fs.readFileSync(path.join(ROOT, "Dockerfile"), "utf8").split("\n");
  const copyIdx = lines.findIndex((l) => l.trim() === "COPY NEEDS.md ./NEEDS.md");
  assert.notEqual(copyIdx, -1, "Dockerfile 缺 `COPY NEEDS.md ./NEEDS.md` 行(SCAN 读 /app/NEEDS.md 会静默落空)");
  const lastFromIdx = lines.reduce((acc, l, i) => (/^\s*FROM\s/.test(l) ? i : acc), -1);
  const workdirAppIdx = lines.findIndex((l) => l.trim() === "WORKDIR /app");
  assert.ok(copyIdx > lastFromIdx, `COPY 行(第 ${copyIdx + 1} 行)必须在最后一个 FROM(第 ${lastFromIdx + 1} 行)之后的最终阶段`);
  assert.ok(copyIdx > workdirAppIdx && workdirAppIdx !== -1, `COPY 行必须在 WORKDIR /app(第 ${workdirAppIdx + 1} 行)之后(落位 /app/NEEDS.md)`);
});

test(".dockerignore:没有任何模式能排除 NEEDS.md(排除=COPY 静默拷空,build 不报错)", () => {
  const ig = path.join(ROOT, ".dockerignore");
  assert.ok(fs.existsSync(ig), ".dockerignore 缺席(现状应有)");
  // 简单通配:* = 任意段(不追 docker 的 ** / 字符类语义;评审点名的 *.md / NEEDS* / !* 三形全覆盖)
  const globToRe = (p) => new RegExp(`^${p.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*")}$`);
  const ignoring = fs.readFileSync(ig, "utf8").split("\n").map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#") && !l.startsWith("!")) // "!"/"!*"/!x = 取反行,不排除
    .filter((l) => globToRe(l).test("NEEDS.md"));
  assert.deepEqual(ignoring, [], `.dockerignore 这些模式会排除 NEEDS.md(COPY 拷不到且 build 不报错):${ignoring.join("、")}`);
});
