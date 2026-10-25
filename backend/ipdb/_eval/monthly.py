# backend/ipdb/_eval/monthly.py
"""月轮报告 v2 组合器 (S28 记分卡 / S30 行动区块 / S24 锚对 OC / S34 偷泊
诊断 / S6 年度递减计数 / S12+S17 换版注记(共识代理层滚动豁免) /
Q22 诊断层统计)。

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

# S12/S17 换版=趋势重置注记只辖稳定层(truth/infra/neutral); 共识代理层
# =滚动语料(Q22 诊断层裁决: 月月随键集自然更替, 不做趋势断言)→ 豁免
# 注记, 由 compose_monthly_md 的声明行显式交代(非静默省略)。
RESET_NOTE_KINDS = frozenset({"truth", "infra", "neutral"})

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


def _sorted_runs(kd: Path) -> list[Path]:
    """keysets/<run_id>/ 全部轮按 meta.json date 升序(long_memory_ips
    同款口径; 同日平手按目录名, 确定性)。"""
    runs = []
    for rd in sorted(kd.iterdir()):
        meta_p = rd / "meta.json"
        if rd.is_dir() and meta_p.is_file():
            runs.append((json.loads(meta_p.read_text()).get("date", ""), rd))
    return [rd for _, rd in sorted(runs)]


def _latest_keyset_run(kd: Path) -> Path | None:
    """keysets/<run_id>/ 最新轮(按 meta.json date 排序, long_memory_ips
    同款口径); 无轮目录 → None(调用方渲染 N/A, 不炸报告)。"""
    runs = _sorted_runs(kd)
    return runs[-1] if runs else None


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


def render_steal_parking_diag(keyset_dir: Path) -> list[str]:
    """S34 内容偷泊诊断列: 取最新两轮, 双轮 meta.json counts 同在的源
    逐个比对 —— rc 恒定而键集 symmetric diff 非零 → 偷泊嫌疑行交人裁
    (哲学 5 测量建言, 人裁终局: 只报不判, 不自动触发任何动作)。<2 轮 →
    快照不足行; 成员 gz 缺席(空名单同锚对口径)逐源跳过不炸; 全无可
    比对 → 单行声明。rc 一手读 meta.json counts, 键集一手读 gz, 两手
    各述(证据原样, 不互相回算)。"""
    kd = Path(keyset_dir)
    runs = _sorted_runs(kd) if kd.is_dir() else []
    if len(runs) < 2:
        return ["偷泊诊断: 快照不足(<2 轮)"]
    prev_run, cur_run = runs[-2], runs[-1]
    prev_counts = json.loads(
        (prev_run / "meta.json").read_text()).get("counts", {})
    cur_counts = json.loads(
        (cur_run / "meta.json").read_text()).get("counts", {})
    lines: list[str] = []
    compared = False
    for name in sorted(set(prev_counts) & set(cur_counts)):
        prev_ks = _load_keyset(prev_run, name)
        cur_ks = _load_keyset(cur_run, name)
        if prev_ks is None or cur_ks is None:  # 成员缺席 → 跳过, 不炸
            continue
        compared = True
        if prev_counts[name] != cur_counts[name]:  # rc 已变 → 非偷泊
            continue
        added, removed = cur_ks - prev_ks, prev_ks - cur_ks
        if added or removed:
            lines.append(f"偷泊嫌疑: {name} (rc 恒定 {cur_counts[name]}, "
                         f"键集 +{len(added)}/-{len(removed)})→人裁")
    return lines if compared else ["偷泊诊断: 无可比对"]


# ── 能力轨北星观测件(#185;STANDARD.md E-5)──────────────────
# 只观测不持门: 北星 = 「整体情报更准」的可计算代理(v0 两腿 = 锚集全绿率
# + 谱系去重后 corroborated 精度月环比), 记录落 readout 腿工件, 不设阈值、
# 不进 CI、不拦月轮退出码 —— 与回归轨(anchors-*.json 失败 sys.exit(1)
# 判定门)双轨分立(ADR 0008 决策 2;E-2 阈值语义不同, 不得互相原谅)。
# 代理可换(换代理≠典章版本变更), 方向恒 = 整体情报更准。


def load_anchor_green(model_dir: Path) -> list[dict]:
    """anchors-*.json 按文件名 ts 升序 → 全绿率读数列表
    [{artifact, n_total, n_fail, rate}](月轮真实序: --anchors 腿先于
    --readout 落 model/, 本轮件 = 最新一件; n_total=0 无信息量同跳)。
    坏 JSON/非 dict/缺 n_total 形状跳过不炸(_oc_latest 同款宽容)。
    锚读数单一真源 = 回归轨判定门工件(anchors_report 落件), 能力轨
    只读不复算 —— 同轮月报两轨读数恒一致。"""
    out: list[dict] = []
    for p in sorted(Path(model_dir).glob("anchors-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        n_total = d.get("n_total") if isinstance(d, dict) else None
        if not isinstance(n_total, int) or isinstance(n_total, bool) \
                or n_total <= 0:
            continue
        n_fail = len(d.get("failures") or [])
        out.append({"artifact": p.name, "n_total": n_total,
                    "n_fail": n_fail,
                    "rate": (n_total - n_fail) / n_total})
    return out


def load_prev_northstar(out_dir: Path, run_id: str) -> dict | None:
    """上轮北星件: <out_dir>/northstar-*.json 排除本轮工件
    (northstar-{run_id}.json, 同 run 重跑不喂自身环比)后的最新一件;
    无 → None(首轮, 环比不虚构)。坏件跳过不炸(同上宽容律)。"""
    prev = None
    for p in sorted(Path(out_dir).glob("northstar-*.json")):
        if p.name == f"northstar-{run_id}.json":
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if isinstance(d, dict):
            prev = d  # 文件名升序扫描 → 末次赋值即最新
    return prev


def load_leg_status(out_dir: Path) -> dict | None:
    """腿级状态件(#193 C5): <out_dir>/leg-status-*.json 最新一件;
    月轮壳在 readout 腿前写入(腿名→rc, readout=null=本腿在飞),
    接线方渲染进月报头块 —— 腿级红随工件可见(_alerts 只认心跳
    mtime, 红态必须长在工件里, 评审D P1-3)。无件 → None(首轮/
    手工跑不虚构); 坏件跳过不炸(同 load_prev_northstar 宽容律)。"""
    latest = None
    for p in sorted(Path(out_dir).glob("leg-status-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if isinstance(d, dict):
            latest = d  # 文件名升序扫描 → 末次赋值即最新
    return latest


def render_leg_status(leg: dict | None) -> list[str]:
    """月报腿级行(#193 C5): 全景一行(腿名=rcN, null→渲染中在飞)
    + 红腿单独点名行(仅有红时出)。只观测不持门 —— 红态外显靠月轮壳
    结尾聚合退出码, 本行只长在工件里供人/机读。"""
    if not leg:
        return []
    legs = leg.get("legs") or {}
    if not legs:
        return []
    cells = " | ".join(
        f"{name}=" + ("进行中(在飞)" if rc is None else f"rc{rc}")
        for name, rc in legs.items())
    lines = [f"- 腿级状态(#193 C5): {cells}"]
    red = [f"{k}(rc{v})" for k, v in legs.items() if v not in (0, None)]
    if red:
        lines.append(f"- 腿级红: {', '.join(red)} —— 红态记录≠管线中止"
                     "(机器可读件 leg-status-*.json)")
    return lines


def northstar_record(readout: dict, anchor_hist: list[dict],
                     prev_ns: dict | None, *, run_id: str, eval_env: str,
                     today: date) -> dict:
    """北星两腿纯计算(接线方传 readout + 工件读数, 本函数不碰文件)。

    ①锚集全绿率 = anchor_hist 最新一件(回归轨工件直读);
    ②谱系去重后 corroborated 精度: OK 层 k_all 直方图 k≥2 桶求和
    (层经交集审计互斥, 求和无回声双计 = F6 同款裁决)为 corroborated
    总数, 派生簇独证(readout["derived_only_corroboration"], 114DNS
    事故面 = 聚合器互证假印证)折减 → precision = (n − derived_only)/n;
    n=0 → None(零读数≠精度 0, 无话不虚构)。月环比 = 本轮 − 前轮
    (百分点), 任一侧值缺席(首轮件无/N/A)→ None。直方图键 int 强转
    (str 键 JSON 往返同容), 非数键跳过。只观测不持门: 本函数及调用方
    均不设阈值、不产退出码。"""
    kcorr = 0
    for block in (readout.get("layers") or {}).values():
        if block.get("status") != "OK":
            continue  # NO-LAYER 层无读数(缺层≠0 层)
        for k, n in (block.get("k_all") or {}).items():
            try:
                if int(k) >= 2:
                    kcorr += n
            except (TypeError, ValueError):
                continue
    derived_only = readout.get("derived_only_corroboration") or 0
    precision = (kcorr - derived_only) / kcorr if kcorr else None
    cur = anchor_hist[-1] if anchor_hist else None
    prev = anchor_hist[-2] if len(anchor_hist) >= 2 else None
    prev_prec = ((prev_ns or {}).get("corroborated") or {}).get("precision")
    return {
        "kind": "northstar",
        "run_id": run_id,
        "eval_env": eval_env,
        "generated_at": today.isoformat(),
        "anchor_green": cur,
        "anchor_prev": prev,
        "anchor_green_mom_pp":
            (cur["rate"] - prev["rate"]) * 100
            if cur and prev and cur.get("rate") is not None
            and prev.get("rate") is not None else None,
        "corroborated": {"n": kcorr, "derived_only": derived_only,
                         "precision": precision},
        "corroborated_precision_mom_pp":
            (precision - prev_prec) * 100
            if precision is not None and prev_prec is not None else None,
        "prev_northstar_present": prev_ns is not None,
    }


def render_northstar(ns: dict) -> list[str]:
    """北星行(恒一行;「只观测不持门」写进行文)。N/A 哨兵分立:
    锚读数缺席 / 零 corroborated 读数 / 首轮 / 前轮 N/A 各自显式措辞,
    读者可区分「没算」「没件」「前轮无值」。"""
    if ns.get("anchor_green") is None:
        anchor = "锚集全绿率 N/A(无 anchors 工件)"
    else:
        g = ns["anchor_green"]
        if ns.get("anchor_green_mom_pp") is not None:
            mom = f"环比 {ns['anchor_green_mom_pp']:+.1f}pp"
        elif ns.get("anchor_prev") is None:
            mom = "环比 首轮"
        else:
            mom = "环比 前轮 N/A"
        anchor = (f"锚集全绿率 {g['n_total'] - g['n_fail']}/{g['n_total']}"
                  f"({g['rate'] * 100:.1f}%, {mom}, "
                  f"读数源 {g['artifact']})")
    corr = ns.get("corroborated") or {}
    if corr.get("precision") is None:
        prec = "corroborated 精度 N/A(零 corroborated 读数)"
    else:
        if ns.get("corroborated_precision_mom_pp") is not None:
            pmom = f"环比 {ns['corroborated_precision_mom_pp']:+.1f}pp"
        elif ns.get("prev_northstar_present") is False:
            pmom = "环比 首轮"
        else:
            pmom = "环比 前轮 N/A"
        prec = (f"corroborated 精度 {corr['precision'] * 100:.1f}%"
                f"(corroborated {corr['n']} 读数, 派生独证 "
                f"{corr['derived_only']}, {pmom})")
    return [f"- 能力轨北星(E-5, 只观测不持门): {anchor}|{prec}"]


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)


def _fmt_hist(h) -> str:
    return "—" if not h else ", ".join(f"{k}:{v}" for k, v in h.items())


def compose_monthly_md(readout: dict, disclosures_lines: list[str],
                       action_items: list[ActionItem],
                       scorecard_rows: list[tuple],
                       consensus_diag_lines: list[str],
                       header_meta: dict,
                       steal_parking_lines: list[str] | None = None,
                       north_star_lines: list[str] | None = None,
                       leg_status_lines: list[str] | None = None) -> str:
    """组装月轮报告 v2 markdown。头块 = 环境指纹 + 语料版本/指纹逐层 +
    S12/S17 换版注记(仅稳定层指纹实变才出, F2 趋势纪律; 共识代理层=
    滚动语料豁免, 声明行交代)+ S6 年度递减计数 +
    S30 处置状态汇总 + F7 ε 三档行; 正文 = 分层读数表(T8)/行动区块
    (S30)/R10 混杂披露/记分卡(S28)/诊断层统计(Q22, S24 锚对 OC 行由
    接线方并入 consensus_diag_lines;S34 偷泊行经 steal_parking_lines
    并入同节 Q22 行之后, 缺省 None 不出, schema-stable)/能力轨北星行
    (#185 E-5, north_star_lines 缺省 None 不出, schema-stable; 只观测
    不持门 —— 无阈值无门语义, 行文自带声明)/腿级状态行(#193 C5,
    leg_status_lines 缺省 None 不出, schema-stable; 腿级红随工件可见,
    红态外显靠月轮壳结尾聚合退出码)。F1: 无任何总分列。"""
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
               if k in RESET_NOTE_KINDS
               and isinstance(corpus.get(k), dict)
               and corpus[k].get("fingerprint") not in (None, v)]
    if changed:
        detail = ", ".join(f"{k}: {prev[k]} → {corpus[k]['fingerprint']}"
                           for k in changed)
        lines.append(f"- ⚠ 换版=趋势重置(S12/S17): {detail}"
                     "(趋势断言仅限指纹未变窗口)")
    # 共识滚动豁免声明行(替代静默省略): 读者须能区分「豁免」与「没变」
    lines.append("- 共识代理层=滚动语料(Q22), 豁免换版注记, 不做趋势断言")
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
    eps = header_meta.get("epsilon")
    if eps:
        cells = " / ".join(f"ε={e:.2f} → {v:.4f}"
                           for e, v in sorted(eps.items()))
        lines.append(f"- F7 ε 敏感性(真值层命中率三档): {cells}")
    elif "epsilon" in header_meta:
        # 真值层 NO-LAYER → ε 三档不算(缺层≠0 层, §2.3): 显式哨兵行,
        # 不静默省略 —— 读者须能区分「没算」与「没层」。
        lines.append("- F7 ε 敏感性(真值层命中率三档): 真值层缺(N/A)")

    if north_star_lines:  # 能力轨北星行(#185): 头块尾, 只观测不持门
        lines += north_star_lines
    if leg_status_lines:  # 腿级状态行(#193 C5): 北星行后, 同律只观测
        lines += leg_status_lines

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
    if steal_parking_lines:  # S34 偷泊列: Q22 行之后, 只报人裁
        lines += steal_parking_lines

    # 声明 r(report.py 脚注纪律同款斜体行): 测量建言, 人裁终局
    lines += ["", "_声明 r: 本报告为测量建言,人裁终局;读数不自动触发任何"
              "接入/剔除/调权动作。_",
              "_F1: 读数为表+行向量,无综合总分;趋势仅在语料指纹未变窗口"
              "内解读(F2/S12/S17)。_", ""]
    return "\n".join(lines)
