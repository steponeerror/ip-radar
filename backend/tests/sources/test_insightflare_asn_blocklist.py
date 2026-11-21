"""insightflare_asn_blocklist:ASN 键查询期 join 源(票 #332 P1)。
生命周期合同与 caida_asorg 同款:数据是 hosting ASN 集合(无 CIDR 可入库),
load()/rebuild() 把文件解析为内存 set,query(ip) 恒 None;join 走
hosting_for_asn 钩子——_registry 在 asn 胜者解出后注入 is_hosting 资产
陈述(as_org/org_for_asn join 同款形状)。
夹具行取自实抓全量(dist/hosting.txt,2026-11-15 Release,2,957 行全为
`AS<数字>`、无注释/表头/脏行;以下逐字选自首/尾行)。
"""
import pytest

from ipdb._sources.insightflare_asn_blocklist import InsightflareAsnBlocklistSource

# 实抓样本(逐字:文件首 3 行 + 尾 2 行)
SAMPLE = "AS249\nAS714\nAS939\nAS403156\nAS403187\n"
_FILENAME = "insightflare_asn_blocklist.txt"


def _make(tmp_path, text=SAMPLE):
    (tmp_path / _FILENAME).write_text(text, encoding="utf-8")
    return InsightflareAsnBlocklistSource(tmp_path)


# ── 解析与生命周期(caida_asorg 断言族)──

def test_rebuild_parses_asn_set(tmp_path):
    s = _make(tmp_path)
    n = s.rebuild()
    assert n == 5
    assert s.hosting_for_asn(249) is not None
    assert s.hosting_for_asn(714) is not None
    assert s.hosting_for_asn(403187) is not None
    assert s.hosting_for_asn(99999) is None      # 表外 ASN


def test_hook_accepts_int_and_numeric_str(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    assert s.hosting_for_asn("714") is not None  # 数值字符串可 join
    assert s.hosting_for_asn("not-an-asn") is None
    assert s.hosting_for_asn(None) is None


def test_query_is_none_never_per_ip(tmp_path):
    s = _make(tmp_path)
    s.rebuild()
    assert s.query("1.1.1.1") is None            # 无 CIDR 面,恒不答


def test_health_loaded_and_count(tmp_path):
    s = _make(tmp_path)
    s.load()
    h = s.health()
    assert h.loaded is True
    assert h.record_count == 5
    assert h.is_stale is False                   # 刚写的新文件


def test_load_without_file_returns_zero(tmp_path):
    s = InsightflareAsnBlocklistSource(tmp_path)
    assert s.load() == 0
    assert s.health().loaded is False


def test_fresh_instance_reopens_same_set(tmp_path):
    _make(tmp_path).rebuild()
    s2 = InsightflareAsnBlocklistSource(tmp_path)
    assert s2.load() == 5
    assert s2.hosting_for_asn(249) is not None


# ── 坏行处置:键列坏(非 AS<数字> 形)整行丢弃,不进键计数 ──
# (实抓全量无脏行——2,957 行全 `AS<数字>`;以下坏行是解析器鲁棒性探针,
# 防上游未来混入 HTML 残页/噪声)

def test_dirty_lines_dropped_not_counted(tmp_path):
    s = _make(tmp_path, text=(
        "AS249\n"
        "\n"                 # 空行
        "AS12x\n"            # 坏后缀
        "123\n"              # 裸数字(无 AS 前缀,非本源键形)
        "as714\n"            # 小写前缀(实数据全大写)
        "<html>404</html>\n" # CDN 错误页残行
        "AS403187\n"
    ))
    n = s.rebuild()
    assert n == 2                              # 只剩两个合法 AS 行
    assert s.hosting_for_asn(12) is None       # "AS12x" 不落成 AS12
    assert s.hosting_for_asn(123) is None      # 裸数字不落键
    assert s.hosting_for_asn(714) is None      # 小写行整行丢弃,不污染键


# ── download 守卫(cloudzy/dns_public fail-closed 同款)──

def test_download_fail_closed_keeps_old_file(tmp_path, monkeypatch):
    s = _make(tmp_path)                        # 旧文件在场
    monkeypatch.setattr(
        s, "_http_get", lambda *a, **k: b"<html>Not Found</html>\n")
    monkeypatch.setattr(type(s), "_MIN_ASN_ROWS", 2)
    with pytest.raises(RuntimeError):
        s.download()
    assert (tmp_path / _FILENAME).read_text(encoding="utf-8") == SAMPLE


def test_download_ok_writes_file(tmp_path, monkeypatch):
    s = InsightflareAsnBlocklistSource(tmp_path)
    monkeypatch.setattr(
        s, "_http_get", lambda *a, **k: SAMPLE.encode())
    monkeypatch.setattr(type(s), "_MIN_ASN_ROWS", 2)
    s.download()
    assert (tmp_path / _FILENAME).read_text(encoding="utf-8") == SAMPLE


# ── 元数据契约(源文件内声明)──

def test_metadata_declared_in_file(tmp_path):
    s = _make(tmp_path)
    assert s.name == "insightflare_asn_blocklist"
    assert s.category == "asset"
    assert 0.0 < s.reliability <= 1.0
    assert s.fields == ("is_hosting",)
    assert s.authoritative_for == ()
    assert s.lmdb_backed is False               # 无 per-IP LMDB 面(caida 同款)


# ── 查询期 join:_registry 在 asn 胜者后注入 is_hosting 资产陈述 ──
# (test_registry_new.TestLookupResultShape 桩形状;as_org join 端到端同款思路)

class _FakeFactual:
    def __init__(self, default):
        self.field = ""
        self.default = default

    def merge(self, sv, ctx):
        vals = [v for v in sv.values() if v and v != self.default]
        if not vals:
            from ipdb._types import MergedField
            return MergedField(self.default, 0, "voting", [])
        from ipdb._types import MergedField, SourceAttribution
        return MergedField(vals[0], 85, "voting", [
            SourceAttribution(k, v, 0.5, False) for k, v in sv.items() if v])


class _FakeSource:
    name = "iptoasn"
    fields = ("country_code", "asn", "as_name")

    def __init__(self, asn):
        self._asn = asn

    def health(self):
        from ipdb._types import SourceHealth
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated="2026-11-18T00:00:00Z", is_stale=False)

    def query(self, ip):
        return {"country_code": "US", "asn": self._asn, "as_name": "X"}


@pytest.fixture()
def _fake_registry(monkeypatch):
    import ipdb._registry as reg

    def install(blocklist, asn):
        monkeypatch.setattr(reg, "_sources", [_FakeSource(asn), blocklist])
        monkeypatch.setattr(reg, "_strategies", {
            "country_code": _FakeFactual("N/A"),
            "city": _FakeFactual("N/A"),
            "asn": _FakeFactual(0),
            "as_name": _FakeFactual("N/A"),
            "ip_range": _FakeFactual("N/A"),
        })
    return install


def test_join_injects_is_hosting_statement(tmp_path, _fake_registry):
    s = _make(tmp_path)
    s.load()
    _fake_registry(s, 714)                     # AS714 在清单内
    import ipdb._registry as reg
    r = reg.lookup("1.1.1.1")
    stmts = r.attributes.get("is_hosting")
    assert stmts, "join 未注入 is_hosting 资产陈述"
    st = stmts[0]
    assert st.source == "insightflare_asn_blocklist"
    assert st.value is True
    assert st.native_type                       # native label 在场


def test_join_silent_when_asn_not_listed(tmp_path, _fake_registry):
    s = _make(tmp_path)
    s.load()
    _fake_registry(s, 99999)                    # 表外 ASN
    import ipdb._registry as reg
    r = reg.lookup("1.1.1.1")
    assert not r.attributes.get("is_hosting")


def test_join_respects_allowed_sources(tmp_path, _fake_registry, monkeypatch):
    s = _make(tmp_path)
    s.load()
    _fake_registry(s, 714)
    import ipdb._registry as reg
    r = reg.lookup("1.1.1.1",
                   allowed_sources=frozenset({"iptoasn"}))
    assert not r.attributes.get("is_hosting")   # 白名单过滤,join 不得旁路
