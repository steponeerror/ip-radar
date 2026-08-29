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
    """每 IP 的可比视图:标量 conf + 各威胁组 (conf, n_sources, min_first_seen)。

    防御式读取:缺 conf 的字段/组降级为缺行,不让 KeyError 炸掉整个对比。
    """
    scalars = {k: result[k]["confidence"]
               for k in ("country", "asn", "as_name")
               if isinstance(result.get(k), dict)
               and result[k].get("confidence") is not None}
    classes = {}
    for ctype, ca in (result.get("classifications") or {}).items():
        if not isinstance(ca, dict) or ca.get("confidence") is None:
            continue
        details = ca.get("details") or []
        firsts = [d.get("first_seen") for d in details if d.get("first_seen")]
        classes[ctype] = {
            "conf": ca["confidence"],
            "verdict": ca.get("verdict"),
            "n_sources": len({d["source"] for d in details if d.get("source")}),
            "min_first_seen": min(firsts) if firsts else None,
            "max_first_seen": max(firsts) if firsts else None,
        }
    return {"scalars": scalars, "classifications": classes}


def _age_days(iso):
    from datetime import datetime, timezone
    if not iso:
        return None
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:                       # 源馈偶发无时区戳 → 按字面 UTC
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).days


def check_directional(old: dict, new: dict) -> list[str]:
    """A2 限定(裁决 2026-08-29 精确化后):单源新鲜±2;多源新鲜不降
    (old≠80——旧 Admiralty floor 把值恰好垫到 80,只有它是非法参照);
    组内最新 obs >180d 才算陈旧(用当前侧 max_first_seen),收敛 [45,55];
    as_name 单源 50→r×100 只查方向(新值 > 50)。返回违规描述列表。"""
    problems = []
    for field, old_conf in old["scalars"].items():
        new_conf = new["scalars"].get(field)
        if new_conf is None:
            continue
        if field == "as_name" and old_conf == 50 and new_conf not in (0, 50) \
                and new_conf < 50:
            problems.append(f"{field}: as_name 单源 conf 反向下降 {old_conf}->{new_conf}")
    for ctype, oc in old["classifications"].items():
        nc = new["classifications"].get(ctype)
        if nc is None:
            continue
        age = _age_days(oc.get("min_first_seen"))
        n = oc.get("n_sources", 0)
        if n == 1 and age is not None and age <= 7:
            if abs(nc["conf"] - oc["conf"]) > 2:
                problems.append(f"{ctype}: 单源新鲜漂移 {oc['conf']}->{nc['conf']}")
        elif n >= 2 and age is not None and age <= 30 and oc["conf"] != 80:
            if nc["conf"] < oc["conf"]:
                problems.append(f"{ctype}: 多源新鲜下降 {oc['conf']}->{nc['conf']}")
        else:
            # 陈旧判定用当前侧组内最新 obs:任一新鲜观测在,组即不陈旧
            newest_age = _age_days(nc.get("max_first_seen"))
            if newest_age is not None and newest_age > 180 \
                    and not (45 <= nc["conf"] <= 55):
                problems.append(f"{ctype}: 陈旧未收敛中立 {nc['conf']}")
    # spec §9 断言5:旧侧全 clean 的 IP,新实现凭空出现威胁组 → 违规。
    # 仅限旧侧零组(benign)才断言,避免旧侧已有组的 IP 因 DB 漂移新增组误报
    # (那是数据变化非评分 bug;丢组同样只进 markdown 报告,不违规)。
    if not old["classifications"]:
        for ctype, nc in new["classifications"].items():
            if nc.get("conf") is not None:
                problems.append(
                    f"{ctype}: 旧 clean IP 凭空出现威胁组 conf={nc['conf']}")
    return problems


def _fmt(v):
    return "—" if v is None else str(v)


def _diff_rows(ip: str, old: dict, new: dict) -> list[tuple]:
    """一行 = (ip, 字段/类型, old→new),只收有变化或单侧缺失的项。"""
    rows = []
    for field in old["scalars"] | new["scalars"]:
        o, n = old["scalars"].get(field), new["scalars"].get(field)
        if o != n:
            rows.append((ip, field, o, n))
    for ctype in old["classifications"] | new["classifications"]:
        oc, nc = old["classifications"].get(ctype), new["classifications"].get(ctype)
        if (oc or {}).get("conf") != (nc or {}).get("conf") \
                or (oc or nc) is None:
            if oc is None or nc is None:
                rows.append((ip, ctype, (oc or {}).get("conf"), (nc or {}).get("conf")))
            else:
                age = _age_days(oc.get("min_first_seen"))
                rows.append((ip, f"{ctype}(n={oc['n_sources']},age={_fmt(age)}d)",
                             oc["conf"], nc["conf"]))
    return rows


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
    # --compare:同一稳定样本集用当前(新)实现重评分,对基线出 diff 报告 + 方向断言
    base = json.loads(Path(args.compare).read_text())
    cur = {}
    for ip in ips:
        r = reg.lookup(ip).to_dict()
        if r.get("error") or r.get("is_reserved"):
            continue
        cur[ip] = snapshot_entry(r)
    rows, violations = [], []
    n_cls_old = n_cls_new = sum_cls_old = sum_cls_new = 0
    for ip in sorted(set(base) & set(cur)):
        violations += [f"{ip}: {p}" for p in check_directional(base[ip], cur[ip])]
        rows += _diff_rows(ip, base[ip], cur[ip])
        for ctype, oc in base[ip]["classifications"].items():
            nc = cur[ip]["classifications"].get(ctype)
            if oc.get("conf") is not None:
                n_cls_old += 1; sum_cls_old += oc["conf"]
            if nc and nc.get("conf") is not None:
                n_cls_new += 1; sum_cls_new += nc["conf"]
    only_base, only_cur = set(base) - set(cur), set(cur) - set(base)
    report = _PKG_DIR.parent.parent / "data" / "replay_diff_report.md"
    lines = [f"# replay diff report — {len(base)} baseline / {len(cur)} current ips",
             f"compared: {len(set(base) & set(cur))}; only-baseline: {len(only_base)}; "
             f"only-current: {len(only_cur)}",
             "",
             "| ip | field/type | old | new |",
             "|---|---|---|---|"]
    for ip, field, o, n in rows:
        lines.append(f"| {ip} | {field} | {_fmt(o)} | {_fmt(n)} |")
    report.write_text("\n".join(lines) + "\n")
    mean_old = sum_cls_old / n_cls_old if n_cls_old else 0
    mean_new = sum_cls_new / n_cls_new if n_cls_new else 0
    print(f"compare: {len(set(base) & set(cur))} ips, {len(rows)} changed rows -> {report}")
    print(f"classification groups: old {n_cls_old} (mean conf {mean_old:.1f}) "
          f"-> new {n_cls_new} (mean conf {mean_new:.1f})")
    print(f"directional violations: {len(violations)}")
    for v in violations:
        print(f"  VIOLATION {v}")
    sys.exit(1 if violations else 0)


def _bind(reg):
    class _R:
        sources = reg._sources
    return _R


if __name__ == "__main__":
    main()
