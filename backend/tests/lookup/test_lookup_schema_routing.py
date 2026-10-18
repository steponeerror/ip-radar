# backend/test_lookup_schema_routing.py
"""lookup() routes fields by the declared SCALAR_SLOTS schema, not a hardcoded
tuple. Verified behaviorally: a source emitting country_code has it flow
source.query -> route_record -> field_values -> country_code strategy ->
LookupResult.country.

The isp slot was removed (spec 2026-08-19 §4.1 D3): no strategy ever consumed it, and its
only emitter (proxyscrape) now rides carrier. Stale stored "isp" keys fold
into extra until the next rebuild.
"""
from ipdb._evidence import SCALAR_SLOTS, route_record


def test_lookup_routes_scalar_slot_to_result(monkeypatch):
    """A source emitting a SCALAR_SLOTS field must reach LookupResult via the
    schema router -- exercise the real lookup() path, not source-text inspection."""
    from ipdb import _registry
    from ipdb._types import SourceHealth

    class FakeSrc:
        name = "fake"
        reliability = 0.5
        authoritative_for = []
        fields = ("country_code",)

        def health(self):
            return SourceHealth("fake", True, 1, None, False)

        def query(self, ip):
            return {"country_code": "US"}

    monkeypatch.setattr(_registry, "_sources", [FakeSrc()])
    monkeypatch.setattr(_registry, "_disabled", set())

    import ipdb._registry as R
    lr = R.lookup("1.2.3.4")

    # country_code routed end-to-end to the merged result (would be "N/A" if
    # lookup stopped collecting SCALAR_SLOTS fields).
    assert lr.country.value == "US"
    # isp slot removed (spec 2026-08-19 §4.1 D3): values ride carrier now; stale stored
    # "isp" keys fold into extra until the next rebuild.
    assert "isp" not in SCALAR_SLOTS
    assert "country_code" in SCALAR_SLOTS


def test_as_domain_is_asset_slot():
    """as_domain rides the asset schema (string value like carrier); ipinfo_lite
    stores it per-node and lookup routes it without bespoke code (spec 2026-08-19 §4.2 D5/Q7-A)."""
    from ipdb._evidence import ASSET_SLOTS
    assert "as_domain" in ASSET_SLOTS


def test_route_record_keeps_abuse_contact_at_top_level():
    """abuse_contact 是类 3 所有权与联系标量槽(rir_abuse,2026-10-18):
    route_record 后留在顶层、不落 extra——lookup 的 SCALAR_SLOTS 收集才看得见。"""
    raw = {"country_code": "NL", "abuse_contact": "abuse@ripe.net"}
    out = route_record(raw)
    assert out["abuse_contact"] == "abuse@ripe.net"          # stays top level
    assert "abuse_contact" not in (out.get("extra") or {})    # NOT folded into extra
    assert "abuse_contact" in SCALAR_SLOTS


def test_lookup_routes_abuse_contact_to_merged_field(monkeypatch):
    """abuse_contact per-IP 标量,同 country_code 路径(无 join 钩子):
    source.query → route_record → SCALAR_SLOTS 收集 → NamingAuthority →
    LookupResult.abuse_contact(单证人 conf=r 公理)。"""
    from ipdb import _registry
    from ipdb._types import SourceHealth

    class FakeSrc:
        name = "fake_rir"
        reliability = 0.85
        authoritative_for = []
        fields = ("abuse_contact",)

        def health(self):
            return SourceHealth("fake_rir", True, 1, None, False)

        def query(self, ip):
            return {"abuse_contact": "abuse@ripe.net"}

    monkeypatch.setattr(_registry, "_sources", [FakeSrc()])
    monkeypatch.setattr(_registry, "_disabled", set())
    import ipdb._merge as _merge
    monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"fake_rir": 0.85})

    import ipdb._registry as R
    lr = R.lookup("1.2.3.4")

    assert lr.abuse_contact is not None
    assert lr.abuse_contact.value == "abuse@ripe.net"
    assert lr.abuse_contact.confidence == 85       # int(0.85*100+0.5)
    assert lr.abuse_contact.algorithm == "authority"
    assert lr.abuse_contact.sources[0].source == "fake_rir"


def test_route_record_keeps_org_name_at_top_level():
    """org_name 是注册组织名标量槽(rir_abuse 扩展 2026-10-18):
    route_record 后留在顶层、不落 extra——lookup 的 SCALAR_SLOTS 收集才看得见。"""
    raw = {"country_code": "NL", "org_name": "Nederlandse Spoorwegen"}
    out = route_record(raw)
    assert out["org_name"] == "Nederlandse Spoorwegen"          # stays top level
    assert "org_name" not in (out.get("extra") or {})    # NOT folded into extra
    assert "org_name" in SCALAR_SLOTS


def test_lookup_routes_org_name_to_merged_field(monkeypatch):
    """org_name per-IP 标量,同 country_code 路径(无 join 钩子):
    source.query → route_record → SCALAR_SLOTS 收集 → NamingAuthority →
    LookupResult.org_name(单证人 conf=r 公理)。"""
    from ipdb import _registry
    from ipdb._types import SourceHealth

    class FakeSrc:
        name = "fake_rir"
        reliability = 0.85
        authoritative_for = []
        fields = ("org_name",)

        def health(self):
            return SourceHealth("fake_rir", True, 1, None, False)

        def query(self, ip):
            return {"org_name": "RIPE Network Coordination Center"}

    monkeypatch.setattr(_registry, "_sources", [FakeSrc()])
    monkeypatch.setattr(_registry, "_disabled", set())
    import ipdb._merge as _merge
    monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"fake_rir": 0.85})

    import ipdb._registry as R
    lr = R.lookup("1.2.3.4")

    assert lr.org_name is not None
    assert lr.org_name.value == "RIPE Network Coordination Center"
    assert lr.org_name.confidence == 85       # int(0.85*100+0.5)
    assert lr.org_name.algorithm == "authority"
    assert lr.org_name.sources[0].source == "fake_rir"
    # to_dict 恒写键、缺证出 null(同 as_org/abuse_contact 出海契约)
    d = lr.to_dict()
    assert d["org_name"]["value"] == "RIPE Network Coordination Center"
