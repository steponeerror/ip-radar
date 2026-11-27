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
            trust_xff: bool = False, follow_redirects: bool = True):
    """TestClient with ``_startup`` patched out (no cold-start downloads).
    尾斜杠变形用例必须 follow_redirects=False:307 被跟进后终点仍是守卫的
    404,面具的「不 307」承诺就看不见了(变异证据:默认值下去镜像匹配的
    变异不转红)。"""
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
        with TestClient(main.app, follow_redirects=follow_redirects) as c:
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


def test_demo_login_reachable_but_logout_hidden(monkeypatch):
    """例外②:POST /api/auth/jwt/login 不隐藏(主人不在白名单地址上时也要能
    登录)。monkeypatch 把进程级管理员标志(ipdb._auth._admin_flag)钉成
    未配置,断言稳定落在依赖层的 503 admin_disabled——不再随进程态(admin
    已配时是表单层 400/422)漂(评审返工·建议改 6)。同族 logout 带超管
    依赖,照推导规则隐藏。"""
    import ipdb._auth as _auth
    monkeypatch.setattr(_auth, "_admin_flag", False)
    with _client("1") as c:
        r = c.post("/api/auth/jwt/login")
        assert r.status_code == 503, (
            f"登录口应 503 admin_disabled,实得 {r.status_code}")
        assert r.json()["error"]["code"] == "admin_disabled"
        assert c.post("/api/auth/jwt/logout").status_code == 404


def test_demo_hidden_path_method_agnostic_404():
    """匹配只看路径不看方法:隐藏路径上未声明的方法也是 404(不给方法级
    探测通道);对照:可见路径的方法不对由路由器 405,非守卫职责。"""
    with _client("1") as c:
        r = c.delete("/api/tasks")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


# 评审返工·必须改 1:尾斜杠变形此前穿透面具被 starlette 路由器 307 跳到
# 规范路径(Location 自报存在性);%2F 进 ASGI 前已百分号解码成 /,同路。
SLASH_VARIANTS = [
    "/api/tasks/", "/api/tasks//", "/api/tasks///", "/api/tasks%2F",
    "/api/sources/x/", "/api/users/me/", "/api/auth/jwt/logout/",
    "/api/update/", "/api/ops/items/", "/api/tasks/?x=1",
]


@pytest.mark.parametrize("path", SLASH_VARIANTS)
def test_demo_trailing_slash_variants_masked(path):
    """尾斜杠变形与裸路径同样拿 404 信封:守卫镜像路由器的去尾斜杠(rstrip
    全部)+ 补斜杠两个跳转候选再判一次,307 跳转不再先于面具出现。
    follow_redirects=False 断言守卫直答的 404——默认跟随后 307 的终点仍会
    被面具接住,变异(去镜像)看不见。?x=1 一行钉住 request.url.path 不含
    查询串。"""
    with _client("1", follow_redirects=False) as c:
        r = c.get(path)
        assert r.status_code == 404, f"GET {path} 应 404,实得 {r.status_code}"
        assert r.json()["error"]["code"] == "not_found"


# 单元级用的路径 = 同一批变形到了守卫手里的样子:查询串不在 url.path 里,
# %2F 进 ASGI 前已百分号解码成 /(上面走完整请求的用例覆盖这两步)。
SLASH_VARIANT_PATHS = [p.split("?")[0].replace("%2F", "/") for p in SLASH_VARIANTS]


@pytest.mark.parametrize("path", SLASH_VARIANT_PATHS)
def test_demo_path_hidden_covers_slash_variants(path):
    """同一个判定的单元级钉子:不经路由器,直接问 _demo_path_hidden。
    上面那条走完整请求的用例只在「没有前端构建」的形态下有判别力——带
    frontend/dist 时根路径的外壳挂载先接住一切不认识的路径,路由器不会
    走补斜杠跳转,去掉镜像它照样绿(CI 的后端任务就是这种形态)。这条在
    两种形态下都要求隐藏判定自己认得尾斜杠变形。"""
    import main
    assert main._demo_path_hidden(main.app, path) is True, path
    assert main._demo_path_hidden(main.app, "/api/version/") is False
    assert main._demo_path_hidden(main.app, "/api//tasks") is None


@pytest.mark.parametrize("path", ["/api//tasks", "/api/./tasks",
                                  "/api/tasks;x=1/", "/api/tasks/.."])
def test_demo_noncanonical_shapes_still_404(path):
    """对照组(评审返工·必须改 1):这些 /api/ 下的形状在镜像前后都拿 404——
    去尾斜杠/补斜杠都命中不了任何路由(fastapi 不规范化路径、; 不是
    分隔符)。镜像不得引入新放行,这条钉住它。"""
    with _client("1", follow_redirects=False) as c:
        r = c.get(path)
        assert r.status_code == 404, f"GET {path} 应 404,实得 {r.status_code}"
        assert r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("path", ["/API/tasks/", "/API/ops/items/", "/API/tasks"])
def test_demo_non_api_shapes_get_no_api_answer(path):
    """不在 /api/ 下的变形(大小写不同,守卫不判隐藏):正则大小写敏感,没有任何
    接口路由匹配。有没有前端构建产物决定了谁来收——有,是前端外壳页回 200;
    没有,是路由器回 404(CI 的后端任务有构建产物,开发工作树通常没有)。
    两种形态下都不该出现「有接口在应答」的迹象:不是 307(没有 Location)、
    没有 Allow 头;回 200 的必须是 HTML 外壳页(不是接口的 JSON)。404 的
    响应体是哪种形状不在这里管(全站 404 都走同一个信封处理器)。"""
    with _client("1", follow_redirects=False) as c:
        r = c.get(path)
        assert r.status_code in (200, 404), (
            f"GET {path} 应是外壳页 200 或 404,实得 {r.status_code}")
        assert "location" not in r.headers, f"GET {path} 不该跳转"
        assert "allow" not in r.headers, f"GET {path} 不该报出允许的方法"
        if r.status_code == 200:
            assert "text/html" in r.headers.get("content-type", ""), (
                f"GET {path} 的 200 应是前端外壳页")


def _api_routes():
    """全部 /api 路由的 (path, methods)(fastapi 0.141 平面视图,同
    test_security_matrix)。"""
    from fastapi.routing import iter_route_contexts
    import main
    routes = []
    for ctx in iter_route_contexts(main.app.routes):
        path = getattr(ctx, "path", "")
        if not path.startswith("/api/"):
            continue  # 守卫只在 /api 上判隐藏;非 /api 路径全放,无隐藏可言
        methods = sorted(getattr(ctx, "methods", set()) - {"HEAD"})
        routes.append((path, methods))
    return routes


def _expected_hidden_from_frozen():
    """独立对照源(评审返工·建议改 1):期望「隐不隐藏」从
    test_security_matrix.FROZEN(手维护的鉴权类别冻结表)推导,与实现的
    依赖树遍历零共享代码——实现若在「遍历哪一层」上错,这张表不会跟着错。
    管理员类 = {admin, logout}(logout 是「须已登录超管」操作,匿名同样装
    不存在;login 不算——它是例外②的放行口;keyed / open-status /
    open-selfupdate-token 可见);或路径 == /api/update(例外①)。同路径
    多方法:任一方法属管理员类即隐藏——与实现侧「同路径取或」同口径。"""
    from tests.auth.test_security_matrix import FROZEN
    admin_classes = frozenset({"admin", "logout"})
    classes_by_path: dict[str, set] = {}
    for (_method, path), cls in FROZEN.items():
        classes_by_path.setdefault(path, set()).add(cls)
    return {path: bool(classes & admin_classes) or path == "/api/update"
            for path, classes in classes_by_path.items()}


def test_demo_hidden_table_derived_full_sweep():
    """全表扫描(票 #482 验收):遍历全部 /api 路由,期望值从 FROZEN 冻结表
    推导(见 _expected_hidden_from_frozen——独立对照源),再在演示模式下对
    每条路由发匿名真实请求(路径参数取样例值,方法用路由声明之一):该隐藏
    的回 404 信封;不该隐藏的不回 404(200/401/403/422/503 都是合法后续层
    应答)。FROZEN 没覆盖的路由在这里响亮失败——新路由先去
    test_security_matrix 登记(那张表自己也钉这件事,这里是双保险)。"""
    import re
    from unittest.mock import AsyncMock
    import main
    routes = _api_routes()
    expected = _expected_hidden_from_frozen()
    assert len(routes) >= 40, f"路由表异常地小: {len(routes)}"
    missing = sorted({path for path, _ in routes} - set(expected))
    assert not missing, (
        f"FROZEN 表没覆盖的路由(先去 test_security_matrix 登记): {missing}")
    hidden_count = sum(1 for path, _ in routes if expected[path])
    assert hidden_count, "FROZEN 推导无隐藏路由,规则失效?"
    assert hidden_count < len(routes), "FROZEN 推导全是隐藏路由,可见面被吞?"
    # /api/version 匿名可达;fetch_latest 桩掉免网络(同 test_version_reports_demo_flag)
    with patch.object(main._ipdb_version, "fetch_latest",
                      AsyncMock(return_value=None)):
        with _client("1") as c:
            for path, methods in routes:
                url = re.sub(r"\{[^}]+\}", "x", path)  # 路径参数样例(全表 str 转换器)
                expect_hidden = expected[path]
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
        # 数量键缓存看不见「同数量换内容」(评审记一笔·认可的限制):临时路由
        # 逐个加删都是 len±1,不清掉派生表,下一个加路由的用例会命中 stale 面具
        try:
            del main.app.state._demo_hidden_routes
        except AttributeError:
            pass


def test_demo_param_level_depends_hides():
    """递归 + 参数级 Depends(评审返工·建议改 2):管理员依赖挂在端点参数的
    子依赖上(inner = Depends(_inner),_inner(guard = Depends(第二锚)))——
    fastapi 把参数级 Depends 也收进 dependant.dependencies,遍历必须递归到
    第二层才看得到;匿名 → 404。把 _route_has_admin_dep 改成只看第一层
    (不递归)时这条转红。"""
    from fastapi import Depends
    import main

    async def _inner(guard: None = Depends(main._ipdb_auth.current_superuser)):
        return None

    async def _param_dep_probe(inner: None = Depends(_inner)):
        return {"ok": True}

    main.app.add_api_route("/api/_demo_param_dep_probe", _param_dep_probe,
                           methods=["GET"])
    route = main.app.routes[-1]
    try:
        with _client("1") as c:
            r = c.get("/api/_demo_param_dep_probe")
            assert r.status_code == 404, (
                f"参数级 Depends 挂管理员依赖的路由应隐藏,实得 {r.status_code}")
            assert r.json()["error"]["code"] == "not_found"
    finally:
        main.app.routes.remove(route)
        try:
            del main.app.state._demo_hidden_routes
        except AttributeError:
            pass


def test_demo_login_exception_scoped_to_login_route_only():
    """例外②只作用于 POST /api/auth/jwt/login 那一条路由(评审返工·建议
    改 4):同一路径上的其他路由照推导规则 1 计入取或——临时挂一条带管理员
    依赖的 GET 到同一路径,整条路径即被判隐藏(路径级取或,往严处走;POST
    例外救不回同路径的管理员路由)。例外被改回「整条路径放行」时这条转红
    (旧行为下 GET 拿 503 admin_disabled 而非 404)。"""
    from fastapi import Depends
    import main

    async def _login_get_probe():
        return {"ok": True}

    main.app.add_api_route("/api/auth/jwt/login", _login_get_probe,
                           methods=["GET"],
                           dependencies=[Depends(main.require_admin_configured)])
    route = main.app.routes[-1]
    try:
        with _client("1") as c:
            r = c.get("/api/auth/jwt/login")
            assert r.status_code == 404, (
                f"同路径新增的管理员路由应照规则 1 隐藏,实得 {r.status_code}")
            assert r.json()["error"]["code"] == "not_found"
    finally:
        main.app.routes.remove(route)
        try:
            del main.app.state._demo_hidden_routes
        except AttributeError:
            pass


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


def test_demo_preflight_hidden_or_missing_masked_404():
    # 评审返工·必须改 1(预检同病兄弟):预检形状 OPTIONS 不再整体豁免——
    # 隐藏或没有任何路由匹配都由守卫回 404 信封(「隐藏」与「不存在」在任何
    # 部署形态下同形;此前隐藏路径的预检被放行给 CORS,由 CORS 均匀应答);
    # 可见路由(db-status)的预检照旧 200,由上面的
    # test_demo_options_preflight_shape_only 钉住。
    with _client("1") as c:
        for path in ("/api/tasks/", "/api/tasks", "/api/no-such-thing"):
            r = c.options(path, headers=PREFLIGHT)
            assert r.status_code == 404, (
                f"OPTIONS {path} 应 404,实得 {r.status_code}")
            assert r.json()["error"]["code"] == "not_found"


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
