"""T3 结构守门(#315,规格 §3):lookup() 旁路收编为 _BYPASS_SPECS 声明表。
两断言机械钉死「新旁路只碰一处」:①lookup() 本体内不得再出现旁路源名
"geolite_city"/"rir_delegated" 字面量(源名只许活在表项 trigger 里);
②表项四要素齐(key/trigger/collect/resolve)、key 与 LookupResult 出海
字段对应、表序 = 组装序(city_zh, location, registration)。"""
import dataclasses
import inspect

import ipdb._registry as reg
from ipdb._types import LookupResult


def test_lookup_body_has_no_bypass_source_names():
    src = inspect.getsource(reg.lookup)
    assert "geolite_city" not in src
    assert "rir_delegated" not in src


def test_bypass_specs_table_shape():
    keys = [spec.key for spec in reg._BYPASS_SPECS]
    assert keys == ["city_zh", "location", "registration"]
    for spec in reg._BYPASS_SPECS:
        assert callable(spec.trigger)
        assert callable(spec.collect)
        assert callable(spec.resolve)
    result_fields = {f.name for f in dataclasses.fields(LookupResult)}
    assert set(keys) <= result_fields
