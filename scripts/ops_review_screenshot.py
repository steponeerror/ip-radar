# 票 #157 验收截屏脚本(P1 审阅面):「审阅」子 tab 三图——满态 active 行
# 展开态(四键后果文案 + <pre> 全文详情入图)+ 终态行展开态(无四键+详情)
# + --empty 空态对照(硬规⑥)。纯前端 mock 面(共享骨架 = ops_screenshot_
# common,t149 范式),不起后端;产物 png 落工作树根不入仓。
# 契约真源:GET /api/ops/items → OpsItemsOut({items});GET /api/ops/items/{id}
# → OpsFileTextOut({text})——详情路由必须 mock,否则面板永挂「加载中…」
# (视觉门二轮 Finding 1);断言用 <pre> 详情独有串(dedup_key/frontmatter
# 键),严禁行摘要已含的串(Finding 2 二犯教训)。
import json
import sys
from pathlib import Path

from ops_screenshot_common import VERSION, build_handle_api, open_admin, serve_dist, sync_playwright

PORT = 4181
EMPTY = "--empty" in sys.argv
SUFFIX = "-empty" if EMPTY else ""
OUT = Path(__file__).resolve().parents[1] / f"ops-review-t157{SUFFIX}.png"

# 满态四行:可逆执行(high)/集外立项(medium)/可逆低危(low)/终态 done(无键)
ITEMS = [
    {"id": "2026-10-23-2f81c0a4d1", "action": "retry_download",
     "args": {"source": "spamhaus_drop"}, "evidence": {"consecutive_failures": 3, "error_code": "HTTP 403"},
     "impact": "spamhaus_drop 数据停更,威胁覆盖面收缩",
     "rollback": "重新触发下载即可恢复;无不可逆变更",
     "dedup_key": "spamhaus_drop|download|http_403_anonymous",
     "severity": "high", "cause_group": "download_failure", "status": "active",
     "modified": "2026-10-23T11:52:09Z"},
    {"id": "2026-10-23-9b04e7c2aa", "action": "refresh_source",
     "args": {"source": "cn_isp"}, "evidence": {"content_age_h": 172, "period_h": 168},
     "impact": "cn_isp 内容年龄超 2× 刷新周期,地理标注可能过期",
     "rollback": "重新拉取即恢复;无不可逆变更",
     "dedup_key": "cn_isp|staleness|age_gt_2x_refresh",
     "severity": "medium", "cause_group": "staleness", "status": "active",
     "modified": "2026-10-23T11:07:44Z"},
    {"id": "2026-10-23-5c19a3f6be", "action": "disable_source",
     "args": {"source": "threatview_c2"}, "evidence": {"consecutive_failures": 2, "error_code": "HTTP 404"},
     "impact": "threatview_c2 间歇 404,建议暂停观察",
     "rollback": "源页重新启用即恢复",
     "dedup_key": "threatview_c2|download|http_404",
     "severity": "low", "cause_group": "download_failure", "status": "active",
     "modified": "2026-10-22T18:30:00Z"},
    {"id": "2026-10-22-7d33f8a1c0", "action": "retry_download",
     "args": {"source": "sblam"}, "evidence": {"consecutive_failures": 1, "error_code": "timeout"},
     "impact": "sblam 单次超时已自愈",
     "rollback": "—",
     "dedup_key": "sblam|download|timeout",
     "severity": "low", "cause_group": "download_failure", "status": "done",
     "modified": "2026-10-22T09:12:31Z"},
]


def _detail(it):
    """OpsFileTextOut({text}) 形状;详情 = 条目全文逐字(证据不灭失),
    含 args/evidence/impact/rollback(形状对拍 OpsReviewSection.test.tsx)。"""
    lines = [
        "---",
        f"action: {it['action']}",
        f"args: {json.dumps(it['args'], ensure_ascii=False)}",
        f"evidence: {json.dumps(it['evidence'], ensure_ascii=False)}",
        f"impact: {it['impact']}",
        f"rollback: {it['rollback']}",
        f"dedup_key: {it['dedup_key']}",
        f"severity: {it['severity']}",
        f"cause_group: {it['cause_group']}",
        f"status: {it['status']}",
        "---", "",
        f"# 待审:{it['args']['source']}", "",
        f"{it['impact']};{it['rollback']}。", "",
    ]
    return {"text": "\n".join(lines)}


DETAIL_ROUTES = {f"/ops/items/{it['id']}": _detail(it) for it in ITEMS}

if EMPTY:
    OVERRIDES = {"/version": {**VERSION, "current": "g157-mock"},
                 "/ops/items": {"items": []}}
else:
    OVERRIDES = {"/version": {**VERSION, "current": "g157-mock"},
                 "/ops/items": {"items": ITEMS}, **DETAIL_ROUTES}
handle_api = build_handle_api(OVERRIDES)

httpd = serve_dist(PORT)
with sync_playwright() as p:
    browser, page = open_admin(p, PORT, handle_api)
    page.get_by_role("tab", name="审阅").click(timeout=5000)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    if EMPTY:
        assert "暂无" in page.inner_text("body"), "空态必须显基准「暂无」提示(硬规⑥)"
        page.screenshot(path=str(OUT), full_page=True)
    else:
        # active 行展开:详情 <pre> 就位(路由命中,不挂加载中)+ 四键钮面断言
        page.get_by_role("button", name="spamhaus_drop").first.click()
        page.wait_for_selector("pre", timeout=5000)
        for label, n in (("同意·执行", 1), ("修改", 1), ("忽略", 1), ("稍后", 2)):
            got = page.get_by_role("button", name=label).count()
            assert got == n, f"展开态按钮面不符:{label} 期望 {n} 实得 {got}"
        detail = page.locator("pre").inner_text()
        assert "rollback: 重新触发下载即可恢复" in detail, "详情独有串(frontmatter 键)必须命中"
        assert "spamhaus_drop|download|http_403_anonymous" in detail
        page.screenshot(path=str(OUT), full_page=True)
        # 终态行展开(手风琴单开,active 面已收):详情可见 + 四键全零
        page.get_by_role("button", name="sblam").first.click()
        page.wait_for_selector("pre", timeout=5000)
        for label in ("同意·执行", "修改", "忽略", "稍后"):
            assert page.get_by_role("button", name=label).count() == 0, \
                f"终态行不得渲染四键:{label} 实得非零"
        detail2 = page.locator("pre").inner_text()
        assert "sblam|download|timeout" in detail2, "终态详情独有串(dedup_key)必须命中"
        out_done = OUT.with_name(OUT.name.replace("-t157", "-t157-done"))
        page.screenshot(path=str(out_done), full_page=True)
    browser.close()
httpd.shutdown()
print(f"OK {OUT}")
