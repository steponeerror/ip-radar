"""Payload interning write path: dedup, ref layout, compact, guards."""
import pytest
lmdb = pytest.importorskip("lmdb")

def test_rebuild_interns_duplicate_payloads(tmp_path):
    from ipdb._sources._lmdb import rebuild_lmdb, lookup, ip_to_int, PAYLOADS_NAME
    ev_a = {"classification_type": "scanner", "verdict": "malicious"}
    ev_b = {"classification_type": "proxy", "verdict": "suspicious"}
    recs = [(f"10.{i}.0.0/16", [ev_a]) for i in range(1, 200)] + \
           [(f"172.16.{i}.0/24", [ev_b]) for i in range(1, 50)]
    envs = []
    n = rebuild_lmdb(recs, tmp_path / "t.lmdb", envs.append)
    assert n == len(recs)
    env = envs[0]
    for i in (1, 42, 199):
        assert lookup(env, ip_to_int(f"10.{i}.0.5"), disjoint=True) == [ev_a]
    assert lookup(env, ip_to_int("172.16.5.5"), disjoint=True) == [ev_b]
    # 字典只有 2 个条目(去重生效),pidx 已 drop
    with env.begin() as txn:
        pay = env.open_db(PAYLOADS_NAME)
        assert txn.stat(db=pay)["entries"] == 2
        with pytest.raises(lmdb.NotFoundError):
            env.open_db(b"pidx", create=False)
    env.close()

# (尺寸缩减不在合成数据上断言:writemap 预分配使小 env 文件尺寸失真,
# 去重效果由上一测试的 entries==2 钉死,真实缩比由 Task 4 SC-1 实测)

def test_rebuild_mapfull_grows_with_interning(tmp_path):
    from ipdb._sources._lmdb import rebuild_lmdb, lookup, ip_to_int
    # 唯一 payload(每条不同)迫使 pidx+payloads 双写体积真实增长,
    # 256KB 初始 map 必然溢出 → 验证增长循环在字典化写路径下仍正确
    # (brief 原 fixture f"10.{i}.0.0/24" 对 i≥256 非法 IPv4,改双八位组展开)
    recs = [(f"10.{i // 256}.{i % 256}.0/24", [{"k": i, "pad": "y" * 200}])
            for i in range(1, 900)]
    envs = []
    n = rebuild_lmdb(recs, tmp_path / "g.lmdb", envs.append, map_size=1 << 18)
    assert n == 899
    assert lookup(envs[0], ip_to_int("10.1.244.1"), disjoint=True) \
        == [{"k": 500, "pad": "y" * 200}]   # 500 = 1*256+244 → 10.1.244.0/24
    envs[0].close()

def test_rebuild_zero_guard_cleans_staging_and_cmp(tmp_path):
    from ipdb._sources._lmdb import (rebuild_lmdb, read_ptr, count_path,
                                     cleanup_stale)
    base = tmp_path / "z.lmdb"
    envs = []
    stale_cmp = tmp_path / "z.lmdb.0.new.123.cmp"
    stale_cmp.mkdir()      # 崩溃残留 .cmp:成功 rebuild 的 prune 兜底(head<新 epoch)
    rebuild_lmdb([("10.0.0.0/24", [{"a": 1}])], base, envs.append)
    envs[0].close()
    assert not stale_cmp.exists()
    count_path(base).write_text("1")
    with pytest.raises(RuntimeError, match="zero records"):
        rebuild_lmdb([], base, envs.append)
    boot_cmp = tmp_path / "z.lmdb.1.new.999.cmp"
    boot_cmp.mkdir()       # 启动残留 .cmp:cleanup_stale 后缀匹配兜底
    cleanup_stale(base)
    assert not boot_cmp.exists()
    leftovers = [p.name for p in tmp_path.iterdir() if ".new." in p.name or ".cmp" in p.name]
    assert leftovers == []

def test_rebuild_empty_env_compact_writes_ptr(tmp_path):
    from ipdb._sources._lmdb import rebuild_lmdb, read_ptr
    envs = []
    n = rebuild_lmdb([], tmp_path / "e.lmdb", envs.append)
    assert n == 0
    assert read_ptr(tmp_path / "e.lmdb") is not None
    envs[0].close()

def test_rebuild_v6_interned_roundtrip(tmp_path):
    from ipdb._sources._lmdb import rebuild_lmdb, lookup, ip_to_int6
    ev = {"classification_type": "scanner"}
    envs = []
    rebuild_lmdb([("2001:db8::/32", [ev]), ("2001:db9::/48", [ev])],
                 tmp_path / "t.v6.lmdb", envs.append, ip_version=6)
    assert lookup(envs[0], ip_to_int6("2001:db8::1"), disjoint=True,
                  ip_version=6) == [ev]
    envs[0].close()

def test_interned_descriptor_key_does_not_poison_scans(tmp_path):
    """命名库描述符键(LMDB 把 sub-db 注册项落在主库键空间,键=b"payloads"、
    值=二进制描述符)不得毒化回扫/全序扫描:v6 env 描述符是末键,past-end
    miss 曾在 prev() 后 _end_int 直接崩;乱序插入触发 detect_disjoint 曾在
    描述符上崩(修复前本测试两处均 ValueError)。"""
    from ipdb._sources._lmdb import (rebuild_lmdb, lookup, ip_to_int6,
                                     read_ptr, read_disjoint_flag)
    envs = []
    rebuild_lmdb([("2a00::/32", [{"v": 1}]), ("2001:db8::/32", [{"v": 2}])],
                 tmp_path / "d.v6.lmdb", envs.append, ip_version=6)
    env = envs[0]
    assert lookup(env, ip_to_int6("8000::1"), disjoint=True,
                  ip_version=6) is None      # past-end miss:回扫跨过描述符
    assert lookup(env, ip_to_int6("2a00::1"), disjoint=True,
                  ip_version=6) == [{"v": 1}]  # 命中不经描述符
    env.close()
    base = tmp_path / "d.v6.lmdb"
    # 乱序插入(2a00 先于 2001)触发 detect_disjoint 全序扫描:描述符被跳过,
    # 判定结果为真不相交
    assert read_disjoint_flag(base, read_ptr(base)) is True
