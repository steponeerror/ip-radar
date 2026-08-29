"""calibrated.json 覆盖加载(spec §8):class attr 先验 → 文件后验。"""
import json

import pytest

from ipdb import _registry
from ipdb._merge import SOURCE_RELIABILITY


@pytest.fixture(autouse=True)
def _restore_reliability():
    # 全局 dict 污染防护:每条用例前后快照还原
    snap = dict(SOURCE_RELIABILITY)
    yield
    SOURCE_RELIABILITY.clear()
    SOURCE_RELIABILITY.update(snap)


def test_apply_calibrated_overrides_default_domain(tmp_path):
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({
        "spamhaus": {"default": 0.91, "country": 0.95},   # 非 default 域本期不消费
        "firehol": {"default": 0.55},
    }))
    SOURCE_RELIABILITY["spamhaus"] = 0.90
    _registry._apply_calibrated(f)
    assert SOURCE_RELIABILITY["spamhaus"] == 0.91
    assert SOURCE_RELIABILITY["firehol"] == 0.55


def test_apply_calibrated_missing_file_is_noop(tmp_path):
    SOURCE_RELIABILITY["dshield"] = 0.70
    _registry._apply_calibrated(tmp_path / "absent.json")
    assert SOURCE_RELIABILITY["dshield"] == 0.70


def test_apply_calibrated_clamps_to_098(tmp_path):
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({"x": {"default": 1.0}}))
    _registry._apply_calibrated(f)
    assert SOURCE_RELIABILITY["x"] == 0.98


def test_apply_calibrated_skips_out_of_range_with_warning(tmp_path, caplog):
    # 信任边界:≤0 或 >1(含 NaN/Inf/bool)非法,跳过并告警,绝不写入
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({
        "bad_low": {"default": 0.0},
        "bad_neg": {"default": -0.2},
        "bad_high": {"default": 1.5},
        "bad_bool": {"default": True},
        "bad_nan": {"default": float("nan")},
        "ok": {"default": 0.77},
    }))
    with caplog.at_level("WARNING"):
        _registry._apply_calibrated(f)
    for src in ("bad_low", "bad_neg", "bad_high", "bad_bool", "bad_nan"):
        assert src not in SOURCE_RELIABILITY
    assert SOURCE_RELIABILITY["ok"] == 0.77
    assert sum("out of (0,1]" in r.message for r in caplog.records) == 5


def test_apply_calibrated_malformed_json_is_noop(tmp_path, caplog):
    f = tmp_path / "_calibrated.json"
    f.write_text("{not json")
    with caplog.at_level("WARNING"):
        _registry._apply_calibrated(f)
    assert SOURCE_RELIABILITY  # 未被清空/改动
