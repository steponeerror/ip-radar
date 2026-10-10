"""DNSCrypt public-resolvers community feed — fetched Source subclass.

https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/
public-resolvers.md is the DNSCrypt project's community resolver list
(maintainer: Frank Denis / jachym@… — see file header), v3 stamp format:
`sdns://<base64url>` with byte0 proto (0x01 DNSCrypt, 0x02 DoH), u64 LE
props, then varstrings (len-byte + bytes). Each `## <slug>` section is one
resolver; its stamp lines carry the endpoint addresses. Only IP literals are
harvested (DNSCrypt `ip[:port]` / `[v6]:port`; DoH first varstr ip / `[v6]`) —
hostname-only and empty addresses are skipped (宁少算: no DNS resolution),
and unknown protos (0x03 odoh / 0x04 doq / 0x05 relay) get the same
conservative first-varstr treatment (design ruling 2026-10-10). Same IP under
multiple sections dedups to one row; the provider label is the first
section's name verbatim. props bits are deliberately NOT decoded into
vocabulary. service="dns" rides the asset slot; verdict="" abstention, same
spelling as infra_services/root_servers (R17A-1: to_dict 特判保留,读回按
"" 处理不兑底).

License status: the repo carries NO LICENSE file — factual IP data, consumed
for attribution purposes. The upstream file header itself lists mirror URLs
(download.dnscrypt.info / cdn.jsdelivr.net) as the intended distribution
channel — mirror-retry download is a noted upgrade path, not implemented.
"""
import base64
import binascii
import ipaddress
import logging
import re

from .._evidence import Evidence
from .._source_base import Source
from ._download import atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)

_URL = ("https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/"
        "master/v3/public-resolvers.md")

# section 切分:`## a-and-a` 行;`#` 单井文件头与 `--` 分隔条天然不匹配
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
_MIN_STAMP_LINES = 50   # download 守卫阈值(实测快照 890 行,余量充足)


def _addr_to_ip(addr: str) -> str | None:
    """stamp 地址 varstr → 规范化 IP 字面量;非字面量/空 → None。

    `[v6]` 去括号([v6]:port 同)、`v4:port` 去端口(host 仍含冒号即裸 v6,
    不剥);末过 ip_address() 兜底,失败即跳(宁少算:不猜不解析域名)。
    """
    if not addr:
        return None
    if addr.startswith("[") and "]" in addr:
        addr = addr[1:addr.index("]")]
    elif ":" in addr:
        host, _, port = addr.rpartition(":")
        if port.isdigit() and ":" not in host:
            addr = host
    try:
        return str(ipaddress.ip_address(addr))
    except ValueError:
        return None


def _decode_stamp_ip(b64: str) -> str | None:
    """`sdns://` 载荷(base64url 无补齐)→ 首 varstr 的 IP,坏编码 → None。

    纯函数便于测试。跳过 proto(1)+ props u64(8)后取第一个 varstr——
    proto 只影响后续字段布局,首 varstr 恒为地址(裁定:任何 proto 同此
    保守处理)。
    """
    try:
        raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    except (binascii.Error, ValueError):
        return None
    if len(raw) < 10:           # proto + u64 props + ≥1 长度字节
        return None
    n = raw[9]
    if 10 + n > len(raw):
        return None
    return _addr_to_ip(raw[10:10 + n].decode("utf-8", errors="replace"))


class DnsPublicSource(Source):
    name = "dns_public"
    category = "asset"
    fields = ("service",)
    url = _URL
    filename = "dns_public.md"
    stale_days = 7              # 周更 feed,7 天余量
    reliability = 0.9
    authoritative_for = ("service",)

    def download(self, token=None) -> None:
        """GET public-resolvers.md → 校验 → 原子落盘。

        ≥50 个 `sdns://` 行才放行(200-OK 空/坏内容守卫,skill Phase 3 §8:
        空文件落地会被下次 rebuild 静默清源);失败在写盘前抛出,既有数据
        文件不动。不做镜像重试(留 docstring 升级注记)。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = self._http_get(_URL)
        text = data.decode("utf-8", errors="replace")
        n = sum(1 for ln in text.splitlines()
                if ln.strip().startswith("sdns://"))
        if n < _MIN_STAMP_LINES:
            raise RuntimeError(
                f"dns_public: only {n} sdns:// lines (<{_MIN_STAMP_LINES}) "
                f"from {redact_url(_URL)} — existing data file kept")
        atomic_write_bytes(self._path, data)
        logger.info(f"Downloaded {self.name} ({n} sdns stamps)")

    def harvest(self):
        seen: set[str] = set()          # 同 IP 去重:文件序首见者胜
        section = None
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                m = _SECTION_RE.match(line)
                if m:
                    section = m.group(1)
                    continue
                if not line.startswith("sdns://"):
                    continue            # 文件头/正文噪声容错跳过
                if section is None:
                    continue            # 首个 section 前无归属,宁少算
                ip = _decode_stamp_ip(line[len("sdns://"):].strip())
                if ip is None or ip in seen:
                    continue
                seen.add(ip)
                yield ip, Evidence(
                    service="dns",
                    native_types={"service": section},
                    verdict="",  # 弃权拼写:同 infra_services(R17A-1)
                )
