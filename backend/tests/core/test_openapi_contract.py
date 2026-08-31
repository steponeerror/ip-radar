"""PR③ T11: OpenAPI 契约测试 — 20 业务端点全部有响应 schema,错误信封注册。

防漂移:paths 数 == 路由数(多挂少挂都会炸);流式三端点
(query/upload stream、events)不入 response_model,但 description
必须写事件结构(NDJSON/SSE,错误事件含 code)。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

STREAM = {"/api/query/stream", "/api/upload/stream", "/api/events"}
BUSINESS_ROUTES = 19


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
                else:
                    responses = op.get("responses", {})
                    resp = responses.get("200") or responses.get("202")
                    assert resp, f"{method} {path} 无成功响应声明"
                    assert "schema" in json.dumps(resp), \
                        f"{method} {path} 成功响应无 schema"

    def test_paths_count_matches_routes(self):
        """19 业务 + 3 流式;多/少挂一个立刻红(防漂移)。"""
        assert len(self.spec["paths"]) == BUSINESS_ROUTES + len(STREAM)

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
                for status, resp in op.get("responses", {}).items():
                    if not (status.startswith("4") or status.startswith("5")):
                        continue
                    if status == "422" and path in STREAM:
                        continue  # 流式声明走 description,不重复挂
                    refs = json.dumps(resp)
                    assert "ErrorEnvelope" in refs, \
                        f"{method} {path} {status} 错误响应未引用信封 schema"

    def test_business_endpoints_have_response_model(self):
        """20 业务端点 200/202 schema 都指向具体模型(非空 object)。"""
        for path, ops in self.spec["paths"].items():
            if path in STREAM:
                continue
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                resp = op.get("responses", {}).get("200") or \
                    op.get("responses", {}).get("202")
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
