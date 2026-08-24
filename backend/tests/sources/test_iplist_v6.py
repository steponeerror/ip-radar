"""IpListSource/CsvSource v6 双族(line-based 路径)。

与 Source 基类(_source_base.py,Task 4)平行的两套类的双族 rebuild/load/query。
fixture 类形按 f3csystems/ipsum 实际用法(CsvSource 无 harvest hook,
走 parse_row);断言与 brief 一致。
"""
from ipdb._sources._base import IpListSource, CsvSource


class _ListSrc(IpListSource):
    name = "t_list"
    url = "https://example.com/x.txt"
    filename = "x.txt"
    fields = ("is_malicious",)


class _CsvSrc(CsvSource):
    name = "t_csv"
    url = "https://example.com/x.csv"
    filename = "x.csv"
    fields = ("is_malicious",)
    delimiter = ","

    def parse_row(self, row):
        if not row:
            return None
        return {"_ip": row[0].strip()}


def test_iplist_rebuild_dual(tmp_path):
    src = _ListSrc(tmp_path)
    (tmp_path / "x.txt").write_text("1.2.3.4\n2001:db8::dead\n")
    n = src.rebuild()
    assert n == 1 and src._count6 == 1
    assert src._covered_ips == 1                    # /32 → 1 地址
    assert src._covered_v6_nets == 1                # count-as-1
    assert src.query("2001:db8::dead") is not None
    assert src.query("1.2.3.4") is not None
    assert src.query("2001:db9::1") == {}           # v6 miss 安静
    src._reader.close(); src._reader6.close()


def test_iplist_v6_cidr_line(tmp_path):
    """列表行的 v6 CIDR 形态(ip_network strict=False 归一)。"""
    src = _ListSrc(tmp_path)
    (tmp_path / "x.txt").write_text("2001:db8::/48\n")
    src.rebuild()
    assert src._count == 0 and src._count6 == 1
    assert src.query("2001:db8:1::1") is not None   # 段内命中
    src._reader6.close()


def test_iplist_load_v6_sidecars(tmp_path):
    src = _ListSrc(tmp_path)
    (tmp_path / "x.txt").write_text("1.2.3.4\n2001:db8::dead\n")
    src.rebuild()
    src._reader.close(); src._reader6.close()
    src._reader = src._reader6 = None
    n = src.load()
    assert n == 1
    assert src._count6 == 1 and src._covered_v6_nets == 1
    assert src.query("2001:db8::dead") is not None
    src._reader.close(); src._reader6.close()


def test_iplist_load_v4_only_dir_quiet(tmp_path):
    """旧数据目录(只有 v4 env,无 v6 sidecar):load 正常,v6 查询空。"""
    import shutil
    src = _ListSrc(tmp_path)
    (tmp_path / "x.txt").write_text("1.2.3.4\n")
    src.rebuild()
    src._reader.close()
    for p in tmp_path.glob("x.txt.v6.lmdb*"):
        (shutil.rmtree if p.is_dir() else __import__("os").unlink)(p)
    src.load()
    assert src._reader6 is None
    assert src.query("2001:db8::1") == {}
    assert src.query("1.2.3.4") is not None         # v4 不受影响
    src._reader.close()


def test_csv_rebuild_dual(tmp_path):
    src = _CsvSrc(tmp_path)
    (tmp_path / "x.csv").write_text("1.2.3.4\n2001:db8::dead\n")
    src.rebuild()
    assert src._count == 1 and src._count6 == 1
    assert src.query("2001:db8::dead") is not None
    assert src.query("1.2.3.4") is not None
    src._reader.close(); src._reader6.close()


def test_csv_v6_cidr_branches(tmp_path):
    """_cidr 与含 '/' 的 _ip 两个解析分支的 v6 形态(裸 IP 分支由上一测试盖)。"""
    class _S(CsvSource):
        name = "t_csv2"
        url = "https://example.com/x2.csv"
        filename = "x2.csv"
        fields = ("is_malicious",)
        delimiter = ","

        def parse_row(self, row):
            # 第二列 c → 走 _cidr 分支;否则 _ip 分支
            if len(row) > 1 and row[1].strip() == "c":
                return {"_cidr": row[0].strip()}
            return {"_ip": row[0].strip()}

    src = _S(tmp_path)
    (tmp_path / "x2.csv").write_text("2001:db8::/48,c\n10.0.0.0/24,\n2001:db9::/60,\n")
    src.rebuild()
    assert src._count == 1 and src._count6 == 2
    assert src.query("2001:db8:1::1") is not None   # _cidr 分支段内命中
    assert src.query("2001:db9::5") is not None     # '/' in _ip 分支
    src._reader.close(); src._reader6.close()
