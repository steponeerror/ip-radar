// split-lib.mjs — 劈分算法库(#325 F2 修复抽出;评审 rrsi-a-review.md P1:
// 冻结件 meta.heldoutSeats 与生成器互不可复现,出处链断裂)。largestRemainder 从
// gen-split.mjs 原样迁出(零行为变化),gen-split 与 tests/rrsi-split.test.mjs 共用
// 同一实现——「分席可重算复现」从此有单一真源可对账。
//
// 最大余数法分席:N 个考题、H 个留出名额 → 每类份额;余数并列按类别字典序(确定性)。
export function largestRemainder(countsByCategory, H) {
  const cats = Object.keys(countsByCategory).sort();
  const N = cats.reduce((s, c) => s + countsByCategory[c], 0);
  const base = new Map(cats.map((c) => [c, Math.floor((countsByCategory[c] * H) / N)]));
  let left = H - cats.reduce((s, c) => s + base.get(c), 0);
  const order = cats
    .map((c) => ({ c, rem: (countsByCategory[c] * H) / N - base.get(c) }))
    .sort((x, y) => y.rem - x.rem || (x.c < y.c ? -1 : 1));
  for (const { c } of order) {
    if (left <= 0) break;
    base.set(c, base.get(c) + 1);
    left -= 1;
  }
  if (left !== 0) throw new Error(`分席不闭合:left=${left}(H=${H},N=${N})`);
  return base;
}
