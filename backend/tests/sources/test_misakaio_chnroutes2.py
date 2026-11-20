"""Tests for misakaio/chnroutes2 source — China route aggregation CIDR list.

Format (real fetch 2026-11-20, 3906 lines): two '#' header comment lines
(dump timestamp + aggregation stats), then one IPv4 CIDR per line (3904
prefixes). No dirty rows in the real feed — the only non-CIDR lines are the
header comments; fixtures below are verbatim from the live file.

Evidence shape follows the geo_asn scalar precedent (geolite_city /
dbip_city / iptoasn): country_code="CN" per CIDR, no fusion-core fields
set by the source. Parser is the IpListSource base (comments skipped,
bare IPs and CIDRs both accepted — roster convention).
"""
from ipdb._sources import misakaio_chnroutes2 as mod
from ipdb._sources.misakaio_chnroutes2 import MisakaioChnroutes2Source

# verbatim from https://raw.githubusercontent.com/misakaio/chnroutes2/master/chnroutes.txt
HEADER_LINES = [
    "# 4815403 routes were dumped from us-iad01-rs01cn-b at Fri Nov 20 18:00:04 UTC 2026.",
    "# Found 62429 routes matching, aggregated to 3904.",
]
CIDR_LINES = [
    "1.1.8.0/24",
    "1.2.4.0/24",
    "1.12.0.0/14",
    "223.255.252.0/23",
]


class TestMisakaioChnroutes2:
    def test_config(self):
        assert MisakaioChnroutes2Source.name == "misakaio_chnroutes2"
        assert MisakaioChnroutes2Source.category == "geo_asn"
        assert MisakaioChnroutes2Source.url == (
            "https://raw.githubusercontent.com/misakaio/chnroutes2/"
            "master/chnroutes.txt")
        assert MisakaioChnroutes2Source.filename == "chnroutes.txt"
        assert MisakaioChnroutes2Source.fields == ("country_code",)
        assert MisakaioChnroutes2Source.authoritative_for == ()
        assert MisakaioChnroutes2Source.reliability >= 0.80   # geo_asn peers 0.80-0.90
        assert MisakaioChnroutes2Source.stale_days <= 7       # hourly auto-dump feed

    def test_get_insert_data_scalar_geo_shape(self):
        d = MisakaioChnroutes2Source.get_insert_data(MisakaioChnroutes2Source.__new__(
            MisakaioChnroutes2Source))
        # geo precedent (dbip/geolite/iptoasn): scalar slot only, no
        # classification/reliability set by the source
        assert d["country_code"] == "CN"
        assert "classification_type" not in d
        assert "reliability" not in d
        assert "asn" not in d

    def test_rebuild_skips_headers_and_loads_cidrs(self, tmp_path):
        (tmp_path / "chnroutes.txt").write_text(
            "\n".join(HEADER_LINES + CIDR_LINES) + "\n")
        src = MisakaioChnroutes2Source(data_dir=tmp_path)
        assert src.rebuild() == 4      # header comments don't pollute keys
        rec = src.query("1.2.4.5")     # member of 1.2.4.0/24
        assert isinstance(rec, list) and rec[0]["country_code"] == "CN"
        assert src.query("1.12.3.4")[0]["country_code"] == "CN"   # /14 member
        assert src.query("223.255.253.1")[0]["country_code"] == "CN"  # /23 member
        assert src.query("8.8.8.8") == {}                       # non-member miss
        assert src.query("1.2.5.1") == {}                       # adjacent to /24

    def test_parse_raw_strips_comments_blank(self, tmp_path):
        src = MisakaioChnroutes2Source(data_dir=tmp_path)
        raw = ("\n".join(HEADER_LINES) + "\n" + "\n".join(CIDR_LINES) + "\n\n").encode()
        entries = src.parse_raw(raw)
        assert entries == CIDR_LINES   # comments and blank lines dropped verbatim

    def test_bad_key_row_dropped_not_counted(self, tmp_path):
        # key-column bad (unparseable line) → row dropped, rebuild key count excludes
        (tmp_path / "chnroutes.txt").write_text(
            "\n".join(CIDR_LINES[:2]) + "\nnot-an-ip-or-cidr\n")
        src = MisakaioChnroutes2Source(data_dir=tmp_path)
        assert src.rebuild() == 2
        assert src.query("1.1.8.9")[0]["country_code"] == "CN"
        assert src.health().record_count == 2

    def test_bare_ip_row_accepted(self, tmp_path):
        # roster convention: bare IP (no /nn) treated as /32 by base rebuild
        (tmp_path / "chnroutes.txt").write_text("1.2.4.5\n")
        src = MisakaioChnroutes2Source(data_dir=tmp_path)
        assert src.rebuild() == 1
        assert src.query("1.2.4.5")[0]["country_code"] == "CN"
        assert src.query("1.2.4.6") == {}

    def test_import_alias_variants(self):
        # PEP 562 canonical spellings all import to the same class,
        # and none leak into dir() (registry auto-discovery stays single-row)
        from ipdb._sources.misakaio_chnroutes2 import (
            MisakaioChnroutes2Source as main_cls,
            Misakaiochnroutes2Source as token_form,
            MisakaioCHNROUTES2Source as upper_form,
        )
        assert token_form is main_cls
        assert upper_form is main_cls
        assert mod.MisakaioChnroutes2Source is main_cls
        for variant in ("Misakaiochnroutes2Source", "MisakaioCHNROUTES2Source"):
            assert variant not in dir(mod)
