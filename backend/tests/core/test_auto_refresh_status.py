"""#478:「会不会自动刷新」查询口。

- RefreshScheduler.auto_refresh_status():四项(enabled 恒 True/running
  线程面/interval_s/last_scan_age_s),scan() 前 null、scan() 后数字,
  扫描线程起跑后 running True、停后 False。
- /api/db-status 的 auto_refresh 段:IPRADAR_AUTO_REFRESH=0(调度器未
  装配)→ enabled False、running False、interval/last_scan null;装配
  了 → enabled True、running True、interval_s 有值。
"""
import threading
import time

from fastapi.testclient import TestClient

import main
from ipdb._scheduler import RefreshScheduler

# db-status 是软收窄面(计数非鉴权面):带 web 客户端头匿名放行。
_CLIENT_HEADERS = {"x-ipradar-client": "web"}


def _make_scheduler(interval=1800):
    return RefreshScheduler(
        manager=None,                      # 空源册 + 不触发入队,manager 不被触达
        enabled_offline_sources=lambda: [],
        needs_rebuild_of=lambda s: False,
        interval=interval)


def _start_and_wait_running(sch):
    """起真扫描线程并等 running 翻 True(start() 装线程引用有窗口期)。"""
    stop = threading.Event()
    t = threading.Thread(target=sch.start, args=(stop,), daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while sch.auto_refresh_status()["running"] is not True:
        assert time.monotonic() < deadline, "扫描线程未在 5s 内上报 running"
        time.sleep(0.02)
    return stop, t


def test_auto_refresh_status_before_scan():
    """未扫描、无线程:四项基线 —— enabled True(对象存在即配置已开,
    装配门在 main)、running False、interval_s 原样、last_scan null。"""
    sch = _make_scheduler(interval=900)
    assert sch.auto_refresh_status() == {
        "enabled": True, "running": False, "interval_s": 900,
        "last_scan_age_s": None}


def test_auto_refresh_status_running_and_last_scan():
    """线程起跑 running True;scan() 过 last_scan_age_s 变数字(≥0);
    stop 后循环退出,running 如实回 False。"""
    sch = _make_scheduler()
    stop, t = _start_and_wait_running(sch)
    try:
        sch.scan(now=time.time())
        st = sch.auto_refresh_status()
        assert st["running"] is True
        assert isinstance(st["last_scan_age_s"], (int, float))
        assert st["last_scan_age_s"] >= 0.0
    finally:
        stop.set()
        t.join(timeout=5)
    assert sch.auto_refresh_status()["running"] is False


def test_db_status_auto_refresh_disabled(monkeypatch):
    """IPRADAR_AUTO_REFRESH=0:调度器根本不装配(_ensure_refresh_scheduler
    早退)→ enabled False、running False、interval/last_scan null。
    全局桩回 None:防同进程其它测试装配过的调度器漏进断言。"""
    monkeypatch.setenv("IPRADAR_AUTO_REFRESH", "0")
    monkeypatch.setattr(main, "_refresh_scheduler", None)
    client = TestClient(main.app)
    r = client.get("/api/db-status", headers=_CLIENT_HEADERS)
    assert r.status_code == 200
    assert r.json()["auto_refresh"] == {
        "enabled": False, "running": False,
        "interval_s": None, "last_scan_age_s": None}


def test_db_status_auto_refresh_enabled(monkeypatch):
    """调度器装配且线程在跑:enabled True、running True、interval_s
    有值、last_scan_age_s 还没扫描过 → null(数字分支由调度器单测钉)。"""
    sch = _make_scheduler()
    monkeypatch.setattr(main, "_refresh_scheduler", sch)
    stop, t = _start_and_wait_running(sch)
    try:
        client = TestClient(main.app)
        r = client.get("/api/db-status", headers=_CLIENT_HEADERS)
        assert r.status_code == 200
        st = r.json()["auto_refresh"]
        assert st["enabled"] is True
        assert st["running"] is True
        assert st["interval_s"] == 1800
        assert st["last_scan_age_s"] is None
    finally:
        stop.set()
        t.join(timeout=5)
