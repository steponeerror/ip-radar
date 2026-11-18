"""honeypot_fyi 源测试(票 #360)。

夹具行 = 2026-11-18 实抓 https://honeypot.fyi/data/blocklist.csv 快照
逐字选出(14,086,191 字节 / 807,843 行;注释 L<n> = 该快照真实行号),
覆盖头/尾边界与真实脏行(环路自命中、RFC1918 混入、curated infra 误指面)。
容错面用合成行并就地标注(实抓全量零畸形行,census 2026-11-18)。
"""
import logging
import os
import time

import pytest

from ipdb._sources.honeypot_fyi import HoneypotFyiSource

ENV_SWITCH = "IP_RADAR_INFRA_NOISE_FILTER"

# ── 实抓夹具(逐字,勿改字节)──
HEAD_ROW = "127.0.0.1, 1603125"          # L1: 首行=环路自命中,全场最高计数
TOP_ATTACKER = "185.22.187.221, 82729"   # L2: 与 dossier 实样逐字同
INFRA_1111 = "1.1.1.1, 73"               # L14204: curated infra(ADR 0008 形)
INFRA_1000 = "1.0.0.1, 66"               # L15352: curated infra(Cloudflare DNS)
PRIVATE_ROW = "10.10.40.17, 70"          # L14673: RFC1918 混入(真实脏行)
INFRA_9999 = "9.9.9.9, 2"                # L249130
INFRA_8888 = "8.8.8.8, 2"                # L255409
INFRA_OPENDNS = "208.67.222.222, 3"      # L216741: curated infra(OpenDNS)
TAIL_ROW = "0.202.30.218, 1"             # L807843: 末行,计数=1 下边界
# curated 全集∩块表 = 恰上述五行(56 员 curated 集,2026-11-18 全量实测);
# 真数据全量回算冒烟:807,843 − 5 = 807,838 鍵,计数对账闭合零丢失


def _write_feed(tmp_path, rows):
    (tmp_path / "honeypot_fyi.csv").write_text(
        "".join(r + "\n" for r in rows))


def test_harvest_yields_verbatim_evidence(tmp_path):
    """A 系取数钩子直测(iptoasn 范本):逐行 yield (ip, Evidence),
    Evidence 三槽与旧 CsvSource parse_row 产物逐键一致;脏行在 harvest
    层就弃(不再依赖基类 cidr 解析)。"""
    _write_feed(tmp_path, [HEAD_ROW, TOP_ATTACKER, "not-an-ip, 5",
                           "5.6.7.8, abc", "1.2.3.4"])
    s = HoneypotFyiSource(data_dir=tmp_path)
    rows = list(s.harvest())
    assert [ip for ip, _ in rows] == ["127.0.0.1", "185.22.187.221"]
    ev = rows[0][1]
    assert ev.classification_type == "blacklist"
    assert ev.verdict == "malicious"
    assert ev.reporter_count == 1603125
    # 字节级一致纪律:to_dict 仅三槽,与旧 CsvSource 存储形状同鍵集
    assert ev.to_dict() == {"classification_type": "blacklist",
                            "verdict": "malicious", "reporter_count": 1603125}


def test_rebuilds_real_capture_rows(tmp_path):
    """实抓四行(避开 curated infra)全量入库,计数逐字保真。"""
    _write_feed(tmp_path, [HEAD_ROW, TOP_ATTACKER, PRIVATE_ROW, TAIL_ROW])
    s = HoneypotFyiSource(data_dir=tmp_path)
    assert s.rebuild() == 4
    for ip, hits in (("127.0.0.1", 1603125), ("185.22.187.221", 82729),
                     ("10.10.40.17", 70), ("0.202.30.218", 1)):
        hit = s.query(ip)
        assert hit, ip
        assert hit[0]["classification_type"] == "blacklist"
        assert hit[0]["verdict"] == "malicious"
        # 命中数照 ipsum 先例(reporter_count)进观测计数槽
        assert hit[0]["reporter_count"] == hits


def test_infra_rows_excluded_at_load_and_restore(
        tmp_path, caplog, monkeypatch):
    """块表实测含 curated infra 五行(1.0.0.1/1.1.1.1/208.67.222.222/
    8.8.8.8/9.9.9.9,curated 56 员集∩全量=恰此五行)→ 载入期排除留痕;
    环路/RFC1918 行非 curated 单址 → 原样保留(宁少算:只排对 curated
    单址的精确指控);关开关重建即复原。"""
    _write_feed(tmp_path, [HEAD_ROW, TOP_ATTACKER, PRIVATE_ROW, TAIL_ROW,
                           INFRA_1111, INFRA_1000, INFRA_9999, INFRA_8888,
                           INFRA_OPENDNS])
    s = HoneypotFyiSource(data_dir=tmp_path)
    with caplog.at_level(logging.INFO, logger="ipdb._sources._infra_filter"):
        assert s.rebuild() == 4
    assert not s.query("8.8.8.8")
    assert not s.query("1.1.1.1")
    assert not s.query("9.9.9.9")
    assert not s.query("1.0.0.1")
    assert not s.query("208.67.222.222")
    assert s.query("127.0.0.1")            # 环路非 curated → 保留
    assert s.query("10.10.40.17")          # RFC1918 非 curated → 保留
    log = [r for r in caplog.records
           if "infra noise filter" in r.getMessage()]
    assert len(log) == 1
    msg = log[0].getMessage()
    assert "honeypot_fyi" in msg and "excluded 5" in msg
    for ip in ("8.8.8.8", "1.1.1.1", "9.9.9.9", "1.0.0.1",
               "208.67.222.222"):
        assert f"{ip}/32" in msg
    # 关开关重建 = 原样回算复原(mtime 后移防族级增量跳过,共享判例同款)
    monkeypatch.setenv(ENV_SWITCH, "0")
    fut = time.time() + 10
    os.utime(tmp_path / "honeypot_fyi.csv", (fut, fut))
    assert s.rebuild() == 9
    assert s.query("8.8.8.8")


def test_malformed_rows_skipped(tmp_path):
    """容错面(合成行,非实抓):计数列缺席/非整数/非法 IP/空行 →
    harvest 层整行跳过。"""
    (tmp_path / "honeypot_fyi.csv").write_text(
        "185.22.187.221\n"          # 合成:单列,缺计数 → 弃
        "5.6.7.8, abc\n"            # 合成:非整数计数 → 弃
        "not-an-ip, 5\n"            # 合成:非法 IP → harvest 层弃
        "\n"
        f"{TAIL_ROW}\n")
    s = HoneypotFyiSource(data_dir=tmp_path)
    assert s.rebuild() == 1
    assert s.query("0.202.30.218")[0]["reporter_count"] == 1


def test_source_declarations_pinned():
    """票 #360 档案面钉在真源类上(URL = 实测真路径,档案 /blocklist.csv
    已 404,见源 docstring)。"""
    assert HoneypotFyiSource.name == "honeypot_fyi"
    assert HoneypotFyiSource.category == "threat"
    assert HoneypotFyiSource.classification_type == "blacklist"
    assert HoneypotFyiSource.verdict == "malicious"
    assert HoneypotFyiSource.reliability == 0.60
    assert HoneypotFyiSource.provenance_tier == "A"
    assert HoneypotFyiSource.infra_noise_filter is True
    assert HoneypotFyiSource.single_evidence is True   # 评审 P1-2 流式声明(census 重复鍵=0)
    assert HoneypotFyiSource.url == "https://honeypot.fyi/data/blocklist.csv"
    assert HoneypotFyiSource.stale_days == 1
    assert not getattr(HoneypotFyiSource, "derived", False)


class _Resp:
    """urlopen mock:真走 download_file 的 chunk 循环(test_abuseipdb 同款)。"""

    def __init__(self, b):
        self._b, self._done = b, False
        self.headers = {"Content-Length": str(len(b))}

    def read(self, n=-1):
        if self._done:
            return b""
        self._done = True
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mock_http(monkeypatch, body: bytes):
    monkeypatch.setattr(
        "ipdb._sources._download.urllib.request.urlopen",
        lambda req, timeout=120: _Resp(body))


def test_download_commits_verbatim_bytes(tmp_path, monkeypatch):
    """成功路径:scratch 校验后原字节提交,不留 scratch 残留。"""
    body = "".join(r + "\n" for r in
                   (HEAD_ROW, TOP_ATTACKER, TAIL_ROW)).encode()
    _mock_http(monkeypatch, body)
    s = HoneypotFyiSource(data_dir=tmp_path)
    s.download()
    assert (tmp_path / "honeypot_fyi.csv").read_bytes() == body
    assert not (tmp_path / "honeypot_fyi.csv.dl").exists()


def test_download_empty_200_and_network_failure_keep_existing(
        tmp_path, monkeypatch):
    """200-OK 空体 → 失败;网络层失败 → 失败;两者都不碰既有好文件
    (abuseipdb scratch 先例:失败永不删旧证据)。"""
    good = (TOP_ATTACKER + "\n").encode()
    p = tmp_path / "honeypot_fyi.csv"
    p.write_bytes(good)
    s = HoneypotFyiSource(data_dir=tmp_path)

    _mock_http(monkeypatch, b"")
    with pytest.raises(RuntimeError, match="Empty response"):
        s.download()
    assert p.read_bytes() == good
    assert not (tmp_path / "honeypot_fyi.csv.dl").exists()

    def _boom(req, timeout=120):
        raise OSError("simulated network failure")
    monkeypatch.setattr("ipdb._sources._download.urllib.request.urlopen",
                        _boom)
    with pytest.raises(Exception):
        s.download()
    assert p.read_bytes() == good
    assert not (tmp_path / "honeypot_fyi.csv.dl").exists()


def test_download_html_error_page_fails(tmp_path, monkeypatch):
    """200-OK 但 body 是 HTML 错误页(Cloudflare 形):零有效行 → 失败,
    既有好文件不动(票 #360「空/不可用 payload 按失败处理」)。"""
    good = (TOP_ATTACKER + "\n").encode()
    p = tmp_path / "honeypot_fyi.csv"
    p.write_bytes(good)
    _mock_http(monkeypatch, b"<html><head><title>404</title></head></html>\n")
    s = HoneypotFyiSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="no valid"):
        s.download()
    assert p.read_bytes() == good
    assert not (tmp_path / "honeypot_fyi.csv.dl").exists()
