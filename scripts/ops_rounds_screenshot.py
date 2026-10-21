# 票 #148 验收截屏脚本:轮次子 tab 全页(驾驶舱单卡 + 过往轮次表)。
# 纯前端 mock 面(共享骨架 = ops_screenshot_common),不起后端。
# 产出 工作树根 ops-rounds-t148.png(不提交,报告路径)。
from pathlib import Path

from ops_screenshot_common import VERSION, build_handle_api, open_admin, serve_dist, sync_playwright

PORT = 4178
OUT = Path(__file__).resolve().parents[1] / "ops-rounds-t148.png"

# 轮次态夹具:失败任务在飞历史(上一轮结果卡走内存失败面——人话化错误 +
# 可展开原始信封的验收面)
FAILED_TASK = {
    "id": "t9", "source": "ops", "host": None, "state": "failed",
    "error": "模型失败面 stopReason=error:401 {\"code\":\"401\",\"message\":\"令牌已过期或验证不正确\"}",
    "error_code": "model_face", "batch_id": None,
}

handle_api = build_handle_api({
    "/version": {**VERSION, "current": "g148-mock"},
    "/tasks": {"tasks": [FAILED_TASK], "batch": None},
    "/ops/precedents": {"precedents": ["2026-10-19-ustc-myip-incremental-queue-signoff.md"]},
})

httpd = serve_dist(PORT)
with sync_playwright() as p:
    browser, page = open_admin(p, PORT, handle_api)
    page.get_by_role("tab", name="轮次").click(timeout=5000)
    page.get_by_text("原始信封").click(timeout=8000)  # 展开原始信封(证据不灭失面入镜)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    body_text = page.inner_text("body")
    assert "上游令牌过期" in body_text, "人话化错误未渲染:" + body_text[:600]
    # 视觉门 2026-10-21 低2:轮次表用量列人话化(mono 轨;title 挂台账原始串)
    assert "in 3076 · out 854 · 计 3930" in body_text, "用量人话化未渲染:" + body_text[:600]
    page.screenshot(path=str(OUT), full_page=True)
    print("saved:", OUT)
    browser.close()
httpd.shutdown()
