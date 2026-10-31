"""#253 B 家族 url/filename 非空护栏(metadata_problems 发现期 raise 通道)。

源底座上收(#248/#250,ADR 0014)把 IpListSource 裸注解(漏定义 __init__
即 AttributeError)换成 SourceBase 空串默认——漏定义 filename 从「启动即
炸」退化为「静默空路径」(空路径 = data 目录本身)。本组测试钉住还原后的
闸:合成坏子类发现期即拒,有意空串源显式豁免。2026-10-31 裁决:B1(仅
B 家族)+ E1(显式 url_exempt 标记);A 家族不查(票面口径,新增保护另开票)。
"""
from pathlib import Path

from ipdb._source_base import Source
from ipdb._sources._base import CsvSource, IpListSource
from ipdb._validate import metadata_problems


def _probs(cls, data_dir: Path | None = None):
    """实例化后跑发现期同一检查函数(registry._discover_sources 调用面)。"""
    return metadata_problems(cls(data_dir=data_dir or Path("/tmp")))


class _MissingFilename(IpListSource):
    name = "bad_no_filename"
    url = "https://example.com/list.txt"
    fields = ("is_malicious",)
    # filename 漏定义 → 继承 SourceBase 空串默认(#250 弱化场景本体)


class _EmptyUrlNoExempt(IpListSource):
    name = "bad_no_url"
    filename = "bad_no_url.txt"
    fields = ("is_malicious",)
    # url 漏定义 → 空串走家族默认 download() 必坏


class _WhitespaceUrl(IpListSource):
    name = "bad_ws_url"
    url = "   "
    filename = "bad_ws_url.txt"
    fields = ("is_malicious",)


class _UrlExemptB(IpListSource):
    name = "ok_exempt"
    url = ""
    filename = "ok_exempt.txt"
    fields = ("is_malicious",)
    url_exempt = True


class _GoodB(IpListSource):
    name = "ok_b"
    url = "https://example.com/l.txt"
    filename = "l.txt"
    fields = ("is_malicious",)


class _CsvMissingFilename(CsvSource):
    name = "bad_csv_no_filename"
    url = "https://example.com/x.csv"
    fields = ("is_malicious",)


class _BareA(Source):
    """A 家族不查(裁决 B1):url/filename 全空也不报——钉住门控面。"""

    name = "bare_a"
    fields = ("is_malicious",)

    def harvest(self):  # Source 抽象钩子,实例化不触发
        yield from ()


def test_missing_filename_rejected():
    """#250 弱化场景本体:漏定义 filename 的合成坏子类被拒。"""
    probs = _probs(_MissingFilename)
    assert any("filename is empty" in p for p in probs), probs


def test_empty_url_without_exempt_rejected():
    probs = _probs(_EmptyUrlNoExempt)
    assert any("url is empty" in p for p in probs), probs


def test_whitespace_url_rejected():
    """空白串非空壳:url='   ' 与漏定义同罪(strip 后校验)。"""
    probs = _probs(_WhitespaceUrl)
    assert any("url is empty" in p for p in probs), probs


def test_url_exempt_marker_and_good_source_pass():
    assert _probs(_UrlExemptB) == []
    assert _probs(_GoodB) == []


def test_csvsource_family_gated_too():
    """CsvSource 经 IpListSource 继承命中门控(isinstance 家族面)。"""
    assert any("filename is empty" in p for p in _probs(_CsvMissingFilename))


def test_a_family_not_checked():
    """裁决 B1 钉面:A 家族(及 duck-type 桩)不进本护栏。"""
    assert _probs(_BareA) == []


def test_real_exempted_sources_clean(tmp_path: Path):
    """现役两个有意空串 B 家族源(firehol/blocklist_de)豁免后零问题。"""
    from ipdb._sources.firehol import FireholBlocklistSource
    from ipdb._sources.blocklist_de import BlocklistDeSource
    assert FireholBlocklistSource.url_exempt is True
    assert BlocklistDeSource.url_exempt is True
    assert metadata_problems(FireholBlocklistSource(data_dir=tmp_path)) == []
    assert metadata_problems(BlocklistDeSource(data_dir=tmp_path)) == []


def test_discovery_smoke_all_real_sources(tmp_path: Path):
    """61 源真实发现冒烟:护栏对现役 roster 零误伤(发现期 raise 即本测红)。"""
    import ipdb._registry as reg
    sources = reg._discover_sources(tmp_path)
    names = {s.name for s in sources}
    assert len(sources) == 61          # 本票时点 roster;增删源时同步
    assert {"firehol", "blocklist_de", "malicious_ip", "urlhaus"} <= names
    for s in sources:
        assert metadata_problems(s) == [], s.name
