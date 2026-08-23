"""ipinfo_lite v6:61% 行是 v6(2.09M),OOM 纪律下流式双族。"""
CSV = """network,country,country_code,continent,continent_code,asn,as_name,as_domain
8.8.8.0/24,United States,US,North America,NA,AS15169,GOOGLE,google.com
2001:200::/37,Japan,JP,Asia,AS,AS2500,WIDE-BB,wide.ad.jp
2000:b70:25::/48,United States,US,North America,NA,AS396982,GOOGLE-CLOUD-PLATFORM,google.com
"""


def test_ipinfo_v6_rebuild_and_query(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    src = IPinfoLiteSource(tmp_path)
    (tmp_path / "ipinfo_lite.csv").write_text(CSV)
    n = src.rebuild()
    assert n == 1 and src._count6 == 2
    assert src.query("2001:200::1").get("country_code") == "JP"
    assert src.query("2000:b70:25::a").get("asn") == 396982
    assert src.query("8.8.8.1").get("country_code") == "US"   # v4 不回归
    assert src._covered_v6_nets == 2


def test_ipinfo_v6_shaped_result_has_ip_range(tmp_path):
    """v6 查询结果与 v4 同形:整形后带 ip_range 槽(RangeSpecificity 依赖),
    不泄漏内部 has_asn/_net 键。"""
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    src = IPinfoLiteSource(tmp_path)
    (tmp_path / "ipinfo_lite.csv").write_text(CSV)
    src.rebuild()
    r4 = src.query("8.8.8.1")
    r6 = src.query("2001:200::1")
    assert r6["ip_range"] == "2001:200::/37"
    assert set(r6) == set(r4)                     # 结构同族(两行都带 ASN)
    assert "_net" not in r6 and "has_asn" not in r6
    assert r4["ip_range"] == "8.8.8.0/24"


def test_ipinfo_v6_q3_ptr_written_on_empty_v6(tmp_path):
    """v6 ptr 恒写(Q3 不变量):纯 v4 数据重建后 v6 sidecar 也在。"""
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    from ipdb._sources._lmdb import read_ptr
    src = IPinfoLiteSource(tmp_path)
    (tmp_path / "ipinfo_lite.csv").write_text(CSV.splitlines()[0] + "\n8.8.8.0/24,United States,US,North America,NA,AS15169,GOOGLE,google.com\n")
    n = src.rebuild()
    assert n == 1 and src._count6 == 0
    assert read_ptr(src._lmdb6_base) is not None
    assert src.query("2001:db8::1") == {}          # 无 v6 数据安静 miss


def test_ipinfo_v6_load_reads_sidecars(tmp_path):
    """load() 双路径读 v6 sidecar:进程重启后 v6 查询仍可用。"""
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    src = IPinfoLiteSource(tmp_path)
    (tmp_path / "ipinfo_lite.csv").write_text(CSV)
    src.rebuild()
    src._reader.close(); src._reader6.close()
    src._reader = src._reader6 = None
    src._count = src._count6 = src._covered_ips = src._covered_v6_nets = 0
    n = src.load()
    assert n == 1
    assert src._count6 == 2 and src._covered_v6_nets == 2
    assert src._reader6 is not None
    assert src.query("2001:200::1").get("country_code") == "JP"


def test_ipinfo_v6_load_without_v6_sidecar_is_quiet(tmp_path):
    """旧数据目录(无 v6 sidecar):load 正常,v6 查询安静空,v4 不受影响。"""
    import shutil
    from pathlib import Path
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    src = IPinfoLiteSource(tmp_path)
    (tmp_path / "ipinfo_lite.csv").write_text(CSV)
    src.rebuild()
    src._reader.close(); src._reader6.close()
    for p in tmp_path.glob("ipinfo_lite.csv.v6.lmdb*"):
        (shutil.rmtree if p.is_dir() else Path.unlink)(p)
    n = src.load()
    assert n == 1
    assert src._reader6 is None
    assert src.query("2001:200::1") == {}
    assert src.query("8.8.8.1").get("country_code") == "US"
