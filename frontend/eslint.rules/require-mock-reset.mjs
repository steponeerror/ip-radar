// #304-⑦:vi.mock 的 mock 缺显式复位会跨用例泄漏状态——
// mockResolvedValue/mockImplementation 及未消费的 Once 队列都会带进后续用例。
// 语义:测试文件出现 vi.mock( 而全文件无 mockReset/mockRestore/
// vi.resetAllMocks/vi.restoreAllMocks 任一调用 → 报在首处 vi.mock。
// clearAllMocks/mockClear 只清调用史、不剥实现,不算复位,故不采认;
// 工厂内联默认值的存量文件在 eslint.config.js 豁免区列名写理由,不再新增。
const ALL_RESET_CALLEES = new Set(["vi.resetAllMocks", "vi.restoreAllMocks"]);

// 归一调用名:vi.mock / mockFetch.mockReset → 全名;vi.mocked(x).mockReset → ".mockReset"
function calleeMarker(callee) {
  if (callee.type === "Identifier") return callee.name;
  if (
    callee.type === "MemberExpression" &&
    !callee.computed &&
    callee.property.type === "Identifier"
  ) {
    if (callee.object.type === "Identifier") {
      return `${callee.object.name}.${callee.property.name}`;
    }
    return `.${callee.property.name}`;
  }
  return null;
}

/** @type {import("eslint").Rule.RuleModule} */
export default {
  meta: {
    type: "problem",
    docs: {
      description:
        "vi.mock 测试文件必须有显式 mock 复位(mockReset/mockRestore/resetAllMocks/restoreAllMocks;clear 族不算)",
    },
    schema: [],
    messages: {
      missingReset:
        "vi.mock 在此,但全文件无显式复位(mockReset/mockRestore/vi.resetAllMocks/vi.restoreAllMocks)。" +
        "clearAllMocks/mockClear 只清调用史、不剥实现,不算复位。" +
        "工厂内联默认值会被 reset 族剥掉的存量文件,请到 eslint.config.js 豁免区列名并写明理由。",
    },
  },
  create(context) {
    let firstViMock = null;
    let hasReset = false;
    return {
      CallExpression(node) {
        const marker = calleeMarker(node.callee);
        if (marker === "vi.mock") {
          if (!firstViMock) firstViMock = node;
        } else if (
          marker &&
          (ALL_RESET_CALLEES.has(marker) ||
            marker.endsWith(".mockReset") ||
            marker.endsWith(".mockRestore"))
        ) {
          hasReset = true;
        }
      },
      "Program:exit"() {
        if (firstViMock && !hasReset) {
          context.report({ node: firstViMock, messageId: "missingReset" });
        }
      },
    };
  },
};
