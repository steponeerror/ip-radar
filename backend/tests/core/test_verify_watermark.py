# backend/tests/core/test_verify_watermark.py
"""Verifier tests (spec §5.4): detect() core + probe_data_dir round-trip."""
import random
from pathlib import Path

from ipdb._watermark import canary_family
from ipdb._sources.canary import CanarySource
from scripts.verify_watermark import detect, probe_data_dir


class _FixedRng:
    def randrange(self, lo, hi):
        return 250
    def sample(self, pop, k):
        return list(pop)[:k]


def _obs(ip, source="sentinel", ctype="scanner", verdict="suspicious"):
    return [{"source": source, "classification_type": ctype,
             "verdict": verdict}]


def test_detect_confirmed_partial_none():
    fam = canary_family()
    full = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam}
    r = detect(lambda ip: full.get(ip) or [])
    assert r["hits"] == 500 and r["verdict"] == "CONFIRMED"
    half = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam[:150]}
    r = detect(lambda ip: half.get(ip) or [])
    assert r["hits"] == 150 and r["verdict"] == "CONFIRMED"   # threshold=100
    few = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam[:50]}
    r = detect(lambda ip: few.get(ip) or [])
    assert r["hits"] == 50 and r["verdict"] == "PARTIAL"
    assert detect(lambda ip: [])["verdict"] == "NOT_DETECTED"


def test_detect_rejects_wrong_triples():
    fam = canary_family()
    wrong_ctype = {c.ip: _obs(c.ip, ctype="tor") for c in fam}      # 类型不符
    wrong_src = {c.ip: _obs(c.ip, source="blocklist_de") for c in fam}
    mal = {c.ip: _obs(c.ip, ctype=c.ctype, verdict="malicious") for c in fam}
    assert detect(lambda ip: wrong_ctype[ip])["hits"] == 0
    assert detect(lambda ip: wrong_src[ip])["hits"] == 0
    assert detect(lambda ip: mal[ip])["hits"] == 0


def test_probe_data_dir_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(random, "SystemRandom", _FixedRng)
    CanarySource(tmp_path).rebuild()
    r = probe_data_dir(Path(tmp_path))
    assert r["layer1"]["hits"] == 250
    assert r["layer1"]["verdict"] == "CONFIRMED"
    assert r["layer2"]["invalid"] == 0            # 无假标记 → invalid 必 0
