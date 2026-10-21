import { describe, it, expect } from "vitest";
import { translate } from "../../i18n/translate";
import type { TFn } from "../../i18n";
import { relTime, noteText, precDate } from "../opsTable";

// 票 #148:表格统一件(本票首创,#149 档案面复用)。纯函数面 = 相对时间、
// 台账备注人话化;列名映射 = ops.col.* 词条(组件测试断言列头)。t 注入
// zh-CN 真词典(断言中文人话串,与 en 词条同 key)。
const t: TFn = (key, vars) => translate("zh-CN", key, vars);

describe("precDate — 判例文件名日期前缀(#149 判例行相对时间源)", () => {
  it("YYYY-MM-DD-<slug>.md 命名约定 → 提取日期(day 精度,同台账行)", () => {
    expect(precDate("2026-10-19-ustc-myip-incremental-queue-signoff.md")).toBe("2026-10-19");
    expect(precDate("2026-10-20-ruling-abc123def0.md")).toBe("2026-10-20");
  });

  it("无日期前缀名 → null(宁少算:不猜,调用方不显时间)", () => {
    expect(precDate("notes-plain.md")).toBeNull();
    expect(precDate("2026-10-19.md")).toBeNull(); // 约定形 = 日期后必有 slug 段
    expect(precDate("")).toBeNull();
  });
});

describe("relTime — 相对时间 + title 完整戳", () => {
  const NOW = Date.parse("2026-10-21T12:00:00Z");

  it("台账日期(YYYY-MM-DD)→ 天前,title = 日期原样(台账行精度即日期)", () => {
    const r = relTime("2026-10-20", NOW);
    expect(t(r.key, r.vars)).toBe("1天前");
    expect(r.title).toBe("2026-10-20");
  });

  it("包 modified(ISO)→ 小时/分钟级;悬停 title = ISO 完整戳", () => {
    expect(t(...w(relTime("2026-10-21T11:30:00Z", NOW)))).toBe("30分钟前");
    expect(t(...w(relTime("2026-10-21T05:00:00Z", NOW)))).toBe("7小时前");
    expect(relTime("2026-10-21T05:00:00Z", NOW).title).toBe("2026-10-21T05:00:00Z");
  });

  it("不可解析串 → 未知,title 原样不灭失", () => {
    const r = relTime("not-a-date", NOW);
    expect(t(r.key, r.vars)).toBe("未知");
    expect(r.title).toBe("not-a-date");
  });
});

describe("noteText — 台账备注 key=value 人话化", () => {
  it("spawn error_code=<九词闭集> → 启动失败：模型面", () => {
    expect(noteText(t, "spawn error_code=model_face")).toBe("启动失败：模型面");
  });

  it("spawn 带 pkg 后缀 → 人话 + 包名原样;带自由消息(infra 面)同样人话化", () => {
    expect(noteText(t, "spawn error_code=model_face; pkg=2026-10-20-health-1126.md"))
      .toBe("启动失败：模型面 · 2026-10-20-health-1126.md");
    expect(noteText(t, "spawn error_code=infra; 轮次信封契约违背(rc=2)"))
      .toBe("启动失败：基础设施 · 轮次信封契约违背(rc=2)");
  });

  it("闭集外 error_code 不猜 → null(调用方回原文)", () => {
    expect(noteText(t, "spawn error_code=not_in_closed_set")).toBeNull();
  });

  it("tools=N[ queue=M] sdk=X → 次数人话 + sdk 原样", () => {
    expect(noteText(t, "tools=1 sdk=pi-agent-core")).toBe("1 次工具调用 · sdk=pi-agent-core");
    expect(noteText(t, "tools=2 queue=1 sdk=pi-agent-core"))
      .toBe("2 次工具调用 · 入队 1 项 · sdk=pi-agent-core");
  });

  it("未知形状/空串 → null(宁少算:原文呈现)", () => {
    expect(noteText(t, "manual free-text note")).toBeNull();
    expect(noteText(t, "")).toBeNull();
  });
});

// relTime 返回 {key, vars?} → translate(key, vars) 调用形状适配
const w = (r: { key: string; vars?: Record<string, string | number> }): [string, Record<string, string | number> | undefined] =>
  [r.key, r.vars];
