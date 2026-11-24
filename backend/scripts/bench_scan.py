"""Bench for the key-order blocklist scanner (#444, spec §4.2).

Usage:
  backend/.venv/bin/python backend/scripts/bench_scan.py \
      [--data-dir DIR] [--limit N] [--spill-dir DIR] [--asof EPOCH]

Prints ONE json line: unit counts (single/cidr, v4/v6), wall seconds,
per-unit ms, read-vs-fuse phase split, peak RssAnon, scanner stats.

计时口径:总秒 = open+iterate+close 全程墙钟;读库 vs 融合分账 =
各 phase 的 stats["timings"] 求和(phase_single_* = 归并取数+融合,
phase_cidr_* 同理——融合与取数在同一次遍历里交错,分账按相位给,
不是纯融合耗时);峰值 RssAnon 迭代中每 10 万单元采样一次
(/proc/self/status),--limit 小样本时峰值近似启动基线。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _rss_anon_kb() -> int | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("RssAnon:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--spill-dir", default=None)
    ap.add_argument("--asof", type=float, default=None)
    args = ap.parse_args()

    # data-dir 经环境变量进 _paths 的惰性解析——必须在首次 import ipdb 前
    # 设好,这里把 ipdb 的导入压到 main 内部(与 env 生效同相位)
    if args.data_dir:
        os.environ["IP_RADAR_DATA_DIR"] = args.data_dir
    from ipdb._scan import open_unit_scanner

    t0 = time.perf_counter()
    peak_kb = _rss_anon_kb()
    counts = {"v4_single": 0, "v4_cidr": 0, "v6_single": 0, "v6_cidr": 0}
    n = 0
    stats = {}
    with open_unit_scanner(asof=args.asof, spill_dir=args.spill_dir) as sc:
        for unit in sc:
            counts[f"v{'6' if unit.is_v6 else '4'}_"
                   f"{'cidr' if unit.is_cidr else 'single'}"] += 1
            n += 1
            if n % 100_000 == 0:
                kb = _rss_anon_kb()
                if kb is not None and peak_kb is not None:
                    peak_kb = max(peak_kb, kb)
            if args.limit is not None and n >= args.limit:
                break
        stats = json.loads(json.dumps(sc.stats))   # snapshot before close
        epochs = {k: list(v) for k, v in sc.epochs.items()}
    total_s = time.perf_counter() - t0

    phase_s = sum(stats.get("timings", {}).values())
    out = {
        "units_total": n,
        "units": counts,
        "total_s": round(total_s, 1),
        "per_unit_ms": round(total_s * 1000 / n, 4) if n else None,
        "phase_split_s": {
            "sum_of_phases": round(phase_s, 1),
            "timings": stats.get("timings", {}),
            "note": "phase_single/cidr 各自含归并取数与融合(交错,非纯融合)",
        },
        "peak_rss_anon_kb": peak_kb,
        "sources_read": sorted(stats.get("records", {}).keys()),
        "records": stats.get("records", {}),
        "cidr_records": stats.get("cidr_records", {}),
        "skipped_anomalies": stats.get("skipped_anomalies"),
        "epochs": epochs,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
