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


# ── Task 4:key-source-sets —— sources 契约(POST/PATCH/GET)+ 种子行删除保护 ──
# brief 用例里 "dbip" 已改名 dbip_city(发现序 10 < dshield 12,去重+registry
# 序断言语义不变);fixture 沿用本文件 client_as_admin+key_env 既有模式。

def test_create_key_with_sources_roundtrip(client_as_admin, key_env):
    r = client_as_admin.post("/api/admin/keys", json={
        "name": "t", "sources": ["dshield", "dbip_city", "dbip_city"]})
    assert r.status_code == 201
    assert r.json()["meta"]["sources"] == ["dbip_city", "dshield"]  # 去重+registry 序


def test_create_key_null_sources(client_as_admin, key_env):
    r = client_as_admin.post("/api/admin/keys", json={"name": "t"})
    assert r.json()["meta"]["sources"] is None


def test_create_key_unknown_source_422(client_as_admin, key_env):
    r = client_as_admin.post("/api/admin/keys",
                             json={"name": "t", "sources": ["nope"]})
    assert r.status_code == 422


def test_create_key_empty_sources_422(client_as_admin, key_env):
    r = client_as_admin.post("/api/admin/keys",
                             json={"name": "t", "sources": []})
    assert r.status_code == 422


def test_patch_set_then_reset_sources(client_as_admin, key_env):
    sub = client_as_admin.post(
        "/api/admin/keys",
        json={"name": "t", "sources": ["dbip_city"]}).json()["meta"]["sub"]
    r = client_as_admin.patch(f"/api/admin/keys/{sub}",
                              json={"sources": ["dshield"]})
    assert r.json()["sources"] == ["dshield"]
    r = client_as_admin.patch(f"/api/admin/keys/{sub}", json={"sources": None})
    assert r.json()["sources"] is None   # model_fields_set 区分"显式 null=重置"


def test_delete_seed_row_403(client_as_admin, key_env):
    import asyncio
    from ipdb import _apikeys
    asyncio.run(_apikeys.ensure_demo_row())
    r = client_as_admin.delete(f"/api/admin/keys/{_apikeys.DEMO_SUB}")
    assert r.status_code == 403
    # 种子行仍在
    assert any(k["web"] for k in
               client_as_admin.get("/api/admin/keys").json())


def test_patch_seed_row_private_source_422(client_as_admin, key_env, monkeypatch):
    # P2 sweep Item A:私源∩demoweb 种子行后端硬拒(422),sources 保持原样。
    import asyncio
    from ipdb import _apikeys, _registry
    monkeypatch.setattr(_registry, "_PRIVATE", frozenset({"dshield"}))
    asyncio.run(_apikeys.ensure_demo_row())
    r = client_as_admin.patch(f"/api/admin/keys/{_apikeys.DEMO_SUB}",
                              json={"sources": ["dshield"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    row = next(k for k in client_as_admin.get("/api/admin/keys").json() if k["web"])
    assert row["sources"] is None   # 未变


def test_patch_regular_key_private_source_ok(client_as_admin, key_env, monkeypatch):
    # 同一私源名对普通 key 仍合法(私源授予 = admin 显式授权动作)。
    from ipdb import _registry
    monkeypatch.setattr(_registry, "_PRIVATE", frozenset({"dshield"}))
    sub = client_as_admin.post(
        "/api/admin/keys", json={"name": "t"}).json()["meta"]["sub"]
    r = client_as_admin.patch(f"/api/admin/keys/{sub}",
                              json={"sources": ["dshield"]})
    assert r.status_code == 200
    assert r.json()["sources"] == ["dshield"]


def test_patch_seed_row_public_then_null_ok(client_as_admin, key_env, monkeypatch):
    # 公源名与显式 null 重置不受守卫影响。
    import asyncio
    from ipdb import _apikeys, _registry
    monkeypatch.setattr(_registry, "_PRIVATE", frozenset({"dshield"}))
    asyncio.run(_apikeys.ensure_demo_row())
    r = client_as_admin.patch(f"/api/admin/keys/{_apikeys.DEMO_SUB}",
                              json={"sources": ["dbip_city"]})
    assert r.status_code == 200 and r.json()["sources"] == ["dbip_city"]
    r = client_as_admin.patch(f"/api/admin/keys/{_apikeys.DEMO_SUB}",
                              json={"sources": None})
    assert r.status_code == 200 and r.json()["sources"] is None


def test_keys_unknown_sub_404(client_as_admin, key_env):
    r = client_as_admin.patch("/api/admin/keys/doesnotexist0000",
                              json={"disabled": True})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "source_not_found"
    r = client_as_admin.delete("/api/admin/keys/doesnotexist0000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "source_not_found"
