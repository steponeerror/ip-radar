"""Source 基类 v6 状态与分派(load/query/rebuild)。"""
from pathlib import Path

from ipdb._source_base import Source
from ipdb._evidence import Evidence


class _FakeV6Source(Source):
    name = "fake_v6"
    fields = ("country_code",)
    filename = "fake.csv"
    single_evidence = True

    def harvest(self):
        yield "10.0.0.0/24", Evidence(country_code="XX")
        yield "2001:db8::/32", Evidence(country_code="YY")


def _mk(tmp_path: Path) -> _FakeV6Source:
    src = _FakeV6Source(tmp_path)
    (tmp_path / "fake.csv").write_text("placeholder\n")
    return src


def test_rebuild_writes_both_families(tmp_path):
    src = _mk(tmp_path)
    n = src.rebuild()
    assert n == 1                                  # 返回值语义:v4 记录数(兼容现状)
    assert src._count == 1 and src._count6 == 1
    assert src._covered_ips == 256
    assert src._covered_v6_nets == 1               # count-as-1
    assert src._reader is not None and src._reader6 is not None
    assert (tmp_path / "fake.csv.v6.lmdb.ptr").exists()


def test_query_dispatches_by_family(tmp_path):
    src = _mk(tmp_path)
    src.rebuild()
    # query() 契约:evidence source 返回 list[dict](见 test_source_query_shapes)
    assert src.query("10.0.0.5")[0].get("country_code") == "XX"
    assert src.query("2001:db8::9")[0].get("country_code") == "YY"
    src._reader6 = None
    assert src.query("2001:db8::9") == {}          # 无 v6 env → 安静空
    src._reader = None
    assert src.query("10.0.0.5") == {}             # v4 路径现状不变


def test_load_reads_v6_sidecars(tmp_path):
    src = _mk(tmp_path)
    src.rebuild()
    src._reader.close(); src._reader6.close()
    src._reader = src._reader6 = None
    src._count = src._count6 = src._covered_ips = src._covered_v6_nets = 0
    n = src.load()
    assert n == 1
    assert src._count6 == 1 and src._covered_v6_nets == 1
    assert src._reader6 is not None
    assert src.query("2001:db8::9")[0].get("country_code") == "YY"


def test_load_without_v6_ptr_is_quiet_miss(tmp_path):
    """旧数据目录(无 v6 sidecar):load 正常,v6 查询空。"""
    import shutil
    src = _mk(tmp_path)
    src.rebuild()
    src._reader.close(); src._reader6.close()
    for p in tmp_path.glob("fake.csv.v6.lmdb*"):
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    src.load()
    assert src._reader6 is None
    assert src.query("2001:db8::9") == {}
    assert src.query("10.0.0.5")[0].get("country_code") == "XX"   # v4 不受影响
