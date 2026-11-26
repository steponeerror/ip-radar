"""公共 demo 模式中间件测试 — spec: docs/superpowers/specs/2026-08-23-public-demo-mode-design.md

三态:写/内部接口 404 信封 not_found(当作不存在);查询读接口无 header 403
信封 forbidden;OPTIONS 仅 preflight 形状豁免;回环/version 豁免。
env 需动态读(monkeypatch 可切换)。
"""
import asyncio
import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

HEADER = {"x-ipradar-client": "web"}


@contextmanager
def _client(env_value: str | None, admin: str | None = None,
            trust_xff: bool = False):
    """TestClient with ``_startup`` patched out (no cold-start downloads)."""
    import main
    with patch.object(main, "_startup"):
        import os
        if admin is not None:
            os.environ["IP_RADAR_DEMO_ADMIN_IPS"] = admin
        if trust_xff:
            os.environ["IP_RADAR_DEMO_TRUST_XFF"] = "1"
        if env_value is None:
            os.environ.pop("IP_RADAR_PUBLIC_DEMO", None)
        else:
            os.environ["IP_RADAR_PUBLIC_DEMO"] = env_value
        with TestClient(main.app) as c:
            yield c


@pytest.fixture(autouse=True)
def _restore_env():
    import os
    yield
    os.environ.pop("IP_RADAR_PUBLIC_DEMO", None)
    os.environ.pop("IP_RADAR_DEMO_ADMIN_IPS", None)
    os.environ.pop("IP_RADAR_DEMO_TRUST_XFF", None)


def test_demo_hidden_endpoints_404():
    with _client("1") as c:
        cases = [
            ("post", "/api/update-db"),
            ("post", "/api/update-db/cancel"),
            ("post", "/api/update-db/pause"),
            ("post", "/api/update-db/resume"),
            ("get", "/api/sources"),
            ("get", "/api/tasks"),
            ("get", "/api/events"),
            ("get", "/api/update/status"),
            ("post", "/api/update"),
            # #482 起四族内部接口同样装不存在(此前漏网,匿名拿 401/503 自报存在)
            ("get", "/api/ops/items"),
            ("get", "/api/admin/keys"),
            ("get", "/api/users/me"),
            ("post", "/api/auth/jwt/logout"),
        ]
        for method, path in cases:
            res = getattr(c, method)(path)
            assert res.status_code == 404, f"{method} {path} -> {res.status_code}"


# ── #482:隐藏与否从路由管理员依赖推导 ──
def test_demo_newly_hidden_families_404():
    """四族各挑一条写明行为:推导前匿名访问这些路径拿 401/503(自报存在),
    推导后一律 404 信封 not_found。"""
    with _client("1") as c:
        for method, path in (("GET", "/api/ops/items"),
                             ("GET", "/api/admin/keys"),
                             ("GET", "/api/users/me"),
                             ("POST", "/api/auth/jwt/logout")):
            r = c.request(method, path)
            assert r.status_code == 404, f"{method} {path} -> {r.status_code}"
            assert r.json()["error"]["code"] == "not_found"


def test_demo_login_reachable_but_logout_hidden():
    """例外②:POST /api/auth/jwt/login 不隐藏(主人不在白名单地址上时也要能
    登录)。匿名实测:admin 未配置 → 依赖层 503 admin_disabled;若进程态里
    admin 已配(此前用例登录过),则是表单层 400/422 —— 都不是守卫的 404。
    同族 logout 带超管依赖,照推导规则隐藏。"""
    with _client("1") as c:
        r = c.post("/api/auth/jwt/login")
        assert r.status_code != 404, "登录口必须可达"
        assert r.json()["error"]["code"] != "not_found"
        assert c.post("/api/auth/jwt/logout").status_code == 404


def test_demo_hidden_path_method_agnostic_404():
    """匹配只看路径不看方法:隐藏路径上未声明的方法也是 404(不给方法级
    探测通道);对照:可见路径的方法不对由路由器 405,非守卫职责。"""
    with _client("1") as c:
        r = c.delete("/api/tasks")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


def _api_routes_with_expected_hidden():
    """按规则 1/2 独立推导 (path, methods, expect_hidden) 全表(票 #482):
    规则 1 = 依赖树带 require_admin_configured ∪ current_superuser;
    规则 2 = /api/update 一律隐藏、/api/auth/jwt/login 不隐藏。
    实现侧不引用本函数——两侧各自从路由表推导,只共享规则不共享代码。"""
    from fastapi.routing import iter_route_contexts
    import ipdb._auth as _auth
    import main
    anchors = {main.require_admin_configured, _auth.current_superuser}

    def has_admin_dep(dependant):
        for sub in getattr(dependant, "dependencies", ()) or ():
            if getattr(sub, "call", None) in anchors or has_admin_dep(sub):
                return True
        return False

    routes = []
    for ctx in iter_route_contexts(main.app.routes):
        path = getattr(ctx, "path", "")
        if not path.startswith("/api/"):
            continue  # 守卫只在 /api 上判隐藏;非 /api 路径全放,无隐藏可言
        expect = (path == "/api/update"
                  or (path != "/api/auth/jwt/login"
                      and has_admin_dep(ctx.dependant)))
        methods = sorted(getattr(ctx, "methods", set()) - {"HEAD"})
        routes.append((path, methods, expect))
    return routes


def test_demo_hidden_table_derived_full_sweep():
    """全表扫描(票 #482 验收):遍历全部 /api 路由,按规则 1/2 独立推导应否
    隐藏,再在演示模式下对每条路由发匿名真实请求(路径参数取样例值,方法
    用路由声明之一):该隐藏的回 404 信封;不该隐藏的不回 404(200/401/
    403/422/503 都是合法后续层应答)。期望表从路由依赖树推导,不手抄路径。"""
    import re
    from unittest.mock import AsyncMock
    import main
    routes = _api_routes_with_expected_hidden()
    assert len(routes) >= 40, f"路由表异常地小: {len(routes)}"
    assert any(h for _, _, h in routes), "推导表无隐藏路由,规则失效?"
    assert any(not h for _, _, h in routes), "推导表全是隐藏路由,可见面被吞?"
    # /api/version 匿名可达;fetch_latest 桩掉免网络(同 test_version_reports_demo_flag)
    with patch.object(main._ipdb_version, "fetch_latest",
                      AsyncMock(return_value=None)):
        with _client("1") as c:
            for path, methods, expect_hidden in routes:
                url = re.sub(r"\{[^}]+\}", "x", path)  # 路径参数样例(全表 str 转换器)
                res = c.request(methods[0], url)
                if expect_hidden:
                    assert res.status_code == 404, (
                        f"{methods[0]} {url} 应 404,实得 {res.status_code}")
                    assert res.json()["error"]["code"] == "not_found"
                else:
                    assert res.status_code != 404, (
                        f"{methods[0]} {url} 不该隐藏(无管理员依赖),"
                        f"实得 404 body={res.text[:120]}")


def test_demo_rule_second_anchor_current_superuser_alone_hides():
    """规则 1 第二锚的行为证:只挂 current_superuser(无
    require_admin_configured)的路由同样隐藏。现网路由都是双锚(_ADMIN_DEPS
    两个一起挂、fastapi-users 路由器级依赖兜底),拿临时路由单独钉第二锚;
    顺带走一遍「路由数量变了 → 推导表重建」的缓存失效路径(加路由后首问
    必须重建,否则新路由漏面具)。finally 还原路由表。"""
    from fastapi import Depends
    import main

    async def _only_superuser_probe():
        return {"ok": True}

    main.app.add_api_route("/api/_demo_anchor_probe", _only_superuser_probe,
                           methods=["GET"],
                           dependencies=[Depends(main._ipdb_auth.current_superuser)])
    route = main.app.routes[-1]
    try:
        with _client("1") as c:
            r = c.get("/api/_demo_anchor_probe")
            assert r.status_code == 404, (
                f"只挂 current_superuser 的路由应隐藏,实得 {r.status_code}")
            assert r.json()["error"]["code"] == "not_found"
    finally:
        main.app.routes.remove(route)


def test_demo_read_endpoints_need_header():
    with _client("1") as c:
        assert c.get("/api/db-status").status_code == 403
        res = c.get("/api/db-status", headers=HEADER)
        assert res.status_code == 200


def test_demo_stix_same_header_rule_as_lookup():
    # PR #63 Q1-B:STIX 改 fetch+blob(apiFetch 带 web header),守卫不再豁免;
    # 无 header → 403(守卫),带 header → 过守卫后由路由层 api_key_dep 兑底(非 403)。
    with _client("1") as c:
        assert c.get("/api/lookup/1.1.1.1/stix").status_code == 403
        res = c.get("/api/lookup/1.1.1.1/stix", headers=HEADER)
        assert res.status_code != 403


def test_demo_admin_credentials_bypass_guard():
    # 三层鉴权合并:伪 cookie/伪 Bearer 不再被守卫 404/403 拦在展示层,
    # 而是交给依赖层真校验(此处无有效会话/密钥 → 401;keys 未配置时 503)。
    with _client("1") as c:
        res = c.get("/api/tasks", cookies={"ipradar_admin": "forged"})
        assert res.status_code != 404  # 守卫放行,superuser 门拒之
        res = c.get("/api/lookup/1.1.1.1",
                   headers={"Authorization": "Bearer forged"})
        assert res.status_code != 403  # 守卫放行,api_key_dep 拒之


def test_demo_options_passthrough():
    # CORS 预检不带业务 header,必须直通(中间件在 CORS 外层)
    with _client("1") as c:
        res = c.options(
            "/api/db-status",
            headers={"Origin": "http://localhost:5173",
                     "Access-Control-Request-Method": "GET"},
        )
        assert res.status_code != 403


def test_demo_loopback_exempt():
    # compose healthcheck 无 header 直击 db-status;httpx.ASGITransport
    # 默认 client=("127.0.0.1", 123),恰好模拟回环来源
    import main
    with _client("1"):
        async def run():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://t"
            ) as ac:
                return await ac.get("/api/db-status")
        res = asyncio.run(run())
    assert res.status_code != 403


def test_normal_mode_unaffected():
    with _client(None) as c:
        assert c.get("/api/db-status").status_code == 200  # 无 header 也放行
        # PR #63 后管理端点超管门接管:无守卫干扰 = 路由应答(503 admin_disabled),非 404
        assert c.get("/api/tasks").status_code == 503


def test_version_reports_demo_flag():
    import main
    for env, expected in [("1", True), (None, False)]:
        with _client(env) as c:
            monkey_target = main._ipdb_version
            with patch.object(
                monkey_target, "fetch_latest", AsyncMock(return_value=None)
            ):
                res = c.get("/api/version")
            assert res.status_code == 200
            assert res.json()["public_demo"] is expected


def test_demo_admin_direct_peer_bypasses_all():
    # 直连 peer 命中(应用端口直接暴露的部署)
    import main
    with _client("1", admin="testclient") as c:  # starlette TestClient peer host 是字面量 testclient
        monkey_target = main._ipdb_version
        with patch.object(
            monkey_target, "fetch_latest", AsyncMock(return_value=None)
        ):
            res = c.get("/api/version")
            assert res.status_code == 200
            assert res.json()["public_demo"] is False   # 前端据此显示完整 UI
        # 守卫全旁路:管理端点由超管门应答(503 未配置),不再被守卫 404
        assert c.get("/api/tasks").status_code == 503
        assert c.get("/api/db-status").status_code == 200


def test_demo_admin_trust_xff_first_hop():
    # 显式声明信任反代后,首跳 XFF 命中即旁路(配套网关保证,见 main.py 注释)
    with _client("1", admin="10.9.8.7", trust_xff=True) as c:
        # 旁路 = 守卫放行(非 404/403);路由层由超管门接管(503 未配置)
        assert c.get("/api/tasks",
                     headers={"x-forwarded-for": "10.9.8.7, 172.64.1.1"}
                     ).status_code == 503


def test_demo_admin_xff_ignored_without_trust_flag():
    # 回归:默认不信任任何 XFF(可伪造,实测可穿透 CF→Caddy 链)
    with _client("1", admin="10.9.8.7") as c:
        assert c.get("/api/tasks",
                     headers={"x-forwarded-for": "10.9.8.7"}).status_code == 404


def test_demo_admin_mismatch_still_guarded():
    with _client("1", admin="10.9.8.7", trust_xff=True) as c:
        assert c.get("/api/tasks",
                     headers={"x-forwarded-for": "1.2.3.4"}).status_code == 404


# ── guard hardening(Task 1):② OPTIONS 仅认 preflight 形状 ──
PREFLIGHT = {"Origin": "http://localhost:5173",
             "Access-Control-Request-Method": "GET"}


def test_demo_options_preflight_shape_only():
    # /api 路径上仅放行真 CORS 预检(Origin + Access-Control-Request-Method
    # 两头齐全);缺任一头按路径走既有判定(hidden 前缀 404 / header 前缀 403)。
    with _client("1") as c:
        assert c.options("/api/db-status", headers=PREFLIGHT).status_code == 200
        assert c.options("/api/sources").status_code == 404
        assert c.options("/api/db-status").status_code == 403
        assert c.options("/api/db-status",
                         headers={"Origin": "http://localhost:5173"}
                         ).status_code == 403
        assert c.options("/api/db-status",
                         headers={"Access-Control-Request-Method": "GET"}
                         ).status_code == 403


def test_demo_options_non_api_still_exempt():
    # 非 /api 路径 OPTIONS 照旧全放,应答来自路由/静态挂载而非守卫:
    # 无静态构建时路由 404(not_found);静态挂载时 OPTIONS 405(method_not_allowed
    # ——守卫永不发 405)。两态都证明守卫未拦。
    with _client("1") as c:
        res = c.options("/no-such-page")
        assert res.status_code in (404, 405)
        assert res.json()["error"]["code"] in ("not_found", "method_not_allowed")


# ── ③ 守卫 404/403 信封化 ──
def test_demo_guard_errors_use_envelope():
    # 中间件在全局 exception handler 之外 → 手工构造 {"error":{code,message}}:
    # 404=not_found(当作不存在),403=forbidden。
    with _client("1") as c:
        r = c.get("/api/sources")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        r = c.get("/api/db-status")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"


# ── ④ /api/update/status 路由层真锁(守卫 404 只是展示层)──
def test_update_status_locked_without_admin(auth_client):
    # admin 已配置的匿名请求:依赖层 401 unauthorized(非 superuser 登录则 403)。
    r = auth_client.get("/api/update/status")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_update_status_ok_for_admin(client_as_admin):
    r = client_as_admin.get("/api/update/status")
    assert r.status_code == 200
    assert "state" in r.json()


def test_demo_update_status_defense_in_depth():
    # demo 模式:匿名仍 404(守卫展示层);带伪凭据守卫放行 → 路由锁接管,
    # 由依赖层拒绝(admin 未配置 503 先于 401/403,见 main 依赖顺序约定)。
    with _client("1") as c:
        assert c.get("/api/update/status").status_code == 404
        r = c.get("/api/update/status", cookies={"ipradar_admin": "forged"})
        assert r.status_code in (401, 403, 503)


# ── ⑥ PUBLIC_DEMO 值告警 ──
def test_public_demo_misconfig_warns(caplog, monkeypatch):
    # 唯一生效值是 "1";设了其他非空值 → 启动告警(含原值与正确写法),
    # ="1"/未设 → 无告警;告警绝不阻断启动。
    import main
    with caplog.at_level(logging.WARNING):
        monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "true")
        main._warn_public_demo_misconfig()
        assert "IP_RADAR_PUBLIC_DEMO" in caplog.text
        assert "true" in caplog.text
        assert 'exactly "1"' in caplog.text
        caplog.clear()
        monkeypatch.setenv("IP_RADAR_PUBLIC_DEMO", "1")
        main._warn_public_demo_misconfig()
        assert "IP_RADAR_PUBLIC_DEMO" not in caplog.text
        monkeypatch.delenv("IP_RADAR_PUBLIC_DEMO")
        main._warn_public_demo_misconfig()
        assert "IP_RADAR_PUBLIC_DEMO" not in caplog.text
