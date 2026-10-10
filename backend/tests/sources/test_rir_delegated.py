"""rir_delegated 源测试(信息维度批 2026-10-10,grill #3 口径)。"""
from pathlib import Path

import pytest

from ipdb._sources.rir_delegated import (
    RirDelegatedSource, _norm_date, _parse_row, _parse_rows,
)


def test_norm_date():
    assert _norm_date("20071126") == "2007-11-26"
    assert _norm_date("") is None and _norm_date("2007") is None
    assert _norm_date("2007-11-26") is None


def test_parse_row_v4_aligned_single_cidr():
    out = _parse_row(
        "ripencc|PS|ipv4|1.178.112.0|4096|20071126|allocated|uuid".split("|"))
    assert out == [("1.178.112.0/20",
                    {"registry": "ripencc", "reg_country": "PS",
                     "alloc_date": "2007-11-26", "status": "allocated"})]


def test_parse_row_v4_unaligned_spans_two_cidrs():
    """count 非对齐:范围展开必须全返回;真值用 stdlib 现场算(丢网=覆盖缺口)。"""
    from ipaddress import summarize_address_range, IPv4Address
    out = _parse_row(
        "test|XX|ipv4|1.0.0.0|770|20200101|assigned|u".split("|"))
    expected = [str(n) for n in summarize_address_range(
        IPv4Address("1.0.0.0"), IPv4Address("1.0.3.1"))]  # 1.0.0.0 + 769
    assert [c for c, _ in out] == expected


def test_parse_row_skips_available_reserved_and_asn():
    assert _parse_row(
        "ripencc||ipv4|85.8.248.0|2048||available|".split("|")) is None
    assert _parse_row(
        "test|XX|ipv4|1.2.3.0|256|20200101|reserved|u".split("|")) is None
    assert _parse_row(
        "test|XX|asn|64512|1|20200101|allocated|u".split("|")) is None
    # 星号 cc(汇总行形状)不该带 reg_country
    out = _parse_row(
        "test|*|ipv4|9.9.9.0|256|20200101|allocated|u".split("|"))
    assert out and "reg_country" not in out[0][1]


def test_parse_row_ipv6_value_is_prefixlen():
    out = _parse_row(
        "afrinic|ZA|ipv6|2001:4200::|32|20051021|allocated|F36".split("|"))
    assert out == [("2001:4200::/32",
                    {"registry": "afrinic", "reg_country": "ZA",
                     "alloc_date": "2005-10-21", "status": "allocated"})]


def test_parse_rows_skips_header_and_summary():
    lines = ["# header", "ripencc|*|ipv4|*|100993|summary",
             "ripencc|PS|ipv4|1.178.112.0|4096|20071126|allocated|u"]
    assert list(_parse_rows(lines)) == [
        ("1.178.112.0/20", {"registry": "ripencc", "reg_country": "PS",
                            "alloc_date": "2007-11-26",
                            "status": "allocated"})]


def test_harvest_reads_directory(tmp_path):
    src = RirDelegatedSource(data_dir=tmp_path)
    d = tmp_path / "rir_delegated"
    d.mkdir()
    (d / "ripencc.txt").write_text(
        "ripencc|PS|ipv4|1.178.112.0|4096|20071126|allocated|u\n"
        "ripencc||ipv4|85.8.248.0|2048||available|\n"
        "ripencc|DE|ipv6|2001:abcd::|32|20100101|assigned|u\n")
    rows = list(src.harvest())
    assert [c for c, _ in rows] == ["1.178.112.0/20", "2001:abcd::/32"]
    ev = rows[0][1]
    assert ev.verdict == ""                 # 弃权拼写:信息位不指控
    assert ev.classification_type is None   # 永不进观测
    assert ev.extra["status"] == "allocated"


def _fake_download_factory(payload_by_reg):
    """download_file 假体:按 URL 含 reg 名写对应内容到目标路径。"""
    def fake(url, dest, token=None, timeout=None, headers=None):
        for reg, text in payload_by_reg.items():
            if f"/{reg}/" in url or reg in url:
                Path(dest).write_text(text)
                return
        Path(dest).write_text("x")
    return fake


def _healthy_rows(n):
    return "".join(
        f"test|XX|ipv4|10.{i // 256}.{i % 256}.0|256|20200101|allocated|u\n"
        for i in range(n))


def test_download_guard_thin_payload_keeps_old(monkeypatch, tmp_path):
    """守卫 fail-closed:薄载荷不替换旧文件;全五家薄 → 全败 raise。"""
    src = RirDelegatedSource(data_dir=tmp_path)
    d = tmp_path / "rir_delegated"
    d.mkdir()
    old = d / "ripencc.txt"
    old.write_text(_healthy_rows(3100))
    monkeypatch.setattr(
        "ipdb._sources.rir_delegated.download_file",
        _fake_download_factory({reg: "thin" for reg in
                                ("afrinic", "apnic", "arin", "lacnic",
                                 "ripencc")}))
    with pytest.raises(RuntimeError, match="all rir_delegated feeds failed"):
        src.download()
    assert old.read_text().startswith("test|XX")   # 旧数据保留


def test_download_partial_failure_tolerated(monkeypatch, tmp_path):
    """一家失败容忍:四家落地,last_partial_failure 记名。"""
    src = RirDelegatedSource(data_dir=tmp_path)

    def fake(url, dest, token=None, timeout=None, headers=None):
        if "apnic" in url:
            raise RuntimeError("network down")
        Path(dest).write_text(_healthy_rows(3100))

    monkeypatch.setattr(
        "ipdb._sources.rir_delegated.download_file", fake)
    src.download()
    assert src.last_partial_failure == ["apnic"]
    assert (tmp_path / "rir_delegated" / "ripencc.txt").exists()
    assert not (tmp_path / "rir_delegated" / "apnic.txt").exists()
