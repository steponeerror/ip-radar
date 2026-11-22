"""#406 _paths:路径类 IP_RADAR_* 解析唯一真源 —— 单测 + 消费方一致性对拍。

对拍两档(env 设/未设)钉「同一 env 状态下全部路径消费者同源」:
折并前 _update 回落 /app/data 而 _registry 回落 <backend>/data,
dev 检出上 update_state.json 会落到不可写路径(第一红,已绿)。"""
from pathlib import Path

import pytest

from ipdb import _paths

_APP_DIR = Path(_paths.__file__).resolve().parent.parent


# ── 单测:各访问器 env 优先 + 缺省回落 ─────────────────────────────


def test_data_dir_env_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    assert _paths.data_dir() == tmp_path
    monkeypatch.delenv("IP_RADAR_DATA_DIR")
    assert _paths.data_dir() == _APP_DIR / "data"


def test_source_state_path_env_and_derivation(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SOURCE_STATE_PATH", raising=False)
    assert _paths.source_state_path() == tmp_path / "source_state.json"
    monkeypatch.setenv("SOURCE_STATE_PATH", str(tmp_path / "s.json"))
    assert _paths.source_state_path() == tmp_path / "s.json"


def test_env_path_or_state_sibling_truthiness(monkeypatch, tmp_path):
    # #258 折并钉子随迁:空串 env 视同未设(真值语义,折并前后零变化)
    monkeypatch.setenv("SOURCE_STATE_PATH", str(tmp_path / "s.json"))
    assert _paths.env_path_or_state_sibling(
        "IP_RADAR_AUTH_DB", "auth.db") == tmp_path / "auth.db"
    monkeypatch.setenv("IP_RADAR_AUTH_DB", "")
    assert _paths.env_path_or_state_sibling(
        "IP_RADAR_AUTH_DB", "auth.db") == tmp_path / "auth.db"
    monkeypatch.setenv("IP_RADAR_AUTH_DB", str(tmp_path / "x.db"))
    assert _paths.env_path_or_state_sibling(
        "IP_RADAR_AUTH_DB", "auth.db") == tmp_path / "x.db"


def test_update_state_path_env_and_derivation(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("IP_RADAR_STATE_FILE", raising=False)
    assert _paths.update_state_path() == tmp_path / "update_state.json"
    monkeypatch.setenv("IP_RADAR_STATE_FILE", str(tmp_path / "u.json"))
    assert _paths.update_state_path() == tmp_path / "u.json"


def test_update_state_default_uses_backend_data_not_app_literal(monkeypatch):
    # #406 修活钉子:未设 env 时回落 <backend>/data,不再落容器字面量
    # /app/data(dev 检出不可写;容器 env 恒有值不受影响)
    monkeypatch.delenv("IP_RADAR_STATE_FILE", raising=False)
    monkeypatch.delenv("IP_RADAR_DATA_DIR", raising=False)
    assert _paths.update_state_path() == \
        _APP_DIR / "data" / "update_state.json"


def test_repo_and_compose_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("IP_RADAR_REPO_DIR", raising=False)
    monkeypatch.delenv("IP_RADAR_COMPOSE_FILE", raising=False)
    assert _paths.repo_dir() == ""
    assert _paths.compose_file() == "docker-compose.yml"   # repo="" 同 os.path.join
    monkeypatch.setenv("IP_RADAR_REPO_DIR", str(tmp_path))
    assert _paths.compose_file() == str(tmp_path / "docker-compose.yml")
    monkeypatch.setenv("IP_RADAR_COMPOSE_FILE", "/x.yml")
    assert _paths.compose_file() == "/x.yml"


def test_eval_dir_env_and_checkout_default(monkeypatch, tmp_path):
    # 缺省钉 checkout 树 <backend>/data/eval(不随 DATA_DIR 派生:
    # 写侧 _eval.__main__.report_dir ADR 0021 冻结,读写缺省必须同址)
    monkeypatch.delenv("IP_RADAR_EVAL_DIR", raising=False)
    assert _paths.eval_dir() == _APP_DIR / "data" / "eval"
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    assert _paths.eval_dir() == tmp_path


def test_honyport_dir_derives_from_data_dir(monkeypatch, tmp_path):
    # 原字面量 /app/data/honyport-aggregate 清除;从 data_dir 派生
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("IP_RADAR_HONYPORT_AGGREGATE_DIR", raising=False)
    assert _paths.honyport_aggregate_dir() == tmp_path / "honyport-aggregate"
    monkeypatch.setenv("IP_RADAR_HONYPORT_AGGREGATE_DIR", str(tmp_path / "agg"))
    assert _paths.honyport_aggregate_dir() == tmp_path / "agg"


def test_eval_heartbeat_path(monkeypatch, tmp_path):
    monkeypatch.delenv("IP_RADAR_EVAL_HEARTBEAT", raising=False)
    assert _paths.eval_heartbeat_path() is None
    monkeypatch.setenv("IP_RADAR_EVAL_HEARTBEAT", "")
    assert _paths.eval_heartbeat_path() is None
    monkeypatch.setenv("IP_RADAR_EVAL_HEARTBEAT", str(tmp_path / "hb"))
    assert _paths.eval_heartbeat_path() == tmp_path / "hb"


def test_static_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("IP_RADAR_STATIC_DIR", raising=False)
    assert _paths.static_dir() is None
    monkeypatch.setenv("IP_RADAR_STATIC_DIR", "")
    assert _paths.static_dir() is None
    monkeypatch.setenv("IP_RADAR_STATIC_DIR", str(tmp_path))
    assert _paths.static_dir() == tmp_path


def test_build_version_file_default_literal(monkeypatch):
    # 缺省字面量原样保留(容器烤进镜像;checkout 恒 miss)
    monkeypatch.delenv("IP_RADAR_BUILD_VERSION_FILE", raising=False)
    assert _paths.build_version_file() == Path("/app/BUILD_VERSION")
    monkeypatch.setenv("IP_RADAR_BUILD_VERSION_FILE", "/x/BUILD_VERSION")
    assert _paths.build_version_file() == Path("/x/BUILD_VERSION")


# ── 一致性对拍:同一 env 状态下全部路径消费者同源(两档)─────────────

_PATH_ENVS = (
    "IP_RADAR_DATA_DIR", "SOURCE_STATE_PATH", "IP_RADAR_STATE_FILE",
    "IP_RADAR_EVAL_DIR", "IP_RADAR_HONYPORT_AGGREGATE_DIR",
    "IP_RADAR_AUTH_DB", "IP_RADAR_ALERTS_DB", "IP_RADAR_EVAL_HEARTBEAT",
    "IP_RADAR_STATIC_DIR",
)


@pytest.mark.parametrize("mode", ["env_set", "env_unset"])
def test_all_path_consumers_share_one_root(mode, monkeypatch, tmp_path):
    for var in _PATH_ENVS:
        monkeypatch.delenv(var, raising=False)
    if mode == "env_set":
        monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "eval"))
    root = _paths.data_dir()

    # data_dir 派生族:state/ops/honyport 全部落同一根下
    assert _paths.source_state_path().parent == root
    assert _paths.update_state_path().parent == root
    from ipdb import _ops_store
    assert _ops_store.ops_root() == root / "ops"
    assert _paths.honyport_aggregate_dir() == root / "honyport-aggregate"
    # eval 目录:unset 档 = <backend>/data/eval(恰为 root/eval);set 档 =
    # 显式 env。两档都与读侧 _eval_reader 同源。
    assert _paths.eval_dir() == root / "eval"
    from ipdb import _eval_reader
    assert _eval_reader._dir() == _paths.eval_dir()
    # 兄弟 db 族(auth.db/alerts.db)落 source_state 同目录
    state_parent = _paths.source_state_path().parent
    assert _paths.env_path_or_state_sibling(
        "IP_RADAR_AUTH_DB", "auth.db").parent == state_parent
    assert _paths.env_path_or_state_sibling(
        "IP_RADAR_ALERTS_DB", "alerts.db").parent == state_parent


# ── P2(评审补钉):观察 _update 默认档真实写点 ──────────────────────
# 一致性对拍只锁 _paths 家族视图;若 _update 局部回潮 /app/data 字面量
# (绕过 _paths),对拍照样绿——本测试经 _paths 缝把写点指到 tmp 标记,
# 字面量回潮时标记不出现即红(评审 #406 P2)。
def test_update_state_write_goes_through_paths_seam(monkeypatch, tmp_path):
    for var in _PATH_ENVS:
        monkeypatch.delenv(var, raising=False)
    marker = tmp_path / "probe" / "update_state.json"
    monkeypatch.setattr(_paths, "update_state_path", lambda: marker)

    from ipdb import _update
    _update.mark_failed("probe")

    import json
    assert marker.exists(), "_update 写点绕过了 _paths 缝(字面量回潮?)"
    payload = json.loads(marker.read_text())
    assert payload["state"] == "failed"
    assert payload["error"] == "probe"
