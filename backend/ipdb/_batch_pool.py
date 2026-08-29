"""S1 batch process-pool: auto-sized fan-out for big batch queries.

compute_layout() apportions a total process budget P between N uvicorn workers
(parallelism across requests) and M pool workers per uvicorn worker
(parallelism within one big batch). Constants are measurement-calibrated; see
docs/superpowers/specs/2026-08-06-batch-process-pool-design.md.
"""
import json
import logging
import os
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import functools

_log = logging.getLogger(__name__)

# ── Measurement-calibrated constants (do NOT change without re-measuring) ──
PER_PROC_MB = 90        # private RSS per process (Pss_Anon ~87 MB + headroom)
RESERVE_MB = 512        # OS + app + shared-mmap headroom
M_CAP = 6              # K>6 diminishing (measured K=8 slower than K=6)
INLINE_THRESHOLD = 200  # <= this many IPs -> inline, no IPC
CHUNK = 200            # fan-out task granularity


def _split_budget(P: int) -> tuple[int, int]:
    """Split total process budget P into (N uvicorn workers, M pool per worker)."""
    if P >= 6:
        N = 2
        M = min(M_CAP, (P - N) // N)
    elif P >= 3:
        N = 1
        M = min(M_CAP, P - 1)
    else:
        N, M = 1, 1
    return N, M


def compute_layout(cpu: int, ram_avail_mb: int) -> tuple[int, int]:
    """Return (N uvicorn workers, M pool workers per uvicorn worker) for the host."""
    P = min(cpu, max(2, (ram_avail_mb - RESERVE_MB) // PER_PROC_MB))
    return _split_budget(P)


def detect_host() -> tuple[int, int]:
    """Return (cpu_count, ram_available_mb). psutil 是硬依赖(requirements)."""
    cpu = os.cpu_count() or 2
    import psutil
    return cpu, psutil.virtual_memory().available // (1024 * 1024)


def _env_int(env: dict, key: str, default: int) -> int:
    """Parse env var as int. Returns ``default`` on missing/non-numeric; logs a
    warning on non-numeric so typos surface without crashing startup."""
    raw = env.get(key)
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        _log.warning(
            "ignoring non-integer env %s=%r (using default %d)", key, raw, default)
        return default


def resolve_layout(cpu: int, ram_avail_mb: int, env: dict) -> tuple[int, int]:
    """Compute (N, M) layout with precedence: env var > perf_config > auto formula.

    Precedence order:
    1. IPRADAR_TOTAL_PROCS env var (re-splits budget via _split_budget)
    2. Otherwise compute_layout(cpu, ram_avail_mb) formula
    3. IPRADAR_WORKERS/IPRADAR_BATCH_POOL env overrides (if present)
    4. Final values floored at 1 (minimum 1 worker, 1 pool per worker)

    Env overrides tolerate non-numeric values (e.g. IPRADAR_WORKERS=foo)
    by falling back to the value that would have been used without the override;
    a warning is logged so typos are visible. Missing/empty values are ignored.
    """
    auto_n, auto_m = compute_layout(cpu, ram_avail_mb)
    if "IPRADAR_TOTAL_PROCS" in env and env["IPRADAR_TOTAL_PROCS"]:
        P = _env_int(env, "IPRADAR_TOTAL_PROCS", 0)
        if P >= 2:
            N, M = _split_budget(P)
        else:
            N, M = auto_n, auto_m
    else:
        N, M = auto_n, auto_m
    if env.get("IPRADAR_WORKERS"):
        N = _env_int(env, "IPRADAR_WORKERS", N)
    if env.get("IPRADAR_BATCH_POOL"):
        M = _env_int(env, "IPRADAR_BATCH_POOL", M)
    return max(1, N), max(1, M)


# ── Process pool worker functions (spawn-safe: module-level, not under __main__) ──
def _init_worker():
    """ProcessPoolExecutor initializer: load the DB once per worker process.
    Spawn-safe: this module is imported as ipdb._batch_pool in the child."""
    global _IN_POOL_WORKER
    _IN_POOL_WORKER = True
    # 子进程永不跑启动清理(cleanup_stale 见此旗标即退):懒孵化的 worker
    # 首次批查询就会 load_db,不得 rmtree 主进程在途的 .new.<pid> staging。
    os.environ["IP_RADAR_POOL_CHILD"] = "1"
    from ipdb import _registry
    _registry.load_db()


def _epoch_fingerprint():
    """离线源 epoch 指纹 + 5 分钟时间桶。

    指纹: 任一源后台刷新换 epoch → 失效。时间桶: 瞬态降质(mid-reload 空贡献)
    结果的冻结窗口从 epoch 长度(≤30min+)封顶到 ≤5min, 在线源数据时效同封顶。
    只含离线源(有 _lmdb_base 者)——全部源均为离线(在线 enricher 已删, spec D1)。
    """
    from ipdb import _registry
    from ipdb._sources._lmdb import read_ptr
    fp = tuple(
        (s.name, read_ptr(s._lmdb_base))
        for s in _registry._enabled_sources()
        if hasattr(s, "_lmdb_base")
    )
    return fp + (int(time.time()) // 300,)


@functools.lru_cache(maxsize=2048)
def _cached_lookup(ip: str, epoch_fp: tuple) -> dict:
    """有界 LRU: 只读契约 —— 返回 dict 不 mutate。epoch_fp 进键保时效。"""
    from ipdb import _registry
    return _registry.lookup(ip).to_dict()


def _dedup_lookup(ips: list[str]) -> list[dict]:
    """Chunk 级去重:唯一 IP 只走一次全管线,结果按输入顺序展开。
    返回长度 == 输入长度(协议不变)。主进程 inline 路径(无池全量 + 有池
    ≤200 小批,顺序 chunk)走 LRU;池 worker(_IN_POOL_WORKER)直查零驻留。"""
    from ipdb import _registry
    if _IN_POOL_WORKER:
        def _get(ip):
            return _registry.lookup(ip).to_dict()
    else:
        epoch_fp = _epoch_fingerprint()
        def _get(ip):
            return _cached_lookup(ip, epoch_fp)
    unique: list[str] = []
    seen: dict[str, int] = {}
    for ip in ips:
        if ip not in seen:
            seen[ip] = len(unique)
            unique.append(ip)
    results = [_get(ip) for ip in unique]
    return [results[seen[ip]] for ip in ips]


def _work_chunk(ips: list[str]) -> list[dict]:
    """Worker: lookup + to_dict for a chunk of IPs (deduped). Returns plain dicts."""
    return _dedup_lookup(ips)


# ── Module-level pool handle (managed by lifespan) ──
_POOL: ProcessPoolExecutor | None = None
_IN_POOL_WORKER = False


def set_pool(pool: ProcessPoolExecutor | None) -> None:
    global _POOL
    _POOL = pool


def get_pool() -> ProcessPoolExecutor | None:
    return _POOL


def fan_out_lookup(ips: list[str]) -> list[dict]:
    """Lookup+to_dict for a list of IPs. Inline for small batches or when no
    pool / broken pool; otherwise fan out across the process pool. Output is in
    input order, one dict per IP."""
    if len(ips) <= INLINE_THRESHOLD or _POOL is None:
        return _dedup_lookup(ips)
    chunks = [ips[i:i + CHUNK] for i in range(0, len(ips), CHUNK)]
    try:
        chunk_results = list(_POOL.map(_work_chunk, chunks))
    except BrokenProcessPool:
        import logging
        logging.getLogger(__name__).warning(
            "batch pool broken; falling back to inline")
        return _dedup_lookup(ips)
    return [d for chunk in chunk_results for d in chunk]


def _cli(argv: list[str]) -> None:
    """CLI entry for start scripts: `python -m ipdb._batch_pool n-workers`."""
    cpu, ram = detect_host()
    N, M = resolve_layout(cpu, ram, os.environ)
    if argv and argv[0] == "n-workers":
        print(N)
    elif argv and argv[0] == "m-pool":
        print(M)
    else:
        print(f"n_workers={N} m_pool={M}")


if __name__ == "__main__":
    import sys
    _cli(sys.argv[1:])
