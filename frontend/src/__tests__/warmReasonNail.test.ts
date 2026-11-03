// @vitest-environment node
// #294 状态字单源:跨栈对拍钉子(绊线测试)。
//
// 契约链:后端冷启动门 X-IPRadar-Reason 头字面值(真源 = backend/ipdb/
// _coldstart.py 的 REASON_* 常量)→ backend/main.py _reason_code 映射为
// 信封语义码(连字符→下划线)→ 前端 LookupView 的 code 判定。本钉子机读
// 两端源文件,任一侧擅自改字面值即红(先例:两端常数对拍见
// backend/tests/test_ops_rounds.py 的 _OPS_LOG_KEEP 钉子,此为其前端侧)。
// 期望值全部来自独立已知好值(API 契约与既有 header 断言),非回算。
//
// node 环境原因:文件读取要真 fs(jsdom 下 import.meta.url 是 http: 协议)。
// ts 指令原因:tsconfig.app.json types 白名单不含 node,显式 node:fs
// 导入报 TS2591;又不能把 node 加进全局 types —— node 全局类型会泄漏
// 污染 setInterval 等 DOM 全局(误伤 WarmingProvider)。若将来 node
// 类型正式入列,下行 expect-error 变 unused 自动报错提醒清理。
// @ts-expect-error TS2591: node:fs 在 types 白名单外(见上注)
import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";

const repoRoot = new URL("../../..", import.meta.url); // src/__tests__/ → 仓根

function read(rel: string): string {
  return readFileSync(new URL(rel, repoRoot), "utf8");
}

const gatePy = read("backend/ipdb/_coldstart.py");
const mainPy = read("backend/main.py");
const lookupView = read("frontend/src/LookupView.tsx");

function extractConst(source: string, name: string): string {
  const m = source.match(new RegExp(`${name} = "([^"]+)"`));
  if (!m) throw new Error(`${name} not found in backend gate module`);
  return m[1];
}

describe("跨栈对拍:冷启动门 reason 串(backend/ipdb/_coldstart.py ↔ frontend)", () => {
  const reasonWarming = extractConst(gatePy, "REASON_WARMING");
  const reasonNoSources = extractConst(gatePy, "REASON_NO_SOURCES");

  it("后端 reason 常量 = 头契约已知好值", () => {
    expect(reasonWarming).toBe("warming");
    expect(reasonNoSources).toBe("no-sources");
  });

  it("前端 LookupView 消费的语义码 = 信封契约已知好值", () => {
    const codes = [...lookupView.matchAll(/code === "([a-z_]+)"/g)].map((m) => m[1]);
    expect(codes).toContain("warming");
    expect(codes).toContain("no_sources");
  });

  it("reason→语义码换算(连字符→下划线)两端成对一致", () => {
    // 单侧改名(如 backend 改 "warming-up" 或前端改 "warm")都会使配对断开
    expect(reasonWarming.replace(/-/g, "_")).toBe("warming");
    expect(reasonNoSources.replace(/-/g, "_")).toBe("no_sources");
  });

  it("后端单源接线:main.py 的 reason 头与 _reason_code 全走模块常量,零裸串", () => {
    // 头设置 + 头→语义码映射共 4 处引用必须都是 _coldstart.REASON_*
    const wired =
      [...mainPy.matchAll(/X-IPRadar-Reason": _coldstart\.REASON_(WARMING|NO_SOURCES)/g)].length +
      [...mainPy.matchAll(/reason == _coldstart\.REASON_(WARMING|NO_SOURCES)/g)].length;
    expect(wired).toBe(4);
    // 裸字面值回流 = 单源被绕过,绊
    expect(mainPy).not.toMatch(/X-IPRadar-Reason": "(warming|no-sources)"/);
  });
});
