#!/usr/bin/env python3
"""C2 物化谓词双门(#192 / ADR 0009):位等价 + 版本戳消融。

门①位等价:代码未变时连续两次 rebuild,第二次必须零副作用——
  sidecar(ptr/count/cov/disjoint/.rev)/纪元目录逐字节同、mtime 同、
  纪元号不动。首跑(拷入的存量族无 .rev)先做一次迁移重建,再验证跳写。
门②消融(3 真实源 myip_ms/ziyadnz/cps):对照「touch csv 强制重建」
  (旧仪式,依赖 mtime 腿)与「HARVEST_REV 前进强制重建」(C2 代码代腿,
  csv mtime 全程不动)——两路径的计数 sidecar 与排除/告警日志必须一致,
  即版本戳机制下 touch 不再必要。

用法(在 worktree 根):
  backend/../../backend/.venv/bin/python scripts/c2_predicate_gates.py
数据隔离:从主仓 backend/data 只读 cp -a 到 worktree backend/data/gate/,
绝不写主仓。退出码 0 = 双门全过。

产物:notes/c2-predicate-ablation-2026-10-25.md 由本脚本打印的表格手工
汇编(脚本只输出机检结论,人读叙述在 notes)。
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # worktree 根
MAIN_DATA = Path("/home/huxiao/dev/pi-ip-lookup-tool/backend/data")   # 只读真相源
GATE_DATA = ROOT / "backend" / "data" / "gate"          # worktree 内隔离数据面

sys.path.insert(0, str(ROOT / "backend"))

import ipdb._sources._lmdb as lm                       # noqa: E402

SOURCES = [                                            # (模块, 类, raw 文件名)
    ("ipdb._sources.myip_ms", "MyipMsSource", "myip_ms"),
    ("ipdb._sources.ziyadnz", "ZiyadnzSource", "ziyadnz.csv"),
    ("ipdb._sources.cps_collected_iocs", "CpsCollectedIocsSource",
     "cps_collected_iocs.txt"),
]

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        failures.append(label)


def family_state(base: Path) -> dict:
    """族完整指纹:sidecar 字节 + 纪元目录清单 + 逐文件 sha256 + mtime_ns。"""
    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    side_names = [".ptr", ".count", ".cov", ".disjoint", ".rev"]
    st: dict = {"sidecars": {}, "epochs": {}}
    for suf in side_names:
        p = base.parent / (base.name + suf)
        st["sidecars"][suf] = (p.exists(), sha(p) if p.exists() else None,
                               p.stat().st_mtime_ns if p.exists() else None)
    if base.parent.exists():
        for child in sorted(base.parent.iterdir()):
            if child.is_dir() and child.name.startswith(base.name + ".") \
                    and child.name[len(base.name) + 1:].split(".")[0].isdigit():
                st["epochs"][child.name] = {
                    f.name: (sha(f), f.stat().st_mtime_ns)
                    for f in sorted(child.iterdir())}
    return st


class LogCap(logging.Handler):
    """rebuild 期间排除/告警日志捕手(同格式三元组,可多重集比对)。"""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.rows: list[tuple] = []

    def emit(self, rec):
        self.rows.append((rec.levelname, rec.name, rec.getMessage()))

    def __enter__(self):
        logging.getLogger().addHandler(self)
        return self

    def __exit__(self, *a):
        logging.getLogger().removeHandler(self)


def snapshot(data_dir: Path, raw: str) -> dict:
    stem = raw.rsplit(".csv", 1)[0] if raw.endswith(".csv") else raw
    v4 = data_dir / f"{raw}.lmdb"
    v6 = data_dir / f"{raw}.v6.lmdb"
    return {"v4": family_state(v4), "v6": family_state(v6),
            "raw_mtime_ns": (data_dir / raw).stat().st_mtime_ns}


def counts(data_dir: Path, raw: str) -> dict:
    stem = raw
    out = {}
    for fam in (f"{raw}.lmdb", f"{raw}.v6.lmdb"):
        cp = data_dir / (fam + ".count")
        pp = data_dir / (fam + ".ptr")
        out[fam] = ((cp.read_text().strip() if cp.exists() else None),
                    (pp.read_text().strip() if pp.exists() else None))
    return out


def prep_source(name: str, raw: str) -> Path:
    """cp -a 主仓该源全套(raw+两族 sidecar+纪元)到隔离目录,保 mtime。"""
    d = GATE_DATA / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in MAIN_DATA.iterdir():
        if f.name == raw or f.name.startswith(raw + "."):
            shutil.copy2(f, d / f.name) if f.is_file() else shutil.copytree(f, d / f.name)
    assert (d / raw).exists()
    return d


def run_source(cls_path: str, cls_name: str, raw: str) -> None:
    import importlib
    print(f"\n== {cls_name} ({raw}) ==")
    d = prep_source(cls_name.lower(), raw)
    cls = getattr(importlib.import_module(cls_path), cls_name)
    src = cls(data_dir=d)

    pre = counts(d, raw)
    print(f"  拷入存量族:{pre}")

    # ── 迁移重建(存量无 .rev → 版本戳腿触发;#192 部署注记的预期行为)──
    with LogCap() as cap_mig:
        src.rebuild()
    post = counts(d, raw)
    check(post[f"{raw}.lmdb"][0] == pre[f"{raw}.lmdb"][0],
          f"迁移重建 v4 计数不变 {pre[f'{raw}.lmdb'][0]} → {post[f'{raw}.lmdb'][0]}")
    check(post[f"{raw}.v6.lmdb"][0] == pre[f"{raw}.v6.lmdb"][0],
          f"迁移重建 v6 计数不变 {pre[f'{raw}.v6.lmdb'][0]} → {post[f'{raw}.v6.lmdb'][0]}")
    rev_v4 = (d / f"{raw}.lmdb.rev").read_text().strip()
    rev_v6 = (d / f"{raw}.v6.lmdb.rev").read_text().strip()
    check(rev_v4 == str(lm.HARVEST_REV) == rev_v6,
          f"两族盖章 .rev={rev_v4}/{rev_v6} == HARVEST_REV={lm.HARVEST_REV}")
    check(post[f"{raw}.lmdb"][1] != pre[f"{raw}.lmdb"][1],
          "迁移重建 v4 纪元前进(真重建非跳写)")

    # ── 门①:代码未变连续 rebuild → 零副作用逐字节同 ──
    s1 = snapshot(d, raw)
    src.rebuild()
    s2 = snapshot(d, raw)
    check(s1 == s2, "门① 位等价:第二次 rebuild 零副作用(sidecar/纪元/mtime 逐字节同)")
    check(s1["raw_mtime_ns"] == s2["raw_mtime_ns"], "门① raw mtime 未被触碰")

    # ── 门②a 旧仪式:touch csv(mtime 腿)强制重建 ──
    import os
    (d / raw).touch()
    m_before = (d / raw).stat().st_mtime_ns
    with LogCap() as cap_touch:
        src.rebuild()
    c_touch = counts(d, raw)
    check(c_touch[f"{raw}.lmdb"][0] == pre[f"{raw}.lmdb"][0], "touch 路径 v4 计数不变")
    rows_touch = sorted(cap_touch.rows)
    # 排除/过滤日志对照(touch vs 后续 rev 路径,同 multiset)
    print(f"  touch 路径日志 {len(rows_touch)} 行")

    # ── 门②b C2:harvest 代码代前进(HARVEST_REV+1),csv mtime 全程不动 ──
    lm.HARVEST_REV = lm.HARVEST_REV + 1
    try:
        m_b = (d / raw).stat().st_mtime_ns
        with LogCap() as cap_rev:
            src.rebuild()
        c_rev = counts(d, raw)
        m_a = (d / raw).stat().st_mtime_ns
        check(m_a == m_b == m_before, "门② rev 路径 csv mtime 全程不动(touch 不再必要)")
        # 计数对照:count sidecar 必相等;纪元号必然各自前进(机制便如此)
        cnt_touch = {k: v[0] for k, v in c_touch.items()}
        cnt_rev = {k: v[0] for k, v in c_rev.items()}
        check(cnt_rev == cnt_touch, f"门② 计数对照 rev路径==touch路径 {cnt_rev}")
        check(int(c_rev[f"{raw}.lmdb"][1]) > int(c_touch[f"{raw}.lmdb"][1]),
              f"rev 路径真重建纪元前进 {c_touch[f'{raw}.lmdb'][1]} → {c_rev[f'{raw}.lmdb'][1]}")
        rows_rev = sorted(cap_rev.rows)
        check(rows_rev == rows_touch,
              f"门② 排除/告警日志对照一致({len(rows_rev)} 行 multiset 相等)")

        # 收敛不循环:rev 前进后 .rev 已=新代,再 rebuild 必须跳写
        s3 = snapshot(d, raw)
        src.rebuild()
        check(snapshot(d, raw) == s3, "rev 前进后收敛:再 rebuild 零副作用(无循环)")
    finally:
        lm.HARVEST_REV = lm.HARVEST_REV - 1


def main() -> int:
    assert GATE_DATA.resolve() != MAIN_DATA.resolve()
    GATE_DATA.mkdir(parents=True, exist_ok=True)
    for cls_path, cls_name, raw in SOURCES:
        run_source(cls_path, cls_name, raw)
    print("\n" + ("=" * 60))
    if failures:
        print(f"双门未过:{len(failures)} 项失败")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("双门全过:门① 位等价 OK / 门② 消融(计数+日志对照,touch 不再必要)OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
