"""gorkemgun/sgb-blocklist — IpListSource subclass.
Hourly plain-text GitHub mirror of the T.C. Siber Güvenlik Başkanlığı
(Turkish Cyber Security Presidency, ex-USOM) malicious address API. The
retired usom.gov.tr/url-list.txt feed lives on here after upstream moved
API-only (2026-06-01). Data file ipv4.txt: 4-line '#' header (title /
Source / Records / Last change) then one bare IPv4 per line, numerically
sorted; 2026-11-20 live fetch = 16,564 records, all bare IPv4 (no CIDR,
no dirty rows — base default parser covers the shape verbatim).
Official government list via community mirror → provenance B
(mirror operator gorkemgun, repo live same day). Undifferentiated
single accusation, no per-row category → blacklist/malicious slot
(Convention 2, binarydefense/data_shield twins). File header carries
`Last change` freshness signal; mirror syncs hourly → stale_days=1.
reliability 0.60: automated government sensor list, one hop from
official API (between ciarm 0.60 and blocklist_de mirrors).
"""
from ._base import IpListSource


class GorkemgunSgbBlocklistSource(IpListSource):
    name = "gorkemgun_sgb_blocklist"
    category = "threat"
    url = "https://raw.githubusercontent.com/gorkemgun/sgb-blocklist/main/ipv4.txt"
    filename = "sgb_ipv4.txt"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1                      # hourly mirror; header `Last change` = internal ts
    reliability = 0.60                  # official sensor list via one-hop mirror
    provenance_tier = "B"               # community mirror of official government data
    authoritative_for = ()              # corroboration only (SM-F1)


# 消费方 import 面冻结拼法兜底(PEP 562):三种规范变体均可导入,
# 且不进 dir() → 注册表自动发现不会双注册。
_IMPORT_ALIASES = {
    "GorkemgunSgbblocklistSource": "GorkemgunSgbBlocklistSource",  # ①令牌机械形
    "GorkemgunSGBBlocklistSource": "GorkemgunSgbBlocklistSource",  # ③缩写全大写形(SGB)
    "GorkemGunSgbBlocklistSource": "GorkemgunSgbBlocklistSource",  # ②品牌拆词形
}


def __getattr__(name):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}")
