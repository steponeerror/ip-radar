"""Rebuild 子进程隔离(IP_RADAR_REBUILD_SUBPROCESS)三场景。

- 默认 off:rebuild-only 任务走原 in-process 路径(位等价约束)。
- 子进程 E2E:`python -m ipdb._rebuild_child greensnow` 对 tmp 数据目录
  重建 → rc 0 + OK 行 + ptr sidecar。
- 父进程开关:manager 走子进程车道 → done + ptr 推进;未知源名 rc 2 →
  failed 且 error 非空。

取消路径不做时序测试(terminate 与子进程写管道的竞态复杂度过高,
见任务报告);记账语义由 _run_task 共享尾巴保证,与 in-process 取消同路。
源选 greensnow:全仓最简 IpListSource(零覆写 download/rebuild,裸 IP 列表)。
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ipdb._sources._lmdb import read_ptr
from ipdb._tasks import UpdateManager

BACKEND = Path(__file__).resolve().parents[2]


def _make_manager(by_name: dict):
    locks: dict[str, threading.Lock] = {}

    def lock_for(n):
        locks.setdefault(n, threading.Lock())
        return locks[n]

    return UpdateManager(resolve_source=lambda n: by_name.get(n),
                         lock_for=lock_for)


def _wait_terminal(mgr, task, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = mgr.task_state(task.id)
        if state in ("done", "failed", "cancelled"):
            return state
        time.sleep(0.05)
    return mgr.task_state(task.id)


def test_default_off_runs_rebuild_in_process(tmp_path, monkeypatch):
    """不设 IP_RADAR_REBUILD_SUBPROCESS:rebuild-only 任务走原 in-process
    路径(位等价)——rebuild 在父进程对象上执行,任务 done。"""
    monkeypatch.delenv("IP_RADAR_REBUILD_SUBPROCESS", raising=False)
    calls = {"rebuild": 0}

    class Src:
        name = "s"
        download_host = None

        def __init__(self):
            self._path = tmp_path / "s.raw"
            self._path.write_text("x")

        def download(self, token=None):
            raise AssertionError("rebuild-only 且 raw 存在时不得下载")

        def rebuild(self):
            calls["rebuild"] += 1

    mgr = _make_manager({"s": Src()})
    task = mgr.enqueue_one_detached("s", rebuild_only=True)
    assert _wait_terminal(mgr, task) == "done"
    assert calls["rebuild"] == 1


def test_child_e2e_builds_and_commits_ptr(tmp_path, monkeypatch):
    """子进程 E2E:IP_RADAR_DATA_DIR 指 tmp(仅子进程导入期读取,父测试
    进程的 registry 不受影响),raw 落一份小 greensnow 列表 → 子进程
    rc 0、stdout 有 OK 行、tmp 下 ptr sidecar 出现。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    raw = tmp_path / "greensnow.txt"
    raw.write_text("1.2.3.4\n5.6.7.8\n9.9.9.9\n")
    r = subprocess.run(
        [sys.executable, "-m", "ipdb._rebuild_child", "greensnow"],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-400:]
    assert "OK 3" in r.stdout.splitlines()      # 3 个 v4 /32 → 3 键
    assert read_ptr(tmp_path / "greensnow.txt.lmdb") is not None


def test_manager_subprocess_lane_done_ptr_advances_and_rc2_fails(
        tmp_path, monkeypatch):
    """父进程开关路径:两 env 齐设,manager 的 rebuild-only 任务走子进程
    车道 → done、tmp 下 ptr 推进、父进程 load() 重同步 count;对子进程
    侧不存在的源名 → rc 2 → failed 且 error 非空。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    from ipdb._sources.greensnow import GreensnowSource
    raw = tmp_path / "greensnow.txt"
    raw.write_text("1.2.3.4\n5.6.7.8\n")
    src = GreensnowSource(tmp_path)

    class UnknownSource:
        """失败注入:子进程 registry 里没有此名 → rc 2;父进程侧的
        rebuild/load 均不得被触达。"""
        name = "no_such_source_zz"
        download_host = None

        def __init__(self):
            self._path = raw                # 存在即可:rebuild-only 跳过下载

        def rebuild(self):
            raise AssertionError("rc!=0 路径不得调用父进程 rebuild")

        def load(self):
            raise AssertionError("rc!=0 不得走到父进程 load()")

    mgr = _make_manager({"greensnow": src,
                         "no_such_source_zz": UnknownSource()})
    base = tmp_path / "greensnow.txt.lmdb"

    task = mgr.enqueue_one_detached("greensnow", rebuild_only=True)
    assert _wait_terminal(mgr, task) == "done"
    ptr1 = read_ptr(base)
    assert ptr1 is not None                  # tmp 下 ptr sidecar 出现
    assert src._count == 2                   # 父进程已重同步到新 epoch

    # raw 内容前进 + mtime 显式后移(防文件系统时间粒度把族级增量
    # needs_convert 判成已收敛而跳过重建)
    raw.write_text("1.2.3.4\n5.6.7.8\n9.9.9.9\n")
    fut = time.time() + 10
    os.utime(raw, (fut, fut))
    task2 = mgr.enqueue_one_detached("greensnow", rebuild_only=True)
    assert _wait_terminal(mgr, task2) == "done"
    assert read_ptr(base) > ptr1             # ptr 推进(子进程换新 epoch)
    assert src._count == 3

    bad = mgr.enqueue_one_detached("no_such_source_zz", rebuild_only=True)
    assert _wait_terminal(mgr, bad) == "failed"
    assert bad.error                         # stderr 尾部非空
    assert bad.error_code == "rebuild"       # 子进程车道构建失败码(2026-10-17 裁定)


def test_child_infra_exclusion_log_survives_lanes(tmp_path, monkeypatch, caplog):
    """issue #183 排除留痕在两条 rebuild 车道都可见:
    - 子进程车道:child basicConfig(INFO)→ stderr 带 infra noise filter 行
      (否则 logger.info 落 lastResort(WARNING+)之下,生产容器永不可见);
    - 父进程成功路径:stderr 人类可读行转发父 logger.info(原先只在失败
      尾摘 300 字,成功即丢)。
    源选 myip_ms:事故源之一(infra_noise_filter=True)。"""
    import logging as _logging
    import subprocess as _sp
    import sys as _sys
    from ipdb._sources.myip_ms import MyipMsSource
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    raw = tmp_path / "myip_ms"
    raw.write_text("8.8.8.8\n203.0.113.7\n")

    # 子进程车道:排除计数日志随 stderr 落地(关不掉的审计面)
    r = _sp.run([_sys.executable, "-m", "ipdb._rebuild_child", "myip_ms"],
                cwd=str(BACKEND), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-400:]
    assert "OK 1" in r.stdout                    # 8.8.8.8 载入面被排
    assert "infra noise filter" in r.stderr
    assert "8.8.8.8/32" in r.stderr

    # 父进程车道:成功路径的 stderr 行转发到父 logger(容器日志面)
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    src = MyipMsSource(tmp_path)
    mgr = _make_manager({"myip_ms": src})
    fut = time.time() + 10
    os.utime(raw, (fut, fut))                    # 族级增量:mtime 前移再重建
    with caplog.at_level(_logging.INFO, logger="ipdb._tasks"):
        task = mgr.enqueue_one_detached("myip_ms", rebuild_only=True)
        assert _wait_terminal(mgr, task) == "done"
    assert any("infra noise filter" in rec.getMessage() and "myip_ms" in
               rec.getMessage() for rec in caplog.records)
    assert src._count == 1
