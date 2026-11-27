"""Rebuild 子进程隔离(IP_RADAR_REBUILD_SUBPROCESS)三场景。

- 默认 off:rebuild-only 任务走原 in-process 路径(位等价约束)。
- 子进程 E2E:`python -m ipdb._rebuild_child greensnow` 对 tmp 数据目录
  重建 → rc 0 + OK 行 + ptr sidecar。
- 父进程开关:manager 走子进程车道 → done + ptr 推进;未知源名 rc 2 →
  failed 且 error 非空。

取消路径不做时序测试(terminate 与子进程写管道的竞态复杂度过高,
见任务报告);记账语义由 _run_task 共享尾巴保证,与 in-process 取消同路。
↑ 这段指本文件前三个原始场景;下方 #478 新增场景用 Popen 拦截注入假
子进程,取消/停顿/读事故都有时序断言(返工评审建议 9 的口径澄清)。
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


# ── #478:停顿超时 + 随时可取消 ──
# 子进程命令硬编码 `python -m ipdb._rebuild_child <name>`,子进程 registry
# 是固定名册,测试进程没法向子进程注入假源 —— 假子进程在 Popen 层拦:
# 命中 rebuild-child 命令形状的调用换成测试给的 argv,其余透传(测试
# 进程里其它 subprocess 用户不受影响)。拦截器必须在打补丁前抓真 Popen。
_real_popen = subprocess.Popen


class _PopenIntercept:
    def __init__(self, child_argv):
        self._child_argv = child_argv
        self.proc = None

    def __call__(self, argv, **kwargs):
        if argv[1:3] == ["-m", "ipdb._rebuild_child"]:
            self.proc = _real_popen(self._child_argv, **kwargs)
            return self.proc
        return _real_popen(argv, **kwargs)


class _QuietSrc:
    """父进程侧源对象:子进程车道里 rebuild/load 都不该被触达
    (failed/cancelled 都在 load() 之前收口)。_path 必须存在 ——
    rebuild-only 车道 raw 缺失会回退 download。"""
    name = "quiet_src"
    download_host = None

    def __init__(self, path):
        self._path = path

    def rebuild(self):
        raise AssertionError("子进程车道父进程 rebuild 不得被调")

    def load(self):
        raise AssertionError("非成功路径不得走到父进程 load()")


_SILENT_CHILD = "import time; time.sleep(600)"
# 输出不停的孩子:每 0.2s 一行 PROG,永不自己退出(被 terminate 才死)
_CHATTY_CHILD = (
    "import time\n"
    "for i in range(600):\n"
    "    print(f'PROG {i} 600', flush=True)\n"
    "    time.sleep(0.2)\n"
)


def _wait_loading(mgr, task, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mgr.task_state(task.id) == "loading":
            return True
        time.sleep(0.02)
    return False


def test_stall_timeout_fails_silent_child_and_cleans_staging(
        tmp_path, monkeypatch):
    """假子进程永不出声:IP_RADAR_REBUILD_QUIET_MAX_MIN 是分钟浮点口径
    (返工裁决改名;原 STALL_MIN 撞 _lmdb._stall_budget_s 的
    IP_RADAR_REBUILD_STALL_S 秒口径),测试设 0.02 分 ≈ 1.2s 直达秒级
    阈值 —— 首次 1s 轮询即越过停顿线。子进程先造一个
    <base>.<epoch>.new.<pid> 暂存再睡:failed 后暂存必须被车道定点清掉
    (返工必须改 5)—— 反复停顿每次换 pid 留一个大暂存,原口径要等
    下次成功重建后的 load() 或重启才清,40G 小机盘会被占满。总等待
    上限 10s:变异(去掉停顿段)时本用例超时转红而不是挂死。断言:
    failed、error_code=rebuild(2026-10-17 裁定)、说明有「停顿」、
    子进程已不在、tmp 下无 .new. 残留。"""
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    monkeypatch.setenv("IP_RADAR_REBUILD_QUIET_MAX_MIN", "0.02")
    staging = tmp_path / "greensnow.txt.lmdb.41.new.99999"
    icpt = _PopenIntercept([
        sys.executable, "-c",
        f"import os, time; os.makedirs({str(staging)!r}, exist_ok=True); "
        "time.sleep(600)"])
    monkeypatch.setattr(subprocess, "Popen", icpt)
    raw = tmp_path / "greensnow.txt"
    raw.write_text("x")
    from ipdb._sources.greensnow import GreensnowSource
    mgr = _make_manager({"greensnow": GreensnowSource(tmp_path)})
    task = mgr.enqueue_one_detached("greensnow", rebuild_only=True)
    try:
        deadline = time.monotonic() + 8
        while not staging.exists():
            assert time.monotonic() < deadline, "假子进程未在时限内造出暂存"
            assert mgr.task_state(task.id) not in ("done", "failed",
                                                   "cancelled"), \
                "车道先于暂存创建就终态:阈值相对子进程启动过短"
            assert icpt.proc is None or icpt.proc.poll() is None, \
                "子进程在造出暂存前就死了"
            time.sleep(0.01)
        assert _wait_terminal(mgr, task, timeout=10) == "failed"
        assert task.error_code == "rebuild"
        assert "停顿" in task.error
        assert icpt.proc is not None
        assert icpt.proc.poll() is not None       # 子进程已不在,无残留
        assert not list(tmp_path.glob("*.new.*"))  # 暂存被定点清,无残留
    finally:
        if icpt.proc is not None and icpt.proc.poll() is None:
            icpt.proc.kill()                      # 不给套件留孤儿子进程


def test_cancel_while_silent_within_2s(tmp_path, monkeypatch):
    """安静期取消(#478 主诉求):原实现逐行读才查取消,子进程不出声
    时取消不可达;改后主循环至多每 1 秒看一次。cancel 后 2 秒内变
    cancelled,子进程被结束。STALL_MIN 不设(缺省 60 分),停顿线绝不
    先到 —— 本用例量的是取消通路,与停顿无关。"""
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    monkeypatch.delenv("IP_RADAR_REBUILD_QUIET_MAX_MIN", raising=False)
    icpt = _PopenIntercept([sys.executable, "-c", _SILENT_CHILD])
    monkeypatch.setattr(subprocess, "Popen", icpt)
    raw = tmp_path / "quiet_src.raw"
    raw.write_text("x")
    mgr = _make_manager({"quiet_src": _QuietSrc(raw)})
    task = mgr.enqueue_one_detached("quiet_src", rebuild_only=True)
    assert _wait_loading(mgr, task)
    t0 = time.monotonic()
    mgr.cancel(task.id)
    while mgr.task_state(task.id) != "cancelled":
        assert time.monotonic() - t0 < 2.0, (
            f"cancel 未在 2s 内生效,state={mgr.task_state(task.id)}")
        time.sleep(0.02)
    assert icpt.proc.poll() is not None       # 子进程被结束


def test_cancel_during_output_still_works(tmp_path, monkeypatch):
    """输出途中取消(老路径,#478 重构读循环后照旧绿):假子进程每
    0.2s 发一行 PROG,取消在下一行(≤1s)被看到 → cancelled;PROG 行
    照常驱动进度面。"""
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    monkeypatch.delenv("IP_RADAR_REBUILD_QUIET_MAX_MIN", raising=False)
    icpt = _PopenIntercept([sys.executable, "-c", _CHATTY_CHILD])
    monkeypatch.setattr(subprocess, "Popen", icpt)
    raw = tmp_path / "quiet_src.raw"
    raw.write_text("x")
    mgr = _make_manager({"quiet_src": _QuietSrc(raw)})
    task = mgr.enqueue_one_detached("quiet_src", rebuild_only=True)
    assert _wait_loading(mgr, task)
    deadline = time.monotonic() + 5
    while task.received <= 0:                 # 等 PROG 真到进度面,别赌 sleep
        assert time.monotonic() < deadline, "PROG 行从未到达进度面"
        time.sleep(0.02)
    mgr.cancel(task.id)
    assert _wait_terminal(mgr, task, timeout=5) == "cancelled"
    assert icpt.proc.poll() is not None


def test_quiet_max_threshold_parsing(monkeypatch, caplog):
    """阈值解析直接面(返工必须改 2):未设→缺省 3600s;「1.5」分钟口径
    → 90s;「0」→ None(关掉检查);负数/非数字/NaN → 缺省 + 告警
    (写错的开关不得静默关掉挂死保护;单式比较 not val>=0 把负数和
    NaN 一起判掉 —— NaN 两侧皆假,漏拦会静默落进 nan*60 的永假阈值,
    主会话已实测 max(0.0, float('nan')) == 0.0)。"""
    import logging
    from ipdb import _tasks
    default_s = _tasks._REBUILD_QUIET_MAX_MIN_DEFAULT * 60.0
    cases = [
        (None, default_s, False),   # 未设
        ("1.5", 90.0, False),       # 分钟 → 秒
        ("0", None, False),         # 0 = 关
        ("-5", default_s, True),    # 负数 → 缺省 + 告警
        ("abc", default_s, True),   # 非数字 → 缺省 + 告警
        ("nan", default_s, True),   # NaN → 缺省 + 告警
    ]
    with caplog.at_level(logging.WARNING, logger="ipdb._tasks"):
        for raw, want, want_warn in cases:
            if raw is None:
                monkeypatch.delenv("IP_RADAR_REBUILD_QUIET_MAX_MIN",
                                   raising=False)
            else:
                monkeypatch.setenv("IP_RADAR_REBUILD_QUIET_MAX_MIN", raw)
            got = _tasks._rebuild_quiet_max_s()
            assert got == want, f"env={raw!r}: got {got!r}, want {want!r}"
            warns = [r for r in caplog.records
                     if "IP_RADAR_REBUILD_QUIET_MAX_MIN" in r.getMessage()]
            assert bool(warns) == want_warn, \
                f"env={raw!r}: warn={bool(warns)}, want {want_warn}"
            caplog.clear()


def test_reader_crash_fails_fast(tmp_path, monkeypatch):
    """读事故快速失败(返工必须改 1):读线程里的异常随队列递回主循环,
    立即按 failed 收口(异常文本进 error、子进程被结束),不等停顿阈值
    —— 注入点 = queue.Queue 子类在含 BOOM 的行上 put 抛错,模拟「iter
    迭代中途炸」(encoding/errors=replace 之后真实解码炸已不可能,见
    任务报告 M1 取舍)。"""
    import queue as _queue
    monkeypatch.setenv("IP_RADAR_REBUILD_SUBPROCESS", "1")
    monkeypatch.delenv("IP_RADAR_REBUILD_QUIET_MAX_MIN", raising=False)
    icpt = _PopenIntercept([
        sys.executable, "-c",
        "import time\n"
        "print('hello BOOM line', flush=True)\n"
        "time.sleep(600)\n"])

    class _BoomOnMarkerQueue(_queue.Queue):
        def put(self, item, *a, **k):
            if isinstance(item, str) and "BOOM" in item:
                raise RuntimeError("injected reader crash")
            return super().put(item, *a, **k)

    monkeypatch.setattr(_queue, "Queue", _BoomOnMarkerQueue)
    monkeypatch.setattr(subprocess, "Popen", icpt)
    raw = tmp_path / "quiet_src.raw"
    raw.write_text("x")
    mgr = _make_manager({"quiet_src": _QuietSrc(raw)})
    task = mgr.enqueue_one_detached("quiet_src", rebuild_only=True)
    try:
        assert _wait_terminal(mgr, task, timeout=10) == "failed"
        assert "injected reader crash" in (task.error or "")
        assert task.error_code == "rebuild"
        assert icpt.proc is not None and icpt.proc.poll() is not None
    finally:
        if icpt.proc is not None and icpt.proc.poll() is None:
            icpt.proc.kill()
