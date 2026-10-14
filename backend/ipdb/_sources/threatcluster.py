"""ThreatCluster public IOC feed — CsvSource subclass (feed.csv IP rows).

threatcluster.io's public ``feed.csv`` (same 30-day window, same publisher as
the retired ``ips.txt``) mixes ~786 rows of ipv4/ipv6/domain indicators with
context columns (confidence label, first/last_seen, source_count, sources,
reason; 2026-10-14 plan snapshot). This source takes the IP subset (~182 v4 +
~4 v6) and drops domain rows: this tool's key space is IP/CIDR only
(architecture red line — no DNS resolution, no domain keys), so domain rows
are out of scope by design, not by omission. Volume stays honestly tiny and
curated — kept as a c2/mal corroboration witness, not a coverage source.

Field routing (feed.csv header:
``type,value,confidence,first_seen,last_seen,source_count,sources,reason``):

- ``type`` must be ipv4/ipv6 — filters domain rows, header remnants, noise.
- ``confidence`` is a label, mapped ``{high:90, medium:60, low:40}`` to int
  percentiles (threatfox precedent); unknown labels leave the key absent
  (无证据即无话 — no invented number).
- ``first_seen``/``last_seen`` pass through verbatim: the feed's ISO-8601
  ``T``+``+00:00`` shape is natively accepted by the time-decay parser
  ``parse_first_seen`` (``datetime.fromisoformat``, ipdb/_logodds.py —
  threatfox's space-separated form feeds the same parser), and is exactly
  the canonical ``EvidenceObservation.first_seen`` contract shape
  ("ISO-8601 +00:00"; verified 2026-10-14 on py3.12 venv: both
  ``2026-10-13T17:33:11+00:00`` and the fractional ``last_seen`` form
  round-trip). No re-shaping.
- Attribution rides in ``extra``: ``reason``, ``sources`` (pipe-joined string
  verbatim), ``source_count`` (only when ``int()`` succeeds).
"""
from ._base import CsvSource

# confidence 标签 → 整数百分位(threatfox 先例:int confidence);未知标签不写键
_CONFIDENCE_LABELS = {"high": 90, "medium": 60, "low": 40}


class ThreatClusterSource(CsvSource):
    name = "threatcluster"
    category = "threat"
    url = "https://threatcluster.io/api/iocs/public/feed.csv"
    filename = "threatcluster.csv"   # 格式诚实;旧 threatcluster.txt 由部署步骤清理,代码不迁移
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 3
    reliability = 0.70                   # human-curated, high-confidence
    authoritative_for = ()
    skip_lines = 1   # header: type,value,confidence,first_seen,last_seen,source_count,sources,reason

    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 2:
            return None
        if row[0].strip().lower() not in ("ipv4", "ipv6"):
            return None              # domain 行 + 表头残余 + 杂行(IP 键空间红线)
        _ip = row[1].strip()
        if not _ip:
            return None

        def _cell(i: int) -> str:
            # 上游截断行(尾部列缺失)按空列处理,不炸 rebuild(threatfox 先例)
            return row[i].strip() if len(row) > i else ""

        out: dict = {
            "_ip": _ip,
            "classification_type": self.classification_type,
            "verdict": self.verdict,
        }
        confidence = _CONFIDENCE_LABELS.get(_cell(2))
        if confidence is not None:
            out["confidence"] = confidence
        first_seen = _cell(3)
        if first_seen:
            out["first_seen"] = first_seen   # ISO-8601 T+00:00 直传(decay 解析器原生认,见类 docstring)
        last_seen = _cell(4)
        if last_seen:
            out["last_seen"] = last_seen
        extra: dict = {}
        try:
            extra["source_count"] = int(_cell(5))
        except ValueError:
            pass
        sources = _cell(6)
        if sources:
            extra["sources"] = sources          # 管道串原样(逐源归因在 extra,不做二次拆分)
        reason = _cell(7)
        if reason:
            extra["reason"] = reason
        if extra:
            out["extra"] = extra
        return out
