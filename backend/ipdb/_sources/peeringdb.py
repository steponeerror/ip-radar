"""PeeringDB IX fabric 前缀源(信息维度批,2026-10-10 grill #4)。

PeeringDB(社区维护主数据注册库,provenance 闸门 pass 判例同 dns_public)
开放 API 三端点,下载期一次拉全落本地(查询期零在线,otx REST 先例):
- /api/ixpfx — fabric 前缀 CIDR(主数据)
- /api/ix + /api/ixlan — 仅建 prefix→IX 名映射(native label 用)

裁定口径:仅 status=ok;in_dfz 进 extra 保留(不删证据);落盘为
`prefix,ix_name,in_dfz` CSV(单文件,harvest 直读)。呈现 = service 轴新值
"ix" + IX 名 native label(与 infra_services 的 service 值并列);
authoritative_for=()(service 权威留 DNS 双源,本源只作证);verdict=""
弃权(资产位作证不指控)。守卫:≥100 前缀行 fail-closed(200-OK 空/坏
内容不替换旧数据防清源)。分页 limit=250 循环到空页。
"""
import csv
import io
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .._evidence import Evidence
from .._source_base import Source

logger = logging.getLogger(__name__)

_API = "https://www.peeringdb.com/api"
_PAGE_LIMIT = 2000           # 裁剪 fields 后大页可达(实测 2000 稳定);全字段大页(250+)被当重查询限流→429(2026-10-10)
_MIN_PREFIX_ROWS = 100      # download 守卫(实测在千级,余量 10×)
_TIMEOUT = 120
_PAGE_SLEEP = 2.0           # 页间节流:无 key 开放 API 窗口较长(2026-10-10 实测短退避打穿,429/404 变体)
_HEADERS = {"User-Agent": "ip-lookup-tool/1.0",
            "Accept": "application/json"}


def _get_json(path: str, params: dict, retries: int = 4) -> dict:
    """单页 GET;429/5xx 长退避重试(窗口实测打穿过短退避;周更源,耐心免费),终败上抛。"""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{_API}{path}?{qs}", headers=_HEADERS)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
            wait = 10 * 3 ** (attempt - 1)     # 10/30/90/270s
            logger.info(f"peeringdb {path}: HTTP {e.code}, "
                        f"retrying in {wait}s (attempt {attempt})")
            time.sleep(wait)
    raise RuntimeError(f"peeringdb {path}: exhausted retries")  # unreachable


def _fetch_all(path: str, key: str, extra_params: dict | None = None) -> list[dict]:
    """offset 步进分页(PeeringDB 无 page 参数:实测 page=2 → 404,2026-10-10);
    页间节流;尾页短页即停。"""
    out, offset = [], 0
    while True:
        params = {"limit": _PAGE_LIMIT, "offset": offset}
        if extra_params:
            params.update(extra_params)
        body = _get_json(path, params)
        rows = body.get("data") or []
        out.extend(rows)
        if len(rows) < _PAGE_LIMIT:
            return out
        offset += _PAGE_LIMIT
        time.sleep(_PAGE_SLEEP)


def fetch_dataset() -> str:
    """三端点 → join → CSV 文本(prefix,ix_name,in_dfz)。

    纯函数(网络在 _fetch_all),下载守卫与测试共用。join:ixpfx.ixlan_id
    → ixlan.ix_id → ix.name;失链行仍保留(ix_name 空,宁少算不删证据)。
    """
    # 三坑入册(2026-10-10 实测):①无 page 参数(page=2→404,须 offset 步进)
    # ②全字段大页=重查询遭端点级限流≈1h(fields 裁剪后 2000 大页秒过)
    # ③连发触发分钟级惩罚窗(页间 2s 节流+退避)。裁剪到只取 join 所需列。
    ix_name = {r["id"]: (r.get("name") or "").strip()
               for r in _fetch_all("/ix", "ix", {"fields": "id,name"})}
    ixlan2ix = {r["id"]: r.get("ix_id") for r in _fetch_all(
        "/ixlan", "ixlan", {"fields": "id,ix_id"})}
    buf = io.StringIO()
    w = csv.writer(buf)
    seen = set()
    for pfx in _fetch_all("/ixpfx", "ixpfx",
                          {"fields": "prefix,ixlan_id,in_dfz,status"}):
        if (pfx.get("status") or "").strip() != "ok":
            continue
        prefix = (pfx.get("prefix") or "").strip()
        if not prefix or prefix in seen:
            continue          # 同段多 IX 声明:文件序首见者胜(dns_public 判例)
        seen.add(prefix)
        name = ix_name.get(ixlan2ix.get(pfx.get("ixlan_id")), "")
        w.writerow([prefix, name, "1" if pfx.get("in_dfz") else "0"])
    return buf.getvalue()


class PeeringDbSource(Source):
    name = "peeringdb"
    category = "asset"
    fields = ("service",)
    url = None                    # 多端点 REST,otx 先例;download_host 固定
    stale_days = 7
    reliability = 0.85            # 社区维护主数据注册库(编辑开放,较 dns_public 降半档)
    authoritative_for = ()
    single_evidence = True

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self._path = data_dir / "peeringdb.csv"

    @property
    def download_host(self) -> str | None:
        return urllib.parse.urlparse(_API).hostname

    def download(self, token=None) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        text = fetch_dataset()
        n = sum(1 for ln in text.splitlines() if ln.strip())
        if n < _MIN_PREFIX_ROWS:
            raise RuntimeError(
                f"peeringdb: only {n} prefix rows (<{_MIN_PREFIX_ROWS}) "
                f"— existing data file kept (fail-closed)")
        from ._download import atomic_write_bytes
        atomic_write_bytes(self._path, text.encode("utf-8"))
        logger.info(f"Downloaded peeringdb ({n} ix prefixes)")

    def harvest(self):
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 1:
                    continue
                prefix = row[0].strip()
                name = row[1].strip() if len(row) > 1 else ""
                in_dfz = row[2].strip() == "1" if len(row) > 2 else None
                if not prefix:
                    continue
                extra = ({"in_dfz": in_dfz} if in_dfz is False else None)
                yield prefix, Evidence(
                    service="ix",
                    native_types={"service": name} if name else None,
                    verdict="",   # 弃权(R17A-1):资产位作证不指控
                    extra=extra,
                )
