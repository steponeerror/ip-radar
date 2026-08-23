from ipdb._sources._lmdb import encode_value, decode_value, _end_int

def test_codec_roundtrip_ascii():
    ev = {"country_code": "CN", "asn": 4134, "as_name": "Chinanet"}
    raw = encode_value(134744075, ev)
    end, out = decode_value(raw)
    assert end == 134744075 and out == ev

def test_codec_roundtrip_non_ascii():
    ev = {"comment": "恶意主机", "tags": ["botnet", "僵尸"]}
    raw = encode_value(42, ev)
    end, out = decode_value(raw)
    assert out == ev
    # orjson 不转义非 ASCII:字节里直接出现 UTF-8 中文
    assert "恶意主机".encode() in raw

def test_codec_stdlib_written_value_still_decodes():
    import json
    old = json.dumps([99, {"city": "北京"}], separators=(",", ":")).encode()
    end, out = decode_value(old)          # 历史 epoch 的 value 仍可解码
    assert end == 99 and out == {"city": "北京"}

def test_end_int_prefix_parses_orjson_bytes():
    assert _end_int(encode_value(134744075, {"x": 1})) == 134744075


def test_encode_value_v6_end_string_roundtrip():
    """>64-bit 端点以字符串落盘(orjson 拒绝超限整数);三层读路径兼容。"""
    import orjson
    end = 0x20010db8ffffffffffffffffffffffff
    raw = encode_value(end, {"k": 1})
    assert _end_int(raw) == end
    d, ev = decode_value(raw)
    assert d == end and ev == {"k": 1}
    # v4 数值形式字节不变(位元一致)
    assert encode_value(134744075, {}) == orjson.dumps([134744075, {}])


def test_ip_to_int6_roundtrip():
    from ipdb._sources._lmdb import ip_to_int6
    assert ip_to_int6("::") == 0
    assert ip_to_int6("2001:db8::1") == 0x20010db8000000000000000000000001

def test_ip_to_int6_invalid_raises():
    import pytest
    from ipdb._sources._lmdb import ip_to_int6
    with pytest.raises(ValueError):
        ip_to_int6("8.8.8.8")          # v4 串必须拒绝,防族混用

def test_encode_key6_width():
    from ipdb._sources._lmdb import encode_key6
    assert len(encode_key6(1)) == 16
    assert encode_key6(0x20010db8000000000000000000000000) == bytes.fromhex(
        "20010db8000000000000000000000000")

def test_rebuild_lmdb_v6_roundtrip(tmp_path):
    import lmdb
    from ipdb._sources._lmdb import rebuild_lmdb, lookup, ip_to_int6
    envs = []
    n = rebuild_lmdb(
        [("2001:db8::/32", [{"classification_type": "scanner"}]),
         ("2001:db9::/48", [{"classification_type": "scanner"}])],
        tmp_path / "t.v6.lmdb", envs.append, ip_version=6)
    assert n == 2
    env = envs[0]
    # 段内命中
    assert lookup(env, ip_to_int6("2001:db8::1234"), disjoint=True) is not None
    # 非精确起点命中(回退 prev)
    assert lookup(env, ip_to_int6("2001:db8::ffff"), disjoint=False) is not None
    # miss
    assert lookup(env, ip_to_int6("2600::1"), disjoint=True) is None
    env.close()

def test_rebuild_lmdb_v6_empty_writes_ptr(tmp_path):
    from ipdb._sources._lmdb import rebuild_lmdb, read_ptr
    envs = []
    n = rebuild_lmdb([], tmp_path / "e.v6.lmdb", envs.append, ip_version=6)
    assert n == 0
    assert read_ptr(tmp_path / "e.v6.lmdb") is not None   # Q3 不变量:空也写 ptr
    envs[0].close()

def test_rebuild_lmdb_v4_rejects_v6_cidr_unchanged(tmp_path):
    """v4 路径对 v6 CIDR 的静默跳过是既有行为,本任务不改。"""
    from ipdb._sources._lmdb import rebuild_lmdb
    envs = []
    n = rebuild_lmdb([("2001:db8::/32", [{}]), ("10.0.0.0/24", [{}])],
                     tmp_path / "t.lmdb", envs.append)
    assert n == 1
    envs[0].close()
