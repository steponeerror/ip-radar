"""gorkemgun/sgb-blocklist — IpListSource tests.
Hourly GitHub mirror of the Turkish Cyber Security Presidency (Siber Güvenlik
Başkanlığı, ex-USOM) malicious address API. Data file: ipv4.txt — 4-line '#'
header (title / Source / Records / Last change) then one bare IPv4 per line.
2026-11-20 live fetch: 16,568 lines total, all non-comment lines valid bare
IPv4 (no CIDR, no dirty rows); CIDR handling asserted per list-archetype
convention (base parser/rebuild pass-through, emerging_threats style).
"""
from pathlib import Path
from ipdb._sources.gorkemgun_sgb_blocklist import GorkemgunSgbBlocklistSource

# Header lines verbatim from the live 2026-11-20 ipv4.txt; body lines
# verbatim from the same fetch (first records of the file + a C&C slice one).
HEADER = (
    "# T.C. Siber Guvenlik Baskanligi - IPv4 address - all categories\n"
    "# Source : https://siberguvenlik.gov.tr/api/address/index?type=ip\n"
    "# Records: 16564\n"
    "# Last change: 2026-11-20 13:01:30 UTC (sync mode: delta)\n"
)


def test_config():
    assert GorkemgunSgbBlocklistSource.name == "gorkemgun_sgb_blocklist"
    assert GorkemgunSgbBlocklistSource.category == "threat"
    assert GorkemgunSgbBlocklistSource.classification_type == "blacklist"
    assert GorkemgunSgbBlocklistSource.authoritative_for == ()
    assert GorkemgunSgbBlocklistSource.reliability == 0.60


def test_loads_bare_ips_skips_header_and_blank(tmp_path: Path):
    (tmp_path / "sgb_ipv4.txt").write_text(
        HEADER
        + "1.12.37.113\n"
        + "1.13.102.222\n"
        + "1.32.249.20\n"
        + "\n"
    )
    s = GorkemgunSgbBlocklistSource(data_dir=tmp_path)
    assert s.rebuild() == 3                    # 4 '#' header lines + blank = noise, not keys
    rec = s.query("1.13.102.222")[0]
    assert rec["classification_type"] == "blacklist"
    assert rec["verdict"] == "malicious"
    assert s.query("9.9.9.9") == {}            # miss → empty dict


def test_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "sgb_ipv4.txt").write_text(HEADER + "223.194.70.136\n")
    s = GorkemgunSgbBlocklistSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("223.194.70.136")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.60,
    ).to_dict()
    assert "native_type" not in (rec.get("extra") or {})  # undifferentiated → no force-fit


def test_cidr_line_is_member_queryable(tmp_path: Path):
    """List-archetype convention: CIDR rows pass the base parser and answer
    member queries (live ipv4.txt is bare-IP-only today; base contract kept)."""
    (tmp_path / "sgb_ipv4.txt").write_text(HEADER + "203.0.113.0/24\n")
    s = GorkemgunSgbBlocklistSource(data_dir=tmp_path)
    assert s.rebuild() == 1
    assert s.query("203.0.113.42")[0]["classification_type"] == "blacklist"
    assert s.query("203.0.112.42") == {}       # outside prefix → no partial hit
