"""Tests for ThreatFox source — zip handling + real abuse.ch column mapping."""
import csv
import io
import zipfile
from pathlib import Path

import pytest

from ipdb._sources.threatfox import ThreatFoxSource

# A realistic abuse.ch full.csv data row (space after comma, quoted fields),
# matching the documented header:
# first_seen_utc, ioc_id, ioc_value, ioc_type, threat_type, fk_malware,
# malware_alias, malware_printable, last_seen_utc, confidence_level, ...
_IP_ROW = ('"2026-06-13 12:41:29", "1831757", "1.2.3.4:80", "ip:port", '
           '"payload_delivery", "win.vidar", "None", "Vidar", "", "75", '
           '"True", "None", "Vidar", "1", "reporter"')
_DOMAIN_ROW = ('"2026-06-13 12:41:29", "1831757", "evil.example.com", "domain", '
               '"payload_delivery", "js.clearfake", "None", "ClearFake", "", '
               '"100", "False", "None", "ClearFake", "1", "reporter"')


def _make_source(tmp_path) -> ThreatFoxSource:
    return ThreatFoxSource(data_dir=tmp_path)


class TestThreatFoxParseRow:
    def test_parses_ip_row_with_correct_columns(self, tmp_path):
        src = _make_source(tmp_path)
        row = next(csv.reader([_IP_ROW]))

        parsed = src.parse_row(row)

        assert parsed is not None
        assert parsed["_ip"] == "1.2.3.4"
        assert parsed["classification_type"] == "malware-distribution"
        assert parsed["verdict"] == "malicious"
        assert parsed["malware_name"] == "win.vidar"
        assert parsed["confidence"] == 75
        assert parsed["native_categories"] == ["payload_delivery"]
        assert parsed["extra"] == {"port": "80", "malware_printable": "Vidar",
                                  "threatfox_ioc": "1831757"}

    def test_parse_row_preserves_native_type(self, tmp_path):
        src = _make_source(tmp_path)
        # threat_type = "botnet_cc" column index 4
        row = ["2026-06-14", "1", "9.9.9.9:80", "ip:port", "botnet_cc", "trickbot",
               "", "", "", "90"]
        parsed = src.parse_row(row)
        assert parsed["classification_type"] == "c2-server"
        assert parsed["native_categories"] == ["botnet_cc"]
        assert "native_type" not in parsed["extra"]

    def test_skips_non_ip_rows(self, tmp_path):
        src = _make_source(tmp_path)
        row = next(csv.reader([_DOMAIN_ROW]))

        assert src.parse_row(row) is None

    def test_skips_short_malformed_rows(self, tmp_path):
        src = _make_source(tmp_path)
        # Real abuse.ch dump contains ragged rows; must not raise IndexError.
        assert src.parse_row([]) is None
        assert src.parse_row(["1", "2"]) is None
        assert src.parse_row(["1", "2", "3"]) is None


class TestThreatFoxDownloadUnzips:
    def test_download_extracts_inner_csv_from_zip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ABUSECH_AUTH_KEY", "TESTKEY123")   # v2 认证端点(票 #159)
        # Build a valid zip containing full.csv (what abuse.ch actually serves).
        csv_body = "\n".join(["#"] * 9) + "\n" + _IP_ROW + "\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("full.csv", csv_body)
        zip_bytes = buf.getvalue()
        assert zip_bytes[:4] == b"PK\x03\x04"

        class _Resp:
            def __init__(self, b):
                self._b = b
                self._pos = 0
                self.headers = {}

            def read(self, n=-1):
                if n is None or n < 0:
                    data, self._pos = self._b[self._pos:], len(self._b)
                    return data
                data = self._b[self._pos:self._pos + n]
                self._pos += len(data)
                return data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=120: _Resp(zip_bytes))

        src = _make_source(tmp_path)
        src.download()

        saved = (tmp_path / "threatfox.csv").read_bytes()
        # Must be the extracted CSV, not the zip.
        assert not saved.startswith(b"PK")
        assert b"1.2.3.4" in saved

    def test_download_then_load_yields_records(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ABUSECH_AUTH_KEY", "TESTKEY123")   # v2 认证端点(票 #159)
        csv_body = "\n".join(["#"] * 9) + "\n" + _IP_ROW + "\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("full.csv", csv_body)
        zip_bytes = buf.getvalue()

        class _Resp:
            def __init__(self, b):
                self._b = b
                self._pos = 0
                self.headers = {}

            def read(self, n=-1):
                if n is None or n < 0:
                    data, self._pos = self._b[self._pos:], len(self._b)
                    return data
                data = self._b[self._pos:self._pos + n]
                self._pos += len(data)
                return data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=120: _Resp(zip_bytes))

        src = _make_source(tmp_path)
        src.download()
        count = src.rebuild()

        assert count == 1
        assert src.query("1.2.3.4")[0]["classification_type"] == "malware-distribution"


from ipdb._sources.threatfox import ThreatFoxSource, _clean


def test_parse_row_maps_threat_type(tmp_path):
    src = ThreatFoxSource(data_dir=tmp_path)
    # columns: first_seen, ioc_id, ioc_value, ioc_type, threat_type, fk_malware, ...
    row = ["2026-06-14", "1", "5.6.7.8:443", "ip:port", "payload_delivery", "win.vidar",
           "", "", "", "100"]
    parsed = src.parse_row(row)
    assert parsed["classification_type"] == "malware-distribution"
    assert parsed["malware_name"] == "win.vidar"
    assert parsed["_ip"] == "5.6.7.8"


def test_parse_row_botnet_cc(tmp_path):
    src = ThreatFoxSource(data_dir=tmp_path)
    row = ["2026-06-14", "2", "9.9.9.9:80", "ip:port", "botnet_cc", "trickbot",
           "", "", "", "90"]
    parsed = src.parse_row(row)
    assert parsed["classification_type"] == "c2-server"


def test_threatfox_harvest_per_row_classification(tmp_path):
    from ipdb._sources.threatfox import ThreatFoxSource
    # write a 10-line abuse.ch-style file (9 header + 1 data row)
    lines = ["#hdr"] * 9 + ['"2026-01-01","ip","1.2.3.4:80","ip:port","botnet_cc","win.vidar","","","2026-01-01","85",']
    (tmp_path / "threatfox.csv").write_text("\n".join(lines) + "\n")
    s = ThreatFoxSource(data_dir=tmp_path)
    s._path = tmp_path / "threatfox.csv"
    s.rebuild()
    rec = s.query("1.2.3.4")
    assert rec[0]["classification_type"] == "c2-server"   # botnet_cc → c2-server
    assert rec[0]["malware_name"] == "win.vidar"
    assert rec[0]["confidence"] == 85
    assert rec[0]["native_categories"] == ["botnet_cc"]
    assert "native_type" not in rec[0].get("extra", {})


def test_parse_row_keeps_port_and_printable_and_last_seen(tmp_path):
    src = ThreatFoxSource(data_dir=tmp_path)
    row = ["2026-06-14", "1", "9.9.9.9:443", "ip:port", "botnet_cc", "trickbot",
           "", "TrickBot", "2026-06-20", "90",
           "True", "ref1", "init,loader", "0", "rep1"]
    parsed = src.parse_row(row)
    assert parsed["extra"]["port"] == "443"
    assert parsed["extra"]["malware_printable"] == "TrickBot"
    assert parsed["last_seen"] == "2026-06-20"
    assert parsed["tags"] == ["init", "loader"]


def test_parse_row_optional_fields_absent_when_empty(tmp_path):
    """last_seen 空、无 tags、无端口、printable=None → 键缺席，不存空值。"""
    src = ThreatFoxSource(data_dir=tmp_path)
    row = ["2026-06-14", "2", "1.2.3.4", "ip:port", "botnet_cc", "trickbot",
           "", "None", "", "90"]
    parsed = src.parse_row(row)
    assert "last_seen" not in parsed
    assert "tags" not in parsed
    assert parsed["extra"] == {"threatfox_ioc": "2"}  # ioc_id 必存,其余可选键缺席


def test_harvest_routes_new_fields_to_evidence(tmp_path):
    lines = ["#hdr"] * 9 + ['"2026-01-01","1","5.6.7.8:8080","ip:port","botnet_cc","win.vidar","","Vidar","2026-01-02","85","True","ref","init","0","rep"']
    (tmp_path / "threatfox.csv").write_text("\n".join(lines) + "\n")
    s = ThreatFoxSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("5.6.7.8")[0]
    assert rec["last_seen"] == "2026-01-02"
    assert rec["tags"] == ["init"]
    assert rec["extra"]["port"] == "8080"
    assert rec["extra"]["malware_printable"] == "Vidar"
    assert rec["native_categories"] == ["botnet_cc"]        # 不动（F2）


def test_parse_row_stores_ioc_id(tmp_path):
    """row[1] ioc_id → extra.threatfox_ioc 溯源（URLhaus urlhaus_link 同槽位）。"""
    src = ThreatFoxSource(data_dir=tmp_path)
    row = ["2026-08-24 20:05:08", "1886405", "193.112.28.215:15443", "ip:port",
           "botnet_cc", "win.vshell", "None", "VShell", "", "100", "True",
           "None", "vshell", "1", "anonymous"]
    parsed = src.parse_row(row)
    assert parsed["extra"]["threatfox_ioc"] == "1886405"


# ── v2 认证端点迁移(票 #159,2026-10-23)──────────────────────────────
# 旧匿名出口 https://threatfox.abuse.ch/export/csv/full/ 2026-10-22 起 410;
# 迁 https://threatfox-api.abuse.ch/v2/files/exports/<KEY>/full.csv.zip,
# Auth-Key 在 URL 路径段(非 query)→ download_file 新增 secret 打码参数。

_KEY = "TESTKEY123"
_KEYED_URL = f"https://threatfox-api.abuse.ch/v2/files/exports/{_KEY}/full.csv.zip"


def _fake_urlopen(body: bytes, seen: list, *, final_url: str | None = None,
                  content_length: int | None = None):
    """urlopen 替身:seen 收集每次请求的 full_url;final_url ≠ None 模拟
    重定向落点;content_length > len(body) 模拟传输层截断。"""

    class _Resp:
        def __init__(self):
            self._pos = 0
            self.headers = (
                {"Content-Length": str(content_length)} if content_length else {})

        def geturl(self):
            return final_url or seen[-1]

        def read(self, n=-1):
            if n is None or n < 0:
                n = len(body)
            data = body[self._pos:self._pos + n]
            self._pos += len(data)
            return data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=120):
        seen.append(req.full_url)
        return _Resp()

    return fake


def _zip_bytes(csv_body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("full.csv", csv_body)
    return buf.getvalue()


class TestThreatFoxAuthExport:
    def test_download_requires_auth_key(self, tmp_path, monkeypatch):
        """缺 ABUSECH_AUTH_KEY → download() 报 RuntimeError 明文(票 #159:
        __init__ 缺省空串,不炸 import/构建;下载时才拦)。"""
        monkeypatch.delenv("ABUSECH_AUTH_KEY", raising=False)
        src = _make_source(tmp_path)
        with pytest.raises(RuntimeError, match="ABUSECH_AUTH_KEY"):
            src.download()

    def test_download_builds_keyed_url_class_attr_stays_keyless(self, tmp_path, monkeypatch):
        """keyed URL 只在 download() 内拼;url class attr 保持无 key 占位形状
        (注册表/日志/测试断言面只见占位,票 #159 泄 key 防护)。"""
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        body = _zip_bytes("\n".join(["#"] * 9) + "\n" + _IP_ROW + "\n")
        seen: list[str] = []
        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(body, seen))
        src = _make_source(tmp_path)
        src.download()
        assert seen == [_KEYED_URL]
        assert src.url == "https://threatfox-api.abuse.ch/v2/files/exports/full.csv.zip"
        assert _KEY not in src.url
        saved = (tmp_path / "threatfox.csv").read_bytes()
        assert not saved.startswith(b"PK") and b"1.2.3.4" in saved

    def test_download_rejects_200_ok_bad_body_keeps_old_evidence(self, tmp_path, monkeypatch):
        """200-OK-坏体守卫(Phase 3 step 8 惯例):v2 错误页也是 200,坏体
        不得替换旧证据——既非 PK zip 亦无 first_seen_utc 列头 → RuntimeError。"""
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        old = b"# previous-good-evidence\n"
        (tmp_path / "threatfox.csv").write_bytes(old)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _fake_urlopen(b"<html>login required</html>", []))
        src = _make_source(tmp_path)
        with pytest.raises(RuntimeError, match="threatfox payload"):
            src.download()
        assert (tmp_path / "threatfox.csv").read_bytes() == old   # 旧证据未灭失
        assert not (tmp_path / "threatfox.zip").exists()          # scratch 已清

    def test_download_truncation_error_masks_key(self, tmp_path, monkeypatch):
        """截断报错串里 keyed URL 打码:key 不入消息体,*** 代位(票 #159 P0)。"""
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _fake_urlopen(b"PK" + b"x" * 498, [], content_length=1000))
        src = _make_source(tmp_path)
        with pytest.raises(RuntimeError, match="truncated") as ei:
            src.download()
        assert _KEY not in str(ei.value)
        assert "***" in str(ei.value)
