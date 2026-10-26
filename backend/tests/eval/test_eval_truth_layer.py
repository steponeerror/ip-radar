import ipaddress

import pytest

from ipdb._eval.assets import fingerprint, load_asset
from ipdb._eval.layer_builders import scanner_ranges_prefixes
from ipdb._eval.truth_layer import (
    TruthLayerDegradedError,
    apply_rir_filter,
    apply_scanner_filter,
    build_truth_layer,
    gates_health,
    parse_rir_delegated,
)


def _ip(s: str) -> int:
    return int(ipaddress.IPv4Address(s))


# 10_000 段 = S9 健康度地板恰过线;9_999 恰不过线
_BIG_RANGES = [(10_000_000 + i * 256, 256, "20000101") for i in range(10_000)]


def test_parse_rir_delegated_keeps_ipv4_allocated_assigned_only():
    lines = [
        "2|ripencc|*|*|*|*|*|*",  # 版本行(8 字段)
        "# comment",
        "ripencc|*|ipv4|*|123456|*|summary",  # 汇总行
        "ripencc|DE|ipv4|5.1.0.0|16384|19840904|allocated",
        "ripencc|FR|ipv4|2.0.0.0|256|20200101|assigned",
        "ripencc|DE|ipv6|2001:600::|32|19990826|allocated",  # 非 ipv4
        "ripencc|NL|ipv4|3.0.0.0|1024|20100101|reserved",  # 其它 status
    ]
    assert parse_rir_delegated(lines) == [
        (_ip("5.1.0.0"), 16384, "19840904"),
        (_ip("2.0.0.0"), 256, "20200101"),
    ]


def test_rir_gate_boundary_0701_kept_0702_dropped():
    # 闸①边界逐字钉死: ≥2024-07-02 剔除;2024-07-01(含)及更早保留(spec §2.2)
    ranges = [(_ip("5.1.0.0"), 256, "20240701"), (_ip("6.1.0.0"), 256, "20240702")]
    ips = ["5.1.0.5", "5.1.0.255", "6.1.0.5", "6.1.0.255", "6.1.1.0"]
    kept, dropped = apply_rir_filter(ips, ranges)
    assert kept == ["5.1.0.5", "5.1.0.255", "6.1.1.0"]  # 末主机含/段外保留
    assert dropped == 2


def test_scanner_filter_cidr_and_bare_ip():
    kept, dropped = apply_scanner_filter(
        ["1.2.3.4", "1.2.4.4", "8.8.8.8", "9.9.9.9"], ["1.2.3.0/24", "8.8.8.8"]
    )
    assert kept == ["1.2.4.4", "9.9.9.9"] and dropped == 2


def test_gates_health_flags_each_cause():
    assert gates_health(_BIG_RANGES, ["10.0.0.0/8"]) == {
        "rir_ok": True, "scanner_ok": True, "degraded": False,
    }
    assert gates_health(_BIG_RANGES[:-1], ["10.0.0.0/8"]) == {  # 9,999 段
        "rir_ok": False, "scanner_ok": True, "degraded": True,
    }
    assert gates_health(_BIG_RANGES, []) == {
        "rir_ok": True, "scanner_ok": False, "degraded": True,
    }
    assert gates_health([], []) == {
        "rir_ok": False, "scanner_ok": False, "degraded": True,
    }


@pytest.mark.parametrize(
    "ranges,scanlist",
    [(_BIG_RANGES[:-1], ["10.0.0.0/8"]), (_BIG_RANGES, [])],  # 两种单因退化
)
def test_build_degraded_refuses_and_writes_nothing(tmp_path, ranges, scanlist):
    out = tmp_path / "truth"
    with pytest.raises(TruthLayerDegradedError):
        build_truth_layer(["1.2.3.4"], ranges, scanlist, out, "v1")
    assert not out.exists() and list(tmp_path.iterdir()) == []  # 拒出版=零落盘


def test_build_happy_path_publishes_truth_asset(tmp_path):
    out = tmp_path / "truth"
    meta = build_truth_layer(
        ["5.1.0.5", "9.9.9.9", "5.1.0.5"],  # 重复成员去重
        _BIG_RANGES,
        ["10.0.0.0/8"],
        out,
        "v2026-10",
    )
    assert meta.kind == "truth" and meta.member_count == 2
    assert set(meta.params) >= {"rir_fingerprint", "scanlist_fingerprint"}  # S37
    assert meta.params["scanlist_fingerprint"] == fingerprint(["10.0.0.0/8"])
    members, loaded = load_asset(out)
    assert members == ["5.1.0.5", "9.9.9.9"] and loaded.kind == "truth"


def test_scanner_ranges_join_two_arm_exclusion_and_fingerprint(tmp_path):
    # SR-T2 D3(#213 / ADR 0011): ops 两臂对照 —— arm A legacy scanlist,
    # arm B legacy+自报段(D1 scanner_ranges_prefixes 供表);同 raw/rir
    # 输入,验证装配侧剔除生效 + 语料版本随附(S12: 成员指纹与
    # scanlist_fingerprint 两臂皆变)。v6 前缀混排过 build_truth_layer
    # 不炸(值域与 v4 永不重叠)。
    csv = tmp_path / "scanner_ranges.csv"
    csv.write_text("40.124.175.0/24,Stretchoid\n2600:1f00::/24,Amazon\n",
                   encoding="utf-8")
    legacy = ["10.0.0.0/8"]  # 不覆盖 40.124.175.29(census 例证 IP)
    raw = ["40.124.175.29", "5.1.0.5", "9.9.9.9"]
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    meta_a = build_truth_layer(raw, _BIG_RANGES, legacy, a_dir, "v1")
    meta_b = build_truth_layer(raw, _BIG_RANGES,
                               legacy + scanner_ranges_prefixes(csv),
                               b_dir, "v1")
    mem_a, load_a = load_asset(a_dir)
    mem_b, load_b = load_asset(b_dir)
    # 40.124.175.29:arm A 在场(污染),arm B 剔除;段外成员两臂同存
    assert mem_a == ["40.124.175.29", "5.1.0.5", "9.9.9.9"]  # 去重定序
    assert mem_b == ["5.1.0.5", "9.9.9.9"]
    # removed_by_scanner_filter 差值精确(arm A legacy 不覆盖该 IP → 0)
    assert meta_a.params["removed_by_scanner_filter"] == 0
    assert meta_b.params["removed_by_scanner_filter"] == 1
    # S12 换版随附:语料指纹与 scanlist 指纹两臂皆变
    assert meta_a.fingerprint != meta_b.fingerprint
    assert meta_a.params["scanlist_fingerprint"] != \
        meta_b.params["scanlist_fingerprint"]
    # 两臂 load_asset 往返一致(指纹闸: 证据永不灭失)
    assert load_a.fingerprint == meta_a.fingerprint
    assert load_b.fingerprint == meta_b.fingerprint
    assert load_a.kind == load_b.kind == "truth"


def test_parse_accepts_delegated_extended_8th_field():
    """真 delegated-extended 带第 8 列 opaque-id(2026-10-14 首真数据实测
    发现:7 字段断言 → 镜像五文件 0 段)。≥7 字段即收,富余列忽略。"""
    lines = [
        "afrinic|ZA|ipv4|41.0.0.0|2097152|20071126|allocated|F364712F",  # 真格式
        "afrinic|ZA|ipv4|41.79.0.0|4096|20170811|allocated",             # 7列旧式
        "afrinic|*|ipv4|*|6111|summary",                                  # 汇总出局
        "2|afrinic|20261014|19858|00000000|20261014|00000",               # 版本行出局
    ]
    out = parse_rir_delegated(lines)
    assert len(out) == 2
    assert out[0] == (int(__import__("ipaddress").IPv4Address("41.0.0.0")), 2097152, "20071126")
