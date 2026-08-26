import gzip
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from ._download import download_file, CancelToken
from ._lmdb import ptr_path as ptr_path_for

logger = logging.getLogger(__name__)


class IPinfoLiteSource:
    name = "ipinfo_lite"
    fields = ("country_code", "asn", "as_name", "ip_range")
    stale_days = 7
    reliability = 0.95

    def __init__(self, data_dir: Path):
        self._token = os.environ.get("IPINFO_TOKEN", "").strip()
        self._path = data_dir / "ipinfo_lite.csv"
        self._gz_path = data_dir / "ipinfo_lite.csv.gz"
        self._data_dir = data_dir
        self._lmdb_base = data_dir / "ipinfo_lite.csv.lmdb"
        # registry 的 needs_convert 比较对象:ptr 文件(mtime 随重建刷新)
        self._mmdb_path = ptr_path_for(self._lmdb_base)
        # _reader 实为 lmdb readonly env(open_env_read 产物),非 maxminddb.Reader
        self._reader: Optional[object] = None
        self._disjoint = False   # epoch-bound sidecar flag(load/retry 时重读)
        self._count: int = 0
        self._covered_ips: int = 0
        self._loaded_at: float = 0.0
        # v6 并行族(spec §3.2):base/ptr/reader/disjoint 全套独立 sidecar
        # (本类不继承 Source/IpListSource,与 _base.py 平行维护)
        self._lmdb6_base = data_dir / "ipinfo_lite.csv.v6.lmdb"
        self._mmdb6_path = ptr_path_for(self._lmdb6_base)
        self._reader6: Optional[object] = None
        self._disjoint6 = False
        self._count6: int = 0
        self._covered_v6_nets: int = 0

    @property
    def _url(self) -> str:
        return (
            f"https://ipinfo.io/data/ipinfo_lite.csv.gz?token={self._token}"
            if self._token
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
            with gzip.open(self._gz_path, "rb") as f_in, open(self._path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            with open(self._path, "r", encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
            if line_count == 0:
                raise RuntimeError("Downloaded file is empty")
            self._gz_path.unlink(missing_ok=True)
            logger.info(f"Downloaded IPinfo Lite ({line_count} lines)")
        except Exception:
            self._path.unlink(missing_ok=True)
            raise
        finally:
            if self._gz_path.exists():
                self._gz_path.unlink(missing_ok=True)

    def load(self) -> int:
        from ._lmdb import (read_ptr, open_env_read, cleanup_stale, count_path,
                            cov_path, read_disjoint_flag)
        cleanup_stale(self._lmdb_base)
        epoch = read_ptr(self._lmdb_base)
        if epoch is None:
            self._reader = None
            self._disjoint = False
            self._load_v6_side()                  # v6 状态照常解析(v4 缺 ≠ v6 缺)
            return 0
        self._disjoint = read_disjoint_flag(self._lmdb_base, epoch)
        self._reader = open_env_read(
            self._lmdb_base.parent / f"{self._lmdb_base.name}.{epoch}")
        cp, vp = count_path(self._lmdb_base), cov_path(self._lmdb_base)
        self._count = int(cp.read_text().strip()) if cp.exists() else 0
        self._covered_ips = int(vp.read_text().strip()) if vp.exists() else 0
        self._load_v6_side()
        self._loaded_at = time.time()
        return self._count

    def _load_v6_side(self) -> None:
        """v6 族 sidecar 解析(additive):ptr 缺失 = 无 v6 数据,不是错误。
        早退/正常两条 v4 路径共用;旧数据目录(无 v6 sidecar)静默零态。
        (与 Source._load_v6_side 平行维护。)"""
        from ._lmdb import (
            read_ptr, open_env_read, cleanup_stale, count_path, cov_path,
            read_disjoint_flag)
        cleanup_stale(self._lmdb6_base)
        e6 = read_ptr(self._lmdb6_base)
        if e6 is None:
            self._reader6 = None
            self._disjoint6 = False
            self._count6 = 0
            self._covered_v6_nets = 0
        else:
            self._disjoint6 = read_disjoint_flag(self._lmdb6_base, e6)
            self._reader6 = open_env_read(
                self._lmdb6_base.parent / f"{self._lmdb6_base.name}.{e6}")
            cp6, vp6 = count_path(self._lmdb6_base), cov_path(self._lmdb6_base)
            self._count6 = int(cp6.read_text().strip()) if cp6.exists() else 0
            self._covered_v6_nets = (
                int(vp6.read_text().strip()) if vp6.exists() else 0)

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
            progress=progress)
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
        import lmdb as _lmdb
        from ._lmdb import (
            ip_to_int, lookup, read_ptr, open_env_read, read_disjoint_flag)
        ip_int = ip_to_int(ip)
        try:
            node = lookup(self._reader, ip_int, disjoint=self._disjoint)
        except (_lmdb.Error, OSError):
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
        (与 IpListSource._query6 平行维护;本类 query 有 node→dict 整形,
        v6 侧同形,否则 v6 结果丢 ip_range 槽。)"""
        if self._reader6 is None:
            return {}
        import lmdb as _lmdb
        from ._lmdb import (
            ip_to_int6, lookup, read_ptr, open_env_read, read_disjoint_flag)
        ip_int = ip_to_int6(ip)
        try:
            node = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                          ip_version=6)
        except (_lmdb.Error, OSError):
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

    def health(self):
        from .._types import SourceHealth

        file_mtime = None
        last_updated = None
        if self._path.exists():
            file_mtime = self._path.stat().st_mtime
            last_updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
        is_stale = file_mtime is None or (
            time.time() - file_mtime > self.stale_days * 86400)
        return SourceHealth(
            name=self.name,
            loaded=self._reader is not None,
            record_count=self._count,
            last_updated=last_updated,
            is_stale=is_stale,
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets,
        )
