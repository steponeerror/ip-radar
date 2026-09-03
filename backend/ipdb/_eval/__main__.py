"""CLI: wires the pure harness to the real ipdb._registry.

  python -m ipdb._eval <source>      # single-source verdict + report
  python -m ipdb._eval --rebuild     # rebuild the frozen benchmark corpus
  python -m ipdb._eval --all         # per-source verdict table (no ranking in v1)
  python -m ipdb._eval --model       # fleet corroboration-contrast model + acceptance suite
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path

from . import config
from .ablation import run_ablation
from .benign import BenignChecker
from .corpus import Corpus, build_benchmark, sample_source_ips, stable_seed
from .independence import oc_suspicion_pairs
from .metrics import (compute_other_distribution, mc, cg, conflict, oc,
                      fp_proxy, other_pct, confidence_uplift, dead_slot_fill,
                      pairs)
from .pairwise import pairwise_oc, source_pair_sets
from .report import write_report
from .suite import run_suite, write_model_report
from .verdict import assess

_PKG_DIR = Path(__file__).resolve().parent              # backend/ipdb/_eval
_REPO_ROOT = _PKG_DIR.parents[2]                        # _eval -> ipdb -> backend -> repo root
# 报告目录(spec 2026-08-28 §5.2):运行时状态区,env 可覆盖;write_report 自带 mkdir
REPORT_DIR = Path(os.environ.get(
    "IP_RADAR_EVAL_DIR",
    str(_REPO_ROOT / "backend" / "data" / "eval")))
CORPUS_PATH = _PKG_DIR / "corpus.json"                  # curated in-package asset (spec §5)

_JSON_HINT = "确认 DB 已 load / corpus 存在(--rebuild)"


def _json_error(code: str, message: str, hint: str) -> None:
    """--json 模式统一错误出口:stdout 合法 JSON + 非零退出(spec §5.2)。"""
    print(json.dumps({"error": {"code": code, "message": message, "hint": hint}},
                     ensure_ascii=False))
    sys.exit(1)


def _real_registry():
    """Bind the real ipdb._registry to the harness's injected interfaces."""
    import ipdb._registry as reg

    def lookup(ip): return reg.lookup(ip).to_dict()

    def toggle(name, enabled):
        # in-memory only — NEVER reg.set_source_enabled (which persists).
        if enabled:
            reg._disabled.discard(name)
        else:
            reg._disabled.add(name)

    from types import SimpleNamespace
    return SimpleNamespace(
        sources=reg._sources,
        load_db=reg.load_db,
        lookup=lookup,
        toggle=toggle,
    )


def run_for_source(source_name: str, registry=None, corpus_path=CORPUS_PATH,
                   out_dir=REPORT_DIR, benign=None):
    registry = registry or _real_registry()
    benign = benign or BenignChecker()
    rng = random.Random(stable_seed(source_name))

    corpus = Corpus.load(corpus_path) if corpus_path.exists() else Corpus()
    # dynamic candidate stratum: fresh sample each run.
    src_obj = next((s for s in registry.sources if s.name == source_name), None)
    if src_obj is not None:
        corpus.candidate_ips = sample_source_ips(src_obj, config.CORPUS_CANDIDATE_N, rng)

    baseline, candidate_snap = run_ablation(registry.lookup, registry.toggle,
                                            source_name, corpus)

    total_pairs = len(pairs(candidate_snap)) or 1
    _mc = mc(baseline, candidate_snap, source_name, total_pairs)
    metrics = {
        "MC": _mc,
        "CG": cg(baseline, candidate_snap, source_name),
        "conflict": conflict(baseline, candidate_snap),
        "oc": oc(baseline, candidate_snap, source_name),
        "dead_slot_fill": dead_slot_fill(baseline, candidate_snap),
        "confidence_uplift": confidence_uplift(baseline, candidate_snap),
        "fp": fp_proxy([ip for ip, _ in _mc.detail], benign),
        "other": other_pct(compute_other_distribution(src_obj, rng)),
    }
    # n-floor (spec §7): candidate-asserted (ip,type) pairs. Counts ONLY the
    # candidate's contribution so the floor actually protects niche sources
    # (counting any-source classifications would always exceed the floor).
    candidate_touched = len(pairs(candidate_snap, source_name))
    # OC suspicion across all source pairs (advisory), fed by the D4 pairwise
    # OC table over the baseline snapshot (= full fleet minus the candidate).
    # Same-declared-cluster pairs (firehol x ipsum) are pre-filtered inside.
    flags = oc_suspicion_pairs(pairwise_oc(source_pair_sets(baseline)))
    from ipdb._registry import SOURCE_CATEGORIES
    category = SOURCE_CATEGORIES.get(source_name, "other")
    verdict = assess(metrics, candidate_touched, flags, source_category=category)
    md, js = write_report(source_name, verdict, metrics, corpus, out_dir)
    return md, js, verdict


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m ipdb._eval")
    p.add_argument("source", nargs="?", help="source name to evaluate")
    p.add_argument("--rebuild", action="store_true", help="rebuild frozen benchmark corpus")
    p.add_argument("--all", action="store_true", help="evaluate every source (no ranking in v1)")
    p.add_argument("--model", action="store_true",
                   help="fleet corroboration-contrast model + acceptance suite")
    p.add_argument("--audit", action="store_true",
                   help="lineage audit over persisted model history (advisory, B1)")
    p.add_argument("--json", action="store_true", help="机器可读 JSON 到 stdout")
    args = p.parse_args(argv)

    registry = _real_registry()
    if args.json:
        # --json 下前置失败也必须走 stdout JSON 信封,不许 stderr 裸栈(spec §5.2)
        try:
            registry.load_db()
        except Exception as e:
            _json_error("internal", f"load_db failed: {e}", _JSON_HINT)
    else:
        registry.load_db()

    if args.rebuild:
        bench = build_benchmark(registry.sources, config.CORPUS_PER_TYPE_N)
        bench.save(CORPUS_PATH)
        print(f"rebuilt corpus -> {CORPUS_PATH}")
        return
    if args.model:
        from ipdb._merge import SOURCE_RELIABILITY
        corpus = Corpus.load(CORPUS_PATH) if CORPUS_PATH.exists() else Corpus()
        result = run_suite(registry.lookup, corpus,
                           declared_r=dict(SOURCE_RELIABILITY))
        md, js = write_model_report(result, REPORT_DIR)
        if args.json:
            print(Path(js).read_text())
        else:
            print(f"model suite: "
                  f"{sum(1 for c in result['checks'].values() if c['pass'])}"
                  f"/{len(result['checks'])} checks pass\n  report: {md}")
        return
    if args.audit:
        from .audit import lineage_audit
        res = lineage_audit(REPORT_DIR / "model")
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            print("lineage audit (advisory):")
            for s in res["recommended_derived"]:
                print(f"  {s}: " + "; ".join(
                    f"<= {u} (contain {f:.2f}, {af}/{af+bf} first)"
                    for u, f, af, bf in res["relations"][s]))
            print(f"  C-3: {'PASS' if res['c3']['pass'] else 'CHECK'} "
                  f"(false accusations: {res['c3']['false_accusations']}, "
                  f"known-missing: {res['c3']['missing_known']})")
        return
    if args.all:
        if args.json:
            results = []
            for s in registry.sources:
                try:
                    _, js, _ = run_for_source(s.name, registry=registry)
                    results.append(json.loads(Path(js).read_text()))
                except Exception as e:
                    results.append({"source": s.name, "error": {
                        "code": "internal", "message": str(e), "hint": _JSON_HINT}})
            print(json.dumps(results, ensure_ascii=False))
            return
        for s in registry.sources:
            _, _, v = run_for_source(s.name, registry=registry)
            print(f"{s.name:<20} {v.state}")
        return
    if not args.source:
        if args.json:
            _json_error("bad_request", "source required (or pass --all / --rebuild)",
                        "用法:python -m ipdb._eval <source> [--all|--rebuild] --json")
        p.error("source required (or pass --all / --rebuild)")
    if args.json:
        if next((s for s in registry.sources if s.name == args.source), None) is None:
            _json_error("source_not_found", f"no source named {args.source!r}",
                        "GET /api/sources 或查 backend/ipdb/_sources/ 确认源名")
        try:
            md, js, v = run_for_source(args.source, registry=registry)
        except Exception as e:
            _json_error("internal", str(e), _JSON_HINT)
        # 复用 write_report 的 render_json 序列化(顶层已含 source/generated_at)
        print(json.dumps(json.loads(Path(js).read_text()), ensure_ascii=False))
        return
    md, _, v = run_for_source(args.source, registry=registry)
    print(f"{args.source}: {v.state}\n  report: {md}")


if __name__ == "__main__":
    main()
