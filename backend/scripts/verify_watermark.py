# backend/scripts/verify_watermark.py
#!/usr/bin/env python3
"""ip-radar lineage watermark verifier (spec 2026-09-14-data-watermark §5.4).

Usage (usage lives HERE ONLY — silent disclosure, decision #10):
  python backend/scripts/verify_watermark.py --url https://suspect.example
      Probe a suspect ipradar-compatible service: GET /api/lookup/{ip} for
      each of the 500 family candidates. >=100 exact triple matches
      (source=="sentinel", derived classification_type, "suspicious")
      -> LINEAGE CONFIRMED. 503 warming: sleep 30s, retry once per IP.
      Report: hits/probed/failed + matched-IP detail (spec §5.4/§8). Per-IP
      transport failures (blocked/limiter, non-JSON) skip that IP and keep
      probing; verdict is based on hits only.

  python backend/scripts/verify_watermark.py --data-dir /path/to/data
      Scan a local data dir (dump/seized copy): layer 1 = exact key seeks
      in sentinel.lmdb (+v6 family); layer 2 = full cursor scan of every
      source LMDB validating extra.ingest_ref == mark_value(start, end).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from ipdb._watermark import (  # noqa: E402
    CONFIRM_THRESHOLD, MARK_GAMMA, canary_family, mark_value)
from ipdb._sources._lmdb import (  # noqa: E402
    decode_value, env_dir, ip_to_int, ip_to_int6, lookup,
    open_env_read, read_disjoint_flag, read_ptr)


def detect(query_fn) -> dict:
    """Layer-1 core: query_fn(ip) -> list[obs dicts] | None (probe failed).

    None = 该 IP 探测失败(屏蔽/限流/网络错):计入 failed、不计入
    probed,其余 IP 继续探测;结论仅由 hits 决定(spec §8:如实报告
    n/实际探到数)。"""
    fam = canary_family()
    hits, probed, failed, matched = 0, 0, 0, []
    for c in fam:
        out = query_fn(c.ip)
        if out is None:
            failed += 1
            continue
        probed += 1
        for it in out:
            if (isinstance(it, dict)
                    and it.get("source") == "sentinel"
                    and it.get("classification_type") == c.ctype
                    and it.get("verdict") == "suspicious"):
                hits += 1
                matched.append(c.ip)
                break
    verdict = ("CONFIRMED" if hits >= CONFIRM_THRESHOLD
               else "PARTIAL" if hits else "NOT_DETECTED")
    return {"hits": hits, "total": len(fam), "probed": probed,
            "failed": failed, "verdict": verdict, "matched": matched}


def _lookup_query_fn(base: str):
    def q(ip: str):
        url = f"{base.rstrip('/')}/api/lookup/{ip}"
        d = None
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    d = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt == 1:
                    time.sleep(30)      # warming: 退避一次后重试(spec §8)
                    continue
                return None             # 该 IP 传输失败:跳过,继续探测其余
            except (urllib.error.URLError, ValueError):
                return None             # 拒连/超时 | 非 JSON 响应体
        if not isinstance(d, dict):
            return None
        out = []
        for ctype, a in (d.get("classifications") or {}).items():
            for det in a.get("details") or []:
                row = dict(det)
                row.setdefault("classification_type", ctype)
                row.setdefault("verdict", a.get("verdict"))
                out.append(row)
        return out
    return q


def _layer1(data_dir: Path) -> dict:
    fam = canary_family()
    hits, matched = 0, []
    for suffix, conv, v6 in ((  # (base name, int conv, family filter)
            "sentinel.lmdb", ip_to_int, False),
            ("sentinel.v6.lmdb", ip_to_int6, True)):
        base = data_dir / suffix
        epoch = read_ptr(base)
        if epoch is None:
            continue
        env = open_env_read(env_dir(base, epoch))
        disjoint = read_disjoint_flag(base, epoch)
        for c in (x for x in fam if x.is_v6 == v6):
            node = lookup(env, conv(c.ip), disjoint=disjoint,
                          ip_version=6 if v6 else 4)
            for ev in (node if isinstance(node, list) else [node] if node else []):
                if (isinstance(ev, dict)
                        and ev.get("classification_type") == c.ctype
                        and ev.get("verdict") == "suspicious"):
                    hits += 1
                    matched.append(c.ip)
                    break
    verdict = ("CONFIRMED" if hits >= CONFIRM_THRESHOLD
               else "PARTIAL" if hits else "NOT_DETECTED")
    return {"hits": hits, "total": len(fam), "verdict": verdict,
            "matched": matched}


def _layer2(data_dir: Path) -> dict:
    valid = invalid = scanned = 0
    for ptr in sorted(data_dir.glob("*.lmdb.ptr")):
        base = data_dir / ptr.name[:-len(".ptr")]
        if base.name.startswith("sentinel"):
            continue                              # canary source = layer 1
        epoch = read_ptr(base)
        if epoch is None:
            continue
        env = open_env_read(env_dir(base, epoch))
        with env.begin() as txn:
            cur = txn.cursor()
            ok = cur.first()
            while ok:
                key, raw = cur.key(), cur.value()
                start = int.from_bytes(key, "big")
                end, ev = decode_value(raw)
                for e in (ev if isinstance(ev, list) else [ev]):
                    scanned += 1
                    ex = e.get("extra") if isinstance(e, dict) else None
                    if isinstance(ex, dict) and "ingest_ref" in ex:
                        if ex["ingest_ref"] == mark_value(start, end):
                            valid += 1
                        else:
                            invalid += 1
                ok = cur.next()
    verdict = ("CONFIRMED" if valid and invalid == 0
               else "SUSPICIOUS" if invalid else "NOT_DETECTED")
    return {"valid": valid, "invalid": invalid, "scanned": scanned,
            "expected": scanned // MARK_GAMMA, "verdict": verdict}


def probe_data_dir(data_dir: Path) -> dict:
    return {"layer1": _layer1(data_dir), "layer2": _layer2(data_dir)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="suspect ipradar-compatible base URL")
    ap.add_argument("--data-dir", help="local data dir to scan")
    args = ap.parse_args()
    if bool(args.url) == bool(args.data_dir):
        ap.error("exactly one of --url / --data-dir is required")
    if args.url:
        r = detect(_lookup_query_fn(args.url))
        m = r["matched"]
        # 模式一 PARTIAL 报告明细(spec §5.4):≤50 条全列,>50 条报数+前 50
        r["matched"] = (", ".join(m) if len(m) <= 50 else
                        f"{len(m)} ips, first 50: {', '.join(m[:50])}")
        print(json.dumps(r, ensure_ascii=False))
    else:
        r = probe_data_dir(Path(args.data_dir))
        for k in ("layer1",):
            r[k]["matched"] = f"{len(r[k]['matched'])} ips"
        print(json.dumps(r, ensure_ascii=False))
    lv = r.get("verdict") or (r["layer1"]["verdict"], r["layer2"]["verdict"])
    done = any(v == "CONFIRMED" for v in
               (lv if isinstance(lv, tuple) else (lv,)))
    print("LINEAGE CONFIRMED — data generated by the ip-radar pipeline"
          if done else "no confirmation", file=sys.stderr)
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
