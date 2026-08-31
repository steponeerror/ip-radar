"""Turris Sentinel Greylist — CsvSource subclass.

CZ.NIC's distributed-router greylist: IPs that probed Turris Omnia sensors.
Format: ``Address,Tags`` with a quoted comma-list of observed protocols
(ftp/http/smtp/telnet...). Regenerated continuously; recommend daily refresh.

License: CC BY-NC-SA 4.0 (view.sentinel.turris.cz/greylist-data/LICENSE.txt)
— non-commercial; user-approved 2026-09-01 for this non-commercial tool.

All rows are protocol probes → single ``scanner`` classification,
``suspicious`` verdict (heuristic greylist, FP risk documented by publisher).
Protocols survive verbatim in ``native_categories`` (f3csystems precedent).
"""
from ._base import CsvSource


class TurrisGreylistSource(CsvSource):
    name = "turris_greylist"
    category = "threat"
    url = "https://view.sentinel.turris.cz/greylist-data/greylist-latest.csv"
    filename = "turris_greylist.csv"
    fields = ("is_malicious",)
    classification_type = "scanner"
    verdict = "suspicious"
    stale_days = 1
    reliability = 0.60
    authoritative_for = ()
    skip_lines = 1   # header: Address,Tags

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 2:
            return None
        tags = [t.strip() for t in row[1].split(",") if t.strip()]
        return {
            "_ip": row[0].strip(),
            "classification_type": self.classification_type,
            "verdict": self.verdict,
            "native_categories": tags,
        }
