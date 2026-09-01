"""db-ip City Lite — the city slot's second voting source (sanctioned since 2026-08-15).

Monthly CC BY 4.0 dump (~83MB gz). download() streams the .gz to disk;
harvest() reads it as a gzip text stream (no decompressed intermediate —
the plain CSV would be ~0.5GB). Ranges expand to CIDRs via
summarize_address_range; v4 and v6 rows both ride the dual-family rebuild.

Routing mirrors geolite_city: city → canonical `city` (FactualVoting
vote-coherent), country → `country_code`, lat/lon → extra (display-only).
'ZZ' continent/country is db-ip's unknown marker (no signal, row skipped);
lat/lon 0/0 is the missing-coordinate marker and is dropped.

Lineage note: db-ip lite is independently compiled but aggregates open geo
sources, so agreement with geolite_city is expected to be high; no
DERIVED_SOURCES declaration — it votes, it is not treated as a copy.
"""
import csv
import gzip
import ipaddress
import socket
import struct

from .._evidence import Evidence
from .._source_base import Source


def _v4_int(s: str) -> int | None:
    """Strict dotted-quad parse via inet_pton (C-fast).

    Differential-tested byte-equivalent to ipaddress.IPv4Address on
    accept/reject + value (edge battery + 300k real rows, 2026-09-01);
    ipaddress is 81% of this source's parse cost, so both families take
    integer fast paths. Theoretical drift: scoped v6 ("%zone") is accepted
    by ipaddress but rejected here — nonexistent in machine-generated geo
    CSVs (300k-row differential: zero)."""
    try:
        return struct.unpack("!I", socket.inet_pton(socket.AF_INET, s))[0]
    except (OSError, ValueError):
        return None


def _v6_int(s: str) -> int | None:
    try:
        return int.from_bytes(socket.inet_pton(socket.AF_INET6, s), "big")
    except (OSError, ValueError):
        return None


def _fmt_v4(a: int, plen: int) -> str:
    return f"{a >> 24 & 255}.{a >> 16 & 255}.{a >> 8 & 255}.{a & 255}/{plen}"


def _fmt_v6(a: int, plen: int) -> str:
    # Full (uncompressed) hex form — valid IPv6Network input; the string is
    # transient (rebuild_lmdb re-parses to int keys), canonical compression
    # buys nothing downstream and costs a Python compressor.
    h = f"{a:032x}"
    return (f"{h[0:4]}:{h[4:8]}:{h[8:12]}:{h[12:16]}:"
            f"{h[16:20]}:{h[20:24]}:{h[24:28]}:{h[28:32]}/{plen}")


class DbIpCitySource(Source):
    name = "dbip_city"
    category = "geo_asn"
    filename = "dbip_city.csv.gz"
    fields = ("city", "country_code")
    stale_days = 35                  # monthly dump; one missed cycle is fine
    reliability = 0.80
    single_evidence = True           # ~4M rows → stream load (OOM guard, cf. geolite)
    authoritative_for = ()

    def __init__(self, data_dir):
        super().__init__(data_dir=data_dir)
        # Monthly date-stamped URL: keep the class contract `url: str` (property/
        # str clash warning, cf. ip2proxy docstring) — compute it per instance.
        import datetime
        m = datetime.date.today().replace(day=1)
        self.url = f"https://download.db-ip.com/free/dbip-city-lite-{m:%Y-%m}.csv.gz"
        prev = (m - datetime.timedelta(days=1)).replace(day=1)
        self._prev_month_url = (
            f"https://download.db-ip.com/free/dbip-city-lite-{prev:%Y-%m}.csv.gz")

    def download(self, token=None):
        from ._download import download_file
        try:
            download_file(self.url, self._path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
        except Exception:
            # early-month: current-month file not published yet → previous month
            download_file(self._prev_month_url, self._path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
        # try-open validation: corrupt/empty → unlink, LMDB keeps serving (cf. geolite)
        try:
            with gzip.open(self._path, "rt", encoding="utf-8", errors="replace") as f:
                if not f.read(64):
                    raise ValueError("empty gzip")
        except Exception:
            self._path.unlink(missing_ok=True)
            raise

    def harvest(self):
        if not self._path.exists():
            return
        with gzip.open(self._path, "rt", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f):
                if len(row) < 8:
                    continue
                start, end, _continent, cc, _state, city, lat, lon = (
                    x.strip() for x in row[:8])
                if cc in ("", "ZZ"):
                    cc = ""
                city = city.strip('"')
                if not cc and not city:
                    continue
                extra = {}
                try:
                    la, lo = float(lat), float(lon)
                    if (la, lo) != (0.0, 0.0):
                        extra["lat"] = la
                        extra["lon"] = lo
                except ValueError:
                    pass
                ev = Evidence(
                    city=city or None,
                    country_code=cc or None,
                    extra=extra or None,
                )
                if ":" in start or ":" in end:
                    a, b, bits, fmt = _v6_int(start), _v6_int(end), 128, _fmt_v6
                else:
                    a, b, bits, fmt = _v4_int(start), _v4_int(end), 32, _fmt_v4
                if a is None or b is None or a > b:
                    continue
                span = b - a + 1
                if span & (span - 1) == 0 and a & (span - 1) == 0:
                    # exact aligned CIDR — integer bit-math, no ipaddress objects
                    yield fmt(a, (bits + 1) - span.bit_length()), ev
                else:
                    # rare non-aligned range → stdlib summarize
                    cls = (ipaddress.IPv6Address if bits == 128
                           else ipaddress.IPv4Address)
                    for cidr in ipaddress.summarize_address_range(cls(a), cls(b)):
                        yield str(cidr), ev
