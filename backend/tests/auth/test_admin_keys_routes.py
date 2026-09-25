# backend/tests/auth/test_admin_keys_routes.py — Task 5: /api/admin/keys CRUD
"""管理员 API key 路由(spec 2026-09-21 §7;REST 契约对 Task 9 前端 FROZEN)。

POST 201 {key, meta}(完整 JWT 仅此一次)→ GET 列表(绝不回 key)→
PATCH 吊销 → DELETE。keys-disabled 语义:仅 POST(签发)503,元数据
CRUD 照常(吊销/清理在 keys 禁用时仍须可用)。

fixtures 来自顶层 tests/conftest.py:client_as_admin(auth_env 链,登录
超管)+ key_env(同一 tmp_path,设 IP_RADAR_API_JWT_SECRET)—— controller
ruling:两者都要显式请求,env 共存无冲突。401 匿名测试用 auth_client
(admin 已配置未登录;仓库无顶层裸 client fixture,401 先于 404 路由层)。
"""
import main  # noqa: F401  (import 触发 app 组装)

# Controller ruling 2026-09-25(key-source-sets Task 1):spec §6 GET/201 增 sources/web,
# 契约演进为增法扩展 —— FROZEN 语义改为跟踪路由真实返回。
_META_KEYS = {"sub", "name", "created_at", "last_used_at", "disabled",
              "sources", "web"}


def test_keys_crud_lifecycle(client_as_admin, key_env):
    r = client_as_admin.post("/api/admin/keys", json={"name": "for-curl"})
    assert r.status_code == 201
    body = r.json()
    assert body["key"].count(".") == 2          # HS256 JWT 三段
    assert set(body["meta"]) == _META_KEYS      # 201 meta = 完整行(契约 FROZEN)
    assert body["meta"]["sources"] is None and body["meta"]["web"] is False
    sub = body["meta"]["sub"]

    lst = client_as_admin.get("/api/admin/keys").json()
    assert any(k["sub"] == sub for k in lst)
    assert all("key" not in k for k in lst)     # 列表绝不回完整 key

    assert client_as_admin.patch(f"/api/admin/keys/{sub}",
                                 json={"disabled": True}).status_code == 200
    # 吊销后查询端点 403(接线在 Task 6,这里先验 meta.disabled)
    assert any(k["disabled"] for k in client_as_admin.get("/api/admin/keys").json()
               if k["sub"] == sub)

    assert client_as_admin.delete(f"/api/admin/keys/{sub}").status_code == 204
    assert all(k["sub"] != sub
               for k in client_as_admin.get("/api/admin/keys").json())


def test_keys_expires_days_ge_1(client_as_admin, key_env):
    # Task 9 ruling 6:expires_days ge=1(负值/0 → 422 信封;None = 默认 180 天,spec §7.1)。
    for bad in (0, -1):
        r = client_as_admin.post("/api/admin/keys",
                                 json={"name": "x", "expires_days": bad})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"


def test_keys_require_admin(auth_client):
    r = auth_client.get("/api/admin/keys")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_keys_disabled_503(client_as_admin, key_env, monkeypatch):
    # keys_enabled() 读 CALL 时 env → delenv 即时生效,无需 reload
    monkeypatch.delenv("IP_RADAR_API_JWT_SECRET", raising=False)
    r = client_as_admin.post("/api/admin/keys", json={"name": "x"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "admin_disabled"
    # 仅签发被拦;元数据视图/吊销/清理在 keys 禁用时仍可用(ruling 3)
    assert client_as_admin.get("/api/admin/keys").status_code == 200


def test_keys_unknown_sub_404(client_as_admin, key_env):
    r = client_as_admin.patch("/api/admin/keys/doesnotexist0000",
                              json={"disabled": True})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "source_not_found"
    r = client_as_admin.delete("/api/admin/keys/doesnotexist0000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "source_not_found"
