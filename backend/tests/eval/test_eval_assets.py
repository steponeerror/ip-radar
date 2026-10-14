# backend/tests/eval/test_eval_assets.py
import pytest

from ipdb._eval.assets import (
    NO_LAYER,
    AssetMeta,
    fingerprint,
    load_asset,
    save_asset,
)


def test_fingerprint_stable_and_order_insensitive():
    assert fingerprint(["1.1.1.1", "2.2.2.2"]) == fingerprint(["2.2.2.2", "1.1.1.1"])


def test_save_load_roundtrip(tmp_path):
    meta = AssetMeta(version="v1", kind="truth", fingerprint=fingerprint(["1.1.1.1"]),
                     member_count=1, params={}, eval_env="monthly", created_at="2026-10-14")
    save_asset(tmp_path, ["1.1.1.1"], meta)
    members, loaded = load_asset(tmp_path)
    assert members == ["1.1.1.1"] and loaded.fingerprint == fingerprint(members)


def test_load_rejects_fingerprint_mismatch(tmp_path):  # 篡改 ips.txt → ValueError
    meta = AssetMeta(version="v1", kind="truth", fingerprint=fingerprint(["1.1.1.1"]),
                     member_count=1, params={}, eval_env="monthly", created_at="2026-10-14")
    save_asset(tmp_path, ["1.1.1.1"], meta)
    (tmp_path / "ips.txt").write_text("1.1.1.1\n9.9.9.9")  # 资产被篡改:证据必须炸出来,不许静默
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_asset(tmp_path)


def test_no_layer_sentinel_singleton():  # repr 含 "NO-LAYER";两次引用同身份
    import ipdb._eval.assets as assets
    assert "NO-LAYER" in repr(NO_LAYER)
    assert assets.NO_LAYER is NO_LAYER
