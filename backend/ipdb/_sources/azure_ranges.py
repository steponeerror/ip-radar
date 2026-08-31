"""Azure Service Tags (Public cloud) — the AzureCloud footprint.

The weekly JSON is date-stamped behind a JS-gated download page, so
download() is a two-step fetch: the confirmation page (browser UA) exposes
the current direct download.microsoft.com link, which is then fetched to
_path. harvest() keeps only the cloud-wide `AzureCloud` tag — its
addressPrefixes are the union of all Azure public ranges (region tags
like AzureCloud.EastUS are subsets and would double-count).
"""
import json
import re

from .._evidence import Evidence
from .._source_base import Source

# details/confirmation page → current ServiceTags_Public_<date>.json link
_PAGE = "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"
_LINK_RE = re.compile(r"https://download\.microsoft\.com/download/[^\s\"']+"
                      r"ServiceTags_Public_\d+\.json")


class AzureRangesSource(Source):
    name = "azure_ranges"
    category = "asset"
    filename = "azure_ranges.json"
    fields = ("service", "is_hosting")
    url = _PAGE                       # UX-facing; the real fetch is two-step
    stale_days = 7
    reliability = 0.95
    authoritative_for = ()

    def download(self, token=None):
        import urllib.request
        self._data_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(_PAGE, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        m = _LINK_RE.search(html)
        if not m:
            raise RuntimeError("no ServiceTags_Public link on confirmation page")
        data = self._http_get(m.group(0))
        if not data.strip():
            raise RuntimeError("empty ServiceTags JSON")
        self._path.write_bytes(data)

    def harvest(self):
        if not self._path.exists():
            return
        d = json.loads(self._path.read_text())
        ev = Evidence(
            service="cloud",
            is_hosting=True,
            native_types={"service": "Azure"},
            verdict="",                # asset-only; suppress "malicious" default
        )
        for v in d.get("values", []):
            if v.get("name") != "AzureCloud":
                continue
            for prefix in (v.get("properties") or {}).get("addressPrefixes", []):
                yield prefix, ev
