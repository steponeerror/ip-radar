"""ThreatClusterSource feed.csv parse_row / dual-family rebuild tests.

Fixture mirrors the 2026-10-14 upstream shape (header
`type,value,confidence,first_seen,last_seen,source_count,sources,reason`;
timestamps ISO-8601 with +00:00 — see plan 2026-10-14-threatcluster-feedcsv).
"""
from datetime import datetime, timezone

from ipdb._logodds import parse_first_seen
from pathlib import Path

from ipdb._sources.threatcluster import ThreatClusterSource

# Verbatim-shaped sample of threatcluster.io/api/iocs/public/feed.csv:
# header + ipv4 full-context row + ipv6 row + domain row + empty-value row +
# unknown-confidence-label row + ragged row + absent-branch rows.
_SAMPLE = (
    "type,value,confidence,first_seen,last_seen,source_count,sources,reason\n"
    "ipv4,108.165.147.64,high,2026-10-13T17:33:11+00:00,"
    "2026-10-14T03:31:37.389774+00:00,2,"
    "www.volexity.com:2026-10-14|Feeds.Feedburner:2026-10-13,"
    "Identified as a host used by the attacker for malicious operations\n"
    "ipv6,2001:db8::dead,medium,2026-10-12T09:15:00+00:00,"
    "2026-10-13T10:15:00+00:00,1,www.watchguard.com:2026-10-13,Malicious v6 host\n"
    "domain,firebox-ssl.com,high,2026-10-13T21:32:17.966241+00:00,"
    "2026-10-13T21:32:17.966241+00:00,1,www.watchguard.com:2026-10-13,"
    "Domain hosting malicious credential-stealing application\n"
    "ipv4,,high,2026-10-13T17:33:11+00:00,2026-10-14T03:31:37+00:00,1,"
    "src:2026-10-13,empty value row\n"
    "ipv4,203.0.113.7,critical,2026-10-13T18:00:00+00:00,"
    "2026-10-13T19:00:00+00:00,3,srcA:2026-10-13|srcB:2026-10-14,unknown label row\n"
    "ipv4\n"
    "ipv4,192.0.2.55,low,2026-10-11T08:00:00+00:00,,notanint,,\n"
    "ipv4,198.51.100.99,medium,2026-10-10T00:00:00+00:00\n"
)


def test_parse_row_filters_non_ip_rows():
    s = ThreatClusterSource(data_dir=Path("/tmp"))
    assert s.parse_row(
        ["domain", "firebox-ssl.com", "high", "2026-10-13T21:32:17.966241+00:00",
         "2026-10-13T21:32:17.966241+00:00", "1", "src:2026-10-13",
         "Domain hosting malicious credential-stealing application"]) is None
    assert s.parse_row(["ipv4", "", "high", "ts", "ts", "1", "src", "why"]) is None
    assert s.parse_row(["ipv4"]) is None                      # ragged (len < 2)
    assert s.parse_row([]) is None
    # header remnant / stray line inside the data body
    assert s.parse_row(["type", "value", "confidence", "first_seen", "last_seen",
                        "source_count", "sources", "reason"]) is None


def test_parse_row_ipv4_full_context():
    s = ThreatClusterSource(data_dir=Path("/tmp"))
    out = s.parse_row(
        ["ipv4", " 108.165.147.64 ", "high", "2026-10-13T17:33:11+00:00",
         "2026-10-14T03:31:37.389774+00:00", "2",
         "www.volexity.com:2026-10-14|Feeds.Feedburner:2026-10-13",
         "Identified as a host used by the attacker for malicious operations"])
    assert out["_ip"] == "108.165.147.64"
    assert out["classification_type"] == "blacklist"
    assert out["verdict"] == "malicious"
    assert out["confidence"] == 90                        # high → int percentile
    assert out["first_seen"] == "2026-10-13T17:33:11+00:00"    # verbatim pass-through
    assert out["last_seen"] == "2026-10-14T03:31:37.389774+00:00"
    assert out["extra"] == {
        "source_count": 2,
        "sources": "www.volexity.com:2026-10-14|Feeds.Feedburner:2026-10-13",
        "reason": "Identified as a host used by the attacker for malicious operations",
    }


def test_parse_row_ipv6_and_confidence_label_map():
    s = ThreatClusterSource(data_dir=Path("/tmp"))
    out = s.parse_row(["ipv6", "2001:db8::dead", "medium", "2026-10-12T09:15:00+00:00",
                       "2026-10-13T10:15:00+00:00", "1",
                       "www.watchguard.com:2026-10-13", "Malicious v6 host"])
    assert out["_ip"] == "2001:db8::dead"
    assert out["confidence"] == 60                         # medium
    out_low = s.parse_row(["ipv4", "192.0.2.55", "low", "2026-10-11T08:00:00+00:00",
                           "", "notanint", "", ""])
    assert out_low["confidence"] == 40                     # low
    # unknown label → key absent (no invented number)
    out_unknown = s.parse_row(
        ["ipv4", "203.0.113.7", "critical", "2026-10-13T18:00:00+00:00",
         "2026-10-13T19:00:00+00:00", "3", "srcA:2026-10-13|srcB:2026-10-14",
         "unknown label row"])
    assert "confidence" not in out_unknown
    assert out_unknown["extra"] == {
        "source_count": 3,
        "sources": "srcA:2026-10-13|srcB:2026-10-14",
        "reason": "unknown label row",
    }


def test_parse_row_absent_branches():
    """Empty last_seen → key absent; unparseable source_count / empty sources
    / empty reason → extra keys absent; short row (truncated tail) still parses
    with only the columns it has."""
    s = ThreatClusterSource(data_dir=Path("/tmp"))
    out = s.parse_row(["ipv4", "192.0.2.55", "low", "2026-10-11T08:00:00+00:00",
                       "", "notanint", "", ""])
    assert out["first_seen"] == "2026-10-11T08:00:00+00:00"
    assert "last_seen" not in out
    assert "extra" not in out   # 三键全缺席 → 整个 extra 不落(空 dict 不写)
    # upstream truncation: 4-column row must not crash mid-parse
    out_short = s.parse_row(["ipv4", "198.51.100.99", "medium",
                             "2026-10-10T00:00:00+00:00"])
    assert out_short["_ip"] == "198.51.100.99"
    assert out_short["confidence"] == 60
    assert "last_seen" not in out_short
    assert "extra" not in out_short


def test_first_seen_shape_feeds_decay_parser():
    """⚠ 钉住 first_seen 形状决定:feed.csv 的 ISO-8601 T+00:00 形直传,
    因为时间衰减解析器 parse_first_seen(datetime.fromisoformat)原生认它
    (2026-10-14 py3.12 venv 实测),且正是 EvidenceObservation.first_seen
    的规范形状(ISO-8601 +00:00)。往返断言:解析结果逐位等于原时刻。"""
    s = ThreatClusterSource(data_dir=Path("/tmp"))
    out = s.parse_row(
        ["ipv4", "108.165.147.64", "high", "2026-10-13T17:33:11+00:00",
         "2026-10-14T03:31:37.389774+00:00", "2",
         "www.volexity.com:2026-10-14", "reason"])
    assert parse_first_seen(out["first_seen"]) == datetime(
        2026, 10, 13, 17, 33, 11, tzinfo=timezone.utc)
    # last_seen 带微秒的 ISO-8601 形同样可解析
    assert parse_first_seen(out["last_seen"]) == datetime(
        2026, 10, 14, 3, 31, 37, 389774, tzinfo=timezone.utc)


def test_rebuild_dual_family_smoke(tmp_path):
    """v4/v6 双族键数:fixture 含 4 条有效 ipv4 + 1 条 ipv6;domain/空值/
    ragged 行全部跳过。rebuild 幂等(同输入同键集,位等价约束)。"""
    (tmp_path / "threatcluster.csv").write_text(_SAMPLE)
    s = ThreatClusterSource(data_dir=tmp_path)
    assert s.rebuild() == 4
    assert s._count == 4 and s._count6 == 1

    row = s.query("108.165.147.64")[0]
    assert row["classification_type"] == "blacklist"
    assert row["confidence"] == 90
    assert row["first_seen"] == "2026-10-13T17:33:11+00:00"
    assert row["extra"]["source_count"] == 2

    assert s.query("2001:db8::dead")[0]["confidence"] == 60   # v6 family
    assert s.query("203.0.113.7")[0].get("confidence") is None  # unknown label
    assert s.query("192.0.2.55")[0]["confidence"] == 40
    assert s.query("198.51.100.99")[0]["confidence"] == 60     # truncated row
    assert s.query("198.51.100.1") == {}                        # miss
    assert s.query("2001:db8::1") == {}                         # v6 miss
    s._reader.close(); s._reader6.close()

    # 位等价:同 fixture 再 rebuild → 同键集(键数不变)
    assert s.rebuild() == 4
    assert s._count == 4 and s._count6 == 1
    assert s.query("108.165.147.64")[0]["first_seen"] == "2026-10-13T17:33:11+00:00"
    s._reader.close(); s._reader6.close()
