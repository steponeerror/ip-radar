# backend/ipdb/_eval/anchors.py
"""Anchor set: known-answer IPs used as a "not broken" gate for any
production-touching change (spec §5.2). Partial ground truth, curated.
Grow the lists, not knobs. A failure anywhere = the change rolls back.
"""
import datetime as _dt
import json
from pathlib import Path

from .._types import _ACCUSING   # 指控章单一口径(EV-F1 同款借道,A2 遗留收口)

ANCHORS: list[tuple[str, str]] = [
    # public DNS/resolver infra — must stay clean
    ("8.8.8.8", "clean"), ("8.8.4.4", "clean"),
    ("1.1.1.1", "clean"), ("1.0.0.1", "clean"),
    ("9.9.9.9", "clean"), ("208.67.222.222", "clean"),
    # reserved ranges — must return the reserved short-circuit
    ("10.0.0.1", "reserved"), ("127.0.0.1", "reserved"),
    ("192.168.1.1", "reserved"), ("172.16.0.1", "reserved"),
    # tor exits (torproject published list; refresh quarterly) — is_tor true
    # 2026-10-14 季度刷新:96.44.159.202 已离 danmeuk_tor 现役表(生产/镜像双
    # 口径一致),换入现役 F3 Netze 段 185.220.101.34(双源 is_tor=True)。
    ("185.220.101.1", "tor"), ("171.25.193.78", "tor"),
    ("185.220.101.34", "tor"),
    # public cloud edges — hosting flag true
    ("52.95.116.115", "hosting"),   # AWS
    ("20.36.253.52", "hosting"),    # Azure
    ("34.64.121.1", "hosting"),     # GCP
]


def _check(res: dict, expect: str) -> str | None:
    if expect == "clean":
        if res.get("is_reserved"):
            return "expected clean, got reserved"
        for ca in (res.get("classifications") or {}).values():
            if ca.get("verdict") in _ACCUSING:
                return f"expected clean, got {ca.get('verdict')}"
        return None
    if expect == "reserved":
        return None if res.get("is_reserved") else "expected reserved"
    if expect in ("tor", "hosting"):
        stmts = (res.get("attributes") or {}).get(
            "is_tor" if expect == "tor" else "is_hosting", [])
        ok = any(s.get("value") for s in stmts)
        return None if ok else f"expected is_{expect}=true"
    return f"unknown expectation {expect}"


def run_anchors(lookup_fn) -> list[dict]:
    failures = []
    for ip, expect in ANCHORS:
        why = _check(lookup_fn(ip), expect)
        if why:
            failures.append({"ip": ip, "expect": expect, "reason": why})
    return failures


def anchors_report(lookup_fn, out_dir=None, *, eval_env: str | None = None
                   ) -> list[dict]:
    """run_anchors + 落盘（Phase 2 T8，清偿 Phase 1 终审 T14 缓议）。

    落 <out_dir>/model/anchors-<ts>.json（ts/序列化同 model-*.json 写法，
    dsem-*.json 同族）；件含 eval_env（S37 裁决①：None → call-time 读
    __main__.eval_env()）。失败也落盘（failures 原样留档，证据不灭）。
    位等价契约：返回值即 run_anchors 原样，CLI --anchors 的 stdout 与
    退出码（失败 sys.exit(1)）不因落盘变化（计算逻辑零改动）。"""
    fails = run_anchors(lookup_fn)
    if out_dir is not None:
        # eval_env 懒解析:仅落盘需要它才读 IP_RADAR_EVAL_ENV——纯读路径
        # (out_dir=None,docstring 契约零副作用)不得因无效 env 值 raise
        # (T8 复审②:裸 run_anchors 可成功则 anchors_report 也必须成功)
        if eval_env is None:
            from .__main__ import eval_env as _current_env
            eval_env = _current_env()
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        (d / f"anchors-{ts}.json").write_text(json.dumps(
            {"kind": "anchors", "eval_env": eval_env,
             "generated_at": _dt.datetime.now(
                 _dt.timezone.utc).date().isoformat(),
             "n_total": len(ANCHORS), "failures": fails},
            indent=1, default=str), encoding="utf-8")
    return fails
