import { describe, it, expect } from "vitest";
import { translate } from "../../i18n/translate";
import type { TFn } from "../../i18n";
import { tArgs } from "../../test/tArgs";
import { humanizeRoundMessage } from "../opsErrorText";

// 票 #148:上一轮失败面人话化——轮次失败信封原始 message(agent.mjs
// model_face:`模型失败面 stopReason=error:401 {"code":"401","message":"…"}`)
// → 人话短语(如「上游令牌过期(401)」)。原始信封不灭失(卡上可展开)。
// 纯函数返回 {key, vars} 由调用方过 t();zh-CN 真词典断言中文串。
const t: TFn = (key, vars) => translate("zh-CN", key, vars);

describe("humanizeRoundMessage — 模型面信封人话化", () => {
  it("已观测主形状:stopReason=error:401 + 嵌入 JSON 信封 → 上游令牌过期(401)", () => {
    const r = humanizeRoundMessage(
      '模型失败面 stopReason=error:401 {"code":"401","message":"令牌已过期或验证不正确"}',
    );
    expect(r && t(r.key, r.vars)).toBe("上游令牌过期（401）");
  });

  it("zai 余额不足面:非 HTTP code(1113)按 message 关键词归类,code 原样入括号", () => {
    const r = humanizeRoundMessage(
      '模型失败面 stopReason=error:1113 {"code":"1113","message":"余额不足"}',
    );
    expect(r && t(r.key, r.vars)).toBe("上游余额不足（1113）");
  });

  it("429 限流面;5xx 服务面;其余三位码 → 泛化上游错误(不猜具体因)", () => {
    expect(t(...tArgs(humanizeRoundMessage('stopReason=error:429 {"code":"429","message":"Too Many Requests"}')!)))
      .toBe("上游限流（429）");
    expect(t(...tArgs(humanizeRoundMessage("stopReason=error:503 upstream unavailable")!)))
      .toBe("上游服务错误（503）");
    expect(t(...tArgs(humanizeRoundMessage("stopReason=error:418")!))).toBe("上游错误（418）");
  });

  it("无码但关键词可判 → 无括号短语;无可判 → null(回退可读 code 名)", () => {
    expect(t(...tArgs(humanizeRoundMessage("上游返回:token expired")!))).toBe("上游令牌过期");
    expect(humanizeRoundMessage("stopReason=aborted")).toBeNull();
    expect(humanizeRoundMessage(null)).toBeNull();
  });
});
