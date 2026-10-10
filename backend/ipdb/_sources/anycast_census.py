"""UT-Dallas Anycast Census(LACeS 主动测量;b/asorg-anycast 批,2026-10-10)。

manycast.net REST CSV 导出(日更,~4.1 万 /24 任播前缀);License MPL-2.0。
列:prefix,AB_*,GCD_*,partial,locations,backing_prefix,ASN。
partial=True(混播前缀,仅部分 IP 任播)整行排除——宁少算,grill Q4 裁定;
is_anycast 走 asset 槽(弃权拼写 R17A-1:信息位不指控)。
任播语义:同一 IP 从多地同时应答;第二证人路径 = bgp.tools anycast 复活后
双源投票(license 真空弃置,见 NEEDS anycast 行)。
"""
import csv
import gzip
import logging
import shutil
from pathlib import Path

from .._evidence import Evidence
from .._source_base import Source
from ._download import download_file, CancelToken

logger = logging.getLogger(__name__)

_URL = "https://manycast.net/api/v1/export/IPv4-latest.csv.gz"


class AnycastCensusSource(Source):
    name = "anycast_census"
    category = "asset"             # 基础设施角色(类4 anycast)
    filename = "anycast_census.csv"
    url = _URL
    fields = ("is_anycast",)
    authoritative_for = ("is_anycast",)
    stale_days = 3                 # 日更
    reliability = 0.9              # 多锚点主动测量
    single_evidence = True         # ~4 万 CIDR,流式重建(OOM 守卫)

    # 2026-10-10 实测 41,382 行;200-OK 空/形状漂移不落地(fail-closed)
    _MIN_ROWS = 1_000

    def download(self, token: CancelToken | None = None) -> None:
        gz = self._data_dir / (self.filename + ".gz")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        logger.info("Downloading anycast_census...")
        try:
            download_file(_URL, gz, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            with gzip.open(gz, "rb") as f_in, open(tmp, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            with open(tmp, "r", encoding="utf-8", errors="replace") as f:
                header = f.readline().strip().split(",")
                if "prefix" not in header or "partial" not in header:
                    raise RuntimeError(
                        "anycast_census: header shape drift — existing file kept")
                rows = sum(1 for _ in f)
            if rows < self._MIN_ROWS:
                raise RuntimeError(
                    f"anycast_census: only {rows} rows "
                    f"(<{self._MIN_ROWS}) — existing file kept")
            tmp.replace(self._path)
            logger.info(f"Downloaded anycast_census ({rows} rows)")
        finally:
            gz.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)

    def harvest(self):
        with open(self._path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)                     # header
            for row in reader:
                if len(row) < 7:
                    continue
                if row[6] != "False":              # 宁少算:混播前缀排除
                    continue
                yield row[0], Evidence(
                    is_anycast=True,
                    verdict="",                    # 弃权拼写(R17A-1)
                    native_types={"is_anycast": "LACeS anycast census"},
                )
