"""消费端文档 ↔ 实现对拍(#510,第四轮架构评审卡 32)。

手册与集成说明的四处说法曾与实现漂移且无测试管:判定值漏
`informational`、分类词表手抄 10/19、STIX 段写了不产出的
observed-data、graylog 顶层置信度写成「最差组选角」。本文件钉四条腿:

1. 判定值集:两份 MANUAL 的「融合判定/fused verdict」行反引号词集
   ⊇ PRECEDENCE 全部键(真源 = backend/ipdb/_merge.py
   _assess_classification 内的函数局部 dict,import 取不到,ast 解析)。
2. 分类词表:两份 MANUAL 的「IntelMQ 词表/vocabulary」行反引号词集
   == ipdb._classification.CLASSIFICATION_TYPES(全集等值,多漏都红)。
3. STIX 对象清单:backend/ipdb/_stix_export.py 实际构造的 stix2 对象
   类型(ast Call 全量扫描)↔ 本文件固定清单——以后新增对象类型而
   手册没跟,先在构造侧红,清单更新后手册提及腿接着钉文档侧;
   两份 MANUAL 的 STIX 段逐类提到(按手册自己的叫法)且禁现
   observed-data。
4. graylog README:verdict 行反引号词集 ⊇ PRECEDENCE 键;旧说法
   "worst classification by precedence" 禁现(顶层置信度是全部指控组
   证人明细池化重算的后验,_types.LookupResult.threat_summary
   2026-10-04 refusion;「最差组选角」只剩空池边界兜底)。

句式锚点照真文档写(test_vocab_contract.py 先例;正则命中失败时断言
消息带文件与期望形状,不许提取器空转绿)。前端文件一律读仓内源码,
路径锚 __file__,worktree/主检出各自自洽。
"""
import ast
import re
from pathlib import Path

from ipdb._classification import CLASSIFICATION_TYPES

REPO = Path(__file__).resolve().parents[3]  # 仓库根(先例 test_vocab_contract.py)

MANUAL_EN = REPO / "MANUAL.md"
MANUAL_ZH = REPO / "MANUAL.zh-CN.md"
GRAYLOG_README = REPO / "integrations/graylog/README.md"
STIX_EXPORT_PY = REPO / "backend/ipdb/_stix_export.py"
MERGE_PY = REPO / "backend/ipdb/_merge.py"

# _stix_export.py 实际构造的 stix2 对象类型(2026-11-27 #510 逐类核对):
# Bundle 是容器不算对象类型;UUID 是 uuid5 命名空间的 stdlib 调用。
_STIX_OBJECT_TYPES = {
    "Identity", "Indicator", "Relationship",
    "IPv4Address", "IPv6Address", "AutonomousSystem", "Location",
}
_STIX_SANCTIONED_NON_OBJECT_CALLS = {"Bundle", "UUID"}
# 手册 STIX 段对每个对象类型的提及词(按手册自己的叫法,不硬套 STIX
# 类型名;两份手册都用英文词,大小写不敏感比对)。
_STIX_MANUAL_MENTIONS = {
    "Identity": "identity",
    "Indicator": "indicator",
    "Relationship": "relationship",
    "IPv4Address": "ipv4",
    "IPv6Address": "ipv6",
    "AutonomousSystem": "autonomous system",
    "Location": "location",
}


def _merge_precedence_keys() -> set[str]:
    """PRECEDENCE 是 _assess_classification 的函数局部变量,import 不到,
    ast 解析赋值节点取键集(_merge.py 内该名唯一)。"""
    tree = ast.parse(MERGE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "PRECEDENCE"
                        for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            keys = {k.value for k in node.value.keys}
            assert len(keys) == len(node.value.keys), \
                "backend/ipdb/_merge.py PRECEDENCE 出现重复键"
            return keys
    raise AssertionError(
        "backend/ipdb/_merge.py 找不到 PRECEDENCE dict(判定值集真源漂了?"
        "测试选择器要跟着改)")


def _manual_section(text: str, header: str) -> str:
    """取 `header` 小节(到下一个 # 标题)的正文。"""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    assert start is not None, (
        f"找不到小节 {header!r}(手册结构变了,测试选择器要跟着改)")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("#")), len(lines))
    return "\n".join(lines[start + 1:end])


def _contract_line(section: str, phrase: str, path: Path) -> str:
    line = next((ln for ln in section.splitlines() if phrase in ln), None)
    assert line is not None, (
        f"{path.name}: 小节里找不到含 {phrase!r} 的行(句式漂了,测试选择器"
        "要照真文档改,不照想象写)")
    return line


def _stix_paragraph(text: str, path: Path) -> str:
    """STIX 段 = `**STIX 2.1**` 起到空行为止的连续块(Exports 小节内)。"""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.lstrip().startswith("**STIX 2.1**")), None)
    assert start is not None, f"{path.name}: 找不到 STIX 段(**STIX 2.1** 起)"
    body = []
    for ln in lines[start:]:
        if not ln.strip() and body:
            break
        body.append(ln)
    return "\n".join(body)


# --- 1. 判定值集 ----------------------------------------------------------

def test_manual_verdict_line_covers_all_precedence_values():
    keys = _merge_precedence_keys()
    for path, header, phrase in (
            (MANUAL_EN, "### The verdict line", "fused verdict"),
            (MANUAL_ZH, "### 判定行", "融合判定")):
        line = _contract_line(_manual_section(path.read_text(encoding="utf-8"),
                                              header), phrase, path)
        backticked = set(re.findall(r"`([^`]+)`", line))
        missing = keys - backticked
        assert not missing, (
            f"{path.name}:{header} 的判定行反引号缺判定值 {missing}"
            f"(实现真源 backend/ipdb/_merge.py PRECEDENCE = {sorted(keys)};"
            "informational 只在纯存档证据在场、无指控证据时出现)")


# --- 2. 分类词表 ----------------------------------------------------------

def test_manual_intelmq_vocab_line_equals_classification_types():
    for path, header, phrase in (
            (MANUAL_EN, "### Per-type threat evidence", "IntelMQ vocabulary"),
            (MANUAL_ZH, "### 逐类型威胁证据", "IntelMQ 词表")):
        line = _contract_line(_manual_section(path.read_text(encoding="utf-8"),
                                              header), phrase, path)
        listed = set(re.findall(r"`([^`]+)`", line))
        assert listed == set(CLASSIFICATION_TYPES), (
            f"{path.name}:{header} 的 IntelMQ 词表行与 CLASSIFICATION_TYPES"
            f" 不等值:手册多写 {sorted(listed - set(CLASSIFICATION_TYPES))},"
            f"手册漏写 {sorted(set(CLASSIFICATION_TYPES) - listed)}"
            "(真源 backend/ipdb/_classification.py;dns/ntp 是良性断言的"
            "面标签,非威胁词汇)")


# --- 3. STIX 对象清单 -----------------------------------------------------

def test_stix_export_constructs_exactly_documented_object_types():
    called = set()
    for node in ast.walk(ast.parse(STIX_EXPORT_PY.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id[:1].isupper():
            # 只认大写开头的调用(stix2 对象构造形态);set/dict/list 等
            # 内建小写调用不入榜
            called.add(node.func.id)
    assert "Bundle" in called, (
        "backend/ipdb/_stix_export.py 里扫不到 Bundle( 构造——扫描空转,"
        "文件换结构了要改选择器")
    objects = called - _STIX_SANCTIONED_NON_OBJECT_CALLS
    assert objects == _STIX_OBJECT_TYPES, (
        f"_stix_export.py 实际构造的对象类型 {sorted(objects)} ≠ 固定清单 "
        f"{sorted(_STIX_OBJECT_TYPES)}(多出的类型 = 新增了手册没跟的对象;"
        "少了 = 有对象类型被删)。两边一起改:先更本清单,手册 STIX 段"
        "跟着提及,test_manual_stix_sections_* 会钉文档侧)")


def test_manual_stix_sections_mention_every_object_type_and_no_observed_data():
    for path, header in ((MANUAL_EN, "## 4. Exports"), (MANUAL_ZH, "## 4. 导出")):
        para = _stix_paragraph(
            _manual_section(path.read_text(encoding="utf-8"), header), path)
        assert "observed-data" not in para, (
            f"{path.name}: STIX 段不许再写 observed-data——_stix_export.py"
            "不产该对象(Identity/地址 SCO/location/autonomous-system/"
            "relationship/Indicator)")
        missing = [obj for obj, mention in _STIX_MANUAL_MENTIONS.items()
                   if mention not in para.lower()]
        assert not missing, (
            f"{path.name}: STIX 段缺对象类型提及 {missing}(固定清单见 "
            "test_stix_export_constructs_exactly_documented_object_types)")


# --- 4. graylog README ----------------------------------------------------

def test_graylog_verdict_values_and_no_worst_pick_phrase():
    text = GRAYLOG_README.read_text(encoding="utf-8")
    row = next((ln for ln in text.splitlines() if "Threat verdict" in ln), None)
    assert row is not None, "graylog README 找不到 Threat verdict 行(漂了改名)"
    backticked = set(re.findall(r"`([^`]+)`", row))
    missing = _merge_precedence_keys() - backticked
    assert not missing, (
        f"integrations/graylog/README.md verdict 行缺判定值 {missing}"
        "(实现真源 backend/ipdb/_merge.py PRECEDENCE 四值)")
    assert not re.search(r"worst\s+classification\s+by\s+precedence", text), (
        "graylog README 禁现旧说法 worst classification by precedence——"
        "顶层置信度是全部指控组证人明细池化重算的后验(_types.py "
        "threat_summary,2026-10-04 refusion),不是最差组自己的置信度;"
        "单指控组时数字才恰好等于该组 confidence")
