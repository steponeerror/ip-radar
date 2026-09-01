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
    assert lookup(env, ip_to_int6("2001:db8::1234"), disjoint=True, ip_version=6) is not None
    # 非精确起点命中(回退 prev)
    assert lookup(env, ip_to_int6("2001:db8::ffff"), disjoint=False, ip_version=6) is not None
    # miss
    assert lookup(env, ip_to_int6("2600::1"), disjoint=True, ip_version=6) is None
    env.close()

def test_lookup_small_v6_int_dispatch(tmp_path):
    """F1 回归:小 v6 整数(::,::1,::2)不得走 4 字节 key(曾致假命中/假漏)。"""
    from ipdb._sources._lmdb import rebuild_lmdb, lookup, ip_to_int6
    envs = []
    rebuild_lmdb([("::/128", [{"classification_type": "bogon"}]),
                  ("::5/128", [{"classification_type": "scanner"}])],
                 tmp_path / "f.v6.lmdb", envs.append, ip_version=6)
    env = envs[0]
    assert lookup(env, ip_to_int6("::2"), disjoint=True, ip_version=6) is None
    assert lookup(env, ip_to_int6("::2"), disjoint=False, ip_version=6) is None
    assert lookup(env, ip_to_int6("::"), disjoint=True, ip_version=6) is not None
    env.close()

def test_rebuild_lmdb_v4_rejects_bad_ip_version(tmp_path):
    """F3:rebuild_lmdb 拒绝未知 ip_version(不静默建 v4 env)。"""
    import pytest
    from ipdb._sources._lmdb import rebuild_lmdb
    with pytest.raises(ValueError):
        rebuild_lmdb([], tmp_path / "bad.lmdb", lambda e: None, ip_version=5)

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

def test_rebuild_dual_family_list_form(tmp_path):
    from ipdb._sources._lmdb import rebuild_dual_family, lookup, ip_to_int
    envs = []
    n4, n6 = rebuild_dual_family(
        [("10.0.0.0/24", [{"v": 4}]), ("2001:db8::/32", [{"v": 6}])],
        tmp_path / "a.lmdb", tmp_path / "a.v6.lmdb",
        reader_setter4=envs.append, reader_setter6=envs.append,
        covered4=256, covered6=1)
    assert (n4, n6) == (1, 1)
    v4env, v6env = envs
    assert lookup(v4env, ip_to_int("10.0.0.5")) is not None
    v4env.close(); v6env.close()
    # v6 侧在 v6env 里(换个方式验:count sidecar)
    assert (tmp_path / "a.v6.lmdb.count").read_text() == "1"
    assert (tmp_path / "a.v6.lmdb.cov").read_text() == "1"

def test_rebuild_dual_family_factory_form_streams(tmp_path):
    """callable 形式:两次独立遍历,不物化(流式源用)。"""
    from ipdb._sources._lmdb import rebuild_dual_family
    envs = []
    made = []
    def factory():
        made.append(1)
        return iter([("192.0.2.0/24", [{}]), ("2001:db8::/64", [{}])])
    n4, n6 = rebuild_dual_family(
        factory, tmp_path / "b.lmdb", tmp_path / "b.v6.lmdb",
        reader_setter4=envs.append, reader_setter6=envs.append)
    assert (n4, n6) == (1, 1)
    assert len(made) == 2          # 调了两次,各自过滤
    for e in envs: e.close()

def test_rebuild_dual_family_progress_covers_v6(tmp_path):
    """progress 跨 v4+v6 两 pass 单调递增:received 终值 == n4+n6,
    不允许 v6 pass 从 0 重新计数(倒退会让 UI 行数回跳)。"""
    from ipdb._sources._lmdb import rebuild_dual_family
    envs = []
    events = []
    n4, n6 = rebuild_dual_family(
        [("10.0.0.0/24", [{}]), ("2001:db8::/32", [{}])],
        tmp_path / "p.lmdb", tmp_path / "p.v6.lmdb",
        reader_setter4=envs.append, reader_setter6=envs.append,
        progress=lambda done, total: events.append((done, total)))
    assert (n4, n6) == (1, 1)
    received = [d for d, _ in events]
    assert received == sorted(received), f"progress 倒退: {events}"
    totals = [tt for _, tt in events]
    assert totals == sorted(totals), f"total 倒退: {events}"
    assert events[-1] == (2, 2)  # 列表形态 len 已知:终值 (n4+n6, n4+n6)
    for e in envs: e.close()

def test_rebuild_dual_family_auto_covered_both_families(tmp_path):
    """covered4/6=Auto: 双族 sidecar 循环内统计,setter 各自回调正确值。"""
    from ipdb._sources._lmdb import rebuild_dual_family, Auto
    envs = []
    got4, got6 = [], []
    n4, n6 = rebuild_dual_family(
        [("10.0.0.0/24", [{}]), ("1.2.3.4", [{}]),
         ("2001:db8::/32", [{}]), ("2a00::/32", [{}])],
        tmp_path / "d.lmdb", tmp_path / "d.v6.lmdb",
        reader_setter4=envs.append, reader_setter6=envs.append,
        covered4=Auto, covered6=Auto,
        covered_setter4=got4.append, covered_setter6=got6.append)
    assert (n4, n6) == (2, 2)
    assert got4 == [257] and got6 == [2]
    assert (tmp_path / "d.lmdb.cov").read_text() == "257"
    assert (tmp_path / "d.v6.lmdb.cov").read_text() == "2"
    for e in envs: e.close()

def test_rebuild_dual_family_empty_v6_writes_ptr(tmp_path):
    from ipdb._sources._lmdb import rebuild_dual_family, read_ptr
    envs = []
    n4, n6 = rebuild_dual_family(
        [("10.0.0.0/24", [{}])],
        tmp_path / "c.lmdb", tmp_path / "c.v6.lmdb",
        reader_setter4=envs.append, reader_setter6=envs.append)
    assert (n4, n6) == (1, 0)
    assert read_ptr(tmp_path / "c.v6.lmdb") is not None   # Q3 不变量
    for e in envs: e.close()


def test_dual_family_streaming_v6_progress_uses_total_est(tmp_path):
    """流式 factory(无 __len__)+ total_est:v6 pass 的进度事件必须携带
    换算后的 total。断言 mid-flush 分数:终值事件经 max(total, n) 自适应
    会空洞通过,故只认 BATCH_SIZE 边界前的未完成分数(修复前 v6 段
    total 恒 0,事件形如 (d, 0),分数恒满)。"""
    from ipdb._sources._lmdb import BATCH_SIZE, rebuild_dual_family

    events = []

    def records():
        yield ("1.2.3.4/32", [{}])
        yield ("1.2.3.5/32", [{}])
        for i in range(BATCH_SIZE + 1):          # 触发一次 mid-flush + 终值
            # 双 hextet 展开任一 i(BATCH_SIZE≥0x10000 时单 hextet 会溢出 4 hex 位)
            yield (f"2001:db8:{i >> 16:x}:{i & 0xffff:x}::/48", [{}])

    n4, n6 = rebuild_dual_family(
        records, tmp_path / "v4.lmdb", tmp_path / "v6.lmdb",
        reader_setter4=lambda e: None, reader_setter6=lambda e: None,
        progress=lambda done, total: events.append((done, total)),
        total_est=BATCH_SIZE + 3)
    assert (n4, n6) == (2, BATCH_SIZE + 1)
    # v6 阶段(d 已越过 v4 计数)必须出现未完成分数:received < total
    assert any(d < t for d, t in events if d > 2)


def test_rebuild_lmdb_zero_records_with_history_raises_keeps_ptr(tmp_path):
    """空记录 + 历史 count>0 → raise,ptr/sidecars 不动(旧 epoch 保留,
    任务显式失败;防 feed 改格式后空 rebuild 清库)。"""
    import pytest
    from ipdb._sources._lmdb import rebuild_lmdb, count_path, ptr_path

    base = tmp_path / "guard.lmdb"
    # 预置历史:一次正常 rebuild 建库 + count sidecar
    rebuild_lmdb([("10.0.0.0/24", [{}])], base, lambda e: None)
    old_ptr = ptr_path(base).read_text().strip()
    assert count_path(base).read_text().strip() == "1"

    with pytest.raises(RuntimeError):
        rebuild_lmdb([], base, lambda e: None)
    # 提交未发生:ptr 仍指向旧 epoch,count sidecar 未被改写
    assert ptr_path(base).read_text().strip() == old_ptr
    assert count_path(base).read_text().strip() == "1"


def test_rebuild_lmdb_zero_records_first_build_succeeds(tmp_path):
    """首建(无 count sidecar)零记录仍成功 — 全新源空 feed 不是错误。"""
    from ipdb._sources._lmdb import rebuild_lmdb, read_ptr
    n = rebuild_lmdb([], tmp_path / "fresh.lmdb", lambda e: None)
    assert n == 0
    assert read_ptr(tmp_path / "fresh.lmdb") is not None
