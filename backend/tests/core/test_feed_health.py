from dataclasses import asdict
import ipdb._types as t
from ipdb._api_models import SourceHealthOut

def test_source_health_feeds_default_none():
    h = t.SourceHealth(name="x", loaded=True, record_count=1,
                       last_updated=None, is_stale=False)
    assert h.feeds is None
    assert "feeds" not in asdict(h) or asdict(h)["feeds"] is None

def test_source_health_feeds_roundtrip():
    h = t.SourceHealth(name="cloud_ranges", loaded=True, record_count=1,
                       last_updated=None, is_stale=True,
                       feeds=[t.FeedHealth(name="Azure", last_updated="2026-10-01T00:00:00Z", is_stale=True)])
    d = asdict(h)
    assert d["feeds"][0]["name"] == "Azure"

def test_api_model_serializes_feeds():
    out = SourceHealthOut(name="x", loaded=True, record_count=0, last_updated=None,
                          is_stale=False, covered_ips=0, covered_v6_nets=0,
                          feeds=[{"name": "AWS", "last_updated": None, "is_stale": False}])
    assert out.model_dump()["feeds"][0]["name"] == "AWS"
