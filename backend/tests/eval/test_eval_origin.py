# backend/tests/eval/test_eval_origin.py
"""W0 层1 leave-self-out:origin_map raw 文件成员判定 + estimate/run_dsem/
run_suite 剔除自采样 pair;origin=None 兼容锁(默认路径输出与现状一致)。"""
import json
from types import SimpleNamespace

import pytest

from ipdb._eval.corpus import Corpus
from ipdb._eval.dsem import run_dsem
from ipdb._eval.events import Events, SourceEvents
from ipdb._eval.model import estimate
from ipdb._eval.origin import origin_map
from ipdb._eval.suite import run_suite


# ── origin_map:raw 文件正则成员判定 ──────────────────────────────

def _fake_source(name, path=None, files=None):
    return SimpleNamespace(name=name, _path=path, _files=files)


def test_origin_map_membership(tmp_path):
    has = tmp_path / "has.txt"
    has.write_text("noise line\n1.2.3.4\n5.6.7.8/32\n")
    lacks = tmp_path / "lacks.txt"
    lacks.write_text("8.8.8.8\n8.8.4.4\n")
    missing = tmp_path / "missing.txt"          # 无文件 → 该源空集合
    multi = tmp_path / "multi"                   # 多文件源(_path 是目录,
    multi.mkdir()                                # 读自报 _files,跳过残缺项)
    m1 = multi / "a.netset"; m1.write_text("1.2.3.4\n")
    m2 = multi / "b.netset"; m2.write_text("8.8.8.8\n")
    m3 = multi / "stale.tmp"; m3.write_text("4.4.4.4\n")
    m = origin_map([_fake_source("has", has),
                    _fake_source("lacks", lacks),
                    _fake_source("gone", missing),
                    _fake_source("agg", multi,
                                 files=[m1, m2, multi / "c.netset"])],
                   ["1.2.3.4", "5.6.7.8", "8.8.8.8", "4.4.4.4"])
    assert m["1.2.3.4"] == {"has", "agg"}       # 目录内自报清单命中
    assert m["5.6.7.8"] == {"has"}              # CIDR 掩码剥除后命中
    assert m["8.8.8.8"] == {"lacks", "agg"}
    assert m["4.4.4.4"] == set()                # .tmp 残件不在 _files → 不计
    assert all("gone" not in v for v in m.values())       # 文件缺失不贡献


# ── estimate:LSO 剔除自采样 pair ─────────────────────────────────

def test_estimate_lso_drops_self_sampled():
    ps = {"a": {("1.2.3.4", "t"), ("5.6.7.8", "t")},
          "b": {("1.2.3.4", "t"), ("7.7.7.7", "t")}}
    ev = Events(pair_sets=ps, monopoly_ctypes=set(),
                per_source={"a": SourceEvents(n=2, k=0, by_ctype={"t": (2, 0)}),
                            "b": SourceEvents(n=2, k=0, by_ctype={"t": (2, 0)})})
    origin = {"1.2.3.4": {"a"}, "5.6.7.8": {"a"}}   # a 的 pair 全部自采样
    sc = {s.source: s for s in estimate(ev, origin=origin)}
    assert sc["a"].theta is None and sc["a"].n == 0
    assert sc["a"].evidence is False    # 全剔空 → no-signal 分支(诚实结果)
    assert sc["b"].theta is not None    # b 不在 origin → 证据保留


def test_estimate_lso_partial_drop_recomputes_nk():
    a_ips = {("10.0.0.1", "t"), ("10.0.0.2", "t"),
             ("10.0.0.3", "t"), ("10.0.0.4", "t")}
    c_ips = {("10.0.0.1", "t"), ("10.1.1.1", "t"), ("10.1.1.2", "t"),
             ("10.1.1.3", "t"), ("10.1.1.4", "t")}
    ps = {"a": a_ips, "c": c_ips}           # OC(a,c)=1/4 ≤ 0.30 → 独立
    ev = Events(pair_sets=ps, monopoly_ctypes=set(),
                per_source={"a": SourceEvents(n=4, k=1, by_ctype={"t": (4, 1)}),
                            "c": SourceEvents(n=5, k=1, by_ctype={"t": (5, 1)})})
    origin = {"10.0.0.1": {"a"}}            # 仅剔 a 的自采样 pair
    base = {s.source: s for s in estimate(ev)}
    lso = {s.source: s for s in estimate(ev, origin=origin)}
    assert (base["a"].n, base["a"].k) == (4, 1)
    assert (lso["a"].n, lso["a"].k) == (3, 0)   # 被佐证 pair 恰是被剔的那个
    assert lso["a"].evidence is False
    assert (lso["c"].n, lso["c"].k) == (5, 1)   # LSO 只剔本源视角,他不失证


def test_estimate_without_origin_unchanged():
    ps = {"a": {("1.2.3.4", "t"), ("5.6.7.8", "t")},
          "b": {("1.2.3.4", "t")}}
    ev = Events(pair_sets=ps, monopoly_ctypes=set(),
                per_source={"a": SourceEvents(n=2, k=1, by_ctype={"t": (2, 1)}),
                            "b": SourceEvents(n=1, k=1, by_ctype={"t": (1, 1)})})
    assert estimate(ev, {"a": 0.9}, 10) == estimate(
        ev, {"a": 0.9}, 10, origin=None)    # 显式 None ≡ 默认缺省
    # 金样本钉住现状语义(兼容锁):rho = LOO 市场 θ̂ = (w·ρ+k)/(w+n)
    sc = {s.source: s for s in estimate(ev, {"a": 0.9}, w=10, origin=None)}
    assert sc["a"].rho == pytest.approx((1 + 0.5) / (1 + 1))   # 仅 b 贡献 (1,1)
    assert sc["a"].theta == pytest.approx((10 * 0.75 + 1) / 12)
    assert (sc["a"].n, sc["a"].k) == (2, 1)
    assert sc["b"].rho == pytest.approx((1 + 0.5) / (2 + 1))   # 仅 a 贡献 (2,1)
    assert sc["b"].theta == pytest.approx((10 * 0.5 + 1) / 11)
    assert sc["a"].declared_r == 0.9 and sc["b"].declared_r is None


# ── run_dsem:同规则剔除后进 EM ───────────────────────────────────

def test_run_dsem_origin_drops_self_sampled():
    ps = {"a": {("1.2.3.4", "t"), ("5.6.7.8", "t")},
          "b": {("1.2.3.4", "t"), ("9.9.9.9", "t"), ("7.7.7.7", "t")}}
    origin = {"1.2.3.4": {"a"}, "5.6.7.8": {"a"}}   # a 全剔 → 退出 EM
    base = run_dsem(ps, {"a": 0.8, "b": 0.7})
    lso = run_dsem(ps, {"a": 0.8, "b": 0.7}, origin=origin)
    assert "a" in {k[0] for k in base["pi_hat"]}
    assert {k[0] for k in lso["pi_hat"]} == {"b"}


# ── 接线:run_suite 报告 lso 键 ──────────────────────────────────

def _fleet_lookup():
    rows = []
    for i in range(12):
        ip = f"10.0.0.{i}"
        srcs = ["a"] + (["b"] if i % 2 == 0 else [])
        rows.append((ip, "spam", srcs))

    def lookup_fn(x):
        res = {"classifications": {}}
        for ip, ctype, srcs in rows:
            if ip == x:
                res["classifications"][ctype] = {"sources": [
                    {"source": s, "value": True, "reliability": 0.5,
                     "authoritative": False} for s in srcs]}
        return res
    return lookup_fn


def _fleet_corpus():
    return Corpus(benchmark={"spam": [f"10.0.0.{i}" for i in range(12)]})


def test_run_suite_dual_track_lso():
    base = run_suite(_fleet_lookup(), _fleet_corpus())
    assert base["lso"] is False and base["scores_lso"] is None  # 旧基:无视图
    origin = {f"10.0.0.{i}": {"a"} for i in range(12)}
    result = run_suite(_fleet_lookup(), _fleet_corpus(), origin=origin)
    assert result["lso"] is True                  # LSO advisory 视图在场
    # 双轨制(09-02 A2 先例):主表 scores 与全部 checks 恒旧基,逐字段一致
    # —— 月轮 T 检查序列可比,LSO 不进 checks
    assert result["scores"] == base["scores"]
    assert result["checks"] == base["checks"]
    main = {s.source: s for s in result["scores"]}
    lso = {s.source: s for s in result["scores_lso"]}
    assert main["a"].theta is not None            # 主表保留原值
    assert lso["a"].theta is None and lso["a"].n == 0   # 被剔源 advisory no-signal
    assert lso["b"].theta is not None


def test_model_report_lso_advisory_section(tmp_path):
    from ipdb._eval.suite import write_model_report
    origin = {f"10.0.0.{i}": {"a"} for i in range(12)}
    result = run_suite(_fleet_lookup(), _fleet_corpus(), origin=origin)
    md, js = write_model_report(result, tmp_path)
    text = md.read_text()
    assert "## LSO advisory (debiased)" in text
    assert text.count("| source | theta |") == 2   # 旧表 + LSO 表同列格式
    payload = json.loads(js.read_text())
    assert payload["lso"] is True and payload["scores_lso"]
    rows = {r["source"]: r for r in payload["scores_lso"]}
    assert rows["a"]["theta"] is None and rows["a"]["n"] == 0


def test_dsem_report_dual_track_lso(tmp_path):
    from ipdb._eval import dsem_cli
    origin = {f"10.0.0.{i}": {"a"} for i in range(12)}
    res = dsem_cli.run_dsem_report(_fleet_lookup(), _fleet_corpus(),
                                   {"a": 0.8, "b": 0.7}, out_dir=tmp_path,
                                   origin=origin)
    # fair fight / dsem 主视图 = 旧基(结构不动,a 仍在 headline)
    assert set(res["dsem"]) == {"pi_hat", "spread", "headline",
                                "solo_share", "theta0"}
    assert res["dsem"]["headline"]["a"] is not None
    assert set(res["fair_fight"]) == {"market_t3", "declared_t3",
                                      "pihat_t3", "pihat_beats_declared"}
    # lso advisory:仅 headline,a 全剔 → None
    assert set(res["lso"]) == {"headline"}
    assert res["lso"]["headline"]["a"] is None
    assert res["lso"]["headline"]["b"] is not None
    json.dumps(res)


# ── 入口装填:中性层进 corpus.neutral ────────────────────────────

def test_cli_entry_loads_neutral_asset():
    from ipdb._eval.__main__ import _load_corpus
    c = _load_corpus()
    assert len(c.neutral) == 600                   # W0 层2 静态资产
    assert "8.8.8.8" in c.all_ips()                # 中性层进 all_ips → 进快照
