"""配对显著性(Q14): pairs 级 bootstrap + McNemar 精确二项。

月度分层读数与(Phase 2)门 ON/OFF 差值一律配对设计(Q14 裁决): 同一
样本单位两臂各有一个命中指示, 重抽样抽的是索引(对), 不是边缘分布;
边际(非配对)Wilson 区间对配对设计无效, 本模块不提供(宁少算勿多算)。
纯 stdlib(random/math), 不引 scipy/numpy。
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence


def _check_paired(on_hits: Sequence[bool], off_hits: Sequence[bool]) -> int:
    """配对输入公共校验: 等长且非空(空序列的配对统计无定义)。"""
    n = len(on_hits)
    if n != len(off_hits):
        raise ValueError(
            f"paired sequences must be equal length, got {n} != {len(off_hits)}")
    if n == 0:
        raise ValueError("paired sequences must be non-empty (n=0 undefined)")
    return n


def paired_bootstrap(on_hits: Sequence[bool], off_hits: Sequence[bool],
                     B: int = 2000, *, seed: int) -> dict[str, float]:
    """配对差 bootstrap(Q14): 每次重抽样抽 n 个索引(对), delta = mean(on)-mean(off)。

    CI 取 bootstrap delta 的 2.5/97.5 最近秩百分位(第 ceil(p·B) 个;
    千分整数算, 避免浮点 ceil 漂移, 确定性)。p_one_sided 按观测方向数
    对立侧重抽样比例: delta>0 数 ≤0、delta<0 数 ≥0、delta==0 → 1.0;
    +1 平滑 (count+1)/(B+1): 有限 B 次重抽样永不出 p=0(保守, 宁少算)。
    seed keyword-only 必填: B 带默认后位置参数无法表达"无默认", 强制
    显式传防共享默认 rng。
    """
    n = _check_paired(on_hits, off_hits)
    if B < 1:
        raise ValueError("B must be >= 1")
    diff = [int(bool(a)) - int(bool(b)) for a, b in zip(on_hits, off_hits)]
    delta = sum(diff) / n
    rng = random.Random(seed)
    boots = sorted(sum(rng.choices(diff, k=n)) / n for _ in range(B))
    if delta > 0:
        p = (sum(1 for d in boots if d <= 0) + 1) / (B + 1)
    elif delta < 0:
        p = (sum(1 for d in boots if d >= 0) + 1) / (B + 1)
    else:
        p = 1.0
    return {
        "delta": delta,
        "ci_lo": boots[-(-25 * B // 1000) - 1],    # 2.5% 最近秩(整数 ceil)
        "ci_hi": boots[-(-975 * B // 1000) - 1],   # 97.5% 最近秩(整数 ceil)
        "p_one_sided": p,
    }


def mcnemar(on_hits: Sequence[bool], off_hits: Sequence[bool]) -> dict[str, int | float]:
    """McNemar 精确检验(Q14): 只看两臂不一致对 b = on∧¬off, c = ¬on∧off。

    双侧 p = min(1, 2·BinomCDF(min(b,c); b+c, 1/2)), math.comb 精确整数
    求和、只在最终除法转 float(与 temporal.fisher_exact 同款纪律);
    b == c == 0(零不一致对, 无证据)→ p = 1.0。
    """
    _check_paired(on_hits, off_hits)
    b = sum(1 for a, o in zip(on_hits, off_hits) if a and not o)
    c = sum(1 for a, o in zip(on_hits, off_hits) if o and not a)
    n = b + c
    cdf = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return {"b": b, "c": c, "p": min(1.0, 2 * cdf / 2 ** n)}
