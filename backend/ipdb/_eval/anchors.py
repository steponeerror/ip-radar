# backend/ipdb/_eval/anchors.py
"""Anchor set: known-answer IPs used as a "not broken" gate for any
production-touching change (spec §5.2). Partial ground truth, curated.
Grow the lists, not knobs. A failure anywhere = the change rolls back.
"""
ANCHORS: list[tuple[str, str]] = [
    # public DNS/resolver infra — must stay clean
    ("8.8.8.8", "clean"), ("8.8.4.4", "clean"),
    ("1.1.1.1", "clean"), ("1.0.0.1", "clean"),
    ("9.9.9.9", "clean"), ("208.67.222.222", "clean"),
    # reserved ranges — must return the reserved short-circuit
    ("10.0.0.1", "reserved"), ("127.0.0.1", "reserved"),
    ("192.168.1.1", "reserved"), ("172.16.0.1", "reserved"),
    # tor exits (torproject published list; refresh quarterly) — is_tor true
    ("185.220.101.1", "tor"), ("171.25.193.78", "tor"),
    ("96.44.159.202", "tor"),
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
            if ca.get("verdict") in ("malicious", "suspicious"):
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
