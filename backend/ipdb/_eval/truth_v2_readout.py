"""真值语料 v2 附录读数腿(ADR 0017 §4 / issue #261 T2).

T1 构建器(truth_v2.py)把出版件落在 report_dir/truth-v2/<version>/;
本腿只消费该处现场: 对 v2 语料(我方传感器确证的攻击 IP)逐成员查池,
试算 θ̂ 与独有指控核查, 读数落 model/truth-v2-readout-<ts>.json,
月报(run_readout)读最新件嵌「附录」节。观测身份零持门(northstar
同律): 不设阈值、不进回归族、缺语料件/哨兵态 rc 恒 0 且渲染 N/A
哨兵不虚构;坏出版件(指纹失配)原样上抛 = 操作失败族, 不装假零
(2026-10-10 假零判例, sinkhole_probe 同款立场)。

读数口径(全部既有语义, 零新机制):
- 成员判定 = lookup 载荷指控源集(layered._accusing_sources 借道,
  组级 verdict ∈ 指控章单一口径);
- k_all/k_nonhoneypot 双报沿用 v1 truth 层(layered_readout 同口径,
  蜜罐方法学源剔除 config.HONEYPOT_METHODOLOGY + 源属性, ADR 0017 §8);
- θ̂ 试算 = Beta(1,1) 后验均值 (k+1)/(n+2)(Laplace 平滑, dsem theta0
  同款): n = 该源在 v2 语料上的指控成员数, k = 其中还有 ≥1 个其他
  池源也指控的成员数。与记分卡 θ(model.estimate: 市场先验 ρ + ctype
  对口径)分立 —— 附录身份不入记分卡, 措辞永远「θ̂ 试算」;零命中
  → None(无证据≠0.5, 无话不虚构);
- 独有指控核查 = k_all==1 的语料成员归因到唯一指控源(独证),
  k_all==0 = 全池无指控成员(已确证攻击行为、池内零指控)——逐成员
  清单留工件, 报告行只点名计数与示例(可读性, 证据在件);
- asof 锚 = 语料 created_at(T1 锚日派生), layered truth 层 T10 同律:
  读数对齐语料时点, 不随引擎现态漂移。

主判定分离(issue #261 验收线): 本腿与月报装配面都只读
truth-v2-readout 工件, 永不直读 truth-v2 语料件 → 删语料件不影响
run_readout 输出字节(负例测试钉住)。
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import config
# _accusing_sources 私有名跨模块借道(口径同源勿复刻, canary/sentinel
# 同款先例): 全部指控源名集, 组级 verdict ∈ _ACCUSING 门控
from .layered import _accusing_sources

ARTIFACT_PREFIX = "truth-v2-readout"

# 附录节里成员点名上限: 报告行可读性;逐成员完整清单永远在工件里
_MD_EXAMPLE_CAP = 5


def latest_truth_v2_dir(corpus_root: Path) -> Path | None:
    """语料根(T1 out_root)→ 最新版本目录(文件名序, 月度重切口径
    truthv2-YYYYMM 字典序=时间序);根缺席/无版本 → None。"""
    root = Path(corpus_root)
    if not root.is_dir():
        return None
    versions = sorted(d for d in root.iterdir()
                      if d.is_dir() and d.name.startswith("truthv2-"))
    return versions[-1] if versions else None


def _asof_from_created(created_at: str) -> float:
    """语料锚日 → epoch 秒(run_readout 对 truth 层同款解析)。"""
    from datetime import timezone
    created = _dt.datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.timestamp()


def truth_v2_corpus_readout(lookup_fn, members: list[str], *,
                            sources=None, asof=None) -> dict:
    """纯计算: 语料成员 × 池指控 → 读数结构(模块 docstring 口径)。

    T3 并排对照(truth_v2_parallel)对 Hornet 卷与 v2 卷同源复用本函数
    —— 同一函数、同一 lookup = 对照口径同源, 两卷读数可直接并排。

    单个 lookup 失败原样上抛(不 except-continue, 假零判例)。"""
    honeypot = set(config.HONEYPOT_METHODOLOGY)
    for s in sources or ():
        if getattr(s, "honeypot_methodology", False):
            honeypot.add(s.name)
    # 声明派生簇(config.LINEAGE_CLUSTERS, layered F6 同款判定): θ̂/k 的
    # 印证计数不剔派生簇内互证 —— 派生对(转载关系)互证仍计入 k, 计数
    # 单列披露不折减。T3 对照读数喂换卷人裁时, 该计数应同读(issue #261
    # 评审 P2-5: derived-only 披露)。
    derived = set(config.LINEAGE_CLUSTERS)

    accusers: dict[str, set[str]] = {}
    for ip in members:
        res = lookup_fn(ip) if asof is None else lookup_fn(ip, asof=asof)
        acc = _accusing_sources(res)
        if acc:
            accusers[ip] = acc

    hits = len(accusers)
    k_all_hist: dict[str, int] = {}
    k_nh_hist: dict[str, int] = {}
    per_source: dict[str, dict] = {}
    unique_accusations: list[dict] = []
    blind_spots: list[str] = []
    derived_only = 0
    for ip in sorted(members):
        acc = accusers.get(ip, set())
        if not acc:
            blind_spots.append(ip)          # 已确证攻击、全池无指控
        if len(acc) == 1:
            unique_accusations.append(
                {"ip": ip, "source": next(iter(acc))})
        if len(acc) >= 2 and acc <= derived:
            derived_only += 1               # k≥2 且指控源全属声明派生簇
        for hist, pool in ((k_all_hist, acc),
                           (k_nh_hist, acc - honeypot)):
            key = str(len(pool))
            hist[key] = hist.get(key, 0) + 1
        for src in acc:
            row = per_source.setdefault(
                src, {"source": src, "n": 0, "k": 0, "solo": 0})
            row["n"] += 1
            if len(acc) >= 2:               # 还有 ≥1 个他源同指控 → 印证
                row["k"] += 1
            if len(acc) == 1:
                row["solo"] += 1

    rows = []
    for src in sorted(per_source):
        row = per_source[src]
        # θ̂ 试算 = Beta(1,1) 后验均值;零证据源不入表(无指控即无读数)
        row["theta_hat"] = (row["k"] + 1) / (row["n"] + 2)
        rows.append(row)
    n_corr = sum(1 for acc in accusers.values() if len(acc) >= 2)
    return {
        "n_members": len(members),
        "hits": hits,
        "rate": hits / len(members) if members else None,
        # 键按数值序(非字符串字典序): "2" 排在 "10" 前(issue #261 评审
        # P2-3;layered k 直方图 int 键同口径)
        "k_all_hist": dict(sorted(k_all_hist.items(),
                                  key=lambda kv: int(kv[0]))),
        "k_nonhoneypot_hist": dict(sorted(k_nh_hist.items(),
                                          key=lambda kv: int(kv[0]))),
        "honeypot_excluded": sorted(honeypot),
        "theta_hat_pool": {
            "n_hits": hits, "n_corroborated": n_corr,
            # 零命中 → None: 缺证据不冒充先验均值(无话不虚构)
            "value": (n_corr + 1) / (hits + 2) if hits else None},
        "per_source": rows,
        "unique_accusations": unique_accusations,
        "blind_spots": blind_spots,
        "derived_only_corroboration": derived_only,
        "asof": asof,
    }


def _sentinel_facts(status_path: Path) -> dict:
    """哨兵件 → 引用事实(版本/窗/组件计数);引用自己的件, 不虚构。"""
    st = json.loads(status_path.read_text(encoding="utf-8"))
    return {
        "version": st.get("version"),
        "window": st.get("window"),
        "min_component_ips": st.get("min_component_ips"),
        "components": {
            n: {"member_count": c.get("member_count"),
                "gate_passed": c.get("gate_passed")}
            for n, c in (st.get("components") or {}).items()},
    }


def probe_truth_v2_corpus(corpus_root: Path) -> dict:
    """语料现场探测(单一真源: T2 附录读数与 T3 并排对照共用)。

    返回 {status, members, meta, sentinel, dir};status ∈
    no-corpus(构建器从未跑过)/ insufficient(组件闸哨兵态)/ published。
    出版件走 load_asset 指纹闸(坏件照炸, 不装假零);空出版集 = 坏
    出版 invariant, ValueError;残缺版本目录(三件与哨兵皆无)= 残缺
    出版, ValueError fail-loud。"""
    vdir = latest_truth_v2_dir(corpus_root)
    if vdir is None:
        return {"status": "no-corpus", "members": None, "meta": None,
                "sentinel": None, "dir": None}
    if (vdir / "ips.txt").is_file() and (vdir / "meta.json").is_file():
        from .assets import load_asset
        members, meta = load_asset(vdir)   # 指纹闸: 坏件照炸(不装假零)
        if not members:
            raise ValueError(              # 出版不变量: 空集=坏出版
                f"empty published truth-v2 corpus: {vdir}")
        return {"status": "published", "members": members, "meta": meta,
                "sentinel": None, "dir": vdir}
    if (vdir / "status.json").is_file():
        return {"status": "insufficient", "members": None, "meta": None,
                "sentinel": _sentinel_facts(vdir / "status.json"),
                "dir": vdir}
    raise ValueError(                      # 残缺出版 = 操作失败 fail-loud
        f"incomplete truth-v2 version dir (no ips.txt/meta.json/"
        f"status.json): {vdir}")


def run_truth_v2_readout(registry, out_dir=None, *,
                         corpus_root: Path | None = None) -> dict:
    """CLI 装配: 探测语料现场 → 纯计算/哨兵 → 工件恒落
    <out_dir>/model/truth-v2-readout-<ts>.json(agg-share/anchors 报告族
    同形;缺件与哨兵态也落件 —— 读数留痕, 零持门不因缺输入少证据)。"""
    from .__main__ import eval_env as _current_env
    env = _current_env()
    out_dir = Path(out_dir) if out_dir is not None else None
    if corpus_root is None:
        if out_dir is None:
            from .__main__ import report_dir
            out_dir = report_dir()
        corpus_root = out_dir / "truth-v2"     # T1 构建器的 out_root 同址

    res: dict = {
        "kind": "truth_v2_readout",
        "eval_env": env,
        "status": None,
        "gate": ("observation-only (ADR 0017 §4): 附录读数不设阈值、"
                 "不进回归族、不拦月轮退出码;主判定权仍归 Hornet"),
        "corpus": None, "sentinel": None, "readout": None,
    }
    probed = probe_truth_v2_corpus(corpus_root)
    res["status"] = probed["status"]
    if probed["status"] == "published":
        meta = probed["meta"]
        res["corpus"] = {
            "version": meta.version, "fingerprint": meta.fingerprint,
            "member_count": meta.member_count,
            "window": {k: meta.params.get(k) for k in
                       ("window_start", "window_end", "window_days")},
            "created_at": meta.created_at,
            "asset_dir": str(probed["dir"])}
        res["readout"] = truth_v2_corpus_readout(
            registry.lookup, probed["members"], sources=registry.sources,
            asof=_asof_from_created(meta.created_at))
    elif probed["status"] == "insufficient":
        res["sentinel"] = probed["sentinel"]   # 组件闸哨兵态(ADR 0017 §4)

    if out_dir is not None:
        d = out_dir / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = d / f"{ARTIFACT_PREFIX}-{ts}.json"
        path.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        res["artifact"] = str(path)
    return res


def _fmt_hist(h: dict) -> str:
    return ", ".join(f"{k}:{v}" for k, v in h.items()) or "—"


def _example(ips: list[str]) -> str:
    shown = ips[:_MD_EXAMPLE_CAP]
    more = f" …共 {len(ips)}" if len(ips) > _MD_EXAMPLE_CAP else ""
    return " ".join(shown) + more


def render_truth_v2_appendix(res: dict | None) -> list[str]:
    """附录节渲染(纯函数, run_readout 与工件消费方同一真源)。

    四态措辞分立, 读者可区分: 没工件 / 没语料 / 没过组件闸 / 出版读数。
    None(无 truth-v2-readout 工件)也渲染 N/A —— 缺读数不静默省略
    (issue #261 验收线: 缺工件渲染 N/A 哨兵不虚构)。"""
    header = "## 附录: 真值语料 v2 读数(ADR 0017 T2, 只观测不持门)"
    if res is None:
        return [header, "",
                "- v2 附录读数 N/A(无 truth-v2-readout 工件;月轮先跑 "
                "`python -m ipdb._eval --truth-v2-readout`,附录不虚构)"]
    if res["status"] == "no-corpus":
        return [header, "",
                "- v2 附录读数 N/A(无 truth-v2 语料件——先跑 "
                "`python -m ipdb._eval --truth-v2` 构建器;ADR 0017 §4 "
                "不足期 v2 只出附录读数, 主判定权仍归 Hornet)"]
    if res["status"] == "insufficient":
        s = res["sentinel"] or {}
        comps = ", ".join(
            f"{n}:{c.get('member_count')}/{s.get('min_component_ips')}"
            for n, c in (s.get("components") or {}).items())
        w = s.get("window") or {}
        win = (f"窗 {w.get('start')}..{w.get('end')}"
               if w.get("start") else "窗 N/A")
        return [header, "",
                f"- v2 附录读数 N/A(语料哨兵态 insufficient: {comps} "
                f"未过组件闸, {win};主判定权仍归 Hornet, ADR 0017 §4)"]
    # published
    c = res["corpus"]
    r = res["readout"]
    th = r["theta_hat_pool"]
    art = Path(res["artifact"]).name if res.get("artifact") else "本件"
    uniq = r["unique_accusations"]
    solo_by_src = sorted(
        (u["source"] for u in uniq))
    lines = [
        header, "",
        f"- v2 语料 {c['version']} 指纹 {c['fingerprint']}, "
        f"窗 {c['window']['window_start']}..{c['window']['window_end']}, "
        f"读数源 {art}(只观测不持门;主判定权仍归 Hornet, ADR 0017 §4)",
        f"- 池命中 {r['hits']}/{r['n_members']}"
        f"({r['rate'] * 100:.1f}%);k_all {{{_fmt_hist(r['k_all_hist'])}}};"
        f" k_nonhoneypot {{{_fmt_hist(r['k_nonhoneypot_hist'])}}}"
        f"(蜜罐方法学源剔除 {','.join(r['honeypot_excluded'])};"
        " k 双报沿用 ADR 0017 §8)",
        f"- θ̂ 试算(平坦 Beta(1,1) 后验, 与记分卡 θ 市场先验口径分立): "
        + (f"池级 {th['value']:.4f}(印证 ≥2 源 {th['n_corroborated']}"
           f" / 命中 {th['n_hits']})" if th["value"] is not None
           else "池级 N/A(零命中, 无证据不冒充先验值)"),
        f"- 派生簇独证 {r['derived_only_corroboration']} 个(k≥2 且指控源"
        "全属声明派生簇;θ̂/k 印证不剔派生簇, 换卷对照读数须同读此数"
        "——issue #261 评审 P2-5)",
        f"- 独有指控核查: 单源独证 {len(uniq)} 个"
        + (f"(归属 {_example(solo_by_src)};逐成员清单在工件)"
           if uniq else "(无)")
        + f";全池无指控 {len(r['blind_spots'])} 个"
        + (f"({_example(r['blind_spots'])}——已确证攻击行为、"
           "池内零指控)" if r["blind_spots"] else ""),
        "", "逐源试算(只列在语料上有指控的源):",
        "",
        "| source | n(语料指控) | k(有他源印证) | θ̂ 试算 | 独证 |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {row['source']} | {row['n']} | {row['k']} "
              f"| {row['theta_hat']:.3f} | {row['solo']} |"
              for row in r["per_source"]] or ["| — | — | — | — | — |"]
    return lines
