from ipdb import _batch_pool
import pytest


@pytest.fixture(autouse=True)
def _clear_lru_cache():
    """每个测试前后都清空模块级 LRU,避免跨测试/跨文件污染(Stub 结果泄漏)。
    Task 4:指纹 TTL 缓存同治(同窗内缓存会把上一测试的指纹带给
    monkeypatch 后的假源面)。"""
    _batch_pool._cached_lookup.cache_clear()
    _batch_pool._fp_cache["entry"] = None
    yield
    cached = getattr(_batch_pool, "_cached_lookup", None)
    # pytest ≥9 终结顺序:本 teardown 可能先于 monkeypatch 恢复执行,此刻
    # _cached_lookup 还是测试的普通 spy(无 cache_clear)——跳过本次后置清;
    # 残留由同文件下个用例的前置清兜底(CI per-file 分进程,无跨文件窗口)。
    if cached is not None and hasattr(cached, "cache_clear"):
        cached.cache_clear()
    _batch_pool._fp_cache["entry"] = None

def test_dedup_lookup_preserves_order_and_length(monkeypatch):
    import ipdb._registry as reg
    seen = []
    class Stub:
        def __init__(self, ip): self.ip = ip
        def to_dict(self): return {"ip": self.ip}
    def fake(ip, allowed_sources=None):
        seen.append(ip)
        return Stub(ip)
    monkeypatch.setattr(reg, "lookup", fake)
    ips = ["1.1.1.1", "8.8.8.8", "1.1.1.1", "9.9.9.9", "8.8.8.8", "1.1.1.1"]
    out = _batch_pool._dedup_lookup(ips)
    assert [d["ip"] for d in out] == ips          # 输入序回填
    assert len(out) == len(ips)
    assert seen == ["1.1.1.1", "8.8.8.8", "9.9.9.9"]   # 每唯一 IP 只算一次,首次出现序

def test_work_chunk_uses_dedup(monkeypatch):
    import ipdb._registry as reg
    seen = []
    class Stub:
        def __init__(self, ip): self.ip = ip
        def to_dict(self): return {"ip": self.ip}
    monkeypatch.setattr(reg, "lookup", lambda ip, allowed_sources=None: (seen.append(ip), Stub(ip))[1])
    ips = ["1.1.1.1"] * 200 + ["8.8.8.8"]
    out = _batch_pool._work_chunk(ips)
    assert len(out) == 201
    assert seen == ["1.1.1.1", "8.8.8.8"]         # 每唯一 IP 只算一次

def test_dedup_lookup_repeated_ip_cached(monkeypatch):
    """跨片/重复 IP 经 _dedup_lookup 时,第二次调用命中 LRU 不重复计算。

    验证: 同 ip + 同 epoch_fp 第二次调用不再触发 _registry.lookup。
    (与同文件其它测试一致:monkeypatch lookup 桩,不依赖真实已建 LMDB 数据)
    """
    import ipdb._batch_pool as bp
    import ipdb._registry as reg
    seen = []
    class Stub:
        def __init__(self, ip): self.ip = ip
        def to_dict(self): return {"ip": self.ip}
    monkeypatch.setattr(reg, "lookup", lambda ip, allowed_sources=None: (seen.append(ip), Stub(ip))[1])

    fp = bp._epoch_fingerprint()
    a = bp._dedup_lookup(["8.8.8.8", "8.8.8.8", "1.1.1.1"])
    n_after_first = len(seen)
    # 第二次同 ip 同 fp: LRU 命中, lookup 不再触发
    b = bp._dedup_lookup(["8.8.8.8"])
    assert len(seen) == n_after_first
    assert len(a) == 3 and len(b) == 1
    assert b[0]["ip"] == "8.8.8.8"

def test_epoch_fingerprint_includes_source_names(monkeypatch):
    """指纹键带源名(位置元组碰撞回归): 全新安装所有源 ptr=1 时,
    切换启用源集合后旧指纹(纯 ptr 元组)字节相同 → LRU 返回错误证据组合。
    (Task 4 TTL 后两次取样须越 5s 窗——同窗内命中缓存属预期语义)
    """
    import ipdb._batch_pool as bp
    import ipdb._registry as reg
    import ipdb._sources._lmdb as lmdb_mod

    class FakeSrc:
        def __init__(self, name):
            self.name = name
            self._lmdb_base = f"/fake/{name}.lmdb"

    monkeypatch.setattr(lmdb_mod, "read_ptr", lambda base: 1)  # 全新安装 ptr 恒 1
    clock = {"t": 1_000_200.0}  # 桶对齐,两次取样均在同 300s 桶内
    monkeypatch.setattr(bp.time, "time", lambda: clock["t"])
    monkeypatch.setattr(reg, "_enabled_sources",
                        lambda: [FakeSrc("src_x"), FakeSrc("src_y")])
    fp_a = bp._epoch_fingerprint()
    clock["t"] += 6                             # 越 TTL 窗,强制重算
    monkeypatch.setattr(reg, "_enabled_sources",
                        lambda: [FakeSrc("src_x"), FakeSrc("src_z")])
    fp_b = bp._epoch_fingerprint()
    assert fp_a != fp_b

def test_dedup_lookup_pool_worker_bypasses_lru(monkeypatch):
    """池 worker(_IN_POOL_WORKER=True)直查不走 LRU。"""
    import ipdb._batch_pool as bp
    import ipdb._registry as reg
    calls = []
    class Stub:
        def __init__(self, ip): self.ip = ip
        def to_dict(self): return {"ip": self.ip}
    monkeypatch.setattr(reg, "lookup", lambda ip, allowed_sources=None: (calls.append(ip), Stub(ip))[1])
    hits = {"n": 0}
    orig = bp._cached_lookup
    def spy(ip, fp, allowed=None):
        hits["n"] += 1
        return orig.__wrapped__(ip, fp, allowed)
    monkeypatch.setattr(bp, "_cached_lookup", spy)
    monkeypatch.setattr(bp, "_IN_POOL_WORKER", True)
    # 密封(Task 2 换代检查带入的真库依赖):固定指纹 + 同值预锚定 →
    # fp==锚 不触发真实 load_db/read_ptr;monkeypatch 终结时还原原值,
    # 生产代码直写的 _POOL_EPOCH_FP 模块残留也一并回收。
    monkeypatch.setattr(bp, "_epoch_fingerprint", lambda: ("t",))
    monkeypatch.setattr(bp, "_POOL_EPOCH_FP", ("t",))
    bp._dedup_lookup(["8.8.8.8", "8.8.8.8"])
    assert hits["n"] == 0 and len(calls) == 1   # 直查+片内去重, 无 LRU
    monkeypatch.setattr(bp, "_IN_POOL_WORKER", False)
    bp._dedup_lookup(["8.8.8.8"])
    assert hits["n"] >= 1   # 主进程走 LRU


def test_epoch_fingerprint_time_bucket(monkeypatch):
    """跨 5 分钟桶指纹不同; 同桶相同。

    基准取 300 的整数倍(桶对齐): +299 仍在同桶, +305 跨入下一桶。
    (1_000_000 非桶对齐——距桶界仅 200s, +299 即跨桶, 断言会假失败)
    (Task 4 TTL:跨桶样本还须越上一取样的 5s 窗,否则命中缓存不重算)
    """
    import ipdb._batch_pool as bp
    T0 = 999_900.0  # = 3333 * 300, 桶对齐
    monkeypatch.setattr(bp.time, "time", lambda: T0)
    a = bp._epoch_fingerprint()
    monkeypatch.setattr(bp.time, "time", lambda: T0 + 299)
    b = bp._epoch_fingerprint()
    monkeypatch.setattr(bp.time, "time", lambda: T0 + 305)
    c = bp._epoch_fingerprint()
    assert a == b and a != c


def test_epoch_fingerprint_ttl_cache(monkeypatch):
    """Task 4(grill 候选3):指纹 5s TTL 缓存——同窗内不重读 read_ptr
    (每 inline 批对每启用源的系统调用串实测 1,164µs/次),换代检测
    延迟 ≤5s 最终一致(300s 桶整桶冻结,语义同向);越窗重算见新代。
    """
    import ipdb._batch_pool as bp
    import ipdb._registry as reg
    import ipdb._sources._lmdb as lmdb_mod

    reads = {"n": 0}
    ptr = {"v": 1}

    class FakeSrc:
        name = "src_x"
        _lmdb_base = "/fake/src_x.lmdb"

    def fake_read_ptr(base):
        reads["n"] += 1
        return ptr["v"]

    monkeypatch.setattr(lmdb_mod, "read_ptr", fake_read_ptr)
    monkeypatch.setattr(reg, "_enabled_sources", lambda: [FakeSrc()])
    clock = {"t": 1_000_200.0}  # 桶对齐(300 的倍数),越窗仍在同桶
    monkeypatch.setattr(bp.time, "time", lambda: clock["t"])

    a = bp._epoch_fingerprint()
    assert reads["n"] == 1
    ptr["v"] = 2                            # 模拟后台 rebuild 换 epoch
    b = bp._epoch_fingerprint()             # 同 TTL 窗内:命中缓存不重读
    assert b == a and reads["n"] == 1       # 旧实现此处重读(reads==2)即红
    clock["t"] += 5.1                       # 越 5s 窗(仍在同 300s 桶)
    c = bp._epoch_fingerprint()
    assert reads["n"] == 2 and c != a       # 重算,见新代
