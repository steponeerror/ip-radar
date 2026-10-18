"""rir_abuse 源测试(RIR 注册库 abuse contact,类 3 所有权与联系;2026-10-18
重扫批第 1 名交接件,docs/research/2026-10-18-rdns-abuse-contact-rescan.md)。"""
import gzip
import ipaddress

import pytest

from ipdb._sources.rir_abuse import RirAbuseSource


def _rpsl_db(o: int, v6tag: str, dom: str) -> str:
    """同构 RPSL 样本(ripe/afrinic 两文件同构造):对齐/嵌套/非对齐 inetnum、
    孤儿 abuse-c、无邮箱 role、inet6num、带 abuse-mailbox 的 role +
    org_name 扩展形态 ≥10:⑦organisation 对象、⑧org: 可解析 inetnum
    (org_name + 无损长 descr)、⑨org: 悬空引用 inetnum、⑩descr-only /
    org-only(不产键,准入仍 abuse-c 驱动)。"""
    return f"""\
% registry dump comment header
inetnum:        {o}.15.0.0 - {o}.15.255.255
netname:        OUTER-NET
abuse-c:        ACRO15229-RIPE

inetnum:        {o}.15.7.0 - {o}.15.7.255
netname:        INNER-NET
abuse-c:        ACRO15230-RIPE

inetnum:        192.0.{o}.10 - 192.0.{o}.43
netname:        UNALIGNED-NET
abuse-c:        ACRO15229-RIPE

inetnum:        203.0.{o}.0 - 203.0.{o}.255
netname:        ORPHAN-NET
abuse-c:        NOBODY-RIPE

inetnum:        198.51.{o}.0 - 198.51.{o}.255
netname:        NOMAIL-NET
abuse-c:        NOMAIL-RIPE

inet6num:       2001:db8:{v6tag}:: - 2001:db8:{v6tag}:ffff:ffff:ffff:ffff:ffff
netname:        V6-NET
abuse-c:        ACRO15229-RIPE

inet6num:       2a02:{v6tag}::/32
netname:        V6-PFX-NET
abuse-c:        ACRO15230-RIPE

inetnum:        45.{o}.0.0 - 45.{o}.0.255
netname:        ORG-NET
descr:          {_LONG_DESCR}
org:            ORG-ET1-RIPE
abuse-c:        ACRO15229-RIPE

inetnum:        46.{o}.0.0 - 46.{o}.0.255
netname:        GHOST-NET
org:            ORG-GHOST-RIPE
abuse-c:        ACRO15230-RIPE

inetnum:        203.0.{o}.240 - 203.0.{o}.244
netname:        DESCRONLY-NET
descr:          descr alone never admits a key

inetnum:        203.0.{o}.250 - 203.0.{o}.254
netname:        ORGONLY-NET
org:            ORG-ET1-RIPE

role:           Outer Abuse Role
address:        Some Street
                Tel: +31 20 123 4567
nic-hdl:        ACRO15229-RIPE
abuse-mailbox:  abuse@{dom}

role:           Inner Abuse Role
nic-hdl:        ACRO15230-RIPE
abuse-mailbox:  core@{dom}

role:           Role Without Mailbox
nic-hdl:        NOMAIL-RIPE

organisation:   ORG-ET1-RIPE
org-name:       Example Telecom BV
"""


# ⑧ 形态的 descr:333 字符超长值——无损红线钉死(原样进 extra,不截断不设槽)
_LONG_DESCR = "ERX router block for example telecom." * 9
_RIPE_DB = _rpsl_db(145, "aaaa", "ripe.example")
_AFRINIC_DB = _rpsl_db(196, "bbbb", "afrinic.example")


def _write_source(tmp_path) -> RirAbuseSource:
    src = RirAbuseSource(data_dir=tmp_path)
    d = tmp_path / "rir_abuse"
    d.mkdir(exist_ok=True)
    for reg, text in (("ripe", _RIPE_DB), ("afrinic", _AFRINIC_DB)):
        with gzip.open(d / f"{reg}.db.gz", "wt", encoding="utf-8") as f:
            f.write(text)
    return src


def _expected_v4() -> int:
    """每文件 = 对齐 2 键(外层 /16 + 内层 /24)+ 非对齐范围展开(stdlib
    现场算真值,rir_delegated 同风格)+ org 扩展 2 键(ORG-NET /24 +
    GHOST-NET /24;⑩ descr-only/org-only 不产键不计);两文件同构 ×2。"""
    n = len(list(ipaddress.summarize_address_range(
        ipaddress.IPv4Address("192.0.145.10"),
        ipaddress.IPv4Address("192.0.145.43"))))
    return 2 * (4 + n)


def test_rebuild_count_and_health_record_count(tmp_path):
    src = _write_source(tmp_path)
    n = src.rebuild()
    assert n == _expected_v4()
    assert src.health().record_count == n
    assert src._count6 == 4            # 每文件 2 个 v6 键(范围形 /48 + 前缀形 /32)
    src._reader.close()
    src._reader6.close()
    # LMDB 卫生:同 base 第二实例前先 close;load 读回计数一致
    s2 = RirAbuseSource(data_dir=tmp_path)
    assert s2.load() == n
    s2._reader.close()
    s2._reader6.close()


def test_query_most_specific_hit_and_abstention(tmp_path):
    src = _write_source(tmp_path)
    src.rebuild()
    # 嵌套段:内层 /24 胜外层 /16(最长前缀)
    row = src.query("145.15.7.8")[0]
    assert row["abuse_contact"] == "core@ripe.example"
    assert row["extra"]["registry"] == "ripe"
    assert row["extra"]["abuse_c"] == "ACRO15230-RIPE"
    assert row["extra"]["netname"] == "INNER-NET"
    # 外层段命中
    row = src.query("145.15.200.1")[0]
    assert row["abuse_contact"] == "abuse@ripe.example"
    assert row["verdict"] == ""       # 弃权拼写:信息位不指控(R17A-1)
    # v6 同链:范围形与 RPSLng 前缀形(RFC 4012,现行 inet6num 标准)双路
    row = src.query("2001:db8:aaaa::1")[0]
    assert row["abuse_contact"] == "abuse@ripe.example"
    row = src.query("2a02:aaaa::1")[0]
    assert row["abuse_contact"] == "core@ripe.example"
    assert row["extra"]["netname"] == "V6-PFX-NET"
    # afrinic 文件出键且 registry 标注正确
    row = src.query("196.15.0.9")[0]
    assert row["abuse_contact"] == "abuse@afrinic.example"
    assert row["extra"]["registry"] == "afrinic"
    src._reader.close()
    src._reader6.close()


def test_query_unresolved_and_uncovered(tmp_path):
    """abuse-c 解不出邮箱(不存在 role / role 无 abuse-mailbox)不产生键;
    未覆盖 IP 返回 {}。"""
    src = _write_source(tmp_path)
    src.rebuild()
    assert src.query("203.0.145.7") == {}    # 指向不存在的 role → 丢
    assert src.query("198.51.145.7") == {}   # role 无 abuse-mailbox → 不进映射
    assert src.query("8.8.8.8") == {}        # 无对象覆盖
    assert src.query("2001:db8::1") == {}    # v6 未覆盖安静
    src._reader.close()
    src._reader6.close()


def test_harvest_unaligned_range_summarizes(tmp_path):
    """非对齐范围展开 = stdlib summarize 真值(对齐快速路等价,dbip_city
    同款断言风格)。"""
    src = _write_source(tmp_path)
    got = {c for c, ev in src.harvest() if c.startswith("192.0.145.")}
    want = {str(n) for n in ipaddress.summarize_address_range(
        ipaddress.IPv4Address("192.0.145.10"),
        ipaddress.IPv4Address("192.0.145.43"))}
    assert got == want


def test_download_guard_thin_payload_keeps_old(monkeypatch, tmp_path):
    """守卫 fail-closed:薄载荷(对象计数不足)不替换旧文件;全败 raise。"""
    src = _write_source(tmp_path)      # 先放合法旧文件

    def fake(url, dest, token=None, timeout=None, headers=None):
        with gzip.open(dest, "wt", encoding="utf-8") as f:
            f.write("inetnum: 1.2.3.0 - 1.2.3.255\nabuse-c: X\n")

    monkeypatch.setattr("ipdb._sources.rir_abuse.download_file", fake)
    with pytest.raises(RuntimeError, match="all rir_abuse feeds failed"):
        src.download()
    with gzip.open(tmp_path / "rir_abuse" / "ripe.db.gz", "rt",
                   encoding="utf-8") as f:
        assert "145.15.0.0" in f.read()     # 旧数据保留
    assert not list((tmp_path / "rir_abuse").glob("*.dl"))   # scratch 已清


def test_declares_org_name_field_and_authority():
    """类属性快照:fields/authoritative_for 双槽(abuse_contact+org_name);
    descr 永不设槽(extra-only by design)。"""
    assert RirAbuseSource.fields == ("abuse_contact", "org_name")
    assert RirAbuseSource.authoritative_for == ("abuse_contact", "org_name")


def test_org_name_resolved_and_unresolved_rows(tmp_path):
    """⑧ org: 可解析 → org_name 出现 + descr 无损随行(超长原样不截断);
    ⑨ org: 悬空引用 → 只丢 org_name(None 槽被 to_dict 丢),行内
    abuse_contact 仍在(宁少算:整行证据不因单字段缺席而丢)。⑦
    organisation 对象形态经 ORG-NET 解析链隐式钉死。"""
    src = _write_source(tmp_path)
    src.rebuild()
    # ⑧ 可解析
    row = src.query("45.145.0.1")[0]
    assert row["org_name"] == "Example Telecom BV"
    assert row["abuse_contact"] == "abuse@ripe.example"
    assert row["extra"]["descr"] == _LONG_DESCR    # 333 字符原样,无损红线
    # ⑨ 悬空引用:org_name 缺席,abuse_contact 存活
    row = src.query("46.145.0.1")[0]
    assert "org_name" not in row
    assert row["abuse_contact"] == "core@ripe.example"
    assert "descr" not in row["extra"]
    # afrinic 文件同链同解析(organisation 对象两文件各有)
    row = src.query("45.196.0.1")[0]
    assert row["org_name"] == "Example Telecom BV"
    assert row["extra"]["registry"] == "afrinic"
    src._reader.close()
    src._reader6.close()


def test_descr_only_and_org_only_rows_produce_no_key(tmp_path):
    """⑩ 语义钉死(计划歧义裁决):键空间准入仍由 abuse-c 解析驱动
    (现状语义不变,宁少算/no-bloat)——descr 仅随行、org 仅解析,
    均不独立产键;纯 descr 行与 org-only 行都不出键。"""
    src = _write_source(tmp_path)
    src.rebuild()
    assert src.query("203.0.145.242") == {}   # bare descr,无 abuse-c 无 org
    assert src.query("203.0.145.252") == {}   # org 可解析但无 abuse-c
    src._reader.close()
    src._reader6.close()


def test_org_name_full_chain_to_merged_field(monkeypatch, tmp_path):
    """rebuild→query→merge 全链(Task 1 读路径 × 本源真产数据):源行
    org_name 经 SCALAR_SLOTS 收集 → NamingAuthority → LookupResult
    (单证人 conf=85/authority,abuse_contact 同链同证)。"""
    src = _write_source(tmp_path)
    src.rebuild()
    from ipdb import _registry
    import ipdb._merge as _merge
    monkeypatch.setattr(_registry, "_sources", [src])
    monkeypatch.setattr(_registry, "_disabled", set())
    monkeypatch.setattr(_merge, "SOURCE_RELIABILITY", {"rir_abuse": 0.85})
    lr = _registry.lookup("45.145.0.1")
    assert lr.org_name.value == "Example Telecom BV"
    assert lr.org_name.confidence == 85          # int(0.85*100+0.5)
    assert lr.org_name.algorithm == "authority"
    assert lr.org_name.sources[0].source == "rir_abuse"
    assert lr.abuse_contact.value == "abuse@ripe.example"
    src._reader.close()
    src._reader6.close()
