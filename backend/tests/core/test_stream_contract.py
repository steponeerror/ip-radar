"""#495 流式协议机读契约:事件形状只写一份,前后端对拍,GET 对 row.result。

后端协议面 = backend/main.py 的三个事件构造函数(_row_event/_progress_event/
_done_event;键集与键序的单一出处,#495 之前 done 字面量在 8 处各写一遍);
前端对侧声明 = frontend/src/api.ts 的 `type StreamEvent`。任何一边改形状、
或在 main.py 重新手写事件字典字面量,这里红。另对拍 GET /api/lookup/{ip}
响应顶层键集与流 row.result 顶层键集(同形红线:LookupResultOut docstring
承诺「与 POST /api/query/stream 每行同构」,test_openapi_contract.py::
TestFieldOutShape 是同一红线的字段级版本),差异只能来自写明理由的豁免表。

start 事件不设构造函数(全仓单点发射,main.py 查询入口一处),其键集直接
从 main.py 的 AST 字面量读 —— 单点漂移照样红。
"""
import ast
import json
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import main
from conftest import SAME_ORIGIN

FRONTEND_API_TS = (Path(__file__).resolve().parents[3]
                   / "frontend" / "src" / "api.ts")
MAIN_PY = Path(main.__file__).resolve()

EVENT_TYPES = ("start", "row", "progress", "done")
CONSTRUCTOR_NAMES = ("_row_event", "_progress_event", "_done_event")
FORBIDDEN_TYPES = ("done", "row", "progress")  # start 不在禁列:无构造函数,单点发射

# 前后端键集豁免表:event → 允许只在一边出现的键。初始为空;往里加条目
# = 协议两边形状分叉,必须在评审里给理由。
PARITY_EXEMPTIONS: dict[str, set[str]] = {}

# GET 对 row.result 的键集豁免表:键名 → 原因。初始为空(LookupResultOut
# 的 docstring 承诺同构,等不等对不上就该查清来历,不该随手豁免)。
GET_VS_ROW_EXEMPTIONS: dict[str, str] = {}


# ── 后端构造函数键集 ────────────────────────────────────────────────

def test_backend_row_progress_key_sets():
    assert set(main._row_event(0, {})) == {"type", "idx", "result"}
    assert set(main._progress_event(0, 0)) == {"type", "done", "total"}


def test_backend_done_success_key_set():
    """成功 done 恰三键。ipv6_unsupported 从构造函数摘掉 = 本用例红 +
    前后端对拍红(变异①的双判据)。"""
    assert set(main._done_event(0, 0)) == {
        "type", "invalid_lines", "ipv6_unsupported"}
    assert "error" not in main._done_event(0, 0)


def test_backend_done_error_variant_carries_code():
    """出错 done 一定带 error + code,且追加在基础键之后
    (键序 = 旧手写字面量,orjson 输出字节不变)。"""
    evt = main._done_event(0, 0, error="boom", code="internal")
    assert list(evt) == ["type", "invalid_lines", "ipv6_unsupported",
                         "error", "code"]
    assert evt["code"] == "internal"


# ── 前端 StreamEvent 解析 ──────────────────────────────────────────

def _parse_stream_event_branches(src: str) -> dict[str, set[str]]:
    """从 api.ts 抽 `type StreamEvent = …;` 联合类型每支的键集。
    小解析器:跨行声明、可选键 `?:`、行尾 // 注释都能处理;分支内的
    `;` 是 TS 成员分隔符,靠花括号配对跳过,语句终止符 = 深度 0 的 `;`。"""
    m = re.search(r"^type StreamEvent\s*=", src, re.M)
    assert m, "frontend/src/api.ts 里找不到 type StreamEvent 联合类型声明"
    i, depth = m.end(), 0
    while i < len(src):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ";" and depth == 0:
            break
        i += 1
    body = src[m.end():i]
    branches: dict[str, set[str]] = {}
    for bm in re.finditer(r"\{([^{}]*)\}", body):
        inner = re.sub(r"//[^\n]*", "", bm.group(1))  # 剥行尾注释
        tm = re.search(r'type\s*:\s*"(\w+)"', inner)
        assert tm, f"StreamEvent 分支缺 type 字面量: {inner!r}"
        keys = set()
        for part in inner.split(";"):
            km = re.match(r"\s*(\w+)\s*\??\s*:", part)
            if km:
                keys.add(km.group(1))
        branches[tm.group(1)] = keys
    return branches


def _start_literal_keys() -> set[str]:
    """start 事件键集,从 main.py 源码的 AST 字面量里读(单点发射)。"""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "type"
                    and isinstance(v, ast.Constant) and v.value == "start"):
                keys = {kk.value for kk in node.keys
                        if isinstance(kk, ast.Constant)}
                assert all(isinstance(x, str) for x in keys)
                return keys  # type: ignore[return-value]
    raise AssertionError("main.py 里找不到 start 事件字面量")


def _backend_event_keys() -> dict[str, set[str]]:
    """后端各事件键集。done 取成功+出错两变体的并集:前端 done 一支同时
    描述两种形状(出错键可选声明),对拍口径 = 全键面。"""
    done_keys = (set(main._done_event(0, 0))
                 | set(main._done_event(0, 0, error="x", code="internal")))
    return {
        "start": _start_literal_keys(),
        "row": set(main._row_event(0, {})),
        "progress": set(main._progress_event(0, 0)),
        "done": done_keys,
    }


def test_frontend_backend_parity():
    """四支键集前后端相等;差异只能来自 PARITY_EXEMPTIONS(初始空)。"""
    fe = _parse_stream_event_branches(
        FRONTEND_API_TS.read_text(encoding="utf-8"))
    be = _backend_event_keys()
    assert sorted(fe) == sorted(EVENT_TYPES), f"前端分支集漂移: {sorted(fe)}"
    for event in EVENT_TYPES:
        exempt = PARITY_EXEMPTIONS.get(event, set())
        only_fe = fe[event] - be[event] - exempt
        only_be = be[event] - fe[event] - exempt
        assert not only_fe, \
            f"{event}: 前端多出的键 {sorted(only_fe)}(豁免表未收录)"
        assert not only_be, \
            f"{event}: 后端多出的键 {sorted(only_be)}(豁免表未收录)"


# ── main.py 事件字面量单出口 ────────────────────────────────────────

def test_no_handwritten_event_literals_outside_constructors():
    """main.py 里 {"type": "done"/"row"/"progress"} 字典字面量只许出现在
    三个构造函数定义体内;别处手写 = 单出口破约,报行号(变异③判据)。"""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    spans = [(n.lineno, n.end_lineno) for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name in CONSTRUCTOR_NAMES]
    assert len(spans) == 3, f"事件构造函数应有且仅有三个: {spans}"
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "type"
                    and isinstance(v, ast.Constant)
                    and v.value in FORBIDDEN_TYPES
                    and not any(lo <= node.lineno <= hi for lo, hi in spans)):
                offenders.append((node.lineno, v.value))
    assert not offenders, f"main.py 手写事件字面量(行号, 类型): {offenders}"


# ── GET /api/lookup/{ip} 对流 row.result ───────────────────────────

@pytest.fixture(autouse=True)
def _tiny_db(tiny_db):
    """CI 逐文件跑序里先 import main 的文件会触发冷启动线程写 data/
    (test_stream_pool.py 同款);tmp 最小库打开查询门。"""


@pytest.fixture(autouse=True)
def _hermetic_gate(monkeypatch):
    """密闭积分门:本文件只对拍形状,不测冷启动门(test_stream_pool 同款)。"""
    monkeypatch.setattr(main._cold_gate, "coverage_building", lambda: False)


def test_get_lookup_keys_match_stream_row_result():
    """同形红线:GET /api/lookup/{ip} 响应顶层键集 == 流 row.result 顶层
    键集。差异先查清来历写进 GET_VS_ROW_EXEMPTIONS(带原因),不许改
    响应内容凑相等。"""
    with TestClient(main.app, headers=SAME_ORIGIN) as client:
        r = client.post("/api/query/stream", json={"ips": ["8.8.8.8"]})
        assert r.status_code == 200
        events = [json.loads(line) for line in r.text.splitlines() if line]
        row = next(e for e in events if e["type"] == "row")
        g = client.get("/api/lookup/8.8.8.8")
        assert g.status_code == 200
    get_keys = set(g.json())
    row_keys = set(row["result"])
    exempt = set(GET_VS_ROW_EXEMPTIONS)
    only_get = get_keys - row_keys - exempt
    only_row = row_keys - get_keys - exempt
    assert not only_get, f"GET 多出的键 {sorted(only_get)}(豁免表未收录)"
    assert not only_row, f"流 row.result 多出的键 {sorted(only_row)}(豁免表未收录)"
