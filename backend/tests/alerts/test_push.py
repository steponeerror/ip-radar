# backend/tests/alerts/test_push.py — Task 3:push() apprise 推送出口
"""env 空不 import、URL 分隔解析、add/notify 透传与异常吞噬(约束 5)。

fake 注入走 monkeypatch.setitem(sys.modules, "apprise", fake)(测完自动
还原),不真装 apprise、不出网;calls 记录构造数/add 的 URL/notify 的
(title, body),既是断言依据也是「env 空 → 未 import」的计数核
(未 import 则 Apprise 从未构造)。notify 可配置返回值或抛异常。
"""
import sys
import types

import pytest


def _fake_apprise(add_result=True, notify_result=True, notify_exc=None):
    """造注入用 fake apprise 模块;add_result 可为 bool 或 url->bool。"""
    calls = {"constructs": 0, "adds": [], "notifies": []}
    mod = types.ModuleType("apprise")

    class _FakeApprise:
        def __init__(self):
            calls["constructs"] += 1

        def add(self, url):
            calls["adds"].append(url)
            return add_result(url) if callable(add_result) else add_result

        def notify(self, *, title=None, body=None):
            calls["notifies"].append((title, body))
            if notify_exc is not None:
                raise notify_exc
            return notify_result

    mod.Apprise = _FakeApprise
    return mod, calls


@pytest.fixture()
def inject(monkeypatch):
    """注入 fake apprise 到 sys.modules;还原由 monkeypatch 兜底。"""
    def _inject(**kwargs):
        mod, calls = _fake_apprise(**kwargs)
        monkeypatch.setitem(sys.modules, "apprise", mod)
        return calls
    return _inject


def test_env_unset_returns_false_without_import(monkeypatch):
    # 未设 → False 且 sys.modules 无 apprise 导入痕迹(清场后仍无)
    monkeypatch.delenv("IP_RADAR_ALERT_URLS", raising=False)
    monkeypatch.delitem(sys.modules, "apprise", raising=False)
    from ipdb import _alerts
    assert _alerts.push("ipradar: 1 源异常", "x") is False
    assert "apprise" not in sys.modules


@pytest.mark.parametrize("blank", ["", "   ", ",", " , , "])
def test_env_blank_returns_false_no_construct(monkeypatch, inject, blank):
    # 空白/纯逗号 = 空 → False,Apprise 从未构造(fake 计数核)
    monkeypatch.setenv("IP_RADAR_ALERT_URLS", blank)
    calls = inject()
    from ipdb import _alerts
    assert _alerts.push("t", "b") is False
    assert calls["constructs"] == 0


def test_single_url_adds_and_notifies(monkeypatch, inject):
    monkeypatch.setenv("IP_RADAR_ALERT_URLS", "lark://token")
    calls = inject()
    from ipdb import _alerts
    assert _alerts.push("标题", "正文") is True
    assert calls["adds"] == ["lark://token"]
    assert calls["notifies"] == [("标题", "正文")]  # notify 收 keyword 实参


def test_mixed_separator_urls_all_added(monkeypatch, inject):
    # 逗号 + 空格混合分隔 → 逐个 add,顺序保持
    monkeypatch.setenv("IP_RADAR_ALERT_URLS",
                       "lark://a, gotify://b  mailto://c,dashboard://d")
    calls = inject()
    from ipdb import _alerts
    assert _alerts.push("t", "b") is True
    assert calls["adds"] == ["lark://a", "gotify://b",
                             "mailto://c", "dashboard://d"]


def test_notify_false_passthrough(monkeypatch, inject):
    monkeypatch.setenv("IP_RADAR_ALERT_URLS", "lark://token")
    calls = inject(notify_result=False)
    from ipdb import _alerts
    assert _alerts.push("t", "b") is False
    assert calls["notifies"] == [("t", "b")]


def test_notify_raise_swallowed(monkeypatch, inject):
    # notify 抛异常 → warning 吞掉,push 返回 False 不抛(守护线程红线)
    monkeypatch.setenv("IP_RADAR_ALERT_URLS", "lorkts://dead")
    calls = inject(notify_exc=RuntimeError("network down"))
    from ipdb import _alerts
    assert _alerts.push("t", "b") is False


def test_import_failure_returns_false(monkeypatch):
    # sys.modules["apprise"] = None → import 即 ImportError → 吞掉返回 False
    monkeypatch.setenv("IP_RADAR_ALERT_URLS", "lark://token")
    monkeypatch.setitem(sys.modules, "apprise", None)
    from ipdb import _alerts
    assert _alerts.push("t", "b") is False


def test_failed_add_skipped_others_still_notified(monkeypatch, inject):
    monkeypatch.setenv("IP_RADAR_ALERT_URLS",
                       "good://a bad://x good://b")
    calls = inject(add_result=lambda url: not url.startswith("bad://"))
    from ipdb import _alerts
    assert _alerts.push("t", "b") is True
    # 三个都尝试 add;坏 URL 只是跳过,notify 仍对其余发出
    assert calls["adds"] == ["good://a", "bad://x", "good://b"]
    assert calls["notifies"] == [("t", "b")]
