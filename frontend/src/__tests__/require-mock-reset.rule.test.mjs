// #304-⑦ 规则单测:经 eslint Linter 平面配置直跑规则本体(fixture 为纯 JS 片段,
// 规则只查调用形态,不涉 TS 语法)。本文件是 .mjs:eslint 与被测规则均无仓内类型,
// 进 TS 编译门只会逼出 declare-module 妥协,故按 JS 测 JS;vitest include 已含 mjs 腿。
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Linter } from "eslint";
import rule from "../../eslint.rules/require-mock-reset.mjs";

const linter = new Linter();
const lint = (code) =>
  linter.verify(code, {
    plugins: { ipradar: { rules: { "require-mock-reset": rule } } },
    rules: { "ipradar/require-mock-reset": "error" },
    languageOptions: { ecmaVersion: "latest", sourceType: "module" },
  });

// vi.mock 双行开头,供行号断言(报错落在 vi.mock 那行)
const withViMock = (tail = "") =>
  `import { describe, it, expect, vi } from "vitest";\n` +
  `vi.mock("../api", () => ({ getDbStatus: vi.fn() }));\n` +
  tail;

describe("require-mock-reset(#304-⑦)", () => {
  it("vi.mock 而全文件无任何复位 → 报在 vi.mock 行", () => {
    const errors = lint(withViMock());
    expect(errors).toHaveLength(1);
    expect(errors[0].ruleId).toBe("ipradar/require-mock-reset");
    expect(errors[0].messageId).toBe("missingReset");
    expect(errors[0].line).toBe(2);
  });

  it("beforeEach 里 vi.resetAllMocks → 放行", () => {
    expect(lint(withViMock(`beforeEach(() => { vi.resetAllMocks(); });\n`))).toEqual([]);
  });

  it("vi.restoreAllMocks → 放行", () => {
    expect(lint(withViMock(`afterEach(() => { vi.restoreAllMocks(); });\n`))).toEqual([]);
  });

  it("vi.mocked(x).mockReset() → 放行", () => {
    expect(
      lint(withViMock(`beforeEach(() => { vi.mocked(getDbStatus).mockReset(); });\n`)),
    ).toEqual([]);
  });

  it("本地 mockFetch.mockReset() → 放行", () => {
    expect(lint(withViMock(`beforeEach(() => { mockFetch.mockReset(); });\n`))).toEqual([]);
  });

  it("vi.mocked(x).mockRestore() → 放行", () => {
    expect(
      lint(withViMock(`afterEach(() => { vi.mocked(spy).mockRestore(); });\n`)),
    ).toEqual([]);
  });

  it("仅 vi.clearAllMocks → 仍报(clear 只清调用史不剥实现,不算复位)", () => {
    expect(lint(withViMock(`beforeEach(() => { vi.clearAllMocks(); });\n`))).toHaveLength(1);
  });

  it("仅 x.mockClear() → 仍报", () => {
    expect(lint(withViMock(`beforeEach(() => { getDbStatus.mockClear(); });\n`))).toHaveLength(1);
  });

  it("无 vi.mock 的文件(即便零复位)→ 不报:规则只管 vi.mock 面", () => {
    expect(lint(`const onUpload = vi.fn();\n`)).toEqual([]);
  });

  it("注释里提到 mockReset(无真实调用)→ 仍报:按 AST 调用查,注释不算", () => {
    expect(lint(withViMock(`// 这里应该 mockReset\n`))).toHaveLength(1);
  });

  it("eslint.config.js 豁免区文件数 ≤5(豁免清单只进不出纪律的机检背书,tri-fe 评审 P2)", () => {
    // 读真源配置,数唯一把规则关 'off' 的块里 files: [...] 的 src/ 条目;
    // 超 5 = 有新文件进了豁免区,须先过裁决。>0 是激活钉:配置改引号/改写法
    // 导致零命中时,静默恒绿与真零豁免区分不开(同 check_source_counts 激活钉思想)。
    // 定位姿势同 warmReasonNail:fileURLToPath(vitest 下 import.meta.url 非 file: 协议)
    const cfgPath = join(dirname(fileURLToPath(import.meta.url)), "../../eslint.config.js");
    const cfg = readFileSync(cfgPath, "utf8");
    const offAt = cfg.indexOf("'ipradar/require-mock-reset': 'off'");
    expect(offAt).toBeGreaterThan(-1);
    const filesAt = cfg.lastIndexOf("files: [", offAt);
    const zone = cfg.slice(filesAt, cfg.indexOf("]", filesAt));
    const exempted = zone.match(/'src\/[^']+'/g) ?? [];
    expect(exempted.length).toBeGreaterThan(0);
    expect(exempted.length).toBeLessThanOrEqual(5);
  });
});
