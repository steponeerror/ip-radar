# backend/ipdb/_eval/monthly.py
"""月轮报告 v2 组合器 (S28 记分卡 / S30 行动区块 / S24 锚对 OC / S6 年度
递减计数 / S12+S17 换版注记 / Q22 诊断层统计)。

纯函数消费 dicts/file paths, 无引擎/DB 依赖: 四层读数(T8 layered_readout
输出)、R10 披露行(T9)、model-*.json 历史(suite.write_model_report 形状)、
keysets 快照目录(T5)。装配统计(池大小/贡献源/目录形排除/脱同步/池竭
分子分母)由接线方(CLI wiring)以 readout["assembly_stats"] 注入, 本模块
不自行装配。F1 禁综合分: 报告恒为表+行向量, 无任何总分列; 声明 r:
文案不暗示自动动作, 趋势断言仅限指纹未变窗口(S12/S17)。
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .layered import PRIORITY  # 层序真源, 勿手拼

OPEN = "OPEN"
CARRIED = "CARRIED"
DONE = "DONE"

# S30: 规则生成项 deadline = today + 35 天(月轮节奏 + 一周缓冲)
DEADLINE_DAYS = 35
# S30: 诊断层池竭率 >10%(actual < 90% × expected_pool)→ 待办
POOL_EXHAUSTION = 0.10

# S24 两现役锚对(只监测不设门): OC = |A∩B|/min(|A|,|B|)
ANCHOR_PAIRS = (("emerging_threats", "spamhaus"), ("firehol", "greensnow"))

# Q22 诊断层统计行: (stats 键, 中文标签)
_CONSENSUS_KEYS = (
    ("pool", "诊断层池大小"),
    ("contributing_sources", "贡献源数"),
    ("catalog_excluded", "目录形排除"),
    ("desync", "脱同步(预期指控源不再指控)"),
)


@dataclass
class ActionItem:
    """S30 行动区块行项。status ∈ {OPEN, CARRIED, DONE}; DONE 永不再现,
    生成项 id = f"{slug}-{yyyy-mm}"(同月重跑幂等), 上轮携带项 id 保留。"""

    id: str
    title: str
    source: str
    deadline: str
    status: str


def load_dispositions(eval_dir: Path) -> dict[str, str]:
    """读人编 dispositions.json(项 id → "DONE"|"OPEN"|注记字符串; 顶层
    "last_annual_review": "YYYY-MM" 供 S6 递减计数), 缺文件 → {}(无话,
    不发明处置)。"""
    p = Path(eval_dir) / "dispositions.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text())
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _add(items: list[ActionItem], seen: set[str], item: ActionItem) -> None:
    if item.id not in seen:
        seen.add(item.id)
        items.append(item)


def compose_action_block(readout: dict, prev_items: list[ActionItem],
                         dispositions: dict[str, str],
                         today: date) -> list[ActionItem]:
    """S30 状态机 + 规则生成。上轮携带: DONE(项状态或 disposition)→ 消账
    不再现; disposition "OPEN"(人注记保持)→ 保持 OPEN; 其余(含无
    disposition)→ CARRIED, deadline 统一前移 today+35d。

    规则生成(id = slug-yyyy-mm, 同月幂等): 任一层 status != OK(缺层≠
    0 层, title 点名层)、诊断层池竭率 >10%(readout["assembly_stats"]
    {"expected_pool","actual"} 缺席即跳过该规则)、OK 层 k_nonhoneypot
    直方图全 0(有命中但零非蜜罐佐证; 空直方图=零命中, 非此信号)。
    """
    deadline = (today + timedelta(days=DEADLINE_DAYS)).isoformat()
    items: list[ActionItem] = []
    seen: set[str] = set()
    for it in prev_items:
        if it.status == DONE or dispositions.get(it.id) == DONE:
            seen.add(it.id)  # 记 id: 同月仍触发的规则不得复活 DONE 项
            continue
        status = OPEN if dispositions.get(it.id) == OPEN else CARRIED
        _add(items, seen, ActionItem(it.id, it.title, it.source,
                                     deadline, status))
    ym = today.strftime("%Y-%m")
    layers = readout.get("layers", {})
    for kind in PRIORITY:
        block = layers.get(kind) or {}
        if block.get("status") != "OK":
            _add(items, seen, ActionItem(
                f"{kind}-{ym}",
                f"{kind} 层 NO-LAYER(装配哨兵: 缺层≠0 层)", kind,
                deadline, OPEN))
            continue
        k_nh = block.get("k_nonhoneypot") or {}
        if k_nh and set(k_nh) == {0}:
            _add(items, seen, ActionItem(
                f"{kind}-k0-{ym}",
                f"{kind} 层 k_nonhoneypot 全 0(蜜罐外零佐证)", kind,
                deadline, OPEN))
    stats = readout.get("assembly_stats") or {}
    exp, act = stats.get("expected_pool"), stats.get("actual")
    if exp and act is not None and act < (1 - POOL_EXHAUSTION) * exp:
        _add(items, seen, ActionItem(
            f"consensus-pool-{ym}",
            f"诊断层池竭率 >{POOL_EXHAUSTION:.0%}: actual={act} "
            f"< 90%×expected={exp}(Q22)", "consensus", deadline, OPEN))
    return items


def render_scorecard(model_history: list[dict], sources, *,
                     oc_latest: dict[str, float] | None = None,
                     today: date | None = None) -> list[tuple]:
    """S28 记分卡行 (source, θ 档, 冗余度%, 90d 均分, provenance)。

    θ 档: 最新报告(sources[].theta 按 generated_at 取最新)内 movers 按
    θ 降序、按位次四分位 "ABCD"[min(3, 4*i//n)]; 非 movers(pinned/缺席)
    → "—"。90d 均分: generated_at ≥ today-90d 各报告该源非 None θ 的均值
    (report.py 脚注纪律同款 .3f)。冗余度%: oc_latest(源名 → 该源最新
    --all verdict JSON metrics.oc.value, 接线方装配)缺 → "N/A"。
    """
    today = today or date.today()
    hist = sorted(model_history, key=lambda r: r.get("generated_at", ""))
    latest = hist[-1] if hist else {}
    theta_latest = {s.get("source"): s.get("theta")
                    for s in latest.get("scores", [])}
    ranked = sorted(((n, theta_latest[n]) for n in latest.get("movers", [])
                     if theta_latest.get(n) is not None),
                    key=lambda t: (-t[1], t[0]))
    band = ({name: "ABCD"[min(3, 4 * i // len(ranked))]
             for i, (name, _) in enumerate(ranked)} if ranked else {})
    cutoff = (today - timedelta(days=90)).isoformat()
    rows = []
    for s in sources:
        ths = [sc.get("theta")
               for r in hist if r.get("generated_at", "") >= cutoff
               for sc in r.get("scores", [])
               if sc.get("source") == s.name and sc.get("theta") is not None]
        oc = (oc_latest or {}).get(s.name)
        rows.append((
            s.name, band.get(s.name, "—"),
            "N/A" if oc is None else f"{oc * 100:.1f}%",
            f"{sum(ths) / len(ths):.3f}" if ths else "—",
            getattr(s, "provenance_tier", "—")))
    return rows


def render_consensus_diag(stats: dict) -> list[str]:
    """Q22 诊断层统计行: 池大小/贡献源数/目录形排除/脱同步计数; 键缺席
    渲染 "N/A", 不虚构读数(无证据即无话)。"""
    stats = stats or {}
    return [f"- {label}: {stats.get(k) if stats.get(k) is not None else 'N/A'}"
            for k, label in _CONSENSUS_KEYS]


def _latest_keyset_run(kd: Path) -> Path | None:
    """keysets/<run_id>/ 最新轮(按 meta.json date 排序, long_memory_ips
    同款口径); 无轮目录 → None(调用方渲染 N/A, 不炸报告)。"""
    runs = []
    for rd in sorted(kd.iterdir()):
        meta_p = rd / "meta.json"
        if rd.is_dir() and meta_p.is_file():
            runs.append((json.loads(meta_p.read_text()).get("date", ""), rd))
    return max(runs)[1] if runs else None


def _load_keyset(run_dir: Path, name: str) -> set[str] | None:
    p = run_dir / f"{name}.txt.gz"
    if not p.is_file():
        return None
    with gzip.open(p, "rt") as gz:
        ips = {ln for ln in gz.read().splitlines() if ln}
    return ips or None  # 空名单对锚对无信息量, 视同缺失


def render_anchor_oc(keyset_dir: Path) -> list[str]:
    """S24 两现役锚对 OC 行(只监测不设门); 最新轮任一成员名单缺失 →
    "N/A(名单缺失)", 恒不炸报告。"""
    run = _latest_keyset_run(Path(keyset_dir)) if Path(keyset_dir).is_dir() \
        else None
    lines = []
    for a, b in ANCHOR_PAIRS:
        ka = _load_keyset(run, a) if run else None
        kb = _load_keyset(run, b) if run else None
        if ka is None or kb is None:
            lines.append(f"锚对 OC: {a}×{b} = N/A(名单缺失)")
            continue
        oc = len(ka & kb) / min(len(ka), len(kb))
        lines.append(f"锚对 OC: {a}×{b} = {oc:.2f}(只监测不设门)")
    return lines


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)


def _fmt_hist(h) -> str:
    return "—" if not h else ", ".join(f"{k}:{v}" for k, v in h.items())


def compose_monthly_md(readout: dict, disclosures_lines: list[str],
                       action_items: list[ActionItem],
                       scorecard_rows: list[tuple],
                       consensus_diag_lines: list[str],
                       header_meta: dict) -> str:
    """组装月轮报告 v2 markdown。头块 = 环境指纹 + 语料版本/指纹逐层 +
    S12/S17 换版注记(仅指纹实变才出, F2 趋势纪律) + S6 年度递减计数 +
    S30 处置状态汇总 + F7 ε 三档行; 正文 = 分层读数表(T8)/行动区块
    (S30)/R10 混杂披露/记分卡(S28)/诊断层统计(Q22, S24 锚对 OC 行由
    接线方并入 consensus_diag_lines)。F1: 无任何总分列。"""
    lines: list[str] = ["# 月轮读数报告 v2", ""]
    lines.append(f"- 环境指纹(eval_env): {header_meta.get('eval_env', '—')}")
    corpus = header_meta.get("corpus") or {}
    if corpus:
        cells = ", ".join(
            f"{k}={v['version']}/{v['fingerprint']}"
            if isinstance(v, dict) else f"{k}={v}"
            for k, v in corpus.items())
        lines.append(f"- 语料指纹: {cells}")
    prev = header_meta.get("prev_fingerprints") or {}
    changed = [k for k, v in prev.items()
               if isinstance(corpus.get(k), dict)
               and corpus[k].get("fingerprint") not in (None, v)]
    if changed:
        detail = ", ".join(f"{k}: {prev[k]} → {corpus[k]['fingerprint']}"
                           for k in changed)
        lines.append(f"- ⚠ 换版=趋势重置(S12/S17): {detail}"
                     "(趋势断言仅限指纹未变窗口)")
    annual = header_meta.get("annual")
    if annual:
        y, m = (int(x) for x in annual.split("-")[:2])
        t = header_meta.get("today") or date.today()
        months = (t.year - y) * 12 + (t.month - m)
        lines.append(f"- 年度总检(S6): 距上次 {annual} 已 {months} 个月")
    else:
        lines.append("- 年度总检(S6): 未设")
    counts = {s: sum(1 for i in action_items if i.status == s)
              for s in (OPEN, CARRIED, DONE)}
    lines.append(f"- 处置状态(S30): OPEN {counts[OPEN]}"
                 f" / CARRIED {counts[CARRIED]} / DONE {counts[DONE]}")
    eps = header_meta.get("epsilon") or {}
    if eps:
        cells = " / ".join(f"ε={e:.2f} → {v:.4f}"
                           for e, v in sorted(eps.items()))
        lines.append(f"- F7 ε 敏感性(真值层命中率三档): {cells}")

    layers = readout.get("layers", {})
    lines += ["", "## 分层读数(T8)", "",
              "| 层 | 状态 | hits | rate | k_all | k_nonhoneypot |",
              "|---|---|---|---|---|---|"]
    for kind in PRIORITY:
        b = layers.get(kind) or {}
        lines.append(f"| {kind} | {b.get('status', '—')} "
                     f"| {_fmt(b.get('hits'))} | {_fmt(b.get('rate'))} "
                     f"| {_fmt_hist(b.get('k_all'))} "
                     f"| {_fmt_hist(b.get('k_nonhoneypot'))} |")
    lines.append(f"- 仅双派生佐证(F6): "
                 f"{readout.get('derived_only_corroboration', '—')} IP")
    audit = readout.get("intersection_audit") or {}
    if audit:
        cells = ", ".join(f"{k} 剔 {v.get('removed_overlap', 0)}"
                          for k, v in audit.items())
        lines.append(f"- 交集审计: {cells}")
    for kind in PRIORITY:
        b = layers.get(kind) or {}
        if b.get("status") == "OK" and b.get("ctype_mix"):
            lines.append(f"- {kind} ctype_mix: "
                         f"{_fmt_hist(b.get('ctype_mix'))}")

    lines += ["", "## 行动区块(S30)", ""]
    if action_items:
        lines += ["| id | title | source | deadline | status |",
                  "|---|---|---|---|---|"]
        lines += [f"| {i.id} | {i.title} | {i.source} "
                  f"| {i.deadline} | {i.status} |" for i in action_items]
    else:
        lines.append("(无待办项)")

    lines += ["", "## R10 混杂披露(T9)", "", *disclosures_lines]

    lines += ["", "## 记分卡(S28)", "",
              "| source | θ 档 | 冗余度% | 90d 均分 | provenance |",
              "|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |"
              for r in scorecard_rows] or ["| — | — | — | — | — |"]

    lines += ["", "## 诊断层统计(Q22)+ 锚对 OC(S24)", "",
              *consensus_diag_lines]

    # 声明 r(report.py 脚注纪律同款斜体行): 测量建言, 人裁终局
    lines += ["", "_声明 r: 本报告为测量建言,人裁终局;读数不自动触发任何"
              "接入/剔除/调权动作。_",
              "_F1: 读数为表+行向量,无综合总分;趋势仅在语料指纹未变窗口"
              "内解读(F2/S12/S17)。_", ""]
    return "\n".join(lines)
