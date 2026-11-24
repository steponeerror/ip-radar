#!/usr/bin/env python
"""扫描结果与查询接口的逐字段对拍(#444 规格 §5 的验收工具件)。

同一个数据快照、同一个 asof、同一个 PYTHONHASHSEED,分两步跑——扫描器
开着的时候,同进程不能再 load_db() 打开同一批库:

  PYTHONHASHSEED=0 python backend/scripts/scan_equiv_check.py collect \\
      --asof 1765000000 --single-every 200 --out sample.jsonl.gz
  PYTHONHASHSEED=0 python backend/scripts/scan_equiv_check.py compare \\
      --asof 1765000000 --sample sample.jsonl.gz

两步都可加 --data-dir DIR(经环境变量进引擎的路径解析)。

collect:整库扫描一遍,网段单元全收、单地址单元每 K 个收一个,连同扫描
出的判定结果一行一个存进样本;asof 和各源纪元号写在旁证文件
<out>.head.json 里(纪元号要等扫描结束才齐,样本体是顺序流)。
compare:load_db() 后对样本里每个地址(网段单元用网络地址)调
lookup(addr, asof=…),与存下来的结果逐字节比。口径同扫描器:启用的源、
去掉私源。纪元号和样本首行不一致就退出 2(数据换了,重跑两步)。

退出码:0 = 一致(或与 --mutate-first 的预期不一致数相等);1 = 有不一致;
2 = 样本作废(纪元变了)或用法错。
--mutate-first N(compare):先把样本里前 N 条存下来的结果改坏再比——对拍
工具自己也要能红,N 条必须恰好比出 N 处不一致。
"""
import argparse
import gzip
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import orjson


def _public_enabled_names():
    from ipdb import _registry
    return frozenset(s.name for s in _registry._enabled_sources()
                     if s.name not in _registry._PRIVATE)


def collect(args) -> int:
    from ipdb._scan import open_unit_scanner
    n = {"units": 0, "single": 0, "cidr": 0}
    t0 = time.perf_counter()
    with gzip.open(args.out, "wb") as fh:
        with open_unit_scanner(asof=args.asof,
                               spill_dir=args.spill_dir) as sc:
            for unit in sc:
                n["units"] += 1
                if not (unit.is_cidr or n["units"] % args.single_every == 0):
                    continue
                rec = {"ip": unit.ip, "cidr": unit.is_cidr,
                       "addr": unit.ip.split("/")[0],
                       "result": unit.result.to_dict()}
                fh.write(orjson.dumps(rec) + b"\n")
                n["cidr" if unit.is_cidr else "single"] += 1
                if (args.limit is not None
                        and n["single"] + n["cidr"] >= args.limit):
                    break
            epochs = {k: list(v) for k, v in sc.epochs.items()}
            stats = {k: sc.stats[k] for k in ("units", "skipped_anomalies",
                                              "anomalous_records")}
    head = {"asof": args.asof, "epochs": epochs}
    Path(args.out + ".head.json").write_bytes(orjson.dumps(head))
    print(json.dumps({"mode": "collect", "asof": args.asof,
                      "units_scanned": n["units"],
                      "sampled_single": n["single"],
                      "sampled_cidr": n["cidr"],
                      "epochs": epochs, "stats": stats,
                      "seconds": round(time.perf_counter() - t0, 1),
                      "out": args.out}, ensure_ascii=False))
    return 0


class _Sample:
    """样本体:旁证(asof、各源纪元号)在 <样本>.head.json,样本体逐行迭代。"""

    def __init__(self, path):
        self._path = path
        self.head = orjson.loads(
            Path(path + ".head.json").read_bytes())

    def __iter__(self):
        with gzip.open(self._path, "rb") as fh:
            for line in fh:
                yield orjson.loads(line)


def compare(args) -> int:
    os.environ.setdefault("IP_RADAR_POOL_CHILD", "1")   # 不让加载顺手清旧纪元
    from ipdb import load_db, lookup, _registry
    from ipdb._sources._lmdb import read_ptr
    sample = _Sample(args.sample)
    if sample.head["asof"] != args.asof:
        print(f"asof 不一致:样本 {sample.head['asof']} ≠ 参数 {args.asof}",
              file=sys.stderr)
        return 2
    records = list(sample)
    load_db()
    now = {s.name: [read_ptr(s._lmdb_base), read_ptr(s._lmdb6_base)]
           for s in _registry._enabled_sources()}
    stale = sorted(n for n, e in sample.head["epochs"].items() if now.get(n) != e)
    if stale:
        print("纪元变了,样本作废,两步都要重跑: " + ", ".join(stale),
              file=sys.stderr)
        return 2
    allowed = _public_enabled_names()
    bad = 0
    examples = []
    for i, rec in enumerate(records):
        if i < args.mutate_first:
            rec["result"]["ip"] = "0.0.0.0"           # 对拍工具自检
        got = lookup(rec["addr"], allowed_sources=allowed,
                     asof=args.asof).to_dict()
        if orjson.dumps(got) != orjson.dumps(rec["result"]):
            bad += 1
            if len(examples) < 20:
                old = rec["result"]
                examples.append({
                    "ip": rec["ip"],
                    "differing_keys": sorted(k for k in set(got) | set(old)
                                             if got.get(k) != old.get(k))})
    print(json.dumps({"mode": "compare", "asof": args.asof,
                      "sampled": len(records), "mismatches": bad,
                      "mutate_first": args.mutate_first,
                      "examples": examples}, ensure_ascii=False))
    return 0 if bad == args.mutate_first else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=("collect", "compare"))
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--asof", type=float, required=True)
    ap.add_argument("--out", default=None, help="collect:样本输出 .jsonl.gz")
    ap.add_argument("--sample", default=None, help="compare:样本文件")
    ap.add_argument("--spill-dir", default=None)
    ap.add_argument("--single-every", type=int, default=200)
    ap.add_argument("--limit", type=int, default=None,
                    help="collect:收够这么多条就停(冒烟用)")
    ap.add_argument("--mutate-first", type=int, default=0)
    args = ap.parse_args(argv)
    if args.data_dir:
        os.environ["IP_RADAR_DATA_DIR"] = args.data_dir
    if args.mode == "collect" and not args.out:
        ap.error("collect 需要 --out")
    if args.mode == "compare" and not args.sample:
        ap.error("compare 需要 --sample")
    return collect(args) if args.mode == "collect" else compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
