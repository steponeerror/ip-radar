# backend/tests/eval/test_eval_dsem_cli.py
import json

import pytest

from ipdb._eval import dsem_cli
from ipdb._eval.corpus import Corpus


def _lookup():
    """Synthetic fleet (test_eval_suite.py pattern): a asserts even IPs,
    b asserts i%3 IPs in ctype spam (OC 4/7 -> dependent, k=0). Gives 'a'
    n=10 pairs >= MODEL_N_FLOOR, so movers exist and T-3 actually counts."""
    rows = []
    for i in range(20):
        ip = f"10.0.0.{i}"
        srcs = (["a"] if i % 2 == 0 else []) + (["b"] if i % 3 == 0 else [])
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


def _corpus():
    return Corpus(benchmark={"spam": [f"10.0.0.{i}" for i in range(20)]})


def test_dsem_report_shape_and_fair_fight(tmp_path):
    res = dsem_cli.run_dsem_report(_lookup(), _corpus(), {"a": 0.8, "b": 0.7},
                                   out_dir=tmp_path)
    assert res["kind"] == "dsem"
    assert set(res["dsem"]) == {"pi_hat", "spread", "headline",
                                "solo_share", "theta0"}
    ff = res["fair_fight"]
    for k in ("market_t3", "declared_t3", "pihat_t3"):
        assert isinstance(ff[k], str) and "coverage" in ff[k]
    # R7: bool when both coverage rates parse; None only on unparseable
    assert ff["pihat_beats_declared"] is None or isinstance(
        ff["pihat_beats_declared"], bool)
    # artifact: model dir (REPORT_DIR/"model" contract), parseable, same payload
    arts = list((tmp_path / "model").glob("dsem-*.json"))
    assert len(arts) == 1
    assert json.loads(arts[0].read_text())["fair_fight"] == ff
    # json purity: the whole result must be stdout-serializable as one doc
    # (run_dsem's pi_hat/spread keys are (source, ctype) tuples)
    json.dumps(res)


def test_t3_rate_compares_floats_not_detail_strings():
    rate = dsem_cli._t3_rate(
        "split-half predictive coverage 16/17 = 94% (>=80%)")
    assert rate == pytest.approx(16 / 17)
    assert dsem_cli._t3_rate("garbage") is None
    assert dsem_cli._t3_rate(
        "split-half predictive coverage 0/0 = 0% (>=80%)") is None
