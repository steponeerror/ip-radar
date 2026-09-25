# backend/tests/core/test_scope_wiring.py — Task 5: 查询端点 scope 接线
"""allowed 集贯穿查询路径 + db-status 软收窄(泄露关键路径)。

覆盖:
- _work_chunk/_dedup_lookup 线程传参 + LRU 键含 scope(审计 I2:
  scope 必须到达 lookup 最后一米,且同 IP 不同 key 集合不共享缓存条目)
- GET /api/lookup 按 key 集合收窄;null key 不见私源(Review Focus #3)
- POST /api/query/stream 行结果同样按 key 集合收窄(双流路径)
- /api/db-status 匿名只见公开源计数(Review Focus #5);
  合法 Bearer 软解析放大到其集合
- resolve_allowed(None) 恰剔除私源(T2 缓议 M1 补钉,Q10-A)
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main
from ipdb import _apikeys, _auth
from ipdb import _batch_pool as BP
from ipdb import _registry as reg


@pytest.fixture(autouse=True)
def _lru_hygiene():
    """桩结果不得经模块级 LRU 泄给其它测试文件(前后各清一次)。"""
    BP._cached_lookup.cache_clear()
    yield
    BP._cached_lookup.cache_clear()


@pytest.fixture(autouse=True)
def _hermetic_gate(monkeypatch):
    """密闭积分门(同 test_query_gating 先例):本文件测 scope 不测门。"""
    monkeypatch.setattr(main, "_coverage_building", lambda: False)


@pytest.fixture()
def scoped_registry(monkeypatch):
    """三假源:pub_a/pub_b 公开,priv_x 私有(monkeypatch _PRIVATE)。
    各对任意 IP 出不同 country 值,归因各留一条;record 数 100/50/200
    保证 get_status 子集严格可判。"""
    from ipdb._types import SourceHealth

    class FakeSource:
        def __init__(self, name, country, records):
            self.name = name
            self.fields = ("country_code",)
            self._country = country
            self._records = records

        def health(self):
            return SourceHealth(name=self.name, loaded=True,
                                record_count=self._records,
                                last_updated="2026-06-12T00:00:00Z",
                                is_stale=False)

        def query(self, ip):
            return {"country_code": self._country}

    monkeypatch.setattr(reg, "_sources", [
        FakeSource("pub_a", "AA", 100),
        FakeSource("pub_b", "BB", 50),
        FakeSource("priv_x", "XX", 200),
    ])
    monkeypatch.setattr(reg, "_PRIVATE", frozenset({"priv_x"}))


def _issue(name, sources=None):
    """key_env 前提下签发一把 key:隔离 auth db 已由 key_env 建好。"""
    asyncio.run(_auth.init_auth_db())
    _, token = asyncio.run(_apikeys.issue_key(name, sources=sources))
    return token


def _country_sources(event_result):
    return {a["source"] for a in event_result["country"]["sources"]}


# ── _batch_pool 单元:scope 最后一米 ──

def test_work_chunk_threads_allowed(monkeypatch):
    seen = {}

    class Stub:
        def __init__(self, ip):
            self.ip = ip

        def to_dict(self):
            return {"ip": self.ip}

    def fake_lookup(ip, allowed_sources=None):
        seen[ip] = allowed_sources
        return Stub(ip)

    monkeypatch.setattr(reg, "lookup", fake_lookup)
    BP._work_chunk(["1.2.3.4"], frozenset({"dbip"}))
    assert seen["1.2.3.4"] == frozenset({"dbip"})


def test_dedup_lookup_cache_keyed_by_scope(monkeypatch):
    """泄露面回归:同 IP 不同 key 集合不得共享 LRU 条目 —— 第二个 scope
    必须重算,同 scope 重复才命中缓存。"""
    calls = []

    class Stub:
        def __init__(self, ip):
            self.ip = ip

        def to_dict(self):
            return {"ip": self.ip}

    def fake_lookup(ip, allowed_sources=None):
        calls.append(allowed_sources)
        return Stub(ip)

    monkeypatch.setattr(reg, "lookup", fake_lookup)
    # 指纹钉常量:全套跑序里早期 lifespan 测试的真重建线程会改写 LMDB ptr,
    # 使 fp 漂移成额外 miss(本测试只钉 scope 键,epoch 键归 test_batch_dedup)
    monkeypatch.setattr(BP, "_epoch_fingerprint", lambda: ())
    BP._dedup_lookup(["9.9.9.9"], frozenset({"a"}))
    BP._dedup_lookup(["9.9.9.9"], frozenset({"b"}))
    BP._dedup_lookup(["9.9.9.9"], frozenset({"a"}))   # 同 scope 才命中
    assert calls == [frozenset({"a"}), frozenset({"b"})]


# ── GET /api/lookup:硬口径(Review Focus #3)──

def test_lookup_route_scopes_by_key(scoped_registry, key_env):
    priv_token = _issue("scoped", sources=["priv_x", "pub_a"])
    null_token = _issue("null-scope")
    client = TestClient(main.app)

    r1 = client.get("/api/lookup/1.2.3.4",
                    headers={"Authorization": f"Bearer {priv_token}"})
    assert r1.status_code == 200
    assert _country_sources(r1.json()) == {"priv_x", "pub_a"}   # 非成员 pub_b 不见

    r2 = client.get("/api/lookup/1.2.3.4",
                    headers={"Authorization": f"Bearer {null_token}"})
    assert r2.status_code == 200
    assert _country_sources(r2.json()) == {"pub_a", "pub_b"}    # null key 不见私源


def test_stream_rows_scoped_by_key(scoped_registry, key_env):
    """双流路径同规:行结果归因不含非成员源。"""
    token = _issue("stream-scoped", sources=["priv_x"])
    client = TestClient(main.app)
    r = client.post("/api/query/stream", json={"ips": ["1.2.3.4"]},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rows = [line for line in r.text.splitlines() if '"type":"row"' in line]
    assert len(rows) == 1
    import json
    row = json.loads(rows[0])
    assert _country_sources(row["result"]) == {"priv_x"}


# ── /api/db-status:软收窄(Review Focus #5)──

def test_db_status_anonymous_public_only(scoped_registry):
    """匿名(无 Origin/无 Bearer):计数只含公开源,私源计数不泄露。"""
    client = TestClient(main.app)
    r = client.get("/api/db-status", headers={"x-ipradar-client": "web"})
    assert r.status_code == 200
    assert r.json()["total_records"] == 150   # 100 + 50,不含 priv_x 的 200


def test_db_status_bearer_soft_scope(scoped_registry, key_env):
    """合法 Bearer:软解析放大到其集合(点名私源 → 计数含私源)。"""
    token = _issue("status-scoped", sources=["priv_x"])
    client = TestClient(main.app)
    r = client.get("/api/db-status",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["total_records"] == 200   # 仅 priv_x


# ── T2 缓议 M1 补钉(controller ordered fix #2,Q10-A)──

def test_resolve_allowed_none_pins_private_exclusion(monkeypatch):
    """判别 fixture:两假源其一私有 → resolve_allowed(None) 恰等于公开那个。
    排除语义由测试钉死,不靠代码检视。"""
    class FakeSource:
        name = None
        fields = ("country_code",)

        def health(self):
            from ipdb._types import SourceHealth
            return SourceHealth(name=self.name, loaded=True, record_count=1,
                                last_updated=None, is_stale=False)

        def query(self, ip):
            return {"country_code": "ZZ"}

    a, b = FakeSource(), FakeSource()
    a.name, b.name = "pin_pub", "pin_priv"
    monkeypatch.setattr(reg, "_sources", [a, b])
    monkeypatch.setattr(reg, "_PRIVATE", frozenset({"pin_priv"}))
    assert reg.resolve_allowed(None) == frozenset({"pin_pub"})
