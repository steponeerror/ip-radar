"""月轮报告 v2 测试 (S28 记分卡 / S30 行动区块 / S24 锚对 OC / S34 偷泊
诊断 / S6 年度递减 / S12+S17 换版注记 / Q22 诊断层统计)。

fixtures 全 fake, 无引擎/DB 依赖: readout 手工按 T8 layered_readout 输出
契约构造; model_history 按 suite.write_model_report JSON 形状; sources =
带 .name/.provenance_tier 假对象(测试假注入, T3 真源同形状)。锚对 OC
快照经真实 export_source_keysets 落盘(不手造 meta.json)。
"""
import gzip
import json
import tempfile
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
    load_leg_status,
    render_anchor_oc,
    render_consensus_diag,
    render_leg_status,
    render_scorecard,
    render_steal_parking_diag,
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


def test_same_month_done_disposition_suppresses_regeneration():
    # 同月重跑: 上轮项人裁 DONE 后, 仍触发的规则不得复活同 id 为 OPEN
    # (裁决 "DONE 不再现"; 复现 Critical: DONE continue 未记 seen)
    today = date(2026, 10, 14)
    ro = _readout()
    ro["layers"]["truth"] = _no_layer_block()      # 规则同月再触发
    prev = [_prev("truth-2026-10", OPEN, title="truth 层 NO-LAYER")]
    items = compose_action_block(ro, prev, {"truth-2026-10": "DONE"}, today)
    assert items == []                              # 消账项不复活


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


# ── render_steal_parking_diag (S34) ────────────────────────────


def test_steal_parking_rc_same_keyset_changed_names_source(tmp_path):
    # rc 3→3 恒定而键集 +1/−1: 模板行点名源(S34 偷泊嫌疑→人裁)
    root = tmp_path / "keysets"
    _write_run(root, "r0", 0, {"et": ["1.1.1.1", "2.2.2.2", "3.3.3.3"]})
    _write_run(root, "r1", 30, {"et": ["1.1.1.1", "2.2.2.2", "4.4.4.4"]})
    lines = render_steal_parking_diag(root)
    assert len(lines) == 1
    assert lines[0].startswith("偷泊嫌疑: et")
    assert "rc 恒定 3" in lines[0] and "+1" in lines[0] and "-1" in lines[0]
    assert "人裁" in lines[0]


def test_steal_parking_rc_changed_or_keyset_same_no_line(tmp_path):
    # rc 已变 → 非偷泊; 键集没变 → 无嫌疑行(宁少算)
    root = tmp_path / "keysets"
    _write_run(root, "r0", 0, {"growing": ["1.1.1.1", "2.2.2.2"],
                               "frozen": ["9.9.9.9"]})
    _write_run(root, "r1", 30, {"growing": ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                                "frozen": ["9.9.9.9"]})
    assert render_steal_parking_diag(root) == []


def test_steal_parking_fewer_than_two_runs(tmp_path):
    root = tmp_path / "keysets"
    _write_run(root, "r0", 0, {"et": ["1.1.1.1"]})
    assert render_steal_parking_diag(root) == ["偷泊诊断: 快照不足(<2 轮)"]
    assert render_steal_parking_diag(tmp_path / "nope") == \
        ["偷泊诊断: 快照不足(<2 轮)"]


def test_steal_parking_missing_member_skips_all_missing_line(tmp_path):
    # 最新轮该源 gz 缺席 → 跳过不炸; 无可比对源 → 单行声明
    root = tmp_path / "keysets"
    _write_run(root, "r0", 0, {"et": ["1.1.1.1", "2.2.2.2"]})
    _write_run(root, "r1", 30, {"et": ["1.1.1.1", "3.3.3.3"]})
    (root / "r1" / "et.txt.gz").unlink()
    assert render_steal_parking_diag(root) == ["偷泊诊断: 无可比对"]


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


def test_md_reset_note_excludes_rolling_consensus():
    # 终审 P1-3b: 共识代理层=滚动语料(Q22 诊断层裁决), 月月自然更替≠
    # 趋势重置事件 → 豁免换版注记(声明行替代静默省略); 稳定层实变仍注记
    hm = _header_meta(
        corpus={"truth": {"version": "v2", "fingerprint": "ff2"},
                "infra": {"version": "i9", "fingerprint": "if9"},
                "consensus": {"version": "c9", "fingerprint": "cf9"}},
        prev_fingerprints={"truth": "ff1", "infra": "if8",
                           "consensus": "cf1"})
    md = compose_monthly_md(_readout(), [], [], [], [], hm)
    reset = [l for l in md.splitlines() if "换版=趋势重置" in l]
    assert reset and "infra" in reset[0] and "truth" in reset[0]
    assert "consensus" not in reset[0]          # 滚动层不进注记行
    assert "滚动语料" in md                      # 豁免声明行在场
    # 仅 consensus 指纹变 → 不出换版行
    hm2 = _header_meta(
        corpus={"consensus": {"version": "c9", "fingerprint": "cf9"}},
        prev_fingerprints={"consensus": "cf1"})
    md2 = compose_monthly_md(_readout(), [], [], [], [], hm2)
    assert "换版=趋势重置" not in md2
    assert "滚动语料" in md2


def test_md_reset_note_truth_two_arm_scanner_ranges_join():
    """SR-T2 D3(#213 / ADR 0011): S17 趋势重置注记 —— ops 两臂真指纹换版。"""
    with tempfile.TemporaryDirectory() as td:
        from ipdb._eval.layer_builders import scanner_ranges_prefixes
        from ipdb._eval.truth_layer import build_truth_layer
        tmp = Path(td)
        csv = tmp / "scanner_ranges.csv"
        csv.write_text("40.124.175.0/24,Stretchoid\n2600:1f00::/24,Amazon\n",
                       encoding="utf-8")
        # 与 test_eval_truth_layer._BIG_RANGES 同构: 10.0.0.0 起步 10k 段
        base = 167_772_160  # int("10.0.0.0")
        big = [(base + i * 256, 256, "20000101") for i in range(10_000)]
        raw = ["40.124.175.29", "5.1.0.5", "9.9.9.9"]
        legacy = ["10.0.0.0/8"]
        a_dir, b_dir = tmp / "a", tmp / "b"
        meta_a = build_truth_layer(raw, big, legacy, a_dir, "v1")
        meta_b = build_truth_layer(raw, big,
                                   legacy + scanner_ranges_prefixes(csv),
                                   b_dir, "v1")
        assert meta_a.fingerprint != meta_b.fingerprint  # 换版前提
        md = compose_monthly_md(
            _readout(), [], [], [], [],
            _header_meta(corpus={"truth": {"version": meta_b.version,
                                            "fingerprint": meta_b.fingerprint}},
                         prev_fingerprints={"truth": meta_a.fingerprint}))
        reset = [ln for ln in md.splitlines() if "换版=趋势重置" in ln]
        assert reset, "换版未出注记行"
        assert "truth" in reset[0] and meta_a.fingerprint in reset[0] \
            and meta_b.fingerprint in reset[0]


def test_md_empty_action_block_renders_placeholder():
    md = compose_monthly_md(_readout(), [], [], [], [], _header_meta())
    assert "OPEN 0 / CARRIED 0 / DONE 0" in md


def test_md_steal_parking_lines_after_consensus_default_none():
    md = compose_monthly_md(
        _readout(), [], [], [], ["- 池大小: 570"], _header_meta(),
        steal_parking_lines=["偷泊嫌疑: et (rc 恒定 3, 键集 +1/-1)→人裁"])
    assert md.index("池大小") < md.index("偷泊嫌疑: et")  # Q22 行之后
    default = compose_monthly_md(_readout(), [], [], [], ["- 池大小: 570"],
                                 _header_meta())
    assert "偷泊" not in default  # 缺省 None → 节不变(schema-stable)


def test_md_anchor_family_hades_note_static_line():
    """#233 交付块4(ADR 0013):锚读数族可操纵面注记 = 头块常驻静态
    披露行(HADES NDSS'25 式投毒),不随数据变、无可选参数(共识豁免
    行同律);落点=腿级行之后(头块尾)。"""
    md = compose_monthly_md(_readout(), [], [], [], [], _header_meta())
    note = [l for l in md.splitlines() if "HADES" in l]
    assert note and "NDSS'25" in note[0], md
    assert "人裁终局" in note[0]          # 与声明 r 同口径
    assert "不持门" in note[0]
    # 落点:腿级行之后(头块尾静态注记)
    md2 = compose_monthly_md(_readout(), [], [], [], [], _header_meta(),
                             leg_status_lines=["- 腿级状态(#193 C5): model=rc0"])
    assert md2.index("腿级状态") < md2.index("HADES")


# ── #193 C5: 腿级状态件读法 + 月报腿级行 ───────────────────────

def test_load_leg_status_picks_latest_and_skips_bad(tmp_path):
    """月轮壳写 leg-status-<ts>.json(readout 渲染前件);读法同
    load_prev_northstar 形制: 排序 glob 取最新, 坏件跳过不炸(宽容律)。"""
    (tmp_path / "leg-status-20261024-010101.json").write_text(
        "{ bad json", encoding="utf-8")
    (tmp_path / "leg-status-20261024-010102.json").write_text(
        json.dumps({"schema": "leg-status/1",
                    "legs": {"model": 0, "anchors": 1, "readout": None}}),
        encoding="utf-8")
    leg = load_leg_status(tmp_path)
    assert leg is not None
    assert leg["legs"]["anchors"] == 1 and leg["legs"]["readout"] is None


def test_load_leg_status_missing_returns_none(tmp_path):
    assert load_leg_status(tmp_path) is None  # 首轮无件 → 不虚构


def test_render_leg_status_red_named_null_in_flight():
    lines = render_leg_status({"schema": "leg-status/1",
                               "legs": {"model": 0, "anchors": 1,
                                        "readout": None}})
    joined = "\n".join(lines)
    assert "anchors=rc1" in joined      # 红腿带 rc 点名
    assert "进行中" in joined            # readout null=渲染时本腿在飞
    assert "model=rc0" in joined        # 绿腿全景一行(rcN 紧凑形)
    assert any("腿级红" in l for l in lines)   # 红腿单独点名一行


def test_render_leg_status_all_green_no_red_callout():
    lines = render_leg_status({"schema": "leg-status/1",
                               "legs": {"model": 0, "readout": None}})
    assert not any("腿级红" in l for l in lines)


def test_md_leg_status_lines_position_and_default_none():
    md = compose_monthly_md(
        _readout(), [], [], [], ["- 池大小: 570"], _header_meta(),
        north_star_lines=["- 北星: x"],
        leg_status_lines=["- 腿级状态: model=0 | anchors=1"])
    assert md.index("北星") < md.index("腿级状态") < md.index("## 分层读数")
    default = compose_monthly_md(_readout(), [], [], [], ["- 池大小: 570"],
                                 _header_meta())
    assert "腿级状态" not in default   # 缺省 None 不出(schema-stable)
