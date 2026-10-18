"""malicious_ip (romainmarcoux/malicious-ip 5-shard union) — guard + shape.

Covers: rebuild/query round-trip on verbatim sample lines (2026-10-18 fetch,
bare-IP lines), Evidence-contract equality, junk-row drop, download guards —
per-shard 404/empty tolerated (shard rotation; full-300k-ae is currently 0B),
union below the 500k floor refuses to write (catastrophic-wipe guard),
all-shards-fail raises. Downloads stubbed at Source._http_get — no network
(cloud_ranges idiom); union floor monkeypatched to a small value so the guard
logic is tested without generating 500k rows.
"""
from pathlib import Path

import pytest

import ipdb._sources.malicious_ip as mod
from ipdb._sources.malicious_ip import MaliciousIPSource

# Verbatim-shaped sample of the feed (2026-10-18 fetch, full-40k.txt head).
SAMPLE = (
    "86.54.31.40\n"
    "86.54.31.38\n"
    "86.54.31.34\n"
    "not-an-ip\n"     # junk row → dropped
    "\n"              # blank → dropped
)


def test_malicious_ip_rebuilds_and_queries(tmp_path: Path):
    (tmp_path / "malicious_ip.txt").write_text(SAMPLE)
    s = MaliciousIPSource(data_dir=tmp_path)
    assert s.rebuild() == 3      # 3 valid IPs; junk + blank dropped
    rec = s.query("86.54.31.40")[0]
    assert rec["classification_type"] == "blacklist"
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.50
    assert "native_type" not in (rec.get("extra") or {})


def test_malicious_ip_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "malicious_ip.txt").write_text("9.9.9.9\n")
    s = MaliciousIPSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.50,
    ).to_dict()


def test_malicious_ip_non_present_ip_resolves_empty(tmp_path: Path):
    (tmp_path / "malicious_ip.txt").write_text("1.2.3.4\n")
    s = MaliciousIPSource(data_dir=tmp_path)
    s.load()
    assert not s.query("203.0.113.42")


def _urls() -> list[str]:
    return [f"{mod._BASE_URL}/{shard}.txt" for shard in mod._SHARDS]


def _patch_http(monkeypatch, responses: dict[str, object]) -> None:
    def fake_get(url, *, headers=None, timeout=120, retries=3):
        r = responses[url]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(MaliciousIPSource, "_http_get", staticmethod(fake_get))


def test_download_tolerates_missing_and_empty_shards(tmp_path, monkeypatch):
    """单片 404 + 单片空容忍(碎片轮换):并集照写,last_partial_failure 记名。"""
    monkeypatch.setattr(mod, "MIN_UNION_KEYS", 5)
    urls = _urls()
    ips = [f"10.0.0.{i}" for i in range(1, 7)]
    responses = {
        urls[0]: ("\n".join(ips[0:2]) + "\n").encode(),
        urls[1]: RuntimeError("HTTP 404"),          # 单片 404
        urls[2]: b"",                               # 单片空(ae 现状)
        urls[3]: ("\n".join(ips[2:5]) + "\n").encode(),
        urls[4]: ("\n".join(ips[4:6] + [ips[0]]) + "\n").encode(),  # 跨片重复
    }
    _patch_http(monkeypatch, responses)
    s = MaliciousIPSource(data_dir=tmp_path)
    s.download()
    assert sorted(set(ips)) == s._path.read_text().split()   # 排序去重落地
    assert s.last_partial_failure == [mod._SHARDS[1], mod._SHARDS[2]]


def test_download_refuses_write_below_union_floor(tmp_path, monkeypatch):
    """并集 < 地板 = 拒写不落盘(防灾难性全空清库),scratch 不留。"""
    monkeypatch.setattr(mod, "MIN_UNION_KEYS", 10)
    responses = {u: b"10.0.0.1\n10.0.0.2\n" for u in _urls()}
    _patch_http(monkeypatch, responses)
    s = MaliciousIPSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="refus"):
        s.download()
    assert not any(tmp_path.iterdir())   # 数据文件与 scratch 均未落地


def test_download_all_shards_fail_raises(tmp_path, monkeypatch):
    responses = {u: RuntimeError("network down") for u in _urls()}
    _patch_http(monkeypatch, responses)
    s = MaliciousIPSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="all malicious_ip shards failed"):
        s.download()
    assert not (tmp_path / "malicious_ip.txt").exists()
