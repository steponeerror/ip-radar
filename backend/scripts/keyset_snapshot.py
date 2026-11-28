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

退出码:0 = 成功;2 = 库里没有任何纪元或单元,拒绝落空快照;
其他非 0 = 崩溃或用法错。
"""
import argparse
import gzip
import json
import os
import shutil
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
    from ipdb._types import _ACCUSING
    from keyset_reader import unit_class

    run_id = datetime.fromtimestamp(args.asof, tz=timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    keysets: dict[str, set[str]] = {}      # 源 → {「单元|分类类型」行}
    units_by_class: Counter = Counter()
    n_units = 0
    n_lines = 0
    # S4(评审 2026-11-28):实现只做 detail 级一层,设计稿引的那行
    # (_types.py threat_summary)是「组级 detected ∧ 组级 verdict 指控 ∧
    # detail 级指控」三层——差多少没人量过。两个计数不改行为,第一轮真
    # 月轮(2026-12-01)跑完看数,再决定 PR-2 要不要收紧口径。
    n_accusing_details = 0      # 明细级判定为指控的行数(去重前)
    n_accusing_strict = 0       # 按「组级+明细级」三层口径算出来的行数
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
                    n_accusing_details += 1
                    if ca.detected and ca.verdict in _ACCUSING:
                        n_accusing_strict += 1
                    line = f"{unit.ip}|{ctype}"
                    keyset = keysets.setdefault(src, set())
                    if line not in keyset:   # 同源同单元同类型去重(逐源集合内去重,不同源不互吞)
                        keyset.add(line)
                        n_lines += 1         # = 各源文件数据行总数(去重后)
            if args.limit is not None and n_lines >= args.limit:
                break                   # 冒烟:收够即停(规格同 scan-equiv --limit)
        # 纪元要等扫描结束才齐(sc.epochs 在 _open_envs 钉死)
        epochs = {k: list(v) for k, v in sc.epochs.items()}
        stats = {k: sc.stats[k] for k in ("skipped_anomalies",
                                          "anomalous_records")}
    if not any(e != (None, None) for e in sc.epochs.values()) or n_units == 0:
        # 库里一个纪元都没有 = 数据目录没指对(空库):不写「长得像
        # 成功」的空快照,直接红(无证据即无话;2026-11-28 实测漏加
        # --data-dir 时曾静默落空件)。真库里单个源临时全空是正常的;
        # 登记表派生的全部源连一个纪元都没有,只可能是路径或装载出了事。
        print("库里没有任何纪元/单元(units=%d):数据目录没指对或库未"
              "装载,拒绝落空快照——核对 --data-dir/IP_RADAR_DATA_DIR"
              % n_units, file=sys.stderr)
        return 2
    # 先写 <run_id>.partial/,全部写完再整目录改名(S5,评审 2026-11-28):
    # 进程中途被杀只留 *.partial(一眼可知是半截),第二步按最新 run 目录
    # 找快照不会踩到「meta.json 缺席」的半截目录。同 run_id 重跑整目录替换
    # (快照可复算,不保留旧件)。
    run_dir = Path(args.out_dir) / run_id
    partial_dir = Path(args.out_dir) / f"{run_id}.partial"
    partial_dir.mkdir(parents=True, exist_ok=True)
    # 排序后写(确定性,见模块 docstring):哈希种子不进字节。
    counts: dict[str, int] = {}
    for src in sorted(keysets):
        lines = sorted(keysets[src])
        counts[src] = len(lines)
        with open(partial_dir / f"{src}.txt.gz", "wb") as f:
            with gzip.GzipFile(filename="", fileobj=f, mode="wb",
                               mtime=0) as gz:
                gz.write(("\n".join(lines) + "\n").encode("utf-8"))
    meta = {
        "run_id": run_id,
        "asof": args.asof,
        # 口径随件走(S3,评审 2026-11-28;设计稿 §2.4「口径细节写进
        # meta.json 和报告」):拿到快照目录的人不必翻脚本 docstring 就
        # 知道它是什么口径、哪个版本写的。改口径先升 version。
        "schema": {
            "version": 1,
            "sources": "扫描器读集(#444):启用、非私、非地理,类别不限;"
                       "只落非空源(缺源 = 该源本轮零指控条目)",
            "accusation": "仅收 detail 级 verdict ∈ {malicious, suspicious}"
                          "的明细(#529 口径:缺 verdict 不算,宁少算);"
                          "同源同单元同类型去重,不同源不互吞",
            "line_format": "行 = <单元>|<分类类型>,码位排序后 gzip 写"
                           "(filename='' mtime=0)",
            "unit_classes": "四栏 v4_single/v4_cidr/v6_single/v6_cidr"
                            "(units_by_class)",
            "epochs": "各源 [ptr 纪元号, 单元数],扫描循环结束后取",
            "determinism": "同输入同环境两遍逐字节相同(排序+固定 gzip 头"
                           "+meta sort_keys);时间只进 stdout 的 seconds",
        },
        "epochs": epochs,
        "units_total": n_units,
        "units_by_class": dict(sorted(units_by_class.items())),
        "n_sources": len(counts),
        "counts": counts,
        "stats": {**stats,
                  "accusing_details": n_accusing_details,
                  "accusing_strict": n_accusing_strict},
    }
    (partial_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    if run_dir.exists():
        shutil.rmtree(run_dir)
    partial_dir.rename(run_dir)
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
                    help="收够这么多条(源×单元×类型去重后)就停(冒烟"
                         "用;按明细粒度检查,可越过 limit 一个明细的条数)")
    args = ap.parse_args(argv)
    return collect(args)


if __name__ == "__main__":
    sys.exit(main())
