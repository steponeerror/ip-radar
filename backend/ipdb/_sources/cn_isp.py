import logging
import time
import urllib.request
from pathlib import Path

from .._source_base import Source
from ._download import CancelToken, CancelledError

logger = logging.getLogger(__name__)

_ISP_BASE_URL = "https://ispip.clang.cn"
_ISP_FILES = {
    "chinatelecom": ("CN", "中国电信"),
    "unicom_cnc": ("CN", "中国联通"),
    "cmcc": ("CN", "中国移动"),
    "chinabtn": ("CN", "中国广电"),
    "cernet": ("CN", "教育网"),
    "gwbn": ("CN", "长宽宽带"),
    "othernet": ("CN", "其他"),
    "hk": ("HK", "香港"),
    "mo": ("MO", "澳门"),
    "tw": ("TW", "台湾"),
}


class ChineseISPSource(Source):
    name = "cn_isp"
    category = "geo_asn"
    fields = ("country_code", "carrier", "is_isp", "ip_range")
    stale_days = 7
    reliability = 0.85
    filename = "cn_isp"   # Source base sets _lmdb_base = data_dir/"cn_isp.lmdb"

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)   # _data_dir, _path, _lmdb_base, _reader, _count, _loaded_at
        self._isp_dir = data_dir / "isp"

    @property
    def download_host(self) -> str | None:
        # No single canonical URL — download() iterates _ISP_FILES under _ISP_BASE_URL.
        # Exposed for source-update UX; callers wanting a single host can derive it
        # from _ISP_BASE_URL. Returned as None because there's no ONE primary URL.
        return None

    def download(self, token: CancelToken | None = None) -> None:
        self._isp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading Chinese ISP data from {_ISP_BASE_URL}...")
        for isp_name in _ISP_FILES:
            if token is not None and token.is_cancelled():
                raise CancelledError(f"{self.name} download cancelled")
            url = f"{_ISP_BASE_URL}/{isp_name}.txt"
            dest = self._isp_dir / f"{isp_name}.txt"
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "ip-lookup-tool/1.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                if not data.strip():
                    logger.warning(f"Empty response for {isp_name}")
                    dest.unlink(missing_ok=True)   # don't leave stale to be mixed in
                    continue
                with open(dest, "wb") as f:
                    f.write(data)
                newline = b'\n'
                logger.info(f"Downloaded {isp_name}.txt ({data.count(newline)} lines)")
            except Exception as e:
                logger.error(f"Failed to download {isp_name}.txt: {e}")
                dest.unlink(missing_ok=True)       # don't leave stale to be mixed in
        if not any((self._isp_dir / f"{n}.txt").exists() for n in _ISP_FILES):
            raise RuntimeError("all CN ISP files failed to download")

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

    def rebuild(self, progress=None) -> int:
        import ipaddress as _ipa
        from ._lmdb import covered_ip_count, rebuild_dual_family

        best: dict[str, dict] = {}
        for isp_name, (country, label) in _ISP_FILES.items():
            path = self._isp_dir / f"{isp_name}.txt"
            if not path.exists():
                logger.warning(f"Missing ISP file: {path}")
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        _ipa.ip_network(line, strict=False)
                    except (ValueError, _ipa.AddressValueError,
                            _ipa.NetmaskValueError):
                        continue
                    existing = best.get(line)
                    if existing and existing["isp"] != "其他" and label == "其他":
                        continue
                    best[line] = {"country_code": country, "isp": label, "_net": line}
        cov4 = covered_ip_count(c for c in best.keys() if ":" not in c)
        cov6 = covered_ip_count(
            (c for c in best.keys() if ":" in c), ip_version=6)
        n4, n6 = rebuild_dual_family(
            best.items(), self._lmdb_base, self._lmdb6_base,
            reader_setter4=lambda e: setattr(self, "_reader", e),
            reader_setter6=lambda e: setattr(self, "_reader6", e),
            flag_setter4=lambda v: setattr(self, "_disjoint", v),
            flag_setter6=lambda v: setattr(self, "_disjoint6", v),
            covered4=cov4, covered6=cov6, progress=progress,
        )
        self._covered_ips = cov4
        self._count = n4
        self._count6 = n6
        self._covered_v6_nets = cov6
        self._loaded_at = time.time()
        return n4
    def query(self, ip: str) -> dict:
        if ":" in ip:
            # v6 走并行族 reader(Source._query6)。上游无 v6 文件(C 类),
            # v6 恒 miss 返回 {};若未来接入 v6,需镜像下方 dict 加工形状。
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
        return {
            "country_code": node["country_code"],
            "is_isp": node["country_code"] == "CN",   # D6: HK/MO/TW rows aren't ISPs
            "carrier": node["isp"],
            "ip_range": node["_net"],
        }

    def health(self):
        from .._types import SourceHealth

        mtimes = []
        if self._isp_dir.exists():
            for isp_name in _ISP_FILES:
                p = self._isp_dir / f"{isp_name}.txt"
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
