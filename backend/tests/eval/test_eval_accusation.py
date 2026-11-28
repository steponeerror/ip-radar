# backend/tests/eval/test_eval_accusation.py
"""accusation.is_accusation 表驱动(#529):一条证据算不算指控的单一判断。

裁决 2026-11-28(工单 #529,所有者答「甲」):verdict ∈ _ACCUSING
(malicious/suspicious)才算指控;缺键 / None / 空串一律不算(宁少算)。
此前九处调用点五家缺键兑底 malicious、四家缺键即滤,口径分叉由本函数收口;
变异证据:把函数缺键支改回兑底 malicious → 仅缺键行红;None / 空串行的键
在场,走的是「值不在指控集」那条路,不受该变异影响(评审更正,2026-11-28)。
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
    ({"source": "s", "verdict": True}, False),            # 非字符串
    ({"source": "s", "verdict": 1}, False),               # 非字符串
    ({"source": "s", "verdict": "Malicious"}, False),     # 大小写精确匹配
    ({"source": "s", "verdict": " malicious"}, False),    # 前后空白不算
    ({"source": "s", "verdict": "abstain"}, False),      # 未知词
])
def test_is_accusation_table(detail, accusing):
    assert is_accusation(detail) is accusing
