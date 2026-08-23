"""L2 解锁四条件 + docker.sock 项目名自发现(F1)。"""
import socket
from unittest.mock import patch

import httpx
import pytest

from ipdb import _update


@pytest.fixture(autouse=True)
def _clean():
    _update.reset_checks()
    yield
    _update.reset_checks()


def test_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("IP_RADAR_SELF_UPDATE", raising=False)
    monkeypatch.delenv("IP_RADAR_UPDATE_TOKEN", raising=False)
    monkeypatch.setenv("IP_RADAR_REPO_DIR", str(tmp_path))
    assert _update.self_update_enabled() is False


def test_all_four_conditions(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_RADAR_SELF_UPDATE", "1")
    monkeypatch.setenv("IP_RADAR_UPDATE_TOKEN", "sekrit")
    monkeypatch.setenv("IP_RADAR_REPO_DIR", str(tmp_path))
    with patch.object(_update, "_sock_writable", lambda: True), \
         patch.object(_update, "_git_ok", lambda path: True):
        assert _update.self_update_enabled() is True


def test_missing_token_disables(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_RADAR_SELF_UPDATE", "1")
    monkeypatch.delenv("IP_RADAR_UPDATE_TOKEN", raising=False)
    monkeypatch.setenv("IP_RADAR_REPO_DIR", str(tmp_path))
    with patch.object(_update, "_sock_writable", lambda: True), \
         patch.object(_update, "_git_ok", lambda path: True):
        assert _update.self_update_enabled() is False


def test_compose_labels_parses_response():
    body = b'{"Config": {"Labels": {"com.docker.compose.project": "ip-radar", "com.docker.compose.service": "ipradar"}}}'
    with patch.object(_update, "_http_unix_get", lambda path: body), \
         patch.object(socket, "gethostname", lambda: "abc123container"):
        assert _update._compose_labels() == {"com.docker.compose.project": "ip-radar",
                                             "com.docker.compose.service": "ipradar"}


def test_compose_labels_failure_returns_none():
    with patch.object(_update, "_http_unix_get", lambda path: None):
        assert _update._compose_labels() is None


def test_http_unix_get_uses_uds_transport():
    """B1: httpx 0.28.1 不支持 http+unix scheme,必须走 uds transport。"""
    with patch("httpx.HTTPTransport") as mt, patch("httpx.Client") as mc:
        mc.return_value.__enter__.return_value.get.return_value = httpx.Response(200, content=b"ok")
        r = _update._http_unix_get("/containers/abc/json")
    mt.assert_called_once_with(uds=_update.DOCKER_SOCK)
    mc.assert_called_once_with(transport=mt.return_value)
    called_url = mc.return_value.__enter__.return_value.get.call_args[0][0]
    assert called_url.startswith("http://localhost")
    assert r == b"ok"


def test_git_ok_empty_dir_short_circuits():
    """M1: repo_dir 未配置不得退化到 CWD(容器 WORKDIR 可能恰是 git 仓库)。"""
    with patch.object(_update.sp, "run", side_effect=AssertionError("must not run git")):
        assert _update._git_ok("") is False
