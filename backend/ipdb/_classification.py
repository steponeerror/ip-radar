"""IntelMQ classification.type vocabulary + native→IntelMQ mapping helpers.

Governance: add new classification.type values to CLASSIFICATION_TYPES with a
short comment. Add per-source `{native: intelmq}` maps alongside the source.
No separate YAML/versioning process (YAGNI for this tool's scale).

对照基准(词表版本锚定):RSIT v1003 (machinev1, enisaeu/RSIT-TF) /
IntelMQ develop@bbe452a 2026-04 — 审计 2026-09-05(官方 allowed_values
45 型;本地取子集,方言仅剩 abuse-reports;botnet 已于 P1 2026-09-05
迁往官方型 infected-system)。上游词表改版时重跑对照。
"""
import logging
from collections import Counter

# IntelMQ classification.type subset relevant to IP threat intel. Extensible.

logger = logging.getLogger(__name__)
CLASSIFICATION_TYPES = frozenset({
    "blacklist",            # generic curated blocklist, no subcategory available
    "c2-server",            # command & control
    "malware-distribution", # serves/delivers malware (e.g. ThreatFox payload_delivery)
    "malware",              # malware sample / payload
    "scanner",              # aggressive scanning
    "brute-force",          # credential/protocol brute force (e.g. blocklist_de ssh)
    "phishing",
    "infected-system",      # 被恶意软件感染的主机(botnet drone;
                            # P1 2026-09-05 迁自方言类型 botnet,
                            # RSIT malicious-code.infected-system)
    "exploit",
    "proxy",
    "tor",
    "vulnerable-system",
    "misconfiguration",
    "abuse-reports",
    "spam",
    "ddos",
    # benign② 断言域(#188,2026-10-24):infra_services 良性断言的分类
    # 面标签(服务角色),非威胁词汇 RSIT 子集——良性断言是判断面输入
    # (与指控同场=verdict_conflict),不产 STIX Indicator;注册于此使
    # 本表保持 classification_type 可发值的单一真源。
    "dns",
    "ntp",
    "other",                # fallback for unmappable values
})

THREATFOX_MAP = {
    "botnet_cc": "c2-server",
    "payload_delivery": "malware-distribution",
    "payload": "malware",
    "cc_skimming": "phishing",
    "url": "malware-distribution",
}

# blocklist_de 子列表文件名 -> IntelMQ（2026-08-15 已激活，键=子列表文件名）。
# 源按文件名分发到对应 attack-type（ssh/bruteforcelogin/ftp/imap/sip/mail →
# brute-force；mail = attacks on Mail/Postfix，攻击邮件服务的攻击者，与
# ssh 同族，2026-09-05 修正——曾误归 spam；bots = IRC/论坛/wiki 灌水（上游
# 原文 "spammed on IRC, open forums, wikis"），同日修正——曾误归 botnet；
# ircbot → infected-system(P1 2026-09-05 迁自方言 botnet,IntelMQ
# 官方即此型:IRC bot 受害主机 = 已感染 drone,非 C2);
# apache → scanner。strongips/all 无类型信息，不进表，由源代码兜底
# blacklist（见 Task 6 实现）。对照：IntelMQ 官方 parser 对攻击类子列表
# 一律归 ids-alert（告警来源标签），我们按行为语义化，分歧有意为之。
BLOCKLIST_DE_MAP = {
    "ssh": "brute-force",
    "bruteforcelogin": "brute-force",
    "ftp": "brute-force",
    "imap": "brute-force",
    "sip": "brute-force",
    "mail": "brute-force",
    "bots": "spam",
    "ircbot": "infected-system",
    "apache": "scanner",
}

# ip2proxy proxy_type → IntelMQ. EMPTY since ADR 0001 (2026-10-12, grill Q1):
# ip2proxy 全量资产弃权(VPN/PUB/TOR 继 DCH/SM-F2 之后),生产路径在
# ip2proxy._proxy_evidence 就走 asset-only 分支(classification_type=None,
# verdict="" 弃权),四型都不再喂给这张表。保持空表而非删定义:若回归把
# proxy_type 重新接回 normalize(),一律落 "other" 且绊线告警 —— 绝不
# 静默恢复 "proxy"/"tor" 指控(unmapped types must ring, no per-key
# exemption)。
PROXY_MAP = {}

# OTX pulse name protocol keyword -> IntelMQ. The /pulses/activity feed is
# auto-generated "IMMEDIATE THREAT: {PROTO} Intrusion from..." pulses with
# adversary="Automated Scanner". Protocol keywords from the pulse name map
# to IntelMQ categories; unmapped protocols default to "scanner".
OTX_PROTOCOL_MAP = {
    "smtp": "brute-force",
    "ftp": "brute-force",
    "ssh": "brute-force",
    "imap": "brute-force",
    "pop3": "brute-force",
    "rdp": "brute-force",
    "sip": "brute-force",
    "http": "scanner",
    "https": "scanner",
    "apache": "exploit",
    "web": "scanner",
}

# otx_subscribed indicator 自带 role 字段(pr0viehh 蜜罐逐 IP 角色标签,
# 2026-10-07 实测仅 bruteforce 一种取值)→ IntelMQ。未命中走 pulse 名关键词
# 兜底链(otx_subscribed._NAME_RULES),两个都 miss → blacklist。
OTX_SUBSCRIBED_ROLE_MAP = {
    "bruteforce": "brute-force",
}

# TweetFeed (0xDanielLopez/TweetFeed) — infosec-X IOC feed. The `tag` field is a
# space-separated hashtag list (e.g. "#C2 #CobaltStrike"); tweetfeed.harvest
# splits it and applies the FIRST mappable hashtag. C2/RAT-infra tags collapse
# to c2-server; malware-family tags without a vocab slot (#ransomware, #APT…)
# fall to "other" with the raw tag preserved in extra.native_type (Convention 2).
TWEETFEED_MAP = {
    "#phishing": "phishing",
    "#c2": "c2-server",
    "#cobaltstrike": "c2-server",
    "#remcos": "c2-server",
    "#sliver": "c2-server",
    "#interactsh": "c2-server",
    "#deimos": "c2-server",
    "#asyncrat": "c2-server",
    "#formbook": "c2-server",
    "#quasar": "c2-server",
    "#malware": "malware",
    "#botnet": "infected-system",
    "#mirai": "infected-system",
    "#mozi": "infected-system",
    "#ddos": "ddos",
}

# URLhaus (abuse.ch) malware-distribution-URL feed. The `tags` column is a
# comma-separated list mixing malware-family names with file/arch noise
# (``32-bit,elf,mips,Mozi``). urlhaus.harvest splits on ``,`` and applies the
# first mappable tag. Only IoT-botnet families map to ``infected-system``
# (P1 2026-09-05 迁自方言 botnet:mirai/Mozi/hajime 的宿主 = 已感染
# drone,非 C2);every other row falls to ``malware-distribution``
# (the base classification — every URLhaus URL serves malware), so ``other``%
# stays near 0. Raw tags + reporter are preserved in ``extra``.
URLHAUS_MAP = {
    "mirai": "infected-system",
    "mozi": "infected-system",
    "hajime": "infected-system",
}

# urlhaus `threat` 列（row[5]）原值 → IntelMQ。threat 是上游显式定性字段，
# 优先于 tags 映射；malware_download 无可映射值，落 tags 兜底链路。
URLHAUS_THREAT_MAP = {
    "credential_phishing": "phishing",
}

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

# reportedip (reportedip.de) — CSV `categories` 字段是 ;-分隔数字码。1-58 全码
# 均为官方公开分类(per https://reportedip.com/wp-json/reportedip/v2/categories):
# 1-30 通用攻击,31-58 WordPress 攻击细分。code→IntelMQ 映射基于官方分类名语义。
# 一个 IP 多码 → N evidence(按 canonical 分组);未在表内的未来新增码(59+)→ other 兜底。
# code 9 Open Proxy→proxy、code 29 Zero-Day→exploit 为语义修正(映射语义要对,非数据驱动)。
REPORTEDIP_MAP = {
    # 1-30 通用
    "1": "scanner", "2": "scanner", "14": "scanner",       # DNS compromise/poisoning, port scan
    "3": "phishing", "7": "phishing", "8": "phishing", "17": "phishing",  # fraud/phishing/spoofing
    "4": "ddos", "6": "ddos",
    "5": "brute-force", "18": "brute-force", "22": "brute-force",  # FTP/credential/SSH brute-force
    "9": "proxy",                                          # open proxy
    "10": "spam", "11": "spam", "12": "spam",               # web/email/blog spam
    "15": "exploit", "16": "exploit", "19": "exploit", "21": "exploit",  # hacking/SQLi/bad-bot/web-app
    "20": "malware", "24": "malware", "25": "malware", "26": "malware", "27": "malware",  # exploited/mining/C2/trojan
    "23": "infected-system",                               # IoT targeted(drone 宿主)
    "28": "other", "29": "exploit", "30": "c2-server",     # supply chain(无净 IntelMQ 槽)/zero-day/nation-state
    "13": "proxy",                                         # VPN IP → proxy(低威胁,归 proxy)
    # 31-58 WordPress 攻击细分
    "31": "brute-force", "32": "brute-force", "33": "brute-force", "34": "brute-force",  # WP login/admin/XML-RPC/REST 爆破
    "35": "exploit", "36": "exploit", "37": "exploit", "38": "exploit",  # WP plugin/theme/core/0-day 漏洞
    "39": "spam", "40": "spam", "41": "spam", "42": "spam", "47": "spam", "49": "spam",  # WP comment/contact/reg/trackback/SEO spam
    "43": "malware", "44": "malware", "45": "malware", "46": "malware",  # WP file-upload/code-inj/DB-inj/backdoor
    "48": "scanner", "55": "scanner", "56": "scanner", "57": "scanner", "58": "scanner",  # WP content-scraping/user-enum/version/plugin scan/config exposure
    "50": "exploit",                                       # WP redirect hijacking
    "51": "ddos",                                          # WP resource exhaustion
    "52": "other", "53": "other", "54": "other",           # WP media/search/cron abuse(无净 IntelMQ 槽)
}

# reportedip code → 官方分类名(per reportedip.com v2/categories API, 2026-08-11)。
# 每码一名;harvest 按组去重。未来新增码(59+)或缺失 → harvest 回退原始码字符串。
REPORTEDIP_CODE_THEMATIC = {
    "1": "DNS Compromise", "2": "DNS Poisoning", "3": "Fraud Orders",
    "4": "DDoS Attack", "5": "FTP Brute-Force", "6": "Ping of Death",
    "7": "Phishing", "8": "Fraud VoIP", "9": "Open Proxy",
    "10": "Web Spam", "11": "Email Spam", "12": "Blog Spam",
    "13": "VPN IP", "14": "Port Scan", "15": "Hacking",
    "16": "SQL Injection", "17": "Spoofing", "18": "Brute-Force",
    "19": "Bad Web Bot", "20": "Exploited Host", "21": "Web App Attack",
    "22": "SSH", "23": "IoT Targeted", "24": "Cryptocurrency Mining",
    "25": "Ransomware C&C", "26": "Banking Trojan", "27": "Mobile Malware",
    "28": "Supply Chain Attack", "29": "Zero-Day Exploit", "30": "Nation State",
    "31": "WP Login Brute Force", "32": "WP Admin Brute Force",
    "33": "WP XML-RPC Brute Force", "34": "WP REST API Abuse",
    "35": "WP Plugin Exploit", "36": "WP Theme Exploit",
    "37": "WP Core Exploit", "38": "WP Zero-Day Exploit",
    "39": "WP Comment Spam", "40": "WP Contact Form Spam",
    "41": "WP Registration Spam", "42": "WP Trackback Spam",
    "43": "WP File Upload Malware", "44": "WP Code Injection",
    "45": "WP Database Injection", "46": "WP Backdoor Installation",
    "47": "WP SEO Spam", "48": "WP Content Scraping", "49": "WP Fake SEO Bot",
    "50": "WP Redirect Hijacking", "51": "WP Resource Exhaustion",
    "52": "WP Media Library Abuse", "53": "WP Search Abuse", "54": "WP Cron Abuse",
    "55": "WP User Enumeration", "56": "WP Version Scanning",
    "57": "WP Plugin Scanning", "58": "WP Config Exposure",
}


# ShadowWhisperer/IPs Threats.csv `category` → IntelMQ(波1,2026-10-18)。
# 六值实测谱系:botnet node/recon/intrusion/abuse/exploit/dropper host。
# 四值有净词表槽即映射;abuse/intrusion 语义过宽(泛指控、无行为类型)
# 显式 other(REPORTEDIP "28" 先例:已审视不强行映射,原值仍由
# native_categories 保存;显式映射同时免绊线重警)。
SW_THREATS_MAP = {
    "botnet node": "infected-system",   # botnet drone(词表已无方言 botnet,
                                        # P1 2026-09-05 迁官方型 infected-system)
    "recon": "scanner",
    "exploit": "exploit",
    "dropper host": "malware-distribution",   # 投递宿主 = 恶意软件分发
    "abuse": "other",
    "intrusion": "other",
}


# offseq/mirage-feed `tags` 值 → IntelMQ(#359,2026-11-18)。谱系 = 当日实抓
# 全量 attackers-7d.csv(2107 行)实测 18 值闭集;映射依据 = tag 名语义 +
# 同行 ATT&CK 实测相关(rdp 291/291=T1021.001+T1110、smb 88/88=T1187+
# T1021.002、db-ransom 129/129=T1485+T1486、sip-fraud 43/43=T1657)。
# tags 空行(19 行)不进本表:harvest 兜底 blacklist(词表注释「no
# subcategory available」,siberkapan 同款无差别传感器指控)。
MIRAGE_MAP = {
    # 爆破族(凭证/协议暴力破解,T1110)
    "ssh-bruteforce": "brute-force",
    "vnc-bruteforce": "brute-force",
    "db-bruteforce": "brute-force",
    "mail-bruteforce": "brute-force",
    "vpn-bruteforce": "brute-force",
    "sip-bruteforce": "brute-force",
    "telnet-bruteforce": "brute-force",
    "rdp": "brute-force",            # RDP 远程服务攻击(291/291 T1021.001
                                      # +T1110;167 行仅有此 tag)
    "smb": "brute-force",             # SMB 凭证攻击(88/88 T1187 forced
                                      # authentication + T1021.002)
    "web-exploit": "exploit",         # T1190 Exploit Public-Facing Application
    "web-scan": "scanner",            # T1595.002 漏洞扫描
    "mirai-like": "infected-system",  # 攻击宿主跑 mirai 族恶意软件 = 已感染
                                      # drone(URLHAUS_MAP "mirai" 先例)
    # 匿名化/网络上下文标签:握手验证的出口节点,映射其描述的分类
    # (reportedip "13" VPN IP→proxy 同律);上游自己的 STIX 也按
    # anonymization 而非 malicious-activity 渲染这两标签。
    "tor-exit": "tor",
    "vpn-exit": "proxy",
    # 显式 other(已审视不强行映射,原值由 native_categories 保存;
    # SW_THREATS_MAP "abuse" 先例):
    "cgnat": "other",                 # 运营商级 NAT 上下文(无净槽)
    "shell-commands": "other",        # 攻击者交互 shell 命令(T1059;爆破后
                                      # 登录执行,非漏洞利用,不并入 exploit)
    "db-ransom": "other",             # 数据库勒索冲击(129/129 T1485+T1486;
                                      # 无 ransom 词表槽,不硬塞 malware/ddos)
    "sip-fraud": "other",             # SIP 话费盗打(43/43 T1657 金融窃取;
                                      # 无 fraud 槽)
}


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

# blocklist.net.ua REASON 关键词 → IntelMQ(2026-11-22 三源批)。REASON 是
# 自由文本(俄/英双语全句,内嵌被攻击站点名,同一语义多种措辞),exact-key
# normalize() 不可用——blocklist_netua.harvest 按本表键做**子串匹配**,
# 插入序即优先序(ddos 族 → scanner → brute → spam),全 miss → 源内兜底
# blacklist(每行都是活性封禁指控,urlhaus 基类分类先例)。
# 谱系 = 2026-11-22 实抓全量 83,674 行闭集统计(8 语义族):паразит
# 32,939(上游自译「Паразитные HTTP запросы」= "HTTP flood requests",
# паразитный трафик/запросы 同族)/ddos 24,071/скан 23,851/brute 2,514
# (брутфорс+подбор)/нагрузка 114(含 укр. навантаження)/malicious 111
# (VNC 无差别指控,无净槽→兜底)/спам 39/截断尾 1。
NETUA_MAP = {
    # ddos 系(应用层洪水:HTTP flood/паразит/过载冲击)
    "ddos": "ddos",
    "паразит": "ddos",
    "нагрузка": "ddos",
    "навантаження": "ddos",
    # scanner 系(несанкционированное сканирование/Сканер сайтов)
    "сканиров": "scanner",
    "сканер": "scanner",
    "scanning": "scanner",
    # brute-force 系(брутфорс атака/подбор паролей/brute force)
    "брутфорс": "brute-force",
    "подбор": "brute-force",
    "brute force": "brute-force",
    # spam 系(рассылка email спама/send spam)
    "рассылка": "spam",
    "спам": "spam",
    "spam": "spam",
}


_unmapped_warned: set[tuple[int, str]] = set()


def normalize(raw_type, mapping: dict) -> str:
    """Map a source-native category to a CONTROLLED IntelMQ classification.type
    (the cross-source corroboration axis).

    A clearly-mapped value (present in `mapping` AND in the vocabulary) is used
    as-is. Anything else -> "other" (a controlled bucket that still participates
    in corroboration). Raw native values are NOT passed through here — sources
    that want to preserve an unmappable native value stash it in `extra` (see
    ip2proxy._proxy_evidence). This keeps the vocabulary from growing on every
    edge case while keeping the corroboration axis intact.

    绊线(2026-09-05):未命中映射的原生值按 (map,key) 进程级去重告警一次
    ——上游新增/改名分类码(reportedip 59+、dataplane 新信号)当天可见,
    而非无声落入 other。显式映射到 other 的键(REPORTEDIP "28")不告警。
    """
    key = (raw_type or "").strip().lower()
    mapped = mapping.get(key)
    if mapped and mapped in CLASSIFICATION_TYPES:
        return mapped
    if key and mapped is None and (trip := (id(mapping), key)) not in _unmapped_warned:
        _unmapped_warned.add(trip)
        logger.warning("unmapped native value %r -> 'other' "
                       "(upstream may have added/renamed a category)", key)
    return "other"


# ── 未映射键聚合计数车道(#241 tweetfeed 首创,#254 下沉共享)──────────
# 起因:urlhaus 走共享 normalize() 的逐键 WARN 绊线,生产容器重建窗口
# 实测 296 条(2026-10-31 #241 副产物);tweetfeed 同型问题已内联修 (#241,
# PR #255),本节把「计数代替告警 + 末尾一条摘要」下沉为共享件,两源
# 同调,避免第三份同型拷贝。计数集与旧绊线触发集严格一致(键非空且
# mapping 无此键);mapping 命中但值不在词表的键两车道都不告警不计数。

def normalize_counted(raw_type, mapping: dict, unknown: Counter,
                      *, logger=None, label: str = "", hits: str = "") -> str:
    """normalize() 的聚合计数车道:映射判定同语义,未命中键计入 unknown。

    返回值与 normalize() 逐键一致(位等价由 tweetfeed/urlhaus 的镜像测试
    钉住);唯一差异 = 未命中键不走逐键 WARN 绊线,改计入调用方传入的
    unknown Counter——调用方在解析完整遍结束后发一条聚合摘要
    (unmapped_summary),生成器被中途弃置则摘要不发(#241 契约)。
    logger 传入时,每 distinct 键首现发一条 DEBUG 留痕(哲学 1,信息
    不灭失;label/hits 用于消息文案,如 "tweetfeed: first unmapped
    hashtag '#x' this pass")。
    """
    key = (raw_type or "").strip().lower()
    mapped = mapping.get(key)
    if mapped and mapped in CLASSIFICATION_TYPES:
        return mapped
    if key and mapped is None:
        if logger is not None and unknown[key] == 0:
            logger.debug("%s: first unmapped %s %r this pass "
                         "(counting; aggregate summary at end of parse)",
                         label, hits, key)
        unknown[key] += 1
    return "other"


def unmapped_summary(unknown: Counter, *, logger, label: str, hits: str,
                     item: str, top_n: int = 10) -> None:
    """聚合计数摘要(一条 WARN):总命中数 + distinct + Top-N 及计数。

    #241 票面口径:Top-N 默认 10;unknown 为空零噪音不发。消息形如
    "label: N unmapped-{hits} hit(s), D distinct {item}(s) -> 'other'
    (top K: k1=c1, ...) — upstream may have added/renamed {item}s; ..."
    (hits = 被计名词,如 hashtag/tag;item = distinct 键名词,复数取
    item+'s——tweetfeed 侧两词不同名系沿用 #241 已合文案,测试钉住)。
    """
    if not unknown:
        return
    top = unknown.most_common(top_n)
    logger.warning(
        "%s: %d unmapped-%s hit(s), %d distinct %s(s) -> 'other' "
        "(top %d: %s) — upstream may have added/renamed %ss; "
        "full first-seen trail at DEBUG",
        label, sum(unknown.values()), hits, len(unknown), item, len(top),
        ", ".join(f"{k}={v}" for k, v in top), item)

