# backend/tests/source_infra/test_canary_source.py
"""CanarySource tests (spec §5.2)."""
import random

from ipdb._validate import metadata_problems
from ipdb._watermark import canary_family
from ipdb._sources.canary import CanarySource


class _FixedRng:
    """SystemRandom 替身:randrange 恒 250,sample 取前 k 个。"""
    def randrange(self, lo, hi):
        return 250
    def sample(self, pop, k):
        return list(pop)[:k]


def test_metadata_contract_clean(tmp_path):
    assert metadata_problems(CanarySource(tmp_path)) == []


def test_download_is_noop_and_offline(tmp_path):
    src = CanarySource(tmp_path)
    src.download()                     # no-op, no network, no file created
    assert not (tmp_path / "sentinel").exists()
    assert src.download_host is None


def test_rebuild_embeds_n_and_evidence_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr(random, "SystemRandom", _FixedRng)
    src = CanarySource(tmp_path)
    n = src.rebuild()
    assert n == 250
    src.load()
    # FixedRng.sample 取前 250 → family[:250] 全部可查
    for c in list(canary_family())[:3]:
        ev = src.query(c.ip)[0]
        assert ev["verdict"] == "suspicious"
        assert ev["classification_type"] == c.ctype
        assert ev["reliability"] == c.reliability
        assert ev["extra"]["batch_id"] == "00000000"    # B 期零槽
    # family[250:] 未嵌入
    assert src.query(canary_family()[300].ip) in (None, {}, [])


def test_health_loaded_reflects_real_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(random, "SystemRandom", _FixedRng)
    src = CanarySource(tmp_path)
    h0 = src.health()
    assert h0.loaded is False and h0.is_stale is False    # F2: 未建→未载入
    src.rebuild(); src.load()
    h1 = src.health()
    assert h1.loaded is True and h1.record_count == 250 and h1.is_stale is False
