# backend/tests/sources/test_gaoyifan_china_operator_ip.py
"""gaoyifan/china-operator-ip — CN 运营商聚合 CIDR 清单(iptoasn 同款 A 家族
Source:harvest 逐行 CIDR → Evidence(country_code/ip_range,verdict="" 弃权))。

夹具行逐字取自 ip-lists 分支实抓(2026-11-18):
  china.txt(6,221 行,零脏行,全 CIDR/IPv4)
  china6.txt(3,444 行,全 CIDR/IPv6)
实抓全量 0 条非 CIDR 行(裸 IP/注释/缺列均不存在)→ 脏行夹具无实抓可取,
bad-line 断言用显式合成守卫行(测试内标注,不冒充实抓)。
"""
from pathlib import Path

from ipdb._sources.gaoyifan_china_operator_ip import GaoyifanChinaOperatorIPSource


# ── 实抓样本(ip-lists 分支,逐字)──
_V4_LINES = ["1.0.1.0/24", "1.0.2.0/23", "223.255.252.0/23"]
_V6_LINE = "2001:250::/30"


def _write_fixture(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_subclass_of_source():
    from ipdb._source_base import Source as S2
    assert issubclass(GaoyifanChinaOperatorIPSource, S2)


def test_import_alias_spellings():
    """PEP 562 三拼法别名可导入,且不进 dir()(防 roster 双注册)。"""
    import ipdb._sources.gaoyifan_china_operator_ip as m
    from ipdb._sources.gaoyifan_china_operator_ip import (
        GaoyifanchinaoperatoripSource,      # 令牌机械形
        GaoyifanChinaOperatorIpSource,      # 品牌拆词形(段内保大小写)
        GAOYIFANChinaOperatorIPSource,      # 缩写全大写形
    )
    assert GaoyifanchinaoperatoripSource is GaoyifanChinaOperatorIPSource
    assert GaoyifanChinaOperatorIpSource is GaoyifanChinaOperatorIPSource
    assert GAOYIFANChinaOperatorIPSource is GaoyifanChinaOperatorIPSource
    for a in ("GaoyifanchinaoperatoripSource",
              "GaoyifanChinaOperatorIpSource",
              "GAOYIFANChinaOperatorIPSource"):
        assert a not in dir(m)


def test_harvest_yields_cn_scalar_evidence(tmp_path: Path):
    _write_fixture(tmp_path / "gaoyifan_china_operator_ip.txt", _V4_LINES)
    src = GaoyifanChinaOperatorIPSource(data_dir=tmp_path)
    rows = list(src.harvest())
    assert len(rows) == 3
    cidr, ev = rows[0]
    assert cidr == "1.0.1.0/24"
    assert ev.country_code == "CN"
    assert ev.ip_range == "1.0.1.0/24"
    # 信息位不指控(rir_delegated 同款弃权拼写)
    assert ev.classification_type is None
    assert ev.verdict == ""
    assert ev.reliability is None


def test_harvest_skips_blank_comment_and_bad_lines(tmp_path: Path):
    # 实抓全量零脏行;空行/注释/坏行为通用解析守卫(合成,非实抓)
    _write_fixture(
        tmp_path / "gaoyifan_china_operator_ip.txt",
        ["# comment", "", "not-an-ip", "1.0.1.0/24", "999.1.1.1/24"],
    )
    src = GaoyifanChinaOperatorIPSource(data_dir=tmp_path)
    rows = list(src.harvest())
    assert [c for c, _ in rows] == ["1.0.1.0/24"]


def test_rebuild_query_roundtrip_v4_and_v6(tmp_path: Path):
    _write_fixture(
        tmp_path / "gaoyifan_china_operator_ip.txt",
        _V4_LINES + [_V6_LINE],
    )
    src = GaoyifanChinaOperatorIPSource(data_dir=tmp_path)
    n = src.rebuild()
    assert n == 3                 # 返回值 = v4 主库键数;v6 走并行族 sidecar
    assert src._count6 == 1
    recs = src.query("1.0.1.5")
    assert isinstance(recs, list) and len(recs) == 1
    rec = recs[0]
    assert rec["country_code"] == "CN"
    assert rec["ip_range"] == "1.0.1.0/24"
    assert "_net" not in rec
    # v6 族:同文件 ':' 双族分派,独立 sidecar
    recs6 = src.query("2001:250::1")
    assert isinstance(recs6, list) and len(recs6) == 1
    assert recs6[0]["country_code"] == "CN"
    assert recs6[0]["ip_range"] == "2001:250::/30"
    # 未收录段 miss
    assert src.query("8.8.8.8") == {}
    assert src.query("2001:db8::1") == {}
    # rebuild→load 回程:新实例同答
    src._reader.close()
    src._reader6.close()
    fresh = GaoyifanChinaOperatorIPSource(data_dir=tmp_path)
    assert fresh.load() == 3
    assert fresh._count6 == 1
    rec2 = fresh.query("1.0.1.5")
    assert rec2[0]["ip_range"] == "1.0.1.0/24"
    fresh._reader.close()
    fresh._reader6.close()


def test_download_joins_v4_v6_and_keeps_old_on_v6_fail(tmp_path: Path, monkeypatch):
    src = GaoyifanChinaOperatorIPSource(data_dir=tmp_path)
    src._data_dir.mkdir(parents=True, exist_ok=True)
    # 先落地一份好数据
    _write_fixture(src._path, _V4_LINES + [_V6_LINE])
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("1.0.1.0/24\n").encode()
        raise RuntimeError("network down")

    monkeypatch.setattr(src, "_http_get", fake_get)
    src.download()
    # v6 失败 → 旧 join 文件字节级保留 + last_partial_failure=["china6.txt"]
    assert src._path.read_text(encoding="utf-8").splitlines() == \
        _V4_LINES + [_V6_LINE]
    assert src.last_partial_failure == ["china6.txt"]

    # v4 失败 → raise + 记 ["china.txt"],旧文件保留
    def fail_all(url, *a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(src, "_http_get", fail_all)
    try:
        src.download()
        assert False, "v4 failure must raise"
    except RuntimeError:
        pass
    assert src.last_partial_failure == ["china.txt"]
    assert src._path.read_text(encoding="utf-8").splitlines() == \
        _V4_LINES + [_V6_LINE]
