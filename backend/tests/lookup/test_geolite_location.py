"""geolite lat/lon plumbing: per-source extra.lat/lon → LookupResult.location
(display-only 旁路,同 city_zh;spec 2026-08-25 §4.2)。"""
import ipdb._registry as reg


class _Src:
    def __init__(self, name, city, extra=None, reliability=0.5, cc="CN"):
        self.name = name
        self.reliability = reliability
        self._rec = {"city": city, "country_code": cc}
        if extra:
            self._rec["extra"] = extra

    def query(self, ip):
        return [dict(self._rec)]

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


def _lookup_with(monkeypatch, sources):
    monkeypatch.setattr(reg, "_enabled_sources", lambda: sources)
    return reg.lookup("1.2.3.4")


def test_geolite_winner_carries_location(monkeypatch):
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", "Guangzhou",
             extra={"city_zh": "广州市", "lat": 23.13, "lon": 113.26,
                    "accuracy_radius": 50}, reliability=0.85)])
    assert r.location == {"lat": 23.13, "lon": 113.26, "accuracy_radius": 50}
    assert r.to_dict()["location"] == {"lat": 23.13, "lon": 113.26,
                                       "accuracy_radius": 50}


def test_location_without_accuracy_radius(monkeypatch):
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", "Lyon", extra={"lat": 45.76, "lon": 4.84})])
    assert r.location == {"lat": 45.76, "lon": 4.84}


def test_non_geolite_city_source_no_location(monkeypatch):
    """坐标仅 geolite 产;其他源 city 胜出时无坐标(不虚构)。"""
    r = _lookup_with(monkeypatch, [
        _Src("proxyscrape", "Guangzhou", reliability=0.9)])
    assert r.location is None
