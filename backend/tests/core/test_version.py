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
