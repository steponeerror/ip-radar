# backend/ipdb/_eval/mirror_check.py
"""镜像 manifest 守卫 (S7/S6): rsync 后、读数前校验生产 volume 镜像未塌缩。

S7 (spec §8 镜像一致性): manifest = 文件数 + 总字节 + epoch 指纹 + 抽样
sha256, 与上一轮 manifest 比对; files/bytes 骤降 >20% → FAIL。守卫序:
校验失败必须先于读数失败(monthly_eval.sh set -e, 本步在 run_step model
之前中止)。S6 (新鲜度哨兵): epoch 指纹随 manifest 留档;纪元前进
(rebuild 换 ptr)本身不是失败, 只在 detail 注记。

epoch 指纹口径: 数据目录无单一全局 epoch 文件, 真实纪元标记 = 每源
<name>.lmdb.ptr 文本文件一行整数(_sources/_lmdb.py read_ptr);指纹 =
全部 *.ptr 按名排序「name=epoch」行 sha256 前 16 hex。任何 ptr 缺席或
不可读 → 该行记 "?"(指纹仍变, manifest 永不因 epoch 缺席而炸;缺证据
≠ 镜像塌缩, files/bytes 才是判据)。无任何 ptr → ""。

持久化: manifest 只在 ok(基线/通过)时落盘, 失败保留旧档使失败可
复现。宁响亮勿静默: detail 具名掉了什么、掉了多少(如 "files -37.5%
(>20% drop)")。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SAMPLE_TARGET = 32          # 抽样上限: sorted 相对路径每 len//32 取一
HEX_LEN = 16                # sha256 截断长度, 与指纹口径一致


def _epoch_fingerprint(data_dir: Path) -> str:
    """S6 epoch 指纹: 全部 *.ptr(每源纪元标记)按名排序后 sha256 前 16 hex。"""
    parts: list[str] = []
    for p in sorted(data_dir.rglob("*.ptr")):
        try:
            parts.append(f"{p.name}={p.read_text().strip()}")
        except OSError:
            parts.append(f"{p.name}=?")       # 不可读 ptr 记指纹不炸
    if not parts:
        return ""
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:HEX_LEN]


def manifest(data_dir: Path) -> dict:
    """镜像 manifest: 全量正则文件递归计 files/bytes + 确定性抽样哈希。"""
    data_dir = Path(data_dir)
    rels = sorted(
        p.relative_to(data_dir).as_posix()
        for p in data_dir.rglob("*") if p.is_file()
    )
    step = len(rels) // SAMPLE_TARGET
    sampled = rels[::step] if step else rels   # <32 个文件 → 全取
    return {
        "files": len(rels),
        "bytes": sum((data_dir / r).stat().st_size for r in rels),
        "epoch": _epoch_fingerprint(data_dir),
        "sample_sha256": {
            r: hashlib.sha256((data_dir / r).read_bytes()).hexdigest()[:HEX_LEN]
            for r in sampled
        },
    }


def check_against_previous(data_dir: Path, prev_manifest: dict | None,
                           drop_tolerance: float = 0.2) -> dict:
    """与上一轮 manifest 比对: files/bytes 骤降 >drop_tolerance → FAIL;
    epoch 变更单独非失败(纪元前进留痕)。"""
    return _compare(manifest(Path(data_dir)), prev_manifest, drop_tolerance)


def _compare(cur: dict, prev: dict | None, drop_tolerance: float) -> dict:
    if prev is None:
        return {"ok": True, "detail": f"baseline recorded (files={cur['files']})"}
    drops = []
    for key in ("files", "bytes"):
        before = prev.get(key)
        if isinstance(before, (int, float)) and before > 0:
            frac = 1 - cur[key] / before
            if frac > drop_tolerance:
                drops.append(f"{key} -{frac:.1%} (>{drop_tolerance:.0%} drop)")
    if drops:
        return {"ok": False, "detail": "; ".join(drops)}
    notes = [f"ok (files={cur['files']} bytes={cur['bytes']})"]
    if prev.get("epoch") and prev["epoch"] != cur["epoch"]:
        notes.append("epoch advanced")         # S6: 纪元前进非失败
    return {"ok": True, "detail": "; ".join(notes)}


def main(data_dir: Path, manifest_path: Path) -> int:
    """CLI 入口: 算 manifest → 比对 → ok 才落盘 → 打印 JSON, 非 ok 退出 1。"""
    data_dir, manifest_path = Path(data_dir), Path(manifest_path)
    prev, note = None, ""
    if manifest_path.is_file():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            note = "prev manifest corrupt, re-baselined; "   # 响亮注记不静默
    cur = manifest(data_dir)
    result = _compare(cur, prev, 0.2)
    detail = note + result["detail"]
    if result["ok"]:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(cur, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "detail": detail, "manifest": cur},
                     ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python3 -m ipdb._eval.mirror_check <data_dir> "
              "<manifest_path>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
