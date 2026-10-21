// tArgs — 词条面 → translate(key, vars) 参数形状适配(测试共享件,终审
// standards 重构:opsErrorText.test / opsTable.test 逐字重复的 w 适配器
// 收编于此)。opsErrorText/opsTable 等纯函数返回 {key, vars?}(词条键面由
// 调用方过 t()),测试端以 zh-CN 真词典断言中文串。
export const tArgs = (
  r: { key: string; vars?: Record<string, string | number> },
): [string, Record<string, string | number> | undefined] => [r.key, r.vars];
