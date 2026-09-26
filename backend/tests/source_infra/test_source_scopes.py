"""Task 2 (feat/key-source-sets): _registry 私源集 + 集合解析 + lookup/get_status 收窄。

resolve_allowed(None→启用非私源, list→原样)、private_source_names、
known_source_names(发现序、不含 internal)、lookup(allowed_sources=...)、
get_status(allowed=...)。spec §4 / Q10-A。
"""
import pytest

import ipdb._registry as R


@pytest.fixture
def fake_sources(monkeypatch):
    """两个假非私源 src_x/src_y,各对 1.2.3.4 出不同 country 值(归因各留
    一条);record 数 100/200,保证 get_status 子集和严格变小。
    模式照 tests/source_infra/test_registry_new.py 的 ensure_loaded fixture。"""
    from ipdb._types import SourceHealth

    class FakeSource:
        def __init__(self, name, country, records):
            self.name = name
            self.fields = ("country_code",)
            self._country = country
            self._records = records

        def health(self):
            return SourceHealth(
                name=self.name, loaded=True, record_count=self._records,
                last_updated="2026-06-12T00:00:00Z", is_stale=False)

        def query(self, ip):
            return {"country_code": self._country}

    monkeypatch.setattr(R, "_sources", [
        FakeSource("src_x", "XA", 100),
        FakeSource("src_y", "YB", 200),
    ])


def test_resolve_allowed_none_excludes_private(monkeypatch):
    monkeypatch.setattr(R, "_PRIVATE", frozenset({"priv_a"}))
    allowed = R.resolve_allowed(None)
    assert "priv_a" not in allowed


def test_resolve_allowed_explicit_keeps_private(monkeypatch):
    monkeypatch.setattr(R, "_PRIVATE", frozenset({"priv_a"}))
    assert R.resolve_allowed(["priv_a", "nope"]) == frozenset({"priv_a", "nope"})


def test_lookup_allowed_filters_attribution(fake_sources):
    full = R.lookup("1.2.3.4")
    cut = R.lookup("1.2.3.4", allowed_sources=frozenset({"src_x"}))
    srcs = {a.source for a in cut.country.sources}
    assert srcs <= {"src_x"} and len(full.country.sources) > len(cut.country.sources)


def test_get_status_allowed_sums_subset(fake_sources):
    full = R.get_status()
    cut = R.get_status(allowed=frozenset({"src_x"}))
    assert cut["total_records"] < full["total_records"]


def test_known_source_names_excludes_internal(fake_sources):
    names = R.known_source_names()
    assert names and set(names).isdisjoint(R._INTERNAL_NAMES)
