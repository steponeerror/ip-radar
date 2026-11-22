"""CESNET NERD bad_ips_med_conf — IpListSource 最小面(binarydefense 模式).

夹具 verbatim 取自 2026-11-22 03:00 UTC 实抓(/tmp/nerd-eval-medconf.txt,
76,103 键/1,079,327 字节,小时更)。无差别指控 → blacklist 基类分类
(siberkapan/mirage 空标签同口径)。
"""
from pathlib import Path

from ipdb._sources.nerd_medconf import NerdMedConfSource

# verbatim 头两行 + 前 5 个数据行(实抓快照)
SAMPLE = (
    "# IP addresses in NERD database with reputation score over 0.2 (excluding whitelisted ones). Generated at 2026-11-22 03:00 UTC\n"
    "1.0.211.205\n"
    "1.10.246.160\n"
    "1.100.101.102\n"
    "1.105.106.107\n"
    "1.119.120.121\n"
)


def _build(tmp_path: Path) -> NerdMedConfSource:
    (tmp_path / "nerd_medconf.txt").write_text(SAMPLE, encoding="utf-8")
    return NerdMedConfSource(data_dir=tmp_path)


def test_comments_skipped_and_records_queryable(tmp_path: Path):
    s = _build(tmp_path)
    assert s.rebuild() == 5                     # '#' 头注释行不计
    rec = s.query("1.0.211.205")
    assert rec, "query must return a record"
    assert rec[0]["classification_type"] == "blacklist"
    assert rec[0]["verdict"] == "malicious"
    assert rec[0]["reliability"] == 0.60


def test_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    s = _build(tmp_path)
    s.rebuild()
    rec = s.query("1.10.246.160")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious",
        reliability=0.60,
    ).to_dict()
    assert "native_type" not in (rec.get("extra") or {})


def test_fresh_instance_load_reopens(tmp_path: Path):
    """LMDB 卫生(convention 7):rebuild 实例不复用,新实例重开同 env。"""
    s1 = _build(tmp_path)
    assert s1.rebuild() == 5
    s2 = NerdMedConfSource(data_dir=tmp_path)
    assert s2.load() == 5
    h = s2.health()
    assert h.record_count == 5
    assert h.is_stale is False                    # 刚写,stale_days=2


def test_absent_ip_resolves_empty(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    assert not s.query("203.0.113.42")            # TEST-NET-3,不在清单


def test_parse_raw_logs_upstream_generated_at(tmp_path: Path, caplog):
    """注释头 Generated at 时间戳进日志(新鲜度可见性;下载路径内联调用)。"""
    import logging
    s = NerdMedConfSource(data_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ipdb._sources.nerd_medconf"):
        entries = s.parse_raw(SAMPLE.encode("utf-8"))
    assert len(entries) == 5
    assert any("2026-11-22 03:00 UTC" in r.message for r in caplog.records)
