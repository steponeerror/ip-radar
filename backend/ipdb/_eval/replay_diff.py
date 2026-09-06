# backend/ipdb/_eval/replay_diff.py
"""离线新旧评分对比:评分语义迁移的回放对比工具,方向断言层现为
spec 2026-09-06(verdict-aware scoring:存档退出评分,组 conf 改变 ⟹
新侧必须 has_archive)。

  --snapshot out.json   切换前跑(旧实现),存基线
  --compare base.json   切换后跑(新实现),出 diff 报告 + 方向断言

样本:corpus benchmark+benign + 每威胁源 5 个命中 IP(种子稳定)。

操作注记:baseline 采集与 compare 必须在同一无 pytest 窗口内配对进行
(pytest 冷启动会写 backend/data 造成漂移假阳性)。
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
    """每 IP 的可比视图:标量 conf + 各威胁组 (conf, verdict, n_sources, has_archive, min_first_seen, max_first_seen)。

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
            "has_archive": any(d.get("verdict") == "informational" for d in details),
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
    """spec 2026-09-06 验收断言(全换,旧 8-29 规则作废):

    - scalar conf:逐字节相等(红线);
    - 组 conf 改变 ⟹ 新侧必须 has_archive(唯一合法成因:存档退出
      投票/去重域收窄;全指控组与纯存档组数字不变,自动落入"相等"桶);
    - 旧侧全 clean 的 IP 不得凭空出现威胁组(保留 8-29 断言 5)。

    注:benign 弃权(spec §2.3 审计 F1)落地后,dedup 域收窄无
    informational 观测亦可合法改变组 conf,本守卫暂未枚举,届时需重审此规则。"""
    problems = []
    for field, old_conf in old["scalars"].items():
        new_conf = new["scalars"].get(field)
        if new_conf is not None and new_conf != old_conf:
            problems.append(f"{field}: scalar conf 改变 {old_conf}->{new_conf}")
    for ctype, oc in old["classifications"].items():
        nc = new["classifications"].get(ctype)
        if nc is None:
            continue
        if oc.get("conf") != nc.get("conf") and not nc.get("has_archive"):
            problems.append(
                f"{ctype}: conf 改变 {oc.get('conf')}->{nc.get('conf')} "
                f"且新侧无存档观测(唯一合法成因缺失)")
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
    p.add_argument("--compare", metavar="BASE.json", help="与基线对比")
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
    from types import SimpleNamespace
    return SimpleNamespace(sources=reg._sources)


if __name__ == "__main__":
    main()
