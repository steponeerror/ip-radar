"""blocklist.net.ua — 分号 CSV / 显式解封行过滤 / REASON 关键词分类.

显式解封语义(本源独有):UNBAN_DATE <= now 的行跳过(出库)——测试用
固定远未来(4102444800 = 2100-01-01)/远过去(1600000000 = 2020-09-13)
时间戳钉住,测试 74 年内确定性成立。REASON 行 verbatim 取自 2026-11-22
实抓(/tmp/nerd-eval-netua.csv,83,674 行,BAN/UNBAN 为 unix 秒,REASON
双语带引号;нагрузка 行实测无引号裸值)。
"""
from pathlib import Path

from ipdb._sources.blocklist_netua import BlocklistNetUaSource, NETUA_MAP

ACTIVE = "4102444800"      # 2100-01-01 — 未解封
UNBANNED = "1600000000"    # 2020-09-13 — 已解封 → 出库

SAMPLE = (
    'IP;BAN_DATE;UNBAN_DATE;"REASON"\n'
    # DDoS(词表 ddos)
    '1.0.136.129;1767206003;' + ACTIVE + ';"DDoS атака на сайт 127.lyceum.kr.ua / DDoS attack on site 127.lyceum.kr.ua"\n'
    # 扫描(词表 сканиров/scanning)→ scanner
    '1.0.140.125;1794729713;' + ACTIVE + ';"Несанкционированное сканирование хостов / Unauthorized scanning of hosts"\n'
    # email спам → spam
    '2.56.101.139;1612956965;' + ACTIVE + ';"Рассылка email спама / Send spam emails"\n'
    # паразитный трафик → ddos(HTTP flood 族,上游自译)
    '1.20.172.252;1790796034;' + ACTIVE + ';"Паразитный трафик на сайт domkrovli.od.ua / Parasite traffic on site domkrovli.od.ua"\n'
    # нагрузка(实测无引号裸值)→ ddos(过载冲击)
    '3.237.31.222;1778565152;' + ACTIVE + ';нагрузка\n'
    # 无差别指控(词表无净槽)→ blacklist 兜底
    '2.56.116.164;1779879123;' + ACTIVE + ';"Malicious VNC traffic"\n'
    # брутфорс(xmlrpc 行含逗号/斜杠,verbatim)→ brute-force
    '8.8.4.4;1700000000;' + ACTIVE + ';"Брутфорс атака на сайт mediatour.com.ua. Запросы к скрипту: /xmlrpc.php / Brute force attack on site mediatour.com.ua. Requests to the script: /xmlrpc.php"\n'
    # 已解封 → 出库(核心语义)
    '1.170.100.218;1794619753;' + UNBANNED + ';"Паразитные запросы к сайту nektar.net.ua / Parasite requests to the website nektar.net.ua"\n'
    # 同 IP 第二行(不同 REASON)→ 第二条独立证据
    '1.0.136.129;1770000000;' + ACTIVE + ';"Несанкционированное сканирование хостов / Unauthorized scanning of hosts"\n'
    # UNBAN 无法解析(缺值)→ 防御性保留(仅有显式过去解封才出库)
    '9.9.9.9;1794619753;;"DDoS атака на сайт x.ua / DDoS attack on site x.ua"\n'
    # 尾部截断行(实抓 83,243. 同型)→ 跳过
    "83.243.\n"
)


def _build(tmp_path: Path) -> BlocklistNetUaSource:
    (tmp_path / "blocklist_netua.csv").write_text(SAMPLE, encoding="utf-8")
    return BlocklistNetUaSource(data_dir=tmp_path)


def test_unbanned_rows_are_dropped(tmp_path: Path):
    """显式解封 = 出库:UNBAN_DATE <= now 的行不进库(本源独有语义)。"""
    s = _build(tmp_path)
    assert s.rebuild() == 8                  # 11 数据行 - 1 解封 - 1 截断 - 1 无IP
    assert not s.query("1.170.100.218")      # 已解封 → 无记录


def test_classification_per_reason_keyword(tmp_path: Path):
    s = _build(tmp_path)
    s.rebuild()
    expect = {
        "1.0.136.129": {"ddos", "scanner"},      # 两行 → 两类
        "1.0.140.125": {"scanner"},
        "2.56.101.139": {"spam"},
        "1.20.172.252": {"ddos"},                # паразит → HTTP flood 族
        "3.237.31.222": {"ddos"},                # нагрузка 裸值
        "2.56.116.164": {"blacklist"},           # Malicious VNC → 兜底
        "8.8.4.4": {"brute-force"},
        "9.9.9.9": {"ddos"},                     # 缺 UNBAN → 防御性保留
    }
    for ip, types in expect.items():
        recs = s.query(ip)
        assert recs, ip
        assert {r["classification_type"] for r in recs} == types, ip


def test_native_categories_reason_verbatim(tmp_path: Path):
    """native_categories 放 REASON 原文(含双语全句、逗号斜杠),不裁剪。"""
    s = _build(tmp_path)
    s.rebuild()
    recs = s.query("8.8.4.4")
    assert len(recs) == 1
    assert recs[0]["native_categories"] == [
        "Брутфорс атака на сайт mediatour.com.ua. Запросы к скрипту: /xmlrpc.php"
        " / Brute force attack on site mediatour.com.ua. Requests to the script:"
        " /xmlrpc.php"]
    rec2 = s.query("3.237.31.222")
    assert rec2[0]["native_categories"] == ["нагрузка"]
    assert "native_type" not in (rec2[0].get("extra") or {})


def test_first_seen_from_ban_date_unix_to_iso(tmp_path: Path):
    """first_seen = BAN_DATE unix 秒 → ISO-Z(衰减轴;house 首见语义)。"""
    s = _build(tmp_path)
    s.rebuild()
    rec = s.query("2.56.101.139")[0]
    assert rec["first_seen"] == "2021-02-10T11:36:05Z"     # 1612956965
    # 同 IP 两行各带各的 BAN_DATE,互不覆盖
    by_type = {r["classification_type"]: r for r in s.query("1.0.136.129")}
    assert by_type["ddos"]["first_seen"] == "2025-12-31T18:33:23Z"   # 1767206003
    assert by_type["scanner"]["first_seen"] == "2026-02-02T02:40:00Z"  # 1770000000


def test_same_ip_two_reasons_two_evidence(tmp_path: Path):
    """convention 3:每行一条证据——同 IP 不同 REASON 两条证据共存
    (全证据去重,由 Source 基类累积器保证)。"""
    s = _build(tmp_path)
    s.rebuild()
    recs = s.query("1.0.136.129")
    assert len(recs) == 2
    for r in recs:
        assert r["verdict"] == "malicious"
        assert r["reliability"] == 0.70


def test_fresh_instance_load_reopens(tmp_path: Path):
    s1 = _build(tmp_path)
    assert s1.rebuild() == 8
    s2 = BlocklistNetUaSource(data_dir=tmp_path)
    assert s2.load() == 8
    assert s2.query("9.9.9.9")


def test_map_keywords_are_vocabulary_terms():
    """NETUA_MAP 值必须全在受控词表内(词表现场读,勿造词)。"""
    from ipdb._classification import CLASSIFICATION_TYPES
    assert set(NETUA_MAP.values()) <= CLASSIFICATION_TYPES


# ── download 截断防护(上游 2022-08 截断 bug 前科:原子写前内容校验)──

def test_download_rejects_missing_header(tmp_path: Path):
    """首行非表头(截断/改版)→ 拒收,旧文件字节级保留。"""
    import pytest
    from unittest.mock import patch
    src = BlocklistNetUaSource(tmp_path)
    src._data_dir.mkdir(parents=True, exist_ok=True)
    old = tmp_path / "blocklist_netua.csv"
    old.write_text(SAMPLE, encoding="utf-8")

    truncated = SAMPLE.splitlines(keepends=True)[1:5]   # 数据行无表头的半截
    with patch.object(BlocklistNetUaSource, "_http_get",
                      return_value="".join(truncated).encode("utf-8")):
        with pytest.raises(RuntimeError, match="header"):
            src.download()
    assert old.read_text(encoding="utf-8") == SAMPLE   # 旧文件未动


def test_download_rejects_empty_body(tmp_path: Path):
    import pytest
    from unittest.mock import patch
    src = BlocklistNetUaSource(tmp_path)
    src._data_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(BlocklistNetUaSource, "_http_get", return_value=b"\n"):
        with pytest.raises(RuntimeError):
            src.download()


def test_download_accepts_valid_body(tmp_path: Path):
    from unittest.mock import patch
    src = BlocklistNetUaSource(tmp_path)
    src._data_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(BlocklistNetUaSource, "_http_get",
                      return_value=SAMPLE.encode("utf-8")):
        src.download()
    assert (tmp_path / "blocklist_netua.csv").read_text(encoding="utf-8") == SAMPLE
