import json

from ipdb._eval_reader import read_model


def test_read_model_returns_newest_and_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    assert read_model() is None
    d = tmp_path / "model"
    d.mkdir()
    (d / "model-20260831-010101.json").write_text(json.dumps({"kind": "model", "w": 10}))
    (d / "model-20260831-020202.json").write_text(json.dumps({"kind": "model", "w": 20}))
    assert read_model()["w"] == 20


def test_read_model_strips_pairs_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    d = tmp_path / "model"
    d.mkdir()
    (d / "model-20260831-030303.json").write_text(json.dumps(
        {"kind": "model", "w": 30, "pairs": [{"a": "et", "b": "spamhaus"}]}))
    m = read_model()
    assert "pairs" not in m
    assert m["w"] == 30


def test_read_model_ignores_top_level_source_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    (tmp_path / "spamhaus-20260831-010101.json").write_text(json.dumps({"source": "spamhaus"}))
    assert read_model() is None
