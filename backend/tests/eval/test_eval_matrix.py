# backend/tests/eval/test_eval_matrix.py
"""语义契约矩阵资产(ADR 0003 Task 1):72 格完备、三态与 provenance 规则
(legal 无出处 = 拒载)、未知轴值/坏结构 fail-closed、load/save 往返、
初始填充 = 计划在案五组精确钉死。

轴取值与保守默认语义权威:docs/superpowers/plans/2026-10-18-semantic-matrix.md
Global Constraints + Task 1;指控标签集合复用 _types._ACCUSING(指控章单一口径,
anchors.py 同款借道)。2026-10-19 首轮裁决(案一维持/案二案三转 legal)
权威:docs/superpowers/plans/2026-10-19-matrix-ruling1.md——放宽任何格 =
新裁决 + 改本文件断言。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval.matrix import (
    ALL_CELL_IDS,
    CHANNELS,
    LABELS,
    LAYERS,
    MATRIX_PATH,
    cell_id,
    load_matrix,
    save_matrix,
)
from ipdb._types import _ACCUSING

# 计划 Task 1 §2 的五组在案裁决 → 合法格全集(精确集合断言的期望值)
_TRUTH_CONSENSUS_IDS = {
    cell_id(layer, label, ch)
    for layer in ("truth", "consensus")
    for label in _ACCUSING
    for ch in CHANNELS
}
# 案二(2026-10-19):asset×{UI,stix}×{infra,neutral,consensus} 6 格转 legal
# (infra|asset|UI 初始填充已在 legal,案二维持并补裁决出处)。
_ASSET_CASE2_IDS = {
    cell_id(layer, "asset", ch)
    for layer in ("infra", "neutral", "consensus")
    for ch in ("UI", "stix")
}
EXPECTED_LEGAL_IDS = _TRUTH_CONSENSUS_IDS | _ASSET_CASE2_IDS | {
    cell_id(layer, "clean", ch) for layer in LAYERS for ch in CHANNELS
} | {
    # 案三(2026-10-19):consensus|informational|UI——archival 补充证词
    # 非新指控,已指控对象上的对照显形合法。
    cell_id("consensus", "informational", "UI"),
}

# 案一(2026-10-19):infra 威胁轴 7 格维持非法,note 自 conservative-default
# 升 ruling-confirmed(裁决记录:docs/superpowers/plans/
# 2026-10-19-matrix-ruling1.md 案一)。
RULING1_CONFIRMED_NOTE = "ruling-confirmed(2026-10-19 案一)"
CASE1_STAY_ILLEGAL_IDS = (
    {cell_id("infra", label, ch)
     for label in ("malicious", "suspicious") for ch in CHANNELS}
    | {cell_id("infra", "informational", "UI")})


def _repo_matrix_json() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _mutated_asset(tmp_path: Path, mutate) -> Path:
    """仓内 matrix.json 的副本 + 一次变异 → 落盘路径(load 校验的单点用例)。"""
    data = _repo_matrix_json()
    mutate(data)
    p = tmp_path / "matrix.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ── 仓内资产的结构完备性 ────────────────────────────────────────

def test_repo_asset_axes_enums():
    raw = _repo_matrix_json()
    assert raw["axes"] == {
        "layers": list(LAYERS), "labels": list(LABELS),
        "channels": list(CHANNELS)}
    assert (len(LAYERS), len(LABELS), len(CHANNELS)) == (4, 6, 3)


def test_repo_asset_72_cells_complete():
    m = load_matrix()
    assert set(m.cells) == {
        (l, b, c) for l in LAYERS for b in LABELS for c in CHANNELS}
    assert len(m.cells) == 72


def test_repo_asset_states_three_valued():
    m = load_matrix()
    assert {c.state for c in m.cells.values()} <= {"legal", "illegal", "pending"}
    assert {c.state for c in m.cells.values()} == {"legal", "illegal"}


def test_repo_asset_provenance_and_note_rules():
    m = load_matrix()
    for key, c in m.cells.items():
        if c.state == "legal":
            # no-provenance-no-legal:出处串非空且含可打开的文档位置
            assert isinstance(c.provenance, str) and c.provenance.strip()
            assert ("docs/" in c.provenance) or ("backend/" in c.provenance), key
        else:
            assert c.provenance is None, key          # 依据只属于合法格
        if c.state == "illegal":
            # 非法格 note ∈ {保守默认, 案一裁决确认};案一之外不许新 note 词
            assert c.note in ("conservative-default",
                              RULING1_CONFIRMED_NOTE), key
    # 案一 7 格精确钉死:ruling-confirmed 只落在 infra 威胁轴维持非法格上
    confirmed = {cell_id(*k) for k, c in m.cells.items()
                 if c.note == RULING1_CONFIRMED_NOTE}
    assert confirmed == CASE1_STAY_ILLEGAL_IDS


def test_repo_asset_initial_fill_exactly_documented_groups():
    m = load_matrix()
    legal = {cell_id(*k) for k, c in m.cells.items() if c.state == "legal"}
    assert legal == EXPECTED_LEGAL_IDS
    # 25(初始填充)→ 31(2026-10-19 首轮裁决:案二 +5、案三 +1;
    # 计划原文「25→32」系对 infra|asset|UI 重复计数,裁决记录在案)
    assert len(legal) == 31
    assert ALL_CELL_IDS - legal == {
        cell_id(*k) for k, c in m.cells.items() if c.state == "illegal"}


# ── fail-closed:坏结构一律 ValueError ──────────────────────────

def test_load_rejects_legal_without_provenance(tmp_path):
    def mutate(d):
        d["cells"]["truth|malicious|score"] = {"state": "legal"}
    with pytest.raises(ValueError, match="provenance"):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_provenance_on_illegal(tmp_path):
    def mutate(d):
        d["cells"]["infra|benign|score"] = {
            "state": "illegal", "provenance": "docs/adr/0001-x.md"}
    with pytest.raises(ValueError, match="provenance"):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_unknown_state(tmp_path):
    def mutate(d):
        d["cells"]["neutral|clean|UI"]["state"] = "maybe"
    with pytest.raises(ValueError, match="unknown state"):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_unknown_cell_field(tmp_path):
    def mutate(d):
        d["cells"]["neutral|clean|UI"]["prov"] = "docs/x.md"
    with pytest.raises(ValueError, match="unknown fields"):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_unknown_axis_value_in_axes(tmp_path):
    def mutate(d):
        d["axes"]["channels"] = ["score", "stix", "UI", "csv"]
    with pytest.raises(ValueError, match="axes"):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_unknown_cell_key(tmp_path):
    def mutate(d):
        cells = d["cells"]
        cells["truth|malicious|csv"] = cells.pop("truth|malicious|score")
    with pytest.raises(ValueError, match="missing="):
        load_matrix(_mutated_asset(tmp_path, mutate))


def test_load_rejects_extra_and_missing_cells(tmp_path):
    def drop(d):
        d["cells"].pop("neutral|clean|score")
    with pytest.raises(ValueError, match="missing="):
        load_matrix(_mutated_asset(tmp_path, drop))

    def dupe(d):
        d["cells"]["truth|malicious|score|dup"] = {"state": "illegal"}
    with pytest.raises(ValueError, match="extra="):
        load_matrix(_mutated_asset(tmp_path, dupe))


def test_load_pending_cell_with_note(tmp_path):
    def mutate(d):
        d["cells"]["infra|informational|UI"] = {
            "state": "pending", "note": "8.8.8.8 事故格,待用户裁决(ADR 0003)"}
    m = load_matrix(_mutated_asset(tmp_path, mutate))
    assert m.cells[("infra", "informational", "UI")].state == "pending"


# ── load/save 往返 ──────────────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    m = load_matrix()
    p = tmp_path / "matrix.json"
    save_matrix(m, p)
    assert load_matrix(p).cells == m.cells
    # 再落一轮逐字节等价(同 cells 序 → 确定性序列化)
    p2 = tmp_path / "matrix2.json"
    save_matrix(load_matrix(p), p2)
    assert p.read_bytes() == p2.read_bytes()
