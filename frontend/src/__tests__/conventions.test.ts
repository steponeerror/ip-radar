import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

// 挡粗心的守卫,不是防恶意(#486;做法 = 后端 backend/tests/core/test_conventions.py
// 的源码文本巡检同款):「回 401 踢回登录」的判定已收编进 api.ts 的
// isUnauthorized,手抄 `status === 401` 只会是漏改 —— 漏改的表现是会话过期后
// 那一页落一条红字,而不是回登录页。该写法全 src 只许出现在 api.ts(收编
// 函数本体)一处;新增管理页面/错误路径一律改调 isUnauthorized。
// 注意:连注释里原样写这个式子也会红 —— 措辞绕开即可。
// 锚计数前先去掉行注释(#486 评审 S3):否则 api.ts 注释里的式子也算命中,
// 函数体被改写成守卫不认的形状(如改判 403)时锚不会红。
const SRC = join(import.meta.dirname, ".."); // src/__tests__ → 上一级 src/

// 测试文件不巡检(它们演练 401 场景本属正常);test infra(setup)同免。
const TESTISH = /(^|[\\/])(__tests__|test)([\\/])|\.test\.[cm]?[jt]sx?$/;

function walk(dir: string, out: string[] = []): string[] {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (/\.[cm]?[jt]sx?$/.test(ent.name) && !TESTISH.test(p)) out.push(p);
  }
  return out;
}

describe("conventions: 401 判定唯一入口(#486)", () => {
  it("`status === 401` 只出现在 src/api.ts(isUnauthorized 本体),别处一律改调它", () => {
    const offenders: string[] = [];
    let guardFileHits = 0;
    for (const f of walk(SRC)) {
      const rel = relative(SRC, f);
      // S3:去行注释再数(过度去除只会漏报不会误报,挡粗心够用)
      const hits = readFileSync(f, "utf8").replace(/\/\/.*$/gm, "").match(/status\s*===\s*401/g)?.length ?? 0;
      if (rel === "api.ts") guardFileHits = hits;
      else if (hits > 0) offenders.push(rel);
    }
    expect(guardFileHits,
      "api.ts 里的 isUnauthorized 本体不见了 —— 收编函数被改名/删除,守卫锚失效")
      .toBeGreaterThan(0);
    expect(offenders,
      `手抄 status === 401 必须改调 api.ts 的 isUnauthorized:${offenders.join(", ")}`)
      .toEqual([]);
  });
});
