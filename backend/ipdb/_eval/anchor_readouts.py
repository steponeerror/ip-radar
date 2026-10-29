# backend/ipdb/_eval/anchor_readouts.py
"""锚读数族 v0 两读数(#233 交付块3,ADR 0013):干净锚误报率 + 扫描锚召回。

纯测量零持门(聚合器占比 agg_share 先例,回归轨/能力轨分立 ADR 0008
决策 2):exit 恒 0,阈值冻结另走验收门(预注册纪律);eval 结果不回流
权重(声明 r 人审)——HADES(NDSS'25)式投毒动机弱,v0 仅注记可操纵面。

- 读数A 干净锚误报率:census N = 全部 expect=clean 锚(全量非采样,锚集
  本身就小);指控池按生产合并语义重算(agg_share.py:49-66 先例:同源
  取 max 系数 → dedup_lineage,禁裸 detail.source——镜像对会双计,违
  「宁少算」);被控锚 accusers 留 dedup 后读数,原始指控 detail 三元组
  原样留痕(无损红线:原始证据可回算)。成因三分类(真误列/伪造源摄入/
  消费端误读)按 ADR 0013 是人裁解释框架——v0 只输出 accuser 证据面,
  不做自动归类。
- 读数B 扫描锚召回:真值层 = scanner_ranges 自报段成员;指控池 leave-out
  排除 "scanner_ranges" 自身(源名唯一,66 路 MISP + Xpanse 全收在这一个
  name 下,排一个名即排全部 67 路)。与 ADR 0011 真值层排除刻意不对称:
  那边成员全排除(入语料=自证污染),这边只排自回声——测的是指控池对
  已知扫描器的召回,自证进分子即读数恒 1(ADR 0013「三面不对称是特性
  不是 bug」)。大段成员多 → 段内成员稳定采样(per-source stable_seed +
  容量帽,probe_ips 同纪律),N/seed/成员清单随件落盘(McHugh 2000
  census 纪律:程序可复算)。
- 统计 = Clopper-Pearson 精确界(复用 model.beta_ppf,NR §6.4 连分数;
  ADR 0013 接入关复用条款;仓内零 SciPy 纪律)+ 零事件精确上界
  1-(α/2)^(1/n)(Beta(1,n) 闭式,rule of three 家族)。
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import json
import random
from bisect import bisect_right
from pathlib import Path

from .anchors import ANCHORS
from .corpus import stable_seed
from .layer_builders import scanner_ranges_prefixes
from .model import beta_ppf
from .truth_layer import apply_scanner_filter
from .._logodds import coefficient, dedup_lineage
from .._types import _ACCUSING

CP_LEVEL = 0.95                      # 精确界置信水平(统计约定,非门阈值)
SCANNER_PROBE_N = 300                # 段成员采样容量帽(exclusive.SAMPLE_N 同量级,lookup ~ms)
SCANNER_PROBE_SEED_NAME = "scanner_ranges"   # per-source stable_seed(probe_ips 同纪律)
LEAVE_OUT = "scanner_ranges"         # 自报段源名唯一串(corpus.py:117 判例同款)

_CAUSE_TAXONOMY = ["真误列", "伪造源摄入", "消费端误读"]
_TAXONOMY_NOTE = ("cause taxonomy (真误列/伪造源摄入/消费端误读, ADR 0013) "
                  "is a human-adjudication framework; v0 emits the accuser "
                  "evidence surface only — no auto-classification")
_HADES_NOTE = ("v0 measurement only, never gates; eval results do not flow "
               "back into weights (声明 r 人审). Manipulation surface noted "
               "(HADES NDSS'25-style poisoning): anchor/probe membership is "
               "public knowledge — read as advisory, adjudicate by human")


def clopper_pearson(k: int, n: int, level: float = CP_LEVEL) -> tuple:
    """二项比例精确置信界(Clopper & Pearson 1934, Biometrika 26:404):
    lo = B⁻¹(α/2; k, n-k+1),hi = B⁻¹(1-α/2; k+1, n-k)。

    退化支显式处理,勿喂 beta_ppf a=0(lgamma(0) 发散):k=0 → lo=0
    (零事件精确上界 = 1-(α/2)^(1/n),Beta(1,n) CDF 闭式,rule of three
    家族,Brown-Cai-DasGupta 2001 §1);k=n → hi=1;n=0 → (None, None)
    (零读数≠0,model.ci n=0 同款纪律)。实现复用 model.beta_ppf(NR §6.4
    连分数 + 200 轮二分;往返测试 test_eval_model.py::test_beta_ppf_roundtrip)。
    """
    if n <= 0:
        return (None, None)
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else beta_ppf(k, n - k + 1, tail)
    hi = 1.0 if k == n else beta_ppf(k + 1, n - k, 1.0 - tail)
    return (lo, hi)


def _zero_event_upper(k: int, n: int, level: float = CP_LEVEL):
    """零事件精确上界(仅 k==0 有值;消费面注记字段,数值即 cp95.hi)。"""
    if n <= 0 or k != 0:
        return None
    return 1.0 - ((1.0 - level) / 2.0) ** (1.0 / n)


def _group_accusers(ca: dict, ctype: str) -> dict:
    """单分类组指控池重算(生产 _merge 同款,agg_share.py:49-66 先例):
    同源取 max 系数 → dedup_lineage(谱系去重防镜像回声双计,宁少算)。
    raw_accusers = 原始指控 detail 三元组原样留痕(无损红线);pool =
    dedup 后证人集(读数口径)。"""
    by_source: dict[str, float] = {}
    raw: list[dict] = []
    for d in ca.get("details") or ():
        if d.get("verdict") not in _ACCUSING:
            continue
        src = d.get("source")
        if not src:
            continue
        c = coefficient(d.get("reliability", 0.5), d.get("first_seen"), ctype)
        if src not in by_source or c > by_source[src]:
            by_source[src] = c
        raw.append(d)
    deduped = dedup_lineage(sorted(by_source.items()))
    return {"type": ctype, "group_verdict": ca.get("verdict"),
            "conflict": bool(ca.get("verdict_conflict")),
            "raw_accusers": raw, "pool": [s for s, _ in deduped]}


def clean_anchor_fp(lookup_fn, anchors=ANCHORS) -> dict:
    """读数A:全部 expect=clean 锚的被控率(census N 全量,非采样)。

    单个 lookup 失败原样上抛,不 except-continue(2026-10-10 假零判例)。
    被控判定 = 分类组级 verdict ∈ _ACCUSING(与 anchors._check 判定门
    同一单源口径;anchor_sweep 的裸 detail 集合是巡检留痕面,本读数走
    生产合并语义)。

    活体首例留痕(dev 数据 2026-10-28,成因三分类均待人裁,报告同批):
    ①193.0.14.129 k.root = cps_collected_iocs(114DNS 事故同源聚合器;
    T1 预检门发现,用户裁决挂起);②223.5.5.5 AliDNS = tweetfeed 众包
    单推指控(reporter+推文 URL 在 raw_accusers.extra,教科书真误列
    候选;生产形状另含 infra_services 良性断言 conflict 面,dev 库
    未装时 conflict=False 是数据条件非逻辑缺失)。单测用确定性
    fixture 钉形状(照 T2 测试先例),不断言活数据。"""
    clean = [(ip, exp) for ip, exp in anchors if exp == "clean"]
    accused: list[dict] = []
    for ip, _exp in clean:
        payload = lookup_fn(ip)
        groups = [_group_accusers(ca, ctype)
                  for ctype, ca in sorted(
                      (payload.get("classifications") or {}).items())
                  if ca.get("verdict") in _ACCUSING]
        if groups:
            accused.append({
                "ip": ip, "expect": "clean",
                "accusers": sorted({s for g in groups for s in g["pool"]}),
                "groups": groups,
            })
    n, k = len(clean), len(accused)
    lo, hi = clopper_pearson(k, n)
    return {
        "kind": "clean_anchor_fp",
        "n": n, "k": k,
        "fp_rate": (k / n) if n else None,
        "cp95": {"level": CP_LEVEL, "lo": lo, "hi": hi},
        "zero_event_upper_95": _zero_event_upper(k, n),
        "members": [ip for ip, _ in clean],       # census 成员清单随件
        "accused": accused,
        "cause_taxonomy": {"classes": list(_CAUSE_TAXONOMY),
                           "note": _TAXONOMY_NOTE},
        "note": _HADES_NOTE,
    }


def _parses_v4(prefix: str) -> bool:
    """membership 自证用:可解析且 v4 才入 apply_scanner_filter 输入
    (坏 token/v6 在采样侧已计数,不静默缩水也不重复炸)。"""
    try:
        return ipaddress.ip_network(prefix, strict=False).version == 4
    except ValueError:
        return False


def sample_segment_members(prefixes, *, n: int = SCANNER_PROBE_N,
                           seed_name: str = SCANNER_PROBE_SEED_NAME) -> dict:
    """自报段 v4 成员稳定采样:census 参数(N/seed/成员清单)随件返回。

    - 成员判定照 truth_layer 机制:前缀归一成 (start, end) 区间,排序
      合并重叠/相邻后按累计容量 bisect 采样——O(K log K) 一次合并 +
      每抽样 O(log K),勿写成逐前缀 in 判(29k CIDR × N 次判例禁止)。
    - v4/v6 混排值域天然分离:采样面只取 v4(corpus v4 纪律),v6 与坏
      token 计数入 census 不静默缩水(「坏快照不许静默缩水」哲学)。
    - seed = stable_seed(seed_name)(per-source 纪律,probe_ips 同款):
      同输入同输出,跨进程可复算(PYTHONHASHSEED 无关)。
    - membership_check:抽样结果过一遍 apply_scanner_filter(§3 公共
      判定路径,仅可解析前缀)自证全落段内——防御性不变量,失配即抛
      (不出假读数)。
    """
    n_v4 = n_v6 = n_bad = 0
    prefixes = list(prefixes)          # 只迭代一次:len() 与 membership 自证共用
    nets = []
    for p in prefixes:
        try:
            net = ipaddress.ip_network(p, strict=False)
        except ValueError:
            n_bad += 1
            continue
        if net.version == 4:
            n_v4 += 1
            nets.append(net)
        else:
            n_v6 += 1
    merged: list[tuple[int, int]] = []
    for s, e in sorted((int(x.network_address), int(x.broadcast_address))
                       for x in nets):
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    cum, acc = [], 0
    for s, e in merged:
        acc += e - s + 1
        cum.append(acc)
    total = acc
    rng = random.Random(stable_seed(seed_name))
    probes: list[str] = []
    seen: set[str] = set()
    want = min(n, total)
    while len(probes) < want:
        r = rng.randrange(total)
        i = bisect_right(cum, r)
        base = merged[i][0] + (r - (cum[i - 1] if i else 0))
        ip = str(ipaddress.IPv4Address(base))
        if ip in seen:
            continue
        seen.add(ip)
        probes.append(ip)
    if probes:
        good = [p for p in prefixes if _parses_v4(p)]
        kept, dropped = apply_scanner_filter(probes, good)
        if dropped != len(probes) or kept:
            raise RuntimeError(
                "segment sampler invariant broken: probe outside prefixes")
    return {
        "probes": probes,
        "n_prefixes": len(prefixes),
        "n_v4": n_v4, "n_v6": n_v6, "n_bad": n_bad,
        "v4_covered_addresses": total,
        "probe_n_cap": n,
        "seed": stable_seed(seed_name), "seed_name": seed_name,
        "membership_check": "pass" if probes else "skip(no-v4-universe)",
    }


def scanner_recall(lookup_fn, prefixes, *, n: int = SCANNER_PROBE_N) -> dict:
    """读数B:自报段成员召回率(leave-out 排除 scanner_ranges 自证)。

    分子 = 被 ≥1 非 scanner_ranges 指控源命中的探针成员;self_echo 留痕
    (scanner_ranges 自证在场性,审计 leave-out 是否真在排)。单个 lookup
    失败原样上抛(假零判例)。"""
    census = sample_segment_members(prefixes, n=n)
    probes = census["probes"]
    members: list[dict] = []
    n_self_echo = 0
    k_hit = 0
    for ip in probes:
        payload = lookup_fn(ip)
        pools: dict[str, list[str]] = {}
        self_echo = False
        for ctype, ca in sorted(
                (payload.get("classifications") or {}).items()):
            if ca.get("verdict") not in _ACCUSING:
                continue
            g = _group_accusers(ca, ctype)
            pools[ctype] = g["pool"]
            for d in g["raw_accusers"]:
                if d.get("source") == LEAVE_OUT:
                    self_echo = True
        accusers = sorted({s for pool in pools.values() for s in pool
                           } - {LEAVE_OUT})
        if accusers:
            k_hit += 1
        if self_echo:
            n_self_echo += 1
        members.append({"ip": ip, "hit": bool(accusers),
                        "self_echo": self_echo, "accusers": accusers})
    n_probe = len(probes)
    lo, hi = clopper_pearson(k_hit, n_probe)
    return {
        "kind": "scanner_recall",
        "status": "ok",
        "leave_out": LEAVE_OUT,
        "n_probe": n_probe, "k_hit": k_hit,
        "recall": (k_hit / n_probe) if n_probe else None,
        "cp95": {"level": CP_LEVEL, "lo": lo, "hi": hi},
        "zero_event_upper_95": _zero_event_upper(k_hit, n_probe),
        "n_self_echo": n_self_echo,
        "census": census,                      # N/seed/成员清单随件
        "members": members,                    # per-成员命中明细留痕
        "note": (_HADES_NOTE + "; truth = vendor self-reported segments "
                 "(scanner_ranges); recall measures pool sensitivity to "
                 "known scanners — never seen = blind-spot evidence; "
                 "SANS ISC 观测佐证=v1(其 shodan 列表实测混 Rapid7 Sonar "
                 "段,带污染注记,ADR 0013 采纳排序)"),
    }


def run_anchor_readouts(registry, out_dir=None, *,
                        eval_env: str | None = None) -> dict:
    """CLI 装配:双读数 + 落 <out_dir>/model/anchor-fp-<ts>.json 与
    scanner-recall-<ts>.json(anchors/agg-share 报告族同形,另注 eval_env+
    generated_at 两加性键(T3 评审 P2 注记;agg-share/sinkhole-probe 裸 res
    不带——族内两种信封并存,消费面按键取值不破),ts 形制
    %Y%m%d-%H%M%S)。scanner_ranges 源不在册或 CSV 缺失 → 读数B 显式
    缺层(status=missing,recall=None)不报 0(票 #233 验收:零数据=
    显式缺层);读数A 照常(锚表在代码内,不依赖数据面)。只测量不持门:
    异常原样上抛,无退出码语义。"""
    res_fp = clean_anchor_fp(registry.lookup)
    src = next((s for s in registry.sources
                if getattr(s, "name", None) == LEAVE_OUT), None)
    path = getattr(src, "_path", None)
    if path is not None and Path(path).is_file():
        res_recall = scanner_recall(registry.lookup,
                                    scanner_ranges_prefixes(Path(path)))
    else:
        res_recall = {
            "kind": "scanner_recall", "status": "missing",
            "leave_out": LEAVE_OUT, "n_probe": 0, "k_hit": 0,
            "recall": None, "cp95": {"level": CP_LEVEL, "lo": None,
                                     "hi": None},
            "zero_event_upper_95": None,   # schema 与 ok 形状同键集(稳定)
            "n_self_echo": 0, "census": None, "members": [],
            "note": ("scanner_ranges CSV absent — explicit missing layer, "
                     "not a zero readout (票 #233 验收); " + _HADES_NOTE),
        }
    if out_dir is not None:
        if eval_env is None:
            from .__main__ import eval_env as _current_env
            eval_env = _current_env()
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        for name, res in (("anchor-fp", res_fp),
                          ("scanner-recall", res_recall)):
            (d / f"{name}-{ts}.json").write_text(json.dumps(
                {**res, "eval_env": eval_env,
                 "generated_at": _dt.datetime.now(
                     _dt.timezone.utc).date().isoformat()},
                ensure_ascii=False, indent=1, default=str),
                encoding="utf-8")
    return {"clean_anchor_fp": res_fp, "scanner_recall": res_recall}
