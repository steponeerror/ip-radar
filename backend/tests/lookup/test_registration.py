"""registration 顶层信息块 + location.time_zone 旁路测试
(信息维度批 2026-10-10;geolite tz 同旁路族)。"""
import ipdb._registry as reg


class _Src:
    def __init__(self, name, city=None, cc=None, extra=None):
        self.name = name
        self.reliability = 0.5
        rec = {}
        if city:
            rec["city"] = city
        if cc:
            rec["country_code"] = cc
        if extra:
            rec["extra"] = extra
        self._rec = rec

    def query(self, ip):
        return [dict(self._rec)]

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


def _lookup_with(monkeypatch, sources):
    monkeypatch.setattr(reg, "_enabled_sources", lambda: sources)
    return reg.lookup("1.2.3.4")


def test_registration_block_assembled(monkeypatch):
    r = _lookup_with(monkeypatch, [
        _Src("rir_delegated",
             extra={"registry": "ripencc", "reg_country": "PS",
                    "alloc_date": "2007-11-26", "status": "allocated"})])
    assert r.registration == {"registry": "ripencc", "reg_country": "PS",
                              "alloc_date": "2007-11-26",
                              "status": "allocated"}
    d = r.to_dict()
    assert d["registration"]["registry"] == "ripencc"


def test_registration_partial_keys_and_absent(monkeypatch):
    r = _lookup_with(monkeypatch, [
        _Src("rir_delegated", extra={"registry": "arin",
                                     "status": "assigned"})])
    assert r.registration == {"registry": "arin", "status": "assigned"}
    r2 = _lookup_with(monkeypatch, [_Src("dbip_city", city="Lyon")])
    assert r2.registration is None


def test_registration_never_pollutes_country(monkeypatch):
    """reg_country ≠ 地理国:不进 country_code 融合(专线纪律)。"""
    r = _lookup_with(monkeypatch, [
        _Src("rir_delegated", cc=None,
             extra={"registry": "ripencc", "reg_country": "PS"}),
        _Src("dbip_city", city="Lyon", cc="FR")])
    assert r.country.value == "FR"


def test_location_carries_time_zone(monkeypatch):
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", city="Guangzhou",
             extra={"city_zh": "广州市", "lat": 23.13, "lon": 113.26,
                    "time_zone": "Asia/Shanghai"})])
    assert r.location == {"lat": 23.13, "lon": 113.26,
                          "time_zone": "Asia/Shanghai"}


def test_time_zone_without_latlon_no_location(monkeypatch):
    """无定位即无时区语义:tz 不独立成块(宁少算,不虚构定位)。"""
    r = _lookup_with(monkeypatch, [
        _Src("geolite_city", city="Anywhere",
             extra={"time_zone": "UTC"})])
    assert r.location is None
