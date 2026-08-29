"""PR③ T10: 全局错误信封 — 所有 HTTP 错误统一 {"error":{code,message,detail?}}。

两层码:语义码 ErrorCode(9 值,warming/no_sources/...);普通 HTTPException
按状态映射通用码(not_found/conflict/validation_error/...),require_ready 的
X-IPRadar-Reason 头映射 warming/no_sources。信封是响应体唯一形状变化,
status code 全部透传不变。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _tiny_db(tiny_db):
    """CI 干净检出无 data/ — 需要最小库打开查询门, 否则所有路由 503。"""


class TestErrorEnvelope:
    @classmethod
    def setup_class(cls):
        import main
        from ipdb import load_db
        load_db()
        cls.client = TestClient(main.app)

    def setup_method(self):
        """每测重置门全局态(同 test_main_routes)+ 显式打门成分为可过
        (db loaded、无 coverage building)——防前面文件留下真任务在跑
        (building=True)把本类 gate 测试 503 化。"""
        import math
        import main
        self._orig_deadline = main._BUILD_DEADLINE
        self._orig_episode = main._coverage_episode
        main._BUILD_DEADLINE = math.inf
        main._coverage_episode = False
        self._p_loaded = patch("ipdb._registry._db_loaded", return_value=True)
        self._p_building = patch.object(main, "_coverage_building",
                                        return_value=False)
        self._p_loaded.start()
        self._p_building.start()

    def teardown_method(self):
        import main
        self._p_loaded.stop()
        self._p_building.stop()
        main._BUILD_DEADLINE = self._orig_deadline
        main._coverage_episode = self._orig_episode

    def test_unknown_route_404_envelope(self):
        """Starlette 默认 404(路由不存在)也走信封。"""
        r = self.client.get("/api/nosuchroute")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        assert r.json()["error"]["message"]

    def test_unknown_source_404_envelope(self):
        """既有 404(未知源)不改 raise 方式,handler 兜底映射 not_found。"""
        r = self.client.get("/api/eval/nosuchsrc")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        assert "nosuchsrc" in r.json()["error"]["message"]

    def test_lookup_200_unaffected(self):
        """成功路径不带 error 键(信封只管错误)。"""
        r = self.client.get("/api/lookup/8.8.8.8")
        assert r.status_code == 200
        assert "error" not in r.json()

    def test_bad_request_400_envelope(self):
        r = self.client.post("/api/query/stream", json={"ips": "notalist"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "bad_request"

    def test_validation_422_envelope(self):
        """RequestValidationError 也信封化,字段级错误进 detail。"""
        r = self.client.patch("/api/sources/otx", json={})
        assert r.status_code == 422
        body = r.json()["error"]
        assert body["code"] == "validation_error"
        assert body["detail"]

    def test_warming_503_envelope(self):
        """warming 语义码 + retry_after,X-IPRadar-Reason 头保留。"""
        self._p_loaded.stop()  # 本测需要真实门判定:关掉 setup 的 pass 补丁
        with patch("ipdb._registry._db_loaded", return_value=False):
            r = self.client.get("/api/lookup/8.8.8.8")
        assert r.status_code == 503
        body = r.json()["error"]
        assert body["code"] == "warming"
        assert body["retry_after"] == 30
        assert r.headers["x-ipradar-reason"] == "warming"

    def test_no_sources_503_envelope(self):
        with patch("ipdb._registry._enabled_sources", return_value=[]):
            r = self.client.get("/api/lookup/8.8.8.8")
        assert r.status_code == 503
        body = r.json()["error"]
        assert body["code"] == "no_sources"
        assert "retry_after" not in body
        assert r.headers["x-ipradar-reason"] == "no-sources"

    def test_eval_busy_409_envelope(self):
        import main
        from ipdb._eval_manager import EvalBusyError
        with patch.object(main.eval_manager, "run",
                          side_effect=EvalBusyError("otx")):
            r = self.client.post("/api/eval/otx/run")
        assert r.status_code == 409
        body = r.json()["error"]
        assert body["code"] == "conflict"
        assert "otx" in body["message"]

    def test_unhandled_500_envelope(self):
        """未捕获异常 → internal 信封(不泄栈)。"""
        import main
        raw = TestClient(main.app, raise_server_exceptions=False)
        with patch.object(main, "list_sources",
                          side_effect=RuntimeError("boom")):
            r = raw.get("/api/sources")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "internal"
        assert "boom" not in r.json()["error"]["message"]
