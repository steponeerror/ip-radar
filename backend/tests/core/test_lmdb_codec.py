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


def _epoch_dirs(base):
    return sorted(p.name for p in base.parent.glob(f"{base.name}.*")
                  if p.is_dir() and p.name.rsplit(".", 1)[-1].isdigit())


def test_rebuild_dual_family_converged_family_skipped(tmp_path):
    """T1(2026-10-14 收敛批)族级增量:raw 已被 v4 ptr 覆盖 → v4 跳过
    (不建新纪元、不动 reader、计数取 count sidecar),v6 ptr 落后照建;
    两族均收敛 → 双跳(重试零成本)。"""
    import os
    from ipdb._sources._lmdb import rebuild_dual_family, read_ptr, ptr_path
    raw = tmp_path / "s.txt"
    raw.write_text("x")
    v4, v6 = tmp_path / "s.lmdb", tmp_path / "s.v6.lmdb"
    envs = []
    rebuild_dual_family(
        [("10.0.0.0/24", [{}]), ("2001:db8::/32", [{}])],
        v4, v6, reader_setter4=envs.append, reader_setter6=envs.append,
        raw=raw)
    e4, e6 = envs
    for e in envs: e.close()
    FUT, PAST = 2e9, 1e9   # 与真实时钟无关的确定性两档 mtime
    made = []

    def factory():
        made.append(1)     # 流式源形态:每次调用 = 一整遍 harvest
        return iter([("10.9.0.0/24", [{}]), ("2001:db9::/32", [{}])])

    # 场景 A:仅 v6 落后 —— v4 ptr 拨未来、v6 ptr 拨过去
    os.utime(ptr_path(v4), (FUT, FUT))
    os.utime(ptr_path(v6), (PAST, PAST))
    calls = []
    n4, n6 = rebuild_dual_family(
        factory, v4, v6,
        reader_setter4=lambda e: calls.append(("r4", e)),
        reader_setter6=lambda e: calls.append(("r6", e)),
        raw=raw)
    assert [c[0] for c in calls] == ["r6"]     # v4 reader 未动
    assert n4 == 1                             # 跳过族计数取 sidecar
    assert n6 == 1
    assert read_ptr(v4) == 1                   # v4 无新纪元
    assert read_ptr(v6) == 2                   # v6 重建到下一纪元
    assert _epoch_dirs(v4) == ["s.lmdb.1"]
    assert made == [1]                         # 跳过的族不白跑 harvest(PEP 289 延迟)
    for _, e in calls: e.close()


    # 场景 B:两族 ptr 均 ≥ raw → 双跳,零 reader 回调零新纪元零 harvest
    os.utime(ptr_path(v6), (FUT, FUT))
    calls = []
    made.clear()
    n4, n6 = rebuild_dual_family(
        factory, v4, v6,
        reader_setter4=lambda e: calls.append(("r4", e)),
        reader_setter6=lambda e: calls.append(("r6", e)),
        raw=raw)
    assert calls == []
    assert made == []
    assert (n4, n6) == (1, 1)
    assert read_ptr(v4) == 1 and read_ptr(v6) == 2

    # 场景 C:raw 新于两族 ptr(新下载落地)→ 两族均重建
    os.utime(raw, (FUT + 100, FUT + 100))
    calls = []
    made.clear()
    n4, n6 = rebuild_dual_family(
        factory, v4, v6,
        reader_setter4=lambda e: calls.append(("r4", e)),
        reader_setter6=lambda e: calls.append(("r6", e)),
        raw=raw)
    assert [c[0] for c in calls] == ["r4", "r6"]
    assert made == [1, 1]                      # 两族各跑一遭 harvest
    assert read_ptr(v4) == 2 and read_ptr(v6) == 3
    for _, e in calls: e.close()


def test_rev_sidecar_stamp_and_drift_rebuilds(tmp_path):
    """C2(ADR 0009,issue #192):rebuild 必给两族盖章 .rev=HARVEST_REV;
    戳匹配 + mtime 收敛 → 双跳(harvest 零调用);仅 v4 戳漂移(模拟
    harvest 代码演进,mtime 全程不动)→ 仅 v4 重建,v6 不白跑。"""
    import os
    from ipdb._sources._lmdb import (HARVEST_REV, rebuild_dual_family,
                                     read_ptr, ptr_path, rev_path)
    raw = tmp_path / "s.txt"
    raw.write_text("x")
    v4, v6 = tmp_path / "s.lmdb", tmp_path / "s.v6.lmdb"
    envs = []
    rebuild_dual_family(
        [("10.0.0.0/24", [{}]), ("2001:db8::/32", [{}])],
        v4, v6, reader_setter4=envs.append, reader_setter6=envs.append,
        raw=raw)
    for e in envs: e.close()
    assert rev_path(v4).read_text().strip() == str(HARVEST_REV)   # 两族均盖章
    assert rev_path(v6).read_text().strip() == str(HARVEST_REV)
    FUT = 2e9
    os.utime(ptr_path(v4), (FUT, FUT))       # mtime 收敛,后续场景不再动 mtime
    os.utime(ptr_path(v6), (FUT, FUT))

    made = []

    def factory():
        made.append(1)
        return iter([("10.9.0.0/24", [{}]), ("2001:db9::/32", [{}])])

    calls = []
    rebuild_dual_family(factory, v4, v6,
                        reader_setter4=lambda e: calls.append(("r4", e)),
                        reader_setter6=lambda e: calls.append(("r6", e)),
                        raw=raw)
    assert made == [] and calls == []         # 双收敛:双跳,零 harvest

    rev_path(v4).write_text(str(HARVEST_REV - 1))   # 仅 v4 代码代漂移
    rebuild_dual_family(factory, v4, v6,
                        reader_setter4=lambda e: calls.append(("r4", e)),
                        reader_setter6=lambda e: calls.append(("r6", e)),
                        raw=raw)
    assert made == [1]                        # 只跑了 v4 的 harvest
    assert [c[0] for c in calls] == ["r4"]    # 只有 v4 reader 换代
    assert read_ptr(v4) == 2 and read_ptr(v6) == 1
    for _, e in calls: e.close()


def test_rebuild_dual_family_v4_only_feed_zeroes_v6_phantom(tmp_path):
    """T4(2026-10-14 收敛批)sfs v6 幻影:历史 v6 count=1 的库遇到 v4-only
    feed → n4>0(主族健康)时空 v6 重建允许提交,count 归 0;修复前此处被
    零记录守卫拒("zero records parsed but previous count was 1")。
    v4 主族零记录仍拒由既有 test_rebuild_lmdb_zero_records_with_history_
    raises_keeps_ptr 钉住(allow_empty 默认 False)。"""
    from ipdb._sources._lmdb import (rebuild_dual_family, rebuild_lmdb,
                                     read_ptr, count_path)
    v4, v6 = tmp_path / "f.lmdb", tmp_path / "f.v6.lmdb"
    rebuild_lmdb([("2001:db8::/32", [{}])], v6, lambda e: None, ip_version=6)
    assert count_path(v6).read_text() == "1"      # 幻影:历史 v6 count=1
    envs = []
    n4, n6 = rebuild_dual_family(
        [("10.0.0.0/24", [{}])],                   # v4-only feed
        v4, v6, reader_setter4=envs.append, reader_setter6=envs.append)
    assert (n4, n6) == (1, 0)
    assert count_path(v6).read_text() == "0"      # 幻影归零
    assert read_ptr(v6) is not None               # ptr 前进,空 env 服役
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
    # DQ-2:返回值 = 提交库键数,非流式行数。本 fixture 的 v6 记录全部
    # 被 /48 掩码归一(i&0xffff 落在 host 位)坍缩为 2 个网段
    # (2001:db8::/48 + 2001:db8:1::/48)——旧行数口径 100001 是虚高计数。
    assert (n4, n6) == (2, 2)
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


def test_encode_value_ref_layout_matches_end_int():
    from ipdb._sources._lmdb import encode_value_ref, _end_int, decode_value
    import orjson
    raw = encode_value_ref(134744075, 422800)
    assert _end_int(raw) == 134744075          # 回扫快路径不破
    assert raw == orjson.dumps([134744075, 422800])   # 与 orjson 字节一致
    d, ev = decode_value(raw)
    assert d == 134744075 and ev == 422800

def test_encode_value_ref_v6_end_string():
    from ipdb._sources._lmdb import encode_value_ref, _end_int
    end = 0x20010db8ffffffffffffffffffffffff
    assert _end_int(encode_value_ref(end, 7)) == end

def test_lookup_resolves_interned_ref_and_passes_inline(tmp_path):
    import lmdb, orjson
    from ipdb._sources._lmdb import (lookup, encode_value, encode_value_ref,
                                     ip_to_int, PAYLOADS_NAME, resolve_evidence)
    env = lmdb.open(str(tmp_path / "m"), map_size=1 << 22, subdir=True,
                    max_dbs=1)
    pay = env.open_db(PAYLOADS_NAME)
    inline_ev = {"city": "Oldtown"}
    payload = orjson.dumps({"city": "Newtown"})
    with env.begin(write=True) as txn:
        txn.put(ip_to_int("1.0.0.0").to_bytes(4, "big"),
                encode_value(ip_to_int("1.0.0.255"), inline_ev))
        txn.put(ip_to_int("2.0.0.0").to_bytes(4, "big"),
                encode_value_ref(ip_to_int("2.0.0.255"), 7))
        txn.put((7).to_bytes(8, "big"), payload, db=pay)
    # 混合 env:同一次 lookup 双路——inline 透传、int 解引用
    assert lookup(env, ip_to_int("1.0.0.5"), disjoint=True) == {"city": "Oldtown"}
    assert lookup(env, ip_to_int("2.0.0.5"), disjoint=True) == {"city": "Newtown"}
    # 腐败防御:int 值但字典缺失 → resolve_evidence 必须炸响,不得静默返 int
    import pytest
    with env.begin() as txn:
        with pytest.raises(ValueError):
            resolve_evidence(txn, 999, pay)   # 字典无 999 号
    env.close()

def test_payloads_db_none_on_missing_loud_on_dbsfull(tmp_path):
    import lmdb, pytest
    from ipdb._sources._lmdb import _payloads_db
    slotted = lmdb.open(str(tmp_path / "p"), map_size=1 << 20, subdir=True,
                        max_dbs=1)
    slotted.close()
    ro = lmdb.open(str(tmp_path / "p"), map_size=1 << 20, subdir=True,
                   max_dbs=1, readonly=True, lock=False)
    assert _payloads_db(ro) is None            # 无 payloads db 且有槽位 → None(旧 epoch 形态)
    ro.close()
    # 槽位不足(max_dbs=0)→ DbsFullError 必须向外炸(Review Focus #1:
    # 静默吞 = int 泄漏成证据)。py-lmdb 对 create=False 缺槽位先报 DbsFull
    tight = lmdb.open(str(tmp_path / "t"), map_size=1 << 20, subdir=True,
                      max_dbs=0)
    tight.close()
    ro0 = lmdb.open(str(tmp_path / "t"), map_size=1 << 20, subdir=True,
                    readonly=True, lock=False)
    with pytest.raises(lmdb.Error):
        _payloads_db(ro0)
    ro0.close()
