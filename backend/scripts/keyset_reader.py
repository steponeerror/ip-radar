# backend/scripts/keyset_reader.py
"""全量键集快照的读取函数(#569;PR-2 审计消费面,PR-1 同步交付)。

快照形状见 keyset_snapshot.py:逐源 <源>.txt.gz(行 = <单元>|<分类类型>,
已排序)+ meta.json。这里只做纯读取,不碰库、不开 LMDB(一个进程一种
打开方式)。"""
import gzip
import json
from pathlib import Path


def unit_class(ip_text: str) -> str:
    """单元四栏(v4/v6 × 单地址/网段),从单元文本判:#524 同款分栏
    (524_pairs13.py class_of),网段与单地址不互比。v4 网段文本带
    「/」,v6 任何形都带「:」。"""
    fam = "v6" if ":" in ip_text else "v4"
    kind = "cidr" if "/" in ip_text else "single"
    return f"{fam}_{kind}"


def load_meta(run_dir) -> dict:
    """读一轮快照的 meta.json(坏 json → 直接炸,不静默缩水;
    keysets.long_memory_ips 同款纪律)。"""
    return json.loads((Path(run_dir) / "meta.json").read_text(
        encoding="utf-8"))


def list_sources(run_dir) -> list[str]:
    """本轮有快照件的源(meta.json counts 的键,已排序;快照只落
    非空源,缺源 = 该源本轮零指控条目)。"""
    return sorted(load_meta(run_dir).get("counts", {}))


def load_keyset(run_dir, source: str, ctype: str | None = None) -> set[str]:
    """(源[,分类类型])的单元集;ctype=None → 该源全部类型。
    缺文件 = 空集。"""
    path = Path(run_dir) / f"{source}.txt.gz"
    if not path.exists():
        return set()
    out: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8") as gz:
        for line in gz:
            line = line.rstrip("\n")
            if not line:
                continue
            unit, ct = line.split("|", 1)
            if ctype is None or ct == ctype:
                out.add(unit)
    return out


def load_keyset_pairs(run_dir, source: str) -> set[tuple[str, str]]:
    """源的 (单元, 分类类型) 对集——audit 的 source_pair_sets
    (_eval/pairwise.py:11)同形状,PR-2 直接喂。缺文件 = 空集。"""
    path = Path(run_dir) / f"{source}.txt.gz"
    if not path.exists():
        return set()
    out: set[tuple[str, str]] = set()
    with gzip.open(path, "rt", encoding="utf-8") as gz:
        for line in gz:
            line = line.rstrip("\n")
            if not line:
                continue
            unit, ct = line.split("|", 1)
            out.add((unit, ct))
    return out
