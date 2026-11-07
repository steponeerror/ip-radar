"""T3 结构守门(#315,规格 §3):lookup() 旁路收编为 _BYPASS_SPECS 声明表。
①源名字面量只许活在表项 trigger 里:lookup() 本体不得出现
"geolite_city"/"rir_delegated" 字面量,且必须引用 _BYPASS_SPECS(防表
被内联拼法旁路绕成死代码);②表形/表序:表项四要素齐(key/trigger/
collect/resolve)、key ⊆ LookupResult 出海字段、表序 = 组装序(city_zh,
location, registration)。新增旁路合同:复用既有出海字段 = 仅加表项;
需新出海字段 = 另加 _types.py 字段 + lookup() 出海 kwarg 一行——本测试
钉的是①②(字面量缺席 + 表形/表序/键⊆字段),钉不了未来改动次数。"""
import dataclasses
import inspect

import ipdb._registry as reg
from ipdb._types import LookupResult


def test_lookup_body_has_no_bypass_source_names():
    src = inspect.getsource(reg.lookup)
    assert "geolite_city" not in src
    assert "rir_delegated" not in src
    # lookup() 本体必须引用登记表:防表被换拼法的内联旁路绕成死代码。
    assert "_BYPASS_SPECS" in src


def test_bypass_specs_table_shape():
    keys = [spec.key for spec in reg._BYPASS_SPECS]
    assert keys == ["city_zh", "location", "registration"]
    for spec in reg._BYPASS_SPECS:
        assert callable(spec.trigger)
        assert callable(spec.collect)
        assert callable(spec.resolve)
    result_fields = {f.name for f in dataclasses.fields(LookupResult)}
    assert set(keys) <= result_fields
