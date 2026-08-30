"""Firehol blocklist source — IpListSource subclass with multi-list download.

子列表拆分(2026-08-30):level1/2 之外订阅 firehol 自有的三个语义净新增
列表,per-list 分类(verdict 与同轴直接源对齐,详见 _LIST_SPEC 注释):
- abusers_30d(7/7 上游为 spam 族追踪器)→ spam/informational(对齐 sfs,
  ffae4caf 的 off-threat-axis 裁决);
- proxies(iblocklist/socks/sslproxies 三个无直接源的代理上游)→
  proxy/suspicious + is_proxy(对齐 proxyscrape/ip2proxy);
- webserver(98% IP 为 sfs toxic 段)→ spam/informational(同 sfs 轴)。
重叠部分由谱系去重兜底(derived=True);同 CIDR 异分类共存(convention 3)。
"""
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from ._base import IpListSource
from ._download import download_file, CancelToken, CancelledError
from .._types import SourceHealth

_BASE_URL = "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master"

logger = logging.getLogger(__name__)

# 列表 → (classification, verdict, Evidence 附加槽)。
# 未列出的列表回退类属性 blacklist/malicious(兼容任意 selected_lists)。
_LIST_SPEC = {
    "firehol_level1":      ("blacklist", "malicious", {}),
    "firehol_level2":      ("blacklist", "malicious", {}),
    "firehol_abusers_30d": ("spam", "informational", {}),
    "firehol_proxies":     ("proxy", "suspicious", {"is_proxy": True}),
    "firehol_webserver":   ("spam", "informational", {}),
}

# 超大列表(2.8M 行)流式直读不落 acc:内存上界由非流式列表总量决定,
# proxies 增长只影响重建时长。撞 acc 就地合并(实测跨列表同 CIDR ≈8.3k)。
_STREAMED = frozenset({"firehol_proxies"})


class FireholBlocklistSource(IpListSource):
    name = "firehol"
    category = "threat"
    url = ""  # unused — custom download() handles multiple URLs
    filename = "firehol"  # directory name
    fields = ("is_malicious",)
    classification_type = "blacklist"   # 类级回退(未列入 _LIST_SPEC 的列表)
    verdict = "malicious"
    stale_days = 1
    reliability = 0.50
    derived = True                        # 聚合器:谱系去重用(spec 2026-08-29 §3.3)
    authoritative_for = ()

    def __init__(self, data_dir: Path, selected_lists: list[str] | None = None):
        self._lists = selected_lists or list(_LIST_SPEC)
        super().__init__(data_dir=data_dir)
        self._path = data_dir / "firehol"  # directory, not file
        self._files = [self._path / f"{name}.netset" for name in self._lists]

    @property
    def download_host(self) -> str | None:
        # url class attr is "" but downloads actually come from _BASE_URL.
        return urlparse(_BASE_URL).hostname

    def download(self, token: CancelToken | None = None) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        for list_name in self._lists:
            if token is not None and token.is_cancelled():
                raise CancelledError(f"{self.name} download cancelled")
            url = f"{_BASE_URL}/{list_name}.netset"
            dest = self._path / f"{list_name}.netset"
            logger.info(f"Downloading {list_name}...")
            try:
                download_file(url, dest, token=token,
                              headers={"User-Agent": "ip-lookup-tool/1.0"})
                if not dest.read_bytes().strip():
                    dest.unlink(missing_ok=True)   # don't leave stale to be mixed in
            except Exception as e:
                logger.error(f"Failed to download {list_name}: {e}")
                dest.unlink(missing_ok=True)       # don't leave stale to be mixed in
        if not any((self._path / f"{l}.netset").exists() for l in self._lists):
            raise RuntimeError(
                f"all firehol lists failed to download: {self._lists}")

    def load(self) -> int:
        """纯 mmap:打开已有 LMDB env,读 sidecar,不重建。"""
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

    def rebuild(self, progress=None) -> int:
        """重建 LMDB(唯一重建入口)。新 epoch + ptr swap reader。

        Per-list classification(2026-08-30):每列表按 _LIST_SPEC 各投分类;
        同 CIDR 同分类命中合并 tags(2026-08-15 语义推广),异分类各成一条
        证据(convention 3)。流式双族(ipinfo_lite 惯例):非流式列表先
        build acc,流式列表(proxies)行级直吐、撞 acc 就地合并——保证同
        CIDR 跨列表证据零丢失(先物化后流式的顺序是正确性要求)。
        同起止不同长度 CIDR 仍依赖审计脚本零冲突
        (scripts/audit_lmdb_invariants.py)。
        """
        import ipaddress as _ipa
        from ._lmdb import rebuild_dual_family, Auto
        from .._evidence import Evidence
        if not self._path.exists():
            return 0

        def _ev(list_name: str) -> dict:
            cls, verdict, extras = _LIST_SPEC.get(
                list_name, (self.classification_type, self.verdict, {}))
            return Evidence(
                classification_type=cls,
                verdict=verdict,
                reliability=self.reliability,
                tags=[list_name],
                **extras,
            ).to_dict()

        def _merge(bucket: list, d: dict) -> None:
            """同 CIDR:sans-tags 等价则合并 tags,否则共存为独立证据。"""
            for other in bucket:
                if {k: v for k, v in other.items() if k != "tags"} == \
                   {k: v for k, v in d.items() if k != "tags"}:
                    for t in d["tags"]:
                        if t not in other["tags"]:
                            other["tags"].append(t)
                    return
            bucket.append(d)

        def _factory():
            acc: dict[str, list] = {}
            ordered = ([n for n in self._lists if n not in _STREAMED]
                       + [n for n in self._lists if n in _STREAMED])
            for list_name in ordered:
                p = self._path / f"{list_name}.netset"
                if not p.exists():
                    continue
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
                        d = _ev(list_name)
                        if list_name in _STREAMED and net not in acc:
                            yield net, [d]   # 流式直吐,不落 acc
                        else:
                            _merge(acc.setdefault(net, []), d)
            # ponytail: 两个已知天花板(均为保守方向,审计脚本可观测):
            # ① 流式文件内部重复行未设防(实测 5 文件 internal dup=0);
            # ② 同起点不同长度 CIDR 对(实测 1,948/3M≈0.065%,LMDB 键=start
            #    只存其一):跨列表对中 acc 后 yield 恒胜 → 粒度粗化、无假
            #    阳性。要无损消除需 start 集合(~200MB)或排序合并,不值;
            #    升级路径 = _lmdb 键改 (start,prefixlen) 双分量。
            yield from acc.items()

        n4, n6 = rebuild_dual_family(
            _factory, self._lmdb_base, self._lmdb6_base,
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
        return n4

    def query(self, ip: str):
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
        return node

    def health(self) -> SourceHealth:
        import time
        mtimes = []
        if self._path.exists():
            for list_name in self._lists:
                p = self._path / f"{list_name}.netset"
                if p.exists():
                    mtimes.append(p.stat().st_mtime)
        file_mtime = max(mtimes) if mtimes else None
        last_updated = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_mtime))
                        if file_mtime else None)
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
