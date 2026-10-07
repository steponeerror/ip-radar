"""Tests for the OTX subscribed-stream source (otx_subscribed).

Pulse names/roles below are verbatim from the 2026-10-07 live probe of the
demo account's subscription cart (4 authors, 83 pulses): pr0viehh's live SSH
honeypot (role="bruteforce"), ladarrellmiller's TSEC weeklies, CyberHunter
mirrors (Malware Filter / URLHaus / Twitter), BotnetExposer S3# scanners.
"""
from ipdb._classification import OTX_SUBSCRIBED_ROLE_MAP, normalize
from ipdb._sources.otx_subscribed import _classify_row, OtxSubscribedSource


class TestRoleMap:
    def test_bruteforce_role_maps(self):
        assert normalize("bruteforce", OTX_SUBSCRIBED_ROLE_MAP) == "brute-force"

    def test_unknown_role_falls_through(self):
        # normalize() sends unmappable values to the "other" bucket;
        # _classify_row must then try the pulse name instead.
        assert normalize("c2", OTX_SUBSCRIBED_ROLE_MAP) == "other"


class TestClassifyRow:
    """role > pulse-name keyword > blacklist fallback."""

    def test_role_takes_priority(self):
        ctype, tag = _classify_row("bruteforce",
                                   "Scan port 3389 RDP (S3#)")
        assert ctype == "brute-force"
        assert tag == "bruteforce"

    def test_mega_honeypot_pulse_via_role(self):
        # pr0viehh rows carry role="bruteforce"
        ctype, tag = _classify_row("bruteforce", "SSH Brute-Force Honeypot Live")
        assert ctype == "brute-force"

    def test_tsec_brute_force_weekly(self):
        ctype, _ = _classify_row("", "TSEC Honeypot: Brute Force - Week of 2026-10-05")
        assert ctype == "brute-force"

    def test_tsec_malware_delivery(self):
        ctype, _ = _classify_row("", "TSEC Honeypot: Malware Delivery - Week of 2026-09-07")
        assert ctype == "malware-distribution"

    def test_tsec_ics_targeting(self):
        ctype, _ = _classify_row("", "TSEC Honeypot: ICS Targeting - Week of 2026-09-07")
        assert ctype == "scanner"

    def test_malware_filter_botnet_list(self):
        ctype, _ = _classify_row("", "Malware Filter - Botnet List - 06-10-2026 (Part 6)")
        assert ctype == "c2-server"

    def test_urlhaus_mirror(self):
        ctype, _ = _classify_row("", "URLHaus data - 06-10-2026 (Part 3)")
        assert ctype == "malware-distribution"

    def test_phishing_list(self):
        ctype, _ = _classify_row("", "Malware Filter - Phishing List - 06-10-2026")
        assert ctype == "phishing"

    def test_s3_scan_port(self):
        ctype, _ = _classify_row("", "Scan port 3389 RDP (S3#)")
        assert ctype == "scanner"

    def test_s3_variant_scanner(self):
        # non-port S3# pulses ("HTTP Range in small image (S3#)") are
        # scanner-behaviour pulses too
        ctype, _ = _classify_row("", "HTTP Range in small image (S3#)")
        assert ctype == "scanner"

    def test_s3_bruteforce_name(self):
        ctype, _ = _classify_row("", "Bruteforce SSH port 22 (S3)")
        assert ctype == "brute-force"

    def test_unmapped_role_falls_through_to_name_keyword(self):
        # role="c2" 不在 OTX_SUBSCRIBED_ROLE_MAP(normalize → "other"),
        # 契约 = 脉冲名关键词接手而非丢行(契约钉住,防未来漂移)
        assert _classify_row(
            "c2", "Malware Filter - Botnet List - 06-10-2026 (Part 6)") \
            == ("c2-server", "botnet")

    def test_unmatched_falls_back_to_blacklist(self):
        # Twitter Feed mirrors and unknown future pulses → generic curated list
        ctype, tag = _classify_row("", "Twitter Feed - harugasumi - 06-10-2026")
        assert ctype == "blacklist"
        assert tag == ""

    def test_empty_everything(self):
        assert _classify_row("", "") == ("blacklist", "")


class TestOtxSubscribedConfig:
    def test_config(self):
        assert OtxSubscribedSource.fields == ("is_malicious",)
        assert OtxSubscribedSource.category == "threat"
        assert OtxSubscribedSource.reliability == 0.6
        assert OtxSubscribedSource.authoritative_for == ()
        # Aggregator platform (same lineage tier as otx/firehol/ipsum):
        # dedup_lineage suppresses us when a stronger non-derived source
        # reports the same IP (spec 2026-08-29 §3.3).
        assert OtxSubscribedSource.derived is True

    def test_stale_days(self):
        # 12h slot grid (stale_days<=1 → SLOT_GRID 43200s): honeypot Live
        # pulse + CyberHunter dailies both refresh intraday.
        assert OtxSubscribedSource.stale_days == 1


class TestHarvest:
    """harvest() reads the 7-col CSV download() writes:
    [indicator, ctype, tag, author, pulse, created, description]
    """

    def _write_fixture(self, path, rows):
        import csv as _csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            for r in rows:
                w.writerow(r)

    def test_harvest_yields_evidence(self, tmp_path):
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["82.165.104.10", "brute-force", "bruteforce",
              "pr0viehh", "SSH Brute-Force Honeypot Live",
              "2026-09-29T20:38:49",
              "SSH intrusion attempt from 82.165.104.10"],
             ["182.138.158.182", "scanner", "ics targeting",
              "ladarrellmiller",
              "TSEC Honeypot: ICS Targeting - Week of 2026-09-07",
              "2026-09-09T13:14:42",
              "ICS targeting. confidence 81/100. source: TSEC T-Pot"]],
        )
        src = OtxSubscribedSource(tmp_path)
        rows = list(src.harvest())

        ip0, ev0 = rows[0]
        assert ip0 == "82.165.104.10"
        assert ev0.classification_type == "brute-force"
        assert ev0.verdict == "malicious"
        assert ev0.first_seen == "2026-09-29T20:38:49"
        assert ev0.native_categories == ["bruteforce"]
        assert ev0.extra["author"] == "pr0viehh"
        assert ev0.extra["pulse"] == "SSH Brute-Force Honeypot Live"
        assert "intrusion attempt" in ev0.extra["description"]
        assert ev0.reliability is None   # falls back to class-level 0.6

        ip1, ev1 = rows[1]
        assert ev1.classification_type == "scanner"
        assert ev1.native_categories == ["ics targeting"]
        assert ev1.extra["author"] == "ladarrellmiller"

    def test_round_trip_rebuild_and_query(self, tmp_path):
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["82.165.104.10", "brute-force", "bruteforce",
              "pr0viehh", "SSH Brute-Force Honeypot Live",
              "2026-09-29T20:38:49", ""]],
        )
        src = OtxSubscribedSource(tmp_path)
        src.rebuild()
        rec = src.query("82.165.104.10")[0]
        assert rec["classification_type"] == "brute-force"
        assert rec["verdict"] == "malicious"
        assert rec["first_seen"] == "2026-09-29T20:38:49"
        assert rec["native_categories"] == ["bruteforce"]
        assert rec["extra"]["author"] == "pr0viehh"
        assert "description" not in rec["extra"]   # empty desc not stored

    def test_optional_columns_graceful(self, tmp_path):
        # 4-col minimal row (no pulse/created/description)
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["1.2.3.4", "c2-server", "botnet", "CyberHunterAutoFeed"]],
        )
        src = OtxSubscribedSource(tmp_path)
        rows = list(src.harvest())
        ip, ev = rows[0]
        assert ip == "1.2.3.4"
        assert ev.classification_type == "c2-server"
        assert ev.first_seen is None
        assert ev.extra == {"author": "CyberHunterAutoFeed"}

    def test_skips_short_and_blank_rows(self, tmp_path):
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["1.2.3.4", "scanner", "", "", "", "", ""],   # valid
             ["only-one-column"],                            # too short
             ["", "scanner", "", "", "", "", ""],           # blank indicator
             ["9.9.9.9", "", "", "", "", "", ""],           # blank ctype
             ],
        )
        src = OtxSubscribedSource(tmp_path)
        rows = list(src.harvest())
        assert [ip for ip, _ in rows] == ["1.2.3.4"]
        # empty tag → no native_categories entry
        assert rows[0][1].native_categories == []

    def test_cross_pulse_classifications_both_survive(self, tmp_path):
        # 同一 IP 见于两个 pulse、分类不同(Botnet List=c2-server vs
        # Phishing List=phishing):(IP, 分类) 去重不得互相覆盖——
        # convention 3 证据不预坍缩,坍缩点在 rebuild
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["203.0.113.9", "c2-server", "botnet", "CyberHunterAutoFeed",
              "Malware Filter - Botnet List - 06-10-2026 (Part 6)",
              "2026-10-06T02:00:00", ""],
             ["203.0.113.9", "phishing", "phishing", "CyberHunterAutoFeed",
              "Malware Filter - Phishing List - 06-10-2026",
              "2026-10-06T03:00:00", "Phishing website"]],
        )
        src = OtxSubscribedSource(tmp_path)
        src.rebuild()
        recs = src.query("203.0.113.9")
        assert sorted(r["classification_type"] for r in recs) == [
            "c2-server", "phishing"]
        by_ctype = {r["classification_type"]: r for r in recs}
        assert by_ctype["c2-server"]["native_categories"] == ["botnet"]
        assert by_ctype["phishing"]["extra"]["pulse"] == \
            "Malware Filter - Phishing List - 06-10-2026"

    def test_cidr_row_supported(self, tmp_path):
        self._write_fixture(
            tmp_path / "otx_subscribed.csv",
            [["5.6.7.0/24", "scanner", "scan port", "BotnetExposer",
              "Scan port 445 SMB (S3#)", "2026-10-07T03:39:10", ""]],
        )
        src = OtxSubscribedSource(tmp_path)
        src.rebuild()
        rec = src.query("5.6.7.3")[0]
        assert rec["classification_type"] == "scanner"


class TestDownloadDedup:
    """download() 的 (IP, 分类) 去重键:异分类互不覆盖,同键保最新 created。

    免网络:monkeypatch 实例 _fetch_json_page 喂合成页(两连空页终结,
    与真实流同型)。"""

    @staticmethod
    def _page(name, indicators, author="CyberHunterAutoFeed"):
        return {"results": [{
            "author_name": author, "name": name,
            "indicators": indicators,
        }]}

    def _run_download(self, tmp_path, pages):
        import csv as _csv
        seq = list(pages) + [{"results": []}, {"results": []}]
        src = OtxSubscribedSource(tmp_path)
        src._fetch_json_page = lambda page, headers: seq[page - 1]
        src.download()
        with open(tmp_path / "otx_subscribed.csv") as f:
            return [row for row in _csv.reader(f)]

    def test_distinct_classifications_keep_both_rows(
            self, tmp_path, monkeypatch):
        # 同 IP 跨 pulse 异分类:两行都要落 CSV(裸 IP 键会丢一行)
        monkeypatch.setenv("OTX_API_KEY", "test-key")
        rows = self._run_download(tmp_path, [
            self._page("Malware Filter - Botnet List - 06-10-2026 (Part 6)",
                       [{"type": "IPv4", "indicator": "203.0.113.9",
                         "created": "2026-10-06T02:00:00"}]),
            self._page("Malware Filter - Phishing List - 06-10-2026",
                       [{"type": "IPv4", "indicator": "203.0.113.9",
                         "created": "2026-10-06T03:00:00"}]),
        ])
        assert rows == [
            ["203.0.113.9", "c2-server", "botnet", "CyberHunterAutoFeed",
             "Malware Filter - Botnet List - 06-10-2026 (Part 6)",
             "2026-10-06T02:00:00", ""],
            ["203.0.113.9", "phishing", "phishing", "CyberHunterAutoFeed",
             "Malware Filter - Phishing List - 06-10-2026",
             "2026-10-06T03:00:00", ""],
        ]

    def test_same_pair_dedups_to_latest_created(self, tmp_path, monkeypatch):
        # 同 (IP, 分类) 重复观测:只保 created 最新那行(87% 重复的成因)
        monkeypatch.setenv("OTX_API_KEY", "test-key")
        rows = self._run_download(tmp_path, [
            self._page("SSH Brute-Force Honeypot Live",
                       [{"type": "IPv4", "indicator": "198.51.100.7",
                         "role": "bruteforce",
                         "created": "2026-10-05T00:00:00"}],
                       author="pr0viehh"),
            self._page("SSH Brute-Force Honeypot Live",
                       [{"type": "IPv4", "indicator": "198.51.100.7",
                         "role": "bruteforce",
                         "created": "2026-10-06T00:00:00",
                         "description": "newer observation"}],
                       author="pr0viehh"),
        ])
        assert rows == [
            ["198.51.100.7", "brute-force", "bruteforce", "pr0viehh",
             "SSH Brute-Force Honeypot Live",
             "2026-10-06T00:00:00", "newer observation"],
        ]
