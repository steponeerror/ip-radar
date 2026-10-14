"""T10 引擎 asof 时钟锚(spec §8 四条款之三,F2/S37)——位等价护栏。

衰减评估锚定语料装配时钟而非墙钟,月度读数可复现;asof=None 默认 =
墙钟 = 现网行为逐位不变(哲学 7)。链条:registry.lookup(asof=) →
_merge._assess_classification(asof=) → _logodds.coefficient(now=)
(叶参 now:datetime|None 现成);顶层 threat 重融合(_types.threat_summary)
同锚——LookupResult.asof 携带,to_dict() 时免重查引擎(F10 快照消费点)。
"""
from datetime import datetime, timedelta, timezone

import pytest

import ipdb._logodds as lo
import ipdb._registry as reg
from ipdb._types import SourceHealth


# ── (a) 叶级位等价:now=None ≡ 显式同刻墙钟值 ─────────────────────

def test_coefficient_none_now_bit_identical_to_explicit(monkeypatch):
    fixed = datetime(2026, 10, 14, 6, 0, 0, 123456, tzinfo=timezone.utc)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(lo, "datetime", Frozen)
    first_seen = "2026-06-01T00:00:00Z"
    default = lo.coefficient(0.9, first_seen, "spam")            # now=None
    explicit = lo.coefficient(0.9, first_seen, "spam", now=fixed)
    assert default == explicit              # 同一 now → 同一浮点,逐位一致
    assert repr(default) == repr(explicit)


# ── (b) asof 换算 + 过去锚 → 衰减更轻 ─────────────────────────────

def test_asof_to_now_roundtrip_exact():
    t0 = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    assert lo.asof_to_now(t0.timestamp()) == t0   # epoch 秒往返不丢 µs
    assert lo.asof_to_now(None) is None           # None → 墙钟哨兵


def test_past_asof_lighter_decay():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fs = "2026-01-01T00:00:00Z"                   # first_seen == t0
    age = lambda days: t0.timestamp() + days * 86400
    c_10d = lo.coefficient(0.9, fs, "spam", now=lo.asof_to_now(age(10)))
    c_100d = lo.coefficient(0.9, fs, "spam", now=lo.asof_to_now(age(100)))
    assert c_10d > c_100d                    # 近锚 → 衰减更轻 → 系数更大
    # 锚点精确:恰 60d(1 半衰期)→ 系数恰减半
    assert lo.coefficient(0.9, fs, "spam",
                          now=lo.asof_to_now(age(60))) == lo.logit(0.9) * 0.5


# ── (c) 端到端:lookup(asof=) 组级与顶层 threat 同锚 ────────────────

class FakeThreatSource:
    """最小 threat 假源(同 test_calibrated_r_fusion 模式):固定 first_seen,
    单源单组 → threat 顶层 conf 与组 conf 退化恒等,便于钉 asof 语义。"""

    name = "zz_asof_probe"
    fields = ("is_malicious",)
    authoritative_for = ()
    reliability = 0.9

    def __init__(self, first_seen):
        self._first_seen = first_seen

    def query(self, ip):
        return {"classification_type": "blacklist", "verdict": "malicious",
                "first_seen": self._first_seen}

    def health(self):
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


def _lookup_with(source, **kw):
    mp = pytest.MonkeyPatch()
    mp.setattr(reg, "_sources", [source])
    try:
        return reg.lookup("1.2.3.4", **kw)
    finally:
        mp.undo()


def test_lookup_asof_kwonly_and_default_none():
    src = FakeThreatSource(
        (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
    r = _lookup_with(src)                      # 不传 asof:现网默认路径
    assert r.asof is None
    assert "blacklist" in r.classifications    # 照常出分
    with pytest.raises(TypeError):             # asof 仅限关键字
        reg.lookup("1.2.3.4", None, 1.0)


def test_lookup_asof_anchors_group_and_threat_confidence():
    t0 = datetime.now(timezone.utc) - timedelta(days=100)
    src = FakeThreatSource(t0.isoformat())
    early = _lookup_with(src, asof=(t0 + timedelta(days=10)).timestamp())
    late = _lookup_with(src, asof=(t0 + timedelta(days=100)).timestamp())
    assert early.asof is not None and late.asof is not None
    ce = early.classifications["blacklist"].confidence
    cl = late.classifications["blacklist"].confidence
    assert ce > cl                              # 组级:近锚衰减更轻
    te = early.to_dict()["threat"]["confidence"]
    tl = late.to_dict()["threat"]["confidence"]
    assert te > tl                              # 顶层重融合同锚(F10 快照消费点)
    assert te == ce and tl == cl                # 单指控组退化恒等


def test_lookup_default_none_bit_identical_to_asof_wall(monkeypatch):
    """默认路径逐位护栏:e2e 层面 asof=None ≡ asof=同刻墙钟值。"""
    fixed = datetime(2026, 10, 14, 6, 0, 0, tzinfo=timezone.utc)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    src = FakeThreatSource((fixed - timedelta(days=45)).isoformat())
    monkeypatch.setattr(lo, "datetime", Frozen)
    r_default = _lookup_with(src)                        # asof=None → 冻结墙钟
    r_asof = _lookup_with(src, asof=fixed.timestamp())   # 显式同刻
    assert (r_default.classifications["blacklist"].confidence
            == r_asof.classifications["blacklist"].confidence)
    assert r_default.to_dict()["threat"] == r_asof.to_dict()["threat"]
