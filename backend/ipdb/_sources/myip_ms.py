"""myip.ms (myip.ms) htaccess blacklist — IpListSource with deny-from parse_raw.

myip.ms 自有爬虫全网抓取 + 用户滥用举报记录聚合的活跃黑名单,htaccess 形态
发布(「deny from <ip>」行 + '#' 头注释;头行内嵌生成时间戳,10 天滚动窗,
实测 2026-10-19:1,621 行 = 1,565 唯一 v4 + 56 v6,云爬虫浓度高 GCP 34.x /
Aliyun 47.x)。排他率 46.0%(138/300,N=300 对池探针,seed 20261018,对照
20/20;dossier docs/research/2026-10-19-tails-discover.md)。

许可:文件头「Copyright 2026, Myip.ms」,无再分发授权声明,且站点已知限流
(免费档逐日拉取额度有限)——按用户裁决 2026-10-19「有增量价值的都入队」
签核收录(ustc_blackip 同款;rtbh 判例)。stale_days=4:10 天滚动窗意味着
4 天不更新仍在窗内非死键,但限流环境下留出重试余量、不必逐日判死。

parse 决策(skill Phase-1,选项 A 语义):剥前缀走 IpListSource 父类管线,
落点选基类钦定钩子 parse_raw(tor_exits 先例)而非覆写 download()——父类
download() 本就调用 parse_raw 并原子安装归一化产物,中间文件即裸 IP 列表,
rebuild/query 全走父类零重实现;选项 B(harvest)需整链重写而灰区触发器
全不命中(无行过滤/条件路由/1→多/归档),弃。parse_raw 内即做 ip_address
版本感知校验:限流页/HTML 错误页会解析出零条目 → 触发父类 download() 的
空载荷 RuntimeError(前一份好证据原样保留),同时 v6 deny 行不被丢弃。
"""
import ipaddress
import re
from ._base import IpListSource


_DENY_RE = re.compile(r"^deny\s+from\s+(\S+)$")


class MyipMsSource(IpListSource):
    name = "myip_ms"
    category = "threat"
    url = "https://myip.ms/files/blacklist/htaccess/latest_blacklist.txt"
    filename = "myip_ms"
    fields = ("is_malicious",)          # decorative for typed sources; base uses classification_type
    classification_type = "blacklist"   # brief 2026-10-19 wave-4 T2
    verdict = "malicious"
    stale_days = 4                      # 10 天滚动窗;限流环境留重试余量(见 docstring)
    reliability = 0.55                  # brief 2026-10-19
    provenance_tier = "B"               # B=社区(第三方自有爬虫非自采;sblam 同档)
    authoritative_for = ()               # corroboration only (SM-F1)
    honeypot_methodology = False        # 全网爬虫+滥用举报,非诱饵部署

    def parse_raw(self, raw: bytes) -> list[str]:
        """剥「deny from 」前缀 → 裸 IP 归一化文件;注释/空行/非 deny 行/
        非 IP 载荷丢弃,v4/v6 均收(父类 rebuild 原生双族解析)。"""
        ips = []
        for line in raw.decode(errors="ignore").splitlines():
            m = _DENY_RE.match(line.strip())
            if not m:
                continue
            try:
                ipaddress.ip_address(m.group(1))   # 版本感知(v6 deny 行也收)
            except (ipaddress.AddressValueError, ValueError):
                continue
            ips.append(m.group(1))
        return ips
