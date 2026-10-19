# backend/ipdb/_eval/matrix.py
"""语义契约矩阵(ADR 0003):对象层 × 标签语义 × 显形通道的合法性空间。

仓内治理数据 matrix.json 是单一真源(与 corpus.json/neutral_ips.json 同层,
进 PR);本模块只做数据模型 + 加载校验,不做现状判定(扫描引擎归
matrix_scan,Task 2)。72 格完备 fail-closed:缺格/多格/未知轴值/坏状态/
坏 provenance = ValueError——治理数据不许静默漂移。

保守默认(ADR 0003):
- legal 必带非空 provenance(no-provenance-no-legal,load 时强制)——出处串
  引用可打开的文档位置(ADR/spec/计划/判例代码注释);
- illegal = 保守默认态,禁带 provenance(合法性依据只属于合法格;降格史
  写 note);初始填充统一 note="conservative-default";
- pending = 违例待裁(可带 note 说明待裁原因)。
初始合法填充只来自计划在案五组裁决(docs/superpowers/plans/
2026-10-18-semantic-matrix.md Task 1 §2),合法格全集由
tests/eval/test_eval_matrix.py 精确钉死;放宽任何一格 = 新裁决 + 改测试。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# 轴取值 = ADR 0003 grill 裁决,精确 4×6×3 = 72 格。通道 token 沿计划/任务
# 简报字面(score|stix|UI);CSV 为 UI 同源序列化,不独立成轴(ADR 0003)。
LAYERS: tuple[str, ...] = ("truth", "infra", "neutral", "consensus")
LABELS: tuple[str, ...] = (
    "malicious", "suspicious", "benign", "informational", "asset", "clean")
CHANNELS: tuple[str, ...] = ("score", "stix", "UI")

# 格值三态(ADR 0003 保守默认)
STATES: tuple[str, ...] = ("legal", "illegal", "pending")

CellKey = tuple[str, str, str]   # (layer, label, channel)

MATRIX_PATH = Path(__file__).parent / "matrix.json"


def cell_id(layer: str, label: str, channel: str) -> str:
    """规范格键 "<layer>|<label>|<channel>"(matrix.json cells 的键形态)。"""
    return f"{layer}|{label}|{channel}"


ALL_CELL_IDS: frozenset[str] = frozenset(
    cell_id(l, b, c) for l in LAYERS for b in LABELS for c in CHANNELS)


@dataclass(frozen=True)
class RuledCell:
    state: str                      # STATES 之一
    provenance: str | None = None   # 仅 legal:非空出处串(在案裁决位置)
    note: str | None = None         # illegal=conservative-default;pending=待裁原因


@dataclass(frozen=True)
class SemanticMatrix:
    """72 格裁决表;cells 键 = CellKey 三元组,经 load_matrix 校验后只含合法键。"""
    cells: dict[CellKey, RuledCell]


def _parse_cell(cid: str, body) -> RuledCell:
    if not isinstance(body, dict):
        raise ValueError(f"matrix cell {cid}: expected object, "
                         f"got {type(body).__name__}")
    extra = set(body) - {"state", "provenance", "note"}
    if extra:
        raise ValueError(f"matrix cell {cid}: unknown fields {sorted(extra)}")
    if "state" not in body:
        raise ValueError(f"matrix cell {cid}: missing state")
    state = body["state"]
    if state not in STATES:
        raise ValueError(f"matrix cell {cid}: unknown state {state!r}")
    provenance, note = body.get("provenance"), body.get("note")
    if state == "legal":
        if not (isinstance(provenance, str) and provenance.strip()):
            raise ValueError(
                f"matrix cell {cid}: legal requires non-empty provenance "
                f"(no-provenance-no-legal, ADR 0003)")
    elif provenance is not None:
        raise ValueError(f"matrix cell {cid}: provenance only allowed on "
                         f"legal cells (state={state!r})")
    return RuledCell(state=state, provenance=provenance, note=note)


def load_matrix(path: Path | str = MATRIX_PATH) -> SemanticMatrix:
    """读矩阵资产并全量校验;任何偏离轴枚举/72 格完备/三态/provenance 规则
    的写法 raise ValueError(fail-closed,不静默容错)。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_axes = {"layers": LAYERS, "labels": LABELS, "channels": CHANNELS}
    axes = data.get("axes")
    if (not isinstance(axes, dict) or set(axes) != set(expected_axes)
            or any(tuple(axes[k]) != v for k, v in expected_axes.items())):
        raise ValueError(f"matrix axes mismatch: {axes!r}")
    raw = data.get("cells")
    if not isinstance(raw, dict):
        raise ValueError("matrix cells: expected object")
    missing = ALL_CELL_IDS - set(raw)
    extra = set(raw) - ALL_CELL_IDS
    if missing or extra:
        raise ValueError(f"matrix cells not complete (72): "
                         f"missing={sorted(missing)} extra={sorted(extra)}")
    cells: dict[CellKey, RuledCell] = {}
    for cid, body in raw.items():
        layer, label, channel = cid.split("|")
        cells[(layer, label, channel)] = _parse_cell(cid, body)
    return SemanticMatrix(cells=cells)


def save_matrix(m: SemanticMatrix, path: Path | str) -> None:
    """序列化落盘(load 的逆);None 字段省略,cells 序 = 三轴乘积序,
    同表重落逐字节等价(测试钉)。"""
    raw_cells = {}
    for (layer, label, channel), c in m.cells.items():
        body = {"state": c.state}
        if c.provenance is not None:
            body["provenance"] = c.provenance
        if c.note is not None:
            body["note"] = c.note
        raw_cells[cell_id(layer, label, channel)] = body
    out = {"axes": {"layers": list(LAYERS), "labels": list(LABELS),
                    "channels": list(CHANNELS)},
           "cells": raw_cells}
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                          encoding="utf-8")
