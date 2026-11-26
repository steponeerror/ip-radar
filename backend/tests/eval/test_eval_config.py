# backend/test_eval_config.py
from ipdb._eval import config

def test_thresholds_present_and_typed():
    assert config.THRESHOLDS["MC"] == 0.02
    assert config.THRESHOLDS["CG"] == 5
    assert config.THRESHOLDS["conflict"] == 3
    assert config.THRESHOLDS["fp"] == 0.05
    assert config.THRESHOLDS["other"] == 0.50

def test_n_floor_and_oc_threshold():
    assert config.N_FLOOR == 20
    assert config.OC_SUSPICION == 0.70

def test_lineage_clusters_cover_derived_sources():
    # LINEAGE_CLUSTERS（模型事件层/告警过滤的声明谱系）与生产
    # DERIVED_SOURCES 一致；计数器已改用生产 dedup_lineage(D5/B3)。
    from ipdb._logodds import DERIVED_SOURCES
    for s in DERIVED_SOURCES:
        assert config.LINEAGE_CLUSTERS.get(s), f"{s} missing from LINEAGE_CLUSTERS"


def test_republishes_closure_covers_production_anchors():
    """#464 卡2上半一致性钉:生产 LINEAGE_ANCHORS(registry 按
    republishes 类属性灌装)的每一对都在评测转载闭包里——计分与评测读
    同一份声明,任一边漂移即红。预期声明面按 2026-11-26 生产镜像全库
    扫描冻结(dev/arch-r4-scan/scan_step3.json pairs_contained;
    firehol→greensnow 沿 grill Q2 2026-10-11 判例,实测数字见各源类注)。"""
    import ipdb._logodds as lo
    from ipdb._eval.events import same_republish_chain
    expected = {
        "emerging_threats": ("spamhaus",),
        "ustc_blackip": ("spamhaus", "emerging_threats"),
        "x4bnet_vpn": ("protonvpn",),
        "danmeuk_tor": ("tor_exits",),
        "firehol": ("greensnow",),
    }
    assert lo.LINEAGE_ANCHORS == expected     # 声明面冻结(mutation ① 钉)
    for target, anchors in lo.LINEAGE_ANCHORS.items():
        for a in anchors:
            assert same_republish_chain(target, a), (target, a)
    # 不同链之间仍独立(闭包不把所有声明并成一簇)
    assert not same_republish_chain("spamhaus", "greensnow")
    assert not same_republish_chain("protonvpn", "tor_exits")

def test_warninglists_are_ip_relevant_only():
    # provider substrings (cloud/CDN + public DNS); no domain/top-site patterns.
    for name in ["amazon aws", "azure", "gcp", "cloudflare", "fastly", "akamai",
                 "ipv4 public dns"]:
        assert name in config.IP_WARNINGLISTS
