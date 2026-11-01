# backend/tests/eval/test_eval_truth_v2_parallel.py
"""真值语料 v2 并排对照 + 换卷触发测试(ADR 0017 §5 / issue #262 T3)。

全部离线合成:Hornet 侧资产与 v2 语料件现场合成出版;registry 用富假
lookup(满足 32 锚四类期望: clean/reserved/tor/hosting)。验收线
(issue #262):双语料装配通路一次月轮端到端(锚回归+θ 记分双卷)、
对照读数落工件可复核、换卷触发判定 = 布尔+依据行(人裁执行,判定工件
不触发任何自动动作)、坏语料件照炸不装假零。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval.anchors import ANCHORS, run_anchors
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset

from test_eval_truth_v2_readout import _publish_corpus, _write_sentinel
from test_eval_truth_v2 import _context


# ── fixtures: 富假 registry(锚四类期望 + 语料指控表) ──────────

_RESERVED = {"10.0.0.1", "127.0.0.1", "192.168.1.1", "172.16.0.1"}
_TOR = {ip for ip, expect in ANCHORS if expect == "tor"}
_HOSTING = {ip for ip, expect in ANCHORS if expect == "hosting"}


class _AnchorsRegistry:
    """lookup: 锚 IP 按期望形状作答(32 锚全绿可复现);语料成员按
    accusers 表给指控载荷;其余 IP 干净(无指控)。"""

    def __init__(self, accusers: dict[str, list[str]]):
        self.accusers = accusers
        self.sources = []

    def load_db(self):                     # CLI 面注册表契约(no-op, 离线)
        pass

    def lookup(self, ip, asof=None):
        if ip in _RESERVED:
            return {"ip": ip, "is_reserved": True, "classifications": {}}
        if ip in _TOR or ip in _HOSTING:
            attr = "is_tor" if ip in _TOR else "is_hosting"
            return {"ip": ip, "attributes": {attr: [{"value": True}]},
                    "classifications": {}}
        srcs = self.accusers.get(ip, [])
        if not srcs:
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"bruteforce": {
            "type": "bruteforce", "verdict": "malicious",
            "verdict_conflict": False, "confidence": 50,
            "details": [{"source": s, "verdict": "malicious"}
                        for s in srcs]}}}


# Hornet 成员(198.51.100/24)与 v2 成员(203.0.113/24)分段互斥,
# 两卷同享一套读数口径下的可分辨指控表。
_HORNET_MEMBERS = ["198.51.100.10", "198.51.100.11", "198.51.100.12",
                   "198.51.100.13"]
# A=s1+s2(印证), B=s1(独证), C=无人, D=s1+s2(印证)
_HORNET_ACCUSERS = {
    "198.51.100.10": ["s1", "s2"],
    "198.51.100.11": ["s1"],
    "198.51.100.13": ["s1", "s2"],
}
_V2_MEMBERS = ["203.0.113.10", "203.0.113.11", "203.0.113.12",
               "203.0.113.13"]
# A=s1+s2(印证), B=s2(独证), C=s1+s2(印证), D=无人
_V2_ACCUSERS = {
    "203.0.113.10": ["s1", "s2"],
    "203.0.113.11": ["s2"],
    "203.0.113.12": ["s1", "s2"],
}


def _publish_hornet(assets_root: Path, members=_HORNET_MEMBERS):
    """合成 Hornet 现行卷资产(assets 根 truth/ 目录, v1 装配面同位)。"""
    d = Path(assets_root) / "truth"
    save_asset(d, members, AssetMeta(
        version="hornet-202609", kind="truth",
        fingerprint=fingerprint(members), member_count=len(members),
        params={"rir_cutoff": "2024-07-02"}, eval_env="monthly",
        created_at="2026-09-30"))
    return d


# ── 1. 双语料装配通路: 同轮并排实算, 对照读数落工件 ──────────────


def test_parallel_dual_corpus_end_to_end(tmp_path):
    """同一次月轮双语料各跑一遍: 32 锚回归(引擎判定门, 卷无关, 同轮单跑
    两卷共用)+ θ̂/k 记分(两卷同源口径);对照工件两翼齐全可复核。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    assets = tmp_path / "assets"
    _publish_hornet(assets)
    out = tmp_path / "out"
    _publish_corpus(out, members=_V2_MEMBERS)
    reg = _AnchorsRegistry({**_HORNET_ACCUSERS, **_V2_ACCUSERS})

    res = run_truth_v2_parallel(reg, out_dir=out, assets_root=assets)

    assert res["kind"] == "truth_v2_parallel"
    # Hornet 翼: 现行卷实算(hits 3/4; θ̂ 逐源与池级同 T2 口径)
    h = res["hornet"]
    assert h["status"] == "published"
    assert h["corpus"]["version"] == "hornet-202609"
    hr = h["readout"]
    assert hr["n_members"] == 4 and hr["hits"] == 3   # C 无人指控
    ps = {row["source"]: row for row in hr["per_source"]}
    assert ps["s1"] == {"source": "s1", "n": 3, "k": 2,
                        "theta_hat": pytest.approx(3 / 5), "solo": 1}
    assert hr["theta_hat_pool"] == {
        "n_hits": 3, "n_corroborated": 2,
        "value": pytest.approx(3 / 5)}
    # v2 翼: 同一纯函数、同一 lookup —— 对照口径同源
    v = res["v2"]
    assert v["status"] == "published"
    vr = v["readout"]
    assert vr["n_members"] == 4 and vr["hits"] == 3
    assert set(vr.keys()) == set(hr.keys())           # 读数键形一致(可对照)
    # 锚回归: 引擎判定门同轮单跑, 两卷共用一份读数
    a = res["anchors"]
    assert a["n_total"] == len(ANCHORS) == 32 and a["n_fail"] == 0
    assert a["all_green"] is True
    # 工件落盘可复核
    arts = list((out / "model").glob("truth-v2-parallel-*.json"))
    assert len(arts) == 1
    doc = json.loads(arts[0].read_text())
    assert doc["hornet"]["status"] == "published"
    assert doc["v2"]["corpus"]["fingerprint"] == fingerprint(_V2_MEMBERS)
    assert "只观测不持门" in doc["gate"]


def test_parallel_theta_same_machinery_both_corpora(tmp_path):
    """θ 记分对照的公平性钉测: 同一指控源在两卷上的 θ̂ 由同一函数算出
    (s1 在 Hornet 卷 n=3/k=2, 在 v2 卷 n=2/k=2 → 数值随卷成员实算)。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    assets = tmp_path / "assets"
    _publish_hornet(assets)
    out = tmp_path / "out"
    _publish_corpus(out, members=_V2_MEMBERS)
    reg = _AnchorsRegistry({**_HORNET_ACCUSERS, **_V2_ACCUSERS})
    res = run_truth_v2_parallel(reg, out_dir=out, assets_root=assets)
    h_s1 = {r["source"]: r for r in res["hornet"]["readout"]["per_source"]}["s1"]
    v_s1 = {r["source"]: r for r in res["v2"]["readout"]["per_source"]}["s1"]
    # v2 卷上 s1: A、C 指控(n=2), 两者都有 s2 同指控(k=2)
    assert v_s1 == {"source": "s1", "n": 2, "k": 2,
                    "theta_hat": pytest.approx(3 / 4), "solo": 0}
    assert h_s1["theta_hat"] != v_s1["theta_hat"]      # 两卷读数各自实算


def test_parallel_missing_sides_na_not_fabricated(tmp_path):
    """两翼缺件 = N/A 哨兵不虚构(缺资产/缺语料都不是 0 读数);
    工件照写(腿红不持门、工件照写的观测腿律)。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    res = run_truth_v2_parallel(_AnchorsRegistry({}), out_dir=tmp_path / "out",
                                assets_root=tmp_path / "no-assets")
    assert res["hornet"]["status"] == "no-asset"
    assert res["hornet"]["readout"] is None and res["hornet"]["corpus"] is None
    assert res["v2"]["status"] == "no-corpus"
    assert res["v2"]["readout"] is None
    assert list((tmp_path / "out" / "model")
                .glob("truth-v2-parallel-*.json"))    # 缺件也落工件


def test_parallel_sentinel_and_empty_asset_states(tmp_path):
    """v2 哨兵态(组件闸不足)与 Hornet 空资产(member_count=0 = 缺层≠0 层,
    assemble_four_layers 同律)各自显式状态, 不混读数。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    assets = tmp_path / "assets"
    _publish_hornet(assets, members=[])               # 空资产(指纹一致)
    out = tmp_path / "out"
    _write_sentinel(out)
    res = run_truth_v2_parallel(_AnchorsRegistry({}), out_dir=out,
                                assets_root=assets)
    assert res["hornet"]["status"] == "empty-asset"
    assert res["v2"]["status"] == "insufficient"
    assert res["v2"]["sentinel"]["min_component_ips"] == 1000


def test_parallel_corrupt_corpus_fails_loud(tmp_path):
    """坏语料件(指纹失配)原样上抛 = 操作失败族, 不装假零(T2 tamper-red
    同款立场;对照读数喂换卷人裁, 更不许静默降级)。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    assets = tmp_path / "assets"
    _publish_hornet(assets)
    out = tmp_path / "out"
    d = _publish_corpus(out, members=_V2_MEMBERS)
    (d / "ips.txt").write_text("203.0.113.99\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        run_truth_v2_parallel(_AnchorsRegistry({}), out_dir=out,
                              assets_root=assets)


# ── 2. 换卷触发判定: 连续两轮 32 锚全绿 = 满足(人裁执行) ─────────


def _write_anchors_round(model_dir: Path, name: str, *, n_total=32,
                         failures=(), generated_at="2026-11-01"):
    model_dir.mkdir(parents=True, exist_ok=True)
    p = model_dir / name
    p.write_text(json.dumps({"kind": "anchors", "eval_env": "monthly",
                             "generated_at": generated_at,
                             "n_total": n_total, "failures": list(failures)}),
                 encoding="utf-8")
    return p


def test_swap_trigger_two_consecutive_green_rounds(tmp_path):
    """正例: 最近两轮全绿 → 布尔 True + 依据行点名两轮工件;工件带人裁
    声明(判定不触发任何自动动作)。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_swap
    out = tmp_path / "out"
    md = out / "model"
    _write_anchors_round(md, "anchors-20261001-041700.json",
                         generated_at="2026-10-01")
    _write_anchors_round(md, "anchors-20261101-041700.json",
                         generated_at="2026-11-01")
    res = run_truth_v2_swap(md, out_dir=out)
    assert res["trigger_met"] is True
    assert res["n_expected"] == 32 and res["rounds_seen"] == 2
    ev = "\n".join(res["evidence"])
    assert "anchors-20261001-041700.json" in ev
    assert "anchors-20261101-041700.json" in ev
    assert "n_total=32 n_fail=0" in ev
    assert "人裁" in res["human_decision"]           # 不自动换卷
    art = list(md.glob("truth-v2-swap-*.json"))
    assert len(art) == 1
    doc = json.loads(art[0].read_text())
    assert doc["trigger_met"] is True


def test_swap_trigger_not_met_single_round(tmp_path):
    """<2 轮在案 → 不满足, 依据行明说轮数不足(首轮月轮的诚实读数)。"""
    from ipdb._eval.truth_v2_parallel import (load_anchor_rounds,
                                              swap_trigger_from_rounds)
    md = tmp_path / "model"
    _write_anchors_round(md, "anchors-20261101-041700.json")
    rounds = load_anchor_rounds(md)
    assert len(rounds) == 1
    res = swap_trigger_from_rounds(rounds, n_expected=32)
    assert res["trigger_met"] is False
    assert "不足" in "\n".join(res["evidence"]) and "需连续两轮" in "\n".join(
        res["evidence"])


def test_swap_trigger_not_met_latest_red(tmp_path):
    """最近一轮有锚失败(工件在、失败也在)→ 不满足;红轮点名在依据行。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_swap
    md = tmp_path / "out" / "model"
    _write_anchors_round(md, "anchors-20261001-041700.json")
    _write_anchors_round(md, "anchors-20261101-041700.json",
                         failures=[{"ip": "8.8.8.8", "expect": "clean",
                                    "reason": "expected clean, got malicious"}])
    res = run_truth_v2_swap(md, out_dir=tmp_path / "out")
    assert res["trigger_met"] is False
    assert "n_fail=1" in "\n".join(res["evidence"])


def test_swap_trigger_not_met_anchor_set_shape_change(tmp_path):
    """历史轮锚集形状与当前不符(n_total≠len(ANCHORS), 如锚集扩员前的旧轮)
    → 该轮不算「32 锚全绿」, 依据行明示形状失配。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_swap
    md = tmp_path / "out" / "model"
    _write_anchors_round(md, "anchors-20260901-041700.json", n_total=19)
    _write_anchors_round(md, "anchors-20261101-041700.json")
    res = run_truth_v2_swap(md, out_dir=tmp_path / "out")
    assert res["trigger_met"] is False
    assert "n_total=19" in "\n".join(res["evidence"])


def test_swap_trigger_same_month_rerun_not_two_rounds(tmp_path):
    """轮粒度 = 月(评审环条目 2): 同月手工重跑 + 月轮各绿一次仍只算
    一轮 —— 不得把「同月重跑照绿」当连续两轮误判满足换卷。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_swap
    md = tmp_path / "out" / "model"
    _write_anchors_round(md, "anchors-20261101-041700.json")   # 月轮
    _write_anchors_round(md, "anchors-20261102-093000.json")   # 同月手工重跑
    res = run_truth_v2_swap(md, out_dir=tmp_path / "out")
    assert res["trigger_met"] is False
    assert res["rounds_seen"] == 1
    assert "不足" in "\n".join(res["evidence"])


def test_swap_trigger_month_dedupe_takes_last_within_month(tmp_path):
    """同月多件取末件(评审环条目 2): 月内先红后绿(重跑修好)→ 该月按
    末件算绿;与上一月绿轮相连 → 满足。末件口径 = 修好后的真态, 不是首跑。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_swap
    md = tmp_path / "out" / "model"
    _write_anchors_round(md, "anchors-20261001-041700.json")   # 上月绿
    _write_anchors_round(md, "anchors-20261101-041700.json",   # 本月首跑红
                         failures=[{"ip": "8.8.8.8", "expect": "clean",
                                    "reason": "expected clean, got malicious"}])
    _write_anchors_round(md, "anchors-20261105-041700.json")   # 本月末件绿
    res = run_truth_v2_swap(md, out_dir=tmp_path / "out")
    assert res["trigger_met"] is True
    assert res["rounds_seen"] == 2
    ev = "\n".join(res["evidence"])
    assert "anchors-20261105-041700.json" in ev    # 末件逃依据行
    assert "anchors-20261101-041700.json" not in ev  # 首跑被月内去重


def test_swap_trigger_loader_tolerance(tmp_path):
    """坏 JSON / n_total 无信息量形状跳过不炸(load_anchor_green 同律)。"""
    from ipdb._eval.truth_v2_parallel import load_anchor_rounds
    md = tmp_path / "model"
    (md).mkdir(parents=True)
    (md / "anchors-20261001-000000.json").write_text("{ bad json",
                                                     encoding="utf-8")
    _write_anchors_round(md, "anchors-20261015-000000.json", n_total=0)
    _write_anchors_round(md, "anchors-20261101-000000.json")
    rounds = load_anchor_rounds(md)
    assert [r["artifact"] for r in rounds] == \
        ["anchors-20261101-000000.json"]
    assert rounds[0]["generated_at"] == "2026-11-01"   # 依据行可读性来源


# ── 3. CLI 接线: 一腿三工件 + 构建腿工件 ───────────────────────


def test_cli_readout_leg_writes_three_artifacts(tmp_path, monkeypatch,
                                                capsys):
    """--truth-v2-readout(T3 扩展): 附录读数 + 并排对照 + 换卷触发判定
    一腿三工件(anchor-readouts 一腿双工件先例);缺件态 rc 恒 0。"""
    import ipdb._eval.__main__ as M
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep"))
    monkeypatch.setattr(M, "_real_registry", lambda: _AnchorsRegistry({}))
    M.main(["--truth-v2-readout"])
    out = capsys.readouterr().out
    assert "no-corpus" in out                          # T2 附录行保留
    assert "truth-v2-parallel" in out and "truth-v2-swap" in out
    rep = tmp_path / "rep" / "dev" / "model"
    for pat in ("truth-v2-readout-*.json", "truth-v2-parallel-*.json",
                "truth-v2-swap-*.json"):
        assert list(rep.glob(pat)), pat                 # 三件齐落
    swap = json.loads(sorted(rep.glob("truth-v2-swap-*.json"))[-1]
                      .read_text())
    assert swap["trigger_met"] is False                # 零锚工件在案


def test_cli_build_leg_writes_summary_artifact(tmp_path, monkeypatch,
                                               capsys):
    """--truth-v2 构建腿(T3 接线): published 与哨兵两态恒落
    model/truth-v2-build-<ts>.json 摘要件(monthly_eval.sh 报告族写者;
    崩溃 rc=2 不落件 = 族缺员即死, 与其他腿同语义)。"""
    import ipdb._eval.__main__ as M
    from ipdb._eval.truth_v2 import MIN_COMPONENT_IPS
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep"))
    ctx = _context(tmp_path, n_pass=MIN_COMPONENT_IPS)
    M.main(["--truth-v2",
            "--truth-v2-component", f"smallbox={ctx['components']['smallbox']}",
            "--rir-dir", str(ctx["rir_dir"]),
            "--scanner-csv", str(ctx["scanner_csv"])])
    rep = tmp_path / "rep" / "dev" / "model"
    builds = sorted(rep.glob("truth-v2-build-*.json"))
    assert len(builds) == 1
    doc = json.loads(builds[0].read_text())
    assert doc["kind"] == "truth_v2_build"
    assert doc["status"] == "published" and doc["member_count"] >= 1000
    # 哨兵态(999): 同律落件, status=insufficient
    ctx2 = _context(tmp_path / "s2", n_pass=MIN_COMPONENT_IPS - 1)
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep2"))
    M.main(["--truth-v2",
            "--truth-v2-component", f"smallbox={ctx2['components']['smallbox']}",
            "--rir-dir", str(ctx2["rir_dir"]),
            "--scanner-csv", str(ctx2["scanner_csv"])])
    doc2 = json.loads(sorted((tmp_path / "rep2" / "dev" / "model")
                             .glob("truth-v2-build-*.json"))[-1].read_text())
    assert doc2["status"] == "insufficient"


def test_anchors_run_once_shared_by_both_sides(tmp_path):
    """「各跑一遍锚回归」的接线口径钉测: 锚回归 = 引擎判定门(run_anchors,
    32 锚已知答案, 与真值卷无关)→ 同轮单跑、两卷共用一份读数(宁少算,
    同引擎同轮跑两遍是回声不是印证);并排件单 anchors 块自带该声明。"""
    from ipdb._eval.truth_v2_parallel import run_truth_v2_parallel
    assets = tmp_path / "assets"
    _publish_hornet(assets)
    out = tmp_path / "out"
    _publish_corpus(out, members=_V2_MEMBERS)
    reg = _AnchorsRegistry({**_HORNET_ACCUSERS, **_V2_ACCUSERS})
    assert not run_anchors(reg.lookup)                 # 富假 registry 全绿
    res = run_truth_v2_parallel(reg, out_dir=out, assets_root=assets)
    assert res["anchors"]["all_green"] is True
    assert "卷无关" in res["anchors"]["note"] or "单跑" in res["anchors"]["note"]
