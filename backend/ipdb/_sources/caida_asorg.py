"""CAIDA AS-to-Organization 映射(ASN 键,查询期 join;b/asorg-anycast 批,2026-10-10)。

数据:as-organizations 月度快照(aut/org 双记录型 pipe 文本,~11 万 aut 行)。
License:CAIDA AUA(公共,署名引用
https://www.caida.org/catalog/datasets/as-organizations/)。

生命周期合同差异(全仓唯一无 LMDB 的源):数据是 ASN→组织名,无 CIDR 可
入库,LMDB per-IP 查询面用不上 —— download() 落原始文件(防坏守卫),
load()/rebuild() 解析为内存 dict {asn: org_name},query(ip) 恒 None;
lookup() 在 asn 胜者解出后经 org_for_asn() 钩子注入 as_org 值,走 as_org
策略合并(NamingAuthority,单证人 conf=r 公理)。NEEDS 类10「ASN 的组织级
名称」;org 记录的 country 丢弃(组织注册地≠IP 坐落,无需求不造槽,grill Q5)。
"""
import gzip
import logging
import shutil
import time
from pathlib import Path

from .._evidence import Evidence  # noqa: F401 — fields 契约可见性
from .._source_base import Source
from .._types import SourceHealth
from ._download import download_file, CancelToken

logger = logging.getLogger(__name__)

_URL = "https://data.caida.org/datasets/as-organizations/latest.as-org2info.txt.gz"


class CaidaAsorgSource(Source):
    name = "caida_asorg"
    category = "geo_asn"          # 路由与分配族(类10 组织与商业)
    filename = "as-org2info.txt"
    url = _URL
    fields = ("as_org",)
    authoritative_for = ("as_org",)
    stale_days = 45               # 月更快照,双月余量
    reliability = 0.8

    # 202610 快照实测 ~11 万 aut 行;200-OK 空/坏内容不落地(fail-closed)
    _MIN_AUT_ROWS = 50_000

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self._orgs: dict[int, str] | None = None   # None = 未加载

    def download(self, token: CancelToken | None = None) -> None:
        gz = self._data_dir / (self.filename + ".gz")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        logger.info("Downloading caida_asorg...")
        try:
            download_file(_URL, gz, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            with gzip.open(gz, "rb") as f_in, open(tmp, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            n = self._count_aut_rows(tmp)
            if n < self._MIN_AUT_ROWS:
                raise RuntimeError(
                    f"caida_asorg: only {n} aut rows "
                    f"(<{self._MIN_AUT_ROWS}) — existing file kept")
            tmp.replace(self._path)
            logger.info(f"Downloaded caida_asorg ({n} aut rows)")
        finally:
            gz.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _count_aut_rows(p: Path) -> int:
        n = 0
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) == 6 and parts[0].isdigit():
                    n += 1
        return n

    def _parse(self) -> dict[int, str]:
        """aut 记录(asn|changed|aut_name|org_id|op_type|source)join
        org 记录(org_id|changed|org_name|country|source)→ {asn: org_name}。"""
        org_names: dict[str, str] = {}
        aut: list[tuple[int, str]] = []
        with open(self._path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("|")
                if len(parts) == 6 and parts[0].isdigit():
                    aut.append((int(parts[0]), parts[3]))
                elif len(parts) == 5:
                    org_names[parts[0]] = parts[2]
        orgs: dict[int, str] = {}
        for asn, org_id in aut:
            name = org_names.get(org_id)
            if name:
                orgs[asn] = name
        return orgs

    # ── 无 LMDB 生命周期:文件即持久层,解析即加载 ──

    def load(self) -> int:
        if not self._path.exists():
            self._orgs = None
            return 0
        self._orgs = self._parse()
        self._loaded_at = time.time()
        return len(self._orgs)

    def rebuild(self, progress=None) -> int:
        # 无 LMDB:重建 = 重新解析文件为内存 dict(UpdateManager 队列照常调用)
        return self.load()

    def query(self, ip: str):
        return None                # 无 per-IP 面;join 走 org_for_asn 钩子

    def org_for_asn(self, asn) -> str | None:
        if self._orgs is None:
            return None
        try:
            return self._orgs.get(int(asn))
        except (TypeError, ValueError):
            return None

    def health(self) -> SourceHealth:
        # convention 4 同理:鲜度看文件 mtime,不看加载时刻
        file_mtime = self._path.stat().st_mtime if self._path.exists() else None
        return SourceHealth(
            name=self.name,
            loaded=self._orgs is not None,
            record_count=len(self._orgs or {}),
            last_updated=(time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(file_mtime))
                          if file_mtime else None),
            is_stale=file_mtime is None or (
                time.time() - file_mtime > self.stale_days * 86400),
        )
