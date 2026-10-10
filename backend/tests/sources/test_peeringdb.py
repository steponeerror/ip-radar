"""peeringdb 源测试(信息维度批 2026-10-10,grill #4 口径)。"""
import pytest

from ipdb._sources import peeringdb as pdb
from ipdb._sources.peeringdb import PeeringDbSource, fetch_dataset


def test_fetch_all_paginates_until_short_page(monkeypatch):
    monkeypatch.setattr(pdb, "_PAGE_SLEEP", 0)   # 测试不真睡
    rows = [{"id": i} for i in range(pdb._PAGE_LIMIT + 3)]
    calls = []

    def fake(path, params):
        calls.append((path, params["offset"]))
        lo = params["offset"]
        return {"data": rows[lo:lo + pdb._PAGE_LIMIT]}

    monkeypatch.setattr(pdb, "_get_json", fake)
    got = pdb._fetch_all("/ixpfx", "ixpfx")
    assert len(got) == pdb._PAGE_LIMIT + 3
    assert [o for _, o in calls] == [0, pdb._PAGE_LIMIT]   # offset 步进,短页即停


def test_fetch_dataset_joins_name_and_filters_status(monkeypatch):
    canned = {
        "/ix": [{"id": 1, "name": "Equinix Ashburn"},
                {"id": 2, "name": "DE-CIX Frankfurt"}],
        "/ixlan": [{"id": 10, "ix_id": 1}, {"id": 11, "ix_id": 2},
                   {"id": 12, "ix_id": None}],
        "/ixpfx": [
            {"prefix": "206.223.115.0/24", "ixlan_id": 10,
             "in_dfz": True, "status": "ok"},
            {"prefix": "2001:504:0:2::/64", "ixlan_id": 11,
             "in_dfz": False, "status": "ok"},
            {"prefix": "10.0.0.0/24", "ixlan_id": 12,
             "in_dfz": False, "status": "deleted"},   # status 过滤
            {"prefix": "", "ixlan_id": 10, "in_dfz": True, "status": "ok"},
            {"prefix": "198.32.160.0/24", "ixlan_id": 999,
             "in_dfz": True, "status": "ok"},         # join 失链:保留空名
            {"prefix": "206.223.115.0/24", "ixlan_id": 11,
             "in_dfz": True, "status": "ok"},         # 同段重复:首见者胜
        ],
    }

    def fake(path, key, extra_params=None):
        return canned[path]

    monkeypatch.setattr(pdb, "_fetch_all", fake)
    text = fetch_dataset()
    lines = text.strip().splitlines()
    assert lines == [
        "206.223.115.0/24,Equinix Ashburn,1",
        "2001:504:0:2::/64,DE-CIX Frankfurt,0",
        "198.32.160.0/24,,1",
    ]


def test_download_guard_thin_payload_keeps_old(monkeypatch, tmp_path):
    src = PeeringDbSource(data_dir=tmp_path)
    src._data_dir.mkdir(parents=True, exist_ok=True)
    src._path.write_text("206.223.115.0/24,Old IX,1\n")
    monkeypatch.setattr(pdb, "fetch_dataset",
                        lambda: "1.2.3.0/24,Lone,1\n")
    with pytest.raises(RuntimeError, match="fail-closed"):
        src.download()
    assert src._path.read_text() == "206.223.115.0/24,Old IX,1\n"


def test_harvest_evidence_shape(tmp_path):
    src = PeeringDbSource(data_dir=tmp_path)
    src._path.write_text(
        "206.223.115.0/24,Equinix Ashburn,1\n"
        "2001:504:0:2::/64,DE-CIX Frankfurt,0\n")
    rows = list(src.harvest())
    assert [c for c, _ in rows] == ["206.223.115.0/24",
                                    "2001:504:0:2::/64"]
    a = rows[0][1]
    assert a.service == "ix"
    assert a.native_types == {"service": "Equinix Ashburn"}
    assert a.verdict == ""                       # 弃权:资产位不指控
    assert a.classification_type is None
    assert a.extra is None                       # in_dfz=1:多数路径零 extra
    b = rows[1][1]
    assert b.extra == {"in_dfz": False}          # 非 DFZ 证据保留
