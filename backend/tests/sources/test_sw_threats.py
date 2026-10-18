"""sw_threats (ShadowWhisperer/IPs · Threats.csv, CsvSource) — Evidence shape assertions.

Covers: header skip (skip_lines=1), the three-way classification contract
(mapped categories hit the controlled vocabulary — botnet node→infected-system
/ recon→scanner / exploit→exploit / dropper host→malware-distribution;
unmappable abuse/intrusion → other with raw values alive in
native_categories), native_categories = [category, detail] verbatim,
bracketed pipe tags → tags slot, note → extra, first_seen/last_seen
(YYYY-MM-DD) pass-through, dirty-row / bad-date drops, and the DQ-2 count
contract (record_count = env key count).
"""
from pathlib import Path

from ipdb._sources.sw_threats import SWThreatsSource

# Verbatim-shaped sample of ShadowWhisperer/IPs Lists/Threats.csv
# (2026-10-18 fetch): header, one row per category (incl. the quoted-comma
# note form), empty detail/tags/note cells, and dirty rows of every drop class.
SAMPLE = (
    "ip,category,detail,note,tags,first_seen,last_seen\n"
    "1.242.43.91,abuse,proxy-abuse,SSH port-forward abuse"
    " (HTTPS proxy tunnel to external host),[abuse|proxy|ssh|ssh-tunnel],"
    "2026-10-11,2026-10-11\n"
    "1.0.214.202,botnet node,mirai,Mirai-family shell-verification handshake,"
    "[handshake|mirai|worm],2026-07-13,2026-07-13\n"
    "1.24.16.65,recon,ics,Modbus device identification,[ics|modbus],"
    "2026-09-22,2026-09-22\n"
    "1.24.16.144,intrusion,remote,VNC session established,[remote|vnc],"
    "2026-08-31,2026-08-31\n"
    "3.16.155.161,exploit,router,CVE-2018-14847,[cve|mikrotik|router|rce],"
    "2026-07-24,2026-07-24\n"
    "5.75.162.206,dropper host,,,,2026-09-13,2026-09-14\n"
    '9.9.9.9,recon,voip,"SIP-only, high connect volume",[sip|voip],'
    "2026-07-07,2026-07-13\n"
    "not-an-ip,abuse,proxy-abuse,note,[abuse],2026-10-11,2026-10-11\n"
    "1.2.3.5,abuse,proxy-abuse,note,[abuse],2026-13-45,2026-10-11\n"
    "1.2.3.6,abuse,proxy-abuse,note,[abuse]\n"
    "\n"
)


def _source(tmp_path: Path) -> SWThreatsSource:
    (tmp_path / "sw_threats.csv").write_text(SAMPLE)
    return SWThreatsSource(data_dir=tmp_path)


def test_sw_threats_rebuilds_and_counts_keys(tmp_path: Path):
    s = _source(tmp_path)
    # 表头/脏行(not-an-ip/坏日期 2026-13-45/短行)全弃;7 个有效键。
    assert s.rebuild() == 7
    # DQ-2(b2843b13):record_count = env 主库键数。
    assert s.health().record_count == 7


def test_sw_threats_mapped_categories_hit_vocabulary(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    assert s.query("1.0.214.202")[0]["classification_type"] == "infected-system"
    assert s.query("1.0.214.202")[0]["native_categories"] == ["botnet node", "mirai"]
    assert s.query("1.24.16.65")[0]["classification_type"] == "scanner"
    assert s.query("3.16.155.161")[0]["classification_type"] == "exploit"
    rec = s.query("5.75.162.206")[0]
    assert rec["classification_type"] == "malware-distribution"
    # 空 detail 不进 native;空 tags/note 不发键(to_dict 丢空契约)。
    assert rec["native_categories"] == ["dropper host"]
    assert "tags" not in rec
    assert "extra" not in rec


def test_sw_threats_unmapped_falls_to_other_with_natives_alive(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("1.242.43.91")[0]
    assert rec["classification_type"] == "other"      # abuse 勿强拟合
    assert rec["native_categories"] == ["abuse", "proxy-abuse"]
    rec = s.query("1.24.16.144")[0]
    assert rec["classification_type"] == "other"      # intrusion 勿强拟合
    assert rec["native_categories"] == ["intrusion", "remote"]


def test_sw_threats_tags_note_dates_routing(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("1.242.43.91")[0]
    assert rec["tags"] == ["abuse", "proxy", "ssh", "ssh-tunnel"]   # 剥 [] 按 | 拆
    assert rec["extra"]["note"] == ("SSH port-forward abuse"
                                    " (HTTPS proxy tunnel to external host)")
    assert rec["first_seen"] == "2026-10-11"
    assert rec["last_seen"] == "2026-10-11"
    # 引号内逗号 note 完整存活(csv 引号规则)。
    rec = s.query("9.9.9.9")[0]
    assert rec["extra"]["note"] == "SIP-only, high connect volume"
    assert rec["tags"] == ["sip", "voip"]
    assert "native_type" not in (rec.get("extra") or {})            # dead convention


def test_sw_threats_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("9.9.9.9")[0]
    assert rec == Evidence(
        classification_type="scanner", verdict="malicious", reliability=0.55,
        first_seen="2026-07-07", last_seen="2026-07-13",
        native_categories=["recon", "voip"],
        tags=["sip", "voip"],
        extra={"note": "SIP-only, high connect volume"},
    ).to_dict()


def test_sw_threats_dirty_rows_dropped(tmp_path: Path):
    s = _source(tmp_path)
    s.rebuild()
    assert s.query("1.2.3.5") == {}     # 坏日期行(2026-13-45)不落库
    assert s.query("203.0.113.42") == {}   # not in feed
