# backend/ipdb/_eval/sentinel.py
"""生效性哨兵: 新源物化后验证「引擎真的能看到它」(Q18 §3.2 / S13)。

Q18 物化流程 (spec 2026-10-12-eval-loop-hardening-design.md §3.2):
fetch→rebuild→生效性哨兵 20/20→评估→epoch 清理/回滚。哨兵从候选源自身
原始文件采样 n 个已知成员 (corpus.sample_source_ips 同款正则提取 ——
eval 包唯一真实键集通路, 不发明新数据通路), 经注入 lookup_fn 回查引擎
载荷 (LookupResult.to_dict() 形状, suite/ablation/layered 同约定), 按
源 category 三通道分派 (S13):

- threat: 成员须由「本源自身」以指控 verdict 作证 —— 组级 verdict 与
  组 details 逐源 verdict 均 ∈ _ACCUSING (malicious/suspicious; _types
  顶层单一真源, metrics/anchors/layered 同款借道)。只看融合顶判会把
  跨源清单重叠当成本源生效 (回声不是印证, 哲学 3); 失败探针区分
  not-accused (引擎全静默) 与 accused-by-others[...] (他源回声、本源
  缺席 —— 物化失效的典型形态)。
- asset: 成员须带本源 AssetStatement —— payload.attributes[axis] 含
  source==name, axis ∈ fields∩ASSET_SLOTS (陈述形态 = to_dict 落地
  {source,value,native_type}); ≥1 声明轴成立即过 (同源多轴成员可只
  陈述子集, 如 ip2proxy 行只带 is_proxy)。同样按 source 名归属, 他源
  同轴陈述不顶替 (回声禁令同 threat 通道)。
- geo_asn: 标量轴无 verdict/陈述判据 → 显式 N/A 标记 (pass=None, 禁
  冒充 False=拒或 True=过; S13: geo_asn 标量轴=非目标 spec §9), 键集
  型验证走 coverage_check。

采样确定性 (接口条款 2): seed 可显式传参, 缺省 = corpus.stable_seed
(source.name) (进程无关 sha256 名派生, 同名源跨进程恒同); 结果携
seed/n/channel, 报告可复算。
"""
from __future__ import annotations

import random

# _ACCUSING 私有名跨模块借道 (EV-F1 同款, metrics/anchors/layered 同源):
# 指控章单一口径 —— malicious/suspicious 证人集合由 _types 顶层唯一持有。
from .._types import _ACCUSING
# ASSET_SLOTS = asset 槽词表单一真源 (_evidence 顶层): 源 fields 与
# payload.attributes 键都以它为准, 勿另立清单。
from .._evidence import ASSET_SLOTS
# _accusing_sources 私有函数借道 (口径同源勿复刻): 全部指控源名集,
# 失败描述区分「他源回声」用。
from .layered import _accusing_sources
from .corpus import sample_source_ips, stable_seed


def _own_accusing_ctypes(payload: dict, source_name: str) -> set[str]:
    """本源自身指控 ctype 集: 组 verdict ∈ _ACCUSING 且组 details 有本源
    指控证人 (缺 verdict 键兑底 malicious, layered._accusing_sources 同
    口径的逐源变体)。"""
    out: set[str] = set()
    for ctype, ca in (payload.get("classifications") or {}).items():
        if ca.get("verdict") not in _ACCUSING:
            continue
        for d in ca.get("details", []):
            if (d.get("source") == source_name
                    and d.get("verdict", "malicious") in _ACCUSING):
                out.add(ctype)
                break
    return out


def _own_asset_axes(payload: dict, source_name: str,
                    axes) -> set[str]:
    """本源自身 asset 陈述轴集: payload.attributes[axis] 逐陈述按 source
    名归属, 他源同轴陈述不顶替。"""
    attrs = payload.get("attributes") or {}
    return {a for a in axes
            if any(s.get("source") == source_name
                   for s in (attrs.get(a) or []))}


def sentinel_probe(source, lookup_fn, n: int = 20,
                   *, seed: int | None = None) -> dict:
    """物化生效性探针: -> {"pass", "probes":[{ip,expected,actual}], ...}。

    pass=True ⟺ 全部探针命中 (spec §3.2 「哨兵 20/20」); 成员不足 n 时
    全取, pass 按实探数判 (宁少算, corpus 采样同款)。geo_asn 通道
    pass=None + status="N/A" (显式不适用标记, 非 bool)。fail-closed:
    未知 category / 原始文件无可提取成员 / asset 源无 asset 槽 →
    pass=False + 具名 status, 绝不放行。probes 每条 {ip, expected,
    actual} 恰三键: 失败由 expected≠actual 列明。
    """
    category = getattr(source, "category", "threat")
    if category == "geo_asn":
        # S13: geo_asn 标量轴=非目标 (spec §9) —— 无判据可探, 显式 N/A,
        # 不查引擎不打伪分; 键集型生效性判据 = coverage_check。
        return {"pass": None, "probes": [], "channel": "geo_asn",
                "status": "N/A", "seed": None, "n": 0, "ok": None,
                "source": source.name,
                "reason": "S13: geo_asn 标量轴=非目标 (spec §9); "
                          "键集型生效性验证用 coverage_check"}
    if category not in ("threat", "asset"):
        # 落地源 category ∈ {threat,asset,geo_asn} (_sources 元数据契约),
        # 出现第四种即配置漂移 → fail-closed 具名, 不猜通道
        return {"pass": False, "probes": [], "channel": category,
                "status": "UNKNOWN-CATEGORY", "seed": None, "n": 0, "ok": 0,
                "source": source.name,
                "reason": f"unsupported category {category!r} "
                          "(threat|asset|geo_asn)"}
    if seed is None:
        seed = stable_seed(source.name)   # 名派生缺省: 报告可复算的稳定 seed
    ips = sample_source_ips(source, n, rng=random.Random(seed))
    base = {"channel": category, "seed": seed, "n": len(ips),
            "source": source.name}
    if not ips:
        # fail-closed: 原始文件缺/无可提取成员 → 无探针可回查, 绝不放行
        # (无证据≠生效)
        return {**base, "pass": False, "probes": [], "ok": 0,
                "status": "NO-MEMBERS",
                "reason": "no member IPs extracted from source raw file"}

    if category == "threat":
        probes, ok = [], 0
        for ip in ips:
            payload = lookup_fn(ip)
            if _own_accusing_ctypes(payload, source.name):
                actual = "accusing"
                ok += 1
            else:
                others = _accusing_sources(payload) - {source.name}
                actual = (f"accused-by-others[{','.join(sorted(others))}]"
                          if others else "not-accused")
            probes.append({"ip": ip, "expected": "accusing",
                           "actual": actual})
    else:  # asset (attributes 通道)
        axes = sorted(f for f in getattr(source, "fields", ())
                      if f in ASSET_SLOTS)
        if not axes:
            # category=asset 却无 asset 槽 = 类属性自相矛盾 → 具名拒绝
            return {**base, "pass": False, "probes": [], "ok": 0,
                    "status": "NO-ASSET-AXIS",
                    "reason": "category=asset but fields∩ASSET_SLOTS is empty"}
        expected = f"any[{','.join(axes)}]@{source.name}"
        probes, ok = [], 0
        for ip in ips:
            payload = lookup_fn(ip)
            found = _own_asset_axes(payload, source.name, axes)
            if found:
                ok += 1
            probes.append({"ip": ip, "expected": expected,
                           "actual": f"[{','.join(sorted(found))}]"
                                     f"@{source.name}"})
    return {**base, "pass": ok == len(ips), "probes": probes, "ok": ok,
            "status": "OK" if ok == len(ips) else "FAILED"}


def coverage_check(source, keyset) -> dict:
    """S13 键集型: 键集成员经引擎逐源读路径可回查的占比 -> {"covered": float}。

    签名无 lookup_fn (契约即如此): 「引擎可回查」的可验证口径 = 引擎读
    该源 LMDB 的 source.query(ip) 原始读回非空 —— 融合 lookup 对
    非指控/标量通道无判据 (S13), 逐源读回才是物化生效的直接证据
    (geo_asn/attributes 通道用)。keyset 任意可迭代 (如
    keysets._source_ips 提取物), 去重定序后全量核; 空键集 →
    covered=None (空分母不冒充 0, layered rate=None 同纪律)。
    """
    members = sorted(set(keyset))
    base = {"source": source.name, "n": len(members)}
    if not members:
        return {**base, "covered": None, "hits": 0}
    hits = sum(1 for ip in members if source.query(ip))
    return {**base, "covered": hits / len(members), "hits": hits}
