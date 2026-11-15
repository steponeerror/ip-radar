# backend/tests/eval/test_eval_mutation_check.py
"""变异自检(#352 / ADR 0021 决策6)测试:变异体模板行为 + 真门会红
路径 + survived 显形红面 + 契约表接线。

红面证明 = 读数语义本体:门被改瞎(monkeypatch 拆判定核)时,注入的
缺陷杀不掉 → runner 必须报 survived(带 finding 人裁文本),不造假
killed、不炸——「survived=漏放行显形」是被测行为,不是声明。

夹具纪律:同模块本体(全部沙箱 tempfile 种完即清;填充 IP 用 RFC
5737 三文档段;净锚 8.8.8.8 原样用 = 被测已知答案集真实成员,#351
同款纪律)。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval import contract as C
from ipdb._eval import mirror_check, mutation_check as MC
from ipdb._eval.anchors import ANCHORS
from ipdb._eval.contract import CONTRACT_PATH, load_contract, run_contract

MUTATION_IDS = {
    "fake-source-key-collapse",
    "fake-source-accuses-clean-anchor",
    "fake-source-field-malformed",
    "erroneous-merge-echo-on-clean-anchor",
}


# ── 绿面:全量读数形状 + 今日诚实读数 ───────────────────────────────

def test_report_shape_and_matrix_complete():
    r = MC.run_mutation_check()
    assert r["kind"] == "mutation_check"
    assert {m["id"] for m in r["mutations"]} == MUTATION_IDS
    # 矩阵完备:每变异体 × 每可跑门恰一对,状态合法
    runnable = set(r["gates"]["runnable"])
    assert runnable == {"anchors", "mirror-s7"}
    pairs = {(p["mutation"], p["gate"]) for p in r["matrix"]}
    assert pairs == {(m, g) for m in MUTATION_IDS for g in runnable}
    for p in r["matrix"]:
        assert p["status"] in ("killed", "survived", "green",
                               "unexpected-red")
        assert isinstance(p["expected_red"], bool)
        assert p["detail"]                     # 缺读数不虚构,有读数不带空
    s = r["summary"]
    assert s["n_mutations"] == len(MUTATION_IDS)
    assert s["killed"] + s["survived"] == s["n_mutations"]
    assert sum(s["pairs"].values()) == len(r["matrix"])


def test_current_readings_three_killed_one_survived():
    """今日诚实读数(真门真红非 stub):键数坍塌被 S7 杀、指控锚与回声
    合并被锚门杀;字段错形部分坍塌(字节面净变低于阈)存活=盲区显形。
    盲区被填补时(如 #350 阳性锚落地)此断言须人裁更新。"""
    r = MC.run_mutation_check()
    by_id = {m["id"]: m for m in r["mutations"]}
    assert by_id["fake-source-key-collapse"]["status"] == "killed"
    assert by_id["fake-source-key-collapse"]["killed_by"] == ["mirror-s7"]
    assert by_id["fake-source-accuses-clean-anchor"]["killed_by"] == \
        ["anchors"]
    assert by_id["erroneous-merge-echo-on-clean-anchor"]["killed_by"] == \
        ["anchors"]
    fm = by_id["fake-source-field-malformed"]
    assert fm["status"] == "survived" and fm["killed_by"] == []
    assert "#350" in fm["finding"]              # 宪章捕获者指向真源
    assert r["survived_findings"] == [fm["finding"]]


def test_no_reading_gates_surface_with_reason():
    r = MC.run_mutation_check()
    by_gate = {g["gate"]: g["reason"] for g in r["gates"]["no_reading"]}
    assert set(by_gate) == {"c2-idempotent", "golden-diff"}
    assert "一次性脚本" in by_gate["c2-idempotent"]      # 与契约表行同口径
    assert "ops" in by_gate["golden-diff"]


# ── 变异体模板行为钉住 ────────────────────────────────────────────────

def test_template_accuses_anchor_defect_reaches_gate(tmp_path):
    """模板行为:指控锚变异体的沙箱投影真的指控 8.8.8.8(缺陷到达门面,
    无 infra 过滤车道),健康孪生不指控。"""
    state = MC._mut_accuses_anchor(tmp_path)
    [bad] = [s for s in state["mutated"]["sources"]
             if s.name == "binarydefense"]
    [good] = [s for s in state["healthy"]["sources"]
              if s.name == "binarydefense"]
    assert bad.query("8.8.8.8")
    assert not good.query("8.8.8.8")


def test_template_key_collapse_shrinks_bytes_over_threshold(tmp_path):
    state = MC._mut_key_collapse(tmp_path)
    cur = mirror_check.manifest(state["mutated"]["dir"])
    prev = state["manifest_baseline"]
    frac = 1 - cur["bytes"] / prev["bytes"]
    assert frac > 0.2                          # 稳超 S7 塌缩阈
    assert state["mutated"]["counts"]["ipsum"] < \
        state["healthy"]["counts"]["ipsum"]


def test_template_field_malformed_collapses_keys_below_byte_threshold(
        tmp_path):
    """模板行为:字段错形键坍塌至 40% 且字节面净变低于 20% 阈
    (data.mdb 8KB 页粒度收缩被原始件增字节部分抵消)——盲区的机制面。
    行数不硬钉 _N_IPSUM 具体值(评审 P2-1 拉宽余量后免漂移)。"""
    state = MC._mut_field_malformed(tmp_path)
    assert state["healthy"]["counts"]["ipsum"] == MC._N_IPSUM
    assert state["mutated"]["counts"]["ipsum"] == MC._N_IPSUM * 2 // 5
    cur = mirror_check.manifest(state["mutated"]["dir"])
    prev = state["manifest_baseline"]
    assert 0 < 1 - cur["bytes"] / prev["bytes"] < 0.2


def test_sandbox_lookup_feeds_anchor_gate_consumed_shape(tmp_path):
    """夹具适配层形状 = 锚门消费面:classifications 带 verdict/details
    (source/verdict/reliability),reserved 短路由真模块;健康基线自带
    tor/hosting 夹具性失败(沙箱宇宙无属性源,差分读数的取消对象)。"""
    state = MC._mut_accuses_anchor(tmp_path)
    lk = MC._sandbox_lookup(state["mutated"]["sources"])
    res = lk("8.8.8.8")
    ca = res["classifications"]["blacklist"]
    assert ca["verdict"] == "malicious"
    assert {d["source"] for d in ca["details"]} == {"binarydefense"}
    assert all(k in d for d in ca["details"]
               for k in ("source", "verdict", "reliability"))
    reserved_ip = next(ip for ip, k in ANCHORS if k == "reserved")
    assert lk(reserved_ip)["is_reserved"] is True
    # 健康基线自带 tor/hosting 夹具性失败(沙箱宇宙无属性源,差分读数的
    # 取消对象);指控只出现在变异体面
    fails = MC._anchors.run_anchors(
        MC._sandbox_lookup(state["healthy"]["sources"]))
    assert {f["expect"] for f in fails} == {"tor", "hosting"}


# ── 红面:门改瞎 → survived 必须显形(不造假 killed 不炸)──────────

def test_survived_surfaced_when_anchor_gate_neutered(monkeypatch):
    """锚门判定核改瞎(_check 恒 None=已知答案门死件形态)→ 指控锚/
    回声合并两变异体杀不掉,runner 报 survived+finding。"""
    monkeypatch.setattr(MC._anchors, "_check", lambda res, expect: None)
    r = MC.run_mutation_check()
    pairs = {(p["mutation"], p["gate"]): p["status"] for p in r["matrix"]}
    assert pairs[("fake-source-accuses-clean-anchor", "anchors")] == \
        "survived"
    assert pairs[("erroneous-merge-echo-on-clean-anchor", "anchors")] == \
        "survived"
    by_id = {m["id"]: m for m in r["mutations"]}
    assert by_id["fake-source-accuses-clean-anchor"]["status"] == \
        "survived"
    assert by_id["erroneous-merge-echo-on-clean-anchor"]["finding"]
    assert r["summary"]["survived"] >= 2


def test_survived_surfaced_when_mirror_gate_neutered(monkeypatch):
    """S7 塌缩闸改瞎(比对恒 ok)→ 键数坍塌杀不掉,survived+finding。"""
    monkeypatch.setattr(
        MC.mirror_check, "check_against_previous",
        lambda data_dir, prev, **kw: {"ok": True, "detail": "neutered"})
    r = MC.run_mutation_check()
    pair = next(p for p in r["matrix"]
                if p["mutation"] == "fake-source-key-collapse"
                and p["gate"] == "mirror-s7")
    assert pair["status"] == "survived"
    assert pair["detail"] == "neutered"          # 门自报读数留痕
    kc = next(m for m in r["mutations"]
              if m["id"] == "fake-source-key-collapse")
    assert kc["status"] == "survived" and kc["finding"]


def test_pair_status_four_faces():
    assert MC._pair_status(True, True) == "killed"
    assert MC._pair_status(True, False) == "survived"
    assert MC._pair_status(False, False) == "green"
    assert MC._pair_status(False, True) == "unexpected-red"


# ── 契约表接线:门自检维度行,func oracle 可解析可执行 ───────────────

def test_contract_table_has_mutation_selfcheck_row():
    doc = load_contract(CONTRACT_PATH)
    row = next(r for r in doc["rows"] if r["dimension"] == "门自检")
    assert row["id"] == "mutation-selfcheck-baseline-gates"
    assert row["verdict"] == "finding"          # 验门不持门,语义诚实
    assert row["track"] == "baseline"
    assert row["trigger"] == "round"            # 月度(接线待人裁,票尾)
    assert row["oracle"] == {
        "kind": "func",
        "ref": "ipdb._eval.mutation_check.run_mutation_check"}
    assert callable(C._resolve_func(row["oracle"]["ref"]))
    for token in ("ADR 0021 决策6", "#352", "Jia & Harman 2011"):
        assert token in row["provenance"]       # 出处进表
    assert "零容忍" in row["expectation"]


def test_mutation_row_runs_through_runner(tmp_path, monkeypatch):
    """单行迷你契约表端到端:finding 腿读数入报告单(gate_pass 恒 None,
    不判门),md 面「门自检」维度可见,读数带 survived finding。"""
    real = load_contract(CONTRACT_PATH)
    row = next(r for r in real["rows"]
               if r["id"] == "mutation-selfcheck-baseline-gates")
    table = tmp_path / "mini.json"
    table.write_text(json.dumps(
        {"schema": C.SCHEMA, "rows": [row]}, ensure_ascii=False),
        encoding="utf-8")
    report = run_contract(table, params={}, out_dir=tmp_path)
    leg = report["rows"][0]
    assert leg["status"] == "ok"
    assert leg["gate_pass"] is None             # finding 腿不判门
    assert leg["reading"]["kind"] == "mutation_check"
    assert leg["reading"]["summary"]["survived"] == 1
    assert leg["reading"]["survived_findings"]
    md = Path(report["paths"]["md"]).read_text(encoding="utf-8")
    assert "门自检" in md
    assert "mutation_check" in md               # 读数进 md(截断面)
    assert report["summary"]["n_ok"] == 1
