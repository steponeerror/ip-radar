# backend/ipdb/_eval/truth_v2_parallel.py
"""真值语料 v2 并排对照 + 换卷触发判定(ADR 0017 §5 / issue #262 T3).

Hornet 现行卷(assets 根 truth/ 资产, ops 侧三闸产出)与 v2 卷
(report_dir/truth-v2/, T1 构建器产物)在同一次月轮并排实算: 同一
lookup、同一读数口径(truth_v2_readout.truth_v2_corpus_readout 单源
复用 —— θ̂ 试算 / k 双报 / 池命中), 对照读数落 model/truth-v2-
parallel-<ts>.json。32 锚回归 = 引擎判定门(anchors.run_anchors, 32 锚
已知答案, 与真值卷无关)→ 同轮单跑、两卷共用一份读数(宁少算: 同引擎
同轮跑两遍是回声不是印证)。

换卷触发(ADR 0017 §5): 输入 = 逐轮锚回归结果(anchors-*.json 工件,
--anchors 判定门腿所落), 连续两轮 32 锚全绿 = 满足换卷条件; 输出 =
布尔判定 + 依据行, 落 model/truth-v2-swap-<ts>.json。判定工件不触发
任何自动动作 —— 换卷由人裁执行(测量建言, 人裁终局); 换版即 S17 趋势
重置(monthly.compose_monthly_md 换版注记既有机制, 指纹变化即重置)。

零持门(northstar / T2 附录腿同律): 无阈值、不进回归族、缺件/哨兵态
rc 恒 0 且工件照写; 坏语料件(指纹失配)原样上抛 = 操作失败族, 不装
假零(2026-10-10 假零判例)。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from .anchors import ANCHORS, run_anchors
from .truth_v2_readout import (
    _asof_from_created,
    probe_truth_v2_corpus,
    truth_v2_corpus_readout,
)

PARALLEL_PREFIX = "truth-v2-parallel"
SWAP_PREFIX = "truth-v2-swap"


# 轮归属月从工件名提取(评审环条目 2): anchors-YYYYMMDD-HHMMSS.json
# → YYYYMM;非标名不归类, 各自成轮(不误并不同月的手写件)
_ROUND_MONTH_RE = re.compile(r"^anchors-(\d{6})")


def load_anchor_rounds(model_dir: Path) -> list[dict]:
    """anchors-*.json 按文件名 ts 升序 → 逐轮锚回归结果
    [{artifact, generated_at, n_total, n_fail}](换卷触发判定的输入面)。
    轮粒度 = 月(评审环条目 2): 同月多件(如手工重跑 + 月轮)按文件名序
    只取末件 —— 「连续两轮」= 连续两个轮月, 同月重跑不得顶一轮;
    末件口径 = 该月最后一次跑的真态。坏 JSON / 非 dict / n_total 无信息量
    形状跳过不炸(monthly.load_anchor_green 同律宽容);锚读数单一真源 =
    回归轨判定门工件, 本模块只读不复算。"""
    by_month: dict[str, dict] = {}
    for p in sorted(Path(model_dir).glob("anchors-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        n_total = d.get("n_total") if isinstance(d, dict) else None
        if not isinstance(n_total, int) or isinstance(n_total, bool) \
                or n_total <= 0:
            continue
        m = _ROUND_MONTH_RE.match(p.name)
        key = m.group(1) if m else p.name
        by_month[key] = {"artifact": p.name,
                         "generated_at": str(d.get("generated_at") or ""),
                         "n_total": n_total,
                         "n_fail": len(d.get("failures") or [])}
    return list(by_month.values())   # dict 保插入序 = 文件名序(月序)


def swap_trigger_from_rounds(rounds: list[dict], *, n_expected: int) -> dict:
    """纯判定(issue #262 验收线): 逐轮锚回归结果 → 布尔 + 依据行。

    规则 = 连续两轮(最近两个月轮, 同月重跑去重后)32 锚全绿 → 满足
    换卷条件(ADR 0017 §5 「并排两轮 32 锚全绿、人裁执行」)。全绿 =
    n_fail==0 且 n_total 与当前锚集同形(n_total != len(ANCHORS) 的历史轮,
    如锚集扩员前的旧轮, 不算「32 锚全绿」, 依据行明示形状失配)。判定不
    触发任何自动动作 —— 换卷(真值指纹变化 + Hornet 退役为存档比对)由
    人裁执行。"""
    evidence: list[str] = [
        f"rule: 连续两轮 {n_expected} 锚回归全绿(最近两轮; 轮粒度=月, "
        "同月重跑取末件)→ 满足换卷条件"
        "(ADR 0017 §5);换卷由人裁执行, 本判定不触发任何自动动作"]
    if len(rounds) < 2:
        evidence.append(f"判定: 不满足 —— 锚回归轮数不足"
                        f"({len(rounds)} 轮在案, 需连续两轮)")
        return {"trigger_met": False, "n_expected": n_expected,
                "rounds_seen": len(rounds), "evidence": evidence}
    latest_two = rounds[-2:]
    green = 0
    for r in latest_two:
        if r["n_total"] != n_expected:
            evidence.append(
                f"round: {r['artifact']} generated_at={r['generated_at']} "
                f"n_total={r['n_total']} n_fail={r['n_fail']} → 形状失配"
                f"(当前锚集 {n_expected} 锚, 该轮不算全绿)")
        elif r["n_fail"] == 0:
            green += 1
            evidence.append(
                f"round: {r['artifact']} generated_at={r['generated_at']} "
                f"n_total={r['n_total']} n_fail={r['n_fail']} → green")
        else:
            evidence.append(
                f"round: {r['artifact']} generated_at={r['generated_at']} "
                f"n_total={r['n_total']} n_fail={r['n_fail']} → red")
    met = green == 2
    evidence.append(
        "判定: " + ("满足换卷条件(连续两轮全绿)——人裁执行换卷: Hornet 退役"
                    "为存档比对(不再算分), v2 卷接棒; 换版即 S17 趋势重置"
                    "(ADR 0017 §5)" if met else
                    "不满足(见上轮读数)"))
    return {"trigger_met": met, "n_expected": n_expected,
            "rounds_seen": len(rounds), "evidence": evidence}


def _hornet_side(assets_root: Path) -> dict:
    """Hornet 现行卷现场(assets 根 truth/ 资产)→ 翼结构。

    状态语义照 layered.assemble_four_layers: 目录缺席 = no-asset、
    空资产 = empty-asset(缺层≠0 层)——都不虚构 0 读数;坏资产
    (指纹失配)load_asset 原样炸出(操作失败族)。"""
    d = Path(assets_root) / "truth"
    side: dict = {"status": None, "corpus": None, "readout": None}
    if not d.is_dir():
        side["status"] = "no-asset"
        return side
    from .assets import load_asset
    members, meta = load_asset(d)
    if meta.member_count == 0:
        side["status"] = "empty-asset"
        return side
    side["status"] = "published"
    side["corpus"] = {
        "version": meta.version, "fingerprint": meta.fingerprint,
        "member_count": meta.member_count,
        "created_at": meta.created_at, "asset_dir": str(d)}
    side["_members"] = members
    side["_asof"] = _asof_from_created(meta.created_at)
    return side


def run_truth_v2_parallel(registry, out_dir=None, *,
                          corpus_root: Path | None = None,
                          assets_root: Path | None = None) -> dict:
    """并排对照装配(issue #262 验收线): 同轮双语料各实算一遍 θ̂/k 记分,
    32 锚回归引擎判定门单跑共用;对照工件恒落 <out_dir>/model/
    truth-v2-parallel-<ts>.json(缺翼 N/A 也落件, 读数留痕)。"""
    from .__main__ import _ASSETS_ROOT_DEFAULT, eval_env as _current_env, \
        report_dir
    env = _current_env()
    out_dir = Path(out_dir) if out_dir is not None else report_dir()
    if corpus_root is None:
        corpus_root = out_dir / "truth-v2"     # T1 构建器 out_root 同址
    if assets_root is None:
        assets_root = _ASSETS_ROOT_DEFAULT     # --assets-dir 缺省同 run_readout

    res: dict = {
        "kind": "truth_v2_parallel",
        "eval_env": env,
        "gate": ("observation-only (ADR 0017 §5): 并排对照只观测不持门; "
                 "换卷由人裁执行(触发判定见 truth-v2-swap 工件), 主判定权"
                 "过渡期仍归 Hornet"),
        "anchors": None,
        "hornet": None,
        "v2": None,
    }

    hornet = _hornet_side(assets_root)
    if hornet["status"] == "published":
        hornet["readout"] = truth_v2_corpus_readout(
            registry.lookup, hornet.pop("_members"),
            sources=registry.sources, asof=hornet.pop("_asof"))
    else:
        hornet.pop("_members", None)
        hornet.pop("_asof", None)
    res["hornet"] = hornet

    v2 = probe_truth_v2_corpus(corpus_root)
    side_v2: dict = {"status": v2["status"], "corpus": None,
                     "sentinel": v2["sentinel"], "readout": None}
    if v2["status"] == "published":
        meta = v2["meta"]
        side_v2["corpus"] = {
            "version": meta.version, "fingerprint": meta.fingerprint,
            "member_count": meta.member_count,
            "window": {k: meta.params.get(k) for k in
                       ("window_start", "window_end", "window_days")},
            "created_at": meta.created_at,
            "asset_dir": str(v2["dir"])}
        side_v2["readout"] = truth_v2_corpus_readout(
            registry.lookup, v2["members"], sources=registry.sources,
            asof=_asof_from_created(meta.created_at))
    res["v2"] = side_v2

    # 32 锚回归 = 引擎判定门(run_anchors, 32 锚已知答案, 与真值卷无关)
    # → 同轮单跑、两卷共用一份读数(宁少算: 同引擎同轮跑两遍是回声);
    # 失败清单原样留档(证据不灭失), 只观测不持门(判定门腿 = --anchors)
    fails = run_anchors(registry.lookup)
    res["anchors"] = {
        "n_total": len(ANCHORS), "n_fail": len(fails),
        "all_green": not fails, "failures": fails,
        "note": ("32 锚回归=引擎判定门(run_anchors), 与真值卷无关;同轮"
                 "单跑, 两卷共用此读数(宁少算);判定门退出码归 --anchors 腿"),
    }

    d = out_dir / "model"
    d.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = d / f"{PARALLEL_PREFIX}-{ts}.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    res["artifact"] = str(path)
    return res


def run_truth_v2_swap(model_dir: Path, out_dir=None, *,
                      assets_root: Path | None = None,
                      corpus_root: Path | None = None) -> dict:
    """换卷触发装配(issue #262 验收线): 逐轮锚回归工件 → 纯判定 →
    工件恒落 <out_dir>/model/truth-v2-swap-<ts>.json。context 段引用
    两卷指纹(换卷涉及的两造)——只作复核参照, 不入判定输入。"""
    from .__main__ import _ASSETS_ROOT_DEFAULT, eval_env as _current_env, \
        report_dir
    out_dir = Path(out_dir) if out_dir is not None else report_dir()
    if corpus_root is None:
        corpus_root = out_dir / "truth-v2"
    if assets_root is None:
        assets_root = _ASSETS_ROOT_DEFAULT

    rounds = load_anchor_rounds(model_dir)
    verdict = swap_trigger_from_rounds(rounds, n_expected=len(ANCHORS))

    # 复核参照(非判定输入): 换卷两造的当前指纹;坏件照炸(操作失败族)
    hornet_fp, hornet_ver = None, None
    hdir = Path(assets_root) / "truth"
    if hdir.is_dir():
        from .assets import load_asset
        _, hmeta = load_asset(hdir)
        hornet_fp, hornet_ver = hmeta.fingerprint, hmeta.version
    v2 = probe_truth_v2_corpus(corpus_root)
    v2_ctx = {"status": v2["status"],
              "version": v2["meta"].version if v2["meta"] else None,
              "fingerprint": v2["meta"].fingerprint if v2["meta"] else None}

    res: dict = {
        "kind": "truth_v2_swap_trigger",
        "eval_env": _current_env(),
        "trigger_met": verdict["trigger_met"],
        "n_expected": verdict["n_expected"],
        "rounds_seen": verdict["rounds_seen"],
        "evidence": verdict["evidence"],
        "context": {"hornet_truth": {"version": hornet_ver,
                                      "fingerprint": hornet_fp},
                    "v2_corpus": v2_ctx},
        "human_decision": ("换卷(真值指纹变化: Hornet 退役为存档比对不再"
                           "算分, v2 接棒)由人裁执行(ADR 0017 §5);本判定"
                           "工件不触发任何自动动作;换版即 S17 趋势重置"),
    }
    d = Path(out_dir) / "model"
    d.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = d / f"{SWAP_PREFIX}-{ts}.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    res["artifact"] = str(path)
    return res
