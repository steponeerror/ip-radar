# backend/tests/auth/test_security_matrix.py — 安全攻击矩阵(API 重构后全量)
"""攻击向量层测试(与 test_query_gating 的正常流互补):

1. 路由分类冻结网:每条 /api 路由的鉴权类别写入冻结表;新增路由忘挂
   依赖时,本测试第一个红 —— 未分类路由不得静默上线。
2. admin 面匿名全扫:管理端点无凭据一律 401(eval/model 与 eval/{source}
   的行为 401 另由 test_admin_gating._MANAGEMENT 携带,FROZEN 兜底分类)。
3. JWT 攻击向量:alg=none 无签名 token、畸形 Bearer → 401。
4. Referer 伪造(跨源 Referer 无 key)→ 401。
5. Host 头伪造同源绕过:行为钉(grill Q1=A 接受+文档化)—— 同源层是
   浏览器 UX 非鉴权边界,应用层不修;demo 由 CF/Caddy/回环三层实测挡死,
   README「安全须知」已文档化。

公开面(2026-09-22 审计口径,均已在冻结表内显式认可):
- GET /api/version、/api/db-status:公开 UI 需要。
- POST /api/update:handler 内 token 校验(本文件钉 403);
  GET /api/update/status:更新状态。
- eval×3 + GET /api/sources 已收 admin(F2/F5,本波)。
"""
import asyncio
import base64
import json

import pytest
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from fastapi.testclient import TestClient

import main
from tests.conftest import KEY_JWT_SECRET

# ── 冻结表:(method, path) -> 鉴权类别 ──
# admin   = require_admin_configured + superuser(401/403/503)
# keyed   = api_key_dep(同源放行 / Bearer 401/403 / 503)
# login   = 登录端点本身(限流 + 错误凭据 400)
# logout  = 需已登录(匿名 401)
# open-*  = 无鉴权依赖,显式认可(见模块 docstring)
FROZEN = {
    ("POST", "/api/query/stream"): "keyed",
    ("POST", "/api/upload/stream"): "keyed",
    ("GET", "/api/lookup/{ip}"): "keyed",
    ("GET", "/api/lookup/{ip}/stix"): "keyed",
    ("GET", "/api/db-status"): "open-status",
    ("GET", "/api/sources"): "admin",
    ("PATCH", "/api/sources/{name}"): "admin",
    ("POST", "/api/sources/{name}/update"): "admin",
    ("GET", "/api/eval"): "admin",
    ("GET", "/api/eval/model"): "admin",
    ("GET", "/api/eval/{source}"): "admin",
    ("POST", "/api/eval/{source}/run"): "admin",
    ("POST", "/api/update-db"): "admin",
    ("POST", "/api/update-db/cancel"): "admin",
    ("POST", "/api/update-db/pause"): "admin",
    ("POST", "/api/update-db/resume"): "admin",
    ("GET", "/api/tasks"): "admin",
    ("POST", "/api/tasks/{task_id}/cancel"): "admin",
    ("GET", "/api/events"): "admin",
    ("GET", "/api/version"): "open-status",
    ("POST", "/api/update"): "open-selfupdate-token",
    ("GET", "/api/update/status"): "open-status",
    ("POST", "/api/auth/jwt/login"): "login",
    ("POST", "/api/auth/jwt/logout"): "logout",
    ("GET", "/api/users/me"): "admin",
    ("PATCH", "/api/users/me"): "admin",
    ("GET", "/api/users/{id}"): "admin",
    ("PATCH", "/api/users/{id}"): "admin",
    ("DELETE", "/api/users/{id}"): "admin",
    ("GET", "/api/admin/keys"): "admin",
    ("POST", "/api/admin/keys"): "admin",
    ("PATCH", "/api/admin/keys/{sub}"): "admin",
    ("DELETE", "/api/admin/keys/{sub}"): "admin",
}


def _classify(route, path: str) -> tuple[str, list[str]]:
    names = set()
    for d in getattr(route, "dependencies", []):
        f = getattr(d, "dependent", None)
        names.add(getattr(f, "__name__", ""))
    if isinstance(route, (APIRoute, RouteContext)):
        # RouteContext(fastapi 0.141 展开视图)以 __getattr__ 委托 dependant
        for p in route.dependant.dependencies:
            names.add(getattr(p.call, "__name__", ""))
    if "api_key_dep" in names:
        return "keyed", sorted(names)
    if path == "/api/auth/jwt/login":
        return "login", sorted(names)
    if path == "/api/auth/jwt/logout":
        return "logout", sorted(names)
    if "require_admin_configured" in names:
        return "admin", sorted(names)
    return "open-?", sorted(names)


def test_route_classification_frozen():
    """每条 /api 路由必须命中冻结表且类别一致;新增路由先来这里登记。"""
    seen = set()
    # fastapi 0.141 起 include_router 不再摊平进 app.routes(出现 _IncludedRouter
    # 嵌套节点);用官方 iter_route_contexts 还原平面视图,ctx 以 __getattr__
    # 委托出 path/methods/dependencies/dependant,下游分类逻辑不变。
    for r in iter_route_contexts(main.app.routes):
        path = getattr(r, "path", "")
        if not path.startswith("/api/"):
            continue
        for m in getattr(r, "methods", []) - {"HEAD"}:
            got, deps = _classify(r, path)
            key = (m, path)
            seen.add(key)
            assert key in FROZEN, (
                f"未分类路由 {m} {path}(deps={deps})——新路由必须先在 "
                "test_security_matrix.FROZEN 登记鉴权类别")
            if got == "open-?":
                assert FROZEN[key].startswith("open-"), (
                    f"{m} {path} 无任何鉴权依赖 —— 冻结表必须以 open- 前缀"
                    f"显式认可({deps})")
            else:
                assert FROZEN[key] == got, (
                    f"{m} {path} 鉴权类别漂移:冻结表={FROZEN[key]} 实测={got}")
    missing = set(FROZEN) - seen
    assert not missing, f"冻结表里有路由已不存在: {sorted(missing)}"


# admin 面匿名全扫(auth_client = admin 已配置、未登录)
_ADMIN_PROBES = [
    ("POST", "/api/update-db", None),
    ("POST", "/api/update-db/cancel", None),
    ("POST", "/api/update-db/pause", None),
    ("POST", "/api/update-db/resume", None),
    ("PATCH", "/api/sources/x", {"enabled": False}),
    ("POST", "/api/sources/x/update", None),
    ("POST", "/api/eval/x/run", None),
    ("GET", "/api/eval", None),
    ("GET", "/api/eval/model", None),
    ("GET", "/api/eval/{source}", None),
    ("GET", "/api/sources", None),
    ("GET", "/api/tasks", None),
    ("POST", "/api/tasks/t/cancel", None),
    ("GET", "/api/events", None),
    ("GET", "/api/users/me", None),
    ("PATCH", "/api/users/me", {}),
    ("GET", "/api/users/00000000-0000-0000-0000-000000000000", None),
    ("PATCH", "/api/users/00000000-0000-0000-0000-000000000000", {}),
    ("DELETE", "/api/users/00000000-0000-0000-0000-000000000000", None),
    ("GET", "/api/admin/keys", None),
    ("POST", "/api/admin/keys", {"name": "x"}),
    ("PATCH", "/api/admin/keys/deadbeef", {"disabled": True}),
    ("DELETE", "/api/admin/keys/deadbeef", None),
    ("POST", "/api/auth/jwt/logout", None),
]


@pytest.mark.parametrize("method,path,body", _ADMIN_PROBES)
def test_admin_routes_anonymous_401(auth_client, method, path, body):
    r = auth_client.request(method, path, json=body) if body is not None \
        else auth_client.request(method, path)
    assert r.status_code == 401, f"{method} {path} 匿名应 401,实得 {r.status_code}"


@pytest.fixture()
def client(tiny_db):
    """匿名 TestClient(无 Origin/Referer),同 test_query_gating。"""
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _hermetic_gate(monkeypatch):
    """warming 门密闭(同 test_query_gating 先例,防全量跑序时序 flake)。"""
    monkeypatch.setattr(main, "_coverage_building", lambda: False)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _alg_none_token() -> str:
    h = _b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    p = _b64u(json.dumps({"sub": "forged", "kname": "x",
                          "exp": 4102444800}).encode())  # 2100 年
    return f"{h}.{p}."  # 无签名段


def test_alg_none_and_malformed_bearer_401(client, key_env):
    asyncio.run(__import__("ipdb")._auth.init_auth_db())
    for tok in (_alg_none_token(), "garbage", "a.b.c",
                _b64u(b"x") + "." + _b64u(b"y") + "." + _b64u(b"z")):
        r = client.get("/api/lookup/1.1.1.1",
                       headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, f"伪造 token 应 401: {tok[:24]}…"
        assert r.json()["error"]["code"] == "unauthorized"


def test_stix_cross_origin_referer_401(client):
    """Origin 缺席时 _same_origin 回退 Referer:跨源 Referer 不得放行。"""
    r = client.get("/api/lookup/1.1.1.1/stix",
                   headers={"Referer": "https://evil.example/page"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_host_forgery_same_origin_bypass(client):
    """行为钉(grill Q1=A:接受+文档化):_same_origin loose 集信任请求自带
    Host/XFH,裸 HTTP 客户端伪造 Host+Origin 免 key 通过 —— HTTP 层无法与
    合法无反代浏览器区分,应用层不修。2026-09-22 线上实测 demo 由 CF 验
    Host / Caddy 站点匹配 / 回环绑定三层挡死;README「安全须知」已文档化。"""
    r = client.get("/api/lookup/1.1.1.1",
                   headers={"Host": "evil.example",
                            "Origin": "http://evil.example"})
    assert r.status_code == 200
    body = r.json()
    assert body["ip"] == "1.1.1.1"            # 真 lookup 应答,非别的 200
    assert body["country"]["value"] == "AU"   # tiny_db: 1.1.1.0/24 = AU


def test_self_update_without_token_403(client):
    """POST /api/update 的 handler 内 token 校验:匿名/错 token 一律 403。"""
    assert client.post("/api/update").status_code == 403
    assert client.post(
        "/api/update", json={"token": "wrong"}
    ).status_code == 403


def test_expired_token_route_level_401(client, key_env):
    """路由级过期 401(单元级已有;此处钉端到端信封)。"""
    from ipdb import _apikeys, _auth
    import jwt as pyjwt
    import time
    asyncio.run(_auth.init_auth_db())
    asyncio.run(_apikeys.issue_key("anchor"))
    dead = pyjwt.encode(
        {"sub": "deadbeef", "kname": "e", "iat": int(time.time()) - 999,
         "exp": int(time.time()) - 1}, KEY_JWT_SECRET, algorithm="HS256")
    r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                    headers={"Authorization": f"Bearer {dead}"})
    assert r.status_code == 401


def test_docs_gated_by_env(tmp_path):
    """docs 门控(审计 F3):/openapi.json 默认不出 schema,IP_RADAR_ENABLE_DOCS=1
    才是真 schema。env 在 main 模块级读取、运行中不可翻转 → 子进程各自起
    真实 app 验证(hermetic,不污染本进程已 import 的 main 单例)。
    断言安全属性(schema 是否出海)而非状态码:docs 关闭时该路径会被 SPA
    回退接住返回 index.html(200),但那不是 schema。"""
    import os
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent("""
        from fastapi.testclient import TestClient
        import main
        c = TestClient(main.app)
        r = c.get("/openapi.json")
        try:
            schema = isinstance(r.json(), dict) and "openapi" in r.json()
        except ValueError:
            schema = False
        print("SCHEMA" if schema else "HIDDEN")
    """)
    env = {k: v for k, v in os.environ.items()
           if k != "IP_RADAR_ENABLE_DOCS"}
    env["IP_RADAR_AUTH_DB"] = str(tmp_path / "docs-gate.db")
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    for extra, want in (({}, "HIDDEN"),
                        ({"IP_RADAR_ENABLE_DOCS": "1"}, "SCHEMA")):
        r = subprocess.run([sys.executable, "-c", probe],
                           env={**env, **extra}, cwd=backend_dir,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-400:]
        assert r.stdout.strip() == want, (
            f"IP_RADAR_ENABLE_DOCS={extra or 'unset'}: 期望 {want}")
