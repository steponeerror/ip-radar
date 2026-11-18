"""OffSeq Mirage Feed — Source subclass (CSV, per-row multi-tag classification).

`offseq/mirage-feed` (OffSeq Mirage honeypot fleet, feeds.offseq.com) is a
daily attacker-truth feed: handshake-verified IPs only (UDP/spoofable traffic
never qualifies), each listed after ≥3 sensors in ≥2 networks saw it within
7 days, first sighting ≥24h old, with first-party infra and known research
scanners allowlisted upstream. 7-day activity window, published daily ~03:00
UTC (24h after data cutoff). Only the full-record face ``attackers-7d.csv`` is
harvested (issue #359: the ipv4-1d/30d plain-IP faces are the same data —
echo, never double-counted; the known-scanners face is a future signal, not
wired here). Data license: TLP:CLEAR, attribution string required:
"Mirage Feed by OffSeq Mirage (https://github.com/offseq/mirage-feed), CC BY 4.0".

CSV columns: ``ip,asn,as_org,country,first_seen,last_seen,services,tags,cves,
kev,attack,sensors,networks,hits,confidence``. The ``tags`` column is a
``;``-separated list mapped via ``MIRAGE_MAP``; tags are GROUPED by derived
canonical type: one ``Evidence`` per distinct type, each carrying
``native_categories`` = its raw tags (reportedip pattern). Empty tags
(19 rows in the 2026-11-18 snapshot) fall back to ``blacklist`` —
undifferentiated sensor accusation, siberkapan precedent.

Field routing: ``asn``/``country_code`` slots; ``as_org`` → ``as_name``
(dataplane/dshield precedent: threat feeds carry their ASN-name column into
the slot; NamingAuthority orders by reliability so iptoasn 0.90 wins where
present); ``hits`` → ``reporter_count`` (dshield ``attacks_n`` precedent);
``confidence`` → ``Evidence.confidence`` verbatim 0-100; first_seen/last_seen
verbatim ISO-Z (decay axis). ``services``/``attack`` (ATT&CK, ICS techniques
included)/``sensors``/``networks`` ride in ``extra``; ``cves``/``kev`` only
when non-empty/true (kev=true ⟺ cves non-empty in observed data).

No ``infra_noise_filter``: upstream excludes public resolvers/root servers and
first-party ranges (Cloudflare/Akamai/Apple/Microsoft 365/Google/GitHub)
before publishing — the #347 incident class is filtered at the source.
"""
import csv
import logging

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize, MIRAGE_MAP

logger = logging.getLogger(__name__)


class MirageFeedSource(Source):
    name = "mirage_feed"
    category = "threat"
    url = "https://feeds.offseq.com/mirage-feed/latest/attackers-7d.csv"
    filename = "mirage_feed.csv"
    fields = ("is_malicious",)
    classification_type = "other"   # default; overridden per-row in harvest
    verdict = "malicious"
    stale_days = 1                  # daily publish ~03:00 UTC (24h after cutoff)
    reliability = 0.65              # multi-sensor honeypot fleet, ≥3 sensors
                                    # ≥2 networks per IP (cf. reportedip 0.65;
                                    # single-undifferentiated-sensor siberkapan 0.60)
    authoritative_for = ()
    provenance_tier = "A"           # official first-party feed (S21)
    honeypot_methodology = True     # honeypot fleet (S33; binarydefense/knock_knock precedent)

    def harvest(self):
        """Yield (ip, Evidence) per row, one Evidence per distinct canonical
        type of its tags. Bare IPv4 addresses (upstream CI pins single-address
        records, /32 under dual-family rebuild)."""
        import ipaddress as _ipa
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ip = (row.get("ip") or "").strip()
                if not ip:
                    continue
                try:
                    if _ipa.ip_address(ip).version != 4:
                        continue          # defensive: feed face is IPv4-only today
                except ValueError:
                    continue
                # group tags by canonical type (reportedip pattern)
                groups: dict[str, list[str]] = {}
                for t in (row.get("tags") or "").split(";"):
                    t = t.strip()
                    if t:
                        groups.setdefault(normalize(t, MIRAGE_MAP), []).append(t)
                if not groups:
                    groups = {"blacklist": []}   # empty tags → undifferentiated
                                                 # sensor accusation (siberkapan)
                # per-row shared fields
                asn_raw = (row.get("asn") or "").strip()
                asn = int(asn_raw) if asn_raw.isdigit() else None
                conf_raw = (row.get("confidence") or "").strip()
                confidence = int(conf_raw) if conf_raw.isdigit() else None
                hits_raw = (row.get("hits") or "").strip()
                reporter_count = int(hits_raw) if hits_raw.isdigit() else None
                first_seen = (row.get("first_seen") or "").strip() or None
                last_seen = (row.get("last_seen") or "").strip() or None
                extra: dict = {}
                services = [s for s in (row.get("services") or "").split(";") if s.strip()]
                if services:
                    extra["services"] = services
                attack = [a for a in (row.get("attack") or "").split(";") if a.strip()]
                if attack:
                    extra["attack"] = attack
                cves = [c for c in (row.get("cves") or "").split(";") if c.strip()]
                if cves:
                    extra["cves"] = cves
                if (row.get("kev") or "").strip().lower() == "true":
                    extra["kev"] = True
                sensors_raw = (row.get("sensors") or "").strip()
                if sensors_raw.isdigit():
                    extra["sensors"] = int(sensors_raw)
                networks_raw = (row.get("networks") or "").strip()
                if networks_raw.isdigit():
                    extra["networks"] = int(networks_raw)
                country = (row.get("country") or "").strip()
                as_org = (row.get("as_org") or "").strip()
                for ctype, group_tags in groups.items():
                    # dedupe preserving first-seen order (tags unique per row in
                    # observed data; belt-and-braces for future upstream shapes)
                    seen: set[str] = set()
                    natives = [t for t in group_tags
                               if not (t in seen or seen.add(t))]
                    yield ip, Evidence(
                        classification_type=ctype,
                        verdict="malicious",
                        confidence=confidence,
                        first_seen=first_seen,
                        last_seen=last_seen,
                        country_code=country or None,
                        asn=asn,
                        as_name=as_org or None,
                        reporter_count=reporter_count,
                        native_categories=natives,
                        extra=dict(extra),
                    )
