# backend/ipdb/_watermark.py
"""Lineage watermark derivation (spec: docs/superpowers/specs/2026-09-14-data-watermark-design.md).

Pure functions, zero I/O. The seed is PUBLIC by design (Kerckhoffs /
decision #4): detection is universal; the security property is
removal-cost > rebuild-cost, not secrecy. Silent disclosure (decision #10):
never mention this module in README/CHANGELOG/release notes.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac as _hmac_mod
import ipaddress
from functools import lru_cache
from typing import NamedTuple

WM_SEED_V1 = b"ipradar-lineage-v1::9f27a4c1e83b5d06"   # fixed forever

FAMILY_SIZE = 500          # probe family: 400 v4 /32 + 100 v6 /128
N_MIN, N_MAX = 150, 400    # per-rebuild embed count (F6: >=33% delete margin)
CONFIRM_THRESHOLD = 100    # family hits >= this -> CONFIRMED
MARK_GAMMA = 512           # 1-in-512 records carry ingest_ref
BATCH_SLOT_ZERO = "00000000"   # B-phase instance slot, zero until enabled

_CTYPES = ("scanner", "bruteforce", "proxy")


def _hmac(label: str, *parts: str) -> bytes:
    msg = "|".join((label, *parts)).encode()
    return _hmac_mod.new(WM_SEED_V1, msg, hashlib.sha256).digest()


class CanaryIP(NamedTuple):
    ip: str
    is_v6: bool
    ctype: str
    reliability: float
    first_seen: str
    last_seen: str


def _family_entry(i: int) -> CanaryIP:
    h = _hmac("canary", str(i))
    v6 = i % 5 == 4
    while True:
        addr = (ipaddress.IPv6Address(int.from_bytes(h[:16], "big")) if v6
                else ipaddress.IPv4Address(int.from_bytes(h[:4], "big")))
        if addr.is_global:
            break
        h = _hmac_mod.new(WM_SEED_V1, h, hashlib.sha256).digest()
    days = h[16] % 214   # plan-defect fix (controller ruling): keep 2025 anchor
    ts = (_dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc)
          + _dt.timedelta(days=days)).isoformat()
    return CanaryIP(
        ip=str(addr), is_v6=v6,
        ctype=_CTYPES[h[17] % 3],
        reliability=round(0.55 + (h[18] % 21) / 100, 2),
        first_seen=ts, last_seen=ts)


@lru_cache(maxsize=1)
def canary_family() -> tuple[CanaryIP, ...]:
    return tuple(_family_entry(i) for i in range(FAMILY_SIZE))


def mark_hit(start_int: int, end_int: int) -> bool:
    return (int.from_bytes(
        _hmac("mark", str(start_int), str(end_int))[:8], "big")
        % MARK_GAMMA == 0)


def mark_value(start_int: int, end_int: int) -> str:
    return "ir-" + _hmac("mark", str(start_int), str(end_int))[8:12].hex()
