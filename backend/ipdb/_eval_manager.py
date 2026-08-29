"""eval 子进程单槽管理器(spec 2026-08-28 §5.2)。
eval 消融会改内存 _disabled——必须子进程隔离,永不触碰主进程状态。"""
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent   # backend/


class EvalBusyError(RuntimeError):
    def __init__(self, running_source):
        super().__init__(f"eval already running: {running_source}")
        self.running_source = running_source


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EvalManager:
    def __init__(self, timeout_s: int = 1800):
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._timeout = timeout_s

    @property
    def current(self) -> dict | None:
        return self._current

    def run(self, source: str) -> dict:
        with self._lock:
            if self._current and self._current["state"] == "running":
                raise EvalBusyError(self._current["source"])
            job = {"job_id": uuid.uuid4().hex[:12], "source": source,
                   "state": "running", "started_at": _now(), "error": None}
            self._current = job
        threading.Thread(target=self._wait, args=(job,), daemon=True).start()
        return job

    def _wait(self, job: dict) -> None:
        try:
            p = subprocess.Popen(
                [sys.executable, "-m", "ipdb._eval", job["source"], "--json"],
                cwd=str(_BACKEND_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                out, err = p.communicate(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                job["state"], job["error"] = "failed", "timeout"
                return
            if p.returncode == 0:
                job["state"] = "done"
            else:
                job["state"] = "failed"
                job["error"] = (err or out or "").strip()[-500:] or f"exit {p.returncode}"
        except Exception as e:
            job["state"], job["error"] = "failed", str(e)[:500]
