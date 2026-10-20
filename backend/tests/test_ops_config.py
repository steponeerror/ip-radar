"""运营 agent 配置面(票 #140,TDD 红先行)。

钉住契约(期望值取自独立真源,不从被测模块导入常量防套套逻辑):

- 配置文件 = ops 树 agent-config.json(字段 model_health/model_discover/
  zai_api_key;原子写沿 _ops_store 基座);缺文件 = 未配置(GET 零副作用,
  不建文件);
- 模型闭集 = zai-coding-cn 实测装载目录五值(2026-10-20 本仓 ops/agent
  npm ci 后 loadModels().catalog 逐字;pi-ai 锁版,lockfile 升级须复测)
  ——PUT 未知值 422,先校验后落盘(坏入参零写);
- key 永不回显:GET/PUT 出参只含 zai_api_key{configured, tail4}(沿
  TokenStatus 先例);响应/错误消息绝无完整 key;空串/缺省 = 保持不改;
- 优先级链:配置 > 进程 effective env > models.mjs 缺省(override 灌 key
  兜底语义不动;env 模型覆盖在 status 可见);
- GET 带 allowed_models(前端下拉单一真相源,裁决 2026-10-20);
- 坏文件显式报错不静默(非法 JSON/非映射/字段非 str → RuntimeError →
  GET/PUT 500;无证据≠清白,不伪装成未配置);
- admin 鉴权沿 P2/P3 _ADMIN_DEPS 惯例(匿名 401)。

spawn 注入三元(OPS_MODEL_HEALTH/OPS_MODEL_DISCOVER/ZAI_CODING_CN_API_KEY,
每次 spawn 现读=改完即生效)在 test_ops_rounds.py 用假 agent 真过 spawn 层钉。
"""

import json
from pathlib import Path

import pytest

# ── 冻结件期望值(独立真源)──
# 实测装载目录(loadModels().catalog,2026-10-20;裁决:闭集=对齐实际目录)
MODEL_CATALOG = ["glm-4.6v", "glm-5.3", "glm-5.3-flash",
                 "glm-5.3-highspeed", "glm-5.3-flashx"]
# models.mjs DEFAULTS 逐字(独立抄录,不导入被测模块)
DEFAULT_HEALTH = "glm-5.3-flash"
DEFAULT_DISCOVER = "glm-5.3"
CONFIG_FILE = "agent-config.json"


@pytest.fixture
def cfg():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误;P1 同型)。"""
    import ipdb._ops_config as ops_config
    return ops_config


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp;剥掉三类 effective env(开发机 .env 可能灌 zai key,
    剥净保证「未配置」基线确定)。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    for var in ("ZAI_CODING_CN_API_KEY", "OPS_MODEL_HEALTH", "OPS_MODEL_DISCOVER"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _plant(ops_env: Path, cfg: dict) -> Path:
    """直接落配置文件(独立于被测模块的写入面)。"""
    (ops_env / "ops").mkdir(parents=True, exist_ok=True)
    p = ops_env / "ops" / CONFIG_FILE
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


# ── A. 存取面(_ops_config)──────────────────────────────────────────


def test_status_absent_config_defaults_and_catalog(cfg, ops_env):
    """缺文件 = 未配置:模型回落 models.mjs 缺省、key configured=false、
    allowed_models = 实测闭集五值;GET 语义零副作用(不建文件)。"""
    st = cfg.status()
    assert st["model_health"] == DEFAULT_HEALTH
    assert st["model_discover"] == DEFAULT_DISCOVER
    assert st["zai_api_key"] == {"configured": False, "tail4": None}
    assert st["allowed_models"] == MODEL_CATALOG
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_update_roundtrip_persists_and_reports_tail4(cfg, ops_env):
    """写入:文件落 ops 树(JSON 三字段)+ 状态回 model 值与 tail4;
    出参永不回显完整 key。"""
    st = cfg.update(model_health="glm-4.6v", model_discover="glm-5.3-highspeed",
                    zai_api_key="sk-live-zai-SECRET-9988")
    assert st["model_health"] == "glm-4.6v"
    assert st["model_discover"] == "glm-5.3-highspeed"
    assert st["zai_api_key"] == {"configured": True, "tail4": "9988"}
    assert "sk-live-zai-SECRET-9988" not in json.dumps(st, ensure_ascii=False)
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk == {"model_health": "glm-4.6v", "model_discover": "glm-5.3-highspeed",
                    "zai_api_key": "sk-live-zai-SECRET-9988"}


def test_update_rejects_unknown_model_before_write(cfg, ops_env):
    """闭集外模型 422 面(ValueError);写前门:坏入参零写(文件不落地)。"""
    for bad in ("gpt-4o", "", "GLM-5.3"):
        with pytest.raises(ValueError):
            cfg.update(model_health=bad)
        with pytest.raises(ValueError):
            cfg.update(model_discover=bad)
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_update_blank_or_missing_key_keeps_current(cfg, ops_env):
    """key 空串/缺省/纯空白 = 保持不改(沿票面:无清除面)。"""
    cfg.update(zai_api_key="sk-first-AAAA")
    for keep in ("", "   ", None):
        cfg.update(model_health="glm-5.3", zai_api_key=keep)
        st = cfg.status()
        assert st["zai_api_key"] == {"configured": True, "tail4": "AAAA"}
        assert st["model_health"] == "glm-5.3"
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["zai_api_key"] == "sk-first-AAAA"


def test_update_partial_fields_keep_others(cfg, ops_env):
    """部分更新:未涉字段原样保留(合并语义,非整包覆写)。"""
    cfg.update(model_health="glm-4.6v", model_discover="glm-5.3-flashx",
               zai_api_key="sk-keep-BBBB")
    cfg.update(model_discover="glm-5.3")
    st = cfg.status()
    assert st["model_health"] == "glm-4.6v"
    assert st["model_discover"] == "glm-5.3"
    assert st["zai_api_key"]["tail4"] == "BBBB"


def test_update_rejects_oversized_key_without_echo(cfg, ops_env):
    """key 长度上限 512(_tokens 同值);错误消息不回带值(永不回显纪律)。"""
    long_key = "k" * 513
    with pytest.raises(ValueError) as ei:
        cfg.update(zai_api_key=long_key)
    assert long_key not in str(ei.value)
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_corrupt_config_raises_loud(cfg, ops_env):
    """坏文件显式报错(RuntimeError)不静默当未配置:非法 JSON/顶层非映射/
    字段非字符串三路;消息不含字段值。"""
    p = _plant(ops_env, {})
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()
    p.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()
    p.write_text(json.dumps({"model_health": 42}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()


def test_status_env_fallback_key_and_models(cfg, ops_env, monkeypatch):
    """未配置时回落 effective env:key 状态按 env 值;模型 env 覆盖在
    status 可见(operator 链,spawn 同链)。"""
    monkeypatch.setenv("ZAI_CODING_CN_API_KEY", "env-fallback-key-7777")
    monkeypatch.setenv("OPS_MODEL_HEALTH", "glm-5.3-flashx")
    st = cfg.status()
    assert st["zai_api_key"] == {"configured": True, "tail4": "7777"}
    assert st["model_health"] == "glm-5.3-flashx"
    assert st["model_discover"] == DEFAULT_DISCOVER  # env 未设 → 缺省


def test_status_config_beats_env(cfg, ops_env, monkeypatch):
    """配置优先于 env(同名字段配置赢;key 同链)。"""
    _plant(ops_env, {"model_health": "glm-5.3-highspeed",
                     "zai_api_key": "cfg-wins-key-2222"})
    monkeypatch.setenv("OPS_MODEL_HEALTH", "glm-4.6v")
    monkeypatch.setenv("ZAI_CODING_CN_API_KEY", "env-loses-key-1111")
    st = cfg.status()
    assert st["model_health"] == "glm-5.3-highspeed"
    assert st["zai_api_key"] == {"configured": True, "tail4": "2222"}


# ── B. 路由层(GET/PUT /api/ops/agent-config;鉴权/形状/422/永不回显)──


@pytest.fixture
def admin_env(ops_env, auth_env):
    return ops_env


def test_config_routes_require_admin(admin_env, auth_client):
    for method, body in (("get", None), ("put", {"model_health": "glm-5.3"})):
        r = auth_client.request(method, "/api/ops/agent-config", json=body)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_get_route_shape_defaults(admin_env, client_as_admin):
    r = client_as_admin.get("/api/ops/agent-config")
    assert r.status_code == 200
    body = r.json()
    assert body["model_health"] == DEFAULT_HEALTH
    assert body["model_discover"] == DEFAULT_DISCOVER
    assert body["zai_api_key"] == {"configured": False, "tail4": None}
    assert body["allowed_models"] == MODEL_CATALOG


def test_put_then_get_roundtrip_no_key_echo(admin_env, client_as_admin):
    """PUT → 200 状态回显(tail4,无完整 key);GET 同形;盘上真落 key。"""
    r = client_as_admin.put("/api/ops/agent-config", json={
        "model_health": "glm-4.6v", "model_discover": "glm-5.3-highspeed",
        "zai_api_key": "sk-route-SECRET-4321"})
    assert r.status_code == 200
    assert "sk-route-SECRET-4321" not in r.text
    assert r.json()["zai_api_key"] == {"configured": True, "tail4": "4321"}
    g = client_as_admin.get("/api/ops/agent-config")
    assert g.status_code == 200
    assert "sk-route-SECRET-4321" not in g.text
    assert g.json()["model_health"] == "glm-4.6v"
    disk = json.loads((admin_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["zai_api_key"] == "sk-route-SECRET-4321"


def test_put_unknown_model_422(admin_env, client_as_admin):
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"model_health": "not-a-model"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "glm-5.3-flashx" in r.json()["error"]["message"]  # 消息带闭集可读
    assert not (admin_env / "ops" / CONFIG_FILE).exists()  # 坏入参零写


def test_put_blank_key_keeps_current(admin_env, client_as_admin):
    client_as_admin.put("/api/ops/agent-config", json={"zai_api_key": "sk-aa-ZZZZ"})
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"model_discover": "glm-4.6v", "zai_api_key": ""})
    assert r.status_code == 200
    assert r.json()["zai_api_key"] == {"configured": True, "tail4": "ZZZZ"}
    assert r.json()["model_discover"] == "glm-4.6v"


def test_put_oversized_key_422_no_echo(admin_env, client_as_admin):
    long_key = "x" * 600
    r = client_as_admin.put("/api/ops/agent-config", json={"zai_api_key": long_key})
    assert r.status_code == 422
    assert long_key not in r.text
    assert not (admin_env / "ops" / CONFIG_FILE).exists()


def test_corrupt_config_routes_500(admin_env, client_as_admin):
    _plant(admin_env, {})
    (admin_env / "ops" / CONFIG_FILE).write_text("{{broken", encoding="utf-8")
    g = client_as_admin.get("/api/ops/agent-config")
    assert g.status_code == 500
    assert g.json()["error"]["code"] == "internal"
    p = client_as_admin.put("/api/ops/agent-config", json={"model_health": "glm-5.3"})
    assert p.status_code == 500
    assert p.json()["error"]["code"] == "internal"
