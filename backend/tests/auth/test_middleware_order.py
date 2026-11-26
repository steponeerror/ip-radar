# backend/tests/auth/test_middleware_order.py — 访问顺序红线(票 #482)
"""中间件叠放顺序此前只靠注释(拒超大请求体在最外、演示站守卫在其内),
后果:演示站上对隐藏端点发超大请求体先被 400,404 面具穿帮——body 大小
泄漏端点存在性。@app.middleware / add_middleware 都插到栈最前,后定义者
在外,所以顺序由 main.py 里的定义先后决定,无结构检查时可以悄悄漂移。

本文件钉两层:
- 结构:user_middleware 里守卫(最外)→ reject_oversized_bodies(中间)
  → CORS(最里)的顺序;
- 行为:演示模式下「隐藏端点 × 超大请求体 = 404 面具」与「可见端点 ×
  超大请求体 = 仍 400」成对(前一腿守卫先跑,后一腿大小检查仍生效)。

其余两条访问顺序红线:「401 先于预热 503」在 test_query_gating.py
(预热门真关着的两向对);「限流装饰器在路由装饰器之下」在 test_ratelimit.py。
"""
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import main  # noqa: F401  (import 触发 app 组装)

# 60MB > MAX_UPLOAD_BYTES(50MB);content=b"" 只借头,大小检查读声明值
OVERSIZED = {"Content-Length": str(60 * 1024 * 1024)}


def test_middleware_stack_demo_guard_outermost():
    """结构钉:守卫最外 → 拒超大请求体中间 → CORS 最里。user_middleware[0]
    = 栈最外(后定义者在外);@app.middleware 登记为 BaseHTTPMiddleware,
    以 dispatch 函数对象身份比对。"""
    stack = main.app.user_middleware
    assert stack[0].kwargs.get("dispatch") is main.public_demo_guard
    assert stack[1].kwargs.get("dispatch") is main.reject_oversized_bodies
    assert stack[2].cls is CORSMiddleware


def test_demo_hidden_endpoint_oversized_body_masked_404(monkeypatch):
    """行为红线(守卫侧):演示模式下隐藏端点(/api/update-db)× 超大请求体
    → 404 面具,不是 400——400 等于承认端点存在。守卫回 404 后,请求不再
    向内层走,大小检查根本轮不到。"""
    monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
    client = TestClient(main.app)
    r = client.post("/api/update-db", content=b"", headers=OVERSIZED)
    assert r.status_code == 404, f"隐藏端点×超大请求体应 404,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "not_found"


def test_demo_visible_endpoint_oversized_body_still_400(monkeypatch):
    """行为对照(大小检查侧):同一叠放下,可见端点(/api/upload/stream,
    带 web header 过守卫的 header 门)× 超大请求体 → 仍是中间层 400——
    证明 404 面具来自叠放顺序,而不是大小检查消失。"""
    monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
    client = TestClient(main.app)
    r = client.post("/api/upload/stream", content=b"",
                    headers={**OVERSIZED, "x-ipradar-client": "web"})
    assert r.status_code == 400, f"可见端点×超大请求体应 400,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "bad_request"
