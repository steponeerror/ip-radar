"""Q14 配对显著性测试: pairs 级 bootstrap + McNemar 精确二项。

配对设计重抽样抽索引(对); 边际(非配对)Wilson 对配对设计无效,
不属本模块(见 significance.py 模块注)。
"""
import pytest

from ipdb._eval.significance import mcnemar, paired_bootstrap

IDENT = [True] * 30 + [False] * 70   # 全同臂: on == off


def test_identical_sequences_delta_zero_ci_contains_zero_p_large():
    res = paired_bootstrap(IDENT, list(IDENT), seed=7)
    assert res["delta"] == 0.0
    assert res["ci_lo"] <= 0.0 <= res["ci_hi"]
    assert res["p_one_sided"] == 1.0


def test_mcnemar_b10_c0_exact_p_below_001():
    on = [True] * 10 + [True] * 50    # 前 10 对: on 命中而 off 未命中
    off = [False] * 10 + [True] * 50  # → b=10, c=0
    res = mcnemar(on, off)
    assert (res["b"], res["c"]) == (10, 0)
    assert res["p"] == 2 / 2 ** 10    # 精确二项: 2·C(10,0)/2^10 = 1/512
    assert res["p"] < 0.01


def test_fixed_seed_bit_identical_results():
    a = paired_bootstrap(IDENT, list(IDENT), B=500, seed=42)
    b = paired_bootstrap(IDENT, list(IDENT), B=500, seed=42)
    assert a == b


def test_seed_is_required_keyword_only():
    # seed 必填(keyword-only): B 带默认后位置参数无法表达必填, 防共享默认 rng
    with pytest.raises(TypeError):
        paired_bootstrap(IDENT, list(IDENT))


def test_length_mismatch_raises_value_error():
    with pytest.raises(ValueError):
        paired_bootstrap(IDENT, IDENT[:-1], seed=1)
    with pytest.raises(ValueError):
        mcnemar(IDENT, IDENT[:-1])


def test_empty_paired_sequences_raise_value_error():
    with pytest.raises(ValueError):
        paired_bootstrap([], [], seed=1)
    with pytest.raises(ValueError):
        mcnemar([], [])


def test_one_sided_p_smoothed_never_zero_both_directions():
    # 单侧全胜: 全部重抽样 delta 落在观测侧, +1 平滑后 p = 1/(B+1), 永不 0
    pos = paired_bootstrap([True] * 20 + [False] * 80, [False] * 100, B=500, seed=3)
    neg = paired_bootstrap([False] * 100, [True] * 20 + [False] * 80, B=500, seed=3)
    assert pos["delta"] == 0.2 and neg["delta"] == -0.2
    assert pos["p_one_sided"] == neg["p_one_sided"] == 1.0 / 501
    assert pos["ci_lo"] > 0.0 and neg["ci_hi"] < 0.0
