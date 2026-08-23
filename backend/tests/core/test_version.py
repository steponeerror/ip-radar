"""_version: 版本真源 + base-tag semver 比较（spec F3）。"""
import os
from unittest.mock import patch

from ipdb import _version


class TestVersionConstant:
    def test_reads_build_version_file(self, tmp_path):
        f = tmp_path / "BUILD_VERSION"
        f.write_text("v1.2.0")
        with patch.object(_version, "_BUILD_VERSION_PATH", f):
            assert _version._resolve_version() == "v1.2.0"

    def test_env_fallback_when_no_file(self, tmp_path):
        with patch.object(_version, "_BUILD_VERSION_PATH", tmp_path / "nope"), \
             patch.dict(os.environ, {"IP_RADAR_VERSION": "v9.9.9"}):
            assert _version._resolve_version() == "v9.9.9"

    def test_dev_when_nothing(self, tmp_path):
        with patch.object(_version, "_BUILD_VERSION_PATH", tmp_path / "nope"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IP_RADAR_VERSION", None)
            assert _version._resolve_version() == "dev"


class TestBaseTag:
    def test_plain_tag(self):
        assert _version.base_tag("v1.2.0") == "v1.2.0"

    def test_describe_suffix(self):
        assert _version.base_tag("v1.1.0-3-gabcdef") == "v1.1.0"

    def test_describe_dirty(self):
        assert _version.base_tag("v1.1.0-dirty") == "v1.1.0"

    def test_bare_sha(self):
        # --always 退化输出:无 tag 可达,纯 SHA → base_tag 返回原样,update_available 判 False
        assert _version.base_tag("abc1234") == "abc1234"


class TestUpdateAvailable:
    def test_latest_none_false(self):
        assert _version.update_available("v1.0.0", None) is False

    def test_dev_false(self):
        assert _version.update_available("dev", "v9.0.0") is False

    def test_equal_false(self):
        assert _version.update_available("v1.1.0", "v1.1.0") is False

    def test_ahead_no_banner(self):
        # F3 核心:用户 master 领先 tag → 不弹
        assert _version.update_available("v1.1.0-3-gabc", "v1.1.0") is False

    def test_behind_true(self):
        assert _version.update_available("v1.1.0-3-gabc", "v1.2.0") is True

    def test_bare_sha_never_updates(self):
        # 无法解析 tag → 保守不弹
        assert _version.update_available("abc1234", "v1.2.0") is False


# ── Task 2: GitHub Releases 惰性缓存查询(ETag) ──────────────────────────
# anyio pytest 插件(venv 已装 4.13,自带默认 anyio_backend fixture);
# 类级 marker 覆盖全部 async 方法。
import httpx
import pytest


@pytest.mark.anyio
class TestFetchLatest:
    async def test_success_caches(self):
        _version.reset_cache()
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.headers.get("if-none-match"))
            return httpx.Response(200, json={"tag_name": "v1.2.0", "body": "修复若干", "html_url": "http://x"})

        transport = httpx.MockTransport(handler)
        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=transport)):
            r1 = await _version.fetch_latest()
            r2 = await _version.fetch_latest()  # 命中缓存,不再请求
        assert r1 == {"tag": "v1.2.0", "summary": "修复若干", "url": "http://x"}
        assert r2 == r1
        assert len(calls) == 1

    async def test_304_uses_cache(self):
        _version.reset_cache()
        state = {"etag": None, "n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            etag = request.headers.get("if-none-match")
            if etag:
                return httpx.Response(304, headers={"ETag": etag})
            state["etag"] = '"abc"'
            return httpx.Response(200, json={"tag_name": "v1.3.0", "body": "", "html_url": "http://x"}, headers={"ETag": '"abc"'})

        transport = httpx.MockTransport(handler)
        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=transport)):
            await _version.fetch_latest()
            r2 = await _version.fetch_latest(force=True)  # 回源但 304 → 缓存续命
        assert r2["tag"] == "v1.3.0"
        assert state["n"] == 2

    async def test_network_error_returns_none_and_keeps_cache(self):
        _version.reset_cache()

        async def ok(request):
            return httpx.Response(200, json={"tag_name": "v1.2.0", "body": "b", "html_url": "u"})

        async def dead(request):
            raise httpx.ConnectError("no network")

        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(ok))):
            await _version.fetch_latest()
        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(dead))):
            r = await _version.fetch_latest(force=True)
        assert r == {"tag": "v1.2.0", "summary": "b", "url": "u"}  # 降级吐旧缓存

    async def test_never_succeeded_returns_none(self):
        _version.reset_cache()

        async def dead(request):
            raise httpx.ConnectError("no network")

        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(dead))):
            assert await _version.fetch_latest() is None

    async def test_summary_truncated_200(self):
        _version.reset_cache()

        async def handler(request):
            return httpx.Response(200, json={"tag_name": "v1.2.0", "body": "字" * 300, "html_url": "u"})

        with patch.object(_version, "_client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))):
            r = await _version.fetch_latest()
        assert len(r["summary"]) == 200
