"""ipinfo_lite load/rebuild 分离:load 纯 mmap,rebuild 重建(LMDB 试点)。"""
import builtins
from pathlib import Path

from ipdb._sources._lmdb import rebuild_lmdb, ptr_path


def test_ipinfo_lite_load_pure_mmap(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    s = IPinfoLiteSource(tmp_path)
    envs = []
    rebuild_lmdb(
        [("9.9.9.0/24", {"country_code": "US", "_net": "9.9.9.0/24", "has_asn": False})],
        tmp_path / "ipinfo_lite.csv.lmdb", envs.append,
    )
    # py-lmdb 禁止同进程对同一路径双开:生产中 load() 只在启动调用
    # (rebuild 后走 reader_setter,不再 load),这里关掉 rebuild 句柄再让 load 开。
    envs[0].close()
    assert s.load() == 1
    assert s.query("9.9.9.9")["country_code"] == "US"
    s._reader.close()


def test_ipinfo_lite_rebuild_from_csv(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    (tmp_path / "ipinfo_lite.csv").write_text(
        "network,country,country_code,continent,continent_code,asn,as_name,as_domain\n"
        "1.0.0.0/24,Australia,AU,Oceania,OC,AS13335,Cloudflare,cloudflare.com\n"
    )
    s = IPinfoLiteSource(tmp_path)
    n = s.rebuild()
    assert n == 1
    assert s.query("1.0.0.1")["country_code"] == "AU"
    s._reader.close()


def test_ipinfo_lite_not_built_returns_empty(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    s = IPinfoLiteSource(tmp_path)
    assert s.load() == 0
    assert s.query("1.2.3.4") == {}


def test_ipinfo_lite_mmdb_path_points_at_ptr(tmp_path):
    """注册表重建判定靠 _mmdb_path + needs_convert 的 mtime 比较;
    试点把它重指向 ptr 文件,raw 更新后 ptr 旧 → 触发重建。"""
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    from ipdb._sources._lmdb import needs_convert
    s = IPinfoLiteSource(tmp_path)
    assert s._mmdb_path.name == "ipinfo_lite.csv.lmdb.ptr"
    (tmp_path / "ipinfo_lite.csv").write_text("network\n1.0.0.0/24\n")
    assert needs_convert(tmp_path / "ipinfo_lite.csv", s._mmdb_path) is True


def test_ipinfo_lite_query_returns_three_new_keys(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    header = ("network,country,country_code,continent,continent_code,"
              "asn,as_name,as_domain\n")
    row = '1.0.0.0/24,Australia,AU,Oceania,OC,AS13335,"Cloudflare, Inc.",cloudflare.com\n'
    (tmp_path / "ipinfo_lite.csv").write_text(header + row)
    s = IPinfoLiteSource(data_dir=tmp_path)
    s.rebuild()
    r = s.query("1.0.0.1")
    assert r["country_code"] == "AU"
    assert r["continent_code"] == "OC"
    assert r["country_name"] == "Australia"
    assert r["as_domain"] == "cloudflare.com"
    s._reader.close()


def test_ipinfo_lite_empty_geo_columns_omit_keys(tmp_path):
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    header = ("network,country,country_code,continent,continent_code,"
              "asn,as_name,as_domain\n")
    row = "1.0.1.0/24,,CN,,,AS13335,,\n"
    (tmp_path / "ipinfo_lite.csv").write_text(header + row)
    s = IPinfoLiteSource(data_dir=tmp_path)
    s.rebuild()
    r = s.query("1.0.1.5")
    for k in ("continent_code", "country_name", "as_domain"):
        assert k not in r
    s._reader.close()


def test_ipinfo_rebuild_parses_csv_twice_not_four(tmp_path, monkeypatch):
    """预扫描(_cidrs)删除后,CSV 只被 _records 解析两次(族分区)。"""
    from ipdb._sources import ipinfo_lite as mod
    (tmp_path / "ipinfo_lite.csv").write_text(
        "ip,network_start,network_end,country,continent,asn,as_name,as_domain\n"
        "1.2.3.0/24,,,US,NA,AS65530,Test AS,test.example\n"
        "2001:db8::/32,,,JP,AS,AS65531,V6 AS,v6.example\n"
    )
    opened = {"n": 0}
    real_open = builtins.open
    def counting_open(file, *a, **k):
        if str(file).endswith("ipinfo_lite.csv"):
            opened["n"] += 1
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", counting_open)
    src = mod.IPinfoLiteSource(tmp_path)
    src.rebuild()
    assert opened["n"] == 2                  # 旧行为 4:_cidrs 2 + _records 2
    assert src._covered_ips == 256
    assert src._covered_v6_nets == 1


def test_ipinfo_lite_download_gunzip_replaces_old_csv(tmp_path, monkeypatch):
    """F-5 成功路径:gz 下载 → 解压 scratch → replace;旧 CSV 换新,gz/scratch 清理。"""
    import gzip as _gzip
    import ipdb._sources.ipinfo_lite as mod
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource

    csv_new = "network,country_code\n9.9.9.0/24,DE\n8.8.8.0/24,US\n"

    def fake_download_file(url, dest, token=None, **kw):
        dest.write_bytes(_gzip.compress(csv_new.encode()))

    monkeypatch.setenv("IPINFO_TOKEN", "t")
    monkeypatch.setattr(mod, "download_file", fake_download_file)
    src = IPinfoLiteSource(tmp_path)
    src._path.write_text("network,country_code\n1.1.1.0/24,AU\n")
    src.download()
    assert src._path.read_text() == csv_new
    assert not (tmp_path / "ipinfo_lite.csv.dl").exists()
    assert not (tmp_path / "ipinfo_lite.csv.gz").exists()


def test_ipinfo_lite_gunzip_write_failure_keeps_old_csv(tmp_path, monkeypatch):
    """F-5 代表源(gz 形):解压写 scratch 半途抛(模拟 ENOSPC)→ 旧 CSV
    字节级保留、scratch/gz 清理,异常上抛走退避(旧实现的直写会留半文件,
    且 except 分支 unlink 会把旧证据一并删掉)。"""
    import gzip as _gzip
    import pytest
    import ipdb._sources.ipinfo_lite as mod
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource

    def fake_download_file(url, dest, token=None, **kw):
        dest.write_bytes(_gzip.compress(b"network,country_code\n9.9.9.0/24,DE\n"))

    def boom(src, dst, length=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setenv("IPINFO_TOKEN", "t")
    monkeypatch.setattr(mod, "download_file", fake_download_file)
    monkeypatch.setattr(mod.shutil, "copyfileobj", boom)
    src = IPinfoLiteSource(tmp_path)
    csv_old = "network,country_code\n1.1.1.0/24,AU\n"
    src._path.write_text(csv_old)
    with pytest.raises(OSError):
        src.download()
    assert src._path.read_text() == csv_old          # 字节级完好
    assert not (tmp_path / "ipinfo_lite.csv.dl").exists()
    assert not (tmp_path / "ipinfo_lite.csv.gz").exists()
