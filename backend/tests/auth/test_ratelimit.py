# backend/tests/auth/test_ratelimit.py — Task 7: slowapi 限流
"""四桶验证(spec §8 + Q1-B 修正案):匿名批量 6/min 按 IP、匿名单查
(lookup+stix)30/min 按 IP、keyed 60/min 统一桶、登录 5/min 按 IP(计
所有尝试)。

本文件重开限流(套件其余部分经 conftest 的 rate_limit_off autouse 默认
关闭),rl_on 清存储且依赖该 off-fixture 保证顺序;无 sleep(内存固定
窗口)。匿名 volley 必须带同源头(Task 6:否则先 401 轮不到限流)。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

import main  # noqa: F401  (import 触发 app 组装)
from conftest import ADMIN_EMAIL, SAME_ORIGIN
from ipdb import _apikeys, _auth, _ratelimit


@pytest.fixture()
def client(tiny_db):
    """匿名 TestClient;tiny_db 打开 require_ready 门。"""
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _hermetic_gate(monkeypatch):
    """密闭门(test_query_gating 先例):全量跑序里早期 lifespan 测试武装
    warming 门,真实 503 会污染本文件的 200 断言。"""
    monkeypatch.setattr(main, "_coverage_building", lambda: False)


@pytest.fixture()
def rl_on(rate_limit_off):
    """重开限流 + 清存储;依赖 conftest autouse off-fixture 保证其先跑。"""
    _ratelimit.limiter.reset()
    _ratelimit.limiter.enabled = True
    yield
    _ratelimit.limiter.enabled = False


def _bearer(name):
    """key_env 前提下签发一把 key(key_env 已建隔离 auth db)。"""
    asyncio.run(_auth.init_auth_db())
    _, token = asyncio.run(_apikeys.issue_key(name))
    return {"Authorization": f"Bearer {token}"}


def test_anon_batch_6_per_min(client, rl_on):
    for _ in range(6):
        r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                        headers=SAME_ORIGIN)
        assert r.status_code == 200
    r7 = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                     headers=SAME_ORIGIN)
    assert r7.status_code == 429
    err = r7.json()["error"]
    assert err["code"] == "rate_limited"
    assert "retry_after" in err
    assert r7.headers["Retry-After"].isdigit()


def test_keyed_not_counted_into_anon_bucket(client, key_env, rl_on):
    """双向互斥(Review Focus #5):keyed 7 连发(超匿名 6/min——若漏进
    匿名桶,第 7 发即 429)全 200;随后匿名请求仍 200(keyed 流量没占
    匿名桶)。"""
    auth = _bearer("rl-excl")
    for _ in range(7):
        r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                        headers=auth)
        assert r.status_code == 200
    r_anon = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                         headers=SAME_ORIGIN)
    assert r_anon.status_code == 200


def test_keyed_61st_429(client, key_env, rl_on):
    auth = _bearer("rl-61")
    for _ in range(60):
        r = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                        headers=auth)
        assert r.status_code == 200
    r61 = client.post("/api/query/stream", json={"ips": ["1.1.1.1"]},
                      headers=auth)
    assert r61.status_code == 429
    assert r61.json()["error"]["code"] == "rate_limited"


def test_login_bruteforce_429(auth_client, rl_on):
    """5/min 计所有尝试:前 5 次错密码 400,第 6 次 429(包装器在
    authenticate 之前检查,失败尝试同样计数)。"""
    for _ in range(5):
        r = auth_client.post("/api/auth/jwt/login",
                             data={"username": ADMIN_EMAIL,
                                   "password": "wrong"})
        assert r.status_code == 400
    r6 = auth_client.post("/api/auth/jwt/login",
                          data={"username": ADMIN_EMAIL,
                                "password": "wrong"})
    assert r6.status_code == 429
    assert r6.json()["error"]["code"] == "rate_limited"


def test_lookup_get_31st_429(client, rl_on):
    for _ in range(30):
        r = client.get("/api/lookup/1.1.1.1", headers=SAME_ORIGIN)
        assert r.status_code == 200
    r31 = client.get("/api/lookup/1.1.1.1", headers=SAME_ORIGIN)
    assert r31.status_code == 429


def test_lookup_shared_budget_across_paths_and_stix(client, rl_on):
    # 固定 scope 的行为学钉子:lookup 30/min 是跨路径、lookup+stix 共用的
    # 一个桶 —— slowapi 默认 per-URL 键控下单 URL 测试照样过,此测试才会红。
    for i in range(15):
        for path in ("/api/lookup/1.1.1.1", "/api/lookup/8.8.8.8/stix"):
            r = client.get(path, headers=SAME_ORIGIN)
            assert r.status_code == 200, f"volley {i} {path}"
    r31 = client.get("/api/lookup/1.1.1.1", headers=SAME_ORIGIN)
    assert r31.status_code == 429
