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

from .._evidence import Evidence
from .._source_base import Source


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
                try:
                    sa = ipaddress.ip_address(start)
                    ea = ipaddress.ip_address(end)
                except ValueError:
                    continue
                if sa.version != ea.version:
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
                for cidr in ipaddress.summarize_address_range(sa, ea):
                    yield str(cidr), ev
