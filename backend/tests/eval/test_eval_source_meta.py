# 源元数据契约(S21/S33,2026-10-14 eval-loop phase1 Task 3):
# 每 threat 源必须声明 provenance_tier(A 官方/自采 | B 社区 | C 聚合派生)
# 与 honeypot_methodology(蜜罐法采集);Task 8 读侧用它们做
# k_all/k_nonhoneypot 双报告与 scorecard 谱系列。
import pytest

from ipdb import _registry
from ipdb._eval import config

# 判例对拍表(S21 裁决;未列出 = 基类默认 B)。feodo 已于 2026-03 退役
# (tests/core/test_no_feodo_residue.py 守卫),A 名单无对应类可落属性。
TIER_PRECEDENTS = {
    "threatfox": "A",
    "spamhaus": "A",
    "emerging_threats": "A",
    "abuseipdb": "A",
    "root_servers": "A",
    "dns_public": "A",
    "tor_exits": "A",
    "firehol": "C",
    "ipsum": "C",
    "otx": "C",
    "otx_subscribed": "C",
    "greensnow": "C",
    "drb_ra": "C",
    "ciarm": "B",
}

HONEYPOT_SOURCES = ("knock_knock", "binarydefense", "sblam")


def _threat_sources():
    return [s for s in _registry._sources if s.category == "threat"]


def test_threat_sources_declare_valid_provenance_tier():
    threat = _threat_sources()
    assert threat, "registry discovered no threat sources"
    for s in threat:
        assert getattr(s, "provenance_tier", "") in ("A", "B", "C"), (
            f"{s.name}: provenance_tier missing or invalid")


def test_honeypot_methodology_sources_flag_true():
    by_name = {s.name: s for s in _threat_sources()}
    for name in HONEYPOT_SOURCES:
        assert by_name[name].honeypot_methodology is True, name


def test_tier_precedents_match():
    # 机械对拍:类目表 vs 源类属性(含 asset 类 tor_exits/root_servers/dns_public)
    by_name = {s.name: s for s in _registry._sources}
    for name, tier in TIER_PRECEDENTS.items():
        assert by_name[name].provenance_tier == tier, (
            f"{name}: expected {tier}, got {by_name[name].provenance_tier!r}")


def test_config_honeypot_fallback_set():
    # k 排除集兜底:源声明优先,config 收敛漏报(读侧合并语义)
    assert config.HONEYPOT_METHODOLOGY == set(HONEYPOT_SOURCES)
