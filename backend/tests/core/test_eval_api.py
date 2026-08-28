"""eval 报告 reader + 3 端点 + sources 聚合(spec 2026-08-28 §5.2,PR② Task 7)。

schema 按 report.py 实测:source / generated_at(日粒度串)/ verdict{state,...}
/ metrics{k:{value,n}}。文件名 {source}-{YYYYMMDD-HHMMSS}.json(T5 修复),
秒级时间戳做同日排序 tie-break。"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _tiny_db_gate(tiny_db, monkeypatch):
    """最小库打开查询门 + 强制 release 构建窗口:全量序下前面的测试模块
    (如 test_api_tasks)会在 manager 里留下 in-flight 任务状态,把
    require_ready 持续关成一 503(与已知 15 个顺序隔离失败同病理)。
    deadline 置 0(已过期)+ episode 置 True(不再重新武装)→ 门放行,
    本模块对顺序污染免疫。monkeypatch 保证洞测后还原。"""
    import main
    monkeypatch.setattr(main, "_BUILD_DEADLINE", 0.0)
    monkeypatch.setattr(main, "_coverage_episode", True)


def _write_report(d: Path, source: str, at: str, state: str = "POSITIVE-VERIFIED",
                  ts: str = "000000"):
    """按 report.py 实际产出写最小自洽报告(文件名含秒级时间戳)。"""
    date_compact = at.replace("-", "")
    (d / f"{source}-{date_compact}-{ts}.json").write_text(json.dumps({
        "source": source,
        "generated_at": at,
        "verdict": {"state": state, "action": "keep"},
        "metrics": {"MC": {"value": 0.1, "n": 420}, "CG": {"value": 4, "n": 9},
                    "OC": {"value": 0.03, "n": 9}},
    }))


class TestEvalRoutes:
    @classmethod
    def setup_class(cls):
        import main
        from ipdb import load_db
        load_db()
        cls.client = TestClient(main.app)

    # ── GET /api/eval(overview,嵌 current_job)──

    def test_overview_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        r = self.client.get("/api/eval")
        assert r.status_code == 200
        body = r.json()
        assert body["current_job"] is None
        assert body["verdicts"] == []

    def test_overview_latest_per_source(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        _write_report(tmp_path, "spamhaus", "2026-08-28", state="POSITIVE-UNVERIFIED")
        _write_report(tmp_path, "spamhaus", "2026-08-29", ts="120000")
        _write_report(tmp_path, "otx", "2026-08-29", state="NEGATIVE-DEPRIORITIZE")
        body = self.client.get("/api/eval").json()
        vs = {v["source"]: v for v in body["verdicts"]}
        assert set(vs) == {"spamhaus", "otx"}
        # 最新胜出(同源取 generated_at 最大)
        assert vs["spamhaus"]["verdict"] == "POSITIVE-VERIFIED"
        assert vs["spamhaus"]["at"] == "2026-08-29"
        # metrics 取嵌套 value(Controller 修正:metrics{k:{value,n}})
        assert vs["spamhaus"]["mc"] == 0.1
        assert vs["spamhaus"]["cg"] == 4
        assert vs["spamhaus"]["oc"] == 0.03
        assert vs["otx"]["verdict"] == "NEGATIVE-DEPRIORITIZE"

    def test_overview_same_day_tiebreak_by_filename_ts(self, tmp_path, monkeypatch):
        """generated_at 日粒度 → 同日多报告靠文件名秒级时间戳分先后。"""
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        _write_report(tmp_path, "spamhaus", "2026-08-29", state="POSITIVE-UNVERIFIED",
                      ts="010000")
        _write_report(tmp_path, "spamhaus", "2026-08-29", ts="020000")
        body = self.client.get("/api/eval").json()
        v = next(v for v in body["verdicts"] if v["source"] == "spamhaus")
        assert v["verdict"] == "POSITIVE-VERIFIED"   # 后写者胜

    # ── GET /api/eval/{source}(detail:latest + history)──

    def test_detail_history_and_latest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        _write_report(tmp_path, "spamhaus", "2026-08-28", ts="010000")
        _write_report(tmp_path, "spamhaus", "2026-08-29", ts="020000")
        d = self.client.get("/api/eval/spamhaus").json()
        assert len(d["history"]) == 2
        assert d["history"] == [
            {"at": "2026-08-28", "verdict": "POSITIVE-VERIFIED"},
            {"at": "2026-08-29", "verdict": "POSITIVE-VERIFIED"},
        ]
        assert d["latest"]["verdict"]["state"] == "POSITIVE-VERIFIED"
        assert d["latest"]["metrics"]["MC"]["value"] == 0.1
        assert d["latest"]["source"] == "spamhaus"

    def test_detail_existing_source_no_history(self, tmp_path, monkeypatch):
        """源存在但从未评估 → latest null + 空 history(与 404 区分)。"""
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        d = self.client.get("/api/eval/spamhaus")
        assert d.status_code == 200
        assert d.json() == {"latest": None, "history": []}

    def test_detail_unknown_source_404(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        assert self.client.get("/api/eval/nosuchsrc").status_code == 404

    # ── POST /api/eval/{source}/run ──

    def test_run_unknown_source_404(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        assert self.client.post("/api/eval/nosuchsrc/run").status_code == 404

    def test_run_accepted_202(self, tmp_path, monkeypatch):
        import main
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        with patch.object(main.eval_manager, "run",
                          return_value={"job_id": "abc123", "source": "spamhaus",
                                        "state": "running"}) as m:
            r = self.client.post("/api/eval/spamhaus/run")
        assert r.status_code == 202
        assert r.json() == {"job_id": "abc123"}
        m.assert_called_once_with("spamhaus")

    def test_run_busy_409(self, tmp_path, monkeypatch):
        import main
        from ipdb._eval_manager import EvalBusyError
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        with patch.object(main.eval_manager, "run",
                          side_effect=EvalBusyError("otx")):
            r = self.client.post("/api/eval/spamhaus/run")
        assert r.status_code == 409
        assert "otx" in r.json()["detail"]

    # ── /api/sources 聚合 eval 字段 ──

    def test_sources_aggregates_eval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
        _write_report(tmp_path, "spamhaus", "2026-08-29")
        items = self.client.get("/api/sources").json()
        by = {i["name"]: i for i in items}
        assert by["spamhaus"]["eval"] == {"verdict": "POSITIVE-VERIFIED",
                                          "at": "2026-08-29"}
        # 无报告的源 → null(tiny_db 里 ipinfo_lite 有数据必在)
        assert by["ipinfo_lite"]["eval"] is None
