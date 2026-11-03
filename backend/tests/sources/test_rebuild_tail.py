"""#291 rebuild 收尾共享件(_sources/_rebuild_tail)测试面。

Seam = 共享件公开面 + 三车道接线钉子:
- InfraNoiseGate:enabled 判定(源 opt-in × 总开关)/命中记账(str(net)
  明文,宁少算只排 curated 单址)/flush 留痕(去重计数进 rebuild 日志,
  单/双遍 harvest 的重复记账靠 log 端去重吸收——A 车道注释既有契约);
- covered_counts:B/C 预扫描覆盖数 v4/v6 分流(worked example 独立算例,
  v6 count-as-1;A 车道不经此处 = covered=Auto 写库循环内统计);
- 三车道接线钉子:spy 换入各车道基类模块的共享件名,证明 rebuild 确实
  路由到共享件(「同一段过滤+记账逻辑只存在一份」的行为面验收;
  字节级一致由 #291 基线对照另证)。
"""
import ipaddress
import logging
from pathlib import Path

import pytest

from ipdb._sources._rebuild_tail import InfraNoiseGate, covered_counts

ENV_SWITCH = "IP_RADAR_INFRA_NOISE_FILTER"


def _net(s: str):
    return ipaddress.ip_network(s, strict=False)


# ── InfraNoiseGate ──

def test_gate_enabled_requires_source_optin_and_env_switch(monkeypatch):
    monkeypatch.delenv(ENV_SWITCH, raising=False)
    assert InfraNoiseGate("s", True).enabled is True
    assert InfraNoiseGate("s", False).enabled is False   # 未声明源零变化
    monkeypatch.setenv(ENV_SWITCH, "0")
    assert InfraNoiseGate("s", True).enabled is False    # 总开关关 = 复原口径


def test_gate_blocks_curated_single_address_only():
    g = InfraNoiseGate("s", True)
    assert g.blocks(_net("8.8.8.8")) is True
    assert g.excluded == ["8.8.8.8/32"]                  # 明文留痕形态
    # 宁少算:更大 CIDR 是不同断言,不排也不记账
    assert g.blocks(_net("8.8.8.0/24")) is False
    assert g.excluded == ["8.8.8.8/32"]
    assert g.blocks(_net("203.0.113.7")) is False


def test_gate_disabled_never_blocks_or_accounts(monkeypatch):
    monkeypatch.setenv(ENV_SWITCH, "0")
    g = InfraNoiseGate("s", True)
    assert g.blocks(_net("8.8.8.8")) is False
    assert g.excluded == []


def test_gate_flush_dedups_and_logs_once(tmp_path, caplog):
    g = InfraNoiseGate("fake_src", True)
    g.blocks(_net("114.114.114.114"))
    g.blocks(_net("114.114.114.114"))          # A 车道双遍 harvest 同条双记
    g.blocks(_net("8.8.8.8"))
    with caplog.at_level(logging.INFO,
                         logger="ipdb._sources._infra_filter"):
        g.flush()
    log = [r for r in caplog.records
           if "infra noise filter" in r.getMessage()]
    assert len(log) == 1
    msg = log[0].getMessage()
    assert "fake_src" in msg and "excluded 2" in msg   # 去重后计数
    assert "8.8.8.8/32" in msg and "114.114.114.114/32" in msg


def test_gate_flush_noop_when_nothing_excluded(caplog):
    g = InfraNoiseGate("s", True)
    with caplog.at_level(logging.INFO,
                         logger="ipdb._sources._infra_filter"):
        g.flush()
    assert not [r for r in caplog.records
                if "infra noise filter" in r.getMessage()]


# ── covered_counts(v4/v6 分流,B/C 预扫描口径)──

def test_covered_counts_worked_example_v4():
    # /32→1、/24→256、/32→1(独立算例,非按实现回算)
    assert covered_counts(["1.2.3.4", "10.0.0.0/24",
                           "203.0.113.7/32"]) == (258, 0)


def test_covered_counts_worked_example_v6_count_as_1():
    assert covered_counts(["2001:db8::/32", "::1"]) == (0, 2)
    assert covered_counts(["10.0.0.0/24", "::1"]) == (256, 1)


def test_covered_counts_skips_invalid_entries():
    assert covered_counts(["bogus", "1.2.3.4"]) == (1, 0)


# ── 三车道接线钉子(spy 证明 rebuild 路由到共享件)──

class _SpyGate(InfraNoiseGate):
    """真门记账语义不动,仅记录构造与 blocks 咨询次数。"""
    made: list = []
    blocks_calls: int = 0

    def __init__(self, source_name, infra_noise_filter):
        super().__init__(source_name, infra_noise_filter)
        _SpyGate.made.append((source_name, infra_noise_filter))

    def blocks(self, net) -> bool:
        _SpyGate.blocks_calls += 1
        return super().blocks(net)


@pytest.fixture()
def spy_gate(monkeypatch):
    _SpyGate.made = []
    _SpyGate.blocks_calls = 0
    from ipdb._sources import _base as base_mod
    from ipdb import _source_base as a_mod
    monkeypatch.setattr(base_mod, "InfraNoiseGate", _SpyGate)
    monkeypatch.setattr(a_mod, "InfraNoiseGate", _SpyGate)
    return _SpyGate


def test_iplist_lane_routes_through_shared_gate(tmp_path, spy_gate):
    from ipdb._sources._base import IpListSource

    class _L(IpListSource):
        name = "spy_list"
        url = "https://example.com/s.txt"
        filename = "s.txt"
        fields = ("is_malicious",)
        classification_type = "blacklist"
        verdict = "malicious"
        reliability = 0.55
        infra_noise_filter = True

    (tmp_path / "s.txt").write_text("8.8.8.8\n203.0.113.7\n")
    assert _L(data_dir=tmp_path).rebuild() == 1
    assert ("spy_list", True) in spy_gate.made
    assert spy_gate.blocks_calls >= 1


def test_csv_lane_routes_through_shared_gate(tmp_path, spy_gate):
    from ipdb._sources._base import CsvSource

    class _C(CsvSource):
        name = "spy_csv"
        url = "https://example.com/s.csv"
        filename = "s.csv"
        fields = ("is_malicious",)
        skip_lines = 1
        infra_noise_filter = True

        def parse_row(self, row):
            return ({"_ip": row[0].strip(), "classification_type":
                     "blacklist", "verdict": "malicious",
                     "reliability": 0.55} if len(row) >= 2 else None)

    (tmp_path / "s.csv").write_text("ip,note\n8.8.8.8,x\n203.0.113.8,y\n")
    assert _C(data_dir=tmp_path).rebuild() == 1
    assert ("spy_csv", True) in spy_gate.made
    assert spy_gate.blocks_calls >= 1


def test_harvest_lane_routes_through_shared_gate(tmp_path, spy_gate):
    from ipdb._evidence import Evidence
    from ipdb._source_base import Source

    class _H(Source):
        name = "spy_harvest"
        url = "https://example.com/s.csv"
        filename = "s.csv"
        fields = ("is_malicious",)
        infra_noise_filter = True
        single_evidence = True  # 钉流式 factory 形态×共享 gate 组合(#291 评审 P2-1)

        def harvest(self):
            yield "8.8.8.8", Evidence(classification_type="blacklist",
                                       verdict="malicious",
                                       reliability=0.55)
            yield "203.0.113.9", Evidence(classification_type="blacklist",
                                          verdict="malicious",
                                          reliability=0.55)

    (tmp_path / "s.csv").write_text("8.8.8.8\n203.0.113.9\n")
    assert _H(data_dir=tmp_path).rebuild() == 1
    assert ("spy_harvest", True) in spy_gate.made
    assert spy_gate.blocks_calls >= 1      # acc 物化路径单遍 harvest
