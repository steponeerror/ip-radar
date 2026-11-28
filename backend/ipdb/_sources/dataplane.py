"""Dataplane.org sensor signals — Source subclass (multi-signal, per-row class).

dataplane.org (an NFP) publishes per-signal rolling 7-day lists of source IPs
that contacted its sensors. This source merges six of them into one feed (eight since 2026-09-05):

  sshpwauth    — IPs attempting SSH password auth        → brute-force
  telnetlogin  — IPs attempting Telnet login             → brute-force
  dnsrd        — IPs sending recursive DNS queries       → scanner
  sipquery     — SIP probe / enumeration attempts        → brute-force
  sipregistration — SIP registration attempts            → brute-force
  smtpgreet    — IPs greeting SMTP servers (connection)  → scanner
  smtpdata     — SMTP clients sending DATA (actual payload    → spam
                 delivery, spam-cannon signature; deliberate
                 divergence from IntelMQ parser's scanner)
  ntpmode7     — source IPs SENDING monlist requests        → scanner
                 (probers scanning for DDoS amplifiers, per the file
                 header's own wording — NOT the probed open NTP servers,
                 which dataplane does not list; 2026-09-05 fix, was
                 misread victim-side as vulnerable-system)

Each file is pipe-delimited with a fixed shape:

    ASN | ASname | IP | lastseen | category

`download()` fetches every signal and concatenates them into one file (the
`category` column carries the signal, so per-row classification survives the
merge). `harvest()` splits on `|`, validates the IP, normalizes the category via
`DATAPLANE_MAP`, and yields one Evidence per row carrying ASN / AS-name /
last-seen — metadata the existing brute-force/scanner sources don't provide.

Free for non-commercial use only (per the file header); the tool downloads at
runtime and does not redistribute the data.
"""
import ipaddress
import logging

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize
from ._download import atomic_write_bytes

logger = logging.getLogger(__name__)


# dataplane.org signal → IntelMQ. sshpwauth/telnetlogin are credential
# brute-force against the sensor; dnsrd = source IPs sending recursive DNS
# queries (probing), not open resolvers — scanner, not misconfiguration.
DATAPLANE_MAP = {
    "sshpwauth": "brute-force",
    "telnetlogin": "brute-force",
    "dnsrd": "scanner",
    "sipquery": "brute-force",          # SIP 探测(telnetlogin 先例)
    "sipregistration": "brute-force",   # SIP 注册尝试
    "smtpgreet": "scanner",             # SMTP 问候连接(dnsrd 先例)
    "smtpdata": "spam",                 # DATA = 实际投递报文体(非 EXPN/RCPT
                                        # 探测)。与 IntelMQ 官方 parser 的
                                        # scanner 是有意分歧:文件头实测
                                        # "SMTP clients sending DATA commands",
                                        # 垃圾邮件大炮特征,RSIT spam 定义
                                        # (spam infrastructure)更贴合。
    "ntpmode7": "scanner",              # 文件头实测:"source IP addresses
                                        # ... sending NTP mode 7 requests"
                                        # ——探测方(扫 monlist 找放大器),
                                        # 非被探测的开放 NTP。RSIT DDoS
                                        # Amplifier 定义对象是被探测服务,
                                        # dataplane 不列它们(2026-09-05 修正,
                                        # 曾误读 victim 侧归 vulnerable-system)
}


class DataplaneSource(Source):
    name = "dataplane"
    # 上游唯一时间 = 最近一次出现(#523 裁决 Q27):只写 last_seen,不写 first_seen。
    single_timestamp_means = "last_seen"
    category = "threat"
    url = "https://dataplane.org/"
    filename = "dataplane.txt"
    fields = ("is_malicious",)
    classification_type = "brute-force"   # default; harvest overrides per row
    verdict = "malicious"
    stale_days = 1                        # hourly refresh
    reliability = 0.70
    authoritative_for = ()
    # 载入期排除 infra_services curated 单址集(issue #183/ADR 0008 同族;
    # 判例 2026-10-29-ruling-kroot-dataplane-dnsrd(docs/ops/precedents/,
    # 2026-10-29 人裁):k.root 193.0.14.129 被 dnsrd 信号指控——根服不
    # 主动扫描,系伪造源反射假象打传感器的典型画像,真误列,与 cps/
    # tweetfeed 同律;实测刷新后 dataplane.txt 全量 curated 命中恰此
    # 1 行(dnsrd)。数据文件零改写,关 IP_RADAR_INFRA_NOISE_FILTER
    # 重建即复原。
    infra_noise_filter = True

    SIGNALS = {
        "sshpwauth": "https://dataplane.org/signals/sshpwauth.txt",
        "telnetlogin": "https://dataplane.org/signals/telnetlogin.txt",
        "dnsrd": "https://dataplane.org/signals/dnsrd.txt",
        "sipquery": "https://dataplane.org/signals/sipquery.txt",
        "sipregistration": "https://dataplane.org/signals/sipregistration.txt",
        "smtpgreet": "https://dataplane.org/signals/smtpgreet.txt",
        "smtpdata": "https://dataplane.org/signals/smtpdata.txt",
        "ntpmode7": "https://dataplane.org/signals/ntpmode7.txt",
    }

    def download(self, token=None) -> None:
        """逐信号拉取 join 单文件(SA-F1):成功 parts join 原子写 + 失败信号
        记 self.last_partial_failure;全挂 raise。join 文件无法新旧混合,
        部分失败的缩水窗口由 scheduler 的 done-但-部分失败 backoff 封顶
        (1h→2h→4h→8h→12h 逐次翻倍退避梯,封顶 12h,非整个 stale 周期;
        计划已裁)。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        parts: list[bytes] = []
        failed: list[str] = []
        for name, url in self.SIGNALS.items():
            try:
                data = self._http_get(url)
            except Exception as e:
                logger.warning(f"dataplane {name} fetch failed: {e}")
                failed.append(name)
                continue
            if not data.strip():
                logger.warning(f"dataplane {name}: empty response")
                failed.append(name)
                continue
            parts.append(data)
        self.last_partial_failure = failed
        if not parts:
            raise RuntimeError(
                f"dataplane: all signals failed to download ({list(self.SIGNALS)})")
        atomic_write_bytes(self._path, b"\n".join(parts))

    def harvest(self):
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.lstrip().startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 5:
                    continue
                asn_raw, as_name, ip, last_seen, category = (
                    parts[0], parts[1], parts[2], parts[3], parts[4])
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    continue
                try:
                    asn = int(asn_raw)
                except ValueError:
                    asn = None
                ctype = normalize(category, DATAPLANE_MAP)
                yield f"{ip}/{128 if ':' in ip else 32}", Evidence(
                    classification_type=ctype,
                    verdict=self.verdict,
                    last_seen=last_seen,   # 单时间源只写 last_seen(#523;时钟按它)
                    asn=asn,
                    as_name=as_name or None,
                    native_categories=[category],
                )
