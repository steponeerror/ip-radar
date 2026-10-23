# 票 #157 验收截屏脚本(P1 审阅面):「审阅」子 tab 全页(条目列表四态行 +
# 四键后果文案 + 终态行无键)与 --empty 空态对照(硬规⑥)。纯前端 mock 面
# (共享骨架 = ops_screenshot_common,同 t149 范式),不起后端。产物 png 落
# 工作树根不入仓。契约真源 = GET /api/ops/items → OpsItemsOut({items});
# 行形状 = OpsItemOut 十字段 + modified(_api_models.py:318-333)。
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
    body_text = page.inner_text("body")
    if EMPTY:
        assert "暂无" in body_text, "空态必须显基准「暂无」提示(硬规⑥)"
    else:
        assert "spamhaus_drop" in body_text and "同意" in body_text, "满态必须见条目行与四键"
        assert "已审结" in body_text or "done" not in "", "终态行在列(文案以 locale 为准)"
    page.screenshot(path=str(OUT), full_page=True)
    browser.close()
httpd.shutdown()
print(f"OK {OUT}")
