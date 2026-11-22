"""#406 路径折并(第一红):同一 env 状态下全部路径消费者须同源。

现状:未设 env 时 _update.py:16 回落容器字面量 "/app/data",而
_registry 回落 <backend>/data —— update_state.json 在 dev 检出上落到
不可写路径。折并(_paths 单源)后本档与 env 设档一并扩成一致性对拍。"""
from pathlib import Path

from ipdb import _registry, _update


def test_env_unset_update_state_shares_registry_data_root(monkeypatch):
    monkeypatch.delenv("IP_RADAR_STATE_FILE", raising=False)
    monkeypatch.delenv("IP_RADAR_DATA_DIR", raising=False)
    assert Path(_update.STATE_PATH).parent == Path(_registry.DATA_DIR)
