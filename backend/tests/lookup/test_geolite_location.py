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


def test_matched_geolite_without_extra_no_location(monkeypatch):
    """首个值匹配即 break 的边界(#315 规格 §3 T1):geolite 值==胜值
    但收集时 extra 空(未入 stash)→ location None;读出既不虚构坐标,
    也不再回退看别的源。"""
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", "Lyon", extra=None, reliability=0.9),
        _Src("dbip_city", "Lyon", reliability=0.3)])
    assert r.city.value == "Lyon"
    assert r.location is None


def test_geolite_losing_city_value_no_location(monkeypatch):
    """值≠胜值的 geolite 源不触发读出匹配(匹配条件 = 源名+值双等)。
    注:geolite_city 在 SOURCE_RELIABILITY 有生产 r(对 _Src 构造参数免疫),
    用两枚未登记假源同投 Guangzhou(Σ=1.0)压过其单独一票。"""
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", "Foshan",
             extra={"lat": 23.02, "lon": 113.12}),
        _Src("aaa_geo", "Guangzhou"),
        _Src("bbb_geo", "Guangzhou")])
    assert r.city.value == "Guangzhou"
    assert r.location is None
