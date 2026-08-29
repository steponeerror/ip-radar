"""Base classes for IP data sources — eliminate ~70% boilerplate across sources."""
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .._types import SourceHealth

logger = logging.getLogger(__name__)


class IpListSource:
    """Base for IP/CIDR list sources (tor_exits, x4bnet_vpn, firehol, spamhaus, blocklist_de).

    Subclasses must define: name, url, filename, fields.
    Optionally override: parse_raw(), get_insert_data(), stale_days, reliability, authoritative_for.
    """

    name: str
    url: str
    filename: str
    fields: tuple[str, ...]
    category: str = "other"            # 元数据契约(spec 2026-08-28 §5.1)
    stale_days: int = 7
    reliability: float = 0.5
    authoritative_for: tuple = ()      # tuple,与 _source_base.Source 同契约

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._path = data_dir / self.filename
        self._lmdb_base = data_dir / f"{self.filename}.lmdb"
        # registry/scheduler 的 needs_convert 比较对象(名保留):ptr 文件
        # (mtime 随重建刷新,与旧 .mmdb 同语义)
        from ._lmdb import ptr_path as _ptr_path
        self._mmdb_path = _ptr_path(self._lmdb_base)
        self._reader = None      # LMDB env (readonly, lock=False)
        self._disjoint = False   # epoch-bound sidecar flag(load/retry 时重读)
        self._count: int = 0
        self._covered_ips: int = 0
        self._loaded_at: float = 0.0
        # v6 并行族(spec §3.2):base/ptr/reader/disjoint 全套独立 sidecar
        # (与 Source 基类六属性平行维护 — 仓库多套平行基类,遵循 house style)
        self._lmdb6_base = data_dir / f"{self.filename}.v6.lmdb"
        self._mmdb6_path = _ptr_path(self._lmdb6_base)
        self._reader6 = None
        self._disjoint6 = False
        self._count6: int = 0
        self._covered_v6_nets: int = 0

    # ── Overridable hooks ──

    def parse_raw(self, raw: bytes) -> list[str]:
        """Parse downloaded bytes → list of IP/CIDR strings.

        Default: strip lines, skip comments and empty lines.
        Override for custom formats (e.g. tor_exits regex extraction).
        """
        return [
            line.strip()
            for line in raw.decode(errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def get_insert_data(self) -> dict:
        """Evidence-shaped value stored per CIDR. Constructs via Evidence so the
        dict is the canonical contract form (routes losslessly at query time)."""
        from .._evidence import Evidence
        if getattr(self, "classification_type", None):
            return Evidence(
                classification_type=self.classification_type,
                verdict=getattr(self, "verdict", "malicious"),
                reliability=getattr(self, "reliability", 0.5),
            ).to_dict()
        return {self.fields[0]: True}   # legacy non-threat list shape

    # ── Standard lifecycle ──

    @property
    def download_host(self) -> str | None:
        """Hostname of the primary remote URL (None when url is unset/local)."""
        return urlparse(self.url).hostname or None if getattr(self, "url", "") else None

    def download(self, token=None) -> None:
        """Fetch the raw list atomically, then parse + rewrite as entries.

        Token-aware: pass a CancelToken to allow cooperative cancellation
        between chunk reads. Subclasses may override for bespoke fetch logic.
        """
        from ._download import download_file
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading {self.name}...")
        try:
            download_file(self.url, self._path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            raw = self._path.read_bytes()
            if not raw.strip():
                raise RuntimeError(f"Empty response from {self.url}")
            entries = self.parse_raw(raw)
            if not entries:
                raise RuntimeError(f"No entries parsed from {self.name} response")
            with open(self._path, "w", encoding="utf-8") as f:
                f.write("\n".join(entries) + "\n")
            logger.info(f"Downloaded {self.name} ({len(entries)} entries)")
        except Exception:
            self._path.unlink(missing_ok=True)
            raise

    def load(self) -> int:
        """纯 mmap:加载现有 LMDB env(若有),永不重建。读 sidecar。"""
        from ._lmdb import (
            read_ptr, open_env_read, cleanup_stale, count_path, cov_path,
            read_disjoint_flag)
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
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。"""
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        if not self._path.exists():
            return 0
        insert_data = self.get_insert_data()
        records = []
        covered = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for sep in (";", "#"):
                    if sep in line:
                        line = line.split(sep, 1)[0].strip()
                if not line:
                    continue
                try:
                    net = _ipa.ip_network(line, strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                records.append((str(net), [insert_data]))
                covered.append(str(net))
        cov4 = covered_ip_count(c for c in covered if ":" not in c)
        cov6 = covered_ip_count(
            (c for c in covered if ":" in c), ip_version=6)
        return commit_dual_family(
            self, records, cov4=cov4, cov6=cov6, progress=progress)
    def query(self, ip: str) -> Any:
        if ":" in ip:                      # v6 查询走并行族 reader(spec §3.2)
            return self._query6(ip)
        if self._reader is None:
            return {}
        import lmdb as _lmdb
        from ._lmdb import (
            ip_to_int, lookup, read_ptr, open_env_read, read_disjoint_flag)
        ip_int = ip_to_int(ip)
        try:
            result = lookup(self._reader, ip_int, disjoint=self._disjoint)
        except (_lmdb.Error, OSError):
            # 撞上刚 close 的旧 env:读 ptr 重开重试一次(与 MMDB 时代同模式)
            epoch = read_ptr(self._lmdb_base)
            self._reader = (open_env_read(
                self._lmdb_base.parent / f"{self._lmdb_base.name}.{epoch}")
                if epoch is not None else None)
            if self._reader is None:
                return {}
            self._disjoint = read_disjoint_flag(self._lmdb_base, epoch)
            result = lookup(self._reader, ip_int, disjoint=self._disjoint)
        return result if result is not None else {}

    def _query6(self, ip: str) -> Any:
        """v6 版 query():与 v4 同构(ptr 重开重试),独立族状态。
        无 v6 env(源无 v6 数据/旧目录)安静返回 {}——与该源不存在同体验。
        (与 Source._query6 平行维护。)"""
        if self._reader6 is None:
            return {}
        import lmdb as _lmdb
        from ._lmdb import (
            ip_to_int6, lookup, read_ptr, open_env_read, read_disjoint_flag)
        ip_int = ip_to_int6(ip)
        try:
            result = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
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
            result = lookup(self._reader6, ip_int, disjoint=self._disjoint6,
                            ip_version=6)
        return result if result is not None else {}

    def health(self) -> SourceHealth:
        file_mtime = None
        last_updated = None
        if self._path.exists():
            file_mtime = self._path.stat().st_mtime
            last_updated = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
        # Staleness tracks the DATA FILE's age (not in-memory load time, which
        # is 0 before load_db runs and would force a re-download every restart).
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


class CsvSource(IpListSource):
    """Base for CSV-format sources (ipsum, ip2proxy, threatfox).

    Subclasses must implement: parse_row(row: list[str]) -> dict | None.
    Optionally override: skip_lines, delimiter.
    """

    skip_lines: int = 0
    delimiter: str = ","

    def parse_raw(self, raw: bytes) -> list[str]:
        """CSV sources store raw bytes (not parsed here)."""
        return [raw.decode(errors="ignore")]

    def parse_row(self, row: list[str]) -> dict | None:
        """Parse one CSV row → {field: value} dict. Return None to skip."""
        raise NotImplementedError("CsvSource subclasses must implement parse_row()")

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。"""
        import csv as _csv
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family, commit_dual_family
        if not self._path.exists():
            return 0
        # cidr_str -> list[evidence dict], deduped by full-evidence equality
        acc: dict[str, list[dict]] = {}
        with open(self._path, "r", encoding="utf-8") as f:
            for _ in range(self.skip_lines):
                next(f, None)
            reader = _csv.reader(f, delimiter=self.delimiter)
            for row in reader:
                if not row:
                    continue
                parsed = self.parse_row(row)
                if parsed is None:
                    continue
                ip_str = parsed.pop("_ip", row[0].strip())
                cidr_str = parsed.pop("_cidr", None)
                try:
                    if cidr_str:
                        net = _ipa.ip_network(cidr_str, strict=False)
                    elif "/" in ip_str:
                        net = _ipa.ip_network(ip_str, strict=False)
                    else:
                        _ipa.ip_address(ip_str)
                        net = _ipa.ip_network(
                            f"{ip_str}/{'128' if ':' in ip_str else '32'}",
                            strict=False)
                except (ValueError, _ipa.AddressValueError,
                        _ipa.NetmaskValueError):
                    continue
                key = str(net)
                bucket = acc.setdefault(key, [])
                # Dedup on the FULL evidence (not just 4-tuple): two rows
                # with same classification/verdict/malware but different
                # native_categories/confidence/first_seen/comment are distinct
                # evidence and must both survive (field-loss fix #6).
                if any(parsed == o for o in bucket):
                    continue
                bucket.append(parsed)
        v4_keys = (c for c in acc if ":" not in c)
        v6_keys = (c for c in acc if ":" in c)
        cov4 = covered_ip_count(v4_keys)
        cov6 = covered_ip_count(v6_keys, ip_version=6)
        # count 语义保持证据数(而非 CIDR 数)——与单族时代一致
        cnt4 = sum(len(acc[c]) for c in acc if ":" not in c)
        cnt6 = sum(len(acc[c]) for c in acc if ":" in c)
        return commit_dual_family(
            self, acc.items(), cov4=cov4, cov6=cov6,
            count4=cnt4, count6=cnt6, progress=progress)
