"""ziyadnz aggregated threat feed (CsvSource) — Evidence shape assertions.

Covers: header skip (skip_lines=1), bare-IP and CIDR rows kept, per-row
lineage routing (sources |split → extra.sources, source_count/confidence →
extra per grill Q3 2026-10-18, raw category → native_categories verbatim,
first_seen/last_seen pass-through), dirty-row drops (ipv6 type gate /
invalid-IP / invalid-CIDR / short row / empty line), multi-evidence CIDR
survival (Convention 3), and the DQ-2 count contract (record_count = env key
count, not evidence rows — the pre-b2843b13 CsvSource wording).
"""
from pathlib import Path

from ipdb._sources.ziyadnz import ZiyadnzSource

# Verbatim-shaped sample of ziyadnz/threat-intel-ip-feeds output/blacklist.csv
# (2026-10-18 fetch): header row, bare IPs, one CIDR row, a repeated CIDR with
# distinct evidence, and dirty rows of every drop class.
SAMPLE = (
    "ip,type,is_cidr,sources,source_count,category,confidence,first_seen,last_seen\n"
    "1.2.3.4,ipv4,False,AbuseIPDB|Stamparm IPsum,2,crowd-sourced,60,"
    "2026-10-18T11:06:13.663265+00:00,2026-10-18T11:06:13.663265+00:00\n"
    "5.6.7.8,ipv4,False,RTBH (Turkiye),1,government-feed,20,"
    "2026-10-17T00:00:00+00:00,2026-10-17T00:00:00+00:00\n"
    "1.10.16.0/20,ipv4,True,Spamhaus DROP,1,infrastructure,20,"
    "2026-10-16T00:00:00+00:00,2026-10-16T00:00:00+00:00\n"
    "45.148.65.28,ipv4,False,CINS Army|SGB (Turkiye),2,scanner,40,"
    "2026-10-15T00:00:00+00:00,2026-10-15T00:00:00+00:00\n"
    "45.148.65.28,ipv4,False,CINS Army,1,multi-source,50,"
    "2026-10-14T00:00:00+00:00,2026-10-14T00:00:00+00:00\n"
    "2001:db8::1,ipv6,False,SomeSource,1,crowd-sourced,20,"
    "2026-10-13T00:00:00+00:00,2026-10-13T00:00:00+00:00\n"
    "not-an-ip,ipv4,False,X,1,crowd-sourced,20,"
    "2026-10-12T00:00:00+00:00,2026-10-12T00:00:00+00:00\n"
    "1.2.3.4/33,ipv4,True,X,1,crowd-sourced,20,"
    "2026-10-12T00:00:00+00:00,2026-10-12T00:00:00+00:00\n"
    "1.0.0.1,ipv4,False,X,1,crowd-sourced\n"
    "\n"
)


def test_ziyadnz_loads_blacklist_csv(tmp_path: Path):
    (tmp_path / "ziyadnz.csv").write_text(SAMPLE)
    s = ZiyadnzSource(data_dir=tmp_path)
    # CsvSource 口径:distinct CIDR keys —— 1.2.3.4/32 + 5.6.7.8/32 +
    # 45.148.65.28/32(双证据并一键)+ 1.10.16.0/20;表头/v6/脏行/空行全弃
    # (样本 IP 避开 curated infra 集:ziyadnz 载入面排 infra 噪声,issue #183)。
    assert s.rebuild() == 4
    # DQ-2(b2843b13):record_count = env 主库键数;证据行 6 ≠ 键数 4。
    assert s.health().record_count == 4
    rec = s.query("1.2.3.4")[0]
    assert rec["classification_type"] == "blacklist"
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.55
    assert rec["native_categories"] == ["crowd-sourced"]      # category 原值(three-way rule)
    assert rec["first_seen"] == "2026-10-18T11:06:13.663265+00:00"
    assert rec["last_seen"] == "2026-10-18T11:06:13.663265+00:00"
    assert rec["extra"]["sources"] == ["AbuseIPDB", "Stamparm IPsum"]   # 按 | 拆
    assert rec["extra"]["source_count"] == 2
    assert rec["extra"]["confidence"] == 60                    # grill Q3:→ extra
    assert "native_type" not in (rec.get("extra") or {})       # dead convention
    assert s.query("203.0.113.42") == {}   # not in feed


def test_ziyadnz_cidr_row_kept_and_member_queryable(tmp_path: Path):
    (tmp_path / "ziyadnz.csv").write_text(SAMPLE)
    s = ZiyadnzSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("1.10.23.7")[0]     # member of 1.10.16.0/20
    assert rec["native_categories"] == ["infrastructure"]
    assert rec["extra"]["sources"] == ["Spamhaus DROP"]


def test_ziyadnz_multi_evidence_cidr_survives(tmp_path: Path):
    (tmp_path / "ziyadnz.csv").write_text(SAMPLE)
    s = ZiyadnzSource(data_dir=tmp_path)
    s.rebuild()
    evs = s.query("45.148.65.28")
    # same CIDR, distinct evidence rows — both survive (Convention 3, no pre-collapse)
    assert len(evs) == 2
    assert {tuple(e["extra"]["sources"]) for e in evs} == {
        ("CINS Army", "SGB (Turkiye)"), ("CINS Army",)}


def test_ziyadnz_record_is_evidence_contract(tmp_path: Path):
    from ipdb._evidence import Evidence
    (tmp_path / "ziyadnz.csv").write_text(SAMPLE)
    s = ZiyadnzSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("5.6.7.8")[0]
    assert rec == Evidence(
        classification_type="blacklist", verdict="malicious", reliability=0.55,
        first_seen="2026-10-17T00:00:00+00:00",
        last_seen="2026-10-17T00:00:00+00:00",
        native_categories=["government-feed"],
        extra={"sources": ["RTBH (Turkiye)"], "source_count": 1,
               "confidence": 20},
    ).to_dict()
