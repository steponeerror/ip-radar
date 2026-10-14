# backend/ipdb/_eval/gate.py
"""接入关运行器(Q4 双口径, spec 2026-10-12-eval-loop-hardening-design.md
§3.1): 一次候选源完整评估, 报告双口径分节显式作答。

「candidate-stratum 自域判别力」与「四层舰队净影响」是两个问题(演示 B
判例, spec §3.1 双口径并报), 各答各节; 交付物 = 分层向量 + verdict 8 态
透传, 任何层/总都不产单一综合分(F1)。

- ① candidate-stratum: 复用 __main__.run_for_source(消融 + 8 态 verdict
  + 逐源报告, Phase 1 落地件原样; call-time 懒导入避 T9 CLI 接线的
  __main__→gate 循环, suite.write_model_report 同款纪律)。
- ② 四层 ON/OFF 两臂: 同一 assets_dir 两次装配(同语料)、同一 run_seed
  (Q14: delta 才是配对读数, 非两独立样本差); 共识层装配后剔除候选键集
  贡献 —— spec §2.3 装配两场景: gate=排除候选, 月轮=全舰队
  (run_readout 不剔, 固有循环语义由月报注记)。选「装配后剔除」而非给
  assemble_four_layers 加 exclude 参数: 共识资产是逐源采样并集, 成员
  归属仅在构建期可知, 按候选键集求交剔除是不动 Phase 1 装配件的最小
  路径; 宁少算 —— 与他源重叠的候选键集 IP 一并剔(在场性证据不可拆分,
  不猜归属)。
- ③ 逐层 paired_bootstrap(on/off hits)+ McNemar(T7 落地件); bootstrap
  全层共用 run_seed: 配对单位逐层不同(各层各 IP), 同 stream 无共噪声
  之虞, 且留 Q14 maxT 共重抽样通道。
- ④ k 族 delta: k_all / k_nonhoneypot 直方图位移(照 Phase 1
  layered_readout 落地形态, 描述性, 不做检验)。
- ⑤ gate-<candidate>-<ts>.md/.json 落 out_dir; eval_env=gate 强制
  (S37 fail-loud: 显式 monthly/dev 下跑 gate 拒绝 —— 环境标签错位会令
  rc_history/报告目录跨 env 混读; 未设 → 进程内钉 gate, 退出还原)。
- ⑥ T6 触发集接线 + conf 档诊断列(spec §3.1/§8 S1-S4/S31):
  evaluate_triggers(triggers.py T5 落地件, 只升旗零写路径)消费键在
  gate 组装 —— truth 资产成员(S1)/蜜罐声明(源类属性 + config 兜底,
  layered 同款读侧合并)/oc(stratum metrics)/unique_share(suite
  model 落地口径)/derived(源类属性, R1-F1); 输出 mandatory_review/
  bands 旗标行进报告「强制人裁」「OC 敏感带」两节。conf 阈值档
  (70, 90, yardstick 实测先例)消融读数自两臂 F10 快照再生(S29),
  诊断列不入读数家族(S31)。

读数家族(F9 显式枚举, 报告头携带): 假设检验族 = 四层命中率 delta ×4;
描述族 = candidate 自域指标族(run_for_source 全套)+ k 族位移 ×2;
conf 档不入家族(S31: 控 FDR 预算, T6 展开为接入关消融诊断列)。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
from dataclasses import asdict
from pathlib import Path

from . import config
from .assets import load_asset
from .keysets import _source_ips
from .layered import (PRIORITY, STATUS_OK, LayerResult, assemble_four_layers,
                      layered_readout)
from .significance import mcnemar, paired_bootstrap
from .snapshots import load_ip_snapshot
from .triggers import evaluate_triggers
from .._types import _ACCUSING

_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parents[2]
# 缺省与 run_readout 同一资产根: 语料/键集是事实不是报告, 跨 env 共享
# (spec §4.2); gate 只消费不重建(月轮 build_all_monthly 的职责, S22
# 冻结时点)。
_DEFAULT_ASSETS = _REPO_ROOT / "backend" / "data" / "eval" / "assets"
_ENV_KEY = "IP_RADAR_EVAL_ENV"

# F9 读数家族枚举(单一真源, md 头与 JSON 同源渲染)
FAMILIES = {
    "hypothesis_tested": ["layer_delta:truth", "layer_delta:infra",
                          "layer_delta:neutral", "layer_delta:consensus"],
    "descriptive": [
        "candidate_stratum: MC/CG/conflict/oc/dead_slot_fill/"
        "confidence_uplift/fp/other(run_for_source 全套)",
        "k_family: k_all 直方图位移(逐层)",
        "k_family: k_nonhoneypot 直方图位移(逐层)",
    ],
    # S31: conf 档不入读数家族(控 FDR 预算); T6 展开为接入关消融诊断列
    "excluded": ["conf 档(S31, T6 展开为消融诊断列)"],
}

# S31 conf 阈值档 = 诊断列档位: 照 Phase 1 yardstick 实测先例
# (docs/research/2026-10-12-yardstick-feasibility.md §二: ≥70 与 ≥90 双档
# 读数形态; §四: conf≥70 回归基线; C3 旧分口径同为 70)。诊断列, 不入
# FAMILIES(控 FDR 预算), 描述性不做检验。
CONF_TIERS = (70, 90)


def _strip_candidate(consensus: LayerResult, keyset: set[str]) -> int:
    """共识层 gate 场景(spec §2.3): 装配后剔除候选键集贡献, 返回剔除数。

    路径选择与宁少算口径见模块 docstring; 剔除记入 LayerResult.notes →
    两臂 intersection_audit 可见(报告可回算)。剔光 → members=[] 且
    rate=None(layered "empty after overlap removal" 同款哨兵)。
    """
    if consensus.status != STATUS_OK:
        return 0
    kept = [ip for ip in consensus.members if ip not in keyset]
    n = len(consensus.members) - len(kept)
    if n:
        consensus.members = kept
        consensus.notes.append(
            f"gate scenario: excluded {n} candidate-keyset ips "
            "(gate=排除候选; monthly=全舰队, spec §2.3)")
    return n


def _arm_layers(assets_root: Path, keyset: set[str]):
    """单臂装配 = assemble_four_layers + 共识剔除候选(两臂各调一次:
    layered_readout 回填 LayerResult, 每臂须独立对象)。"""
    layers = assemble_four_layers(assets_root)
    excluded = _strip_candidate(layers["consensus"], keyset)
    return layers, excluded


def _truth_asof(assets_root: Path, layers) -> float | None:
    """F2 执行锚(run_readout 同款纪律): decay 求值时钟锚定语料装配时点。

    truth 层 OK → 锚 = truth 资产 created_at; NO-LAYER → None 走普通
    查询(不虚构锚)。两臂同资产 → 同锚。
    """
    if layers["truth"].status != STATUS_OK:
        return None
    _, meta = load_asset(Path(assets_root) / "truth")
    created = _dt.datetime.fromisoformat(meta.created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=_dt.timezone.utc)
    return created.timestamp()


def _hist_mean(hist: dict) -> float | None:
    """直方图均值 = 命中 IP 的平均 k; 零命中 → None(无定义, 不冒充 0)。"""
    total = sum(hist.values())
    return sum(int(k) * c for k, c in hist.items()) / total if total else None


def _k_delta(on_hist: dict, off_hist: dict) -> dict:
    """k 族直方图位移(④): 两臂直方图 + 逐 k 差 + 命中均值位移。

    描述性, 不做检验(假设检验族 = 命中率 delta, F9 枚举); 任一臂零命中
    → mean_delta=None(哨兵纪律)。
    """
    m_on, m_off = _hist_mean(on_hist), _hist_mean(off_hist)
    return {
        "on": dict(on_hist), "off": dict(off_hist),
        "delta_hist": {k: on_hist.get(k, 0) - off_hist.get(k, 0)
                       for k in sorted(set(on_hist) | set(off_hist))},
        "mean_delta": (m_on - m_off
                       if m_on is not None and m_off is not None else None),
    }


def _layer_delta(off_lr: LayerResult, off_block: dict,
                 on_lr: LayerResult, on_block: dict, *, seed: int) -> dict:
    """单层两臂配对 delta(③+④)。

    两臂同 assets 装配 → 成员序恒同(sorted); 不一致即证据链断裂, raise
    不静默(配对语义前提, Q14)。n=0(剔光/空资产)→ stats=None: 配对统计
    无定义, 不冒充 0。
    """
    if off_lr.members != on_lr.members:
        raise ValueError(
            "paired arms must share identical layer members "
            f"(got {len(off_lr.members)} vs {len(on_lr.members)})")
    on_set, off_set = set(on_lr.hit_members), set(off_lr.hit_members)
    stats = None
    if off_lr.members:
        on_hits = [ip in on_set for ip in off_lr.members]
        off_hits = [ip in off_set for ip in off_lr.members]
        stats = {
            "paired_bootstrap": paired_bootstrap(on_hits, off_hits, seed=seed),
            "mcnemar": mcnemar(on_hits, off_hits),
        }
    return {
        "n": len(off_lr.members),
        "off_hits": len(off_set), "on_hits": len(on_set),
        "rate_off": off_lr.rate, "rate_on": on_lr.rate,
        "rate_delta": (on_lr.rate - off_lr.rate
                       if on_lr.rate is not None and off_lr.rate is not None
                       else None),
        "stats": stats,
        "k_all": _k_delta(on_block["k_all"], off_block["k_all"]),
        "k_nonhoneypot": _k_delta(on_block["k_nonhoneypot"],
                                  off_block["k_nonhoneypot"]),
    }


def _conf_tier_hits(rows: dict, tier: int) -> int:
    """F10 快照行 → conf≥tier 命中 IP 数。指控判定 = 分组 verdict ∈
    _ACCUSING(layered._accusing_types 同口径), conf 取指控组 max ——
    「最坏 verdict 组内 max 置信度」(yardstick 旧分语义同形); 无指控组
    → 非命中(宁少算; 缺 confidence 兑底 0 = metrics.confidence_uplift
    同字段同兑底)。"""
    n = 0
    for row in rows.values():
        confs = [ca.get("confidence", 0)
                 for ca in (row.get("classifications") or {}).values()
                 if ca.get("verdict") in _ACCUSING]
        if confs and max(confs) >= tier:
            n += 1
    return n


def _conf_tier_deltas(out_dir: Path, run_id: str, layers: dict) -> dict:
    """per-conf 档消融诊断列(S31): 逐层 × conf 阈值档的两臂命中读数。

    数据自两臂 F10 快照再生(S29: 子读数免重查引擎, 证据已落盘; 两臂
    成员恒同 = Q14 配对前提, _layer_delta 已验)。NO-LAYER 层 None
    (缺层≠0 层); n=0 层率值 None(哨兵纪律, 不冒充 0)。描述性, 不做
    检验, 不入 F9 读数家族(S31 控 FDR 预算)。"""
    out: dict[str, dict | None] = {}
    for kind in PRIORITY:
        lr = layers[kind]
        if lr.status != STATUS_OK:
            out[kind] = None
            continue
        n = len(lr.members)
        snap_dir = Path(out_dir) / "snapshots"
        off_rows = load_ip_snapshot(snap_dir / f"{run_id}-off"
                                    / f"{kind}.jsonl.gz")
        on_rows = load_ip_snapshot(snap_dir / f"{run_id}-on"
                                   / f"{kind}.jsonl.gz")
        tiers = {}
        for tier in CONF_TIERS:
            h_off, h_on = (_conf_tier_hits(off_rows, tier),
                           _conf_tier_hits(on_rows, tier))
            r_off = h_off / n if n else None
            r_on = h_on / n if n else None
            tiers[str(tier)] = {
                "off_hits": h_off, "on_hits": h_on,
                "rate_off": r_off, "rate_on": r_on,
                "rate_delta": (r_on - r_off
                               if r_on is not None and r_off is not None
                               else None),
            }
        out[kind] = {"n": n, "tiers": tiers}
    return out


def _candidate_unique_share(src_obj, reg, run_seed: int,
                            corpus_path) -> float | None:
    """S2 象限臂输入: 候选独有命中占比 —— suite/model 落地口径原样
    (SourceScore.unique_share = 自有非垄断 pair 中无他源同指的份额,
    model.estimate; suite model 件同源字段, T5 契约注明消费源)。

    语料与 run_for_source 同 seed 重构(sample_source_ips 的 run_seed
    覆盖 rng, S36: 同 run_seed + 同源文件 → 同 candidate_ips), 候选 ON
    态全语料快照 → source_pair_sets → extract_events → estimate 与
    run_suite 同链, 不另立口径。引擎零改动红线(run_for_source 不回传
    快照)下重查一次语料(数百次 mmap lookup)是接线的最小代价。
    """
    from .ablation import take_snapshot
    from .corpus import Corpus, sample_source_ips
    from .events import extract_events
    from .model import estimate
    from .pairwise import pairwise_oc, source_pair_sets
    corpus = (Corpus.load(corpus_path) if Path(corpus_path).exists()
              else Corpus())
    corpus.candidate_ips = sample_source_ips(
        src_obj, config.CORPUS_CANDIDATE_N, run_seed=run_seed)
    snap = take_snapshot(reg.lookup, corpus.all_ips())
    pair_sets = source_pair_sets(snap)
    events = extract_events(snap, pairwise_oc(pair_sets))
    return next((s.unique_share for s in estimate(events)
                 if s.source == src_obj.name), None)


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.4f}"


def _hist_repr(h: dict) -> str:
    return "{" + ", ".join(f"{k}:{h[k]}" for k in sorted(h)) + "}"


def _delta_repr(d: dict) -> str:
    return "{" + ", ".join(f"{k}:{d[k]:+d}" for k in sorted(d)) + "}"


def _layer_row(kind: str, delta) -> list[str]:
    if delta is None:
        return [kind, "NO-LAYER", "—", "—", "—", "缺层≠0 层(§2.3 哨兵)", "—"]
    b = delta["stats"]["paired_bootstrap"] if delta["stats"] else None
    m = delta["stats"]["mcnemar"] if delta["stats"] else None
    boot = (f"Δ={_fmt(b['delta'])} [{_fmt(b['ci_lo'])}, {_fmt(b['ci_hi'])}] "
            f"p1={_fmt(b['p_one_sided'])}" if b else "n=0 无定义")
    mcn = f"b={m['b']}/c={m['c']} p={_fmt(m['p'])}" if m else "—"
    return [kind, str(delta["n"]),
            f"{delta['off_hits']} ({_fmt(delta['rate_off'])})",
            f"{delta['on_hits']} ({_fmt(delta['rate_on'])})",
            _fmt(delta["rate_delta"]), boot, mcn]


def _render_md(candidate: str, verdict: dict, metrics: dict, deltas: dict,
               excluded_n: int, keyset_n: int, run_seed: int,
               assets_root: Path, trig: dict, conf_tiers: dict) -> str:
    """gate 报告 md: 头部(种子/两场景/F9 家族)+ 双口径两节(演示 B 措辞)
    + 强制人裁/OC 敏感带/conf 档诊断列(T6, S1-S4/S31)。

    禁综合分(F1): 全文无任何单一总分; 只有分层向量行与 verdict 原文。
    零旗标也显式留哨兵行(无旗 ≠ 无话: 人裁面须能区分「未触发」与
    「未评估」)。"""
    lines = [
        f"# 接入关 gate: `{candidate}`(eval_env=gate)",
        "",
        f"- run_seed={run_seed};双臂同一语料资产({assets_root})+ 同一 seed"
        "(Q4/Q14:ON/OFF delta 是配对读数, 不是两独立样本的差)",
        f"- 共识装配两场景(spec §2.3):gate=排除候选(剔除 {excluded_n}/"
        f"{keyset_n} 候选键集 IP);月轮=全舰队(固有循环语义, 月报注记承载)",
        "- 读数家族(F9 枚举):假设检验族 = 四层命中率 delta ×4"
        "(paired bootstrap+McNemar);描述族 = candidate 自域指标族 + "
        "k 族 delta(k_all/k_nonhoneypot 直方图位移);"
        "conf 档不入家族(S31,T6 展开为消融诊断列)",
        "",
        "## ① candidate-stratum 自域判别力",
        "",
        "演示 B 判例:candidate-stratum 自域判别力与四层舰队净影响是两个"
        "问题,本节只答前者 —— 候选在自域语料上搬动了什么。",
        "",
        f"**Verdict: {verdict['state']}**(8 态透传)",
        "",
        f"> {verdict['action']}",
        "",
        "| Metric | Value | n |",
        "|---|---|---|",
    ]
    for name, m in metrics.items():
        lines.append(f"| {name} | {m['value']:.4f} | {m['n']} |")
    lines += [
        "",
        "## ② 四层舰队净影响(ON/OFF 配对 delta)",
        "",
        "演示 B 判例的另一问:加入候选后,四层各自命中率与 k 族移动了多少"
        "(共识层语料已排除候选自身, 见头部两场景注记)。",
        "",
        "| layer | n | OFF hits (rate) | ON hits (rate) | rate Δ | "
        "paired bootstrap | McNemar |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in PRIORITY:
        lines.append("| " + " | ".join(_layer_row(kind, deltas.get(kind))) + " |")
    lines += ["", "### k 族 delta(直方图位移, 描述性)", ""]
    for kind in PRIORITY:
        d = deltas.get(kind)
        if d is None:
            lines.append(f"- {kind}: NO-LAYER(缺层≠0 层)")
            continue
        for fam in ("k_all", "k_nonhoneypot"):
            k = d[fam]
            md_ = "—" if k["mean_delta"] is None else f"{k['mean_delta']:+.4f}"
            lines.append(
                f"- {kind} {fam}:ON {_hist_repr(k['on'])} / OFF "
                f"{_hist_repr(k['off'])} → 位移 {_delta_repr(k['delta_hist'])}"
                f"(均值 Δ {md_})")
    # T6「强制人裁」节(R2 基础三态 + S1-S4, spec §3.1): 只升旗不自动动作
    lines += [
        "",
        "## 强制人裁(R2 基础三态 + S1-S4, spec §3.1)",
        "",
        "触发集只升旗不自动动作(声明 r: 测量建言, 人裁终局);处置归人,",
        "接入关报告必附 PR。",
        "",
    ]
    lines += [f"- {row}" for row in trig["mandatory_review"]] or [
        "- 无强制人裁旗标(基础三态与 S1-S4 本轮均未触发)。"]
    # T6「OC 敏感带」节(S3, report-only: 报告不触发)
    lines += ["", "## OC 敏感带(S3, report-only)", ""]
    lines += [f"- {row}" for row in trig["bands"]] or [
        "- 无敏感带标注(OC 不在 [0.7, 0.9) 或本轮无 OC 读数)。"]
    # T6 conf 档消融诊断列(S31: 诊断列, 不入读数家族 —— 家族枚举见头部
    lines += [
        "",
        "## conf 档消融诊断列(S31: 诊断列, 不入读数家族)",
        "",
        f"档位照 Phase 1 yardstick 实测先例(conf≥{CONF_TIERS[0]} / "
        f"conf≥{CONF_TIERS[-1]}, docs/research/2026-10-12-yardstick-"
        "feasibility.md);自两臂 F10 快照再生(S29),描述性读数,不做检验,",
        "不扩 F9 读数家族(控 FDR 预算)。",
        "",
        "| layer | n | tier | OFF hits (rate) | ON hits (rate) | rate Δ |",
        "|---|---|---|---|---|---|",
    ]
    for kind in PRIORITY:
        ct = conf_tiers.get(kind)
        if ct is None:
            lines.append(f"| {kind} | — | NO-LAYER | 缺层≠0 层(§2.3 哨兵) "
                         "| — | — |")
            continue
        for tier, r in ct["tiers"].items():
            lines.append(
                f"| {kind} | {ct['n']} | conf≥{tier} | "
                f"{r['off_hits']} ({_fmt(r['rate_off'])}) | "
                f"{r['on_hits']} ({_fmt(r['rate_on'])}) | "
                f"{_fmt(r['rate_delta'])} |")
    lines += [
        "",
        "_测量建言, 人裁终局(声明 r);接入关报告必附 PR(spec §3.1)。_",
        "_禁综合分(F1):任何层/总均无单一综合分;verdict 8 态原样透传。_",
    ]
    return "\n".join(lines) + "\n"


def run_gate(candidate: str, reg, out_dir: Path, *,
             run_seed: int | None = None, assets_dir=None,
             benign=None) -> dict:
    """接入关主入口(spec §3.1): ①自域 + ②四层两臂 + ③④delta + ⑤报告。

    返回报告 payload(附 report 路径); 两臂同 assets 同 run_seed, 共识层
    gate 场景排除候选。eval_env=gate 强制(S37 fail-loud): 显式 monthly/
    dev → raise; 未设 → 进程内钉 gate 并在退出还原(嵌套 run_for_source
    的报告标签与 rc_history 随之归 gate 命名空间)。benign 为测试缝
    (run_for_source 同款 DI: 注入假 checker 免真 warninglists 加载)。
    """
    prev = os.environ.get(_ENV_KEY)
    if prev not in (None, "gate"):
        raise ValueError(
            f"{_ENV_KEY}={prev!r}: gate must run in env 'gate' (S37 fail-loud)")
    if prev is None:
        os.environ[_ENV_KEY] = "gate"
    try:
        return _run_gate(candidate, reg, out_dir, run_seed=run_seed,
                         assets_dir=assets_dir, benign=benign)
    finally:
        if prev is None:
            del os.environ[_ENV_KEY]


def _run_gate(candidate: str, reg, out_dir, *, run_seed, assets_dir, benign):
    from .__main__ import CORPUS_PATH, run_for_source  # 懒导入避 T9 CLI 循环(见 docstring)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # S36: run 级 seed 显式随机缺省, 两臂/自域/自举共用一个 run_seed
    run_seed = secrets.randbits(64) if run_seed is None else run_seed
    src_obj = next((s for s in reg.sources if s.name == candidate), None)
    if src_obj is None:
        raise ValueError(f"no source named {candidate!r} in reg.sources")
    corpus_path = CORPUS_PATH

    # ① candidate-stratum 自域判别力(run_for_source 复用: 消融+8态+报告)
    _, js1, verdict = run_for_source(
        candidate, registry=reg, out_dir=out, benign=benign, run_seed=run_seed)
    stratum = json.loads(Path(js1).read_text(encoding="utf-8"))

    # ② 四层两臂: OFF(基线)→ON; finally 复启(run_ablation 同款纪律)
    assets_root = Path(assets_dir) if assets_dir else _DEFAULT_ASSETS
    keyset = set(_source_ips(src_obj))
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"gate-{candidate}-{ts}"
    try:
        reg.toggle(candidate, False)
        off_layers, excluded = _arm_layers(assets_root, keyset)
        off = layered_readout(reg.lookup, off_layers, out_dir=out,
                              run_id=f"{run_id}-off",
                              asof=_truth_asof(assets_root, off_layers),
                              sources=reg.sources)
        reg.toggle(candidate, True)
        on_layers, _ = _arm_layers(assets_root, keyset)
        on = layered_readout(reg.lookup, on_layers, out_dir=out,
                             run_id=f"{run_id}-on",
                             asof=_truth_asof(assets_root, on_layers),
                             sources=reg.sources)
    finally:
        reg.toggle(candidate, True)

    # ③④ 逐层配对 delta + k 族位移(NO-LAYER 层无 delta: 缺层≠0 层)
    deltas: dict[str, dict | None] = {}
    for kind in PRIORITY:
        off_lr, on_lr = off_layers[kind], on_layers[kind]
        if off_lr.status != STATUS_OK or on_lr.status != STATUS_OK:
            deltas[kind] = None
            continue
        deltas[kind] = _layer_delta(
            off_lr, off["layers"][kind], on_lr, on["layers"][kind],
            seed=run_seed)

    # ⑥a per-conf 档消融诊断列(S31): 自两臂 F10 快照再生, 不查引擎
    conf_tiers = _conf_tier_deltas(out, run_id, off_layers)

    # ⑥b 触发集接线(S1-S4 + R2 基础三态, T5 契约键在 gate 组装):
    # 大列表(键集/truth 成员)只在内存装配, JSON 件只落计数与标量 ——
    # 大源键集 10^5-10^6 IP 会把报告件撑到 MB 级, T4 payload 纪律 =
    # 聚合 + 指针(assets_dir 可回算; 旗标行自身携带观测值)。
    truth_lr = off_layers["truth"]
    truth_members = (truth_lr.members if truth_lr.status == STATUS_OK
                     else None)   # NO-LAYER → None: S1 缺键不评(宁少算)
    # 蜜罐声明读侧合并 = layered 同款(源类属性优先, config 集兜底收敛漏报)
    honeypot_declared = (bool(getattr(src_obj, "honeypot_methodology", False))
                         or candidate in config.HONEYPOT_METHODOLOGY)
    # 谱系声明 = 源类属性 derived(registry R1-F1: 导入时 fill-in-place
    # 灌装 DERIVED_SOURCES, 属性即声明本体)
    declared_derived = bool(getattr(src_obj, "derived", False))
    oc_val = ((stratum.get("metrics") or {}).get("oc") or {}).get("value")
    unique_share = _candidate_unique_share(src_obj, reg, run_seed,
                                           corpus_path)  # 候选 ON 态(两臂后)
    trig_raw = evaluate_triggers({
        "candidate_stratum": {"verdict": asdict(verdict)},
        "deltas": deltas,
        "candidate_keyset": sorted(keyset),
        "truth_members": truth_members,
        "honeypot_declared": honeypot_declared,
        "oc": oc_val,
        "unique_share": unique_share,
        "declared_derived": declared_derived,
    })
    trig = {"mandatory_review": trig_raw["mandatory_review"],
            "bands": trig_raw["bands"],
            "inputs": {
                "candidate_keyset_n": len(keyset),
                "truth_members_n": (len(truth_members)
                                    if truth_members is not None else None),
                "honeypot_declared": honeypot_declared,
                "oc": oc_val,
                "unique_share": unique_share,
                "declared_derived": declared_derived,
            }}

    payload = {
        "kind": "gate",
        "eval_env": "gate",
        "candidate": candidate,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).date().isoformat(),
        "run_seed": run_seed,
        "corpus": {"assets_dir": str(assets_root),
                   "pairing": "same assets + same run_seed (Q14 paired)"},
        "consensus_scenario": {
            "gate": "共识层排除候选(候选键集交集剔除)",
            "monthly": "全舰队(固有循环语义, run_readout 不剔除)",
            "excluded_n": excluded,
            "candidate_keyset_n": len(keyset),
            "spec": "§2.3 装配两场景",
        },
        "candidate_stratum": {"verdict": asdict(verdict),
                              "report": {"json": Path(js1).name}},
        "arms": {"off": off, "on": on},
        "deltas": deltas,
        "families": FAMILIES,
        "triggers": trig,
        "conf_tiers": conf_tiers,
    }
    md_path = out / f"gate-{candidate}-{ts}.md"
    js_path = out / f"gate-{candidate}-{ts}.json"
    md_path.write_text(
        _render_md(candidate, payload["candidate_stratum"]["verdict"],
                   stratum.get("metrics") or {}, deltas, excluded,
                   len(keyset), run_seed, assets_root, trig, conf_tiers),
        encoding="utf-8")
    js_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False,
                                  default=str), encoding="utf-8")
    return {**payload, "report": {"md": str(md_path), "json": str(js_path)}}
