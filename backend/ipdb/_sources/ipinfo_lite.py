import gzip
import logging
import os
import shutil
import time
from pathlib import Path

import lmdb

# 源底座(#248):本类原为唯一无基类源,手抄全套生命周期;现挂
# SourceBase(load/_load_v6_side/health 随底座),自有 download/parse/rebuild
# 与 query 整形(_shape)保留。
from ._base import SourceBase
from ._download import download_file, CancelToken
# query()/_query6() 覆写内联 import 提升:缓存 import 实测 273ns/调用
# (PR-2 #111 T3 侦察遗留姊妹件;_lmdb 无反向 import,模块级安全)
from ._lmdb import (
    ip_to_int, ip_to_int6, lookup, read_ptr, open_env_read,
    read_disjoint_flag)

logger = logging.getLogger(__name__)


class IPinfoLiteSource(SourceBase):
    name = "ipinfo_lite"
    category = "geo_asn"
    # 底座 __init__ 由此派生 _path/_lmdb_base/v6 族路径(与原手抄同值,
    # #248 收编;url 无类属性 — 取数走 _url property 读 IPINFO_TOKEN)
    filename = "ipinfo_lite.csv"
    fields = ("country_code", "asn", "as_name", "ip_range")
    stale_days = 7
    reliability = 0.95
    # SM-F1:旧声明 (is_hosting, is_mobile) 为幻影——本源只产
    # country/asn/as_name/ip_range/as_domain,is_mobile 更不在 ASSET_SLOTS;
    # is_hosting 真生产者是 ip2proxy(DCH)/cloud_ranges(未声明,有意不扩面)。
    authoritative_for = ()
    # eval 元数据(S21/S33):默认 B/False 随源底座继承(原手抄同款值)。

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self._gz_path = data_dir / "ipinfo_lite.csv.gz"

    @property
    def _url(self) -> str:
        # token 使用点读取(sources-redesign T1 2026-10-17):admin API 热改
        # env 即时生效;启动时已设的行为逐字节等价。
        token = os.environ.get("IPINFO_TOKEN", "").strip()
        return (
            f"https://ipinfo.io/data/ipinfo_lite.csv.gz?token={token}"
            if token
            else ""
        )

    @property
    def download_host(self) -> str | None:
        # Stable vendor host even before IPINFO_TOKEN is configured — used for
        # UX labeling, not as a readiness signal (_url="" still means "no fetch").
        return "ipinfo.io"

    def download(self, token: CancelToken | None = None) -> None:
        if not self._url:
            logger.warning("IPINFO_TOKEN not set, skipping IPinfo Lite download")
            return
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading IPinfo Lite...")
        try:
            download_file(self._url, self._gz_path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            # F-5: 解压流式落 scratch 再 replace(atomic_write_bytes 同款
            # 语义;解压后 ~2M 行不整体进内存)。旧直写在 copyfileobj 半途
            # kill/ENOSPC 会留下半份 CSV、mtime 新鲜 → 重启后当新证据提交。
            # 失败时 scratch 由 finally 清理,旧 _path 字节级不动。
            scratch = self._path.with_name(self._path.name + ".dl")
            try:
                with gzip.open(self._gz_path, "rb") as f_in, \
                        open(scratch, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                with open(scratch, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                if line_count == 0:
                    raise RuntimeError("Downloaded file is empty")
                os.replace(scratch, self._path)
            finally:
                scratch.unlink(missing_ok=True)
            self._gz_path.unlink(missing_ok=True)
            logger.info(f"Downloaded IPinfo Lite ({line_count} lines)")
        finally:
            if self._gz_path.exists():
                self._gz_path.unlink(missing_ok=True)

    def rebuild(self, progress=None) -> int:
        import ipaddress as _ipa
        import csv as _csv
        from ._lmdb import rebuild_dual_family, Auto
        if not self._path.exists():
            return 0

        def _records():
            with open(self._path, "r", encoding="utf-8") as f:
                reader = _csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) < 8:
                        continue
                    network, country_code, asn, as_name, as_domain = (
                        row[0], row[2], row[5], row[6], row[7])
                    country_name = row[1].strip() if len(row) > 1 else ""
                    continent_code = row[4].strip() if len(row) > 4 else ""
                    try:
                        _ipa.ip_network(network, strict=False)   # v4+v6 网络
                    except (ValueError, _ipa.AddressValueError,
                            _ipa.NetmaskValueError):
                        continue
                    asn_val: int | str = "N/A"
                    has_asn = False
                    if asn.startswith("AS"):
                        try:
                            asn_val = int(asn[2:]); has_asn = True
                        except ValueError:
                            pass
                    elif asn:
                        try:
                            asn_val = int(asn); has_asn = True
                        except ValueError:
                            pass
                    val = {
                        "country_code": country_code,
                        "asn": asn_val,
                        "as_name": as_name or as_domain or "N/A",
                        "has_asn": has_asn,
                        "_net": network,
                    }
                    if continent_code:
                        val["continent_code"] = continent_code
                    if country_name:
                        val["country_name"] = country_name
                    if as_domain:
                        val["as_domain"] = as_domain
                    yield network, val

        # 流式双族(3.4M 行 OOM 纪律):_records 为生成器函数,每次调用
        # 返回新迭代器,partition 不物化。覆盖数经 Auto 循环内统计。
        n4, n6 = rebuild_dual_family(
            _records, self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=Auto, covered6=Auto,
            covered_setter4=lambda v: setattr(self, "_covered_ips", v),
            covered_setter6=lambda v: setattr(self, "_covered_v6_nets", v),
            progress=progress,
            raw=self._path)   # 族级增量:已收敛族跳过,重试只做未收敛族
        self._count = n4
        self._count6 = n6
        self._loaded_at = time.time()
        return n4

    @staticmethod
    def _shape(node: dict) -> dict:
        """node → 对外 dict(v4/v6 两族共用):补 ip_range 槽、剔内部键。"""
        result: dict = {"country_code": node["country_code"], "ip_range": node["_net"]}
        if node["has_asn"]:
            result["asn"] = node["asn"]
            result["as_name"] = node["as_name"]
        for k in ("continent_code", "country_name", "as_domain"):
            if k in node:
                result[k] = node[k]
        return result

    def query(self, ip: str) -> dict:
        if ":" in ip:                      # v6 查询走并行族 reader(spec §3.2)
            return self._query6(ip)
        if self._reader is None:
            return {}
        ip_int = ip_to_int(ip)
        try:
            node = lookup(self._reader, ip_int, disjoint=self._disjoint)
        except (lmdb.Error, OSError):
            # 撞上刚 close 的旧 env:读 ptr 重开重试一次(与 MMDB 时代同模式)
            epoch = read_ptr(self._lmdb_base)
            self._reader = (open_env_read(
                self._lmdb_base.parent / f"{self._lmdb_base.name}.{epoch}")
                if epoch is not None else None)
            if self._reader is None:
                return {}
            self._disjoint = read_disjoint_flag(self._lmdb_base, epoch)
            node = lookup(self._reader, ip_int, disjoint=self._disjoint)
        if node is None:
            return {}
        return self._shape(node)

    def _query6(self, ip: str) -> dict:
        """v6 版 query():与 v4 同构(lookup+重试+整形),独立族状态。
        无 v6 env(源无 v6 数据/旧目录)安静返回 {}——与该源不存在同体验。
        (覆写底座 _query6:本源查询有 node→dict 整形,v6 侧同形,否则 v6
        结果丢 ip_range 槽。)"""
        if self._reader6 is None:
            return {}
        ip_int = ip_to_int6(ip)
        try:
            node = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                          ip_version=6)
        except (lmdb.Error, OSError):
            # 撞上刚 close 的旧 env:读 ptr 重开重试一次(与 v4 同模式)
            epoch = read_ptr(self._lmdb6_base)
            self._reader6 = (open_env_read(
                self._lmdb6_base.parent / f"{self._lmdb6_base.name}.{epoch}")
                if epoch is not None else None)
            if self._reader6 is None:
                return {}
            self._disjoint6 = read_disjoint_flag(self._lmdb6_base, epoch)
            node = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                          ip_version=6)
        if node is None:
            return {}
        return self._shape(node)
