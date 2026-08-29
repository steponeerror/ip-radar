import asyncio
import ipaddress
import json
import logging
import math
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import asynccontextmanager
import orjson

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

import os
import sys
import threading
import time

# Release runs `uvicorn app.main:app` from the package root, so this file's
# directory (holding the sibling `ipdb/` package) isn't on sys.path. Dev runs
# `main:app` from backend/, where cwd already covers it. Insert the dir so
# `from ipdb import ...` resolves in both layouts.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ipdb import (
    load_db, lookup, get_status,
    list_sources, set_source_enabled,
    manager, stale_source_names,
)
from ipdb import _batch_pool
from ipdb._cidr import expand_inputs
from ipdb import _registry as _ipdb_registry
from ipdb import _update as _ipdb_update
from ipdb import _version as _ipdb_version
from ipdb._eval_manager import EvalManager, EvalBusyError
from ipdb._eval_reader import read_overview, read_source
from ipdb._api_models import (
    AckOut, BatchOut, DbStatusOut, ErrorEnvelope, EvalDetailOut,
    EvalJobAcceptedOut, EvalOverviewOut, LookupResultOut, PerfLayoutOut,
    SchedulerStatusOut, SourceInfoOut, TaskAcceptedOut, TasksSnapshotOut,
    UpdateAcceptedOut, UpdateDbOut, UpdateStateOut, VersionOut,
)
from ipdb._errors import (
    ApiError, ErrorCode, RETRY_AFTER_WARMING, envelope,
)

import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB

# eval 单槽任务管理(spec §5.2):子进程隔离,消融不碰主进程 _disabled
eval_manager = EvalManager()

# OpenAPI 错误信封声明(实际响应体由全局 exception handler 统一产出)。
# 按路由真实可达的状态码子集声明,不做全码大杂烩。
_ERRS_422_500 = {
    "422": {"model": ErrorEnvelope, "description": "request validation failed"},
    "500": {"model": ErrorEnvelope, "description": "internal server error"},
}
_ERRS_READY = {**_ERRS_422_500,
               "503": {"model": ErrorEnvelope, "description": "database warming up"}}
_ERRS_SOURCE = {**_ERRS_422_500,
                "404": {"model": ErrorEnvelope, "description": "unknown source"}}


async def _read_upload_capped(file: UploadFile, cap: int) -> bytes:
    """分块读上传体,累计超 cap 立即 400(chunked 传输不带 Content-Length,
    中间件挡不到这条路)。"""
    chunks = []
    size = 0
    while True:
        chunk = await file.read(8 * 1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > cap:
            raise HTTPException(
                400, f"File exceeds {cap // (1024*1024)}MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_body_capped(request: Request, cap: int) -> bytes:
    """流式读 JSON body 并封顶:chunked 传输无 Content-Length,中间件挡不到,
    这里逐块累计、超 cap 即 400(与 _read_upload_capped 同剖面)。"""
    chunks = []
    size = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        size += len(chunk)
        if size > cap:
            raise HTTPException(
                400, f"Request body exceeds {cap // (1024*1024)}MB limit")
        chunks.append(chunk)
    return b"".join(chunks)
ENRICH_CHUNK = 100

# Integral build-gate state. The gate itself is state-driven (see _db_ready):
# queries hold while offline tasks are actively building sources the DB has
# no loaded reader for — by construction this covers every enqueue door
# (cold-start thread, banner Retry via /api/update-db, single-source update,
# registry PATCH-enable, scheduler refresh). _BUILD_DEADLINE only bounds the
# window: past it the gate releases (超时即放行 — a wedged or paused build
# must not hold the server hostage). Armed at cold start; every NEW build
# episode arms a fresh window via the _coverage_episode transition, while a
# continuing episode keeps its original (expiring) deadline.
_BUILD_DEADLINE = math.inf
# True while the last _db_ready() probe saw coverage being built — detects
# build-episode STARTS (False→True) so each new episode gets a fresh
# deadline, while a CONTINUING episode keeps (and can outlive) its own.
_coverage_episode = False
_build_window_sec: float | None = None


def _window_sec() -> float:
    """Cold-start window policy timeout (memory-tiered), computed once."""
    global _build_window_sec
    if _build_window_sec is None:
        import psutil
        _build_window_sec = _cold_start_timeout(
            psutil.virtual_memory().total / 1e9)
    return _build_window_sec


class SourceEnabledPatch(BaseModel):
    enabled: bool


def _build_tasks_active(source_filter=None) -> bool:
    """Any queued/downloading/loading/throttled offline task, optionally
    restricted to sources matching `source_filter(name)`. Paused batches
    keep their tasks in these states by design."""
    return manager.has_active_offline_tasks(source_filter)


def _coverage_building() -> bool:
    """True while offline tasks are in flight whose sources still lack a
    loaded reader — i.e. queryable coverage is actively being constructed.
    Refresh/rebuild of already-loaded sources never gates queries (a
    settled 27/28 deployment stays servable during routine refresh)."""
    if not _build_tasks_active():
        return False
    loaded = {s.name for s in _ipdb_registry._enabled_sources()
              if s.health().loaded}
    return _build_tasks_active(lambda n: n not in loaded)


def _db_ready() -> bool:
    """Integral gate, by state: (a) nothing loaded → hold; (b) coverage is
    being built (in-flight tasks on sources with no loaded reader) within
    the armed deadline → hold — so neither the first cold batch nor any
    later rebuild can open the gate onto partial coverage mid-build (the
    first source's rebuild hot-swap flipping _db_loaded() True is NOT
    sufficient). Past the deadline the window force-releases.

    Deadline lifecycle: a NEW build episode (warm-boot PATCH-enable, a
    day-2 rebuild after the cold window naturally elapsed, a retry after
    a settle) arms a fresh window on its first probe; a CONTINUING
    episode keeps its original deadline, so the 超时即放行 release cannot
    slide forever (a paused build still releases at its deadline).
    Reuses _db_loaded() for the loaded check."""
    global _BUILD_DEADLINE, _coverage_episode
    building = _coverage_building()
    if building and not _coverage_episode:
        _BUILD_DEADLINE = time.time() + _window_sec()
    _coverage_episode = building
    if not _ipdb_registry._db_loaded():
        return False  # zero coverage: hold (never serve empty-DB clean verdicts)
    if building and time.time() < _BUILD_DEADLINE:
        return False
    return True


def require_ready():
    """Gate query endpoints during DB construction. Zero enabled sources is
    reported honestly via a machine-readable header (that state is not
    "warming"); otherwise delegates to _db_ready() so this gate and
    db-status's warming_up field share a single source of truth for "is the
    DB queryable".

    Resolves _db_loaded via the registry module attribute at call time (not a
    name bound at import) so a single patched reference reaches both this gate
    and lookup()'s internal check identically."""
    if not _ipdb_registry._enabled_sources():
        raise HTTPException(
            503, detail="no data sources enabled",
            headers={"X-IPRadar-Reason": "no-sources"})
    if not _db_ready():
        raise HTTPException(
            503, detail="database is warming up",
            headers={"X-IPRadar-Reason": "warming"})


async def _emit_chunks(src, total, done_start=0):
    """src: 产出 (idx, ip) 的可迭代对象; 低层流式吐行 helper。

    islice 按 CHUNK 分片(不整体物化), 逐片 asyncio.to_thread 计算,
    片完成即吐 row + progress。整批一个 try —— 异常向上抛, 由调用方终止。
    """
    import itertools
    it = iter(src)
    done = done_start
    while True:
        batch = list(itertools.islice(it, _batch_pool.CHUNK))
        if not batch:
            break
        ips = [ip for _, ip in batch]
        start_idx = batch[0][0]
        dicts = await asyncio.to_thread(_batch_pool._work_chunk, ips)
        for i, d in enumerate(dicts):
            yield orjson.dumps({"type": "row", "idx": start_idx + i,
                                "result": d}) + b"\n"
        done += len(dicts)
        yield orjson.dumps({"type": "progress",
                            "done": min(done, total), "total": total}) + b"\n"
        await asyncio.sleep(0)


async def _stream_lookup(expansion):
    """Stream lookup results row-by-row as NDJSON (protocol v2).

    Emits: start{total} → row{idx,result} × N → progress{done,total} → done{...}.
    Rows are emitted in chunk-completion order (not input order); each row
    carries its input ``idx`` so the frontend can re-sort. The expansion is
    lazy — IPs are never fully materialized; peak backend memory is bounded
    by the chunk list (≈30MB at 500k IPs).
    """
    import itertools
    total = expansion.total
    yield orjson.dumps({"type": "start", "total": total}) + b"\n"

    if total == 0:
        yield orjson.dumps({
            "type": "done", "invalid_lines": expansion.invalid,
            "ipv6_unsupported": expansion.ipv6,
        }) + b"\n"
        return

    pool = _batch_pool.get_pool()
    chunk_size = _batch_pool.CHUNK

    # Inline path: small batches or no pool — stream chunk-by-chunk.
    if total <= _batch_pool.INLINE_THRESHOLD or pool is None:
        yield (orjson.dumps({"type": "progress", "done": 0, "total": total})
               + b"\n")
        try:
            async for evt in _emit_chunks(expansion, total):
                yield evt
        except Exception as e:            # done-error 不静默 (spec §4)
            logging.getLogger(__name__).exception("inline stream error")
            yield (orjson.dumps({
                "type": "done", "invalid_lines": expansion.invalid,
                "ipv6_unsupported": expansion.ipv6,
                "error": str(e) or type(e).__name__,
                "code": ErrorCode.internal.value}) + b"\n")
            return
        yield (orjson.dumps({
            "type": "done", "invalid_lines": expansion.invalid,
            "ipv6_unsupported": expansion.ipv6,
        }) + b"\n")
        return

    # Pooled path: chunk the lazy generator, submit all, emit rows as they finish.
    yield (orjson.dumps({"type": "progress", "done": 0, "total": total})
           + b"\n")
    loop = asyncio.get_running_loop()
    it = iter(expansion)
    fut_to_chunk: dict = {}  # {future: (start_idx, ips)}
    try:
        while True:
            batch = list(itertools.islice(it, chunk_size))
            if not batch:
                break
            start_idx = batch[0][0]
            ips = [ip for _, ip in batch]
            fut = loop.run_in_executor(pool, _batch_pool._work_chunk, ips)
            fut_to_chunk[fut] = (start_idx, ips)
    except BrokenProcessPool:
        logging.getLogger(__name__).warning(
            "stream batch pool broke during submit; streaming inline")
        yield (orjson.dumps({"type": "progress", "done": 0, "total": total})
               + b"\n")   # 提交期一行未吐, 从头流式
        try:
            async for evt in _emit_chunks(expansion, total):
                yield evt
        except Exception as e:
            logging.getLogger(__name__).exception("submit-fallback stream error")
            yield (orjson.dumps({
                "type": "done", "invalid_lines": expansion.invalid,
                "ipv6_unsupported": expansion.ipv6,
                "error": str(e) or type(e).__name__,
                "code": ErrorCode.internal.value}) + b"\n")
            return
        yield (orjson.dumps({
            "type": "done", "invalid_lines": expansion.invalid,
            "ipv6_unsupported": expansion.ipv6,
        }) + b"\n")
        return

    emitted: set = set()
    pending = set(fut_to_chunk)
    done_count = 0
    try:
        while pending:
            finished, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED)
            for fut in finished:
                start_idx, _ = fut_to_chunk[fut]
                dicts = fut.result()
                for i, d in enumerate(dicts):
                    yield orjson.dumps({
                        "type": "row", "idx": start_idx + i, "result": d}) + b"\n"
                emitted.add(fut)
                done_count += len(dicts)
                yield orjson.dumps({
                    "type": "progress",
                    "done": min(done_count, total), "total": total}) + b"\n"
            await asyncio.sleep(0)
    except BrokenProcessPool:
        logging.getLogger(__name__).warning(
            "stream batch pool broke mid-wait; re-querying un-emitted chunks inline")
        # The broken future "completed" with an exception → it's in `finished`,
        # NOT `pending`. Use the `emitted` set to find ALL chunks that never had
        # their rows yielded: pending futures, the broken future, and any good
        # futures in the same `finished` batch iterated after the broken one.
        # LazyExpansion.__iter__ returns a fresh generator on each iter() call,
        # so re-iterating `expansion` would re-query from idx 0 — would
        # duplicate already-emitted rows. We track per-future instead.
        un_emitted = [(start_idx, ips)
                      for fut, (start_idx, ips) in fut_to_chunk.items()
                      if fut not in emitted]
        if un_emitted:
            # done_start = 已吐计数 = done_count (残局续发, 进度不回跳)
            un_emitted_stream = (
                (si + i, ip) for si, ips in un_emitted for i, ip in enumerate(ips))
            try:
                async for evt in _emit_chunks(
                        un_emitted_stream, total, done_start=done_count):
                    yield evt
            except Exception as e:
                logging.getLogger(__name__).exception(
                    "wait-fallback stream error")
                yield (orjson.dumps({
                    "type": "done", "invalid_lines": expansion.invalid,
                    "ipv6_unsupported": expansion.ipv6,
                    "error": str(e) or type(e).__name__,
                    "code": ErrorCode.internal.value}) + b"\n")
                return
    except Exception as e:            # 非 BPP 异常: done-error 终态, 不静默截断
        logging.getLogger(__name__).exception("stream lookup error")
        yield (orjson.dumps({
            "type": "done", "invalid_lines": expansion.invalid,
            "ipv6_unsupported": expansion.ipv6,
            "error": str(e) or type(e).__name__,
            "code": ErrorCode.internal.value}) + b"\n")
        return

    yield orjson.dumps({
        "type": "done", "invalid_lines": expansion.invalid,
        "ipv6_unsupported": expansion.ipv6,
    }) + b"\n"


def _cleanup_orphan_tmp(data_dir: Path) -> None:
    """lifespan 最早期:删 OOM kill / SIGKILL 残留。此时无 worker 在跑。

    LMDB 时代:_write_staged 的暂存文件(``<name>.lmdb.{count,cov,ptr}.new.<pid>``,
    os.replace 前被杀则永留;cleanup_stale 只删目录不删文件)。
    一次性迁移清洁工:MMDB 时代的 ``*.mmdb.*.tmp`` / ``*.mmdb.new.*`` 旧文件
    还在用户机器上,一并清掉。
    """
    orphans = list(data_dir.glob("*.lmdb.count.new.*")) \
        + list(data_dir.glob("*.lmdb.cov.new.*")) \
        + list(data_dir.glob("*.lmdb.ptr.new.*"))
    orphans += list(data_dir.glob("*.mmdb.*.tmp")) + list(data_dir.glob("*.mmdb.new.*"))
    orphans += list(data_dir.glob("*.mmdb.count.new.*")) + list(data_dir.glob("*.mmdb.cov.new.*"))
    for tmp in orphans:
        try:
            tmp.unlink()
        except OSError:
            pass


def _cold_start_timeout(total_gb: float) -> int:
    """超时分档(B2)。env 覆盖。"""
    env_val = os.environ.get("IP_RADAR_COLD_START_TIMEOUT", "").strip()
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    if total_gb < 6:
        return 1800
    if total_gb < 12:
        return 1200
    return 900


_valve_stop: threading.Event | None = None


def _ensure_valve_sampler() -> None:
    """Start the memory-valve sampler thread once per process."""
    global _valve_stop
    if _valve_stop is not None:
        return
    from ipdb._registry import _valve
    _valve_stop = threading.Event()
    _valve.start_sampler(manager._queue_cv, _valve_stop, interval=2.0)


_refresh_scheduler = None
_scheduler_stop: threading.Event | None = None


def _ensure_refresh_scheduler() -> None:
    """Start the background auto-refresh scheduler once per process.

    Mirrors _ensure_valve_sampler. Disabled entirely when
    IPRADAR_AUTO_REFRESH=0 (status endpoint still reports enabled=False).
    """
    global _refresh_scheduler, _scheduler_stop
    if os.environ.get("IPRADAR_AUTO_REFRESH", "1") == "0":
        return
    if _refresh_scheduler is not None:
        return
    from ipdb._scheduler import RefreshScheduler
    from ipdb._registry import enabled_offline_sources, _needs_rebuild_of
    interval = int(os.environ.get("IPRADAR_REFRESH_INTERVAL_SEC", "1800"))
    _refresh_scheduler = RefreshScheduler(
        manager=manager,
        enabled_offline_sources=enabled_offline_sources,
        needs_rebuild_of=_needs_rebuild_of,
        interval=interval)
    _scheduler_stop = threading.Event()
    threading.Thread(
        target=_refresh_scheduler.start, args=(_scheduler_stop,),
        daemon=True, name="refresh-scheduler").start()
    logging.getLogger(__name__).info(
        "auto-refresh scheduler started (interval=%ds)", interval)


def _is_cold_start() -> bool:
    """True if NO enabled offline source has an existing data file on disk.

    All sources are offline file-backed (online enrichers removed, spec D1).
    A source missing the ``_path`` attribute entirely is treated as having no
    data (defensive; real offline sources always set it in IpListSource.__init__).
    """
    from ipdb._registry import _enabled_sources, _archetype
    offline = [s for s in _enabled_sources() if _archetype(s) == "offline"]
    return not any(getattr(s, "_path", None) and Path(s._path).exists()
                   for s in offline)


def _cold_start_background():
    """Cold start reduced to enqueueing the build batch: the integral gate
    (_db_ready) is driven by live task state, so this thread needs no
    blocking waits — settle and deadline handling live in the gate itself.
    An exception here only abandons the build attempt: zero sources loaded
    → gate holds → WarmupBanner shows failure/retry, with a log record."""
    try:
        _ensure_valve_sampler()
        names = _offline_enabled_names()
        if not names:
            return  # 全在线源部署:_db_loaded() 恒 True,require_ready 直放行
        manager.enqueue_batch(names)
    except Exception:
        logging.getLogger(__name__).exception(
            "cold-start background thread failed")


def _startup_warm():
    """Warm path: load all sources from disk immediately, then refresh any stale
    ones in the background (non-blocking — the whole point of the warm branch)."""
    from ipdb._registry import sources_needing_rebuild
    load_db()
    _ensure_valve_sampler()
    needs_rebuild = sources_needing_rebuild()
    stale = stale_source_names()
    merge = list(dict.fromkeys(needs_rebuild + stale))
    if merge:
        manager.enqueue_stale(merge)


def _startup():
    global _BUILD_DEADLINE
    _ipdb_update.reconcile_on_startup()  # F2:启动对账上次更新结果
    if _is_cold_start():
        _BUILD_DEADLINE = time.time() + _window_sec()
        threading.Thread(daemon=True, target=_cold_start_background,
                         name="cold-start").start()
    else:
        _startup_warm()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ipdb._registry import DATA_DIR
    _cleanup_orphan_tmp(DATA_DIR)
    _startup()
    _ensure_refresh_scheduler()
    cpu, ram = _batch_pool.detect_host()
    env = dict(os.environ)
    cfg = _batch_pool.load_perf_config()
    N, M = _batch_pool.resolve_layout(cpu, ram, env, cfg)
    source = "env" if (env.get("IPRADAR_WORKERS") or env.get("IPRADAR_BATCH_POOL")
                       or env.get("IPRADAR_TOTAL_PROCS")) else ("config" if cfg else "auto")
    _ACTIVE_LAYOUT.update(n_workers=N, m_pool=M, source=source)
    pool = None
    if M > 1:
        try:
            ctx = multiprocessing.get_context("spawn")
            pool = ProcessPoolExecutor(max_workers=M,
                                       initializer=_batch_pool._init_worker,
                                       mp_context=ctx)
        except Exception as e:  # spawn failure -> inline mode, server still serves
            logging.getLogger(__name__).warning(f"batch pool init failed: {e}; inline mode")
            pool = None
    _batch_pool.set_pool(pool)
    try:
        yield
    finally:
        if _scheduler_stop is not None:
            _scheduler_stop.set()
        if _valve_stop is not None:
            _valve_stop.set()
        if pool is not None:
            pool.shutdown(wait=False)
        _batch_pool.set_pool(None)


_ACTIVE_LAYOUT: dict = {"n_workers": 1, "m_pool": 1, "source": "auto"}


def get_active_layout() -> dict:
    return dict(_ACTIVE_LAYOUT)

app = FastAPI(title="IP Lookup Tool", lifespan=lifespan)

# ── 全局错误信封(spec 2026-08-28 §5.3)──
# 所有 HTTP 错误统一 {"error":{code,message,detail?,retry_after?}},status 透传。
# 普通 HTTPException 按状态映射通用码;require_ready 的 X-IPRadar-Reason
# 头映射语义码(warming 带 retry_after)。
_HTTP_FALLBACK_CODE = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 405: "method_not_allowed", 409: "conflict",
    413: "payload_too_large", 415: "unsupported_media_type",
    422: "validation_error", 429: "rate_limited",
    501: "not_implemented", 503: "not_ready",
}


def _reason_code(headers: dict | None):
    """X-IPRadar-Reason 头 → (语义码, retry_after);无头返回 None。"""
    reason = (headers or {}).get("X-IPRadar-Reason")
    if reason == "warming":
        return "warming", RETRY_AFTER_WARMING
    if reason == "no-sources":
        return "no_sources", None
    return None


@app.exception_handler(ApiError)
async def _api_error_handler(request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=exc.envelope())


@app.exception_handler(StarletteHTTPException)
async def _http_error_handler(request, exc: StarletteHTTPException):
    from http import HTTPStatus
    headers = dict(exc.headers) if exc.headers else None
    retry_after = None
    mapped = _reason_code(headers)
    if mapped is not None:
        code, retry_after = mapped
    else:
        code = _HTTP_FALLBACK_CODE.get(exc.status_code, "internal")
        ra = (headers or {}).get("Retry-After")
        if exc.status_code == 429 and ra is not None:
            try:
                retry_after = int(ra)
            except ValueError:
                retry_after = None  # HTTP-date 形式不解析,只留头
    message = str(exc.detail) if exc.detail else \
        HTTPStatus(exc.status_code).phrase
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(code, message, retry_after=retry_after),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        status_code=422,
        content=envelope("validation_error", "request validation failed",
                         detail=jsonable_encoder(exc.errors())),
    )


@app.exception_handler(Exception)
async def _unhandled_error_handler(request, exc: Exception):
    logging.exception("unhandled error on %s %s",
                      request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=envelope("internal", "internal server error"),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_oversized_bodies(request, call_next):
    """信任边界:大 body 在被读进内存之前拒绝(未认证可打的 OOM 面)。
    挡 Content-Length 声明的超限;chunked 传输的洞由路由内分块读再堵。"""
    if request.method == "POST" and request.url.path in (
            "/api/upload/stream", "/api/query/stream"):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_UPLOAD_BYTES:
            # 直接响应不走 exception handler → 手写信封(与全局信封同形状)
            return JSONResponse(
                status_code=400,
                content=envelope(
                    "bad_request",
                    f"Request body exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit"))
    return await call_next(request)


@app.post("/api/query/stream", dependencies=[Depends(require_ready)],
          responses=_ERRS_READY,
          summary="Batch IP lookup (NDJSON stream)",
          description="Streaming NDJSON: one JSON object per input IP, same "
          "shape as GET /api/lookup/{ip} (fields: ip/country/city/asn/as_name/"
          "ip_range/is_isp/threat/classifications/attributes/is_reserved,"
          "merged fields carry value+confidence+algorithm+sources). Each line "
          "is a complete lookup event; malformed input lines count as error "
          "events (error field set). HTTP-level errors (400/503) return the "
          "JSON error envelope instead of a stream. Terminal done events that "
          "carry an error string also carry a machine-readable code field "
          "(e.g. \"internal\").")
async def query_ips_stream(request: Request):
    # body 不走 FastAPI 自动解析(dict 形参会整包缓冲,chunked 无 CL 时
    # 中间件也挡不到)——流式封顶读完后自行解析,语义与原 body:dict 一致。
    body = await _read_body_capped(request, MAX_UPLOAD_BYTES)
    try:
        parsed = orjson.loads(body)
    except orjson.JSONDecodeError:
        raise HTTPException(400, "Request body must be valid JSON")
    if not isinstance(parsed, dict):
        raise HTTPException(400, "Request body must be a JSON object")
    raw = parsed.get("ips", [])
    if not isinstance(raw, list):
        raise HTTPException(400, "'ips' must be a list")
    if not raw:
        raise HTTPException(400, "No IPs provided")
    if len(raw) > 100000:
        raise HTTPException(400, "Max 100,000 input lines per request")
    expansion = expand_inputs([str(x) for x in raw])
    if expansion.total > 500_000:
        raise HTTPException(
            400, f"Expanded size {expansion.total:,} exceeds 500,000 limit")
    return StreamingResponse(
        _stream_lookup(expansion),
        media_type="application/x-ndjson",
    )


@app.post("/api/upload/stream", dependencies=[Depends(require_ready)],
          responses=_ERRS_READY,
          summary="Batch IP lookup from uploaded file (NDJSON stream)",
          description="Streaming NDJSON: same per-line lookup event shape as "
          "POST /api/query/stream (one JSON object per extracted IP). "
          "HTTP-level errors (400/503) return the JSON error envelope. "
          "Terminal done events that carry an error string also carry a "
          "machine-readable code field (e.g. \"internal\").")
async def upload_file_stream(file: UploadFile = File(...)):
    content = await _read_upload_capped(file, MAX_UPLOAD_BYTES)
    content = content.decode("utf-8", errors="ignore")
    lines = content.strip().splitlines()
    if len(lines) > 100000:
        raise HTTPException(400, "File exceeds 100,000 lines")
    # take first CSV column if .csv, else whole line
    first_cols = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if file.filename and file.filename.endswith(".csv"):
            line = line.split(",")[0].strip()
        if line:
            first_cols.append(line)
    expansion = expand_inputs(first_cols)
    if expansion.total > 500_000:
        raise HTTPException(
            400, f"Expanded size {expansion.total:,} exceeds 500,000 limit")
    return StreamingResponse(
        _stream_lookup(expansion),
        media_type="application/x-ndjson",
    )


@app.get("/api/db-status", response_model=DbStatusOut,
          responses=_ERRS_422_500)
async def db_status():
    status = get_status()
    # 全源禁用不是 warming:报 False 隐藏横幅,查询走 require_ready 的诚实报错
    status["warming_up"] = bool(_ipdb_registry._enabled_sources()) and not _db_ready()
    return status


@app.get("/api/scheduler/status", response_model=SchedulerStatusOut,
          responses=_ERRS_422_500)
async def scheduler_status():
    """Read-only snapshot of the auto-refresh scheduler."""
    if _refresh_scheduler is None:
        return {"enabled": False,
                "interval_sec": int(os.environ.get("IPRADAR_REFRESH_INTERVAL_SEC", "1800")),
                "last_scan_at": None, "next_scan_at": None, "sources": []}
    return _refresh_scheduler.status()


def _offline_enabled_names():
    """Names of enabled offline sources (candidates for batch update)."""
    from ipdb._registry import _enabled_sources, _archetype
    return [s.name for s in _enabled_sources() if _archetype(s) == "offline"]


@app.post("/api/update-db", response_model=UpdateDbOut,
           responses=_ERRS_422_500)
async def update_db():
    """Refresh ALL enabled offline sources, regardless of staleness.

    Every source is re-downloaded and rebuilt. The MemoryValve gates rebuild
    concurrency (target_capacity adapts to available memory), so a full batch
    no longer risks OOM the way it did before the valve. Returns
    ``refreshed=0`` only when there are no enabled offline sources at all.
    """
    names = _offline_enabled_names()
    if not names:
        return {"batch_id": None, "refreshed": 0}
    bid = manager.enqueue_batch(names)
    return {"batch_id": bid, "refreshed": len(names)}


@app.post("/api/update-db/cancel", response_model=AckOut,
           responses=_ERRS_422_500)
async def update_db_cancel():
    manager.cancel_batch(manager._active_batch)
    return {"ok": True}


@app.post("/api/update-db/pause", response_model=AckOut,
           responses=_ERRS_422_500)
async def update_db_pause():
    manager.pause()
    return {"ok": True}


@app.post("/api/update-db/resume", response_model=AckOut,
           responses=_ERRS_422_500)
async def update_db_resume():
    manager.resume()
    return {"ok": True}


@app.get("/api/lookup/{ip}", response_model=LookupResultOut,
          dependencies=[Depends(require_ready)],
          responses={"400": {"model": ErrorEnvelope,
                            "description": "invalid IP address"},
                     **_ERRS_READY})
async def lookup_single(ip: str):
    """Single IP lookup — same shape as POST /api/query results[0].

    confidence (0-100) is a log-odds posterior: per-source reliability becomes a
    symmetric logit coefficient, decays with a 60-day half-life, and coefficients
    fuse additively within each classification_type group
    (design: docs/superpowers/specs/2026-08-29-scoring-fusion-design.md §3).
    confidence == 0 on a field means no source reported it — absence of
    evidence, not proof of innocence. Qualifiers: scalar fields (country/asn)
    have no first_seen → no decay and fuse per candidate value with a
    background mass; city/ip_range keep legacy semantics.
    """
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ApiError(ErrorCode.invalid_ip, f"invalid IP address: {ip}")
    result = await asyncio.to_thread(lookup, ip)
    return result.to_dict()


@app.get("/api/lookup/{ip}/stix", response_model=dict,
          dependencies=[Depends(require_ready)],
          responses={"400": {"model": ErrorEnvelope,
                            "description": "invalid/reserved IP"},
                     "501": {"model": ErrorEnvelope,
                             "description": "stix2 package not installed"},
                     **_ERRS_READY})
async def lookup_stix(ip: str):
    """Single IP STIX 2.1 Bundle export."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ApiError(ErrorCode.invalid_ip, f"invalid IP address: {ip}")
    from ipdb._stix_export import to_stix_bundle

    result = await asyncio.to_thread(lookup, ip)
    if result.error:
        raise HTTPException(400, result.error)
    if result.is_reserved:
        raise HTTPException(400, "reserved address: no threat intel")

    bundle = to_stix_bundle(result)
    if bundle is None:
        raise HTTPException(
            501,
            "STIX export unavailable: install stix2 package (pip install stix2)",
        )
    return bundle


@app.get("/api/sources", response_model=list[SourceInfoOut],
          responses=_ERRS_422_500)
async def list_sources_route():
    items = list_sources()
    # eval verdict 聚合(spec §5.2):agent 查目录一次拿到 健康+类别+权重+
    # 最近考分;无报告 → null。不加缓存,29 源量级可接受。
    _ev = {v["source"]: v for v in read_overview()}
    for it in items:
        v = _ev.get(it["name"])
        it["eval"] = {"verdict": v["verdict"], "at": v["at"]} if v else None
    return items


@app.patch("/api/sources/{name}", response_model=SourceInfoOut,
           responses=_ERRS_SOURCE)
async def set_source_enabled_route(name: str, patch: SourceEnabledPatch):
    try:
        return await asyncio.to_thread(set_source_enabled, name, patch.enabled)
    except ValueError:
        raise ApiError(ErrorCode.source_not_found, f"unknown source: {name}")


@app.post("/api/sources/{name}/update", response_model=TaskAcceptedOut,
           responses=_ERRS_SOURCE)
async def update_source_route(name: str):
    try:
        t = manager.enqueue_one(name)
    except ValueError:
        raise ApiError(ErrorCode.source_not_found, f"unknown source: {name}")
    return {"task_id": t.id}


# ── eval 端点(spec 2026-08-28 §5.2:成绩单上墙)──
# 两个 GET 是纯文件读(历史报告),不碰 LMDB → 不挂 require_ready
# (warming 期仍能诚实报告过往 verdict);POST run 会起子进程对当前
# DB 做消融评估,warming 期评估无意义 → 与 lookup 同门。PR③ 统一错误信封。

@app.get("/api/eval", response_model=EvalOverviewOut,
          responses=_ERRS_422_500)
async def eval_overview_route():
    """全源最新 eval verdict 摘要 + 当前 eval 任务状态(current_job)。"""
    return {"current_job": eval_manager.current, "verdicts": read_overview()}


@app.get("/api/eval/{source}", response_model=EvalDetailOut,
          responses=_ERRS_SOURCE)
async def eval_detail_route(source: str):
    """单源 eval 历史 + 最新详情;源存在但无报告 → latest null。"""
    if _ipdb_registry._find_source(source) is None:
        raise ApiError(ErrorCode.source_not_found, f"unknown source: {source}")
    return read_source(source)


@app.post("/api/eval/{source}/run", status_code=202,
          response_model=EvalJobAcceptedOut,
          dependencies=[Depends(require_ready)],
          responses={"404": {"model": ErrorEnvelope,
                            "description": "unknown source"},
                     "409": {"model": ErrorEnvelope,
                             "description": "another eval job is running"},
                     **_ERRS_READY})
async def eval_run_route(source: str):
    """触发单源 eval(子进程 CLI --json);单槽,busy → 409。"""
    if _ipdb_registry._find_source(source) is None:
        raise ApiError(ErrorCode.source_not_found, f"unknown source: {source}")
    try:
        job = eval_manager.run(source)
    except EvalBusyError as e:
        raise ApiError(ErrorCode.eval_busy, str(e))
    return {"job_id": job["job_id"]}


@app.post("/api/tasks/{task_id}/cancel", response_model=AckOut,
           responses=_ERRS_422_500)
async def cancel_task_route(task_id: str):
    manager.cancel(task_id)
    return {"ok": True}


@app.get("/api/tasks", response_model=TasksSnapshotOut,
          responses=_ERRS_422_500)
async def tasks_snapshot():
    """Point-in-time snapshot of in-flight tasks + active batch."""
    return manager.snapshot()


@app.get("/api/events",
          summary="SSE task/batch event stream",
          description="Server-Sent Events: `data: <json>` per event. First "
          "event is {type:'snapshot', data:{tasks,batch}}; then task/batch "
          "lifecycle events ({type:'task'|'batch', ...}). task events in the "
          "failed state carry a machine-readable error_code (e.g. \"internal\", "
          "\"source_not_found\"). No response_model — "
          "event payloads are documented here, not as a JSON schema.")
async def events():
    """SSE stream of task/batch events. Yields an initial snapshot event on
    connect so reconnects resync, then one `data: <json>` line per event."""
    loop = asyncio.get_running_loop()
    q = manager.subscribe(loop)

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'snapshot', 'data': manager.snapshot()})}\n\n"
            while True:
                evt = await q.get()
                yield f"data: {json.dumps(evt)}\n\n"
        finally:
            manager.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/perf/layout", response_model=PerfLayoutOut,
          responses=_ERRS_422_500)
async def perf_layout():
    import psutil
    from ipdb._registry import _valve
    cpu, ram = _batch_pool.detect_host()
    layout = get_active_layout()
    predicted = _batch_pool.predict_layout(cpu, ram, layout)
    warnings = _batch_pool.predict_warnings(predicted["priv_rss_mb"], ram)
    vmem = psutil.virtual_memory()
    state = ("critical" if _valve.target_capacity == 0
             else "throttled" if _valve.target_capacity < _valve.ceiling
             else "normal")
    return {
        "host": {"cores": cpu, "ram_avail_mb": ram},
        "current": layout,
        "predicted": predicted,
        "tunables": {
            "m_cap": _batch_pool.M_CAP,
            "per_proc_mb": _batch_pool.PER_PROC_MB,
            "inline_threshold": _batch_pool.INLINE_THRESHOLD,
        },
        "warnings": warnings,
        "memory_valve": {
            "available_mb": int(vmem.available / 1e6),
            "total_mb": int(vmem.total / 1e6),
            "available_ratio": round(vmem.available / vmem.total, 3),
            "target_capacity": _valve.target_capacity,
            "ceiling": _valve.ceiling,
            "active_rebuilds": _valve.active_rebuilds,
            "state": state,
        },
    }


class SpaStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback: paths that aren't real files (e.g.
    BrowserRouter deep links like /sources) serve index.html so the client
    router handles them on direct hit / refresh. Plain StaticFiles(html=True)
    only returns index.html at the directory root and 404s everything else."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not scope["path"].startswith("/api"):
                return await super().get_response("index.html", scope)
            raise


# ── Static file serving for production frontend ──
# In development: run `npm run dev` separately (port 5173) for hot-reload.
# In production: build first — cd frontend && npm run build — then access :8000.
_static_dir = Path(__file__).parent.parent / "frontend" / "dist"


# ── In-app update endpoints (spec: 2026-08-23-in-app-update-design.md) ──

_UPDATE_BG_TASKS: set = set()  # 持引用防 create_task 被 GC 中途回收


def _spawn_update() -> None:
    """触发即忘:更新成功时本进程会被 compose recreate 杀死(F2 对账收尾)。"""
    task = asyncio.create_task(asyncio.to_thread(_ipdb_update.run_update))
    _UPDATE_BG_TASKS.add(task)
    task.add_done_callback(_UPDATE_BG_TASKS.discard)


@app.get("/api/version", response_model=VersionOut,
          responses=_ERRS_422_500)
async def api_version(refresh: bool = False):
    latest = await _ipdb_version.fetch_latest(force=refresh)
    tag = latest["tag"] if latest else None
    return {
        "current": _ipdb_version.VERSION,
        "latest": tag,
        "update_available": _ipdb_version.update_available(_ipdb_version.VERSION, tag),
        "summary": latest["summary"] if latest else None,
        "release_url": latest["url"] if latest else "https://github.com/steponeerror/ip-radar/releases/latest",
        "self_update_enabled": _ipdb_update.self_update_enabled(),
    }


@app.post("/api/update", status_code=202, response_model=UpdateAcceptedOut,
           responses={"403": {"model": ErrorEnvelope,
                             "description": "token missing/invalid or disabled"},
                     "409": {"model": ErrorEnvelope,
                             "description": "update already in progress"},
                     **_ERRS_422_500})
async def api_update(authorization: str = Header(default="")):
    import hmac
    token = os.environ.get("IP_RADAR_UPDATE_TOKEN", "")
    if not token or not authorization.startswith("Bearer ") or \
       not hmac.compare_digest(authorization[7:].encode(), token.encode()):
        raise HTTPException(403, detail="update token missing or invalid")
    if not _ipdb_update.self_update_enabled():
        raise HTTPException(403, detail="self-update not enabled")
    if _ipdb_update.state()["state"] == "updating":
        raise HTTPException(409, detail="update already in progress")
    _ipdb_update.mark_updating()
    _spawn_update()
    return JSONResponse(status_code=202, content={"status": "accepted"})


@app.get("/api/update/status", response_model=UpdateStateOut,
          responses=_ERRS_422_500)
async def api_update_status():
    return _ipdb_update.state()

_env_static = os.environ.get("IP_RADAR_STATIC_DIR")
if _env_static:
    _static_dir = Path(_env_static)
if _static_dir.exists():
    app.mount("/", SpaStaticFiles(directory=str(_static_dir), html=True), name="frontend")
    logging.info("Serving frontend from %s", _static_dir)
else:
    logging.info("No frontend build at %s — API only", _static_dir)

