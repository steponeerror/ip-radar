# ops_screenshot_common.py — 运营面验收截屏共享骨架(终审 standards 重构:
# ops_rounds_screenshot / ops_archive_screenshot 两脚本 ~70 行逐字重复的
# LEDGER/PKGS 夹具 + /api/* 路由拦截 + VERSION + dist 静态服务收编于此;
# ops_settings_screenshot(#150)同源复用)。范式:纯前端 mock 面——dist 静态
# 服务 + /api/* 路由拦截,不起后端;产物 png 落工作树根不入仓。
import json
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

# 台账夹具:含 T4 冻结表头 + 数据行(spawn 失败行 + tools 收通行)
LEDGER = "\n".join([
    "# 运营轮次台账",
    "",
    "| 日期 | 轮次 | model | 用量 | 备注 |",
    "|---|---|---|---|---|",
    "| 2026-10-18 | health | glm-5.3-flash | in=3076 out=854 total=3930 cost=0.00095 | tools=1 sdk=pi-agent-core |",
    "| 2026-10-19 | health | — | — | spawn error_code=model_face |",
    "| 2026-10-20 | health | — | — | spawn error_code=model_face |",
    "| 2026-10-20 | health | glm-5.3-flash | in=3076 out=854 total=3930 cost=0.00095368 | tools=1 sdk=pi-agent-core |",
    "| 2026-10-21 | discover | — | — | spawn error_code=model_face; pkg=2026-10-21-discover-0902.md |",
])

PKGS = [
    {"name": "2026-10-18-health-1126.md", "size": 3272, "modified": "2026-10-18T11:26:08Z"},
    {"name": "2026-10-20-health-1126.md", "size": 3272, "modified": "2026-10-20T11:26:08Z"},
    {"name": "2026-10-21-discover-0902.md", "size": 5120, "modified": "2026-10-21T09:02:44Z"},
    {"name": "2026-10-21-health-1540.md", "size": 2988, "modified": "2026-10-21T15:40:12Z"},
]

VERSION = {
    "current": "ops-visual-mock", "latest": None, "update_available": False,
    "summary": None, "release_url": "", "self_update_enabled": False, "public_demo": False,
}

# 默认路由表:壳层(登录/任务/事件/版本/源/eval/token)最小合法形状,防
# React 树崩 + 运营面空基线。值 = JSON 可序列化对象;未知路径兜底 {}。
_DEFAULTS = {
    "/users/me": {"id": "u1", "email": "admin@ipradar.local"},
    "/tasks": {"tasks": [], "batch": None},
    "/ops/ledger": {"text": LEDGER},
    "/ops/packages": {"packages": PKGS},
    "/ops/precedents": {"precedents": []},
    "/version": VERSION,
    "/sources": [],
    "/eval/model": {"latest": None},
    "/admin/tokens": [],
}


def build_handle_api(overrides=None):
    """构建 /api/* 拦截器。overrides = {path: JSON 可序列化值 | 零参 callable
    → 值};callable 支持脚本运行中翻态(如 #150 零配置变体换 GET 响应)。
    出参形状对齐后端:_ops_store 的 OpsFileTextOut({text})/OpsPackagesOut
    ({packages})/OpsPrecedentsOut({precedents})——裸 markdown/裸数组不是合法
    JSON,前端 jsonOrThrow 解析即抛(#149 修,勿回退)。/events 固定空 SSE 流。
    """
    routes = {**_DEFAULTS, **(overrides or {})}

    def handle_api(route):
        path = route.request.url.split("?")[0].split("/api", 1)[1]
        if path == "/events":
            return route.fulfill(content_type="text/event-stream", body="")
        spec = routes.get(path)
        if spec is None:
            spec = {}
        body = spec() if callable(spec) else spec
        return route.fulfill(content_type="application/json", body=json.dumps(body))

    return handle_api


def serve_dist(port):
    """dist 静态服务(后台线程);返回 httpd,收尾 httpd.shutdown()。"""
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST))
    httpd = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def open_admin(playwright, port, handle_api):
    """启动浏览器 → locale zh-CN → 进 admin 壳 → 点「运营」一级 tab。
    返回 (browser, page);收尾 browser.close()。子 tab 导航归各脚本自持。
    """
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.route("**/api/**", handle_api)
    page.add_init_script("localStorage.setItem('iplookup.locale', 'zh-CN')")
    page.goto(f"http://127.0.0.1:{port}/admin.html")
    page.wait_for_selector("[role=tab]")  # 壳层稳定(StrictMode 双渲染消停)
    page.wait_for_timeout(300)
    page.get_by_role("tab", name="运营").click(timeout=5000)
    return browser, page


__all__ = [
    "LEDGER", "PKGS", "VERSION", "build_handle_api", "serve_dist", "open_admin",
    "sync_playwright",
]
