# backend/tests/alerts/test_health_fields.py — Task 5:health 扩展透传 /api/sources
"""_source_info 给 health dict 并入三键:content_age_h(now - 文件 mtime,
与 health() 同源读 source._path)与 observed_interval_h(_alerts 近 90 天
间隔中位数;2026-10-15 裁决后仅诊断/告警用,前端不再渲染)与
refresh_period_h(配置刷新周期,scheduler 档位口径 _scheduler._period_of)。
读失败(无文件/无 _path/OSError/_alerts 异常)→ 相应键或两键 None,
/api/sources 不得 500。fake source 循 test_source_mgmt 的
ListSrc 模式;observed 经 env 指向 tmp alerts.db(record_event 造历史)。
"""
import os
import time

import pytest

import ipdb._registry as reg


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    """逐用例独立 db 文件(autouse 已同值,显式同款循 test_storage 惯例)。"""
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


@pytest.fixture(autouse=True)
def _fake_source(tmp_path, monkeypatch):
    """ListSrc(循 test_source_mgmt 模式)换入 _sources,无禁用。"""
    from ipdb._sources._base import IpListSource

    class ListSrc(IpListSource):
        name = "ipinfo_lite"
        url = "https://example.com/x.txt"
        filename = "x.txt"
        fields = ("country_code",)
        reliability = 0.8
        authoritative_for = ["country_code"]

    src = ListSrc(data_dir=tmp_path)
    monkeypatch.setattr(reg, "_sources", [src])
    monkeypatch.setattr(reg, "_disabled", set())
    return src


def _touch_file(tmp_path, age_s):
    """写数据文件并把 mtime 钉到 now - age_s(消除创建时刻抖动)。"""
    f = tmp_path / "x.txt"
    f.write_text("1.2.3.4\n")
    mtime = time.time() - age_s
    os.utime(f, (mtime, mtime))
    return mtime


def _seed_events(n, gap_s=3600.0):
    """n 条等间隔事件 → 间隔中位数 = gap_s;最后一落在 now - gap_s。"""
    from ipdb import _alerts
    base = time.time() - n * gap_s
    for i in range(n):
        _alerts.record_event("ipinfo_lite", at=base + i * gap_s)


def test_file_and_history_both_keys(tmp_path, alerts_db):
    _touch_file(tmp_path, age_s=2 * 3600)
    _seed_events(5)

    h = reg.list_sources()[0]["health"]

    assert h["content_age_h"] == pytest.approx(2.0, abs=0.05)
    assert h["observed_interval_h"] == pytest.approx(1.0)


def test_no_file_content_age_none_observed_still_computed(tmp_path, alerts_db):
    # 文件不存在:content_age_h None;observed 与文件无关照常算
    _seed_events(5)

    h = reg.list_sources()[0]["health"]

    assert h["content_age_h"] is None
    assert h["observed_interval_h"] == pytest.approx(1.0)


def test_fewer_than_five_events_observed_none(tmp_path, alerts_db):
    _touch_file(tmp_path, age_s=3600)
    _seed_events(4)

    h = reg.list_sources()[0]["health"]

    assert isinstance(h["content_age_h"], float)
    assert h["observed_interval_h"] is None


def test_alerts_failure_both_keys_none_no_crash(tmp_path, alerts_db, monkeypatch):
    # _alerts 抛任何异常 → 两键 None,list_sources 不炸(route 不得 500)
    from ipdb import _alerts

    _touch_file(tmp_path, age_s=3600)
    _seed_events(5)

    def boom(source, now):
        raise RuntimeError("alerts db gone")

    monkeypatch.setattr(_alerts, "observed_interval_h", boom)

    h = reg.list_sources()[0]["health"]   # 不得 raise

    assert h["content_age_h"] is None
    assert h["observed_interval_h"] is None


def test_api_sources_json_carries_both_keys(tmp_path, alerts_db, monkeypatch,
                                            client_as_admin):
    # route 级:SourceHealthOut extra=allow 透传,两键出现在外层 JSON
    import main

    _touch_file(tmp_path, age_s=3600)
    _seed_events(5)
    monkeypatch.setattr(main, "list_sources", reg.list_sources)  # 真 registry 输出
    monkeypatch.setattr(main, "read_overview", lambda: [])

    resp = client_as_admin.get("/api/sources")

    assert resp.status_code == 200
    h = resp.json()[0]["health"]
    assert isinstance(h["content_age_h"], float)
    assert h["observed_interval_h"] == pytest.approx(1.0)


# ── refresh_period_h:更新列第二段改显配置刷新周期(2026-10-15 裁决;
# 档位口径与 _scheduler._period_of 同源,这里锁死防漂移)──

def test_refresh_period_tiers_match_scheduler(tmp_path, monkeypatch, alerts_db):
    """档位规则:stale_days<=1 → 12h(日两档);否则 stale_days×24h。"""
    from ipdb._sources._base import IpListSource

    class TwoDay(IpListSource):
        name = "two_day"
        url = "https://example.com/x.txt"
        filename = "x.txt"
        fields = ("country_code",)
        stale_days = 2

    class Daily(IpListSource):
        name = "daily"
        url = "https://example.com/y.txt"
        filename = "y.txt"
        fields = ("country_code",)
        stale_days = 1

    monkeypatch.setattr(reg, "_sources",
                        [TwoDay(data_dir=tmp_path), Daily(data_dir=tmp_path)])
    monkeypatch.setattr(reg, "_disabled", set())

    infos = reg.list_sources()

    assert infos[0]["health"]["refresh_period_h"] == 48.0
    assert infos[1]["health"]["refresh_period_h"] == 12.0


def test_refresh_period_missing_stale_days_falls_back_to_base_default(
        tmp_path, alerts_db):
    """无 stale_days 覆盖 → Source/IpListSource 基类缺省 7 → 168h;与
    payload 顶层 stale_days 同源(均为 None 仅档位回退,值诚实)。"""
    info = reg.list_sources()[0]

    assert info["stale_days"] == 7
    assert info["health"]["refresh_period_h"] == 168.0


def test_refresh_period_present_even_when_alerts_reads_fail(
        tmp_path, alerts_db, monkeypatch):
    """配置值与 _alerts 读取无关:_alerts 抐异常时 observed/content 两键
    None 但 refresh_period_h 照常出(配置周期永不为 None)。"""
    from ipdb import _alerts

    _touch_file(tmp_path, age_s=3600)
    _seed_events(5)

    def boom(source, now):
        raise RuntimeError("alerts db gone")

    monkeypatch.setattr(_alerts, "observed_interval_h", boom)

    h = reg.list_sources()[0]["health"]

    assert h["observed_interval_h"] is None
    assert h["refresh_period_h"] == 168.0


# ── OL-4:加载失败不再静默(ERROR 日志 + health.error 状态面)──

def test_load_failure_error_level_log_and_health_error(
        tmp_path, alerts_db, caplog):
    """epoch 损坏(ptr 指向不存在的 epoch 目录 → open_env_read 抛)→
    load_db 以 ERROR 级落日志(不再 warning 静默),list_sources 的
    health.error 携带异常消息(/api/sources 即状态面);loaded=False。"""
    import logging

    _touch_file(tmp_path, age_s=2 * 3600)
    # 损坏形态:ptr 声称 epoch 42,但 <base>.42 目录不存在
    (tmp_path / "x.txt.lmdb.ptr").write_text("42\n")

    with caplog.at_level(logging.ERROR, logger="ipdb._registry"):
        reg.load_db()

    assert any(r.levelno == logging.ERROR and "load failed" in r.getMessage()
               for r in caplog.records)
    h = reg.list_sources()[0]["health"]
    assert h["loaded"] is False
    assert h["error"] and "x.txt.lmdb.42" in h["error"]


def test_healthy_source_no_error_key_noise(tmp_path, alerts_db):
    """正常源(无库无文件,或库健康)不因 OL-4 合并冒出 error 噪声;
    error 仅在未加载且确有 load_error 时出现。"""
    # 场景:从未建库(无 ptr)→ load() 走 epoch None 早退,零异常
    _touch_file(tmp_path, age_s=2 * 3600)
    reg.load_db()
    h = reg.list_sources()[0]["health"]
    assert h["loaded"] is False
    assert h["error"] is None
