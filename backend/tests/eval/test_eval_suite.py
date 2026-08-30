# backend/tests/eval/test_eval_suite.py
import pytest

from ipdb._eval.corpus import Corpus
from ipdb._eval.suite import run_suite, spearman, write_model_report


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


def test_write_model_report_creates_subdir_files(tmp_path):
    result = run_suite(_lookup(), _corpus())
    md, js = write_model_report(result, tmp_path)
    assert md.parent == tmp_path / "model"
    assert md.exists() and js.exists()
    assert "corroboration" in md.read_text()          # B2 naming red line
