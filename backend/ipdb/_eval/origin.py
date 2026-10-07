# backend/ipdb/_eval/origin.py
"""自采样偏差治理(leave-self-out, W0 层1)。

语料成员若抽自源自身 raw 文件(benchmark 构造即如此),该源在其上的
佐证事件是循环证据:源 s 的 pair (ip, ctype) 若 ip ∈ s 的 raw 文件,
剔除后再计 n/k/ρ。plan 级 Ruling(plan 2026-09-28 §Task2):聚合器
(raw 文件含全宇宙)LSO 后证据近空 → θ̂ no-signal 是诚实结果 —— 循环
佐证本就无信息,其定价走 lineage/权威路径,非缺陷。
"""
from __future__ import annotations

from .corpus import _IP_RE
from .events import Events, SourceEvents, independent
from .pairwise import pairwise_oc

_EMPTY: frozenset = frozenset()


def origin_map(sources, ips: list[str]) -> dict[str, set[str]]:
    """ip → 含该 ip 的源名集合。

    源 raw 文件正则成员判定,token 口径与 corpus.sample_source_ips
    一致(_IP_RE + CIDR 剥掩码);只对入参 ips 判定,不展开全文件宇宙。
    多文件源(firehol/blocklist_de 的 _path 是目录)读自报的 _files
    清单 —— 排除目录内 .tmp 残件;无 _path 或文件缺失 → 该源不贡献。
    """
    want = set(ips)
    out: dict[str, set[str]] = {ip: set() for ip in want}
    for s in sources:
        files = getattr(s, "_files", None)
        if files is None:
            p = getattr(s, "_path", None)
            files = [p] if p is not None and p.is_file() else []
        for f in files:
            if not f.is_file():
                continue
            tokens = _IP_RE.findall(f.read_text(errors="ignore"))
            members = {t.split("/")[0] for t in tokens
                       if t.split("/")[0].count(".") == 3} & want
            for ip in members:
                out[ip].add(s.name)
    return out


def lso_source_events(events: Events, origin: dict[str, set[str]]) -> Events:
    """剔除每源自采样 pair 后重算 per_source(n/k/by_ctype)。

    k 判定与 extract_events 同谓词:他人断言面不变,仅本源视角收缩
    (oc_table 从同一 pair_sets 重导,结果一致)。pair_sets 与
    monopoly_ctypes 原样保留 —— fountain/unique/monopoly 旗标仍按
    全量断言面描述该源,LSO 只治理证据计数与市场先验。
    """
    oc_table = pairwise_oc(events.pair_sets)
    pair_asserters: dict[tuple[str, str], set[str]] = {}
    for src, pairs in events.pair_sets.items():
        for p in pairs:
            pair_asserters.setdefault(p, set()).add(src)
    ev = Events(pair_sets=events.pair_sets,
                monopoly_ctypes=events.monopoly_ctypes)
    for src, pairs in events.pair_sets.items():
        se = SourceEvents()
        for p in pairs:
            if src in origin.get(p[0], _EMPTY):
                continue
            if p[1] in events.monopoly_ctypes:
                continue
            ctype_n, ctype_k = se.by_ctype.get(p[1], (0, 0))
            se.n += 1
            ctype_n += 1
            others = pair_asserters.get(p, set()) - {src}
            if any(independent(src, o, oc_table) for o in others):
                se.k += 1
                ctype_k += 1
            se.by_ctype[p[1]] = (ctype_n, ctype_k)
        ev.per_source[src] = se
    return ev
