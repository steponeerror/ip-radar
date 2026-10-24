# backend/ipdb/_eval/agg_share.py
"""印证对聚合器占比披露(spec #180 Q4 租户 / issue #183)。

v0 只披露,不改 corroborated 语义:纯 derived 组互证(两个聚合器互投,
如 2026-10-24 114.114.114.114 cps+ziyadnz 事故)仍是裁定内现状 ——
grill Q2 2026-10-11 后语义,tests/eval/test_eval_metrics.py::
test_cg_two_derived_alone_corroborate 钉死;改语义须另票过回放闸门。

口径(全部既有原语,零新机制):
- 探针语料 = 启用指控源 raw 文件的稳定采样(corpus.sample_source_ips,
  per-source rng = stable_seed(name);并集超 TOTAL_CAP 时 exclusive.
  sample_keys 以 DEFAULT_SEED 截断——同 seed 逐字节可复算);
- 判定 = lookup 载荷(生产 to_dict 形状)里 verdict ∈ _ACCUSING 且
  corroborated=True 的组;指控池按生产同款重算(by_source 取 max 系数 →
  dedup_lineage),聚合器占比按 dedup 后池计——锚对回声(firehol/
  greensnow 镜像对)已在 dedup 内剔除,不双计(宁少算);
- 产出:n_corroborated_groups(分母)、derived_vote_share(聚合器票占
  总印证票比)、n_pure_derived_groups(纯聚合器互证组数 = 事故机制正身)
  + ≤3 例证据。只测量不持门:exit 恒 0(回归轨/能力轨分立,ADR 0008
  决策 2——披露不是闸门)。
"""
from __future__ import annotations

import datetime as _dt
import json

from .corpus import sample_source_ips, stable_seed
from .exclusive import DEFAULT_SEED, sample_keys
from .._logodds import DERIVED_SOURCES, coefficient, dedup_lineage
from .._types import _ACCUSING

SAMPLE_PER_SOURCE = 100      # 每指控源采样上限(raw 文件口径)
TOTAL_CAP = 1000             # 探针并集上限(月轮巡检量级;lookup ~ms 级)
EXAMPLES_MAX = 3             # 证据样本上限(matrix_scan EVIDENCE_MAX 同款)


def corroboration_agg_share(lookup_fn, probe_ips: list[str]) -> dict:
    """纯函数:probe_ips → 印证对聚合器占比结构(见模块 docstring 口径)。
    单个 lookup 失败原样上抛,不 except-continue(2026-10-10 假零判例)。"""
    n_probe = 0
    n_corr = 0                # 印证组数(分母)
    n_pure = 0                # 纯 derived 互证组数(事故机制正身)
    votes_total = 0
    votes_derived = 0
    examples: list[dict] = []
    for ip in probe_ips:
        payload = lookup_fn(ip)
        n_probe += 1
        for ctype, ca in (payload.get("classifications") or {}).items():
            if ca.get("verdict") not in _ACCUSING:
                continue
            if not ca.get("corroborated"):
                continue
            # 指控池重算(生产 _merge 同款:同源取 max 系数 → dedup_lineage)
            by_source: dict[str, float] = {}
            for d in ca.get("details") or ():
                if d.get("verdict") not in _ACCUSING:
                    continue
                src = d.get("source")
                if not src:
                    continue
                c = coefficient(d.get("reliability", 0.5),
                                d.get("first_seen"), ctype)
                if src not in by_source or c > by_source[src]:
                    by_source[src] = c
            deduped = dedup_lineage(sorted(by_source.items()))
            if len(deduped) < 2:
                continue      # corroborated 旗与镜像重算不一致 → 不计入
            accusers = {s for s, _ in deduped}
            derived = {s for s in accusers if s in DERIVED_SOURCES}
            n_corr += 1
            votes_total += len(accusers)
            votes_derived += len(derived)
            if accusers and derived == accusers:
                n_pure += 1
                if len(examples) < EXAMPLES_MAX:
                    examples.append({"ip": ip, "type": ctype,
                                     "accusers": sorted(accusers)})
    return {
        "kind": "agg_share",
        "n_probe": n_probe,
        "n_corroborated_groups": n_corr,
        "n_pure_derived_groups": n_pure,
        "derived_vote_share": (votes_derived / votes_total
                               if votes_total else None),
        "derived_sources": sorted(DERIVED_SOURCES),
        "examples": examples,
        # 现状注记(披露面自带,读数不依赖注释)
        "note": ("corroborated semantics unchanged in v0: pure-derived "
                 "mutual corroboration still counts (grill Q2 2026-10-11); "
                 "disclosure only (issue #183)"),
    }


def probe_ips(sources, *, per_source: int = SAMPLE_PER_SOURCE,
              total: int = TOTAL_CAP, seed: int = DEFAULT_SEED) -> list[str]:
    """启用指控源 raw 文件稳定采样并集(容量帽:sample_keys(seed) 截断;
    非 accusation 章/无文件的源跳过)。同输入同输出。"""
    import random
    union: list[str] = []
    seen: set[str] = set()
    for s in sources:
        ctype = getattr(s, "classification_type", None)
        verdict = getattr(s, "verdict", "malicious")
        if not ctype or verdict not in _ACCUSING:
            continue
        for ip in sample_source_ips(s, per_source,
                                    rng=random.Random(stable_seed(s.name))):
            if ip not in seen:
                seen.add(ip)
                union.append(ip)
    if len(union) > total:
        return sample_keys(union, seed, total)
    return union


def run_agg_share(registry, out_dir=None, *, eval_env: str | None = None
                  ) -> dict:
    """CLI 装配:启用指控源 → 采样 → 披露;可选落
    <out_dir>/model/agg-share-<ts>.json(anchors 报告族同形,ts/eval_env
    同款;失败不适用——本腿只测量,异常原样上抛)。"""
    res = corroboration_agg_share(
        registry.lookup, probe_ips(list(registry.sources)))
    if out_dir is not None:
        if eval_env is None:
            from .__main__ import eval_env as _current_env
            eval_env = _current_env()
        from pathlib import Path
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        (d / f"agg-share-{ts}.json").write_text(json.dumps(
            res, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    return res
