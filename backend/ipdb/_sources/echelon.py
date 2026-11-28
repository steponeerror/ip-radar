"""Echelon Labs per-tag blocklists — 多子表目录源(blocklist_de 模式).

echelonlabs.co(Echelon Labs 蜜罐传感网联盟)61 个行为分标签端点,每标签
``https://echelonlabs.co/api/tag/block/<slug>`` 返回纯文本一行一 IPv4(免
认证,Vercel CDN;2026-11-22 实测)。每标签一文件目录布局,per-tag 分类
(ECHELON_MAP);同 IP 命中多标签按
exploit > brute-force > infected-system > scanner > other > blacklist
裁决 classification_type,全部认领标签名保留在 native_categories
(blocklist_de 先例)。

slug 清单(权威,2026-11-22 实测核对):站方 /tags 页 50 标签(slug 化 =
lowercase、非字母数字串折单连字符)+ 11 个遗留仍供数标签;排除上游拼写
死标签 ``web-commad-injection``。41+ 标签当日有数据(活性锚:首页 30 分钟
级条目);连接尝试类标签混大量 VPN 出口噪音(实测 x4bnet 覆盖全集合 56%),
reliability 0.70 而非更高。

许可 FLAG(2026-11-22 发现轮,用户裁定立项接受):站点只写 R&E 社区免费
层,未标注数据再分发许可——按非商用本地情报用途收。

下载契约:61 个 GET 串行(小文件走 CDN,礼貌不并发);空标签文件 = 当日
无该类攻击(合法空,blocklist_de 判例 ircbot);但**全部文件都空/失败** =
上游断供 → RuntimeError + 零替换(fail-closed 防灾难性全空清库——本源无
blocklist_de 式聚合锚列表,活性判据 = 全量非空集)。
"""
import logging
import os
from pathlib import Path

from ._base import IpListSource
from ._download import download_file, CancelToken, CancelledError
from ._lmdb import commit_dual_family
from ._rebuild_tail import covered_counts
from .._evidence import Evidence

_BASE_URL = "https://echelonlabs.co/api/tag/block"

logger = logging.getLogger(__name__)

# Echelon Labs 行为分标签 slug → IntelMQ(2026-11-22 三源批)。谱系 =
# 站方 /tags 页 50 标签 + 11 个遗留仍供数标签(见 _sources/echelon.py
# _SLUGS 注释),61 slug 闭集;站方八大类(Recon/Web-attack/Brute-force/
# Botnet/Exploit/Cve/Activity/Tooling)作参考,按行为语义映射:
# - probe/hunt/enumeration/crawl/「connection-attempt」(Activity TCP 连接
#   尝试,非凭证攻击)→ scanner;「login-attempt」/auth-attempt/
#   bruteforcer/credential-spray → brute-force(connection/login 二分 =
#   连接层 vs 凭证层,rsync smtp-auth-attempt 入 brute 系依 blocklist_de
#   "mail" 先例);
# - Outlaw/P2Pinfect/Mirai 族(botnet 类)= 已感染 drone 宿主 →
#   infected-system(URLHAUS_MAP "mirai" 先例;mirai-scanner 的宿主在跑
#   mirai 扫描,感染事实优先于当次行为);
# - exploit/Cve/Web-attack 类(RCE/auth-bypass/traversal/toolshell/
#   php2shell-tooling=webshell 工具化利用)→ exploit;
# - tls(无差别 TLS 活动遗留标签)无净槽 → other(原值由
#   native_categories 保存,SW_THREATS_MAP "abuse" 先例)。
# 测试 test_echelon.test_map_covers_all_slugs 钉 map 键 == _SLUGS(上游
# 改名/新增标签当天绊线,不静默落 other)。
ECHELON_MAP = {
    # scanner 系(Recon 探测 / 爬取 / 通用 hunt / 连接尝试)
    "admin-panel-hunt": "scanner",
    "cgi-script-hunt": "scanner",
    "cisco-asa-probe": "scanner",
    "cisco-ucm-probe": "scanner",
    "citrix-adc-gateway-probe": "scanner",
    "cms-enumeration": "scanner",
    "config-file-hunt": "scanner",
    "cpanel-probe": "scanner",
    "database-admin-hunt": "scanner",
    "enterprise-software-probe": "scanner",
    "exchange-probe": "scanner",
    "fortios-api-probe": "scanner",
    "fortios-ssl-vpn-probe": "scanner",
    "globalprotect-probe": "scanner",
    "ivanti-connect-secure-probe": "scanner",
    "mcp-server-scan": "scanner",
    "port-scan": "scanner",
    "rdp-connection-attempt": "scanner",      # Activity:TCP 连接尝试,非凭证
    "redis-connection-attempt": "scanner",
    "sharepoint-webshell-scanning": "scanner",  # 寻找已植 webshell = 探测
    "sip-register-scanner": "scanner",
    "solarwinds-probe": "scanner",
    "sonicwall-ngfw-probe": "scanner",
    "ssh-connection-attempt": "scanner",      # connection ≠ login(见上)
    "telnet-connection-attempt": "scanner",
    "tls-ssl-crawler": "scanner",
    "web-crawler": "scanner",
    "web-shell-hunt": "scanner",
    "wordpress-enumeration": "scanner",
    # brute-force 系(凭证/协议爆破)
    "iot-default-credential-attempt": "brute-force",
    "mirai-credential-spray": "brute-force",
    "mirai-default-credential-spray": "brute-force",
    "smtp-auth-attempt": "brute-force",       # SMTP 认证尝试=凭证攻击
    "smtp-bruteforcer": "brute-force",
    "ssh-bruteforcer": "brute-force",
    "ssh-login-attempt": "brute-force",       # login=凭证层,connection 异
    "telnet-bruteforcer": "brute-force",
    "telnet-login-attempt": "brute-force",
    "vnc-login-attempt": "brute-force",
    # infected-system 系(Botnet 族宿主)
    "mirai-scanner": "infected-system",
    "outlaw-botnet": "infected-system",
    "p2pinfect-botnet": "infected-system",
    # exploit 系(Web-attack/Exploit/Cve/Tooling)
    "cisco-ucm-exploit": "exploit",
    "cpanel-auth-bypass-cve-2026-41940": "exploit",
    "directory-traversal-attempt": "exploit",
    "file-upload-attempt": "exploit",
    "fortios-authentication-bypass-attempt": "exploit",
    "fortios-ssl-vpn-pre-auth-path-traversal": "exploit",
    "ivanti-epmm-exploit": "exploit",
    "path-traversal-attempt": "exploit",
    "php2shell-tooling": "exploit",           # Tooling:webshell 工具化利用
    "phpunit-rce-scan": "exploit",            # PHPUnit RCE 打点(eval-stdin)
    "router-exploit": "exploit",
    "sharepoint-active-exploitation": "exploit",
    "sharepoint-toolshell-exploit": "exploit",
    "sql-injection-attempt": "exploit",
    "thinkphp-rce": "exploit",
    "uri-parsing-exploit": "exploit",
    "web-vulnerability-exploit": "exploit",
    "wordpress-auth-bypass": "exploit",
    # other(无净槽,原值留 native_categories)
    "tls": "other",
}

# 61 slug = /tags 页 50(slug 化规则见模块 docstring)+ 11 遗留:
# web-crawler/vnc-login-attempt/uri-parsing-exploit/path-traversal-attempt/
# sharepoint-toolshell-exploit/wordpress-auth-bypass/wordpress-enumeration/
# web-shell-hunt/web-vulnerability-exploit/mirai-default-credential-spray/tls。
# 排除 web-commad-injection(上游拼写死标签)。排序 = 迭代序 =
# native_categories 记录序(确定性);测试钉 set(_SLUGS) == set(ECHELON_MAP)。
_SLUGS = [
    "admin-panel-hunt", "cgi-script-hunt", "cisco-asa-probe",
    "cisco-ucm-exploit", "cisco-ucm-probe", "citrix-adc-gateway-probe",
    "cms-enumeration", "config-file-hunt", "cpanel-auth-bypass-cve-2026-41940",
    "cpanel-probe", "database-admin-hunt", "directory-traversal-attempt",
    "enterprise-software-probe", "exchange-probe", "file-upload-attempt",
    "fortios-api-probe", "fortios-authentication-bypass-attempt",
    "fortios-ssl-vpn-pre-auth-path-traversal", "fortios-ssl-vpn-probe",
    "globalprotect-probe", "iot-default-credential-attempt",
    "ivanti-connect-secure-probe", "ivanti-epmm-exploit", "mcp-server-scan",
    "mirai-credential-spray", "mirai-default-credential-spray",
    "mirai-scanner", "outlaw-botnet", "p2pinfect-botnet",
    "path-traversal-attempt", "php2shell-tooling", "phpunit-rce-scan",
    "port-scan", "rdp-connection-attempt", "redis-connection-attempt",
    "router-exploit", "sharepoint-active-exploitation",
    "sharepoint-toolshell-exploit", "sharepoint-webshell-scanning",
    "sip-register-scanner", "smtp-auth-attempt", "smtp-bruteforcer",
    "solarwinds-probe", "sonicwall-ngfw-probe", "sql-injection-attempt",
    "ssh-bruteforcer", "ssh-connection-attempt", "ssh-login-attempt",
    "telnet-bruteforcer", "telnet-connection-attempt", "telnet-login-attempt",
    "thinkphp-rce", "tls", "tls-ssl-crawler", "uri-parsing-exploit",
    "vnc-login-attempt", "web-crawler", "web-shell-hunt",
    "web-vulnerability-exploit", "wordpress-auth-bypass",
    "wordpress-enumeration",
]

# 同 IP 多标签裁决优先级:具体攻击行为 > 泛行为 > 兜底(blocklist_de
# _PRIORITY 先例;数值小者胜)
_PRIORITY = {"exploit": 0, "brute-force": 1, "infected-system": 2,
             "scanner": 3, "other": 4, "blacklist": 5}


class EchelonSource(IpListSource):
    name = "echelon"
    category = "threat"
    url = ""  # unused — custom download() handles 61 tag endpoints
    url_exempt = True  # #253:url 有意空串(多端点走 _BASE_URL),护栏豁免
    filename = "echelon"  # directory name
    fields = ("is_malicious",)
    classification_type = "blacklist"   # 兜底(映射外 slug,当前 61 全覆盖)
    verdict = "malicious"
    stale_days = 3     # 持续滚动无内部 ts;活性证据 = 首页 30 分钟级条目
    reliability = 0.70  # 第一方传感网;连接尝试类混 VPN 出口噪音(见 docstring)
    authoritative_for = ()
    provenance_tier = "A"     # A=官方一手(S21):Echelon Labs 官方 API 直接发布
    honeypot_methodology = True   # 蜜罐传感网采集(S33;k_nonhoneypot 剔除)
    infra_noise_filter = False         # 显式关:存量源行为不变(#531;基类默认已翻 True)

    def __init__(self, data_dir: Path, selected_tags: list[str] | None = None):
        self._tags = selected_tags or list(_SLUGS)
        super().__init__(data_dir=data_dir)
        self._path = data_dir / "echelon"   # directory, not file
        self._files = [self._path / f"{slug}.txt" for slug in self._tags]

    @property
    def download_host(self) -> str | None:
        return "echelonlabs.co"

    def download(self, token: CancelToken | None = None) -> None:
        """两阶段批量下载(blocklist_de 模式):逐标签抓 ``<slug>.txt.dl``
        scratch → 全量空门裁决后统一 os.replace 落地(空文件照落)。

        空文件语义(bare-IP 列表,blocklist_de 判例):单标签 200 空 = 当日
        无该类攻击,合法空。fail-closed 判据(本源无聚合锚):**全部标签**
        空或失败 = 上游断供 → scratch 全清、零替换、RuntimeError(防下轮
        rebuild 静默清库)。单标签抓取异常容忍:旧文件保留、记名
        last_partial_failure(SA-F1 部分失败梯),cancel 直 raise。"""
        self._path.mkdir(parents=True, exist_ok=True)
        landed: list[tuple[Path, Path]] = []   # (scratch, dest) 待裁决
        failed: list[str] = []
        try:
            for slug in self._tags:
                if token is not None and token.is_cancelled():
                    raise CancelledError(f"{self.name} download cancelled")
                dest = self._path / f"{slug}.txt"
                scratch = dest.with_name(dest.name + ".dl")
                logger.info(f"Downloading echelon/{slug}...")
                try:
                    download_file(f"{_BASE_URL}/{slug}", scratch, token=token,
                                  headers={"User-Agent": "ip-lookup-tool/1.0"})
                    landed.append((scratch, dest))
                except Exception as e:
                    failed.append(slug)
                    logger.warning(
                        f"Failed to download echelon/{slug}: {e} "
                        f"— keeping existing file")
                    scratch.unlink(missing_ok=True)
            if not any(s.read_bytes().strip() for s, _ in landed):
                for scratch, _ in landed:
                    scratch.unlink(missing_ok=True)
                raise RuntimeError(
                    f"echelon: all {len(self._tags)} tag files empty or "
                    f"failed — upstream appears dead, keeping existing data "
                    f"(fail-closed)")
            for scratch, dest in landed:
                os.replace(scratch, dest)      # 合法空 0 字节照落
        except CancelledError:
            for scratch, _ in landed:          # 已抓未裁决 scratch 不残留
                scratch.unlink(missing_ok=True)
            raise
        self.last_partial_failure = failed

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一重建入口)。多标签累积(blocklist_de 模式):同
        CIDR 按优先级裁决 classification_type,全部认领标签名进
        native_categories(_SLUGS 序)。"""
        import ipaddress as _ipa
        if not self._path.exists():
            return 0

        # cidr -> {"classification_type": ..., "native_categories": [...]}
        acc: dict[str, dict] = {}
        for slug in self._tags:
            p = self._path / f"{slug}.txt"
            if not p.exists():
                continue
            cls = ECHELON_MAP.get(slug, "blacklist")
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        net = str(_ipa.ip_network(line, strict=False))
                    except (ValueError, _ipa.AddressValueError,
                            _ipa.NetmaskValueError):
                        continue
                    if net in acc:
                        cur = acc[net]
                        if _PRIORITY[cls] < _PRIORITY[cur["classification_type"]]:
                            cur["classification_type"] = cls
                        if slug not in cur["native_categories"]:
                            cur["native_categories"].append(slug)
                    else:
                        acc[net] = {"classification_type": cls,
                                    "native_categories": [slug]}

        records = [
            (cidr, [Evidence(
                classification_type=info["classification_type"],
                verdict=self.verdict,
                reliability=self.reliability,
                native_categories=info["native_categories"],
            ).to_dict()])
            for cidr, info in acc.items()
        ]

        cov4, cov6 = covered_counts(acc)
        return commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)

    def _data_files(self) -> list[Path]:
        # #465 卡16:目录型源只声明数据文件清单,新鲜度算法统一走基类
        # health() → _freshness(本类旧 health() 覆写与基类算法逐字段
        # 等价,已删;工单验收含改前改后 health() 逐字段比对)。
        return list(self._files)
