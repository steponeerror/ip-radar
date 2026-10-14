# backend/ipdb/_eval/assets.py
"""Versioned corpus assets for the four-layer eval readout (eval 闭环硬化批).

An asset is a directory holding `ips.txt` (members, one per line) +
`meta.json` (AssetMeta). `fingerprint` = sha256 of the sorted members
(first 16 hex chars); `load_asset` recomputes it and raises on mismatch —
证据永不灭失: a corrupted asset must blow up, never silently degrade.

NO_LAYER marks "layer absent" ≠ "layer of size 0" (GLOSSARY 质量闸门·
哨兵①装配哨兵: 缺层=显式 NO-LAYER, 禁跳层/禁报 0). Deliverable is
structured assets, not a scalar score (F1 禁综合分). Later layer-ETL and
four-layer assembly tasks read/write all corpus layers through this module.
"""
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

# GLOSSARY 质量闸门四层词汇: kind 枚举(spec 任务书接口块)
KINDS = frozenset({"truth", "infra", "neutral", "consensus"})


@dataclass
class AssetMeta:
    version: str
    kind: str
    fingerprint: str
    member_count: int
    params: dict
    eval_env: str
    created_at: str


class Sentinel:
    """模块级单例哨兵: 身份即语义(两次引用同身份), repr 可读。"""
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<{self.name}>"


NO_LAYER = Sentinel("NO-LAYER")


def fingerprint(members: list[str]) -> str:
    """Order-insensitive content hash: sha256("\\n".join(sorted(members)), hex 前 16 位。"""
    return hashlib.sha256("\n".join(sorted(members)).encode()).hexdigest()[:16]


def save_asset(dir: Path, members: list[str], meta: AssetMeta) -> Path:
    # 写侧也闸 kind 与指纹一致性: 坏资产不许落盘, 等 load 才炸太晚
    if meta.kind not in KINDS:
        raise ValueError(f"unknown asset kind: {meta.kind!r} (kind ∈ {sorted(KINDS)})")
    if meta.fingerprint != fingerprint(members):
        raise ValueError("asset fingerprint mismatch")
    dir.mkdir(parents=True, exist_ok=True)
    # encoding="utf-8" 显式(C-locale 宿主默认 ANSI): 中文/任意非 ASCII
    # 内容写入不得依赖宿主 locale(终审 P2-4)
    (dir / "ips.txt").write_text("\n".join(members), encoding="utf-8")
    (dir / "meta.json").write_text(
        json.dumps(asdict(meta), indent=2, ensure_ascii=False),
        encoding="utf-8")
    return dir


def load_asset(dir: Path) -> tuple[list[str], AssetMeta]:
    meta = AssetMeta(**json.loads((dir / "meta.json").read_text()))  # 坏 json → JSONDecodeError(ValueError)
    members = (dir / "ips.txt").read_text().splitlines()
    if fingerprint(members) != meta.fingerprint:
        raise ValueError("asset fingerprint mismatch")
    return members, meta
