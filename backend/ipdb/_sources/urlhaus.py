"""URLhaus — Source subclass (CSV, URL→IP extraction + per-row classification).

abuse.ch URLhaus is a malware-distribution URL feed, served since the
v2 认证迁移(票 #159,2026-10-23)by
`https://urlhaus-api.abuse.ch/v2/files/exports/<KEY>/online.csv`(旧匿名
出口 `/downloads/csv_online/` 已 410;online = 旧 csv_online 语义,
active only;Auth-Key 在 URL 路径段,由 env `ABUSECH_AUTH_KEY` 注入,
keyed URL 只在 download() 内拼)。Columns (after a ``#``
comment block): ``id, dateadded, url, url_status, last_online, threat, tags,
urlhaus_link, reporter``. Rows whose ``url`` host is a **domain** are dropped
(this is an IP tool — only IP-literal hosts are kept, ~45% of rows). The
``threat`` column is the upstream's explicit classification field and takes
priority over ``tags`` mapping; unmappable threat values (e.g., malware_download)
fall back to ``tags`` for classification. The ``tags`` column is a
comma-separated mix of malware-family names and file/arch noise
(``32-bit,elf,mips,Mozi``); IoT-botnet families (mirai/Mozi/hajime) map
to ``infected-system`` (botnet drones — infected hosts, P1 2026-09-05
migrated from the dialect type ``botnet``), every other row falls to
``malware-distribution``
(the base classification — every URLhaus URL serves malware). Native tags
are extracted from tags, filtered for arch noise, exclude the matched
malware family (already in ``malware_name``), and stored in the ``tags``
slot (migrated from ``extra.tags_raw``). Reporter and url_status are
preserved in ``extra``; the ``threat`` raw value is stored in ``native_categories``.

Domain-feed caveat (FLAG, user-approved): URLhaus URLs expire fast (taken down
within hours/days), so the extracted IP set churns; mitigated by ``stale_days=1``
+ the tool's time-decay on ``first_seen``/``last_online``.
"""
import csv
import ipaddress
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize, URLHAUS_MAP, URLHAUS_THREAT_MAP
from ._download import (
    CancelToken, atomic_write_bytes, download_file, redact_url)

logger = logging.getLogger(__name__)

# File/arch tokens that appear in nearly every IoT-malware sample — structural
# noise, not signal. Tunable; see spec "Per-source open calls".
URLHAUS_ARCH_NOISE = {
    "32-bit", "64-bit", "x86", "x64", "elf", "pe", "mips", "arm",
    "mips64", "arm64", "exe", "dll",
}


def _host_ip(url: str) -> str | None:
    """Return the URL's host iff it is an IPv4 literal; else None (domain)."""
    try:
        host = urlparse(url).hostname
    except Exception:
        return None
    if not host:
        return None
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return None
    return host


def _classify(tags_raw: str) -> tuple[str, str | None]:
    """Return (classification, malware_name). First mappable tag wins
    (mirai/Mozi/hajime → infected-system, with the matched family as malware_name);
    otherwise the ``malware-distribution`` base — every URLhaus row serves
    malware by definition, so nothing lands in ``other``."""
    for tag in (tags_raw or "").split(","):
        tok = tag.strip()
        key = tok.lower()
        if not key or key == "none":
            continue
        ctype = normalize(key, URLHAUS_MAP)
        if ctype != "other":
            return ctype, tok          # original-case family name for display
    return "malware-distribution", None


class URLhausSource(Source):
    name = "urlhaus"
    category = "threat"
    # 无 key 占位形状(票 #159):v2 真实端点把 Auth-Key 作路径段插在文件名前
    # (…/v2/files/exports/<KEY>/online.csv),keyed URL 只在 download() 内拼。
    url = "https://urlhaus-api.abuse.ch/v2/files/exports/online.csv"
    filename = "urlhaus.csv"
    fields = ("is_malicious",)
    classification_type = "malware-distribution"   # default; per-row overrides
    verdict = "malicious"
    stale_days = 1
    reliability = 0.55            # abuse.ch — curated/confirmed malware URLs
    authoritative_for = ()

    def __init__(self, data_dir: Path):
        # 约定 5:源在 __init__ 读自己的 env,注册表只传 data_dir。v2 迁移
        # (票 #159):旧匿名出口 410,Auth-Key 缺省空串 → download() 时报错
        # (不在 import/注册时炸,源仍可离线加载旧证据)。
        super().__init__(data_dir)
        self._auth_key = os.environ.get("ABUSECH_AUTH_KEY", "")

    def download(self, token: CancelToken | None = None) -> None:
        """v2 认证端点(票 #159):keyed URL → scratch 下载 → 200-OK-坏体守卫
        → 原子落地;坏体不替换旧证据(danmeuk_tor 的 scratch 先例同构)。"""
        if not self._auth_key:
            raise RuntimeError(
                "urlhaus: abuse.ch 已迁 Auth-Key(旧匿名出口 410,票 #159)"
                "——须设 ABUSECH_AUTH_KEY 环境变量")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        prefix, _, fname = self.url.rpartition("/")
        keyed_url = f"{prefix}/{self._auth_key}/{fname}"
        scratch = self._path.with_name(self._path.name + ".dl")
        try:
            download_file(keyed_url, scratch, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"},
                          secret=self._auth_key)
            data = scratch.read_bytes()
            if not data.strip():
                raise RuntimeError(f"Empty response from {redact_url(self.url)}")
            # 200-OK-坏体守卫(票 #159;Phase 3 step 8 惯例):v2 错误页也回
            # 200,坏体不得替换旧证据——须 # 注释块开头或含 id,dateadded 列头。
            if not (data.startswith(b"#") or b"id,dateadded" in data):
                raise RuntimeError(
                    f"unexpected urlhaus payload (no # header, no id,dateadded "
                    f"columns) from {redact_url(self.url)}")
            atomic_write_bytes(self._path, data)
        finally:
            scratch.unlink(missing_ok=True)

    def harvest(self):
        """Yield (ip, Evidence) per IP-host row. Domain-host rows are dropped
        (noise for an IP tool). The ``threat`` column takes priority over ``tags``
        for classification; unmappable threat values fall back to ``tags``.
        Native tags are extracted from ``tags``, filtered for arch noise,
        exclude the matched malware family, and stored in the ``tags`` slot.
        The raw ``threat`` value is stored in ``native_categories``; reporter
        and url_status are preserved in ``extra``."""
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or row[0].startswith("#"):     # comment / header block
                    continue
                if len(row) < 9:
                    continue
                ip = _host_ip(row[2].strip().strip('"'))
                if ip is None:
                    continue                               # domain host → filter
                threat = row[5].strip().strip('"')
                tags_raw = row[6].strip().strip('"')
                tag_ctype, malware_name = _classify(tags_raw)
                # threat 是上游显式定性字段，优先于 tags 映射；
                # malware_download 等无可映射值时走 tags 兜底。
                ctype = tag_ctype
                if threat:
                    threat_ctype = normalize(threat, URLHAUS_THREAT_MAP)
                    if threat_ctype != "other":
                        ctype = threat_ctype
                # Split tags, filter noise, exclude matched family
                tags = [t.strip() for t in (tags_raw or "").split(",")
                        if t.strip() and t.strip().lower() != "none"]
                meaningful = [t for t in tags if t.lower() not in URLHAUS_ARCH_NOISE]
                native_tags = [t for t in meaningful if t != (malware_name or "")]
                yield ip, Evidence(
                    classification_type=ctype,
                    verdict="malicious",
                    first_seen=row[1].strip().strip('"').replace(" ", "T"),
                    last_seen=row[4].strip().strip('"').replace(" ", "T"),  # recency
                    malware_name=malware_name,            # mirai/Mozi/hajime
                    native_categories=[threat] if threat else [],
                    tags=native_tags,
                    extra={
                        "reporter": row[8].strip().strip('"'),
                        "url_status": row[3].strip().strip('"'),
                        **({"urlhaus_link": row[7].strip().strip('"')}
                           if len(row) > 7 and row[7].strip().strip('"') else {}),
                    },
                )
