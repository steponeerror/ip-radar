"""四层读数测试: NO-LAYER 哨兵 / 交集审计 / k 双报 / F5 分拆 / F6 派生 / F7 ε。

fake lookup 注入照 test_eval_ablation.py 模式, 载荷 = LookupResult.to_dict()
形状(classifications 顶层 + threat 嵌 verdict); 快照一律真实落盘回读。
"""
import pytest

from ipdb._eval import config
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
from ipdb._eval.layered import (
    assemble_four_layers,
    epsilon_sensitivity,
    layered_readout,
)
from ipdb._eval.snapshots import load_ip_snapshot


def _save_layer(root, kind, ips, version="v1"):
    save_asset(root / kind, ips, AssetMeta(
        version=version, kind=kind, fingerprint=fingerprint(ips),
        member_count=len(ips), params={}, eval_env="monthly",
        created_at="2026-10-14"))


def _group(ctype, verdict, details):
    return {"type": ctype, "verdict": verdict,
            "detected": verdict in ("malicious", "suspicious"),
            "sources": [{"source": s} for s, _ in details],
            "details": [{"source": s, "verdict": v, "reliability": 0.5}
                        for s, v in details]}


def _hit(ctype, details):
    return {"classifications": {ctype: _group(ctype, "malicious", details)},
            "threat": {"verdict": "malicious", "confidence": 90,
                       "types": [ctype], "is_cdn": False}}


def _miss():
    return {"classifications": {},
            "threat": {"verdict": "benign", "confidence": 0,
                       "types": [], "is_cdn": False}}


def _lookup(results):
    def fn(ip):
        return results.get(ip, _miss())
    return fn


class _Src:
    def __init__(self, name, honeypot):
        self.name, self.honeypot_methodology = name, honeypot


# ── 装配: NO-LAYER 哨兵 ─────────────────────────────────────────


def test_missing_dir_is_no_layer_not_zero(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1"])
    layers = assemble_four_layers(tmp_path)
    assert layers["truth"].status == "OK"
    for kind in ("infra", "neutral", "consensus"):
        assert layers[kind].status == "NO-LAYER"
        assert layers[kind].rate is None      # 恒无 0 冒充(spec §2.3)
        assert layers[kind].members == []


def test_empty_asset_is_no_layer_with_note(tmp_path):
    # T4 carry: 闸全绿但剔光的空资产 ≠ 0 读数层, 同哨兵不同注记
    _save_layer(tmp_path, "infra", [])
    layers = assemble_four_layers(tmp_path)
    lr = layers["infra"]
    assert lr.status == "NO-LAYER" and lr.rate is None
    assert lr.notes == ["empty-asset"]


def test_corrupt_asset_raises_not_silently_skipped(tmp_path):
    _save_layer(tmp_path, "neutral", ["1.1.1.1"])
    (tmp_path / "neutral" / "ips.txt").write_text("9.9.9.9")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        assemble_four_layers(tmp_path)


# ── 装配: 交集审计(优先级 truth>infra>neutral>consensus) ────────


def test_overlap_removed_from_lower_priority_only(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1", "2.2.2.2"])
    _save_layer(tmp_path, "infra", ["2.2.2.2"])
    _save_layer(tmp_path, "neutral", ["1.1.1.1", "3.3.3.3"])
    layers = assemble_four_layers(tmp_path)
    assert layers["truth"].members == ["1.1.1.1", "2.2.2.2"]
    assert layers["truth"].removed_overlap == 0       # 高优先层不剔
    assert layers["infra"].members == [] and layers["infra"].removed_overlap == 1
    assert layers["neutral"].members == ["3.3.3.3"]
    assert layers["neutral"].removed_overlap == 1
    assert any("1.1.1.1" in n and "also in truth" in n
               for n in layers["neutral"].notes)      # 逐 IP 注记
    assert any("2.2.2.2" in n and "also in truth" in n
               for n in layers["infra"].notes)
    assert layers["infra"].rate is None               # 剔光层无读数, 不冒充 0


def test_overlap_ip_not_queried_for_lower_layer(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1"])
    _save_layer(tmp_path, "neutral", ["1.1.1.1", "3.3.3.3"])
    queried = []

    def lookup(ip):
        queried.append(ip)
        return _miss()

    readout = layered_readout(lookup, assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="r")
    assert queried.count("1.1.1.1") == 1             # 只按 truth 查一次
    assert "3.3.3.3" in queried
    assert readout["intersection_audit"]["neutral"]["removed_overlap"] == 1


# ── 读数: k 双报 + ctype_mix ────────────────────────────────────


def test_k_double_report_excludes_honeypot_sources(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1", "2.2.2.2"])
    lookup = _lookup({
        "1.1.1.1": _hit("ssh_bruteforce",
                        [("binarydefense", "malicious"),
                         ("threatfox", "malicious")]),
    })
    layers = assemble_four_layers(tmp_path)
    readout = layered_readout(lookup, layers, out_dir=tmp_path, run_id="r")
    t = readout["layers"]["truth"]
    assert t["hits"] == 1 and t["rate"] == 0.5
    assert t["k_all"] == {2: 1}                       # 2 指控源
    assert t["k_nonhoneypot"] == {1: 1}               # binarydefense ∈ config 集
    assert t["ctype_mix"] == {"ssh_bruteforce": 1}
    assert layers["truth"].k_hist == {2: 1}           # LayerResult 回填 k_all 直方图


def test_k_nonhoneypot_uses_source_attrs_when_given(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1"])
    lookup = _lookup({
        "1.1.1.1": _hit("c2-server",
                        [("mystery_pot", "malicious"),
                         ("threatfox", "malicious")]),
    })
    no_srcs = layered_readout(lookup, assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="a")
    # 未传 sources → 仅 config 集兜底(docstring 语义)
    assert no_srcs["layers"]["truth"]["k_nonhoneypot"] == {2: 1}
    with_srcs = layered_readout(lookup, assemble_four_layers(tmp_path),
                                out_dir=tmp_path, run_id="b",
                                sources=[_Src("mystery_pot", True)])
    assert with_srcs["layers"]["truth"]["k_nonhoneypot"] == {1: 1}


# ── 读数: degraded / NO-LAYER 块 ────────────────────────────────


def test_degraded_true_iff_any_layer_not_ok(tmp_path):
    _save_layer(tmp_path, "neutral", ["3.3.3.3"])
    readout = layered_readout(_lookup({}), assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="r")
    assert readout["degraded"] is True                # truth/infra/consensus 缺
    nl = readout["layers"]["truth"]
    assert nl["status"] == "NO-LAYER" and nl["rate"] is None and nl["hits"] is None


def test_degraded_false_when_all_four_ok(tmp_path):
    for kind in ("truth", "infra", "neutral", "consensus"):
        _save_layer(tmp_path, kind, ["1.1.1.1"])
    readout = layered_readout(_lookup({}), assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="r")
    assert readout["degraded"] is False
    assert all(b["status"] == "OK" for b in readout["layers"].values())


# ── F5 长记忆分拆(仅描述性, 不动主读数) ─────────────────────────


def test_long_memory_split_descriptive_only(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"])
    lookup = _lookup({"1.1.1.1": _hit("spam_source", [("firehol", "malicious")]),
                      "3.3.3.3": _hit("spam_source", [("ipsum", "malicious")])})
    base = layered_readout(lookup, assemble_four_layers(tmp_path),
                           out_dir=tmp_path, run_id="a")
    assert base["layers"]["truth"]["split_by_long_memory"] is None  # 缺名单→键在值 null
    readout = layered_readout(lookup, assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="b",
                              long_memory={"1.1.1.1", "2.2.2.2"})
    t = readout["layers"]["truth"]
    assert t["split_by_long_memory"] == {
        "in": {"hits": 1, "rate": 0.5, "n": 2},
        "out": {"hits": 1, "rate": 0.5, "n": 2}}
    assert t["hits"] == 2 and t["rate"] == 0.5        # 主读数不动
    assert "split_by_long_memory" not in readout["layers"]["consensus"]  # 仅 truth


# ── F6 仅双派生佐证计数 ─────────────────────────────────────────


def test_derived_only_corroboration_counts_pure_derived(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1", "2.2.2.2", "5.5.5.5"])
    _save_layer(tmp_path, "infra", ["9.9.9.9"])
    lookup = _lookup({
        "1.1.1.1": _hit("spam_source", [("firehol", "malicious"),
                                        ("ipsum", "malicious")]),   # k=2 全派生
        "2.2.2.2": _hit("c2-server", [("firehol", "malicious"),
                                      ("threatfox", "malicious")]),  # k=2 含非派生
        "5.5.5.5": _hit("spam_source", [("firehol", "malicious")]),  # k=1 不计
        "9.9.9.9": _hit("spam_source", [("firehol", "malicious"),
                                        ("ipsum", "malicious")]),   # 非 truth 层不计
    })
    readout = layered_readout(lookup, assemble_four_layers(tmp_path),
                              out_dir=tmp_path, run_id="r")
    assert readout["derived_only_corroboration"] == 1


# ── F10 快照: 每层落盘 + 顶层 verdict 展平 ──────────────────────


def test_snapshot_persisted_per_layer_with_top_level_verdict(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1"])
    _save_layer(tmp_path, "neutral", ["8.8.8.8"])
    lookup = _lookup({"1.1.1.1": _hit("ssh_bruteforce",
                                      [("threatfox", "malicious")])})
    layered_readout(lookup, assemble_four_layers(tmp_path),
                    out_dir=tmp_path, run_id="run-x")
    truth_snap = load_ip_snapshot(tmp_path / "snapshots" / "run-x" / "truth.jsonl.gz")
    assert set(truth_snap) == {"1.1.1.1"}
    entry = truth_snap["1.1.1.1"]
    assert "classifications" in entry and "verdict" in entry   # T6 carry: 顶层 verdict
    assert entry["verdict"]["verdict"] == "malicious"          # threat 整块展平
    neutral = load_ip_snapshot(tmp_path / "snapshots" / "run-x" / "neutral.jsonl.gz")
    assert set(neutral) == {"8.8.8.8"}
    assert not (tmp_path / "snapshots" / "run-x" / "infra.jsonl.gz").exists()  # NO-LAYER 不留


# ── asof 透传(T10 前引擎链无 asof 参, 默认普通调用) ─────────────


def test_asof_kwarg_forwarded_only_when_given(tmp_path):
    _save_layer(tmp_path, "truth", ["1.1.1.1"])
    calls = []

    def plain(ip):                     # T10 前真实引擎签名: 无 asof 形参
        calls.append(ip)
        return _miss()

    layered_readout(plain, assemble_four_layers(tmp_path),
                    out_dir=tmp_path, run_id="r")
    assert calls == ["1.1.1.1"]        # asof=None → 普通调用不炸
    with pytest.raises(TypeError):
        layered_readout(plain, assemble_four_layers(tmp_path),
                        out_dir=tmp_path, run_id="r", asof=1.0)  # 响亮失败, T10 接线


# ── F7 ε 敏感性三档 ─────────────────────────────────────────────


def test_epsilon_sensitivity_deterministic_drop_counts():
    hits = [f"10.0.0.{i}" for i in range(1, 21)]      # 20 命中
    a = epsilon_sensitivity(hits, n=200, seed=7)
    assert a == epsilon_sensitivity(hits, n=200, seed=7)           # 逐位同
    assert set(a) == {0.0, 0.05, 0.10}
    assert a[0.0] == pytest.approx(20 / 200)
    assert a[0.05] == pytest.approx(19 / 200)        # 剔 5% 命中
    assert a[0.10] == pytest.approx(18 / 200)        # 剔 10% 命中
    with pytest.raises(ValueError):
        epsilon_sensitivity(hits, n=0, seed=7)
    with pytest.raises(TypeError):                   # seed 必填(significance 同款纪律)
        epsilon_sensitivity(hits, n=200)
