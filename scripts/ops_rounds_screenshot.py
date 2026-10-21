# 票 #148 验收截屏脚本:轮次子 tab 全页(驾驶舱单卡 + 过往轮次表)。
# 纯前端 mock 面:dist 静态服务 + /api/* 路由拦截(台账/包/任务快照),
# 不起后端。产出 工作树根 ops-rounds-t148.png(不提交,报告路径)。
import json
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
PORT = 4178
OUT = Path(__file__).resolve().parents[1] / "ops-rounds-t148.png"

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

FAILED_TASK = {
    "id": "t9", "source": "ops", "host": None, "state": "failed",
    "error": "模型失败面 stopReason=error:401 {\"code\":\"401\",\"message\":\"令牌已过期或验证不正确\"}",
    "error_code": "model_face", "batch_id": None,
}

VERSION = {
    "current": "g148-mock", "latest": None, "update_available": False, "summary": None,
    "release_url": "", "self_update_enabled": False, "public_demo": False,
}


def handle_api(route):
    path = route.request.url.split("?")[0].split("/api", 1)[1]
    if path == "/users/me":
        return route.fulfill(content_type="application/json", body=json.dumps({"id": "u1", "email": "admin@ipradar.local"}))
    if path == "/tasks":
        return route.fulfill(content_type="application/json", body=json.dumps({"tasks": [FAILED_TASK], "batch": None}))
    if path == "/events":
        return route.fulfill(content_type="text/event-stream", body="")
    if path == "/ops/ledger":
        return route.fulfill(content_type="text/markdown", body=LEDGER)
    if path == "/ops/packages":
        return route.fulfill(content_type="application/json", body=json.dumps(PKGS))
    if path == "/ops/precedents":
        return route.fulfill(content_type="application/json", body=json.dumps(["2026-10-19-ustc-myip-incremental-queue-signoff.md"]))
    if path == "/version":
        return route.fulfill(content_type="application/json", body=json.dumps(VERSION))
    # 默认壳层(SourcesPage 默认 tab)最小合法形状:空表/空列,防 React 树崩
    if path == "/sources":
        return route.fulfill(content_type="application/json", body="[]")
    if path == "/eval/model":
        return route.fulfill(content_type="application/json", body=json.dumps({"latest": None}))
    if path == "/admin/tokens":
        return route.fulfill(content_type="application/json", body="[]")
    return route.fulfill(content_type="application/json", body="{}")


handler = partial(SimpleHTTPRequestHandler, directory=str(DIST))
httpd = HTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.route("**/api/**", handle_api)
    page.add_init_script("localStorage.setItem('iplookup.locale', 'zh-CN')")
    page.goto(f"http://127.0.0.1:{PORT}/admin.html")
    page.wait_for_selector("[role=tab]")  # 壳层稳定(StrictMode 双渲染消停)
    page.wait_for_timeout(300)
    page.get_by_role("tab", name="运营").click(timeout=5000)
    page.get_by_role("tab", name="轮次").click(timeout=5000)
    page.get_by_text("原始信封").click(timeout=8000)  # 展开原始信封(证据不灭失面入镜)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    body_text = page.inner_text("body")
    assert "上游令牌过期" in body_text, "人话化错误未渲染:" + body_text[:600]
    page.screenshot(path=str(OUT), full_page=True)
    print("saved:", OUT)
    browser.close()
httpd.shutdown()
