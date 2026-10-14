"""月轮报告 v2 测试 (S28 记分卡 / S30 行动区块 / S24 锚对 OC / S6 年度
递减 / S12+S17 换版注记 / Q22 诊断层统计)。

fixtures 全 fake, 无引擎/DB 依赖: readout 手工按 T8 layered_readout 输出
契约构造; model_history 按 suite.write_model_report JSON 形状; sources =
带 .name/.provenance_tier 假对象(测试假注入, T3 真源同形状)。锚对 OC
快照经真实 export_source_keysets 落盘(不手造 meta.json)。
"""
import gzip
import json
from datetime import date, timedelta
from pathlib import Path

from ipdb._eval.keysets import export_source_keysets
from ipdb._eval.monthly import (
    CARRIED,
    DONE,
    OPEN,
    ActionItem,
    compose_action_block,
    compose_monthly_md,
    load_dispositions,
    render_anchor_oc,
    render_consensus_diag,
    render_scorecard,
)

DAY = 86400
BASE = 1_700_000_000


# ── fixtures ───────────────────────────────────────────────────


def _ok_block(hits=2, rate=0.2, k_all=None, k_nh=None, **extra):
    block = {"status": "OK", "hits": hits, "rate": rate,
             "k_all": k_all if k_all is not None else {"1": hits},
             "k_nonhoneypot": k_nh if k_nh is not None else {"1": hits},
             "ctype_mix": {"spam": hits}}
    block.update(extra)
    return block


def _no_layer_block():
    return {"status": "NO-LAYER", "hits": None, "rate": None,
            "k_all": None, "k_nonhoneypot": None, "ctype_mix": None}


def _readout(**over):
    ro = {
        "layers": {
            "truth": _ok_block(split_by_long_memory=None),
            "infra": _ok_block(),
            "neutral": _ok_block(),
            "consensus": _ok_block(),
        },
        "intersection_audit": {k: {"removed_overlap": 0, "notes": []}
                               for k in ("truth", "infra", "neutral", "consensus")},
        "degraded": False,
        "derived_only_corroboration": 0,
    }
    ro.update(over)
    return ro


class _Src:
    def __init__(self, name, tier="B"):
        self.name, self.provenance_tier = name, tier


def _model_report(gen, scores, movers):
    return {"kind": "model", "generated_at": gen,
            "scores": [{"source": n, "theta": t} for n, t in scores],
            "movers": movers}


def _prev(id, status, deadline="2026-09-01", title="旧待办", source="truth"):
    return ActionItem(id=id, title=title, source=source,
                      deadline=deadline, status=status)


# ── load_dispositions ──────────────────────────────────────────


def test_load_dispositions_reads_human_file(tmp_path):
    (tmp_path / "dispositions.json").write_text(json.dumps(
        {"truth-2026-09": "DONE", "last_annual_review": "2026-01"}))
    d = load_dispositions(tmp_path)
    assert d["truth-2026-09"] == "DONE"
    assert d["last_annual_review"] == "2026-01"


def test_load_dispositions_missing_file_empty(tmp_path):
    assert load_dispositions(tmp_path) == {}


# ── compose_action_block: 生成规则 ─────────────────────────────


def test_no_layer_generates_item_naming_layer():
    today = date(2026, 10, 14)
    ro = _readout()
    ro["layers"]["consensus"] = _no_layer_block()
    ro["degraded"] = True
    items = compose_action_block(ro, [], {}, today)
    new = [i for i in items if i.id == "consensus-2026-10"]
    assert len(new) == 1
    assert new[0].status == OPEN
    assert "consensus" in new[0].title          # title 点名层
    assert new[0].deadline == (today + timedelta(days=35)).isoformat()


def test_k_nonhoneypot_all_zero_ok_layer_generates_item():
    ro = _readout()
    ro["layers"]["truth"]["k_nonhoneypot"] = {0: 4}   # 有命中但全 0 非蜜罐源
    items = compose_action_block(ro, [], {}, date(2026, 10, 14))
    assert any(i.id == "truth-k0-2026-10" and "truth" in i.title for i in items)
    # 混合直方图与零命中层不触发
    ro2 = _readout()
    ro2["layers"]["truth"]["k_nonhoneypot"] = {0: 1, 2: 3}
    ro2["layers"]["infra"]["k_nonhoneypot"] = {}
    got = compose_action_block(ro2, [], {}, date(2026, 10, 14))
    assert got == []


def test_pool_exhaustion_over_10pct_generates_item():
    ro = _readout(assembly_stats={"expected_pool": 570, "actual": 500})
    items = compose_action_block(ro, [], {}, date(2026, 10, 14))
    assert any(i.id == "consensus-pool-2026-10" for i in items)
    # <10% 竭率与 stats 缺席都不触发(宁少算待办)
    ok_ro = _readout(assembly_stats={"expected_pool": 570, "actual": 520})
    assert compose_action_block(ok_ro, [], {}, date(2026, 10, 14)) == []
    assert compose_action_block(_readout(), [], {}, date(2026, 10, 14)) == []


# ── compose_action_block: 状态机 ───────────────────────────────


def test_prev_open_without_disposition_becomes_carried_deadline_moves():
    today = date(2026, 11, 5)
    prev = [_prev("truth-2026-09", OPEN)]
    items = compose_action_block(_readout(), prev, {}, today)
    assert len(items) == 1
    assert items[0].id == "truth-2026-09"        # 上轮 id 保留
    assert items[0].status == CARRIED
    assert items[0].deadline == (today + timedelta(days=35)).isoformat()


def test_prev_done_and_disposition_done_never_reappear():
    prev = [_prev("a-2026-09", DONE), _prev("b-2026-09", OPEN)]
    dispositions = {"b-2026-09": "DONE"}
    assert compose_action_block(_readout(), prev, dispositions,
                                date(2026, 11, 5)) == []


def test_disposition_open_with_note_keeps_open():
    prev = [_prev("a-2026-09", OPEN)]
    items = compose_action_block(_readout(), prev, {"a-2026-09": "OPEN"},
                                 date(2026, 11, 5))
    assert items[0].status == OPEN


def test_same_month_regenerate_dedupes_by_id():
    # 同月内重跑: 上轮同 id 携带项在位, 规则不再生成重复行
    today = date(2026, 10, 14)
    ro = _readout()
    ro["layers"]["truth"] = _no_layer_block()
    prev = [_prev("truth-2026-10", OPEN, title="truth 层 NO-LAYER")]
    items = compose_action_block(ro, prev, {}, today)
    assert [i.id for i in items].count("truth-2026-10") == 1


# ── render_scorecard ───────────────────────────────────────────


def test_scorecard_quartile_bands_by_rank():
    scores = [(f"s{i}", 0.9 - i * 0.1) for i in range(8)]
    movers = [f"s{i}" for i in range(8)]
    hist = [_model_report("2026-10-01", scores, movers)]
    rows = render_scorecard(hist, [_Src(f"s{i}") for i in range(8)],
                            today=date(2026, 10, 14))
    by = {r[0]: r for r in rows}
    assert [by[f"s{i}"][1] for i in range(8)] == list("AABBCCDD")
    # pinned(θ=None 不入 movers)无档
    hist2 = [_model_report("2026-10-01", scores + [("pinned", None)],
                           movers)]
    rows2 = render_scorecard(hist2, [_Src(f"s{i}") for i in range(8)]
                             + [_Src("pinned")], today=date(2026, 10, 14))
    assert dict((r[0], r) for r in rows2)["pinned"][1] == "—"


def test_scorecard_90d_window_excludes_old_reports():
    hist = [
        _model_report("2026-01-05", [("a", 0.0)], ["a"]),   # 老报告出局
        _model_report("2026-09-01", [("a", 0.4)], ["a"]),
        _model_report("2026-10-01", [("a", 0.6)], ["a"]),
    ]
    rows = render_scorecard(hist, [_Src("a")], today=date(2026, 10, 14))
    assert rows[0][3] == "0.500"


def test_scorecard_redundency_from_oc_latest_else_na():
    hist = [_model_report("2026-10-01", [("a", 0.5), ("b", 0.4)],
                          ["a", "b"])]
    rows = render_scorecard(hist, [_Src("a"), _Src("b")],
                            oc_latest={"a": 0.123}, today=date(2026, 10, 14))
    by = {r[0]: r for r in rows}
    assert by["a"][2] == "12.3%" and by["b"][2] == "N/A"
    assert by["a"][4] == "B"


# ── render_consensus_diag (Q22) ────────────────────────────────


def test_consensus_diag_renders_present_and_na():
    full = render_consensus_diag({"pool": 570, "contributing_sources": 42,
                                  "catalog_excluded": 3, "desync": 7})
    assert any("570" in l for l in full)
    assert any("42" in l for l in full)
    assert any("目录形排除" in l and "3" in l for l in full)
    assert any("脱同步" in l and "7" in l for l in full)
    empty = render_consensus_diag({})
    assert len(empty) == 4 and all("N/A" in l for l in empty)


# ── render_anchor_oc (S24) ─────────────────────────────────────


def _write_run(root: Path, run_id: str, day: float, per_source: dict):
    srcs = []
    for name, ips in per_source.items():
        p = root / "_raw" / f"{run_id}-{name}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(ips) + "\n")
        srcs.append(type("S", (), {"name": name, "_path": p})())
    return export_source_keysets(srcs, root, run_id,
                                  now=BASE + day * DAY)


def test_anchor_oc_uses_latest_run_and_renders_values(tmp_path):
    root = tmp_path / "keysets"
    _write_run(root, "r0", 0, {
        "emerging_threats": ["1.1.1.1"],
        "spamhaus": ["1.1.1.1", "2.2.2.2"],
        "firehol": ["3.3.3.3"],
        "greensnow": ["3.3.3.3"],
    })
    # 最新轮: ET∩SH = 1, min=2 → OC 0.50;greensnow 本轮缺 → 名单缺失
    _write_run(root, "r1", 30, {
        "emerging_threats": ["1.1.1.1", "2.2.2.2"],
        "spamhaus": ["2.2.2.2", "3.3.3.3"],
        "firehol": ["9.9.9.9"],
    })
    lines = render_anchor_oc(root)
    assert lines[0] == ("锚对 OC: emerging_threats×spamhaus = 0.50"
                        "(只监测不设门)")
    assert "firehol×greensnow" in lines[1] and "N/A(名单缺失)" in lines[1]


def test_anchor_oc_missing_dir_never_crashes(tmp_path):
    lines = render_anchor_oc(tmp_path / "nope")
    assert len(lines) == 2
    assert all("N/A(名单缺失)" in l for l in lines)


# ── compose_monthly_md ─────────────────────────────────────────


def _header_meta(**over):
    hm = {
        "eval_env": "monthly",
        "corpus": {"truth": {"version": "v2", "fingerprint": "ff2"}},
        "prev_fingerprints": {"truth": "ff1"},
        "annual": "2026-01",
        "today": date(2026, 10, 14),
        "epsilon": {0.0: 0.1200, 0.05: 0.1140, 0.10: 0.1080},
    }
    hm.update(over)
    return hm


_ITEMS = [
    ActionItem("a-2026-10", "待办一", "truth", "2026-11-18", OPEN),
    ActionItem("b-2026-10", "待办二", "infra", "2026-11-18", OPEN),
    ActionItem("c-2026-09", "待办三", "neutral", "2026-11-18", CARRIED),
    ActionItem("d-2026-09", "已结", "consensus", "2026-11-18", DONE),
]


def test_md_header_disposition_counts_and_all_sections():
    md = compose_monthly_md(
        _readout(), ["①混杂一", "②混杂二"], _ITEMS,
        [("src", "A", "12.3%", "0.500", "B")],
        ["- 池大小: 570", "锚对 OC: firehol×greensnow = N/A(名单缺失)"],
        _header_meta())
    assert "OPEN 2 / CARRIED 1 / DONE 1" in md
    assert "ε=0.05" in md and "0.1140" in md          # F7 三档行
    assert "9 个月" in md and "2026-01" in md         # S6 递减计数
    assert "换版=趋势重置" in md and "S12/S17" in md  # S12/S17 注记
    assert "monthly" in md                            # eval_env
    assert "R10 混杂披露" in md and "①混杂一" in md
    assert "记分卡" in md and "12.3%" in md and "0.500" in md
    assert "锚对 OC" in md and "池大小: 570" in md    # S24 并入诊断节
    assert "人裁终局" in md                           # 声明 r 脚注
    for banned in ("威胁层", "干净层"):      # _Avoid_ 禁词; F1 由
        assert banned not in md                # 「无综合总分」脚注显式声明


def test_md_stable_fingerprint_no_reset_note_and_unset_annual():
    md = compose_monthly_md(
        _readout(), [], [], [], [],
        _header_meta(prev_fingerprints={"truth": "ff2"}, annual=None))
    assert "换版=趋势重置" not in md
    assert "未设" in md


def test_md_empty_action_block_renders_placeholder():
    md = compose_monthly_md(_readout(), [], [], [], [], _header_meta())
    assert "OPEN 0 / CARRIED 0 / DONE 0" in md
