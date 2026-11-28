# backend/tests/eval/test_eval_accusation.py
"""accusation.is_accusation 表驱动(#529):一条证据算不算指控的单一判断。

裁决 2026-11-28(工单 #529,所有者答「甲」):verdict ∈ _ACCUSING
(malicious/suspicious)才算指控;缺键 / None / 空串一律不算(宁少算)。
此前九处调用点五家缺键兑底 malicious、四家缺键即滤,口径分叉由本函数收口;
变异证据:把函数缺键支改回兑底 malicious → 本表 malicious 行外的全部行红。
"""
import pytest

from ipdb._eval.accusation import is_accusation


@pytest.mark.parametrize("detail, accusing", [
    ({"source": "s"}, False),                             # 缺 verdict 键
    ({"source": "s", "verdict": None}, False),            # None
    ({"source": "s", "verdict": ""}, False),              # 空串(弃权拼写)
    ({"source": "s", "verdict": "malicious"}, True),
    ({"source": "s", "verdict": "suspicious"}, True),
    ({"source": "s", "verdict": "benign"}, False),
    ({"source": "s", "verdict": "informational"}, False),
])
def test_is_accusation_table(detail, accusing):
    assert is_accusation(detail) is accusing
