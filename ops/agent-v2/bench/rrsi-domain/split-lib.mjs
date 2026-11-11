// split-lib.mjs — 劈分算法库(#325 F2 修复抽出;评审 rrsi-a-review.md P1:
// 冻结件 meta.heldoutSeats 与生成器互不可复现,出处链断裂)。largestRemainder 从
// gen-split.mjs 原样迁出(零行为变化),gen-split 与 tests/rrsi-split.test.mjs 共用
// 同一实现——「分席可重算复现」从此有单一真源可对账。
// #333 P2a 增补导出:mulberry32/shuffled(加源基准宇宙 gen-universe.mjs 复用同一
// 随机器与洗牌;gen-split.mjs 内联同款零改动——它的字节级输出由 rrsi-split 测试
// 冻结钉住,不动答案面生成器)。两处实现须保持逐字节同算法。

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

// mulberry32:跨 node 版稳定的 32 位 PRNG(仅用 >>>/Math.imul,无浮点路径分叉)。
// gen-split.mjs 内联款逐字节同源(#333 P2a 前已存在,勿单方改动)。
export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Fisher–Yates(向后洗牌,rng 注入可测)。gen-split.mjs 内联款逐字节同源。
export function shuffled(arr, rng) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
