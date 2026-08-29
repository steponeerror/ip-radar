"""asset 布林后验排序(spec §4:与威胁断言同构;本期只排序不输出 conf)。"""
from ipdb._types import AssetStatement
from ipdb._registry import _order_asset_stmts


def _stmt(src, value, r=None):
    return AssetStatement(source=src, value=value)


def test_true_majority_orders_true_first(monkeypatch):
    monkeypatch.setattr("ipdb._registry.SOURCE_RELIABILITY",
                        {"tor_exits": 0.95, "weak": 0.60})
    stmts = [_stmt("weak", False), _stmt("tor_exits", True)]
    out = _order_asset_stmts(stmts)
    assert out[0].value is True          # 0.95 正向压 0.60 反向


def test_false_majority_orders_false_first(monkeypatch):
    monkeypatch.setattr("ipdb._registry.SOURCE_RELIABILITY",
                        {"tor_exits": 0.95, "weak": 0.60})
    stmts = [_stmt("weak", True), _stmt("tor_exits", False)]
    out = _order_asset_stmts(stmts)
    assert out[0].value is False


def test_non_boolean_keys_untouched():
    stmts = [_stmt("cn_isp", "中国电信"), _stmt("ipinfo_lite", "China Telecom")]
    assert _order_asset_stmts(stmts) == stmts


def test_same_direction_r_desc():
    # MAP 同方向内按 r 降序:三个 True,r 高者在前
    import ipdb._registry as reg
    original = dict(reg.SOURCE_RELIABILITY)
    reg.SOURCE_RELIABILITY.clear()
    reg.SOURCE_RELIABILITY.update({"a": 0.9, "b": 0.7, "c": 0.6})
    try:
        stmts = [_stmt("c", True), _stmt("a", True), _stmt("b", True)]
        out = _order_asset_stmts(stmts)
        assert [s.source for s in out] == ["a", "b", "c"]
    finally:
        reg.SOURCE_RELIABILITY.clear()
        reg.SOURCE_RELIABILITY.update(original)


def test_unknown_source_defaults_neutral():
    # 未登记源 r=0.5:2 个 unknown True vs 1 个 unknown False → σ(logit(.5))=50 边界,
    # p_true>=50 → True 前置(50 边界归 True 方向)
    import ipdb._registry as reg
    original = dict(reg.SOURCE_RELIABILITY)
    reg.SOURCE_RELIABILITY.clear()
    try:
        stmts = [_stmt("u1", False), _stmt("u2", True), _stmt("u3", True)]
        out = _order_asset_stmts(stmts)
        assert out[0].value is True
    finally:
        reg.SOURCE_RELIABILITY.clear()
        reg.SOURCE_RELIABILITY.update(original)
