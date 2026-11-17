#!/usr/bin/env node
// judge.mjs — 同会话成对 + 噪声带判冠军(票 #356 骨架 v1 交付面 1 终点站)。
//
// 判定输入 = 同会话成对 trial 读数:同一轮驱动器在同一时间窗内对冠军面/候选面逐题
// 逐副本各跑一次 trial(成对消会话漂移——prop-r4 判例:全宇宙 k=3 的「史上最高」被
// 同会话成对拆穿=会话面抬升,跨面比较必须同会话成对),对读 score_frac(#343 分级
// 钥匙,run-trial 打分面单源)。
//
// 噪声带判据(k≥3 律,SKILL.md「k≥3 的噪声带内差异不是增益」的机制化):
//   对差 d_i = candFrac_i − champFrac_i(逐对);mean_d = 均值;sd_d = 样本标准差
//   (成对差的面内噪声);带 = [mean_d − sd_d, mean_d + sd_d]。
//   gained ⇔ mean_d > 0 ∧ mean_d > sd_d(均差为正且越出噪声带上沿)。
//   有效对数 < 3(k≥3 律的面)→ insufficient:不是零增益也不是增益——判定数据不足,
//   不入熄火账(异常通道报告)。
// 这是骨架 v1 的可解释判据;健康轮基准落地后若另有带口径,改本文件单源。

const finite = (x) => typeof x === "number" && Number.isFinite(x);

// pairs: [{question, replica, champFrac, candFrac}];任一面 frac 非有限数的对=无效对
// (缺席/崩 trial),剔除出统计但计入 missing 留痕(宁红勿漏:missing 也进报告)。
export function judgePaired({ pairs }) {
  const valid = [];
  let missing = 0;
  for (const p of pairs ?? []) {
    if (finite(p?.champFrac) && finite(p?.candFrac)) valid.push(p);
    else missing += 1;
  }
  const n = valid.length;
  const diffs = valid.map((p) => p.candFrac - p.champFrac);
  const champMean = n ? valid.reduce((s, p) => s + p.champFrac, 0) / n : null;
  const candMean = n ? valid.reduce((s, p) => s + p.candFrac, 0) / n : null;
  const meanDiff = n ? diffs.reduce((a, b) => a + b, 0) / n : null;
  const sdDiff = n > 1 ? Math.sqrt(diffs.reduce((s, d) => s + (d - meanDiff) ** 2, 0) / (n - 1)) : (n === 1 ? 0 : null);
  const insufficient = n < 3;
  const gained = !insufficient && meanDiff > 0 && meanDiff > sdDiff;
  // 逐题汇总(题内均差;报告面)
  const byQ = new Map();
  for (const p of valid) {
    const e = byQ.get(p.question) ?? { question: p.question, pairs: 0, diffSum: 0 };
    e.pairs += 1;
    e.diffSum += p.candFrac - p.champFrac;
    byQ.set(p.question, e);
  }
  return {
    n, missing,
    champ_mean: champMean, cand_mean: candMean,
    mean_diff: meanDiff, sd_diff: sdDiff,
    band: { low: insufficient ? null : meanDiff - sdDiff, high: insufficient ? null : meanDiff + sdDiff },
    insufficient, gained,
    per_question: [...byQ.values()].map((e) => ({ question: e.question, pairs: e.pairs, mean_diff: +(e.diffSum / e.pairs).toFixed(4) })).sort((a, b) => a.question.localeCompare(b.question)),
  };
}
