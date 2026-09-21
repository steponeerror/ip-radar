"""PR③ T11: OpenAPI 契约测试 — 24 业务端点全部有响应 schema,错误信封注册。

防漂移:paths 数 == 路由数(多挂少挂都会炸);流式三端点
(query/upload stream、events)不入 response_model,但 description
必须写事件结构(NDJSON/SSE,错误事件含 code)。

Task 2(admin 认证,spec 2026-09-21 §6)新增 fastapi-users 库挂载的 4
条路径(/api/auth/jwt/login|logout、/api/users/me、/api/users/{id}):
- 成功响应为 204 No Content(cookie 会话,登录写/登出清 Set-Cookie,
DELETE 用户同)—— HTTP 语义上 body 为空,无响应 schema;
- 错误文档用库自带 ErrorModel/描述式(不经本仓 ErrorEnvelope 声明);
  运行时错误仍由全局 StarletteHTTPException handler 统一落信封。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

STREAM = {"/api/query/stream", "/api/upload/stream", "/api/events"}
# fastapi-users 库路由(Task 2):错误声明不经 ErrorEnvelope,见模块 docstring。
AUTH_LIB = {"/api/auth/jwt/login", "/api/auth/jwt/logout",
            "/api/users/me", "/api/users/{id}"}
BUSINESS_ROUTES = 23


class TestOpenAPIContract:
    @classmethod
    def setup_class(cls):
        import main
        cls.spec = main.app.openapi()

    def test_every_endpoint_documented(self):
        for path, ops in self.spec["paths"].items():
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if path in STREAM:
                    assert "event" in (op.get("description") or "").lower(), \
                        f"{path} 流式端点 description 缺事件结构说明"
                    continue
                responses = op.get("responses", {})
                if "204" in responses:
                    continue  # 204 No Content:body 设计为空(fastapi-users cookie 会话)
                resp = responses.get("200") or responses.get("202")
                assert resp, f"{method} {path} 无成功响应声明"
                assert "schema" in json.dumps(resp), \
                    f"{method} {path} 成功响应无 schema"

    def test_paths_count_matches_routes(self):
        """23 业务(含 Task 2 admin 认证 4 路径)+ 3 流式;多/少挂一个立刻红(防漂移)。"""
        assert len(self.spec["paths"]) == BUSINESS_ROUTES + len(STREAM)
        assert AUTH_LIB <= set(self.spec["paths"]), "admin 认证路径缺失/改名"

    def test_error_envelope_registered(self):
        """错误信封 schema 进 components,且所有声明的 4xx/5xx 都引用它。"""
        schemas = self.spec["components"]["schemas"]
        assert "ErrorEnvelope" in schemas, "错误信封未注册"
        err = schemas["ErrorEnvelope"]
        body_ref = err["properties"]["error"].get("$ref", "")
        body = schemas[body_ref.split("/")[-1]] if body_ref else \
            err["properties"]["error"]
        assert set(body["required"]) == {"code", "message"}
        for path, ops in self.spec["paths"].items():
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                if path in AUTH_LIB:
                    # 库路由错误声明用自带 ErrorModel/描述式;运行时仍由全局
                    # StarletteHTTPException handler 统一落信封(实测为准:
                    # include_router responses= 合并时路由自身声明优先,无法覆盖)
                    continue
                for status, resp in op.get("responses", {}).items():
                    if not (status.startswith("4") or status.startswith("5")):
                        continue
                    if status == "422" and path in STREAM:
                        continue  # 流式声明走 description,不重复挂
                    refs = json.dumps(resp)
                    assert "ErrorEnvelope" in refs, \
                        f"{method} {path} {status} 错误响应未引用信封 schema"

    def test_business_endpoints_have_response_model(self):
        """24 业务端点 200/202 schema 都指向具体模型(非空 object);
        204 成功的库路由(cookie 会话)无 body,不计。"""
        for path, ops in self.spec["paths"].items():
            if path in STREAM:
                continue
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                responses = op.get("responses", {})
                if "204" in responses:
                    continue  # 204 No Content:cookie 会话登录/登出/DELETE
                resp = responses.get("200") or responses.get("202")
                s = json.dumps(resp)
                assert "$ref" in s or "properties" in s or \
                    "additionalProperties" in s, \
                    f"{method} {path} 无具体响应模型"


class TestFieldOutShape:
    def test_alternatives_absent_when_not_provided(self):
        """to_dict 仅在非空时写 alternatives;FieldOut 不得用默认 [] 把它
        补进每个响应(GET 与 NDJSON 流同形红线)。extra=allow 透传真值。"""
        from ipdb._api_models import FieldOut
        out = FieldOut(value="CN", confidence=99, algorithm="logodds")
        assert "alternatives" not in out.model_dump()

    def test_alternatives_passthrough_when_present(self):
        from ipdb._api_models import FieldOut
        out = FieldOut(value="CN", confidence=99, algorithm="logodds",
                       alternatives=[{"value": "US", "probability": 1.2}])
        assert out.model_dump()["alternatives"] == [
            {"value": "US", "probability": 1.2}]
