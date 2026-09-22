# backend/tests/auth/test_admin_gating.py — Task 3: 管理端点全部要求超管
"""14 个管理端点(含 /api/events SSE)匿名 401 / 非超管 403 / 超管可达。

依赖顺序(plan Global Constraint + controller ruling 1):
require_admin_configured → current_superuser → require_ready
即 503 admin_disabled 优先于 401,401/403 优先于 warming 503。
503 admin_disabled 语义 Task 2 已测(test_login.py),此处不重复。

SSE(T9:httpx 0.28 ASGITransport 等不到 infinite 流,client.stream 会死锁,
starlette testclient.py portal.call(self.app,...) 全量跑完才返回响应):
- 结构测试(路由依赖声明)承载 /api/events 的 RED 与防漂移;
- 超管 200 行为测试用 finite 化 StreamingResponse(只发首条 snapshot 事件);
- 匿名 401 行为测试在门生效后是有限错误响应,门生效前会挂死 → RED 阶段
  deselect(其 RED 由结构测试承载,controller ruling)。

fixtures 来自顶层 tests/conftest.py(auth_env/auth_client/client_as_admin)。
"""
import asyncio

import pytest

import main  # noqa: F401  (import 触发 app 组装)

# brief _MANAGEMENT 清单 + POST /api/tasks/{task_id}/cancel(brief step 3
# 门控 10 端点中唯一不在 _MANAGEMENT 参数表里的非 SSE 项)。
# firehol 仅是 {name}/{source} 路径参数的代表名(controller ruling 5)。
# 2026-09-22 审计 F2/F5:eval×3 + GET /api/sources 收编(公开 SPA 已不用)。
_MANAGEMENT = [
    ("get", "/api/sources", None),
    ("patch", "/api/sources/firehol", {"enabled": False}),
    ("post", "/api/sources/firehol/update", None),
    ("post", "/api/update-db", None),
    ("post", "/api/update-db/cancel", None),
    ("post", "/api/update-db/pause", None),
    ("post", "/api/update-db/resume", None),
    ("get", "/api/eval", None),
    ("get", "/api/eval/model", None),
    ("get", "/api/eval/firehol", None),
    ("post", "/api/eval/firehol/run", None),
    ("post", "/api/tasks/doesnotexist/cancel", None),
    ("get", "/api/tasks", None),
]

# 结构测试的门控清单:brief step 3 全部 10 端点(真实路由路径参数形态)
# + 2026-09-22 收编的 eval×3 / sources GET。
_GATED = [
    ("get", "/api/sources"),
    ("patch", "/api/sources/{name}"),
    ("post", "/api/sources/{name}/update"),
    ("post", "/api/update-db"),
    ("post", "/api/update-db/cancel"),
    ("post", "/api/update-db/pause"),
    ("post", "/api/update-db/resume"),
    ("get", "/api/eval"),
    ("get", "/api/eval/model"),
    ("get", "/api/eval/{source}"),
    ("post", "/api/eval/{source}/run"),
    ("post", "/api/tasks/{task_id}/cancel"),
    ("get", "/api/tasks"),
    ("get", "/api/events"),
]


@pytest.mark.parametrize("method,path,body", _MANAGEMENT)
def test_management_requires_admin(auth_client, method, path, body):
    r = auth_client.request(method, path, json=body)
    assert r.status_code == 401, f"{path} 不应匿名可达"
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path", _GATED)
def test_gated_routes_declare_admin_deps(method, path):
    """结构防漂移:14 端点路由级依赖含 require_admin_configured + current_superuser
    (controller ruling:T9 下 /api/events 的 RED 由本测试承载)。"""
    route = next(r for r in main.app.routes
                 if getattr(r, "path", None) == path
                 and method.upper() in getattr(r, "methods", set()))
    calls = [d.call for d in route.dependant.dependencies]
    assert main.require_admin_configured in calls, f"{path} 缺 require_admin_configured"
    assert main._ipdb_auth.current_superuser in calls, f"{path} 缺 current_superuser"


def test_management_forbidden_for_non_superuser(auth_client):
    """登录的普通用户(非超管)→ 403 forbidden(controller ruling 2)。"""
    from fastapi_users.password import PasswordHelper
    from ipdb import _auth

    async def _mk_peon():
        async with _auth._session_maker()() as s:
            s.add(_auth.User(
                email="peon@ipradar.local",
                hashed_password=PasswordHelper().hash("peon-pass-123"),
                is_superuser=False, is_active=True))
            await s.commit()

    asyncio.run(_mk_peon())
    r = auth_client.post("/api/auth/jwt/login",
                         data={"username": "peon@ipradar.local",
                               "password": "peon-pass-123"})
    assert r.status_code == 204
    r = auth_client.get("/api/tasks")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_management_ok_as_admin(client_as_admin):
    r = client_as_admin.get("/api/tasks")
    assert r.status_code == 200


def test_events_ok_as_admin_finite_stream(client_as_admin, monkeypatch):
    """超管可达 SSE:StreamingResponse 换成只发首条事件即封流的子类,
    绕开 T9 死锁(controller ruling)——依赖/handler/snapshot 全走真路径。"""
    _base = main.StreamingResponse

    class _FirstEventResponse(_base):
        async def stream_response(self, send):
            await send({"type": "http.response.start",
                        "status": self.status_code,
                        "headers": self.raw_headers})
            chunk = await self.body_iterator.__anext__()
            if not isinstance(chunk, (bytes, memoryview)):
                chunk = chunk.encode(self.charset)
            await send({"type": "http.response.body", "body": chunk,
                        "more_body": False})
            await self.body_iterator.aclose()

    monkeypatch.setattr(main, "StreamingResponse", _FirstEventResponse)
    r = client_as_admin.get("/api/events")
    assert r.status_code == 200
    assert r.text.startswith("data:")
    assert '"snapshot"' in r.text


def test_events_requires_admin_anonymous(auth_client):
    """SSE 匿名 401:门生效后依赖在流开始前抛错 → 有限信封响应。
    门生效前本测试会死锁(infinite 流),RED 阶段 deselect,RED 由结构测试承载。"""
    r = auth_client.get("/api/events")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
