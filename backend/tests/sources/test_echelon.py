"""Echelon Labs per-tag blocklists — 目录布局 / 优先级裁决 / fail-closed 下载.

夹具行 verbatim 取自 2026-11-22 全标签实抓(/tmp/echelon-full,probe 记录
/tmp/echelog.txt):ssh-bruteforcer/outlaw-botnet 共享 1.214.214.114、
1.238.106.229;mirai-scanner/outlaw-botnet 共享 2.26.145.96;
sql-injection-attempt/sharepoint-webshell-scanning 共享 78.128.216.130;
tls.txt 实抓为 0 字节(合法空)。
"""
from pathlib import Path

from ipdb._sources.echelon import EchelonSource, _SLUGS
from ipdb._sources.echelon import ECHELON_MAP

# verbatim from /tmp/echelon-full (2026-11-22 snapshot)
TAG_SSH_BRUTE = "1.214.214.114\n1.238.106.229\n2.57.121.25\n"
TAG_OUTLAW = ("1.214.214.114\n1.238.106.229\n2.180.32.104\n2.26.145.96\n"
              "2.187.38.161\n")
TAG_MIRAI_SCANNER = "2.26.145.96\n47.160.209.223\n84.94.10.219\n216.147.121.64\n"
TAG_Sqli = "102.220.163.241\n185.224.128.198\n45.13.238.166\n45.148.9.76\n78.128.216.130\n"
TAG_SHAREPOINT_WEBSHELL = "78.128.216.130\n"
TAG_WEB_CRAWLER = "1.100.101.102\n1.105.106.107\n1.119.120.121\n"
TAG_TELNET_LOGIN = "101.53.233.137\n101.53.233.185\n101.53.233.20\n"
TAG_IOT_DEFAULT = "101.53.233.137\n101.53.233.185\n101.53.233.20\n101.53.233.88\n"


def _write(tmp_path: Path, files: dict[str, str]) -> EchelonSource:
    d = tmp_path / "echelon"
    d.mkdir(exist_ok=True)
    for name, text in files.items():
        (d / f"{name}.txt").write_text(text, encoding="utf-8")
    return EchelonSource(data_dir=tmp_path)


def test_multi_tag_priority_arbitration(tmp_path: Path):
    """同 IP 命中多标签:blocklist_de 先例——单条证据,classification 按优先级
    裁决(brute-force > infected-system > scanner),全部认领标签进
    native_categories(记录序 = _SLUGS 序)。"""
    s = _write(tmp_path, {
        "ssh-bruteforcer": TAG_SSH_BRUTE,
        "outlaw-botnet": TAG_OUTLAW,
        "mirai-scanner": TAG_MIRAI_SCANNER,
    })
    n = s.rebuild()
    # distinct IPs: ssh∪outlaw∪mirai = {1.214.214.114,1.238.106.229,2.57.121.25,
    # 2.180.32.104,2.26.145.96,2.187.38.161,47.160.209.223,84.94.10.219,216.147.121.64}
    assert n == 9
    # brute-force(ssh) 优先于 infected-system(outlaw/mirai)
    rec = s.query("1.214.214.114")
    assert len(rec) == 1
    assert rec[0]["classification_type"] == "brute-force"
    assert rec[0]["native_categories"] == ["outlaw-botnet",
                                           "ssh-bruteforcer"]        # _SLUGS 序
    # 仅 mirai-scanner+outlaw-botnet 的 IP → infected-system 裁决
    rec2 = s.query("2.26.145.96")
    assert len(rec2) == 1
    assert rec2[0]["classification_type"] == "infected-system"
    assert rec2[0]["native_categories"] == ["mirai-scanner", "outlaw-botnet"]


def test_exploit_outranks_scanner(tmp_path: Path):
    """exploit(sql-injection-attempt) > scanner(sharepoint-webshell-scanning)。"""
    s = _write(tmp_path, {"sql-injection-attempt": TAG_Sqli,
                          "sharepoint-webshell-scanning": TAG_SHAREPOINT_WEBSHELL})
    s.rebuild()
    rec = s.query("78.128.216.130")
    assert len(rec) == 1
    assert rec[0]["classification_type"] == "exploit"
    assert rec[0]["native_categories"] == ["sharepoint-webshell-scanning",
                                           "sql-injection-attempt"]


def test_per_tag_classification_and_evidence_contract(tmp_path: Path):
    """per-tag 分类查证 + Evidence 契约形状(无 extra.native_type)。"""
    from ipdb._evidence import Evidence
    s = _write(tmp_path, {"web-crawler": TAG_WEB_CRAWLER,
                          "telnet-login-attempt": TAG_TELNET_LOGIN,
                          "iot-default-credential-attempt": TAG_IOT_DEFAULT})
    s.rebuild()
    # web-crawler → scanner
    rec = s.query("1.100.101.102")
    assert len(rec) == 1
    assert rec[0]["classification_type"] == "scanner"
    assert rec[0]["native_categories"] == ["web-crawler"]
    assert "native_type" not in (rec[0].get("extra") or {})
    # 两标签同类(brute-force)合并为一条,natives 全留
    rec2 = s.query("101.53.233.137")
    assert len(rec2) == 1
    assert rec2[0]["classification_type"] == "brute-force"
    assert rec2[0]["native_categories"] == [
        "iot-default-credential-attempt", "telnet-login-attempt"]
    # Evidence 契约:裸 /32 记录 == Evidence(classification/verdict/reliability)
    assert rec[0] == Evidence(
        classification_type="scanner", verdict="malicious",
        reliability=0.70, native_categories=["web-crawler"],
    ).to_dict()


def test_empty_tag_file_is_legal_zero(tmp_path: Path):
    """空标签文件 = 当日无该类攻击(合法空),不产生条目也不报错。"""
    s = _write(tmp_path, {"tls": "", "web-crawler": TAG_WEB_CRAWLER})
    assert s.rebuild() == 3
    assert not s.query("9.9.9.9")


def test_fresh_instance_load_reopens(tmp_path: Path):
    """LMDB 卫生(convention 7):rebuild 实例不复用 load(),新实例重开同 env。"""
    s1 = _write(tmp_path, {"web-crawler": TAG_WEB_CRAWLER})
    assert s1.rebuild() == 3
    s2 = EchelonSource(data_dir=tmp_path)
    assert s2.load() == 3
    h = s2.health()
    assert h.record_count == 3
    assert h.last_updated is not None        # max mtime across files
    assert h.is_stale is False               # 文件刚写,stale_days=3


def test_health_max_mtime_across_files(tmp_path: Path):
    import os, time
    s = _write(tmp_path, {"web-crawler": TAG_WEB_CRAWLER,
                          "telnet-login-attempt": TAG_TELNET_LOGIN})
    old = tmp_path / "echelon" / "web-crawler.txt"
    past = time.time() - 10 * 86400
    os.utime(old, (past, past))              # 10 天前 → 超过 stale_days=3
    fresh = tmp_path / "echelon" / "telnet-login-attempt.txt"
    h = EchelonSource(data_dir=tmp_path).health()
    assert h.last_updated is not None
    assert h.is_stale is False               # max mtime = 新文件,不 stale
    os.utime(fresh, (past, past))            # 两个都旧 → stale
    h2 = EchelonSource(data_dir=tmp_path).health()
    assert h2.is_stale is True


def test_map_covers_all_slugs():
    """ECHELON_MAP 必须覆盖全部 61 个订阅 slug——上游改名/新增标签当天绊线,
    不静默落 other(botscout 映射完备性同款)。"""
    assert set(ECHELON_MAP) == set(_SLUGS)
    assert len(_SLUGS) == 61
    assert "web-commad-injection" not in _SLUGS   # 上游拼写死标签,不订阅


# ── download 契约(blocklist_de 同款两阶段 + 本源独有全量空 fail-closed)──

def test_download_all_empty_fail_closed(tmp_path: Path):
    """全 61 文件空 = 上游断供 → RuntimeError + 零替换(防灾难性全空清库)。
    与 blocklist_de 的锚门不同:本源无聚合锚列表,活性判据 = 全量非空集。"""
    import pytest
    from unittest.mock import patch
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh-bruteforcer.txt"
    old.write_text("1.2.3.4\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"")          # 全部 200-OK 空载荷

    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        with pytest.raises(RuntimeError):
            src.download()
    assert old.read_text() == "1.2.3.4\n"    # 零替换
    assert not (src._path / "ssh-bruteforcer.txt.dl").exists()


def test_download_all_empty_with_failures_fail_closed(tmp_path: Path):
    """空+失败混合(全部无内容)同判 fail-closed:零替换 + raise。"""
    import pytest
    from unittest.mock import patch
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh-bruteforcer.txt"
    old.write_text("1.2.3.4\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/tls"):
            raise RuntimeError("404")
        Path(dest).write_bytes(b"")

    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        with pytest.raises(RuntimeError):
            src.download()
    assert old.read_text() == "1.2.3.4\n"


def test_download_partial_failure_keeps_old_file(tmp_path: Path):
    """单标签失败容忍:旧文件字节级保留、其余落地、失败名记
    last_partial_failure、scratch 无残留(SA-F1)。"""
    from unittest.mock import patch
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    src._path.mkdir(parents=True)
    old = src._path / "tls.txt"
    old.write_text("5.6.7.8\n")

    def fake_dl(url, dest, token=None, headers=None, **kw):
        if url.endswith("/tls"):
            raise RuntimeError("boom")
        Path(dest).write_bytes(b"1.2.3.4\n")

    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        src.download()                       # 不 raise
    assert (src._path / "ssh-bruteforcer.txt").read_bytes() == b"1.2.3.4\n"
    assert old.read_text() == "5.6.7.8\n"
    assert src.last_partial_failure == ["tls"]
    assert not (src._path / "tls.txt.dl").exists()


def test_download_legit_empty_tag_lands_zero_byte(tmp_path: Path):
    """合法空:当日无攻击的标签落 0 字节文件(下一 epoch 出清旧条目)。"""
    from unittest.mock import patch
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    src._path.mkdir(parents=True)
    (src._path / "tls.txt").write_text("6.6.6.6\n")   # 旧条目待出清

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"" if url.endswith("/tls") else b"1.2.3.4\n")

    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        src.download()
    assert (src._path / "tls.txt").read_bytes() == b""
    assert src.last_partial_failure == []


def test_download_all_failed_raises(tmp_path: Path):
    """全部标签抓取失败 → raise(防空 rebuild 清库)。"""
    import pytest
    from unittest.mock import patch
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    with patch("ipdb._sources.echelon.download_file",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            src.download()


def test_download_cancel_leaves_no_scratch(tmp_path: Path):
    import pytest
    from unittest.mock import patch
    from ipdb._sources._download import CancelToken, CancelledError
    src = EchelonSource(tmp_path, selected_tags=["ssh-bruteforcer", "tls"])
    src._path.mkdir(parents=True)
    old = src._path / "ssh-bruteforcer.txt"
    old.write_text("1.2.3.4\n")
    token = CancelToken()

    def fake_dl(url, dest, token=None, headers=None, **kw):
        Path(dest).write_bytes(b"5.6.7.8\n")
        token.cancel()                       # 首标签抓完即取消

    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        with pytest.raises(CancelledError):
            src.download(token=token)
    assert old.read_text() == "1.2.3.4\n"
    assert not (src._path / "ssh-bruteforcer.txt.dl").exists()


def test_download_serial_politeness_no_concurrency(tmp_path: Path):
    """礼貌串行:61 个小文件走 CDN 必须逐个抓(标签序 = 调用序),不得并发轰。"""
    from unittest.mock import patch
    calls: list[str] = []
    active = 0
    peak = 0

    def fake_dl(url, dest, token=None, headers=None, **kw):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        calls.append(url.rsplit("/", 1)[-1])
        Path(dest).write_bytes(b"1.2.3.4\n")
        active -= 1

    src = EchelonSource(tmp_path)
    with patch("ipdb._sources.echelon.download_file", side_effect=fake_dl):
        src.download()
    assert peak == 1                          # 严格串行
    assert calls == [f"{s}" for s in _SLUGS]  # _SLUGS 序逐个
    assert src.last_partial_failure == []
