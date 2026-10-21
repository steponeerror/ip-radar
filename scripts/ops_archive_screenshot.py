# 票 #149 验收截屏脚本:档案 + 裁决两子 tab 全页(台账统一表/判例行元数据/
# 节头计数/「暂无」空态/裁决包行元数据)。范式复制自 #148 ops_rounds_screenshot.py
# (dist 静态服务 + /api/* mock 拦截,不起后端)。产出工作树根两工件(不提交,
# 报告路径);--empty 变体另出空态对照图(硬规⑥验收面)。
import json
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
PORT = 4179
EMPTY = "--empty" in sys.argv
SUFFIX = "-empty" if EMPTY else ""
OUT_ARCHIVE = Path(__file__).resolve().parents[1] / f"ops-archive-t149{SUFFIX}.png"
OUT_RULINGS = Path(__file__).resolve().parents[1] / f"ops-rulings-t149{SUFFIX}.png"

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

# 判例夹具:文件名日期前缀(行相对时间源)+ 无日期名(不显时间对照)
PRECEDENTS = [
    "2026-10-19-ustc-myip-incremental-queue-signoff.md",
    "2026-10-19-threatview-sunset-dead-feed.md",
    "2026-10-18-sblam-s3-honeypot-methodology.md",
    "2026-10-18-firehol-webserver-unsubscribe.md",
    "2026-10-18-cps-snapshot-paradox.md",
    "2026-10-17-cloudzy-asset-axis-hosting.md",
    "2026-10-17-ziyadnz-aggregator-misjudge.md",
]

VERSION = {
    "current": "g149-mock", "latest": None, "update_available": False, "summary": None,
    "release_url": "", "self_update_enabled": False, "public_demo": False,
}


def handle_api(route):
    path = route.request.url.split("?")[0].split("/api", 1)[1]
    if path == "/users/me":
        return route.fulfill(content_type="application/json", body=json.dumps({"id": "u1", "email": "admin@ipradar.local"}))
    if path == "/tasks":
        return route.fulfill(content_type="application/json", body=json.dumps({"tasks": [], "batch": None}))
    if path == "/events":
        return route.fulfill(content_type="text/event-stream", body="")
    if path == "/ops/ledger":
        # 出参形状 = OpsFileTextOut({text});空态变体仅标题行零数据行
        ledger_md = LEDGER if not EMPTY else "# 运营轮次台账\n"
        return route.fulfill(content_type="application/json", body=json.dumps({"text": ledger_md}))
    if path == "/ops/packages":
        # 出参形状 = OpsPackagesOut({packages})
        return route.fulfill(content_type="application/json", body=json.dumps({"packages": [] if EMPTY else PKGS}))
    if path == "/ops/precedents":
        # 出参形状 = OpsPrecedentsOut({precedents})
        return route.fulfill(content_type="application/json", body=json.dumps({"precedents": [] if EMPTY else PRECEDENTS}))
    if path == "/version":
        return route.fulfill(content_type="application/json", body=json.dumps(VERSION))
    # 默认壳层最小合法形状,防 React 树崩
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

    # 档案子 tab:台账表 + 判例库
    page.get_by_role("tab", name="档案").click(timeout=5000)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    body_text = page.inner_text("body")
    if EMPTY:
        assert "暂无台账记录" in body_text, "台账空态未渲染:" + body_text[:600]
        assert "暂无判例" in body_text, "判例空态未渲染:" + body_text[:600]
        assert "(5)" not in body_text.split("档案", 1)[-1], "空表不应显计数"
    else:
        assert "台账 (5)" in body_text, "台账计数未渲染:" + body_text[:600]
        assert "判例库 (7)" in body_text, "判例计数未渲染:" + body_text[:600]
        assert "天前" in body_text, "判例行相对时间未渲染:" + body_text[:600]
        assert "只读审计面" in body_text, "只读副注未渲染:" + body_text[:600]
        assert "（只读）" not in body_text, "「(只读)」仍在标题"
    page.screenshot(path=str(OUT_ARCHIVE), full_page=True)
    print("saved:", OUT_ARCHIVE)

    # 裁决子 tab:裁决包列表
    page.get_by_role("tab", name="裁决").click(timeout=5000)
    page.wait_for_timeout(400)
    body_text = page.inner_text("body")
    if EMPTY:
        assert "暂无裁决包" in body_text, "裁决包空态未渲染:" + body_text[:600]
    else:
        assert "裁决包 (4)" in body_text, "裁决包计数未渲染:" + body_text[:600]
        assert "小时前" in body_text or "分钟前" in body_text or "天前" in body_text, "包行相对时间未渲染"
    page.screenshot(path=str(OUT_RULINGS), full_page=True)
    print("saved:", OUT_RULINGS)
    browser.close()
httpd.shutdown()
