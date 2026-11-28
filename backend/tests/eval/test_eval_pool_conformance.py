# backend/tests/eval/test_eval_pool_conformance.py
"""评测面 × 生产池子对拍(返工评审 9,#523):同一个 LookupResult
(details 带 last_seen),四个评测面(metrics._effective_votes /
sinkhole_probe / agg_share / anchor_readouts)重算出的指控池逐项等于
生产 `threat_summary` 的池子。#523 改了池子布局(末位 last_seen)后,
「评测重算 = 生产」必须有单测钉住,不能只靠回放门的脚本镜像。"""
from datetime import datetime, timezone

from ipdb._eval.agg_share import corroboration_agg_share
from ipdb._eval.anchor_readouts import _group_accusers
from ipdb._eval.metrics import _effective_votes
from ipdb._eval.sinkhole_probe import sinkhole_probe
from ipdb._logodds import accuser_pool, asof_to_now, assertion_confidence
from ipdb._types import (ClassificationAssessment, EvidenceObservation,
                         LookupResult, MergedField)

ASOF = datetime(2026, 8, 2, tzinfo=timezone.utc).timestamp()
IP = "198.51.100.7"
CTYPE = "c2-server"


def _lookup_result(with_firehol: bool = False) -> LookupResult:
    obs_a = EvidenceObservation(source="threatfox", classification_type=CTYPE,
                                verdict="malicious", reliability=0.85,
                                first_seen="2026-01-01T00:00:00+00:00",
                                last_seen="2026-08-01T00:00:00+00:00")
    # 五改键源真实形状:fs 缺 + ls 有(#523)
    obs_b = EvidenceObservation(source="stopforumspam", classification_type=CTYPE,
                                verdict="malicious", reliability=0.70,
                                last_seen="2026-08-01T00:00:00+00:00")
    # 谱系去重敏感档(返工评审 9 变异的钩子):firehol(derived)系数
    # 夹在 threatfox 的 fs 时钟系数与 ls 时钟系数之间——评测面若丢了
    # last_seen,threatfox 按 fs 时钟变小,firehol 从「被去重摘除」翻成
    # 「保留」,池成员变化当场红(单看源列表对不上才有钳力)
    obs_c = EvidenceObservation(source="firehol", classification_type=CTYPE,
                                verdict="malicious", reliability=0.90,
                                first_seen="2026-05-26T00:00:00+00:00")
    from ipdb._merge import _assess_classification
    obs_list = [obs_a, obs_b]
    if with_firehol:
        obs_list.append(EvidenceObservation(
            source="firehol", classification_type=CTYPE,
            verdict="malicious", reliability=0.90,
            first_seen="2026-05-26T00:00:00+00:00"))
    ca = _assess_classification(obs_list, asof=ASOF)

    def _mf():
        return MergedField("N/A", 0, "voting", [])

    return LookupResult(ip=IP, country=_mf(), city=_mf(), asn=_mf(),
                        as_name=_mf(), ip_range=_mf(), is_isp=False,
                        classifications={CTYPE: ca}, asof=ASOF)


def _expected_pool(payload) -> list[tuple[str, float]]:
    ca = payload["classifications"][CTYPE]
    ents = [(d["source"], d["reliability"], d.get("first_seen"), CTYPE,
             d.get("last_seen"))
            for d in ca["details"] if d.get("verdict") in ("malicious", "suspicious")]
    return accuser_pool(ents, now=asof_to_now(ASOF))


def test_eval_faces_pools_match_threat_summary():
    r = _lookup_result()
    ts = r.threat_summary()
    payload = r.to_dict()
    expected = _expected_pool(payload)

    # 生产 threat_summary 置信度 = 手算池 σ(Σcoeff)
    assert ts["confidence"] == assertion_confidence([c for _, c in expected])

    # ① metrics._effective_votes:谱系去重后的池大小(snapshot 按 IP 键)
    assert _effective_votes({IP: payload}, IP, CTYPE) == len(expected)

    # ② anchor_readouts._group_accusers:池逐项同源同序;firehol 在
    # ls 时钟下被谱系去重摘除(threatfox 的 ls 时钟系数压过它),
    # 丢了 last_seen 就会翻回保留 —— 本断言是返工评审 9 变异的钉子
    assert _group_accusers(payload["classifications"][CTYPE], CTYPE)["pool"] \
        == [s for s, _ in expected]
    assert "firehol" not in [s for s, _ in expected]

    # ③ agg_share:corroborated 组计入且 accusers 非纯 derived;
    # derived_vote_share = 0/池大小 = 0.0(池非空才非 None,钉池大小 ≥1;
    # examples 只记纯 derived 互证组,本组非 derived 不进 examples)
    agg = corroboration_agg_share(lambda _ip: payload, [IP])
    assert agg["n_corroborated_groups"] == 1
    assert agg["derived_vote_share"] == 0.0
    assert agg["n_pure_derived_groups"] == 0
    assert agg["examples"] == []

    # ④ sinkhole_probe:polluted_sources 逐源 = 池源集(每 IP 一票)
    ranges = {"ip": [IP], "cidr": []}
    sh = sinkhole_probe(lambda _ip: payload, [IP], ranges=ranges)
    polluted = sh["polluted_sources"]
    assert set(polluted) == {s for s, _ in expected}
    for s, _ in expected:
        assert polluted[s]["hits"] == 1


def test_group_accusers_lineage_sensitive(monkeypatch):
    """返工评审 9 的谱系敏感档:_group_accusers 丢了 last_seen 时,
    threatfox 按 fs 时钟变小,夹在中间的 firehol(derived)从「被去重
    摘除」翻回「保留」,池成员变化当场红。anchor_readouts 本走墙钟,
    这里 monkeypatch 注入与生产同款 asof 锚(测的是条目形状不是钟)。"""
    import functools
    from ipdb._eval import anchor_readouts as ar
    from ipdb._logodds import asof_to_now
    monkeypatch.setattr(ar, "accuser_pool",
                        functools.partial(accuser_pool, now=asof_to_now(ASOF)))
    r = _lookup_result(with_firehol=True)
    payload = r.to_dict()
    expected = _expected_pool(payload)
    # 正确实现下 firehol 被 threatfox 的 ls 时钟系数压过而摘除;
    # 本断言同时保证夹层位置成立(去掉它变异就探不到池成员变化)
    assert "firehol" not in [s for s, _ in expected]
    assert ar._group_accusers(payload["classifications"][CTYPE], CTYPE)["pool"] \
        == [s for s, _ in expected]
