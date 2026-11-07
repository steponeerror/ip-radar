"""effective_reliability 有效 r 单一解析入口(#317,冻结规格
docs/research/2026-11-07-effective-reliability-spec.md,裁决链 #293):
优先序 表 > payload_r > attr_r > 0.5(逐字对应 DM-1 lookup 现链);
读侧零钳制(钳制在填装侧 _apply_calibrated);对象身份不变式(表只许
clear+update 原地改,严禁重新赋值)与 T3 结构守门(全仓
SOURCE_RELIABILITY.get( 字面量恰一处 = 函数体内;_stix_export 不再
import 表本体)在此钉死。"""
import json

import pytest

from ipdb import _registry
from ipdb._merge import SOURCE_RELIABILITY, effective_reliability


@pytest.fixture(autouse=True)
def _restore_reliability():
    # 全局 dict 污染防护:每条用例前后快照还原(同 test_calibrated_loader)
    snap = dict(SOURCE_RELIABILITY)
    yield
    SOURCE_RELIABILITY.clear()
    SOURCE_RELIABILITY.update(snap)


# ── T1 优先序(规格 §3:四组合 + 读侧不钳制)──

def test_t1_table_hit_overrides_payload_and_attr():
    SOURCE_RELIABILITY["__t1_src__"] = 0.9
    assert effective_reliability("__t1_src__", payload_r=0.7, attr_r=0.6) == 0.9


def test_t1_table_miss_falls_back_to_payload_r():
    assert effective_reliability("__t1_absent__", payload_r=0.7, attr_r=0.6) == 0.7


def test_t1_payload_missing_falls_back_to_attr_r():
    assert effective_reliability("__t1_absent__", attr_r=0.6) == 0.6


def test_t1_all_missing_returns_05():
    assert effective_reliability("__t1_absent__") == 0.5


def test_t1_read_side_does_not_clamp():
    # 钳制只发生在填装侧(_apply_calibrated 把 1.0 钳 0.98);读侧原样返回
    assert effective_reliability("__t1_absent__", payload_r=1.0) == 1.0


# ── T2 对象身份不变式(规格 §2.1;填装侧原位不动)──

def test_t2_apply_calibrated_keeps_object_identity(tmp_path):
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({"spamhaus": {"default": 0.91}}))
    before = id(SOURCE_RELIABILITY)
    _registry._apply_calibrated(f)
    assert id(SOURCE_RELIABILITY) == before
    assert SOURCE_RELIABILITY["spamhaus"] == 0.91


# ── T3 结构守门(规格 §2.4/§3:解析有效 r 一律走单入口)──

def test_t3_single_get_literal_inside_effective_reliability():
    # backend/ipdb/ 运行时代码中 SOURCE_RELIABILITY.get( 字面量恰一处,
    # 且位于 effective_reliability 函数体内(新读点合同,规格 §2.4)
    import inspect
    from pathlib import Path
    import ipdb._merge as merge_mod
    pkg = Path(merge_mod.__file__).parent
    hits = [
        str(p.relative_to(pkg))
        for p in sorted(pkg.rglob("*.py"))
        if "SOURCE_RELIABILITY.get(" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert hits == ["_merge.py"]
    assert "SOURCE_RELIABILITY.get(" in inspect.getsource(merge_mod.effective_reliability)


def test_t3_stix_export_no_longer_imports_the_table():
    # _stix_export 改 import effective_reliability,不再 import 表本体
    import inspect
    from ipdb import _stix_export
    assert "SOURCE_RELIABILITY" not in inspect.getsource(_stix_export)
