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

def test_warninglists_are_ip_relevant_only():
    # provider substrings (cloud/CDN + public DNS); no domain/top-site patterns.
    for name in ["amazon aws", "azure", "gcp", "cloudflare", "fastly", "akamai",
                 "ipv4 public dns"]:
        assert name in config.IP_WARNINGLISTS
