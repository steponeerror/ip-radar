"""R10 混杂披露测试: 十二条冻结清单 + 渲染契约 (spec §7)。

冻结清单特征片段按 ①-⑫ 顺序钉死(spec §7 正源), 缺一条/错序即 FAIL。
"""
from ipdb._eval.disclosures import REQUIRED_CONFOUNDS, render_disclosures

_FRAGMENTS = (
    "整抄", "v4-only", "ASN", "出口段", "/24", "rir",
    "otx", "ip2proxy", "ctype", "未验证阴性", "滚动窗", "地域分层",
)
_INDEXES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"


def test_required_confounds_exactly_twelve():
    assert len(REQUIRED_CONFOUNDS) == 12


def test_render_twelve_lines_numbered_complete_in_order():
    lines = render_disclosures({}, {})
    assert len(lines) == 12
    assert [line[0] for line in lines] == list(_INDEXES)  # 序号完整且有序


def test_each_clause_covers_spec_fragment():
    for line, frag in zip(render_disclosures({}, {}), _FRAGMENTS):
        assert frag in line, f"missing spec §7 fragment {frag!r}"


def test_v4_only_line_contains_true():
    v4 = next(line for line in render_disclosures({}, {}) if line[0] == "②")
    assert "True" in v4


def test_extra_appends_tail_without_touching_twelve():
    base = render_disclosures({}, {})
    out = render_disclosures({}, {}, extra=["外注甲", "外注乙"])
    assert out[:12] == base                    # 十二条原样, 不覆盖不重排
    assert out[12:] == ["外注甲", "外注乙"]    # extra 只追加在尾


def test_render_deterministic_and_matches_constants():
    assert render_disclosures({}, {}) == list(REQUIRED_CONFOUNDS)
    assert render_disclosures({}, {}) == render_disclosures({}, {})
