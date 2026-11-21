"""gaoyifan/china-operator-ip — 中国运营商聚合 CIDR 清单(A 家族 Source,
iptoasn 同款:harvest 逐行 CIDR → Evidence)。

数据面:GitHub Actions 每日自 ip-lists 分支发布,无鉴权直下。
china.txt(IPv4,实抓 2026-11-18:6,221 行)与 china6.txt(IPv6,3,444 行)
各为纯 CIDR 行式清单——无表头/无注释/无脏行/无裸 IP 记法,download()
按 x4bnet_vpn 双 URL 拼接模式合落单文件,v6 兄弟失败保旧件记
last_partial_failure(["china6.txt"]),v4 失败记 ["china.txt"] 并 raise。

语义:「可信国内 BGP 分类 + 未宣告 RIR-CN 登记兜底」的中国地址聚合
(china.txt 为运营商超集)。信息位不指控:verdict="" 弃权拼写
(rir_delegated R17A-1 同款),classification_type=None,唯一结构化
证据=country_code="CN"(SCALAR_SLOTS)+ ip_range(canonical 槽,iptoasn
同款查询期直接落,不走路由)。文件无内部时间戳,新鲜度信号=ip-lists
分支提交日期(publisher-liveness 通道),本地数据 mtime 走 health 缺省。
"""
import logging

from .._evidence import Evidence
from .._source_base import Source
from ._download import CancelToken, atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)

_V4_URL = ("https://raw.githubusercontent.com/gaoyifan/"
           "china-operator-ip/ip-lists/china.txt")
_V6_URL = ("https://raw.githubusercontent.com/gaoyifan/"
           "china-operator-ip/ip-lists/china6.txt")


class GaoyifanChinaOperatorIPSource(Source):
    name = "gaoyifan_china_operator_ip"
    category = "geo_asn"           # 路由与分配族(cn_isp/iptoasn 同档)
    url = _V4_URL
    filename = "gaoyifan_china_operator_ip.txt"
    fields = ("country_code", "ip_range")   # 不投任何指控字段
    stale_days = 7                  # 上游 Actions 日更;7d silence = feed dead
    reliability = 0.85              # BGP+RIR 派生社区发布(cn_isp 同档)
    provenance_tier = "B"           # 社区
    authoritative_for = ()          # corroboration only(country_code 投票)
    single_evidence = True          # ~10k CIDR 单证据流式,OOM 守卫

    def download(self, token: CancelToken | None = None) -> None:
        """v4+v6 双 URL 拼接单文件(x4bnet_vpn 同型):v6 失败保旧不覆写,
        记 last_partial_failure=["china6.txt"];v4 失败记 ["china.txt"]
        并 raise(退避重试);全绿清空信号。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            v4 = self._http_get(self.url, token=token)
            if not v4.strip():
                raise RuntimeError(f"empty response from {redact_url(self.url)}")
        except Exception:
            self.last_partial_failure = ["china.txt"]
            raise
        try:
            v6 = self._http_get(_V6_URL, token=token)
            if not v6.strip():
                raise RuntimeError(
                    f"empty v6 sibling from {redact_url(_V6_URL)}")
        except Exception as e:
            logger.warning(
                f"{self.name}: china6 fetch failed: {e} — keeping existing file")
            self.last_partial_failure = ["china6.txt"]
            return
        self.last_partial_failure = []
        if v4 and not v4.endswith(b"\n"):
            v4 += b"\n"
        if v6 and not v6.endswith(b"\n"):
            v6 += b"\n"
        atomic_write_bytes(self._path, v4 + v6)
        logger.info(f"Downloaded {self.name} "
                    f"({v4.count(b'\\n') + v6.count(b'\\n')} lines)")

    def harvest(self):
        import ipaddress as _ipa
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    net = _ipa.ip_network(line, strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                yield str(net), Evidence(
                    country_code="CN",
                    ip_range=str(net),
                    verdict="",        # 弃权拼写(R17A-1):信息位不指控
                )


# ── PEP 562 装载别名:三种规范拼法可导入,不进 dir()(防 roster 双注册)──
_IMPORT_ALIASES = {
    "GaoyifanchinaoperatoripSource": "GaoyifanChinaOperatorIPSource",
    "GaoyifanChinaOperatorIpSource": "GaoyifanChinaOperatorIPSource",
    "GAOYIFANChinaOperatorIPSource": "GaoyifanChinaOperatorIPSource",
}


def __getattr__(name):
    if name in _IMPORT_ALIASES:
        return globals()[_IMPORT_ALIASES[name]]
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}")
