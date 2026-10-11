"""S1 batch process-pool: layout sizing + fan-out."""
import pytest

# Module under test (created in this task); tiny_db fixture 来自 tests/conftest.py
from ipdb import _batch_pool
from ipdb import _registry
from concurrent.futures.process import BrokenProcessPool


@pytest.mark.parametrize("cpu, ram_mb, expected", [
    (16, 3900, (1, 6)),   # P=16 -> N=1, M=min(6, 15)=6
    (8, 8192, (1, 6)),    # P=8  -> N=1, M=min(6, 7)=6
    (4, 4096, (1, 3)),    # P=4  -> N=1, M=min(6, 4-1=3)=3
    (2, 2048, (1, 1)),    # P=2  -> below 3 -> serial inline
    (3, 2048, (1, 2)),    # P=3  -> N=1, M=min(6,2)=2
    (6, 4096, (1, 5)),    # P=6  -> N=1, M=min(6, 5)=5
    # RAM-bound: 2 cores, tons of RAM still caps at cpu
    (2, 65536, (1, 1)),
    # RAM-bound: many cores, little RAM (P from RAM)
    (16, 700, (1, 1)),    # (700-512)//90 = 2 -> P=2 -> serial
])
def test_compute_layout_formula(cpu, ram_mb, expected):
    assert _batch_pool.compute_layout(cpu, ram_mb) == expected


def test_compute_layout_constants_are_measured_values():
    assert _batch_pool.PER_PROC_MB == 90
    assert _batch_pool.RESERVE_MB == 512
    assert _batch_pool.M_CAP == 6
    assert _batch_pool.INLINE_THRESHOLD == 200
    assert _batch_pool.CHUNK == 200


@pytest.mark.parametrize("P", [1, 2, 3, 6, 8, 16])
def test_split_budget_always_single_worker(P):
    """恒 N=1(grill Q4 裁决 2026-10-11,P1-2):N=2 时每个 uvicorn worker
    进程各起一个 refresh-scheduler 双开互踩;预算全给批内池。"""
    N, _ = _batch_pool._split_budget(P)
    assert N == 1


def test_detect_host_returns_positive_ints():
    cpu, ram = _batch_pool.detect_host()
    assert isinstance(cpu, int) and cpu >= 1
    assert isinstance(ram, int) and ram > 0


def test_resolve_layout_formula_when_no_overrides():
    assert _batch_pool.resolve_layout(16, 3900, {}) == (1, 6)


def test_resolve_layout_env_overrides_formula():
    env = {"IPRADAR_WORKERS": "4", "IPRADAR_BATCH_POOL": "3"}
    assert _batch_pool.resolve_layout(16, 3900, env) == (4, 3)


def test_resolve_layout_total_procs_env_resplits():
    # IPRADAR_TOTAL_PROCS overrides the budget P, then split
    env = {"IPRADAR_TOTAL_PROCS": "8"}
    N, M = _batch_pool.resolve_layout(2, 2048, env)  # tiny host, but forced P=8
    assert (N, M) == _batch_pool._split_budget(8) == (1, 6)


def test_resolve_layout_non_numeric_env_falls_back(caplog):
    """M3: a non-numeric env override (typo) must not crash startup — it falls
    back to the formula value and logs a warning so the typo is visible."""
    # Formula on (16, 3900) -> (1, 6); typos must not change that.
    env = {"IPRADAR_WORKERS": "foo", "IPRADAR_BATCH_POOL": "bar"}
    with caplog.at_level("WARNING", logger="ipdb._batch_pool"):
        N, M = _batch_pool.resolve_layout(16, 3900, env)
    assert (N, M) == (1, 6)
    # Both typos are surfaced (one warning per key).
    msgs = " ".join(r.message for r in caplog.records)
    assert "IPRADAR_WORKERS" in msgs and "IPRADAR_BATCH_POOL" in msgs


def test_resolve_layout_non_numeric_total_procs_falls_back():
    """M3: IPRADAR_TOTAL_PROCS=foo also falls back to the auto formula."""
    env = {"IPRADAR_TOTAL_PROCS": "foo"}
    N, M = _batch_pool.resolve_layout(16, 3900, env)
    # auto formula on (16, 3900) -> (1, 6)
    assert (N, M) == (1, 6)


def test_work_chunk_returns_to_dict_dicts(tiny_db):
    """_work_chunk returns plain dicts (lookup().to_dict()), not LookupResult."""
    from ipdb import _registry
    out = _batch_pool._work_chunk(["8.8.8.8", "1.1.1.1"])
    assert len(out) == 2
    assert all(isinstance(d, dict) for d in out)
    assert out[0]["ip"] == "8.8.8.8"
    # matches inline
    assert out[0] == _registry.lookup("8.8.8.8").to_dict()


def test_work_chunk_spawns_in_isolated_process(tiny_db):
    """Regression for the spawn __main__ re-import trap: worker fns must run in a
    spawned child. If they were under __main__, this would recurse/crash."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, initializer=_batch_pool._init_worker, mp_context=ctx) as pool:
        out = pool.map(_batch_pool._work_chunk, [["8.8.8.8"]])
    results = list(out)
    assert results == [[_registry.lookup("8.8.8.8").to_dict()]]


def test_fan_out_lookup_inline_below_threshold(monkeypatch, tiny_db):
    """<= INLINE_THRESHOLD IPs go inline even when pool is available."""
    # Inject a poison pool that raises if its .map is called
    class _Poison:
        def map(self, fn, iterable):
            raise AssertionError("pool must not be called for <=threshold batches")
    _batch_pool.set_pool(_Poison())
    ips = ["8.8.8.8", "1.1.1.1"]  # len=2 << INLINE_THRESHOLD=200
    out = _batch_pool.fan_out_lookup(ips)
    # Assert we got inline results (and poison.map was never called)
    assert out == [_registry.lookup("8.8.8.8").to_dict(),
                   _registry.lookup("1.1.1.1").to_dict()]
    _batch_pool.set_pool(None)  # cleanup


def test_fan_out_lookup_falls_back_to_inline_on_broken_pool(monkeypatch, tiny_db):
    """A broken pool triggers inline fallback (never raises to the caller)."""
    # Force the pool path by reducing INLINE_THRESHOLD below our test size
    monkeypatch.setattr(_batch_pool, "INLINE_THRESHOLD", 1)

    # Track that the broken pool.map was actually called
    call_count = {"count": 0}
    class _Broken:
        def map(self, fn, iterable):
            call_count["count"] += 1
            raise BrokenProcessPool("simulated")
    _batch_pool.set_pool(_Broken())

    ips = ["8.8.8.8"] * 5  # len=5 > INLINE_THRESHOLD=1 → pool path taken
    try:
        out = _batch_pool.fan_out_lookup(ips)
        # Prove the pool.map was actually called (coverage of the except clause)
        assert call_count["count"] > 0, "Broken pool.map was never called"
        # Verify inline fallback produced correct results
        assert len(out) == 5
        assert out[0] == _registry.lookup("8.8.8.8").to_dict()
    finally:
        _batch_pool.set_pool(None)


def test_fan_out_lookup_preserves_order_and_count(tiny_db):
    """Output is in input order, one dict per IP, bit-identical to inline."""
    import hashlib, ipaddress
    ips = []
    i = 0
    while len(ips) < 10:
        b = int.from_bytes(hashlib.sha256(str(i).encode()).digest()[:4], "big")
        ip = f"{(b>>24)&255}.{(b>>16)&255}.{(b>>8)&255}.{b&255}"
        i += 1
        try:
            a = ipaddress.IPv4Address(ip)
            if not a.is_global or a.is_multicast:
                continue
        except ValueError:
            continue
        ips.append(ip)
    _batch_pool.set_pool(None)  # force inline path
    out = _batch_pool.fan_out_lookup(ips)
    expected = [_registry.lookup(ip).to_dict() for ip in ips]
    assert out == expected


def test_n_workers_cli_prints_int(monkeypatch, capsys):
    """`python -m ipdb._batch_pool n-workers` resolves N from host+env."""
    monkeypatch.setattr(_batch_pool, "detect_host", lambda: (8, 8192))  # -> N=1
    _batch_pool._cli(["n-workers"])
    out = capsys.readouterr().out.strip()
    assert out == "1"


def test_work_chunk_pool_worker_follows_epoch_rotation(monkeypatch):
    """P1-1(grill 2026-10-11):worker 孵化后主进程 rebuild 换 epoch 并 prune
    旧目录,子进程 mmap 挂未链接 inode 仍可读、不报错、永不触发 _base 的
    重开重试——批查恒旧代直到重启。修法:池 worker 分支进 chunk 前比对
    epoch 指纹,变化即 load_db 跟随轮转(主进程 inline 路径本有 LRU 指纹键
    护着,单查/批查从此同代)。直接测 _work_chunk(与 main.py 现行调用
    一致);fan_out_lookup 禁用(Task 3 将删)。"""
    from ipdb import _batch_pool, _registry

    # 指纹序列:gen1(锚定)→ gen2(换代)→ gen2(同代不得再重载)
    fps = iter([("gen1",), ("gen2",), ("gen2",)])
    monkeypatch.setattr(_batch_pool, "_epoch_fingerprint", lambda: next(fps))

    state = {"gen": "gen1"}  # mock registry 当前服务的代
    load_calls = []

    def _fake_load_db():  # 重载后 registry 服务新代
        load_calls.append(1)
        state["gen"] = "gen2"

    monkeypatch.setattr(_registry, "load_db", _fake_load_db)

    class _Stub:
        def to_dict(self):
            return {"gen": state["gen"]}

    monkeypatch.setattr(_registry, "lookup",
                        lambda ip, allowed_sources=None: _Stub())

    # 池 worker 身份(真实子进程里 _init_worker 置位;单测直置)
    monkeypatch.setattr(_batch_pool, "_IN_POOL_WORKER", True)
    # 预锚 gen1:模拟 worker 孵化装载后的稳态(生产里首 chunk 锚定,
    # 幂等重复装载;本测只测换代轮转分支,勿把锚定装载计入恰一次)
    _batch_pool._POOL_EPOCH_FP = ("gen1",)
    try:
        first = _batch_pool._work_chunk(["8.8.8.8"])    # gen1:锚定指纹
        rotated = _batch_pool._work_chunk(["8.8.8.8"])  # gen2:必重载
        same = _batch_pool._work_chunk(["8.8.8.8"])     # gen2 未变:不再重载
    finally:
        # 生产代码直写的模块缓存,monkeypatch 不认领,手工回收防泄漏
        _batch_pool._POOL_EPOCH_FP = None
    assert first == [{"gen": "gen1"}]   # 换代前照旧
    assert rotated == [{"gen": "gen2"}]  # 第二次查询走新代(旧代码 gen1=stale 即 bug)
    assert same == [{"gen": "gen2"}]
    assert len(load_calls) == 1          # 恰一次换代替换载(旧代码 0=从不重载)


def test_init_worker_sets_pool_child_flag(monkeypatch):
    """FIX6 接线钉死:_init_worker 必须设 IP_RADAR_POOL_CHILD(cleanup_stale
    见旗标即退)。删掉那行生产代码本测试必红 —— 无此接线,懒孵化子进程
    会 rmtree 主进程在途的 .new.<pid> staging。"""
    import os
    from unittest.mock import patch
    from ipdb import _batch_pool, _registry
    os.environ.pop("IP_RADAR_POOL_CHILD", None)
    try:
        # load_db 重:registry 全源装载,单元测试只需接线行为 —— 打桩。
        with patch.object(_registry, "load_db"):
            _batch_pool._init_worker()
        assert os.environ.get("IP_RADAR_POOL_CHILD") == "1"
    finally:
        # 生产代码直接 set(非 monkeypatch 通道),必须手工回收 ——
        # 泄漏会让同进程后续 cleanup_stale 测试全部静默 skip;
        # _IN_POOL_WORKER 同理:泄漏后主进程 LRU 路径(_dedup_lookup)
        # 会被误当池 worker 直查,后续 LRU 相关测试全部失真。
        os.environ.pop("IP_RADAR_POOL_CHILD", None)
        _batch_pool._IN_POOL_WORKER = False
