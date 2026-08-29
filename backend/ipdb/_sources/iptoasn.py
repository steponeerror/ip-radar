import gzip
import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

from .._evidence import Evidence
from .._source_base import Source
from ._download import download_file, CancelToken

logger = logging.getLogger(__name__)

_TSV_URL = "https://iptoasn.com/data/ip2asn-combined.tsv.gz"


class IPtoASNSource(Source):
    name = "iptoasn"
    category = "geo_asn"
    filename = "ip-to-asn.tsv"
    url = _TSV_URL
    fields = ("country_code", "asn", "as_name", "ip_range")
    stale_days = 7
    reliability = 0.90
    single_evidence = True   # one evidence per CIDR → stream load() (OOM guard)

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)

    @property
    def download_host(self) -> str | None:
        return urlparse(_TSV_URL).hostname

    def download(self, token: CancelToken | None = None) -> None:
        gz_path = self._data_dir / "ip-to-asn.tsv.gz"
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        logger.info("Downloading IPtoASN...")
        try:
            download_file(_TSV_URL, gz_path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            with gzip.open(gz_path, "rb") as f_in:
                with open(tmp, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # 空检在换位之前:空文件落地 _path 会被下次 rebuild 吃掉(清库族)
            with open(tmp, "r", encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
            if line_count == 0:
                raise RuntimeError("Downloaded file is empty")
            tmp.replace(self._path)
            logger.info(f"Downloaded IPtoASN ({line_count} lines)")
        finally:
            gz_path.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)

    def harvest(self):
        import ipaddress as _ipa
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                try:
                    start = _ipa.ip_address(parts[0])
                    end = _ipa.ip_address(parts[1])
                    asn = int(parts[2])
                except (_ipa.AddressValueError, ValueError):
                    continue
                if asn == 0:
                    continue
                if start.version != end.version:
                    continue
                for cidr in _ipa.summarize_address_range(start, end):
                    yield str(cidr), Evidence(
                        asn=asn,
                        country_code=parts[3] or None,
                        as_name=parts[4] or None,
                        ip_range=str(cidr),
                    )
