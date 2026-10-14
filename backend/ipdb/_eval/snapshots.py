# backend/ipdb/_eval/snapshots.py
"""F10 per-IP 快照持久化(jsonl.gz)。

把一轮逐 IP 读数(snapshot: ip → LookupResult.to_dict() 载荷)原样落盘,
供 S29 子读出免重查询引擎复算(哲学 1 证据永不灭失)。
精简纪律(照 brief, 不自作额外过滤): 载荷是 dict 且 classifications/verdict
两键齐备 → 逐行只留这两个计分字段; 缺任一键 → 整值照写, 宁多存不丢证。
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

_FIELDS = ("classifications", "verdict")


def persist_ip_snapshot(out_dir: Path, run_id: str, layer_kind: str,
                        snapshot: dict) -> Path:
    """写 <out_dir>/snapshots/<run_id>/<layer_kind>.jsonl.gz, 返回文件路径。

    逐行一条 {"ip": ..., "classifications": ..., "verdict": ...}, 紧凑
    separators; gzip mtime=0 + filename="" 确定性字节(同快照可复现,
    keysets 月度快照同款纪律)。
    """
    path = Path(out_dir) / "snapshots" / run_id / f"{layer_kind}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        # filename="" 头部不嵌路径: 字节只由内容决定
        with gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0) as gz:
            for ip, value in snapshot.items():
                # 两键齐备才精简(T6 评审硬化): 缺任一键整值照写 ——
                # 半形状载荷(如裸 to_dict 的 threat)不许被静默裁掉
                if isinstance(value, dict) and all(k in value for k in _FIELDS):
                    payload = {k: value[k] for k in _FIELDS if k in value}
                else:
                    payload = value  # 形状不符 → 整值照写
                gz.write((json.dumps({"ip": ip, **payload},
                                     separators=(",", ":"),
                                     ensure_ascii=False) + "\n").encode())
    return path


def load_ip_snapshot(path: Path) -> dict:
    """逆操作: 逐行 json 还原 ip → 载荷 dict(插入序 = 落盘行序)。"""
    out: dict = {}
    with gzip.open(path, "rt", encoding="utf-8") as gz:
        for line in gz:
            if not line.strip():
                continue
            entry = json.loads(line)
            out[entry.pop("ip")] = entry
    return out
