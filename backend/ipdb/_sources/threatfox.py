"""ThreatFox IOC feed — Source subclass (ZIP download + per-row classification).

abuse.ch v2 认证导出端点(票 #159,2026-10-23)经
`https://threatfox-api.abuse.ch/v2/files/exports/<KEY>/full.csv.zip` 服务
内含 `full.csv` 的 ZIP;旧匿名出口 `/export/csv/full/` 已 410(2026-10-22)。
Auth-Key 在 URL 路径段,由 env `ABUSECH_AUTH_KEY` 注入,keyed URL 只在
download() 内拼、不入 self.url——注册表 roster/日志/测试断言面只见
占位。新端点列序/9 行注释头与旧解析器逐字节同构(票 #159 实测),
解析面零改动。The real column order (per abuse.ch header) is:

    first_seen_utc, ioc_id, ioc_value, ioc_type, threat_type, fk_malware,
    malware_alias, malware_printable, last_seen_utc, confidence_level, ...

Migrated from CsvSource onto the unified Source base (Task 3.2): download()
streams the ZIP atomically to a sibling .zip via the shared `download_file`
helper (token-aware, mid-stream cancel), then extracts the inner CSV onto
`self._path`. `harvest()` yields `(ip, Evidence)` per row with per-row
classification via `normalize(raw_type, THREATFOX_MAP)`. `parse_row()` is
retained as a legacy helper because existing column-mapping tests depend
on it.

New field routing (source-info-exhaustion P0): `last_seen_utc` (col 8) →
canonical `last_seen` when non-empty; tags (col 12, comma-separated) →
canonical `tags` filtered of empties/"None"; the port suffix of `ioc_value`
and `malware_printable` (col 7) ride in `extra` as `port` /
`malware_printable`. `threat_type` stays routed to `native_categories`
unchanged.
"""
import csv
import io
import logging
import os
import zipfile
from pathlib import Path

from .._source_base import Source
from .._evidence import Evidence
from .._classification import normalize, THREATFOX_MAP
from ._download import download_file, CancelToken, atomic_write_bytes, redact_url

logger = logging.getLogger(__name__)


def _clean(cell: str) -> str:
    """Strip whitespace and surrounding quotes from an abuse.ch CSV field."""
    return cell.strip().strip('"').strip()


class ThreatFoxSource(Source):
    name = "threatfox"
    category = "threat"
    # 无 key 占位形状(票 #159):v2 真实端点把 Auth-Key 作路径段插在文件名前
    # (…/v2/files/exports/<KEY>/full.csv.zip),keyed URL 只在 download() 内拼。
    url = "https://threatfox-api.abuse.ch/v2/files/exports/full.csv.zip"
    filename = "threatfox.csv"
    fields = ("is_malicious",)
    classification_type = "c2-server"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.85
    authoritative_for = ()               # SM-F1:is_malicious 无证据键生产者(幻影轴),不声明
    provenance_tier = "A"                 # A=官方一手(S21):abuse.ch 运营方直接发布
    skip_lines = 9

    def __init__(self, data_dir: Path):
        # 约定 5:源在 __init__ 读自己的 env,注册表只传 data_dir。v2 迁移
        # (票 #159):旧匿名出口 410,Auth-Key 缺省空串 → download() 时报错
        # (不在 import/注册时炸,源仍可离线加载旧证据)。
        super().__init__(data_dir)
        self._auth_key = os.environ.get("ABUSECH_AUTH_KEY", "")

    def _keyed_url(self) -> str:
        # url attr 是无 key 占位(…/exports/full.csv.zip);v2 端点把 Auth-Key
        # 作为路径段插在文件名前(票 #159 实测)。keyed URL 只在此拼,不入
        # self.url——注册表 roster/日志/测试断言面只见占位。
        prefix, _, fname = self.url.rpartition("/")
        return f"{prefix}/{self._auth_key}/{fname}"

    def download(self, token: CancelToken | None = None) -> None:
        if not self._auth_key:
            raise RuntimeError(
                "threatfox: abuse.ch 已迁 Auth-Key(旧匿名出口 410,票 #159)"
                "——须设 ABUSECH_AUTH_KEY 环境变量")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self._data_dir / "threatfox.zip"
        try:
            download_file(self._keyed_url(), zip_path, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"},
                          secret=self._auth_key)
            data = zip_path.read_bytes()
            if not data.strip():
                raise RuntimeError(f"Empty response from {redact_url(self.url)}")
            # 200-OK-坏体守卫(票 #159;Phase 3 step 8 惯例):v2 错误页也回
            # 200,坏体不得替换旧证据——须 PK zip 头或含 first_seen_utc 列头。
            if not (data[:4] == b"PK\x03\x04" or b"first_seen_utc" in data):
                raise RuntimeError(
                    f"unexpected threatfox payload (not a zip, no first_seen_utc "
                    f"header) from {redact_url(self.url)}")
            if data[:4] == b"PK\x03\x04":           # abuse.ch serves a ZIP
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    name = next((n for n in z.namelist() if n.endswith(".csv")), None)
                    if name is None:
                        raise RuntimeError("no .csv inside threatfox zip")
                    data = z.read(name)
            atomic_write_bytes(self._path, data)
        finally:
            zip_path.unlink(missing_ok=True)

    def harvest(self):
        """Yield (ip, Evidence) per row by delegating to parse_row (the single
        abuse.ch column parser), so the load path and the column-mapping tests
        share one parsing path."""
        with open(self._path, "r", encoding="utf-8") as f:
            for _ in range(self.skip_lines):
                next(f, None)
            for row in csv.reader(f):
                parsed = self.parse_row(row)
                if parsed is None:
                    continue
                yield parsed["_ip"], Evidence(
                    classification_type=parsed["classification_type"],
                    verdict=parsed["verdict"],
                    malware_name=parsed["malware_name"],
                    confidence=parsed["confidence"],
                    first_seen=parsed["first_seen"],
                    last_seen=parsed.get("last_seen"),
                    native_categories=parsed.get("native_categories", []),
                    tags=parsed.get("tags", []),
                    extra=parsed["extra"],
                )

    # ── legacy helper (column-mapping tests depend on this shape) ──
    def parse_row(self, row: list[str]) -> dict | None:
        if len(row) < 4:
            return None
        if _clean(row[3]) != "ip:port":   # ioc_type
            return None
        ioc_value = _clean(row[2])         # ioc_value, e.g. "1.2.3.4:80"
        parts = ioc_value.split(":")
        ip = parts[0].strip()
        port = parts[1].strip() if len(parts) > 1 else ""

        def _cell(i: int) -> str:
            return _clean(row[i]) if len(row) > i else ""

        try:
            confidence_pct = int(_clean(row[9]))   # confidence_level
        except (ValueError, IndexError):
            confidence_pct = 50
        out = {
            "_ip": ip,
            "classification_type": normalize(_clean(row[4]), THREATFOX_MAP),
            "verdict": "malicious",
            "malware_name": _clean(row[5]),       # fk_malware, e.g. win.vidar
            "confidence": confidence_pct,
            "first_seen": _clean(row[0]),         # first_seen_utc
            "native_categories": [_clean(row[4])],   # raw threat_type promoted
        }
        last_seen = _cell(8)
        if last_seen:
            out["last_seen"] = last_seen
        tags = [t.strip() for t in _cell(12).split(",")
                if t.strip() and t.strip().lower() != "none"]
        if tags:
            out["tags"] = tags
        extra: dict = {}
        if port:
            extra["port"] = port
        printable = _cell(7)
        if printable and printable.lower() != "none":
            extra["malware_printable"] = printable
        ioc_id = _clean(row[1])
        if ioc_id:
            extra["threatfox_ioc"] = ioc_id
        out["extra"] = extra
        return out
