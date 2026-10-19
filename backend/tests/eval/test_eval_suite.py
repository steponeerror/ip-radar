# backend/tests/eval/test_eval_suite.py
import json

import pytest

from ipdb._eval.corpus import Corpus
from ipdb._eval.model import SourceScore
from ipdb._eval.suite import _c1, run_suite, spearman, write_model_report


def test_spearman_monotone_and_ties():
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2], [5, 5, 7]) == pytest.approx(1.0)  # ties avg
    assert spearman([1, 2, 3], [2, 2, 2]) == 0.0                 # constant


def _lookup():
    """Synthetic fleet: good/peer share ctype t (full overlap -> OC 1.0,
    dependent); lone monopolises ctype t2."""
    rows = []
    for i in range(20):
        ip = f"10.0.0.{i}"
        srcs = ["good", "peer"] if i % 2 == 0 else ["good"]
        rows.append((ip, "t", srcs))
        if i % 4 == 0:
            rows.append((ip, "t2", ["lone"]))          # monopoly ctype t2

    def lookup_fn(x):
        res = {"classifications": {}}
        for ip2, ctype, srcs in rows:
            if ip2 == x:
                res["classifications"][ctype] = {"sources": [
                    {"source": s, "value": True, "reliability": 0.5,
                     "authoritative": False} for s in srcs]}
        return res
    return lookup_fn


def _corpus():
    return Corpus(benchmark={"t": [f"10.0.0.{i}" for i in range(20)]})


def test_run_suite_end_to_end_shape():
    result = run_suite(_lookup(), _corpus(), declared_r={"good": 0.7})
    assert set(result["checks"]) == {"T1", "T2", "T3", "C1", "C2"}
    for chk in result["checks"].values():
        assert isinstance(chk["pass"], bool) and chk["detail"]
    names = {s.source for s in result["scores"]}
    assert {"good", "peer", "lone"} <= names
    lone = next(s for s in result["scores"] if s.source == "lone")
    assert lone.monopoly is True            # t2 sole assertor
    assert result["checks"]["T1"]["pass"]   # stable ranking on this toy fleet


def test_c1_exempt_absent_authorities_but_not_low_ranked():
    # C-1 v1.1: corpus-absent verdict authority -> exempt + visible note
    def _score(source, theta, n=10, k=5):
        return SourceScore(source=source, theta=theta, ci_lo=theta, ci_hi=theta,
                           n=n, k=k, rho=0.3, below_market=False,
                           monopoly=False, declared_r=None)

    absent = [_score("a", 0.8), _score("b", 0.7), _score("c", 0.6)]
    chk = _c1(absent)
    assert chk["pass"] is True
    assert "threatfox: exempt (absent on corpus)" in chk["detail"]
    assert "spamhaus: exempt (absent on corpus)" in chk["detail"]

    ranked = [_score("a", 0.8), _score("b", 0.7), _score("spamhaus", 0.1)]
    chk = _c1(ranked)
    assert chk["pass"] is False
    assert "spamhaus: rank 3/3 > 2" in chk["detail"]

    # present but unrankable (no-signal) is still a failure, not an exemption
    nosig = absent + [SourceScore(source="threatfox", theta=None, ci_lo=None,
                                  ci_hi=None, n=0, k=0, rho=None,
                                  below_market=False, monopoly=False,
                                  declared_r=None)]
    chk = _c1(nosig)
    assert chk["pass"] is False
    assert "threatfox: unscored" in chk["detail"]


def test_write_model_report_creates_subdir_files(tmp_path):
    result = run_suite(_lookup(), _corpus())
    md, js = write_model_report(result, tmp_path)
    assert md.parent == tmp_path / "model"
    assert md.exists() and js.exists()
    assert "corroboration" in md.read_text()          # B2 naming red line


def test_corpus_fingerprint_and_evidence_in_report(tmp_path):
    result = run_suite(_lookup(), _corpus())
    fp = result["corpus"]
    assert fp["n_ips"] == 20
    assert len(fp["sha8"]) == 8 and int(fp["sha8"], 16) >= 0   # 8 hex chars
    good = next(s for s in result["scores"] if s.source == "good")
    assert good.evidence is False        # toy fleet: OC 1.0 -> k=0 -> none
    md, js = write_model_report(result, tmp_path)
    text = md.read_text()
    assert "20 ips @" in text            # fingerprint header line
    assert "| evidence |" in text        # new column
    assert "| none |" in text and "present" not in text
    rows = {r["source"]: r for r in json.loads(js.read_text())["scores"]}
    assert rows["good"]["evidence"] is False
    assert json.loads(js.read_text())["corpus"]["n_ips"] == 20


def test_model_report_persists_pairs_history(tmp_path):
    from ipdb._eval.corpus import Corpus
    from ipdb._eval.suite import run_suite, write_model_report

    def lookup(ip):
        data = {
            "1.1.1.1": {"classifications": {"spam": {
                "sources": [{"source": "a"}, {"source": "b"}],
                "details": [{"source": "a", "first_seen": "2026-08-01"},
                            {"source": "b"}]}}},
            "2.2.2.2": {"classifications": {"proxy": {
                "sources": [{"source": "c"}],
                "details": [{"source": "c", "first_seen": "2026-07-15"}]}}},
        }
        return data.get(ip, {})

    corpus = Corpus(benchmark={"spam": ["1.1.1.1"], "proxy": ["2.2.2.2"]})
    result = run_suite(lookup, corpus)
    assert result["pairs"]["a"] == [["1.1.1.1", "spam", "2026-08-01"]]
    assert result["pairs"]["b"] == [["1.1.1.1", "spam", None]]
    md, js = write_model_report(result, tmp_path)
    payload = json.loads(js.read_text())
    assert payload["pairs"]["c"] == [["2.2.2.2", "proxy", "2026-07-15"]]
    assert '"pairs"' not in md.read_text()   # md stays human-sized


def test_model_md_report_has_new_columns_and_footnotes(tmp_path):
    from ipdb._eval.corpus import Corpus
    from ipdb._eval.suite import run_suite, write_model_report

    def lookup(ip):
        if ip != "1.1.1.1":
            return {}
        return {"classifications": {"spam": {
            "sources": [{"source": "a"}, {"source": "b"}],
            "details": [{"source": "a", "first_seen": "2026-08-01"},
                        {"source": "b"}]}}}

    md, _ = write_model_report(
        run_suite(lookup, Corpus(benchmark={"spam": ["1.1.1.1"]})), tmp_path)
    text = md.read_text()
    assert "| source | theta | 90% CI | n | k | rho | evidence | below-mkt | mono | fountain | unique | declared_r |" in text
    assert "specialist / uncovered niche, not necessarily weak" in text
    assert "information-theoretically uncorroboratable" in text


# ── 矩阵断言段(ADR 0003 Task 3:violation→失败级 / pending→警示行)────
# 接线面 = run_suite(matrix_assets=...)(缺省不接,旧入口/旧测试零漂移,
# sources=None 可选注入同款先例);月度入口 --model 传四层资产根。

def _save_matrix_layer(root, kind, ips):
    from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
    save_asset(root / kind, ips, AssetMeta(
        version="v1", kind=kind, fingerprint=fingerprint(ips),
        member_count=len(ips), params={}, eval_env="monthly",
        created_at="2026-10-19"))


def _incident_payload(ip):
    # 8.8.8.8 事故形状:infra IP 经存档章显形 informational(UI 通道)
    return {"ip": ip, "threat": {"verdict": "informational", "confidence": 0,
                                 "types": ["spam"], "is_cdn": False},
            "classifications": {"spam": {
                "type": "spam", "verdict": "informational", "detected": True,
                "confidence": 0, "details": [
                    {"source": "firehol_webserver", "verdict": "informational",
                     "reliability": 0.5}]}},
            "attributes": {}}


def _matrix_lookup(hits):
    def lookup(ip):
        return hits.get(ip, {"ip": ip, "classifications": {}})
    return lookup


def test_run_suite_matrix_segment_violation_fails(tmp_path):
    _save_matrix_layer(tmp_path, "infra", ["8.8.8.8"])
    result = run_suite(_matrix_lookup({"8.8.8.8": _incident_payload("8.8.8.8")}),
                       _corpus(), matrix_assets=tmp_path)
    assert set(result["checks"]) == {"T1", "T2", "T3", "C1", "C2", "MATRIX"}
    chk = result["checks"]["MATRIX"]
    assert chk["pass"] is False                     # violation = 失败级
    assert "violation 1" in chk["detail"] and "pending 0" in chk["detail"]
    assert chk["violation_cells"] == ["infra|informational|UI"]


def test_run_suite_matrix_segment_pending_warns_passes(tmp_path, monkeypatch):
    from ipdb._eval import matrix_scan
    from ipdb._eval.matrix import (CHANNELS, LABELS, LAYERS, RuledCell,
                                   SemanticMatrix, save_matrix)
    _save_matrix_layer(tmp_path, "infra", ["8.8.8.8"])
    cells = {(l, b, c): RuledCell(state="illegal", note="conservative-default")
             for l in LAYERS for b in LABELS for c in CHANNELS}
    cells.update({(l, "clean", c): RuledCell(state="pending", note="待裁例")
                  for l in ("infra",) for c in CHANNELS})
    mpath = tmp_path / "matrix.json"
    save_matrix(SemanticMatrix(cells=cells), mpath)
    monkeypatch.setattr(matrix_scan, "MATRIX_PATH", mpath)
    result = run_suite(_matrix_lookup({}), _corpus(), matrix_assets=tmp_path)
    chk = result["checks"]["MATRIX"]
    assert chk["pass"] is True                      # pending = 警示级不拦
    assert "violation 0" in chk["detail"] and "pending 3" in chk["detail"]
    assert "pending 3" in chk["warn"] and "待裁" in chk["warn"]
    md, js = write_model_report(result, tmp_path)
    text = md.read_text()
    assert "**MATRIX: PASS**" in text
    assert "⚠" in text and "pending 3" in text      # 警示行进 Checks 段
    assert json.loads(js.read_text())["checks"]["MATRIX"]["pass"] is True


def test_run_suite_matrix_segment_clean_passes_no_warn(tmp_path):
    _save_matrix_layer(tmp_path, "infra", ["8.8.8.8"])
    result = run_suite(_matrix_lookup({}), _corpus(), matrix_assets=tmp_path)
    chk = result["checks"]["MATRIX"]
    assert chk["pass"] is True
    assert "violation 0" in chk["detail"] and "pending 0" in chk["detail"]
    assert "warn" not in chk and "violation_cells" not in chk


def test_cli_model_wires_matrix_segment(monkeypatch, tmp_path, capsys):
    # 月度入口接线面:--model 传四层资产根(缺省 <repo>/backend/data/
    # eval/assets,--assets-dir 覆盖)→ 套件增 MATRIX 段(真 matrix.json)
    import ipdb._registry as reg
    monkeypatch.setattr(reg, "_sources", [])
    monkeypatch.setattr(reg, "load_db", lambda: None)

    class _Result:
        def __init__(self, payload):
            self._p = payload
        def to_dict(self):
            return self._p

    monkeypatch.setattr(
        reg, "lookup",
        lambda ip, allowed_sources=None, *, asof=None: _Result(
            {"8.8.8.8": _incident_payload("8.8.8.8")}.get(
                ip, {"ip": ip, "classifications": {}})))
    from ipdb._eval import __main__ as em
    monkeypatch.setattr(em, "REPORT_DIR", tmp_path)
    _save_matrix_layer(tmp_path, "infra", ["8.8.8.8"])
    em.main(["--model", "--assets-dir", str(tmp_path)])
    assert "model suite:" in capsys.readouterr().out
    js = next((tmp_path / "model").glob("model-*.json"))
    chk = json.loads(js.read_text())["checks"]["MATRIX"]
    assert chk["pass"] is False
    assert chk["violation_cells"] == ["infra|informational|UI"]
