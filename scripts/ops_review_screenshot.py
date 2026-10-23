# 票 #157 验收截屏脚本(P1 审阅面):「审阅」子 tab 三图——满态 active 行
# 展开态(四键后果文案入图)+ 终态行展开态(无四键图证)+ --empty 空态对照
# (硬规⑥)。纯前端 mock 面(共享骨架 = ops_screenshot_common,t149 范式),
# 不起后端;产物 png 落工作树根不入仓。契约真源 = GET /api/ops/items →
# OpsItemsOut({items});行形状 = OpsItemOut 十字段 + modified。
# 手风琴单开模型:断言序 = active 展开→四键→截图;sblam 终态展开→四键
# 归零+详情可见→截图(视觉门 Finding 1/2 修复:钮面断言不被页头提示语
# 误满足,b/c 两项图证齐)。
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

if EMPTY:
    OVERRIDES = {"/version": {**VERSION, "current": "g157-mock"},
                 "/ops/items": {"items": []}}
else:
    OVERRIDES = {"/version": {**VERSION, "current": "g157-mock"},
                 "/ops/items": {"items": ITEMS}}
handle_api = build_handle_api(OVERRIDES)

httpd = serve_dist(PORT)
with sync_playwright() as p:
    browser, page = open_admin(p, PORT, handle_api)
    page.get_by_role("tab", name="审阅").click(timeout=5000)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    if EMPTY:
        assert "暂无" in page.inner_text("body"), "空态必须显基准「暂无」提示(硬规⑥)"
    else:
        # active 行展开:四键后果文案入图入断言(钮面级,非页头提示语)
        page.get_by_role("button", name="spamhaus_drop").first.click()
        page.wait_for_timeout(200)
        for label, n in (("同意·执行", 1), ("修改", 1), ("忽略", 1), ("稍后", 2)):
            got = page.get_by_role("button", name=label).count()
            assert got == n, f"展开态按钮面不符:{label} 期望 {n} 实得 {got}"
        page.screenshot(path=str(OUT), full_page=True)
        # 终态行展开:详情可见 + 四键全零(手风琴单开,active 面已收)
        page.get_by_role("button", name="sblam").first.click()
        page.wait_for_timeout(200)
        assert "已自愈" in page.inner_text("body"), "终态行展开后详情可见"
        for label in ("同意·执行", "修改", "忽略", "稍后"):
            assert page.get_by_role("button", name=label).count() == 0, \
                f"终态行不得渲染四键:{label} 实得非零"
        out_done = OUT.with_name(OUT.name.replace("-t157", "-t157-done"))
        page.screenshot(path=str(out_done), full_page=True)
    if EMPTY:
        page.screenshot(path=str(OUT), full_page=True)
    browser.close()
httpd.shutdown()
print(f"OK {OUT}")
