# backend/tests/eval/test_eval_nodata.py
"""W4: NO-DATA 双判据 + source_health 块 + C1 specialist 分支(spec §5.5)。

Fixture 锁死两个生产复现形态:
- threatfox(threat 类)17k→1:历史 [17000, 16500, 16800] 硬编码中位 16800,
  坍塌线 NO_DATA_COLLAPSE × 16800 = 8400;rc=1 < 8400 → collapsed。
- ip2proxy(asset 类死源):NO-DATA 判定必须在 asset 早退之前 ——
  asset + rc=0 → NO-DATA 优先于 N/A-ASSET(dead asset 也要告警)。
"""
import json

from ipdb._eval.corpus import Corpus
from ipdb._eval.metrics import Metric
from ipdb._eval.model import SourceScore
from ipdb._eval.suite import _c1, run_suite, write_model_report
from ipdb._eval.verdict import assess


def _m(value=0.0, n=100):
    return Metric(value=value, n=n)


def _metrics():
    return {"MC": _m(0.001), "CG": _m(0), "conflict": _m(0),
            "fp": _m(0.01), "other": _m(0.1)}   # → MARGINAL on the 5-state path


# threatfox 复现样本:median([17000, 16500, 16800]) = 16800,坍塌线 8400
_THREATFOX_HISTORY = [17000, 16500, 16800]


# ── NO-DATA verdict 双判据 ─────────────────────────────────────

def test_nodata_empty():
    v = assess(_metrics(), candidate_touched_n=5, suspicion_flags=[],
               rc=0, rc_history=None)
    assert v.state == "NO-DATA"
    assert v.reason == "empty"
    assert v.insufficient is False          # 前置 n-floor,不再 INSUFF


def test_nodata_empty_beats_asset_early_exit():
    # ip2proxy 形态:asset 类死源也必须告警(NO-DATA 在 asset 早退之前)
    v = assess({}, candidate_touched_n=0, suspicion_flags=[],
               source_category="asset", rc=0, rc_history=None)
    assert v.state == "NO-DATA"
    assert v.reason == "empty"
    assert v.verified is False


def test_nodata_collapsed():
    # threatfox 17k→1 形态:rc=1 < 0.5 × 16800 = 8400
    v = assess(_metrics(), candidate_touched_n=100, suspicion_flags=[],
               rc=1, rc_history=_THREATFOX_HISTORY)
    assert v.state == "NO-DATA"
    assert v.reason == "collapsed"


def test_nodata_rc0_with_history_still_empty():
    # empty 判据先行:rc=0 带历史也报 empty,不报 collapsed
    v = assess(_metrics(), candidate_touched_n=100, suspicion_flags=[],
               rc=0, rc_history=_THREATFOX_HISTORY)
    assert v.reason == "empty"


def test_nodata_collapsed_boundary_not_triggered():
    # rc=9000 > 8400 → 非 NO-DATA,走正常 5 态
    v = assess(_metrics(), candidate_touched_n=100, suspicion_flags=[],
               rc=9000, rc_history=_THREATFOX_HISTORY)
    assert v.state != "NO-DATA"
    assert v.state == "MARGINAL"


def test_nodata_first_round_no_history():
    # 首轮(本任务之后才有 source_health 证据):无历史只判 empty
    v = assess(_metrics(), candidate_touched_n=100, suspicion_flags=[],
               rc=5000, rc_history=None)
    assert v.state != "NO-DATA"
    v2 = assess(_metrics(), candidate_touched_n=100, suspicion_flags=[],
                rc=5000, rc_history=[])
    assert v2.state != "NO-DATA"


def test_rc_absent_keeps_legacy_paths():
    # rc 缺省(None)→ 全部旧行为不变:asset 早退 / n-floor 均原样
    v = assess({}, candidate_touched_n=100, suspicion_flags=[],
               source_category="asset")
    assert v.state == "N/A-ASSET"
    v2 = assess(_metrics(), candidate_touched_n=5, suspicion_flags=[])
    assert v2.state == "INSUFFICIENT-SAMPLE"


# ── C1 specialist 分支(SC-5)───────────────────────────────────

def _score(source, theta, unique_share=None):
    return SourceScore(source=source, theta=theta, ci_lo=theta, ci_hi=theta,
                       n=20, k=10, rho=0.3, below_market=False,
                       monopoly=False, declared_r=None,
                       unique_share=unique_share)


def _c1_fleet(unique_share):
    """24-scored fleet(生产 fleet 尺寸,half=(24+1)//2=12 即 rank-12 门);
    threatfox 恒 pin 在 rank 22(镜像 SC-5:rank 21/24、uniq 94%)。"""
    scores = [_score(f"a{i:02d}", 0.90 - 0.02 * i) for i in range(21)]  # ranks 1-21
    scores.append(_score("threatfox", 0.44, unique_share=unique_share))  # rank 22
    scores += [_score(f"z{i}", 0.40 - 0.02 * i) for i in range(2)]      # ranks 23-24
    return scores


def test_c1_specialist_exempt():
    # unique_share ≥ 0.8(0.9)→ 不进 rank 门,C1 PASS + 注记
    chk = _c1(_c1_fleet(unique_share=0.9))
    assert chk["pass"] is True
    assert "threatfox: specialist-exempt(22)" in chk["detail"]
    # 边界:恰好 0.8 也豁免(≥ 语义)
    chk80 = _c1(_c1_fleet(unique_share=0.8))
    assert chk80["pass"] is True
    assert "threatfox: specialist-exempt" in chk80["detail"]


def test_c1_low_unique_share_rank_fail_unchanged():
    # unique_share 0.5 → 不豁免,rank 22 > 12 照旧 FAIL
    chk = _c1(_c1_fleet(unique_share=0.5))
    assert chk["pass"] is False
    assert "threatfox: rank 22/24 > 12" in chk["detail"]


def test_c1_none_unique_share_not_exempt():
    # 无非独占断言的源 unique_share=None → 不豁免,rank 门照旧
    chk = _c1(_c1_fleet(unique_share=None))
    assert chk["pass"] is False


# ── source_health 块(run_suite / model report 顶层只增键)──────

class _HealthySource:
    def __init__(self, name, rc, stale=False):
        self.name = name
        self._h = type("H", (), {"record_count": rc, "is_stale": stale})()
    def health(self):
        return self._h


def _tiny_fleet():
    def lookup(ip):
        if ip != "10.0.0.1":
            return {}
        return {"classifications": {"t": {"sources": [{"source": "good"},
                                                   {"source": "peer"}]}}}
    return lookup, Corpus(benchmark={"t": ["10.0.0.1"]})


def test_run_suite_emits_source_health(tmp_path):
    lookup, corpus = _tiny_fleet()
    srcs = [_HealthySource("good", 1234), _HealthySource("dead", 0, stale=True)]
    result = run_suite(lookup, corpus, sources=srcs)
    assert result["source_health"] == {
        "good": {"rc": 1234, "stale": False},
        "dead": {"rc": 0, "stale": True}}
    md, js = write_model_report(result, tmp_path)
    payload = json.loads(js.read_text())
    assert payload["source_health"]["dead"] == {"rc": 0, "stale": True}


def test_run_suite_source_health_none_without_sources():
    lookup, corpus = _tiny_fleet()
    result = run_suite(lookup, corpus)
    assert result["source_health"] is None


# ── rc_history 扫描(REPORT_DIR/model 历史报告)─────────────────

def test_rc_history_scan(tmp_path):
    from ipdb._eval.__main__ import _rc_history
    d = tmp_path / "model"
    d.mkdir()
    def _report(date, ts, sh=None):
        payload = {"generated_at": date}
        if sh is not None:
            payload["source_health"] = sh
        (d / f"model-{ts}.json").write_text(json.dumps(payload))
    _report("2026-09-01", "20260901-010101",
            {"threatfox": {"rc": 17000, "stale": False}})
    # 同日多份 → 字典序最后一份胜(与 _eval_reader 惯例一致)
    _report("2026-09-02", "20260902-010101",
            {"threatfox": {"rc": 99999, "stale": False}})
    _report("2026-09-02", "20260902-020202",
            {"threatfox": {"rc": 16500, "stale": False}})
    _report("2026-09-15", "20260915-010101",
            {"threatfox": {"rc": 16800, "stale": True}})
    # 旧报告(本任务之前)无 source_health 键 → 无条目,不炸
    _report("2026-08-15", "20260815-010101")
    assert _rc_history("threatfox", d) == _THREATFOX_HISTORY
    assert _rc_history("unknown", d) == []


def test_rc_history_missing_dir(tmp_path):
    from ipdb._eval.__main__ import _rc_history
    assert _rc_history("threatfox", tmp_path / "nope" / "model") == []
