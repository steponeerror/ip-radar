"""Regression: a pre-ready False probe must not freeze _db_loaded() into False
once sources hot-swap readers (cold-start gate brick); and the True fast-path
cache must not be fooled by object address reuse (PR-2 #111 终审 P2-3)."""
from types import SimpleNamespace
from ipdb import _registry as r


def test_db_loaded_recomputes_true_after_false_probe_is_not_frozen(monkeypatch):
    class FakeSource:
        name = "fake_probe"          # is_enabled 按名比对,需有 name

        def __init__(self):
            self.loaded = False
        def health(self):
            return SimpleNamespace(loaded=self.loaded)

    src = FakeSource()
    monkeypatch.setattr(r, "_enabled_sources", lambda: [src])
    assert r._db_loaded() is False          # pre-ready probe caches nothing
    src.loaded = True                        # rebuild hot-swaps reader in place
    assert r._db_loaded() is True            # must NOT return frozen False


def test_db_loaded_not_fooled_by_address_reuse(monkeypatch):
    """PR-2 #111 终审 P2-3 挂账:id() 键控下,旧 _sources 被替换回收后新
    list 可同址分配(消融 toggle / set_source_enabled 热替换即此现场),纯
    id 相等误中 stale True → warming_up 误报/放行未载源。修法=缓存持强引用
    以 is 比对:被缓存引用的对象不可能被回收,地址复用无从发生,对象一经
    替换即重算。构造:True 落缓存 → 释放旧 list → 同址再分配未载源 list
    → 必须重算出 False(强引用实现下同址不可能,退化为普通失效断言)。
    不用 monkeypatch 换 _sources:其 teardown 快照会持活待释放对象。"""
    class FakeSource:
        name = "fake_addr_reuse"

        def __init__(self, loaded):
            self._loaded = loaded

        def health(self):
            return SimpleNamespace(loaded=self._loaded)

    monkeypatch.setattr(r, "_enabled_sources", lambda: r._sources)
    orig = r._sources
    try:
        warm = [FakeSource(True)]
        r._sources = warm
        assert r._db_loaded() is True        # True 已按当前对象落进缓存

        id_warm = id(warm)
        r._sources = orig                    # 摘除引用,旧 list 方可回收(无环,
        del warm                             # 引用计数同步释放;gc.collect 反
        reused = None                       # 而扰动 freelist 令首轮失配)
        for _ in range(256):                # CPython freelist:旧实现下即中
            cand = [FakeSource(False)]
            if id(cand) == id_warm:
                reused = cand
                break
        r._sources = reused if reused is not None else [FakeSource(False)]
        assert r._db_loaded() is False       # 未载源:不得沿用 stale True
    finally:
        r._sources = orig
