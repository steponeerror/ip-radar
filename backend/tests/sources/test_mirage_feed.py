"""Mirage Feed (Source subclass) — per-row multi-tag classification + N-evidence.

Covers: tags grouped by canonical type (one Evidence per group, reportedip
pattern), raw tags preserved in native_categories, per-row shared fields
(confidence/first_seen/last_seen/asn/as_name/country/reporter_count=hits),
services/attack/sensors/networks/cves/kev riding in extra, empty-tags rows
falling back to blacklist, empty country → country_code omitted, kev=true ⟺
cves non-empty, mirai-like → infected-system, rdp-only rows → brute-force.

Fixture rows are VERBATIM from the real full attackers-7d.csv (fetched
2026-11-18, md5 81820c70c97c9e9509c8905dc8edc6eb, 2107 data rows), including
dirty/edge rows: empty tags, empty services, empty country, quoted as_org with
embedded comma ("aamra networks limited,"), kev=true with CVE, first_seen ==
last_seen.
"""
from pathlib import Path

from ipdb._sources.mirage_feed import MirageFeedSource
from ipdb._sources.mirage_feed import MIRAGE_MAP

# Header + 7 verbatim rows from attackers-7d.csv (2026-11-18 snapshot).
SAMPLE = (
    "ip,asn,as_org,country,first_seen,last_seen,services,tags,cves,kev,attack,sensors,networks,hits,confidence\n"
    # single tag web-exploit; quoted as_org with comma; empty cves; kev=false
    '1.12.70.96,45090,"Tencent cloud computing (Beijing) Co., Ltd.",CN,2026-11-03T04:00:00Z,2026-11-17T01:00:00Z,http,web-exploit,,false,T1110;T1190;T1595,5,2,31,42\n'
    # two tags → brute-force + exploit groups; unquoted as_org; hits=315
    '2.57.121.25,47890,UNMANAGED-DEDICATED-SERVERS UNMANAGED LTD,RO,2026-10-19T00:00:00Z,2026-11-17T21:00:00Z,http;ssh,ssh-bruteforce;web-exploit,,false,T1078;T1090;T1110;T1190;T1572;T1592.002,7,4,315,77\n'
    # DIRTY/EDGE: empty tags + empty services; quoted as_org with trailing comma inside
    '45.64.134.75,24323,"aamra networks limited,",BD,2026-10-20T05:00:00Z,2026-11-14T13:00:00Z,,,,false,T1046;T1595,3,2,16,30\n'
    # EDGE: empty country; tor-exit context tag → tor group
    '37.114.63.5,58087,FlorianKolb Florian Kolb,,2026-10-27T07:00:00Z,2026-11-12T19:00:00Z,http,tor-exit;web-exploit,,false,T1110;T1190;T1589.002;T1595,6,4,23,68\n'
    # kev=true with CVE; shell-commands → other
    '23.132.164.50,401626,"Netiface America, Inc.",US,2026-11-06T00:00:00Z,2026-11-13T16:00:00Z,http;ssh,shell-commands;ssh-bruteforce;web-exploit,CVE-2017-9841,true,T1059;T1110;T1190;T1552.001,9,4,82,93\n'
    # mirai-like → infected-system
    '2.57.122.150,47890,UNMANAGED-DEDICATED-SERVERS UNMANAGED LTD,RO,2026-10-19T03:00:00Z,2026-11-15T20:00:00Z,ssh,mirai-like;shell-commands;ssh-bruteforce,,false,T1059;T1059.004;T1078;T1105;T1110;T1592.002,5,3,170,61\n'
    # EDGE: rdp as the only tag; first_seen == last_seen
    '5.78.108.120,212317,Hetzner Online GmbH,US,2026-11-16T04:00:00Z,2026-11-16T04:00:00Z,rdp,rdp,,false,T1021.001;T1110;T1210,5,5,6,69\n'
)


def _build(tmp_path: Path) -> MirageFeedSource:
    (tmp_path / "mirage_feed.csv").write_text(SAMPLE, encoding="utf-8")
    return MirageFeedSource(data_dir=tmp_path)


def test_mirage_grouped_by_canonical_type(tmp_path: Path):
    s = _build(tmp_path)
    assert s.rebuild() == 7                       # 7 distinct IPv4 addresses

    two = s.query("2.57.121.25")
    assert len(two) == 2                          # ssh-bruteforce;web-exploit → 2 groups
    by_type = {e["classification_type"]: e for e in two}
    assert set(by_type) == {"brute-force", "exploit"}
    assert by_type["brute-force"]["native_categories"] == ["ssh-bruteforce"]
    assert by_type["exploit"]["native_categories"] == ["web-exploit"]
    for e in two:                                 # per-row shared fields on every evidence
        assert e["verdict"] == "malicious"
        assert e["confidence"] == 77
        assert e["first_seen"] == "2026-10-19T00:00:00Z"
        assert e["last_seen"] == "2026-11-17T21:00:00Z"
        assert e["asn"] == 47890
        assert e["as_name"] == "UNMANAGED-DEDICATED-SERVERS UNMANAGED LTD"
        assert e["country_code"] == "RO"
        assert e["reporter_count"] == 315         # hits → reporter_count (dshield attacks_n precedent)
        assert e["extra"]["services"] == ["http", "ssh"]
        assert e["extra"]["attack"] == [
            "T1078", "T1090", "T1110", "T1190", "T1572", "T1592.002"]
        assert e["extra"]["sensors"] == 7
        assert e["extra"]["networks"] == 4
        assert "kev" not in e["extra"]            # kev=false → omitted
        assert "cves" not in e["extra"]           # empty cves → omitted


def test_mirage_single_tag_row_quoted_as_org(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    one = s.query("1.12.70.96")
    assert len(one) == 1
    assert one[0]["classification_type"] == "exploit"
    assert one[0]["native_categories"] == ["web-exploit"]
    assert one[0]["as_name"] == "Tencent cloud computing (Beijing) Co., Ltd."  # CSV-quoted, comma intact
    assert one[0]["country_code"] == "CN"


def test_mirage_empty_tags_fallback_blacklist(tmp_path: Path):
    """Empty tags (19 rows in the real snapshot) = undifferentiated sensor
    accusation → blacklist (vocab: 'no subcategory available'; siberkapan
    precedent), native_categories empty, empty services omitted from extra."""
    s = _build(tmp_path)
    s.rebuild()
    rec = s.query("45.64.134.75")
    assert len(rec) == 1
    assert rec[0]["classification_type"] == "blacklist"
    assert "native_categories" not in rec[0]     # empty list → omitted by to_dict()
    assert rec[0]["as_name"] == "aamra networks limited,"   # trailing comma inside quotes survives
    ex = rec[0]["extra"]
    assert "services" not in ex                     # empty services → omitted
    assert ex["attack"] == ["T1046", "T1595"]
    assert ex["sensors"] == 3 and ex["networks"] == 2
    assert rec[0]["confidence"] == 30


def test_mirage_empty_country_omitted_tor_exit_maps_tor(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    recs = s.query("37.114.63.5")
    by_type = {e["classification_type"]: e for e in recs}
    assert set(by_type) == {"tor", "exploit"}       # tor-exit;web-exploit
    assert by_type["tor"]["native_categories"] == ["tor-exit"]
    for e in recs:
        assert "country_code" not in e              # empty country → omitted, not ""


def test_mirage_kev_true_carries_cves(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    recs = s.query("23.132.164.50")
    by_type = {e["classification_type"]: e for e in recs}
    assert set(by_type) == {"other", "brute-force", "exploit"}  # shell-commands;ssh-bruteforce;web-exploit
    assert by_type["other"]["native_categories"] == ["shell-commands"]
    for e in recs:
        assert e["extra"]["kev"] is True
        assert e["extra"]["cves"] == ["CVE-2017-9841"]
        assert e["confidence"] == 93


def test_mirage_mirai_like_maps_infected_system(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    recs = s.query("2.57.122.150")
    by_type = {e["classification_type"]: e for e in recs}
    assert set(by_type) == {"infected-system", "other", "brute-force"}
    assert by_type["infected-system"]["native_categories"] == ["mirai-like"]


def test_mirage_rdp_only_row_single_bruteforce(tmp_path: Path):
    """tags == 'rdp' alone (167 rows in the real snapshot) → one brute-force
    evidence; first_seen == last_seen boundary carried verbatim."""
    s = _build(tmp_path)
    s.rebuild()
    rec = s.query("5.78.108.120")
    assert len(rec) == 1
    assert rec[0]["classification_type"] == "brute-force"
    assert rec[0]["native_categories"] == ["rdp"]
    assert rec[0]["first_seen"] == "2026-11-16T04:00:00Z"
    assert rec[0]["last_seen"] == "2026-11-16T04:00:00Z"


def test_mirage_map_covers_observed_tag_vocabulary():
    """All 18 tags observed in the 2026-11-18 full snapshot have explicit
    MIRAGE_MAP entries — upstream renames/additions must trip this, not
    silently fall to 'other'."""
    observed = {
        "web-exploit", "vnc-bruteforce", "rdp", "db-bruteforce", "tor-exit",
        "mail-bruteforce", "ssh-bruteforce", "db-ransom", "shell-commands",
        "vpn-bruteforce", "smb", "vpn-exit", "sip-bruteforce", "web-scan",
        "sip-fraud", "telnet-bruteforce", "mirai-like", "cgnat",
    }
    assert set(MIRAGE_MAP) == observed
