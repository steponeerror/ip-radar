# backend/ipdb/_eval/accusation.py
"""一条证据(classification detail)算不算指控 —— 全仓评测面单一判断。

裁决 2026-11-28(#529,所有者答「甲」):证据缺 verdict 键按「不算
指控」(宁少算)。此前九处调用点各抄一份判式:五处缺键兑底 malicious
(metrics._effective_votes / layered._accusing_sources / exclusive.
flagged_sources / matrix_scan._detail_sources / sentinel.
_own_accusing_ctypes),四处缺键即滤(anchors / agg_share /
anchor_readouts / sinkhole_probe)——分叉旧账见 metrics.py 旧注释。
现网弃权源都不带分类类型,不进观测,本统一只影响评测口径,不动
线上计分(_merge/_logodds 未改;_ACCUSING 定义未改)。"""
from .._types import _ACCUSING


def is_accusation(detail: dict) -> bool:
    """detail 载荷的 verdict ∈ _ACCUSING(malicious/suspicious)才算
    指控;缺键、None、空串一律不算(#529 裁决 2026-11-28,宁少算;
    与生产读路径旧「兑底 malicious」口径的取舍见票 #529)。"""
    return detail.get("verdict") in _ACCUSING
