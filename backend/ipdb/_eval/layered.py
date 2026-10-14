"""四层读数: 装配 + 交集审计 + k 双报 + 分层向量 (spec §2.1-2.3/F5/F6/F7).

assemble_four_layers: 四 kind 资产各 load, 缺目录/空资产 = 显式 NO-LAYER
(§2.3 装配哨兵: 禁跳层、禁报 0; 坏资产照 assets.load_asset 炸出不静默降级);
交集按优先级 truth>infra>neutral>consensus 从低优先层剔除并逐 IP 注记。
layered_readout: 逐层逐 IP 查询引擎, 每层载荷经 persist_ip_snapshot 落盘
(F10 证据永不灭失), 输出嵌套分层向量 —— 无任何标量总分字段(F1 禁综合分)。
k 双报(§2.2 闸③): k_all = 指控源去重计数, k_nonhoneypot 同口径剔除蜜罐
方法学源(源类属性 honeypot_methodology 优先, config.HONEYPOT_METHODOLOGY
兜底; sources=None 时仅 config 集, 宁少算)。F5 长记忆分拆/F6 仅双派生
佐证计数 = 描述性子读数, 不动主读数、禁当召回率。
"""
from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .assets import load_asset
from .snapshots import persist_ip_snapshot

# 指控章单一口径(EV-F1 同款借道, metrics/anchors 同源): malicious/suspicious
from .._types import _ACCUSING

# 交集审计优先级(§2.3): 高优先层成员从低优先层剔除
PRIORITY = ("truth", "infra", "neutral", "consensus")

STATUS_OK = "OK"
STATUS_NO_LAYER = "NO-LAYER"


@dataclass
class LayerResult:
    """单层装配+读数结果。status ∈ {"OK","NO-LAYER"}; NO-LAYER 时其余
    字段为空, rate 恒 None —— 缺层≠0 层(§2.3), 永无 0 冒充。hits/rate/
    k_hist 由 layered_readout 回填(装配期无引擎读数), k_hist = k_all
    直方图 {k: 命中 IP 数}。"""

    kind: str
    status: str
    members: list[str] = field(default_factory=list)
    hits: int = 0
    rate: float | None = None
    k_hist: dict = field(default_factory=dict)
    removed_overlap: int = 0
    notes: list[str] = field(default_factory=list)
    # 命中 IP 具名清单(layered_readout 回填, 排序定序): F7 ε 敏感性
    # 需按身份再采(rng.sample), 不能只拿 hits 计数 —— 计数可再生不出成员。
    hit_members: list[str] = field(default_factory=list)


def assemble_four_layers(assets_root: Path) -> dict[str, LayerResult]:
    """四 kind 各 load <assets_root>/<kind>, 返回按优先序的 LayerResult。

    缺目录 → NO-LAYER(note "no-asset"); 空资产(member_count==0)→ 同哨兵
    (note "empty-asset", T4 carry: 闸全绿剔光的空资产不得当 0 读数层);
    指纹失配等坏资产 → load_asset 原样炸出(证据必须炸, 不许静默缩层)。
    """
    root = Path(assets_root)
    out: dict[str, LayerResult] = {}
    claimed_by: dict[str, str] = {}  # ip → 已占层中最高优先 kind
    for kind in PRIORITY:
        d = root / kind
        if not d.is_dir():
            out[kind] = LayerResult(kind, STATUS_NO_LAYER, notes=["no-asset"])
            continue
        members, meta = load_asset(d)
        if meta.member_count == 0:
            out[kind] = LayerResult(kind, STATUS_NO_LAYER, notes=["empty-asset"])
            continue
        kept, removed = [], []
        for ip in members:
            if ip in claimed_by:
                removed.append(ip)
            else:
                kept.append(ip)
                claimed_by[ip] = kind
        notes = [f"overlap: {ip} (also in {claimed_by[ip]})" for ip in removed]
        if not kept:
            notes.append("empty after overlap removal")  # 剔光层无读数, rate=None
        out[kind] = LayerResult(kind, STATUS_OK, members=kept,
                                removed_overlap=len(removed), notes=notes)
    return out


def _snapshot_payload(res: dict) -> dict:
    """to_dict 载荷 → F10 快照载荷: verdict 从 threat 展平到顶层(T6 carry:
    to_dict 的 verdict 嵌在 threat 下, persist 契约要求顶层带两键)。

    threat 整块作 verdict 值(verdict+confidence+types), S29 子读出免重查
    引擎可回算; 形状不符载荷整值照写, 宁多存不丢证。
    """
    out: dict = {}
    if "classifications" in res:
        out["classifications"] = res["classifications"]
    if "verdict" in res:
        out["verdict"] = res["verdict"]
    elif "threat" in res:
        out["verdict"] = res["threat"]
    return out or res


def _accusing_types(payload: dict) -> list[str]:
    """指控组 ctype 清单: 组级 verdict ∈ _ACCUSING(anchors._check 同口径)。"""
    return [ctype for ctype, ca in (payload.get("classifications") or {}).items()
            if ca.get("verdict") in _ACCUSING]


def _accusing_sources(payload: dict) -> set[str]:
    """指控源名集(跨全部组): 组 details 逐源 verdict ∈ _ACCUSING, 缺
    verdict 键兑底 malicious(metrics._effective_votes 同口径, 旧载荷兼容)。"""
    out: set[str] = set()
    for ca in (payload.get("classifications") or {}).values():
        if ca.get("verdict") not in _ACCUSING:
            continue
        for d in ca.get("details", []):
            if d.get("verdict", "malicious") in _ACCUSING and d.get("source"):
                out.add(d["source"])
    return out


def _lm_split(members: list[str], hit_set: set[str],
              long_memory: set[str]) -> dict:
    """F5 长记忆分拆: in = 成员 ∈ 长记忆名单, out = 其余。仅描述性,
    禁当召回率; 空半区 rate=None(同哨兵纪律, 不冒充 0)。"""
    def half(sel: set[str]) -> dict:
        n = len(sel)
        hits = len(sel & hit_set)
        return {"hits": hits, "rate": hits / n if n else None, "n": n}
    inside = {ip for ip in members if ip in long_memory}
    return {"in": half(inside), "out": half(set(members) - inside)}


def layered_readout(lookup_fn, layers: dict[str, LayerResult], *,
                    out_dir: Path, run_id: str, asof=None,
                    sources: Iterable | None = None,
                    long_memory: set[str] | None = None) -> dict:
    """逐层逐 IP 查询引擎出分层向量, 并按层落 F10 快照(证据永不灭失)。

    回填入参 LayerResult 的 hits/rate/k_hist(单层对象单处真源); readout
    每层块 = {status, hits, rate, k_all, k_nonhoneypot, ctype_mix}
    (k 直方图 {k: 命中 IP 数}; ctype_mix = 指控组 ctype → 命中 IP 数),
    truth 层另携 split_by_long_memory(缺名单 → 键在值 null, 模式稳定)。
    NO-LAYER 层块字段全 None 且不查不落盘 —— 哨兵贯穿, 缺层≠0 层。
    degraded = 任一层 status != "OK"。derived_only_corroboration(F6,
    §2.2 闸③) = 全部 OK 层命中 IP 中 k_all≥2 且指控源全属声明派生簇的
    唯一 IP 数 —— 层成员经交集审计互斥(assemble_four_layers), 全层唯一
    = 逐层求和, 无回声双计(哲学 3: 回声不是印证)。
    asof 非空时以 kwarg 透传(T10 时钟锚; None 走普通调用, T10 前引擎
    链无该形参)。sources 给源对象(.name/.honeypot_methodology)时并入
    蜜罐排除集, None 时仅 config.HONEYPOT_METHODOLOGY 兜底。
    """
    honeypot = set(config.HONEYPOT_METHODOLOGY)
    for s in sources or ():
        if getattr(s, "honeypot_methodology", False):
            honeypot.add(s.name)
    derived = set(config.LINEAGE_CLUSTERS)

    layer_blocks: dict[str, dict] = {}
    derived_only = 0
    for kind, lr in layers.items():
        if lr.status != STATUS_OK:
            block = {"status": lr.status, "hits": None, "rate": None,
                     "k_all": None, "k_nonhoneypot": None, "ctype_mix": None}
            if kind == "truth":
                block["split_by_long_memory"] = None
            layer_blocks[kind] = block
            continue
        snapshot: dict[str, dict] = {}
        k_all_hist: dict[int, int] = {}
        k_nh_hist: dict[int, int] = {}
        ctype_mix: dict[str, int] = {}
        hit_ips: set[str] = set()
        for ip in lr.members:
            # asof=None 普通调用(T10 前兼容); 非空 kwarg 透传引擎链
            res = lookup_fn(ip) if asof is None else lookup_fn(ip, asof=asof)
            payload = _snapshot_payload(res)
            snapshot[ip] = payload
            accusing = _accusing_sources(payload)
            types = _accusing_types(payload)
            if not types:
                continue
            hit_ips.add(ip)
            k_all_hist[len(accusing)] = k_all_hist.get(len(accusing), 0) + 1
            k_nh = len(accusing - honeypot)
            k_nh_hist[k_nh] = k_nh_hist.get(k_nh, 0) + 1
            for t in types:
                ctype_mix[t] = ctype_mix.get(t, 0) + 1
            if len(accusing) >= 2 and accusing <= derived:
                derived_only += 1  # F6 裁决: 全层唯一(层互斥, 无回声双计)
        lr.hits = len(hit_ips)
        lr.rate = len(hit_ips) / len(lr.members) if lr.members else None
        lr.k_hist = dict(sorted(k_all_hist.items()))
        lr.hit_members = sorted(hit_ips)
        persist_ip_snapshot(out_dir, run_id, kind, snapshot)
        block = {
            "status": STATUS_OK,
            "hits": lr.hits,
            "rate": lr.rate,
            "k_all": dict(sorted(k_all_hist.items())),
            "k_nonhoneypot": dict(sorted(k_nh_hist.items())),
            "ctype_mix": dict(sorted(ctype_mix.items())),
        }
        if kind == "truth":
            block["split_by_long_memory"] = (
                _lm_split(lr.members, hit_ips, long_memory)
                if long_memory is not None else None)
        layer_blocks[kind] = block
    return {
        "layers": layer_blocks,
        "intersection_audit": {k: {"removed_overlap": lr.removed_overlap,
                                   "notes": list(lr.notes)}
                               for k, lr in layers.items()},
        "degraded": any(lr.status != STATUS_OK for lr in layers.values()),
        "derived_only_corroboration": derived_only,
    }


def epsilon_sensitivity(truth_hits: Sequence[str],
                        epsilons=(0.0, 0.05, 0.10), *,
                        n: int, seed: int) -> dict[float, float]:
    """F7 ε 敏感性三档: 确定性剔 ε 比例命中后重算命中率 (hits-dropped)/n。

    n = 威胁真值层成员总数(分母固定, 装配层口径); 剔除走 rng.sample 取
    具名子集(S29 按身份再生可复用同 seed); seed/n keyword-only 必填
    (significance.py 同款纪律, 防共享默认 rng)。
    """
    if n <= 0:
        raise ValueError("n must be > 0")
    hits = list(truth_hits)
    rng = random.Random(seed)
    out: dict[float, float] = {}
    for eps in epsilons:
        dropped = rng.sample(hits, round(eps * len(hits)))
        out[eps] = (len(hits) - len(dropped)) / n
    return out
