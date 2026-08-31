"""迁移护栏:三个中央 dict 无论字面量还是派生,必须等于旧值快照。
spec 2026-08-28 §5.1——三处权威修正(abuseipdb/proxyscrape 清空、
ipinfo_lite 补)被此快照锁死,防回退。"""
import ipdb._merge as m
import ipdb._registry as r

OLD_CATEGORIES = {
    "ipinfo_lite": "geo_asn", "iptoasn": "geo_asn", "cn_isp": "geo_asn",
    "geolite_city": "geo_asn",
    "threatfox": "threat", "otx": "threat", "spamhaus": "threat",
    "blocklist_de": "threat", "emerging_threats": "threat", "ipsum": "threat",
    "firehol": "threat", "abuseipdb": "threat", "stopforumspam": "threat",
    "binarydefense": "threat", "tweetfeed": "threat", "urlhaus": "threat",
    "ciarm": "threat", "bruteforce": "threat", "greensnow": "threat",
    "dataplane": "threat", "dshield": "threat", "f3csystems": "threat",
    "reportedip": "threat",
    "siberkapan": "threat", "turris_greylist": "threat",
    "threatcluster": "threat", "drb_ra": "threat",
    "ip2proxy": "asset", "tor_exits": "asset", "x4bnet_vpn": "asset",
    "proxyscrape": "asset", "infra_services": "asset", "cdn_edges": "asset",
    "hookzof": "asset", "thespeedx": "asset",
    "protonvpn": "asset", "nordvpn": "asset",
}
OLD_RELIABILITY = {
    "ipinfo_lite": 0.95, "iptoasn": 0.90, "cn_isp": 0.85, "geolite_city": 0.85,
    "ip2proxy": 0.80, "tor_exits": 0.95, "x4bnet_vpn": 0.70, "ipsum": 0.55,
    "firehol": 0.50, "spamhaus": 0.90, "threatfox": 0.85, "blocklist_de": 0.65,
    "emerging_threats": 0.85, "otx": 0.55, "abuseipdb": 0.65,
    "stopforumspam": 0.70, "binarydefense": 0.65, "tweetfeed": 0.50,
    "urlhaus": 0.55, "ciarm": 0.60, "bruteforce": 0.60, "greensnow": 0.60,
    "dataplane": 0.70, "dshield": 0.70, "f3csystems": 0.60, "reportedip": 0.65,
    "proxyscrape": 0.50, "infra_services": 0.95, "cdn_edges": 0.95,
    "siberkapan": 0.60, "turris_greylist": 0.60, "threatcluster": 0.70,
    "drb_ra": 0.50, "hookzof": 0.50, "thespeedx": 0.50,
    "protonvpn": 0.75, "nordvpn": 0.75,
}
OLD_AUTHORITATIVE = {
    "is_proxy": ["ip2proxy"], "is_tor": ["tor_exits"], "is_vpn": ["x4bnet_vpn"],
    "is_malicious": ["threatfox", "emerging_threats", "spamhaus"],
    "is_hosting": ["ipinfo_lite"], "is_mobile": ["ipinfo_lite"],
    "service": ["infra_services", "cdn_edges"],
}

def test_categories_match_snapshot():
    assert r.SOURCE_CATEGORIES == OLD_CATEGORIES

def test_reliability_match_snapshot():
    assert dict(m.SOURCE_RELIABILITY) == OLD_RELIABILITY

def test_authoritative_match_snapshot():
    got = {k: sorted(v) for k, v in m.AUTHORITATIVE_SOURCES.items()}
    want = {k: sorted(v) for k, v in OLD_AUTHORITATIVE.items()}
    assert got == want

def test_reexport_identity():
    import ipdb
    assert ipdb.SOURCE_RELIABILITY is m.SOURCE_RELIABILITY
    assert ipdb.AUTHORITATIVE_SOURCES is m.AUTHORITATIVE_SOURCES
