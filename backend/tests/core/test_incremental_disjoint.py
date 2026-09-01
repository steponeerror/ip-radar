"""Incremental disjoint pre-check in rebuild_lmdb (2026-09-01).

Invariants:
- sorted disjoint input  → pre-check clean → O(n) post-scan SKIPPED, flag 1
- unsorted disjoint input → pre-check false-positive → post-scan decides, flag 1
- truly nested input      → flag 0 (either path)
The pre-check never misses a real overlap (the later-inserted member of an
overlapping pair always starts at/below the running max end), so a clean run
proves disjointness without the scan.
"""
from ipdb._sources._lmdb import rebuild_lmdb, detect_disjoint, lookup
from ipdb._sources._lmdb import encode_key
from pathlib import Path
import lmdb


def _flag(tmp_path, records, name):
    base = tmp_path / f"{name}.lmdb"
    envs = []
    rebuild_lmdb(records, base, envs.append)
    sidecar = Path(f"{base}.disjoint").read_text().split()
    return int(sidecar[1]), envs[0]


def test_sorted_disjoint_skips_postscan(tmp_path, monkeypatch):
    import ipdb._sources._lmdb as m
    calls = {"n": 0}
    real = m.detect_disjoint
    def counting(env):
        calls["n"] += 1
        return real(env)
    monkeypatch.setattr(m, "detect_disjoint", counting)
    flag, _ = _flag(tmp_path, [("1.0.0.0/24", {}), ("1.0.1.0/24", {}),
                               ("9.9.9.0/24", {})], "sorted")
    assert flag == 1
    assert calls["n"] == 0, "clean pre-check must skip the O(n) scan"


def test_unsorted_disjoint_scan_confirms(tmp_path, monkeypatch):
    import ipdb._sources._lmdb as m
    calls = {"n": 0}
    real = m.detect_disjoint
    def counting(env):
        calls["n"] += 1
        return real(env)
    monkeypatch.setattr(m, "detect_disjoint", counting)
    # [10,20] before [5,7]: insertion-order check trips (5 <= 20), key order is disjoint
    flag, _ = _flag(tmp_path, [("10.0.0.0/32", {"v": 1}),
                               ("10.0.0.20/32", {"v": 1}),
                               ("10.0.0.5/32", {"v": 2})], "unsorted")
    assert flag == 1
    assert calls["n"] == 1, "flagged input must run the exact scan — and it says disjoint"


def test_nested_input_flags_not_disjoint(tmp_path):
    flag, env = _flag(tmp_path, [("1.0.0.0/16", {"v": "p"}),
                                 ("1.0.1.0/24", {"v": "c"})], "nested")
    assert flag == 0
    # and the nested env serves LPM via prefix probing (1.0.1.1 = 0x01000101)
    assert lookup(env, 0x01000101) == {"v": "c"}
    env.close()
