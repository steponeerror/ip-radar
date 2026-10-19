#!/usr/bin/env python3
"""matrix_summary.py — `python -m ipdb._eval --matrix-scan --json` 输出 → 健康包违例读数摘要。

T3 契约:行数少、数字逐字取自 JSON(禁编造,Review Focus 4),flash 摘要员直接引用。
解析失败/失败信封不炸:输出一行说明(测量故障可见,不静默降级;无证据≠清白)。
用法: matrix_summary.py <matrix-scan --json 输出文件>
"""
import json
import sys


def main(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:  # noqa: BLE001 — 测量故障一行说明,不裸栈
        print(f"(matrix-scan JSON 解析失败: {e})")
        return 0
    if isinstance(d, dict) and "error" in d:
        e = d["error"]
        print(f"matrix-scan 失败信封: {e.get('code')}: {e.get('message')}")
        return 0
    c = d["counts"]
    print(f"exit_code={d['exit_code']}(0 干净/1 pending/2 violation) "
          f"violation={c['violation']} pending={c['pending']} "
          f"agreement={c['agreement']}")
    for lay, st in d["layers"].items():
        note = f"({','.join(st.get('notes') or [])})" if st.get("notes") else ""
        print(f"layer {lay}: {st['status']}{note}")
    for e in d["buckets"]["violation"]:
        srcs = sorted({s for ev in e.get("evidence", []) for s in ev["sources"]})
        line = f"violation 格: {e['cell']}"
        if e.get("note"):
            line += f"(note: {e['note']})"
        if srcs:
            line += f" 涉源: {','.join(srcs)}"
        print(line)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: matrix_summary.py <matrix-scan --json 输出文件>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
