# backend/ipdb/_eval/replay_diff.py
"""离线新旧评分对比(spec 2026-08-29 §9)。

  --snapshot out.json   切换前跑(旧实现),存基线
  --compare base.json   切换后跑(Task 10 实现),出 diff 报告 + 方向断言

样本:corpus benchmark+benign + 每威胁源 5 个命中 IP(种子稳定)。
"""
import argparse
import json
import random
import sys
from pathlib import Path

from .corpus import Corpus, sample_source_ips, stable_seed

_PKG_DIR = Path(__file__).resolve().parent
CORPUS_PATH = _PKG_DIR / "corpus.json"


def sample_ips(registry) -> list[str]:
    corpus = Corpus.load(CORPUS_PATH) if CORPUS_PATH.exists() else Corpus()
    ips = corpus.all_ips()
    for s in registry.sources:
        if getattr(s, "classification_type", None):
            rng = random.Random(stable_seed(f"replay:{s.name}"))
            ips.extend(sample_source_ips(s, 5, rng))
    seen, out = set(), []
    for ip in ips:
        if ip not in seen:
            seen.add(ip); out.append(ip)
    return out


def snapshot_entry(result: dict) -> dict:
    """每 IP 的可比视图:标量 conf + 各威胁组 (conf, n_sources, min_first_seen)。"""
    scalars = {k: result[k]["confidence"]
               for k in ("country", "asn", "as_name") if k in result}
    classes = {}
    for ctype, ca in (result.get("classifications") or {}).items():
        details = ca.get("details") or []
        firsts = [d.get("first_seen") for d in details if d.get("first_seen")]
        classes[ctype] = {
            "conf": ca["confidence"],
            "verdict": ca["verdict"],
            "n_sources": len({d["source"] for d in details}),
            "min_first_seen": min(firsts) if firsts else None,
        }
    return {"scalars": scalars, "classifications": classes}


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m ipdb._eval.replay_diff")
    p.add_argument("--snapshot", metavar="OUT.json", help="存当前实现评分基线")
    p.add_argument("--compare", metavar="BASE.json", help="与基线对比(Task 10)")
    args = p.parse_args(argv)
    if not (args.snapshot or args.compare):
        p.error("need --snapshot or --compare")
    import ipdb._registry as reg
    reg.load_db()
    ips = sample_ips(_bind(reg))
    if args.snapshot:
        data = {}
        for ip in ips:
            r = reg.lookup(ip).to_dict()
            if r.get("error") or r.get("is_reserved"):
                continue
            data[ip] = snapshot_entry(r)
        Path(args.snapshot).write_text(json.dumps(data, indent=1))
        print(f"snapshot: {len(data)} ips -> {args.snapshot}")
        return
    print("compare mode ships in Task 10", file=sys.stderr)
    sys.exit(2)


def _bind(reg):
    class _R:
        sources = reg._sources
    return _R


if __name__ == "__main__":
    main()
