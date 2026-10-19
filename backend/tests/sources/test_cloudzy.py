"""cloudzy (Source subclass) — CPS-mirrored Cloudzy VPS ranges, asset axis.

Synthetic mini fixture only (offline; bare-IPv4 lines shaped like the live
feed, which ends without a trailing newline) — real feed numbers are NOT
pinned, upstream drifts (2026-10-19 measured 3,578 keys, recorded in the
source docstring). Phase-1 slot decision pinned here: is_hosting=True 票 +
native label "Cloudzy" (既有 ASSET_SLOTS 槽;选项 B 的 service="hosting" 是
新造 service 角色值,违反不发明词表值纪律), verdict="" 弃权拼写读回不兑底
(R17A-1), 无 classification_type = 永不入 threat 观测(registry 融合门
`if "classification_type" in item` 的缺席形状)。
"""
from pathlib import Path

import pytest

from ipdb._sources.cloudzy import CloudzySource


def _fixture() -> str:
    # 尾行无 \n(活体 feed 实测形态);夹带空行/注释/坏行/散文行钉 skip 语义
    return ("203.0.113.10\n"
            "203.0.113.11\n"
            "\n"
            "# comment noise — live feed has none today, skipped anyway\n"
            "203.0.113.999\n"          # invalid octet
            "Maintenance commit\n"     # prose drift noise
            "198.51.100.7")            # last line, no trailing newline


def test_cloudzy_rebuild_bare_ip_list(tmp_path: Path):
    (tmp_path / "cloudzy.txt").write_text(_fixture())
    s = CloudzySource(data_dir=tmp_path)
    assert s.rebuild() == 3             # 203.0.113.10 / .11 / 198.51.100.7
    h = s.health()
    assert h.record_count == 3
    assert h.covered_ips == 3           # 3 个 /32 单址
    assert h.is_stale is False          # 样本刚写盘,stale_days=30


def test_cloudzy_query_asset_statement_shape(tmp_path: Path):
    (tmp_path / "cloudzy.txt").write_text(_fixture())
    s = CloudzySource(data_dir=tmp_path)
    s.rebuild()
    # 精确契约:只带 is_hosting 票 + native label + 弃权 verdict,别无他键
    assert s.query("203.0.113.10")[0] == {
        "is_hosting": True,
        "_native_types": {"is_hosting": "Cloudzy"},
        "verdict": "",                  # R17A-1: 弃权拼写读回按 "" 不兑底
    }


def test_cloudzy_asset_only_never_accuses(tmp_path: Path):
    """无 verdict 污染断言:asset 位不得以指控身份进威胁融合——存储 dict 不带
    classification_type(registry 融合门 `if "classification_type" in item`
    因此永不产观测/分类组/STIX Indicator),verdict 读回恒 "" 非 malicious。"""
    (tmp_path / "cloudzy.txt").write_text(_fixture())
    s = CloudzySource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("198.51.100.7")[0]
    assert "classification_type" not in rec
    assert rec["verdict"] == ""
    assert s.query("192.0.2.99") == {}  # 未在册 IP 空


def test_cloudzy_download_guard_rejects_thin_payload(tmp_path: Path, monkeypatch):
    """200-OK 坏页守卫:<100 可解析 IP 行即失败,且失败不落盘(空/坏文件会被
    下次 rebuild 静默清源,skill Phase 3 §8;dns_public 同款打桩)。"""
    s = CloudzySource(data_dir=tmp_path)
    monkeypatch.setattr(
        CloudzySource, "_http_get",
        staticmethod(lambda *a, **k: b"<html>404</html>\nnot-an-ip\n"))
    with pytest.raises(RuntimeError):
        s.download()
    assert not s._path.exists()         # 原子写未发生,数据文件未被触碰
