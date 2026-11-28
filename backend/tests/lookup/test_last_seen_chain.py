# backend/tests/lookup/test_last_seen_chain.py
"""last_seen query-path chain (spec 2026-08-19 §4.2 D4): to_observation collects it, the
per-observation details dict carries it. Several sources already emit it into
storage (abuseipdb/tor_exits/threatfox/f3csystems/dataplane/reportedip/
urlhaus) — these tests pin the read side only; the list is illustrative,
not a census."""
from ipdb._types import EvidenceObservation
from ipdb._merge import to_observation, _assess_classification


def test_to_observation_collects_last_seen():
    raw = {"first_seen": "2026-01-01T00:00:00+00:00", "last_seen": "2026-08-01T00:00:00+00:00"}
    obs = to_observation("threatfox", raw, classification_type="c2-server",
                         verdict="malicious", reliability=0.85)
    assert obs.last_seen == "2026-08-01T00:00:00+00:00"


def test_details_dict_carries_last_seen():
    obs = EvidenceObservation(source="threatfox", classification_type="c2-server",
                              reliability=0.85, last_seen="2026-08-01")
    ca = _assess_classification([obs])
    assert ca.details[0]["last_seen"] == "2026-08-01"


def test_details_dict_omits_absent_last_seen():
    obs = EvidenceObservation(source="threatfox", classification_type="c2-server",
                              reliability=0.85)
    ca = _assess_classification([obs])
    assert "last_seen" not in ca.details[0]


def test_threat_summary_pool_uses_last_seen_hand_calc():
    """返工评审 4:生产缝合处(asof 固定、details 带 last_seen)——
    threat_summary 的池子逐项等于手算:_merge 组级与 _types 顶层重融合
    都走 accuser_pool,池条目 = (source, reliability, first_seen, ctype,
    last_seen),时钟按「较晚的时间」(返工裁决);五个改键源的真实形状
    (fs 缺 + ls 有)与双时间源同场。池子本身用同一条目序列手算对拍。"""
    from datetime import datetime, timezone
    from ipdb._logodds import (accuser_pool, asof_to_now, assertion_confidence,
                               coefficient, logit)
    from ipdb._merge import _ACCUSING
    from ipdb._types import LookupResult
    from ipdb._types import MergedField

    asof = datetime(2026, 8, 2, tzinfo=timezone.utc).timestamp()
    def _mf():
        return MergedField("N/A", 0, "voting", [])

    obs_a = EvidenceObservation(source="threatfox", classification_type="c2-server",
                                verdict="malicious", reliability=0.85,
                                first_seen="2026-01-01T00:00:00+00:00",
                                last_seen="2026-08-01T00:00:00+00:00")
    obs_b = EvidenceObservation(source="stopforumspam", classification_type="c2-server",
                                verdict="malicious", reliability=0.70,
                                last_seen="2026-08-01T00:00:00+00:00")   # 五改键源真实形状:fs 缺
    ca = _assess_classification([obs_a, obs_b], asof=asof)

    r = LookupResult(ip="1.2.3.4", country=_mf(), city=_mf(), asn=_mf(),
                     as_name=_mf(), ip_range=_mf(), is_isp=False,
                     classifications={"c2-server": ca}, asof=asof)
    ts = r.threat_summary()

    # 手算池:同一条目序列(含末位 last_seen),同锚刻
    ents = [(d["source"], d["reliability"], d.get("first_seen"), "c2-server",
             d.get("last_seen"))
            for d in ca.details if d.get("verdict") in _ACCUSING]
    pool = accuser_pool(ents, now=asof_to_now(asof))
    assert len(pool) == 2
    now = asof_to_now(asof)
    # threatfox:双时间取较晚(ls)→ 龄 1d;stopforumspam:fs 缺按 ls → 龄 1d
    assert pool[0] == ("stopforumspam", coefficient(0.70, None, "c2-server",
                                                    now=now, last_seen="2026-08-01T00:00:00+00:00"))
    assert pool[1] == ("threatfox", logit(0.85) * 2 ** (-1 / 60))
    # 生产 threat_summary 的置信度 = 手算池的 σ(Σcoeff)
    assert ts["confidence"] == assertion_confidence([c for _, c in pool])
