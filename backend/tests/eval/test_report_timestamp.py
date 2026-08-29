"""write_report 秒级时间戳防同日覆盖(spec 2026-08-28 §5.2 修正:历史自然累积)。"""
import datetime as _real_dt
import types
from types import SimpleNamespace

from ipdb._eval import report as rpt


def test_second_level_timestamp_two_runs_no_overwrite(tmp_path, monkeypatch):
    """同一 source 连续两次 write_report → 4 个独立文件(json/md 各 2),互不覆盖。

    monkeypatch 模块级 _dt(非全局 datetime),now() 两次返回不同秒。"""
    calls = {"n": 0}

    class _FakeNow:
        def strftime(self, fmt):                      # 只需产出唯一串;fmt 不校验
            return f"20260828-1300{calls['n']:02d}"

        def date(self):
            class _D:
                def isoformat(self):
                    return "2026-08-28"               # render_json 的 generated_at 保持 date 粒度
            return _D()

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
            calls["n"] += 1
            return _FakeNow()

    monkeypatch.setattr(rpt, "_dt", types.SimpleNamespace(
        datetime=_FakeDateTime, timezone=_real_dt.timezone))

    verdict = SimpleNamespace(state="POSITIVE-VERIFIED", benefit_high=True,
                              cost_high=False, verified=True, insufficient=False,
                              suspicion_flags=[], action="keep")
    metrics = {"MC": SimpleNamespace(value=0.1, n=5)}

    md1, js1 = rpt.write_report("spamhaus", verdict, metrics, SimpleNamespace(), tmp_path)
    md2, js2 = rpt.write_report("spamhaus", verdict, metrics, SimpleNamespace(), tmp_path)

    assert js1 != js2 and md1 != md2
    assert js1.name.startswith("spamhaus-2026")
    assert len(list(tmp_path.glob("spamhaus-*.json"))) == 2
    assert len(list(tmp_path.glob("spamhaus-*.md"))) == 2
