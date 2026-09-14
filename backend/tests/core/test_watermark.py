# backend/tests/core/test_watermark.py
"""Watermark derivation tests (spec 2026-09-14-data-watermark §5.1)."""
import ipaddress

import pytest

from ipdb._watermark import (
    BATCH_SLOT_ZERO, CONFIRM_THRESHOLD, FAMILY_SIZE, MARK_GAMMA, N_MAX, N_MIN,
    WM_SEED_V1, canary_family, mark_hit, mark_value,
)


def test_constants_match_spec():
    assert FAMILY_SIZE == 500 and N_MIN == 150 and N_MAX == 400
    assert CONFIRM_THRESHOLD == 100 and MARK_GAMMA == 512
    assert BATCH_SLOT_ZERO == "00000000"


def test_family_deterministic_and_global():
    fam1, fam2 = canary_family(), canary_family()
    assert fam1 == fam2                       # same process (lru_cache) ...
    assert len(fam1) == FAMILY_SIZE
    assert len({c.ip for c in fam1}) == FAMILY_SIZE   # no duplicate IPs
    v6 = [c for c in fam1 if c.is_v6]
    assert len(v6) == 100 and len(fam1) - len(v6) == 400
    for c in fam1:
        addr = ipaddress.ip_address(c.ip)
        assert addr.is_global                 # never bogon (registry short-circuit)


def test_family_canary_semantics():
    for c in canary_family():
        assert c.ctype in ("scanner", "bruteforce", "proxy")
        assert 0.55 <= c.reliability <= 0.75
        assert c.first_seen.startswith("2025-") and c.last_seen


def test_mark_deterministic_and_format():
    s, e = 123456789, 123456792
    assert mark_hit(s, e) == mark_hit(s, e)   # pure function
    v = mark_value(s, e)
    assert v.startswith("ir-") and len(v) == 3 + 8   # ir-xxxxxxxx
    assert v == "ir-" + __import__("ipdb._watermark", fromlist=["_hmac"])._hmac(
        "mark", str(s), str(e))[8:12].hex()


def test_mark_gamma_hits_exist_in_sample():
    """扫一段 /32 空间必能找到命中与未命中——γ=1/512 不是 0 也不是 1。"""
    hits = [ip for ip in range(0x2D0A_0000, 0x2D0A_4000)
            if mark_hit(ip, ip)]
    assert 0 < len(hits) < 0x4000             # 16384 样本内 0<hits<全部
