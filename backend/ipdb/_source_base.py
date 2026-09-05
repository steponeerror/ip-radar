# backend/ipdb/_source_base.py
"""Unified Source base for complex/bespoke sources.

Hooks (override what you need):
  download()           — default simple GET to self.url → self._path.
                         Override for state machines (cursor/budget/bg thread),
                         gzip, multi-file, auth headers.
  harvest()            — parse/transform → yields (cidr_str, Evidence) pairs.
                         Returning pairs (not bare Evidence) supports range→CIDR
                         expansion (one input row → many CIDRs).
  normalize(raw)       — optional per-source classification/field mapping.

Shared: LMDB write from harvest (epoch/ptr swap), mmap query,
health (file-mtime staleness), HTTP get with retries + auth header +
atomic tmp→rename write.
"""
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from ._types import SourceHealth
from ._evidence import Evidence
from ._sources._download import warn_if_redirected

logger = logging.getLogger(__name__)


class Source:
    name: str
    fields: tuple[str, ...]
    url: str = ""
    filename: str = ""
    stale_days: int = 7
    reliability: float = 0.5
    # ── 元数据契约(spec 2026-08-28 §5.1):源文件是唯一真相 ──
    category: str = "other"            # geo_asn | threat | asset | other
    authoritative_for: tuple = ()      # 本源权威的字段名(反转成 AUTHORITATIVE_SOURCES)
    # When True, rebuild() streams one (cidr, [evidence]) per harvest yield
    # straight into rebuild_lmdb instead of accumulating a full acc dict. Safe
    # only for sources whose harvest yields each CIDR at most once (geo/asset
    # lists like ip2proxy/iptoasn); insert_network overwrites idempotently, so
    # a stray duplicate is harmless. Multi-evidence threat sources must leave
    # this False — they rely on acc to group several evidence per CIDR.
    single_evidence: bool = False

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._path = data_dir / self.filename
        self._lmdb_base = data_dir / f"{self.filename}.lmdb"
        # registry/scheduler 的 needs_convert 比较对象(名保留):ptr 文件
        # (mtime 随重建刷新,与旧 .mmdb 同语义)
        from ._sources._lmdb import ptr_path as _ptr_path
        self._mmdb_path = _ptr_path(self._lmdb_base)
        self._reader = None      # LMDB env (readonly, lock=False)
        self._disjoint = False   # epoch-bound sidecar flag(load/retry 时重读)
        self._count = 0
        self._covered_ips = 0
        self._loaded_at = 0.0
        # v6 并行族(spec §3.2):base/ptr/reader/disjoint 全套独立 sidecar
        self._lmdb6_base = data_dir / f"{self.filename}.v6.lmdb"
        self._mmdb6_path = _ptr_path(self._lmdb6_base)
        self._reader6 = None
        self._disjoint6 = False
        self._count6 = 0
        self._covered_v6_nets = 0

    # ── hooks ──
    def download(self, token=None) -> None:
        """Default: simple GET → self._path. Override for bespoke fetch.

        ``token`` is accepted (and ignored) so UpdateManager can call
        ``download(token=...)`` uniformly; subclasses with non-cancellable
        fetches need not override for signature compatibility alone."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            self.url, headers={"User-Agent": "ip-lookup-tool/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            warn_if_redirected(self.url, resp)
            data = resp.read()
        if not data.strip():
            raise RuntimeError(f"Empty response from {self.url}")
        self._path.write_bytes(data)

    def harvest(self) -> Iterator[tuple[str, Evidence]]:
        """Parse → yield (cidr_str, Evidence). Override in every concrete source."""
        raise NotImplementedError

    def normalize(self, raw: Evidence) -> Evidence:
        """Optional per-source classification/field mapping. Default: passthrough."""
        return raw

    # ── shared lifecycle ──
    def load(self) -> int:
        """纯 mmap:加载现有 LMDB env(若有),永不重建。读 sidecar。"""
        from ._sources._lmdb import (
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
        # cov 只读,缺失则 0,不触发 harvest(rebuild 负责)
        self._covered_ips = int(vp.read_text().strip()) if vp.exists() else 0
        self._load_v6_side()
        self._loaded_at = time.time()
        return self._count

    def _load_v6_side(self) -> None:
        """v6 族 sidecar 解析(additive):ptr 缺失 = 无 v6 数据,不是错误。
        早退/正常两条 v4 路径共用;旧数据目录(无 v6 sidecar)静默零态。"""
        from ._sources._lmdb import (
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
        """重建 LMDB(唯一入口,经 manager 队列调用)。新 epoch + ptr swap。

        旧 env 不显式 close(各平行副本同此约定):依赖 CPython 引用计数
        在在途读 txn 结束后自然释放 — 查询线程在 reader swap 瞬间正握着旧
        env 时,显式 close 是文档化的段错误路径;而 rebuild 失败时 finally
        里 close 掉的其实是现役 reader(自残)。旧 epoch 目录的磁盘清理由
        rebuild_lmdb 的 prune rmtree 负责(Linux 上 fd 未关亦可删)。"""
        from ._sources._lmdb import Auto, rebuild_dual_family
        from ._logodds import parse_first_seen
        if not self._path.exists():
            return 0
        # 绊线(2026-09-05 IntelMQ 审计):脏 first_seen 在打分期静默按无
        # 衰减计(decay_factor(None)=1.0=最大权重)。中央检查按 distinct 值
        # 去重,单/双遍 harvest(factory 被 rebuild_dual_family 调两次)不双计。
        bad_fs: set[str] = set()

        def _harvest_checked():
            for cidr, ev in self.harvest():
                fs = getattr(ev, "first_seen", None)
                if fs and parse_first_seen(fs) is None:
                    bad_fs.add(str(fs))
                yield cidr, ev

        if self.single_evidence:
            # factory 零参 callable,每次调用返回新迭代器(rebuild_dual_family
            # 调用两次做族分区;严禁传裸生成器对象)。harvest 重复解析是既有
            # 模式(CPU 换内存,OOM 纪律见旧注释)。
            def factory():
                for cidr, ev in _harvest_checked():
                    yield cidr, [self.normalize(ev).to_dict()]
        else:
            acc: dict[str, list[dict]] = {}
            for cidr, ev in _harvest_checked():
                ev = self.normalize(ev)
                d = ev.to_dict()
                bucket = acc.setdefault(cidr, [])
                if d not in bucket:
                    bucket.append(d)
            factory = lambda: iter(acc.items())   # 已物化;统一 callable 形态
        # 覆盖数不再预扫描(省两次全量 harvest):covered=Auto 在写库循环内
        # 统计实际入库记录,ptr 提交后经 setter 落内存。
        # 流式 factory 无 __len__:total 用上一轮计数估计(刷新场景极准);
        # 首次重建无历史 → 0,UI --% 不变。
        n4, n6 = rebuild_dual_family(
            factory, self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=Auto, covered6=Auto,
            covered_setter4=lambda v: setattr(self, "_covered_ips", v),
            covered_setter6=lambda v: setattr(self, "_covered_v6_nets", v),
            progress=progress,
            total_est=self._count + self._count6)
        self._count = n4
        self._count6 = n6
        self._loaded_at = time.time()
        if bad_fs:
            logger.warning(
                "%s: %d distinct unparseable first_seen value(s), e.g. %s — "
                "time-decay silently disabled for those rows",
                self.name, len(bad_fs), sorted(bad_fs)[:3])
        return n4
    def query(self, ip: str) -> Any:
        if ":" in ip:                      # v6 查询走并行族 reader(spec §3.2)
            return self._query6(ip)
        if self._reader is None:
            return {}
        import lmdb as _lmdb
        from ._sources._lmdb import (
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
        无 v6 env(源无 v6 数据/旧目录)安静返回 {}——与该源不存在同体验。"""
        if self._reader6 is None:
            return {}
        import lmdb as _lmdb
        from ._sources._lmdb import (
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
        # convention 4: staleness from FILE mtime, not _loaded_at
        file_mtime = self._path.stat().st_mtime if self._path.exists() else None
        last_updated = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
                        if file_mtime else None)
        is_stale = file_mtime is None or (
            time.time() - file_mtime > self.stale_days * 86400)
        return SourceHealth(
            name=self.name, loaded=self._reader is not None,
            record_count=self._count, last_updated=last_updated, is_stale=is_stale,
            covered_ips=self._covered_ips,
            covered_v6_nets=self._covered_v6_nets)

    # ── HTTP helper for subclasses ──
    @staticmethod
    def _http_get(url: str, *, headers: dict | None = None,
                  timeout: int = 120, retries: int = 3) -> bytes:
        h = {"User-Agent": "ip-lookup-tool/1.0"}
        if headers:
            h.update(headers)
        last = None
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    warn_if_redirected(url, resp)
                    return resp.read()
            except Exception as e:
                last = e
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError(f"unreachable: {last}")
