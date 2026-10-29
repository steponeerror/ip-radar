"""TweetFeed — Source subclass (CSV, per-row hashtag classification).

`0xDanielLopez/TweetFeed` is a crowd-sourced IOC feed aggregated from infosec
X/Twitter. Columns (no header): ``date, author, type, value, tag, link`` where
``type`` ∈ {ip, domain, url, md5, sha256}. Only ``type == "ip"`` rows are kept
(this is an IP tool — other types are filtered as noise). The ``tag`` field is a
space-separated hashtag list (e.g. ``"#C2 #CobaltStrike"``) mapped per-row via
``TWEETFEED_MAP``; the hashtag list is preserved in ``tags`` (space-split) and
the reporter handle in ``extra`` (Convention 1 + the preserve-signal Principle).
"""
import csv
import logging

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize, TWEETFEED_MAP

logger = logging.getLogger(__name__)


def _classify_tag(raw_tag: str) -> str:
    """First mappable hashtag wins; empty / all-unmappable → ``other``.

    Convention 2 (don't force-fit): an unmappable tag (#ransomware, #APT…) falls
    to ``other`` with the raw tag preserved in ``tags``. An *empty* tag is an
    uncategorized-but-flagged IP → also ``other`` (the IP's signal is
    preserved; it is not dropped).
    """
    for tag in (raw_tag or "").split():
        ctype = normalize(tag, TWEETFEED_MAP)
        if ctype != "other":
            return ctype
    return "other"


class TweetFeedSource(Source):
    name = "tweetfeed"
    category = "threat"
    url = "https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master/year.csv"
    filename = "tweetfeed.csv"
    fields = ("is_malicious",)
    classification_type = "other"   # default; overridden per-row in harvest
    verdict = "malicious"
    stale_days = 1
    reliability = 0.50              # 收源红线 r≥0.5(spec §3.4);校准阶段重估 — crowd-sourced researcher reports
    authoritative_for = ()
    # 载入期排除 infra_services curated 单址集(issue #183/ADR 0008 同族;
    # 2026-10-29 人裁真误列整改:223.5.5.5(AliDNS)被单推误列——Winos/
    # ValleyRat 推文的 URL 主机被抽成 ip 型 IOC,实测本地 data/tweetfeed.csv
    # 全量 curated 命中恰此 1 行:2026-02-09 reporter skocherhan
    # x.com/skocherhan/status/2020854107163037900;无 NTP/根服务器等其他
    # 命中。数据文件零改写,关 IP_RADAR_INFRA_NOISE_FILTER 重建即复原)。
    infra_noise_filter = True

    def harvest(self):
        """Yield (ip, Evidence) per IP-type row. Non-IP rows (domain/url/hash)
        are dropped — noise for an IP tool. Tag → classification via
        ``_classify_tag``; hashtag list in ``tags`` + reporter preserved in
        ``extra``."""
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 5:
                    continue
                if row[2].strip() != "ip":
                    continue
                ip = row[3].strip()
                raw_tag = row[4].strip()
                first_seen = row[0].strip().replace(" ", "T")  # → ISO for decay parse
                tweet_url = row[5].strip() if len(row) > 5 else ""
                tags = raw_tag.split() if raw_tag else []
                yield ip, Evidence(
                    classification_type=_classify_tag(raw_tag),
                    verdict="malicious",
                    first_seen=first_seen,
                    tags=tags,
                    extra={
                        "reporter": row[1].strip(),
                        "tweet_url": tweet_url,
                    },
                )
