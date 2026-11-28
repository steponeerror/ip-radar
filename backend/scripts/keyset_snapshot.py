#!/usr/bin/env python
"""每源全量键集快照(#569 第一步,PR-1)。

用按键序扫描器(UnitScanner,#444)把全库扫一遍,把判定为指控
(malicious/suspicious)的明细按源归账,逐源落「单元|分类类型」压缩件
+ meta.json(纪元、asof、单元数、源数),给转载关系审计(#569)当
全量键集输入。口径:

- 收哪些源:扫描器读集 = 启用、非私、非地理(#444 同款,类别不限——
  资产类源的断言以单元 details 出现也收,audit 的 tor_exits/protonvpn
  对需要它们;设计稿 §9);
- 什么算指控:detail 级 verdict ∈ _ACCUSING(ipdb/_eval/accusation.
  is_accusation;#529 裁决:缺键不算,宁少算)。与 #524 调研的「同场」
  判式(dev/arch-r4-scan/524_pairs13.py:121-125)同一判式,验收①
  逐源 presence 对得上靠的就是这一点;
- 行格式:<单元>|<分类类型>,排序后写;gzip filename="" mtime=0
  (_eval/keysets.py:57-58 同款确定性写法)→ 同输入两遍字节相同。

用法(骨架照 scan_equiv_check.py #444 §5;月轮接线见 scripts/
monthly_eval.sh 的 run_keysets_full):

  PYTHONHASHSEED=0 python backend/scripts/keyset_snapshot.py collect \\
      --asof 1765000000 --out-dir backend/data/eval/monthly/keysets-full

run_id 由 asof 推(UTC %Y%m%dT%H%M%SZ),产物落 <out-dir>/<run_id>/:
逐源 <源>.txt.gz + meta.json;尾行打一行 JSON 摘要(mode 键,月轮腿
按 scan-equiv 同款摘取留证)。

退出码:0 = 成功;非 0 = 用法错或崩溃(与 scan-equiv collect 同语义:
正常出口只有 0)。
"""
import argparse
import gzip
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# backend/(ipdb 包)+ 本目录(keyset_reader):按文件路径跑时前者自动在
# sys.path,经 importlib 载入(测试)时两者都要自己插。
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent))
sys.path.insert(0, str(_SCRIPT_DIR))


def collect(args) -> int:
    # 惰性导入:--data-dir 先落环境变量,引擎的路径解析才吃得到
    # (scan_equiv_check.collect 同款顺序)。
    if args.data_dir:
        os.environ["IP_RADAR_DATA_DIR"] = args.data_dir
    from ipdb._eval.accusation import is_accusation
    from ipdb._scan import open_unit_scanner
    from keyset_reader import unit_class

    run_id = datetime.fromtimestamp(args.asof, tz=timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    run_dir = Path(args.out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    keysets: dict[str, set[str]] = {}      # 源 → {「单元|分类类型」行}
    units_by_class: Counter = Counter()
    n_units = 0
    n_lines = 0
    t0 = time.perf_counter()
    with open_unit_scanner(asof=args.asof, spill_dir=args.spill_dir) as sc:
        for unit in sc:
            n_units += 1
            units_by_class[unit_class(unit.ip)] += 1
            for ctype, ca in (unit.result.classifications or {}).items():
                for d in ca.details:
                    # 指控口径单一判断(#529);缺 source 键的明细无法
                    # 归账,跳过(宁少算)。
                    if not is_accusation(d):
                        continue
                    src = d.get("source")
                    if not src:
                        continue
                    keysets.setdefault(src, set()).add(f"{unit.ip}|{ctype}")
                    n_lines += 1
            if args.limit is not None and n_lines >= args.limit:
                break                   # 冒烟:收够即停(规格同 scan-equiv --limit)
        # 纪元要等扫描结束才齐(sc.epochs 在 _open_envs 钉死)
        epochs = {k: list(v) for k, v in sc.epochs.items()}
        stats = {k: sc.stats[k] for k in ("skipped_anomalies",
                                          "anomalous_records")}
    # 排序后写(确定性,见模块 docstring):哈希种子不进字节。
    counts: dict[str, int] = {}
    for src in sorted(keysets):
        lines = sorted(keysets[src])
        counts[src] = len(lines)
        with open(run_dir / f"{src}.txt.gz", "wb") as f:
            with gzip.GzipFile(filename="", fileobj=f, mode="wb",
                               mtime=0) as gz:
                gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    meta = {
        "run_id": run_id,
        "asof": args.asof,
        "epochs": epochs,
        "units_total": n_units,
        "units_by_class": dict(sorted(units_by_class.items())),
        "n_sources": len(counts),
        "counts": counts,
        "stats": stats,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps({"mode": "collect", "run_id": run_id,
                      "asof": args.asof, "units_scanned": n_units,
                      "units_by_class": dict(sorted(units_by_class.items())),
                      "n_sources": len(counts), "lines": n_lines,
                      "epochs": epochs, "stats": stats,
                      "seconds": round(time.perf_counter() - t0, 1),
                      "out": str(run_dir)}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("mode", choices=("collect",))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--asof", type=float, required=True)
    ap.add_argument("--out-dir", required=True,
                    help="快照根目录;产物落 <out-dir>/<run_id>/")
    ap.add_argument("--spill-dir", default=None)
    ap.add_argument("--limit", type=int, default=None,
                    help="收够这么多条(单元×类型)就停(冒烟用;按单元"
                         "粒度检查,可越过 limit 一个单元的明细条数)")
    args = ap.parse_args(argv)
    return collect(args)


if __name__ == "__main__":
    sys.exit(main())
