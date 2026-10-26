"""SR-T3 (#214): scanner_ranges 自报段标签 merge → API 契约钉测。

链路(spec /tmp/scanner-ranges-spec.md §设计定案 5;EXPLORE §3 2026-10-26):
真 ScannerRangesSource + 离线 fixture CSV(不碰网络)→ lookup() 全链(真
to_observation / _assess_classification,仅 monkeypatch _sources,先例
test_lookup_pipeline.py)→ ClassificationAssessment.details 的
native_categories 键 → LookupResult.to_dict() → LookupResultOut 响应模型
(ClassificationOut.details: list[dict] 通用透传,extra=allow)。产品代码
零改(用户裁定零新 UI 机制;透传已通用),以测试钉住不漂移。

红证口径(本票零实现,测试的咬合性经 tamper-red 证明,不落 commit):
摘 _merge.py detail 组装的 native_categories 条件键 → 本文件必红;摘
SourceDetailRow.tsx chip 渲染 → 前端 SourceDetailRow.test.tsx 必红。

verdict_conflict 不点亮(spec §5):scanner_ranges 无良性断言(verdict=
malicious 是行为类型断言,"aggressive scanning" 词表,拒 benign② 路线),
指控组内无 benign 对立 → 无冲突面,断言 False 钉住。
"""
import pytest

from ipdb._api_models import LookupResultOut
from ipdb._sources.scanner_ranges import ScannerRangesSource

# spec §设计定案 6 验收冒烟例(离线版):40.124.175.29 = stretchoid 段内
# (census 例证 IP)= malicious 判决 + scanner 证人行标签
# 「研究扫描 · Stretchoid(自报段)」。fixture 喂该段即可,不必真抓。
_FIXTURE = "40.124.175.0/24,Stretchoid\n"
_LABEL = "研究扫描 · Stretchoid(自报段)"

# detail 期望形状:scanner_ranges 证据只带四键(源/r/verdict/标签),无
# first_seen 等其他条件键 → 整 dict 精确钉(逐字段一键不多不少)。
_EXPECTED_DETAIL = {
    "source": "scanner_ranges",
    "reliability": 0.90,
    "verdict": "malicious",
    "native_categories": [_LABEL],
}


@pytest.fixture
def scanner_src(tmp_path, monkeypatch):
    """真 ScannerRangesSource(离线 fixture,rebuild 打开 reader 打查询门)。"""
    (tmp_path / "scanner_ranges.csv").write_text(_FIXTURE)
    src = ScannerRangesSource(data_dir=tmp_path)
    assert src.rebuild() == 1
    import ipdb._registry as reg
    monkeypatch.setattr(reg, "_sources", [src])
    return src


def test_acceptance_ip_malicious_verdict_with_label_detail(scanner_src):
    """验收例:恶意判决照旧 + 指控证人照列 + 标签全文在 detail
    + verdict_conflict 不点亮(无良性断言 → 无冲突面)。"""
    from ipdb._registry import lookup
    r = lookup("40.124.175.29")

    # 恶意判决照旧(spec §5):threat 摘要 verdict=malicious,scanner 在指控类型内
    # (typed LookupResult 无 threat 属性,摘要经 threat_summary() 序列化面取)
    summary = r.threat_summary()
    assert summary["verdict"] == "malicious"
    assert "scanner" in summary["types"]

    ca = r.classifications["scanner"]
    assert ca.type == "scanner"
    assert ca.verdict == "malicious"
    assert ca.detected is True
    assert ca.corroborated is False       # 单源自报段,无第二票(宁少算)
    assert ca.verdict_conflict is False   # 无良性断言 → 冲突面不存在
    assert ca.details == [_EXPECTED_DETAIL]
    # 证人行全部为指控观测,无 benign(verdict=malicious 行为类型断言)
    assert all(d["verdict"] == "malicious" for d in ca.details)


def test_label_survives_api_response_model(scanner_src):
    """API 出海面:GET /api/lookup/{ip} 与 POST /api/query/stream 同构
    (LookupResultOut 响应模型);标签键经响应模型逐字段可见,形状零漂移。"""
    from ipdb._registry import lookup
    r = lookup("40.124.175.29")

    out = LookupResultOut.model_validate(r.to_dict())
    api_ca = out.classifications["scanner"]
    assert api_ca.verdict == "malicious"
    assert api_ca.verdict_conflict is False
    assert api_ca.details == [_EXPECTED_DETAIL]
    # 序列化后仍逐字段可见(response_model 出的真实 JSON 形状)
    dumped = out.model_dump()
    assert dumped["classifications"]["scanner"]["details"] == [_EXPECTED_DETAIL]
    assert dumped["classifications"]["scanner"]["verdict_conflict"] is False
