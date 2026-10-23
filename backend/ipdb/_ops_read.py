"""P3 ops 只读面(票 #135):包/台账/判例列表与详情、kws 检索、导出 zip。

- 全部只读零写入;ops 根唯一拼写 = _ops_store.ops_root(裁④);
- _schema.md 非判例:列表/详情排除(检索排除同口径),导出随库携带保持
  自描述(P1 import_seeds 口径);
- 导出 = precedents/ 全量 + ledger.md;固定 zip 时间戳(1980-01-01)+ 排序
  遍历 → 同树两次导出字节一致(无损回算,哲学 1);
- 列表/检索倒序(日期前缀文件名 = 新条目先见,与包列表同惯例);
- 读缺失树 = 先 init(幂等)再读:空是真实态,不是 404(P2 spawn 前置
  init 同判例——目录缺失会让 rg 伪装 rc=2 基础设施故障)。
"""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import _ops_store

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)  # 固定时间戳:导出确定性(可回算)


def parse_kws(kws: str) -> list[str]:
    """检索串 → 词表:逗号/空白分隔,去空(P4 搜索框单输入友好形)。"""
    return [p for p in kws.replace(",", " ").split() if p]


def _resolve(kind: str, name: str) -> Path:
    _ops_store.validate_ops_filename(name)
    return _ops_store.ops_root() / kind / name


def list_packages() -> list[dict]:
    """包列表:仅 *.md,按名倒序(新包先见),带 size/modified(ISO-UTC)。"""
    _ops_store.init_ops_tree()
    out = []
    for p in sorted((_ops_store.ops_root() / "packages").glob("*.md"), reverse=True):
        st = p.stat()
        out.append({
            "name": p.name, "size": st.st_size,
            "modified": datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc).isoformat(),
        })
    return out


def read_package(name: str) -> str:
    """包全文逐字;不存在/名字形状非法显式报错(不伪装空)。"""
    path = _resolve("packages", name)
    if not path.is_file():
        raise FileNotFoundError(f"裁决包不存在: {name}")
    return path.read_text(encoding="utf-8")


def read_ledger() -> str:
    """台账全文(表头自建,空树 = 仅表头)。"""
    _ops_store.init_ops_tree()
    return (_ops_store.ops_root() / "ledger.md").read_text(encoding="utf-8")


def list_precedents() -> list[str]:
    """判例文件名列表(_schema.md 排除,倒序 = 新判例先见)。"""
    _ops_store.init_ops_tree()
    names = (p.name for p in (_ops_store.ops_root() / "precedents").glob("*.md")
             if not p.name.startswith("_"))
    return sorted(names, reverse=True)


def read_precedent(name: str) -> str:
    """判例全文逐字;_schema.md 非判例 → 不存在(列表/检索同口径)。"""
    if name.startswith("_"):
        raise FileNotFoundError(f"判例不存在: {name}(_ 前缀为库内说明/索引件,非判例)")
    path = _resolve("precedents", name)
    if not path.is_file():
        raise FileNotFoundError(f"判例不存在: {name}")
    return path.read_text(encoding="utf-8")


def search_precedents(keywords: Sequence[str]) -> list[str]:
    """kws 检索:P1 rg_search_precedents(OR、大小写不敏感、_schema.md 排除),
    命中倒序;rc≥2 基础设施故障原样上抛(不伪装空,T2 Minor-3 判例)。"""
    return sorted(_ops_store.rg_search_precedents(keywords), reverse=True)


def export_zip_bytes() -> bytes:
    """全量判例(含 _schema.md)+ 台账 → 内存 zip 字节。

    precedents 空目录不产空目录项(zip 无目录项语义,判例缺失 = 仅
    ledger.md,形状在而非 404)。"""
    _ops_store.init_ops_tree()
    root = _ops_store.ops_root()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted((root / "precedents").glob("*.md")):
            _add(zf, f"precedents/{path.name}", path)
        _add(zf, "ledger.md", root / "ledger.md")
    return buf.getvalue()


def _add(zf: zipfile.ZipFile, arcname: str, path: Path) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, path.read_bytes())
