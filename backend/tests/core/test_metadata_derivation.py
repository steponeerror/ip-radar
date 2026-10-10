"""迁移护栏:三个中央 dict 无论字面量还是派生,必须等于旧值快照。
spec 2026-08-28 §5.1——三处权威修正(abuseipdb/proxyscrape 清空、
ipinfo_lite 补)被此快照锁死,防回退。SM-F1(2026-10-08):权威快照
修剪——幻影轴(is_malicious/is_hosting/is_mobile)删除,真轴归真生产者。"""
import ipdb._merge as m
import ipdb._registry as r

OLD_CATEGORIES = {
    "ipinfo_lite": "geo_asn", "iptoasn": "geo_asn", "cn_isp": "geo_asn",
    "geolite_city": "geo_asn",
    "threatfox": "threat", "otx": "threat", "otx_subscribed": "threat", "spamhaus": "threat",
    "blocklist_de": "threat", "emerging_threats": "threat", "ipsum": "threat",
    "firehol": "threat", "abuseipdb": "threat", "stopforumspam": "threat",
    "binarydefense": "threat", "tweetfeed": "threat", "urlhaus": "threat",
    "ciarm": "threat", "bruteforce": "threat", "greensnow": "threat",
    "dataplane": "threat", "dshield": "threat", "f3csystems": "threat",
    "reportedip": "threat",
    "siberkapan": "threat", "turris_greylist": "threat",
    "threatcluster": "threat", "drb_ra": "threat",
    "knock_knock": "threat", "rtbh": "threat",
    "ip2proxy": "asset", "tor_exits": "asset", "x4bnet_vpn": "asset",
    "proxyscrape": "asset", "infra_services": "asset", "cdn_edges": "asset",
    "hookzof": "asset", "thespeedx": "asset",
    "protonvpn": "asset", "nordvpn": "asset",
    "cloud_ranges": "asset",
    "dbip_city": "geo_asn",
    "danmeuk_tor": "asset",
    "root_servers": "asset",
    "dns_public": "asset",
    "rir_delegated": "geo_asn",
    "peeringdb": "asset",
    "caida_asorg": "geo_asn",      # b/asorg-anycast 2026-10-10
    "anycast_census": "asset",    # b/asorg-anycast 2026-10-10
}
OLD_RELIABILITY = {
    "ipinfo_lite": 0.95, "iptoasn": 0.90, "cn_isp": 0.85, "geolite_city": 0.85,
    "ip2proxy": 0.80, "tor_exits": 0.95, "x4bnet_vpn": 0.70, "ipsum": 0.55,
    "firehol": 0.50, "spamhaus": 0.90, "threatfox": 0.85, "blocklist_de": 0.65,
    "emerging_threats": 0.85, "otx": 0.55, "otx_subscribed": 0.6, "abuseipdb": 0.65,
    "stopforumspam": 0.60, "binarydefense": 0.65, "tweetfeed": 0.50,
    "urlhaus": 0.55, "ciarm": 0.60, "bruteforce": 0.60, "greensnow": 0.60,
    "dataplane": 0.70, "dshield": 0.70, "f3csystems": 0.60, "reportedip": 0.65,
    "proxyscrape": 0.50, "infra_services": 0.95, "cdn_edges": 0.95,
    "siberkapan": 0.60, "turris_greylist": 0.60, "threatcluster": 0.70,
    "knock_knock": 0.70, "rtbh": 0.70,
    "drb_ra": 0.50, "hookzof": 0.50, "thespeedx": 0.50,
    "protonvpn": 0.75, "nordvpn": 0.75,
    "cloud_ranges": 0.95,
    "dbip_city": 0.80,
    "danmeuk_tor": 0.85,
    "root_servers": 0.99,
    "dns_public": 0.90,
    "rir_delegated": 0.99,
    "peeringdb": 0.85,
    "caida_asorg": 0.8,            # b/asorg-anycast 2026-10-10
    "anycast_census": 0.9,         # b/asorg-anycast 2026-10-10
}
OLD_AUTHORITATIVE = {
    "is_proxy": ["ip2proxy"], "is_tor": ["tor_exits"], "is_vpn": ["x4bnet_vpn"],
    "service": ["infra_services", "cdn_edges", "root_servers", "dns_public"],
    "as_org": ["caida_asorg"], "is_anycast": ["anycast_census"],  # b/asorg-anycast 2026-10-10
}
# SM-F1 删除的幻影轴:is_malicious(threatfox/emerging_threats/spamhaus
# 声明但无证据键生产者)、is_hosting/is_mobile(ipinfo_lite 声明但只产
# geo/asn 槽;is_hosting 真生产者 ip2proxy/cloud_ranges 有意不扩面)。
_PHANTOM_AXES = ("is_malicious", "is_hosting", "is_mobile")

def test_categories_match_snapshot():
    # 47 = b/asorg-anycast 两源入册后实测 len(SOURCE_CATEGORIES)
    live = dict(r.SOURCE_CATEGORIES)
    assert live == OLD_CATEGORIES

def test_reliability_match_snapshot():
    # 公开源快照全等锁死(43 源口径)
    live = dict(m.SOURCE_RELIABILITY)
    assert live == OLD_RELIABILITY

def test_authoritative_match_snapshot():
    got = {k: sorted(v) for k, v in m.AUTHORITATIVE_SOURCES.items()}
    want = {k: sorted(v) for k, v in OLD_AUTHORITATIVE.items()}
    assert got == want
    for axis in _PHANTOM_AXES:     # SM-F1:幻影轴永久禁入(独立于快照逐位比对)
        assert axis not in got, f"phantom authority axis {axis!r} resurrected"

def test_reexport_identity():
    import ipdb
    assert ipdb.SOURCE_RELIABILITY is m.SOURCE_RELIABILITY
    assert ipdb.AUTHORITATIVE_SOURCES is m.AUTHORITATIVE_SOURCES
