# backend/tests/auth/test_middleware_order.py — 访问顺序红线(票 #482)
"""user_middleware 的叠放顺序由 main.py 里的定义先后决定(@app.middleware /
add_middleware 都插到栈最前,后定义者在外),没有检查时可以悄悄漂移。#482 起
守卫挪到最外层:任何其他中间件的应答都排在 404 面具之后。这是防御性顺序,
不是「隐藏端点此前被 400 穿帮」的修复——按代码,拒超大请求体只覆盖
_SIZE_CHECKED_PATHS 两条可见接口(/api/upload/stream、/api/query/stream),
隐藏端点的超大请求体此前与现在都拿不到 400。

本文件钉两层:
- 结构:user_middleware 里守卫(最外)→ reject_oversized_bodies(中间)
  → CORS(最里)的顺序;
- 行为:①把隐藏端点 /api/update-db 用 monkeypatch 临时加进
  _SIZE_CHECKED_PATHS(模拟「日后把隐藏端点纳入大小检查」的部署),守卫仍须
  先回 404——守卫挪回内层时大小检查先答 400,这条转红;②可见流接口的无
  web 头匿名超大请求 → 403(守卫的头部检查排在大小检查前面,#482 起对外
  可见的状态码变化:此部署形态下 400 → 403),带头 → 400(大小检查仍生效)。

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
    """行为红线(守卫侧):演示模式下隐藏端点 × 超大请求体 → 404 面具。
    今天拒超大请求体只覆盖 _SIZE_CHECKED_PATHS 两条可见接口,这里用
    monkeypatch 把隐藏端点 /api/update-db 临时加进该表,模拟「日后把隐藏
    端点纳入大小检查」的部署:守卫先回 404,请求不再向内层走,大小检查
    轮不到。守卫若被挪回内层,大小检查先答 400——400 等于承认端点存在,
    这条转红(评审返工·必须改 2:monkeypatch 之前它对叠放顺序不敏感)。"""
    monkeypatch.setattr(main, "_SIZE_CHECKED_PATHS",
                        ("/api/upload/stream", "/api/query/stream",
                         "/api/update-db"))
    monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
    client = TestClient(main.app)
    r = client.post("/api/update-db", content=b"", headers=OVERSIZED)
    assert r.status_code == 404, f"隐藏端点×超大请求体应 404,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "not_found"


def test_demo_visible_endpoint_oversized_body_still_400(monkeypatch):
    """行为对照(大小检查侧):可见端点(/api/upload/stream,带 web header
    过守卫的 header 门)× 超大请求体 → 中间层 400——大小检查在新叠放下仍
    生效,守卫外层化没有把它架空。"""
    monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
    client = TestClient(main.app)
    r = client.post("/api/upload/stream", content=b"",
                    headers={**OVERSIZED, "x-ipradar-client": "web"})
    assert r.status_code == 400, f"可见端点×超大请求体应 400,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "bad_request"


def test_demo_visible_stream_oversized_header_gate_order(monkeypatch):
    """对外可见的状态码变化(评审返工·必须改 2③):演示模式下,不带
    x-ipradar-client: web 的匿名超大 POST 打可见流接口(/api/query/stream),
    从 400 变成 403——守卫的头部检查排在大小检查前面,守卫外层化后这层
    403 先于中间层 400 出现;带头过守卫后仍由大小检查回 400。两腿都是
    拒绝,不泄漏存在性,但顺序决定状态码。"""
    monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
    client = TestClient(main.app)
    r = client.post("/api/query/stream", content=b"", headers=OVERSIZED)
    assert r.status_code == 403, f"无 web 头匿名超大请求应 403,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "forbidden"
    r = client.post("/api/query/stream", content=b"",
                    headers={**OVERSIZED, "x-ipradar-client": "web"})
    assert r.status_code == 400, f"带 web 头超大请求应 400,实得 {r.status_code}"
    assert r.json()["error"]["code"] == "bad_request"
