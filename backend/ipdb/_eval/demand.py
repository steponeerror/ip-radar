"""--demand:答案率探针(罗盘批,2026-10-10 grill 裁定 #4)。

对双队列逐 IP 查询,聚合每字段答案率——"我们答不出什么"的实测形式,
discover skill Step 1 四输入之一(缺口陈述须引用本表列或 NEEDS 行)。

队列:
- fleet   舰队语料:每源从其原始数据文件抽 N 个 IP(corpus.sample_source_ips
          现成件)——测"我们见过的 IP 上各字段的证据密度"。
- random  随机可路由 v4(corpus.generate_neutral 现成件,is_global 过滤)——
          测真实世界盲区;threat 字段在此列 ≈0 属预期而非信号。

纪律:计数器聚合,逐 IP 流式,不物化百万级列表(OOM 铁律 2026-10-03)。
判例:DNS 批前 service 字段 fleet≈2%/random≈0% 即本探针要显形的形状。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .corpus import generate_neutral, sample_source_ips, stable_seed

_SCALARS = ("country", "city", "asn", "as_name", "ip_range")
_FLAGGED = ("malicious", "suspicious")


@dataclass
class FieldStat:
    """单字段计数器:answered = sources 非空(有证人,非 conf=0 无证据)。"""
    seen: int = 0
    answered: int = 0
    conf_sum: int = 0
    witnesses_sum: int = 0

    def row(self) -> str:
        pct = (100.0 * self.answered / self.seen) if self.seen else 0.0
        conf = (self.conf_sum / self.answered) if self.answered else 0
        wits = (self.witnesses_sum / self.answered) if self.answered else 0.0
        return (f"{pct:6.1f}%  conf~{conf:5.1f}  wits~{wits:4.1f}"
                f"  ({self.answered}/{self.seen})")


def _account(stats: dict[str, FieldStat], res: dict) -> None:
    """一个 lookup 结果(dict 形,to_dict() 契约)计入各字段计数器。"""
    for k in _SCALARS:
        f = res.get(k) or {}
        _hit(stats, k, bool(f.get("sources")), f.get("confidence"),
             len(f.get("sources") or []))
    _hit(stats, "is_isp", bool(res.get("is_isp")), None, None)
    threat = res.get("threat") or {}
    _hit(stats, "threat:flagged",
         threat.get("verdict") in _FLAGGED, None, None)
    types = [t for t, v in (res.get("classifications") or {}).items()
             if isinstance(v, dict) and v.get("detected")]
    _hit(stats, "class:detected", bool(types), None, None)
    for key, stmts in (res.get("attributes") or {}).items():
        _hit(stats, f"attr:{key}", bool(stmts), None, len(stmts or []))


def _hit(stats: dict[str, FieldStat], name: str, answered: bool,
         confidence, witnesses) -> None:
    st = stats.setdefault(name, FieldStat())
    st.seen += 1
    if answered:
        st.answered += 1
        if isinstance(confidence, (int, float)):
            st.conf_sum += confidence
        if isinstance(witnesses, int):
            st.witnesses_sum += witnesses


def probe_cohort(lookup_fn, ips) -> dict[str, FieldStat]:
    """纯函数:逐 IP 查询并聚合(ips 可为生成器;测试注入假 lookup_fn)。

    attr:* 分母 = 队列全体(每个 IP 都被问了"是否 proxy"这类问题,
    键缺席也是答案)——恒 100% 的 attr 行是测量错误,非覆盖事实。"""
    stats: dict[str, FieldStat] = {}
    n = 0
    for ip in ips:
        n += 1
        res = lookup_fn(ip)
        _account(stats, res if isinstance(res, dict) else res.to_dict())
    for st_name, st in stats.items():
        if st_name.startswith("attr:"):
            st.seen = n
    return stats


def fleet_ips(sources, per_source: int,
              rng: random.Random | None = None) -> list[str]:
    """舰队语料:每源抽 per_source 个(去重跨源,顺序稳定)。"""
    rng = rng or random.Random(stable_seed("demand-fleet"))
    seen: dict[str, None] = {}                  # dict 保序去重(3.7+)
    for src in sources:
        for ip in sample_source_ips(src, per_source, rng):
            seen.setdefault(ip, None)
    return list(seen)


def demand_report(lookup_fn, sources, per_source: int = 50,
                  n_random: int = 500) -> str:
    """双队列答案率 Markdown 表(探针 CLI 的输出契约)。"""
    fleet = probe_cohort(
        lookup_fn, iter(fleet_ips(sources, per_source)))
    rnd = probe_cohort(
        lookup_fn, generate_neutral(n_random, seed=stable_seed("demand-rand")))
    keys = sorted(set(fleet) | set(rnd),
                  key=lambda k: ((k.startswith("attr:")), k))
    lines = [
        f"# demand probe(per_source={per_source}, random={n_random})",
        "",
        "| field | fleet | random |",
        "|---|---|---|",
    ]
    for k in keys:
        f_st = fleet.get(k)
        r_st = rnd.get(k)
        lines.append(f"| {k} | {f_st.row() if f_st else '—'} "
                     f"| {r_st.row() if r_st else '—'} |")
    return "\n".join(lines)


def run(lookup_fn, sources, per_source: int = 50, n_random: int = 500,
        as_json: bool = False):
    """CLI 入口:返回报告文本(dict 形态 as_json 时)。"""
    if as_json:
        fleet = probe_cohort(
            lookup_fn, iter(fleet_ips(sources, per_source)))
        rnd = probe_cohort(
            lookup_fn, generate_neutral(n_random, seed=stable_seed("demand-rand")))
        return {
            cohort: {k: {"seen": s.seen, "answered": s.answered}
                     for k, s in stats.items()}
            for cohort, stats in (("fleet", fleet), ("random", rnd))
        }
    return demand_report(lookup_fn, sources, per_source, n_random)
