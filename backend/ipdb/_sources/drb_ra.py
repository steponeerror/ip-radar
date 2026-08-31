"""drb-ra C2IntelFeeds — CsvSource subclass.

Aggregated C2 IP feed (github.com/drb-ra/C2IntelFeeds, IPC2s-30day.csv),
auto-committed daily from proactive Shodan-style hunts. Rows carry a
confidence label ("Possible Cobaltstrike C2 IP") — "Possible" grade, so the
verdict is ``suspicious`` and the label survives verbatim in
``native_categories``. Aggregator → derived=True (lineage dedup).

Format: ``#ip,ioc`` comment header, then ``<ip>,<label>`` rows.
"""
from ._base import CsvSource


class DrbRaSource(CsvSource):
    name = "drb_ra"
    category = "threat"
    url = ("https://raw.githubusercontent.com/drb-ra/C2IntelFeeds/"
           "master/feeds/IPC2s-30day.csv")
    filename = "drb_ra.csv"
    fields = ("is_malicious",)
    classification_type = "c2-server"
    verdict = "suspicious"
    stale_days = 2
    reliability = 0.50                   # "Possible"-grade aggregator output
    derived = True                       # aggregator: lineage dedup (spec 2026-08-29 §3.3)
    authoritative_for = ()

    def parse_row(self, row: list[str]) -> dict | None:
        if not row or row[0].lstrip().startswith("#"):
            return None                  # "#ip,ioc" header comment
        out = {
            "_ip": row[0].strip(),
            "classification_type": self.classification_type,
            "verdict": self.verdict,
        }
        if len(row) > 1:
            label = row[1].strip()
            if label:
                out["native_categories"] = [label]
        return out
