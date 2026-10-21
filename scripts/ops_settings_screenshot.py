# 票 #150 验收截屏脚本:设置子 tab(模型配置双下拉 + 参考成本 + 保存全部
# 节级主操作;API 密钥面 = 搜索 + 已配置置顶 + 只写不回显)。纯前端 mock 面
# (共享骨架 = ops_screenshot_common),不起后端。两态各出一工件(不提交,
# 报告路径):①搜索态(默认仅已配置家 → 搜索唤出未配置家,已配置置顶)
# ②零配置态(硬规⑥「暂无」式空态)。
from pathlib import Path

from ops_screenshot_common import VERSION, build_handle_api, open_admin, serve_dist, sync_playwright

PORT = 4180
OUT_SEARCH = Path(__file__).resolve().parents[1] / "ops-settings-t150.png"
OUT_EMPTY = Path(__file__).resolve().parents[1] / "ops-settings-t150-empty.png"

# 目录夹具:两家供应商(zai 已配置带价三型 + openrouter 未配置一型带价),
# 模型行参考成本提示有价/无价(glm-4.6v)对照
CATALOG = {
    "zai-coding-cn": [
        {"id": "glm-5.3", "name": "GLM-5.3",
         "cost": {"input": 0.6, "output": 2.2, "cacheRead": 0.1, "cacheWrite": 0.6}},
        {"id": "glm-5.3-flash", "name": "GLM-5.3-Flash",
         "cost": {"input": 0.1, "output": 0.6, "cacheRead": 0.02, "cacheWrite": 0.1}},
        {"id": "glm-4.6v", "name": "GLM-4.6V", "cost": None},
    ],
    "openrouter": [
        {"id": "gpt-5.2", "name": "GPT-5.2",
         "cost": {"input": 1.25, "output": 10.0, "cacheRead": 0.125, "cacheWrite": 1.25}},
    ],
}

# GET /ops/agent-config 可变态:搜索态 = zai 已配置(尾 4 显示面);零配置态 =
# api_keys 全空 → 密钥面基准空态。callable override 支持运行中翻态不重建路由。
CFG = {
    "model_health": "zai-coding-cn/glm-5.3-flash",
    "model_discover": "zai-coding-cn/glm-5.3",
    "api_keys": {"zai-coding-cn": {"configured": True, "tail4": "9988"}},
    "catalog": CATALOG,
    "catalog_source": "dynamic",
}

handle_api = build_handle_api({
    "/version": {**VERSION, "current": "g150-mock"},
    "/ops/agent-config": lambda: CFG,
})

httpd = serve_dist(PORT)
with sync_playwright() as p:
    browser, page = open_admin(p, PORT, handle_api)
    page.get_by_role("tab", name="设置").click(timeout=5000)
    page.wait_for_timeout(400)

    # ①搜索态:默认仅已配置家 → 搜索「o」唤出 openrouter(已配置置顶)
    body_text = page.inner_text("body")
    assert "保存全部" in body_text, "节级主操作未渲染:" + body_text[:600]
    assert "参考成本" in body_text, "模型行成本提示未渲染:" + body_text[:600]
    assert "已配置（•••• 9988）" in body_text, "已配置状态未渲染:" + body_text[:600]
    # 供应商下拉的目录项恒含各家(option 文本入 body),密钥面默认仅已配置家
    # ——断「未配置 key」状态不在场,而非供应商名不在场
    assert "未配置 key" not in body_text, "未配置家默认不应出现在密钥面"
    page.get_by_role("searchbox", name="搜索供应商名").fill("o")
    page.wait_for_timeout(200)
    body_text = page.inner_text("body")
    assert "openrouter" in body_text, "搜索未唤出未配置家:" + body_text[:600]
    assert "未配置 key" in body_text, "未配置状态未渲染:" + body_text[:600]
    page.screenshot(path=str(OUT_SEARCH), full_page=True)
    print("saved:", OUT_SEARCH)

    # ②零配置态:api_keys 翻空 → 刷新 → 密钥面「暂无」式空态(硬规⑥)
    CFG["api_keys"] = {}
    page.reload()
    page.wait_for_selector("[role=tab]")
    page.wait_for_timeout(300)
    page.get_by_role("tab", name="运营").click(timeout=5000)
    page.get_by_role("tab", name="设置").click(timeout=5000)
    page.wait_for_timeout(400)
    body_text = page.inner_text("body")
    assert "暂无已配置的 API 密钥" in body_text, "零配置空态未渲染:" + body_text[:600]
    page.screenshot(path=str(OUT_EMPTY), full_page=True)
    print("saved:", OUT_EMPTY)
    browser.close()
httpd.shutdown()
