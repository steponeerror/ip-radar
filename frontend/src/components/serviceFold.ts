import type { AssetStatement } from "../api";

// 折并(GLOSSARY「折并」词条;grill 2026-10-11 五裁 b/a/a/a/a + service chip
// 泛化同日,#105 as_org 判例同构):展示层合并规则——归一判定值一致的多源
// 展示合一,chip 正文只显归一角色词,证人 source · native 逐行下沉悬停;
// 后端载荷、置信度、算法零动,证据不灭失;不按可靠性挑正文赢家(零选择
// 算法,宁少算)。#245 抽取:此前 IpDetailPanel/ResultTable 各持一份内联
// 拷贝,两处靠 `service-${value}` 字符串 key 暗协议耦合(ResultTable 的
// cdn 压制判据 startsWith("service-") 悬在其上),现 key 前缀随本模块常量化。

/** service 折并 chip 的稳定 key 前缀(ResultTable 的 cdn 压制判据派生自此)。 */
export const SERVICE_CHIP_KEY_PREFIX = "service-";

export const serviceChipKey = (role: string) => `${SERVICE_CHIP_KEY_PREFIX}${role}`;

// service 角色词折并:按源侧写死的归一角色词(dns/ntp/cdn/cloud)分组,
// Map 首见序稳定(分组顺序与抽取前两处内联实现逐位一致);attributes 值
// 可布尔(is_*),service 恒字符串,此处 String() 收窄。
export function foldServiceStatements(
  stmts: AssetStatement[],
): { value: string; detail: string }[] {
  const byRole = new Map<string, AssetStatement[]>();
  for (const s of stmts) {
    const v = String(s.value);
    const g = byRole.get(v) ?? [];
    g.push(s);
    byRole.set(v, g);
  }
  return [...byRole].map(([value, group]) => ({
    value,
    detail: group.map((s) => `${s.source} · ${s.native_type ?? s.value}`).join("\n"),
  }));
}
