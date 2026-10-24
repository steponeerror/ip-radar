"""一次性重建子进程入口(`IP_RADAR_REBUILD_SUBPROCESS=1` 车道)。

Why(2026-10 小机 RSS 棘轮根修):964MB 演示机上大源 rebuild 在进程内
worker 线程执行,acc dicts + LMDB 写缓冲把堆高水位推上去后 glibc/pymalloc
永不归还 —— app 进程 anon 内存棘轮到 ~540MB(RSS 222 + swap 318)。重建
挪进一次性子进程,进程退出即把全部内存归还 OS。

协议(父进程 `ipdb._tasks.UpdateManager._rebuild_via_subprocess` 逐行解析,
格式勿改):
    stdout  "PROG <received> <total>"   进度(时间节流 ≥0.15s 或终值)
    stdout  "OK <count>"                成功,随后 exit 0
    stderr  人类可读诊断(traceback / 未知名),失败时父进程取尾部入 error
    rc      0 成功 | 1 rebuild 异常(traceback 已落 stderr)| 2 源名未找到
"""
import inspect
import sys
import time

# 与父进程 _emit_progress 同款节流间隔:SSE 侧已有自己的节流,这里防的
# 是 rebuild 逐行高频回调把 stdout 管道淹没。
_PROG_INTERVAL_S = 0.15


def _main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m ipdb._rebuild_child <source_name>",
              file=sys.stderr, flush=True)
        return 2
    # stderr 除 traceback 外也是人类可读日志面:载入期排除留痕
    # (issue #183 infra noise filter 计数)是 INFO 级,不配置会落
    # lastResort(WARNING+)之下不可见;父进程成功路径会把 stderr 行转发
    # 到容器日志(见 _tasks._rebuild_via_subprocess)。
    import logging
    logging.basicConfig(level=logging.INFO)
    # registry 导入只构源对象元数据,不开 LMDB reader;数据目录经继承的
    # IP_RADAR_DATA_DIR 在本进程导入期解析,与父进程同源。
    import ipdb._registry as _registry
    src = _registry._find_source(argv[0])
    if src is None:
        print(f"source not found: {argv[0]}", file=sys.stderr, flush=True)
        return 2

    last_emit = 0.0

    def _progress(received: int, total: int) -> None:
        nonlocal last_emit
        now = time.monotonic()
        finished = total > 0 and received >= total
        if not (finished or now - last_emit >= _PROG_INTERVAL_S):
            return
        last_emit = now
        print(f"PROG {received} {total}", flush=True)

    try:
        # 预检而非 try/except TypeError 回退(同 _run_task:后者会吞 rebuild
        # 内部真实 TypeError)。
        if "progress" in inspect.signature(src.rebuild).parameters:
            count = src.rebuild(progress=_progress)
        else:
            count = src.rebuild()
    except Exception:
        import traceback
        traceback.print_exc()
        return 1
    print(f"OK {count}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
