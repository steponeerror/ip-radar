"""--demand 答案率探针测试(罗盘批 2026-10-10)。

纯函数注入假 lookup_fn——不碰 registry/DB;假零探针判例:任何探针
测试自证以已命中 fixture 开头。
"""
import pytest

from ipdb._eval.demand import (
    FieldStat, _account, probe_cohort, demand_report,
)

_FULL = {
    "country": {"value": "US", "confidence": 80, "sources": [{"source": "a"}]},
    "city": {"value": "X", "confidence": 70, "sources": [{"source": "a"}]},
    "asn": {"value": 1, "confidence": 90,
            "sources": [{"source": "a"}, {"source": "b"}]},
    "as_name": {"value": "n", "confidence": 90, "sources": [{"source": "a"}]},
    "ip_range": {"value": "1.0.0.0/24", "confidence": 90,
                 "sources": [{"source": "a"}]},
    "is_isp": True,
    "threat": {"verdict": "malicious"},
    "classifications": {"scanner": {"detected": True}},
    "attributes": {"is_proxy": [{"source": "a"}]},
}
_EMPTY = {  # 无证据 ≠ 清白:零证人形态
    "country": {"value": None, "confidence": 0, "sources": []},
    "city": {"value": None, "confidence": 0, "sources": []},
    "asn": {"value": None, "confidence": 0, "sources": []},
    "as_name": {"value": None, "confidence": 0, "sources": []},
    "ip_range": {"value": None, "confidence": 0, "sources": []},
    "is_isp": False,
    "threat": {"verdict": "informational"},
    "classifications": {},
    "attributes": {},
}


def test_account_full_and_empty_balance():
    """一全一空:各字段 50%,conf/wits 只计入 answered。"""
    stats = {}
    _account(stats, _FULL)
    _account(stats, _EMPTY)
    assert stats["country"].seen == 2 and stats["country"].answered == 1
    assert stats["country"].conf_sum == 80
    assert stats["asn"].witnesses_sum == 2        # 双证人计满
    assert stats["threat:flagged"].answered == 1
    assert stats["class:detected"].answered == 1
    assert stats["attr:is_proxy"].answered == 1


def test_probe_cohort_known_positive_then_rates():
    """判例自证:已命中 fixture 必须出现在结果里(防假零)。"""
    stats = probe_cohort(lambda ip: _FULL, ["1.2.3.4"])
    assert stats["country"].answered == 1        # PROBE ALIVE
    stats = probe_cohort(lambda ip: _FULL if ip.endswith(".4") else _EMPTY,
                         ["1.2.3.4", "5.6.7.8"])
    assert stats["country"].answered == 1 and stats["country"].seen == 2


def test_attr_denominator_is_whole_cohort():
    """attr 键缺席也是答案:分母 = 全体,不许恒 100%。"""
    stats = probe_cohort(
        lambda ip: _FULL if ip == "1.1.1.1" else _EMPTY,
        ["1.1.1.1", "2.2.2.2"])
    assert stats["attr:is_proxy"].seen == 2
    assert stats["attr:is_proxy"].answered == 1


def test_row_format_has_pct():
    st = FieldStat(seen=10, answered=2)
    assert "20.0%" in st.row() and "(2/10)" in st.row()


def test_report_table_two_cohorts():
    """双列表结构 + attr 行在场(动态 attribute 键)。"""

    class _Src:  # fleet_ips 经 sample_source_ips 读 _path;此处直接给假 cohort
        pass

    rep = demand_report(lambda ip: _FULL, [_Src()], per_source=0,
                        n_random=2)
    assert "| field | fleet | random |" in rep
    assert "attr:is_proxy" in rep and "country" in rep
