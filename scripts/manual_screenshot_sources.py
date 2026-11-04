# manual_screenshot_sources.py — MANUAL 图 04(admin Sources tab)重拍器(2026-11-03 立,
# 挂账来源:#285 peeringdb 退役后旧图仍 61 源实例)。
# 范式与 ops_*_screenshot 同源(ops_screenshot_common:dist 静态服务 + /api/* 拦截,
# 不起后端),差异:①夹具 = 活服务器 /api/sources 真值(不造数据,重拍之日从
# demo 服务器拉当日真值,见 --payload);②进「源管理」一级 tab(非运营);
# ③full_page 落 assets/manual/04-admin-sources.png(入仓,区别于 ops 图的
# assets/verification 不入仓——放置规范 2026-10-28)。
# 用法:python3 scripts/manual_screenshot_sources.py --payload /tmp/sources.json
#   payload 取法(容器 env 直发,勿从 override 字面抠——插值差异判例 2026-11-03):
#   ssh root@203.88.124.85 'cd /opt/ip-lookup-tool && docker compose exec -T ipradar \
#     sh -c "curl -s -X POST http://127.0.0.1:8000/api/auth/jwt/login -H \
#     \"Content-Type: application/x-www-form-urlencoded\" -d \
#     \"username=admin@ipradar.local&password=\$IP_RADAR_ADMIN_PASSWORD\" -c /tmp/cj.txt && \
#     curl -s http://127.0.0.1:8000/api/sources -b /tmp/cj.txt"' | tail -n +2 > /tmp/sources.json
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from ops_screenshot_common import build_handle_api, serve_dist

OUT = Path(__file__).resolve().parents[1] / "assets" / "manual" / "04-admin-sources.png"
PORT = 8791


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True, help="/api/sources 真值 JSON 路径")
    args = ap.parse_args()
    sources = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    if not isinstance(sources, list) or not sources:
        raise SystemExit("payload 应为非空 /api/sources 数组")
    print(f"fixture: {len(sources)} sources")

    httpd = serve_dist(PORT)
    handle = build_handle_api(overrides={"/sources": sources})
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/**", handle)
            page.add_init_script(
                "localStorage.setItem('iplookup.locale', 'zh-CN')")
            page.goto(f"http://127.0.0.1:{PORT}/admin.html")
            page.wait_for_selector("[role=tab]")
            page.wait_for_timeout(300)
            page.get_by_role("tab", name="源管理").click(timeout=5000)
            # 旧图(2533×3260)是全组展开的逐源长图;组默认折叠,先点开再拍。
            # 断言:展开后页面里须出现首个源名(abuseipdb),防空图静默(2026-11-03
            # 重拍实弹:折叠态下 names_rendered=0,33KB 空图溜过首版)。
            page.wait_for_timeout(800)
            # 组头 = button[aria-controls^=sources-group-](探测实证;每源行另有
            # 自己的 [aria-expanded] 详情折叠,勿用该属性泛点——首版实弹乱开行折叠)。
            groups = page.locator("button[aria-controls^='sources-group-']")
            for i in range(groups.count()):
                g = groups.nth(i)
                if g.get_attribute("aria-expanded") != "true":
                    g.click()
                    page.wait_for_timeout(300)
            page.wait_for_timeout(1500)
            body = page.inner_text("body")
            rendered = sum(1 for s in sources if s["name"] in body)
            print(f"rows_rendered: {rendered}/{len(sources)}")
            if rendered < len(sources):
                raise SystemExit(f"源行渲染不全({rendered}/{len(sources)}),拒绝出图")
            page.screenshot(path=str(OUT), full_page=True)
            browser.close()
        print(f"saved: {OUT} ({OUT.stat().st_size} bytes)")
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
