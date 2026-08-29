from ipdb._validate import validate_source
from ipdb._classification import CLASSIFICATION_TYPES


class _Good:
    name = "good"; fields = ("is_malicious",); classification_type = "c2-server"
    reliability = 0.7
    category = "threat"  # 元数据契约(spec §5.1):干净源必须声明 category
    def health(self): ...
    def query(self, ip): ...
    def load(self): ...


class _BadClassType:
    name = "bad"; fields = ("is_malicious",)
    classification_type = "not-a-real-type"   # not in CLASSIFICATION_TYPES
    def query(self, ip): ...


class _Collision:
    name = "col"; fields = ("is_malicious",)
    classification_type = "blacklist"
    # declares a field_map that collides: same source col → two slots (simulated
    # by exposing a bad field_map attr the validator inspects)
    field_map = {"col_a": "malware_name", "col_b": "malware_name"}


def test_good_source_validates_clean():
    assert validate_source(_Good()) == []


def test_bad_classification_type_flagged():
    probs = validate_source(_BadClassType())
    assert any("classification_type" in p for p in probs)


def test_field_map_collision_flagged():
    probs = validate_source(_Collision())
    assert any("collision" in p.lower() or "malware_name" in p for p in probs)


# ── 元数据契约护栏(spec 2026-08-28 §5.1)──
import pytest
from ipdb._validate import validate_source as _vs  # noqa: F401 (brief 原样保留)

class _Fake:  # 最小源桩
    name = "fake"; classification_type = None; field_map = None
    reliability = 0.5; category = "threat"; authoritative_for = ("is_tor",)

def test_category_required_and_enum():
    ok = validate_source(_Fake())
    assert ok == []
    class Bad(_Fake): category = "bogus"
    assert any("category" in p for p in validate_source(Bad()))

def test_reliability_range():
    class Bad(_Fake): reliability = 1.5
    assert any("reliability" in p for p in validate_source(Bad()))

def test_authoritative_for_known_fields():
    class Bad(_Fake): authoritative_for = ("not_a_field",)
    assert any("authoritative_for" in p for p in validate_source(Bad()))


# ── metadata_problems 独立函数(Controller 修正 #2:registry 启动 raise 用它)──
from ipdb._validate import metadata_problems

def test_metadata_problems_clean_stub():
    assert metadata_problems(_Fake()) == []

def test_metadata_problems_three_states():
    class BadCat(_Fake): category = "bogus"
    class BadRel(_Fake): reliability = 1.5
    class BadAuth(_Fake): authoritative_for = ("not_a_field",)
    assert any("category" in p for p in metadata_problems(BadCat()))
    assert any("reliability" in p for p in metadata_problems(BadRel()))
    assert any("authoritative_for" in p for p in metadata_problems(BadAuth()))

def test_metadata_problems_independent_of_legacy_checks():
    # legacy 语法类问题不影响 metadata_problems(它只看元数据契约)
    class LegacyMess(_Fake):
        classification_type = "not-a-real-type"
        field_map = {"a": "nowhere_slot"}
    assert metadata_problems(LegacyMess()) == []
