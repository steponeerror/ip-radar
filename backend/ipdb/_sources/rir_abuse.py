"""RIR 注册库 abuse contact(类 3 所有权与联系;2026-10-18 重扫批第 1 名,
docs/research/2026-10-18-rdns-abuse-contact-rescan.md)。

RIPE NCC / AFRINIC 注册库全量 dump(RPSL 文本 gz,夜更免费免登录):
    ripe    https://ftp.ripe.net/ripe/dbase/ripe.db.gz       352MB,22:19 UTC
    afrinic https://ftp.afrinic.net/pub/dbase/afrinic.db.gz  10.5MB,00:05 UTC
字段链(两遍流式解压):inetnum/inet6num(网段→CIDR 键:v4 范围形 +
v6 前缀形 RFC 4012)→ abuse-c →
role → abuse-mailbox(邮箱本体);country 弃(caida_asorg 判例:注册属性
≠ IP 属性)。
License:RIPE DB T&C(署名义务;再分发条款需过目,见重扫报告)。
非扩展边界:APNIC 无公开全量(仅 NIR dump)、ARIN 要协议、LACNIC 404——
两 dump 已覆盖约全球 v4 四成;同机构不同数据集于 rir_delegated(delegated
分配台账),不并入:后者 fields=() 零投票纪律与单证人语义不同,混库即
回声。纯信息位:verdict="" 弃权(R17A-1 同款,永不进观测/指控)。
占位 role 实测存在("Placeholder Role Object",重扫报告 quality 扣 1)
→ reliability 0.85 而非官方发布档。
org_name 扩展(rir-abuse-org,2026-10-18):同 dump 增收 inetnum org:
→ organisation.org-name(Evidence.org_name 槽)+ descr(extra 无损随
行,不设槽)。边界:organisation 对象仅存在于全量 dump——NRTM 镜像/
增量文件剥除之,勿换 feed;org: 悬空引用只丢 org_name 不丢行(宁少算),
键空间准入仍由 abuse-c 解析驱动(descr/org 不独立产键)。
登记属性增收(abuse-context 批,2026-10-18,词汇表 CONTEXT.md「登记
声明/登记新鲜度/下挂行」):notify/created/last-modified/mnt-by 自
inetnum、contact_name 自 role 对象名,均入 extra 乘客(投诉工作流用
料);融合层 abuse_contact 下挂行白名单透传 contact_name/notify/
created/last_modified,mnt_by 留 evidence extra(存储/证据层,不进下挂行)。
"""
import gzip
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterator

import ipaddress

from .._evidence import Evidence
from .._source_base import Source
from ._download import download_file
# dbip_city 的整数解析/格式化助手(差分实测过,tests/sources/test_dbip_fastpath
# 钉死):本源 range→CIDR 与之同构(对齐位运算快速路),复用不另抄一份
from .dbip_city import _v4_int, _v6_int, _fmt_v4, _fmt_v6

logger = logging.getLogger(__name__)

_BASE = {
    "ripe": "https://ftp.ripe.net/ripe/dbase/ripe.db.gz",
    "afrinic": "https://ftp.afrinic.net/pub/dbase/afrinic.db.gz",
}
# fail-closed 下限(重扫报告实测口径,余量 ≥2×;AFRINIC 最小实测全库)
_MIN_NET_OBJECTS = {"ripe": 100_000, "afrinic": 1_000}

# 本源消费的 RPSL 属性;过滤后对象 dict 有界(其余属性首值丢弃即足)。
# org_name 扩展(rir-abuse-org,2026-10-18):org/inetnum 侧引用,
# organisation/org-name 组织对象侧锚(全量 dump 专有,见模块 docstring)
# 登记属性增收(abuse-context 批,2026-10-18):notify/created/
# last-modified 单值首见非空;mnt-by 多值属性全收为 list(无损红线)
_KEY_ATTRS = frozenset({
    "inetnum", "inet6num", "netname", "abuse-c",
    "role", "nic-hdl", "abuse-mailbox",
    "org", "descr", "organisation", "org-name",
    "notify", "created", "last-modified", "mnt-by",
})


def _iter_objects(f) -> Iterator[dict[str, Any]]:
    """RPSL 流 → 逐对象 attr dict(对象以空行分隔;%/# 注释行与续行首字符
    空白/+/`)跳过——关心的属性都是单行值,宁少算;多值取首见非空,
    唯一例外 mnt-by 全值累积为 list(多值属性,无损红线)。"""
    obj: dict[str, Any] = {}
    # shortcut: 仅空行分对象,两对象只隔 % 注释行(无空行)会并卷(首值胜保网段但可吸收对侧 abuse-c),RIPE/AFRINIC 官方 dump 恒空行分隔;真源出现注释分隔再升结构
    for line in f:
        line = line.rstrip("\n")
        if not line.strip():
            if obj:
                yield obj
                obj = {}
            continue
        c = line[0]
        if c in "%#" or c in " \t+*" or ":" not in line:
            continue
        attr, _, val = line.partition(":")
        if attr in _KEY_ATTRS:
            val = val.strip()
            if not val:
                continue
            if attr == "mnt-by":
                obj.setdefault("mnt-by", []).append(val)
            elif attr not in obj:
                obj[attr] = val
    if obj:
        yield obj


def _range_to_cidrs(range_str: str) -> list[str]:
    """RPSL 网段值 → CIDR 列表。前缀形(RFC 4012/RPSLng,现行 inet6num
    标准形如 `inet6num: 2001:db8::/32`)直取 ip_network;范围形 "a - b"
    (inetnum 传统形)对齐位运算快速路 + stdlib summarize 兜底(dbip_city
    同款;非 2 幂长范围可能展开多网,全返回防覆盖缺口);解不出 →
    [](丢该对象,不造槽)。v6 地址不含 '-',split 安全。"""
    if "/" in range_str and "-" not in range_str:
        # 前缀形(RFC 4012):真实 inet6num dump 的现行标准形;走范围
        # split 会把 "2001:db8::/32" 当单地址解析失败静默丢——v6 全族
        # 零键(评审 F1,2026-10-18)
        try:
            return [str(ipaddress.ip_network(range_str, strict=False))]
        except ValueError:
            return []
    parts = [p.strip() for p in range_str.split("-")]
    if len(parts) == 1:        # 旧式单地址 inetnum(a==b → /32 或 /128)
        parts = [parts[0], parts[0]]
    if len(parts) != 2:
        return []
    start, end = parts
    v6 = ":" in start or ":" in end
    if v6:
        a, b, bits = _v6_int(start), _v6_int(end), 128
    else:
        a, b, bits = _v4_int(start), _v4_int(end), 32
    if a is None or b is None or a > b:
        return []
    span = b - a + 1
    if span & (span - 1) == 0 and a & (span - 1) == 0:
        # exact aligned CIDR — integer bit-math, no ipaddress objects
        plen = (bits + 1) - span.bit_length()
        return [_fmt_v6(a, plen) if v6 else _fmt_v4(a, plen)]
    cls = ipaddress.IPv6Address if v6 else ipaddress.IPv4Address
    return [str(n) for n in ipaddress.summarize_address_range(cls(a), cls(b))]


def _count_objects(p: Path) -> tuple[int, int]:
    """流式解压计数(不整文件进内存,352MB gz):(inetnum/inet6num 对象数,
    带 abuse-mailbox 的 role 数)。守卫与 harvest 同解析结构。"""
    nets = roles = 0
    with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for obj in _iter_objects(f):
            if "inetnum" in obj or "inet6num" in obj:
                nets += 1
            elif obj.get("nic-hdl") and obj.get("abuse-mailbox"):
                roles += 1
    return nets, roles


class RirAbuseSource(Source):
    name = "rir_abuse"
    category = "geo_asn"          # 路由与分配族(类 3 槽位挂 geo_asn 族,caida_asorg 同例)
    filename = "rir_abuse"        # 目录名;基类靠 filename 推 _lmdb_base(P1 热修教训,rir_delegated 同款声明)
    fields = ("abuse_contact", "org_name")
    authoritative_for = ("abuse_contact", "org_name")   # 双槽单证人(NamingAuthority conf=r 公理,as_org 同族);descr 只随 extra 不入槽
    url = None                    # 双 host(ripe/afrinic),目录形,rir_delegated 同款
    stale_days = 7                # 夜更,一周余量(重扫档案)
    reliability = 0.85            # 注册局一手,但占位 role 实测存在(重扫 quality 扣 1)
    single_evidence = True        # 数 M CIDR → stream load(OOM 守卫)

    @property
    def download_host(self) -> str | None:
        return None                                  # 双 host,无单一权威

    def download(self, token=None) -> None:
        """两家逐个:fetch → scratch → 流式解压守卫 → os.replace 原子落地
        (rir_delegated 同款)。部分失败:保留旧文件记 last_partial_failure;
        全败 raise。守卫 fail-closed:对象计数不足 → RuntimeError 保留旧文件
        (200-OK 坏载荷不清源)。"""
        self._path.mkdir(parents=True, exist_ok=True)
        self.last_partial_failure = []
        for reg, url in _BASE.items():
            dest = self._path / f"{reg}.db.gz"
            scratch = dest.with_name(dest.name + ".dl")
            try:
                download_file(url, scratch, token=token, timeout=300,
                              headers={"User-Agent": "ip-lookup-tool/1.0"})
                nets, roles = _count_objects(scratch)
                if nets < _MIN_NET_OBJECTS[reg] or roles < 1:
                    raise RuntimeError(
                        f"rir_abuse/{reg}: only {nets} net objects / "
                        f"{roles} abuse roles "
                        f"(<{_MIN_NET_OBJECTS[reg]}/1) — existing file kept")
                os.replace(scratch, dest)
                logger.info(f"rir_abuse/{reg}: ok "
                            f"({nets} net objects, {roles} abuse roles)")
            except Exception as e:
                scratch.unlink(missing_ok=True)
                self.last_partial_failure.append(reg)
                logger.warning(f"rir_abuse/{reg} download failed: {e}")
        if len(self.last_partial_failure) == len(_BASE):
            raise RuntimeError(
                f"all rir_abuse feeds failed: {self.last_partial_failure}")

    def health(self):
        """目录形覆写(rir_delegated 同式):逐 RIR mtime → FeedHealth。"""
        from .._types import FeedHealth, SourceHealth
        feeds, mtimes = [], []
        for reg in _BASE:
            p = self._path / f"{reg}.db.gz"
            if p.exists():
                m = p.stat().st_mtime
                mtimes.append(m)
                feeds.append(FeedHealth(
                    name=reg,
                    last_updated=time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(m)),
                    is_stale=time.time() - m > self.stale_days * 86400,
                ))
            else:
                feeds.append(FeedHealth(name=reg, last_updated=None,
                                        is_stale=True))
        file_mtime = max(mtimes) if mtimes else None
        return SourceHealth(
            name=self.name,
            loaded=self._reader is not None,
            record_count=self._count,
            last_updated=(time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(file_mtime))
                          if file_mtime else None),
            is_stale=file_mtime is None or any(f.is_stale for f in feeds),
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets,
            feeds=feeds,
        )

    def harvest(self):
        """目录内两文件 × 两遍流式 gzip → (cidr, Evidence)。
        第 1 遍收 {nic-hdl: (abuse-mailbox, role-name)}(nic-hdl+
        abuse-mailbox 双非空即收,role 对象名缺席为 None——真实 dump 存在
        无名 role;irt/person 不带 abuse-mailbox 自然不收,宁少算)与
        {organisation: org-name}(organisation 对象,org-name 非空才收);
        第 2 遍 inetnum/inet6num 且带 abuse-c → 解析邮箱(解不出丢对象不
        造槽)→ 网段值 → CIDR(范围形/前缀形两路)。org: 解析成功 →
        Evidence.org_name,悬空引用只丢 org_name 不丢行(宁少算);descr
        非空 → extra["descr"] 原样无损(不设槽);登记属性增收(abuse-
        context 批,2026-10-18):contact_name(role 名)/notify(首个非空)
        /created/last_modified(原样 ISO 串,展示截断归前端)/mnt_by
        (全值列表)均入 extra 乘客,不设槽不进融合数学;键空间准入不变
        ——仍由 abuse-c 解析驱动(宁少算/no-bloat)。v6 由写入侧按 ':'
        双族分派。"""
        if not self._path.exists():
            return
        for reg in _BASE:
            p = self._path / f"{reg}.db.gz"
            if not p.exists():
                logger.warning(f"rir_abuse: missing {reg} file — skipped")
                continue
            handles: dict[str, tuple[str, str | None]] = {}
            orgs: dict[str, str] = {}    # {organisation-id: org-name}(org: 引用解析表)
            with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
                for obj in _iter_objects(f):
                    hdl, mbox = obj.get("nic-hdl"), obj.get("abuse-mailbox")
                    if hdl and mbox:
                        # 名缺席 None:contact_name 透传层不造名(宁少算)
                        handles[hdl] = (mbox, obj.get("role"))
                    else:
                        org_id, oname = (obj.get("organisation"),
                                         obj.get("org-name"))
                        if org_id and oname:
                            orgs[org_id] = oname
            with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
                for obj in _iter_objects(f):
                    rng = obj.get("inetnum") or obj.get("inet6num")
                    hdl = obj.get("abuse-c")
                    if not rng or not hdl:
                        continue
                    mbox, cname = handles.get(hdl, (None, None))
                    if not mbox:
                        continue
                    extra = {"registry": reg, "abuse_c": hdl}
                    if cname:
                        extra["contact_name"] = cname
                    if obj.get("notify"):
                        extra["notify"] = obj["notify"]
                    if obj.get("created"):
                        # 登记声明原样 ISO 串入库,展示截断归前端(无损)
                        extra["created"] = obj["created"]
                    if obj.get("last-modified"):
                        extra["last_modified"] = obj["last-modified"]
                    if obj.get("mnt-by"):
                        # 多值属性全值列表(无损红线:不截断不取首)
                        extra["mnt_by"] = list(obj["mnt-by"])
                    if obj.get("netname"):
                        extra["netname"] = obj["netname"]
                    if obj.get("descr"):
                        # descr 无损随行(红线:超长原样不截断,展示层自理)
                        extra["descr"] = obj["descr"]
                    # 宁少算:org: 悬空引用只丢 org_name(None 槽被 to_dict
                    # 丢),行内 abuse_contact/descr 不受牵连
                    org_name = orgs.get(obj["org"]) if obj.get("org") else None
                    for cidr in _range_to_cidrs(rng):
                        yield cidr, Evidence(
                            verdict="",       # 弃权拼写(R17A-1):信息位不指控
                            abuse_contact=mbox,
                            org_name=org_name,
                            extra=dict(extra),
                        )
