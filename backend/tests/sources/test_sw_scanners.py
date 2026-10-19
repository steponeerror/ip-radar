"""sw_scanners (ShadowWhisperer/IPs · Scanners.csv, CsvSource) — Evidence shape assertions.

Covers: header skip (skip_lines=1), all rows → scanner/malicious with the
declared r=0.55 (turris_greylist same-slot precedent; no per-row category
column so no normalize map), company → extra["company"] passenger
(urlhaus reporter precedent) incl. quoted-comma survival and empty-company
no-extra (to_dict drops-empty contract), dirty-row (bad IP / short row)
drops, and the DQ-2 count contract (record_count = env key count).
"""
from pathlib import Path

from ipdb._sources.sw_scanners import SWScannersSource

# Verbatim-shaped sample of ShadowWhisperer/IPs Lists/Scanners.csv
# (2026-10-19 fetch): header `ip,company`, real rows (A10 Networks is the
# feed's dominant company), a quoted-comma company, an empty company cell,
# and dirty rows of every drop class.
SAMPLE = (
    "ip,company\n"
    "23.92.21.53,A10 Networks\n"
    '9.9.9.9,"Tripwire, Inc."\n'
    "1.2.3.4,\n"
    "not-an-ip,A10 Networks\n"
    "1.2.3.5\n"
    "\n"
)


def _source(tmp_path: Path) -> SWScannersSource:
    (tmp_path / "sw_scanners.csv").write_text(SAMPLE)
    return SWScannersSource(data_dir=tmp_path)


def test_sw_scanners_rebuilds_and_counts_keys(tmp_path: Path):
    s = _source(tmp_path)
    # 表头/脏行(not-an-ip/短行 1.2.3.5)全弃;3 个有效键。
    assert s.rebuild() == 3
    # DQ-2(b2843b13):record_count = env 主库键数。
    assert s.health().record_count == 3


def test_sw_scanners_query_routes_scanner_malicious(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("23.92.21.53")[0]
    assert rec["classification_type"] == "scanner"   # scanner 槽 4 源先例同词
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.55
    assert rec["extra"]["company"] == "A10 Networks"
    assert "native_type" not in (rec.get("extra") or {})   # dead convention


def test_sw_scanners_company_quoting_and_empty_cell(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    # 引号内逗号 company 完整存活(csv 引号规则)。
    assert s.query("9.9.9.9")[0]["extra"]["company"] == "Tripwire, Inc."
    # 空 company 不发 extra 键(to_dict 丢空契约)。
    rec = s.query("1.2.3.4")[0]
    assert "extra" not in rec


def test_sw_scanners_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("23.92.21.53")[0]
    assert rec == Evidence(
        classification_type="scanner", verdict="malicious", reliability=0.55,
        extra={"company": "A10 Networks"},
    ).to_dict()


def test_sw_scanners_dirty_rows_dropped(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    assert s.query("203.0.113.42") == {}   # not in feed
    # not-an-ip / 裸行(无 company 列)在 rebuild 解析期弃,不落库
    # (query 只收合法 IP;不落库由 rebuild==3 键数断言钉住)。
