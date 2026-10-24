"""运营 agent 配置面(票 #140 立,票 #143 多供应商扩面,TDD 红先行)。

钉住契约(期望值取自独立真源,不从被测模块导入常量防套套逻辑):

- 配置文件 = ops 树 agent-config.json(字段 model_health/model_discover/
  api_keys{providerId:key};旧 zai_api_key 兼容读 alias,api_keys 赢);原子写
  沿 _ops_store 基座;缺文件 = 未配置(GET 零副作用,不建文件);
- 模型值 = qualified "provider/model"(裸值=缺省 provider zai-coding-cn,#140
  既有盘上值向后兼容);校验闭集 = 动态目录(node 子调用 dump,经
  IP_RADAR_OPS_CATALOG_CMD 测试面注入假 dump),dump 失败兜底 #140 五值闭集
  (catalog_source=fallback 显式标注);PUT 未知 provider/模型 422,先校验后
  落盘(坏入参零写);
- key 永不回显:GET/PUT 出参 api_keys/tool_keys 只 {configured, tail4}(沿
  TokenStatus 先例);响应/错误消息绝无完整 key;api_keys 空串/缺省 = 保持
  不改(无清除面);tool_keys 值非空校验(空串 422;槽闭集 {jina},PR3a);
- 优先级链:配置 > 进程 effective env > models.mjs 缺省(env 兜底链不动);
- 目录缓存 TTL:同窗两次 status 只 dump 一次;
- 坏文件显式报错不静默(非法 JSON/非映射/字段非 str/api_keys 非映射 →
  RuntimeError → GET/PUT 500;无证据≠清白,不伪装成未配置);
- admin 鉴权沿 P2/P3 _ADMIN_DEPS 惯例(匿名 401)。

spawn 注入(OPS_MODEL_*(qualified 透传)/ZAI_CODING_CN_API_KEY/OPS_AUTH 物化
auth.json,每次 spawn 现读=改完即生效)在 test_ops_rounds.py 用假 agent 真过
spawn 层钉。
"""

import json
import os
import sys
from pathlib import Path

import pytest

# ── 冻结件期望值(独立真源)──
# 兜底目录 = #140 时期实测闭集五值(动态目录失败时的闭集,逐字保留)
FALLBACK_CATALOG = {"zai-coding-cn": ["glm-4.6v", "glm-5.3", "glm-5.3-flash",
                                      "glm-5.3-highspeed", "glm-5.3-flashx"]}
# models.mjs DEFAULTS 逐字(独立抄录,不导入被测模块;裸值归 zai)
DEFAULT_HEALTH = "zai-coding-cn/glm-5.3-flash"
DEFAULT_DISCOVER = "zai-coding-cn/glm-5.3"
CONFIG_FILE = "agent-config.json"

# 假目录 dump(测试注入;两家 + 跨家同名模型,钉 provider 作用域)
FAKE_CATALOG = {
    "zai-coding-cn": [
        {"id": "glm-5.3", "name": "GLM-5.3", "cost": {"input": 1.4, "output": 4.4, "cacheRead": 0.26, "cacheWrite": 0}},
        {"id": "glm-5.3-flash", "name": "GLM-5.3-Flash", "cost": None},
    ],
    "fake-prov": [
        {"id": "glm-5.3", "name": "同名家", "cost": None},
        {"id": "fake-7b", "name": "Fake 7B", "cost": {"input": 0.1, "output": 0.2, "cacheRead": 0, "cacheWrite": 0}},
    ],
}


@pytest.fixture
def cfg():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误;P1 同型)。"""
    import ipdb._ops_config as ops_config
    return ops_config


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp;剥掉三类 effective env(开发机 .env 可能灌 zai key,
    剥净保证「未配置」基线确定);目录缓存清零(模块级缓存在测试间会串)。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    for var in ("ZAI_CODING_CN_API_KEY", "OPS_MODEL_HEALTH", "OPS_MODEL_DISCOVER"):
        monkeypatch.delenv(var, raising=False)
    import ipdb._ops_config as ops_config
    monkeypatch.setattr(ops_config, "_catalog_cache", {"at": None, "data": None, "source": None})
    return tmp_path


@pytest.fixture
def fake_catalog(tmp_path, monkeypatch, ops_env):
    """假 dump 脚本:吐 FAKE_CATALOG;调用次数落 hits 文件(TTL 断言面)。"""
    script = tmp_path / "fake-catalog.py"
    script.write_text(
        "import sys\n"
        "open(sys.argv[1], 'a').write('x')\n"
        # 嵌双层 json.dumps(串字面量,Python 源安全;单层会把 null/true 写成裸名)
        f"print({json.dumps(json.dumps(FAKE_CATALOG))})\n", encoding="utf-8")
    hits = tmp_path / "catalog-hits"
    monkeypatch.setenv("IP_RADAR_OPS_CATALOG_CMD", f"{sys.executable} {script} {hits}")
    return hits


def _plant(ops_env: Path, cfg: dict) -> Path:
    """直接落配置文件(独立于被测模块的写入面)。"""
    (ops_env / "ops").mkdir(parents=True, exist_ok=True)
    p = ops_env / "ops" / CONFIG_FILE
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def _fallback_shape(cat: dict) -> dict:
    """兜底目录的 dump 形状(id/name/cost 三键,cost=None——后端手抄不带价)。"""
    return {pid: [{"id": i, "name": i, "cost": None} for i in ids]
            for pid, ids in cat.items()}


# ── A. 存取面(_ops_config)──────────────────────────────────────────


def test_status_absent_config_defaults_and_dynamic_catalog(cfg, ops_env, fake_catalog):
    """缺文件 = 未配置:模型回落 models.mjs 缺省(qualified 归一)、api_keys 空、
    catalog = 动态 dump、catalog_source=dynamic;GET 语义零副作用(不建文件)。"""
    st = cfg.status()
    assert st["model_health"] == DEFAULT_HEALTH
    assert st["model_discover"] == DEFAULT_DISCOVER
    assert st["api_keys"] == {}
    assert st["catalog"] == FAKE_CATALOG
    assert st["catalog_source"] == "dynamic"
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_status_catalog_ttl_cache_single_dump(cfg, ops_env, fake_catalog):
    """同 TTL 窗两次 status 只 dump 一次(调用计数恒 1)。"""
    cfg.status()
    cfg.status()
    assert fake_catalog.read_text(encoding="utf-8") == "x"


def test_status_catalog_failure_falls_back_closed_set(cfg, ops_env, monkeypatch):
    """dump 失败(node 缺失/cmd 炸)→ 兜底 #140 五值闭集 + catalog_source=
    fallback;校验门同用兜底目录(zai 可配、别家 422)。"""
    monkeypatch.setenv("IP_RADAR_OPS_CATALOG_CMD", f"{sys.executable} -c 'import sys; sys.exit(3)'")
    st = cfg.status()
    assert st["catalog"] == _fallback_shape(FALLBACK_CATALOG)
    assert st["catalog_source"] == "fallback"
    cfg.update(model_health="glm-4.6v")  # 兜底目录内 zai 裸值可配
    with pytest.raises(ValueError):
        cfg.update(model_health="anthropic/claude-x")


def test_update_qualified_and_bare_roundtrip(cfg, ops_env, fake_catalog):
    """qualified 落盘回读;裸值归一为 zai qualified(盘上单拼写);跨家同名
    模型按 provider 各自可配。"""
    st = cfg.update(model_health="fake-prov/glm-5.3", model_discover="glm-5.3-flash")
    assert st["model_health"] == "fake-prov/glm-5.3"
    assert st["model_discover"] == "zai-coding-cn/glm-5.3-flash"  # 裸值归一
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["model_health"] == "fake-prov/glm-5.3"
    assert disk["model_discover"] == "zai-coding-cn/glm-5.3-flash"


def test_update_rejects_unknown_before_write(cfg, ops_env, fake_catalog):
    """目录外模型 422 面(ValueError):未知 provider / provider 内未知模型 /
    空串;写前门:坏入参零写(文件不落地)。"""
    for bad in ("no-such-prov/foo", "fake-prov/no-such-model", "gpt-4o", ""):
        with pytest.raises(ValueError):
            cfg.update(model_health=bad)
        with pytest.raises(ValueError):
            cfg.update(model_discover=bad)
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_update_rejects_unknown_model_message_lists_provider_ids(cfg, ops_env, fake_catalog):
    """422 消息带该家目录可读(前 8 型),不带别家(id 撞家时能定位)。"""
    with pytest.raises(ValueError) as ei:
        cfg.update(model_health="fake-prov/no-such-model")
    assert "fake-prov/no-such-model" in str(ei.value)
    assert "fake-7b" in str(ei.value)


def test_update_api_keys_persists_and_reports_tail4(cfg, ops_env, fake_catalog):
    """api_keys 逐家写:盘上 {providerId:key};出参只 configured+tail4,全家
    JSON 无完整 key;部分更新未涉家保留。"""
    st = cfg.update(api_keys={"fake-prov": "sk-live-AAAA", "zai-coding-cn": "sk-zai-BBBB"})
    assert st["api_keys"] == {
        "fake-prov": {"configured": True, "tail4": "AAAA"},
        "zai-coding-cn": {"configured": True, "tail4": "BBBB"},
    }
    assert "sk-live-AAAA" not in json.dumps(st, ensure_ascii=False)
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["api_keys"] == {"fake-prov": "sk-live-AAAA", "zai-coding-cn": "sk-zai-BBBB"}
    cfg.update(api_keys={"third-prov": "sk-3-CCCC"})
    st = cfg.status()
    assert st["api_keys"]["fake-prov"]["tail4"] == "AAAA"  # 未涉家保留
    assert st["api_keys"]["third-prov"]["tail4"] == "CCCC"


def test_update_blank_key_keeps_current(cfg, ops_env, fake_catalog):
    """key 空串/纯空白 = 该家保持不改(沿票面:无清除面);缺省 dict = 整体不动。"""
    cfg.update(api_keys={"fake-prov": "sk-first-AAAA"})
    cfg.update(api_keys={"fake-prov": "", "zai-coding-cn": "   "})
    st = cfg.status()
    assert st["api_keys"] == {"fake-prov": {"configured": True, "tail4": "AAAA"}}
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["api_keys"] == {"fake-prov": "sk-first-AAAA"}


def test_update_rejects_bad_api_keys_without_echo(cfg, ops_env, fake_catalog):
    """provider id 形状坏 / key 超长 → ValueError,消息不回带 key 值;坏入参零写。"""
    long_key = "k" * 513
    with pytest.raises(ValueError) as ei:
        cfg.update(api_keys={"Bad_Provider": "sk-x"})
    assert "Bad_Provider" in str(ei.value)  # provider 名可回(非密)
    with pytest.raises(ValueError) as ei2:
        cfg.update(api_keys={"fake-prov": long_key})
    assert long_key not in str(ei2.value)
    assert not (ops_env / "ops" / CONFIG_FILE).exists()


def test_update_tool_keys_persists_and_masks(cfg, ops_env, fake_catalog):
    """PR3a 发现通道扩槽:tool_keys={jina:key} 写盘往返;出参只 configured+
    tail4(同 api_keys 遮蔽面);未涉字段保留。"""
    st = cfg.update(tool_keys={"jina": "jina-live-KEY9988"})
    assert st["tool_keys"] == {"jina": {"configured": True, "tail4": "9988"}}
    assert "jina-live-KEY9988" not in json.dumps(st, ensure_ascii=False)
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["tool_keys"] == {"jina": "jina-live-KEY9988"}
    cfg.update(api_keys={"fake-prov": "sk-x-AAAA"})  # 未涉字段保留
    assert cfg.status()["tool_keys"]["jina"]["tail4"] == "9988"


def test_update_rejects_bad_tool_keys_without_echo(cfg, ops_env, fake_catalog):
    """值空串/纯空白 = 422(非空校验,与 api_keys「空=保持不改」不同——票面
    明写);槽外 id = 422(防拼写静默失效);超长拒;坏入参零写;消息不回带 key 值。"""
    for bad in ("", "   "):
        with pytest.raises(ValueError) as ei:
            cfg.update(tool_keys={"jina": bad})
        assert "非空" in str(ei.value)
    with pytest.raises(ValueError) as ei2:
        cfg.update(tool_keys={"unknown-tool": "sk-x"})
    assert "unknown-tool" in str(ei2.value)  # 槽名可回(非密)
    long_key = "j" * 513
    with pytest.raises(ValueError) as ei3:
        cfg.update(tool_keys={"jina": long_key})
    assert long_key not in str(ei3.value)
    assert not (ops_env / "ops" / CONFIG_FILE).exists()  # 坏入参零写


def test_round_env_injects_jina_key(cfg, ops_env, fake_catalog, monkeypatch):
    """_round_env:tool_keys.jina 配置 → env 注入 JINA_API_KEY + 物化
    web-search.json(pi-web-access MCP 路由单源:searchRouting 回退链
    duckduckgo→jina + jinaApiKey);未配置不注入 env、链仍物化(duckduckgo
    起步零配置一发即活);PI_CODING_AGENT_DIR 指路 ops 树(auth.json 同型)。"""
    from ipdb import _ops_rounds
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    env = _ops_rounds._round_env()
    assert "JINA_API_KEY" not in env
    assert env["PI_CODING_AGENT_DIR"] == str(ops_env / "ops")
    disk = json.loads((ops_env / "ops" / "web-search.json").read_text(encoding="utf-8"))
    assert disk["searchRouting"]["providers"] == ["duckduckgo", "jina"]  # 回退链(选型注见 _ops_rounds)
    assert "jinaApiKey" not in disk  # 未配 key:duckduckgo 起步,jina 可用性门后置
    cfg.update(tool_keys={"jina": "jina-env-9999"})
    env = _ops_rounds._round_env()
    assert env["JINA_API_KEY"] == "jina-env-9999"
    disk = json.loads((ops_env / "ops" / "web-search.json").read_text(encoding="utf-8"))
    assert disk["jinaApiKey"] == "jina-env-9999"  # 包的 web-search.json 键名


def test_legacy_zai_api_key_alias_read(cfg, ops_env, fake_catalog):
    """旧 zai_api_key 兼容读 alias:视作 api_keys['zai-coding-cn'];新 api_keys
    同家并存时 api_keys 赢;update 不改写/不清除旧字段。"""
    _plant(ops_env, {"zai_api_key": "sk-legacy-7777"})
    st = cfg.status()
    assert st["api_keys"]["zai-coding-cn"] == {"configured": True, "tail4": "7777"}
    cfg.update(api_keys={"zai-coding-cn": "sk-new-2222"})
    st = cfg.status()
    assert st["api_keys"]["zai-coding-cn"]["tail4"] == "2222"  # api_keys 赢
    disk = json.loads((ops_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["zai_api_key"] == "sk-legacy-7777"  # 旧字段原样保留


def test_status_env_fallback_key_and_models(cfg, ops_env, fake_catalog, monkeypatch):
    """未配置时回落 effective env:zai env key 在 api_keys 状态可见;模型 env
    覆盖(qualified/裸值皆透传归一)在 status 可见(operator 链,spawn 同链)。"""
    monkeypatch.setenv("ZAI_CODING_CN_API_KEY", "env-fallback-key-7777")
    monkeypatch.setenv("OPS_MODEL_HEALTH", "fake-prov/fake-7b")
    st = cfg.status()
    assert st["api_keys"]["zai-coding-cn"] == {"configured": True, "tail4": "7777"}
    assert st["model_health"] == "fake-prov/fake-7b"
    assert st["model_discover"] == DEFAULT_DISCOVER  # env 未设 → 缺省
    monkeypatch.setenv("OPS_MODEL_HEALTH", "glm-5.3-flash")  # 裸值 env 归一
    assert cfg.status()["model_health"] == "zai-coding-cn/glm-5.3-flash"


def test_status_config_beats_env(cfg, ops_env, fake_catalog, monkeypatch):
    """配置优先于 env(同名字段配置赢;key 同链)。"""
    _plant(ops_env, {"model_health": "fake-prov/glm-5.3",
                     "api_keys": {"fake-prov": "cfg-wins-key-2222"}})
    monkeypatch.setenv("OPS_MODEL_HEALTH", "glm-5.3")
    monkeypatch.setenv("ZAI_CODING_CN_API_KEY", "env-loses-key-1111")
    st = cfg.status()
    assert st["model_health"] == "fake-prov/glm-5.3"
    assert st["api_keys"]["fake-prov"]["tail4"] == "2222"
    # zai 未配置 → env 兜底 key 仍可见（#140 链不动）；别家 key 面与 zai env 无关
    assert st["api_keys"]["zai-coding-cn"]["tail4"] == "1111"


def test_corrupt_config_raises_loud(cfg, ops_env, fake_catalog):
    """坏文件显式报错(RuntimeError)不静默当未配置:非法 JSON/顶层非映射/
    字段非字符串/api_keys 非映射或值非字符串四路;消息不含字段值。"""
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
    p.write_text(json.dumps({"api_keys": ["not", "a", "map"]}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()
    p.write_text(json.dumps({"api_keys": {"fake-prov": 99}}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()
    p.write_text(json.dumps({"tool_keys": ["not", "a", "map"]}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()
    p.write_text(json.dumps({"tool_keys": {"jina": 99}}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        cfg.status()


# ── B. 路由层(GET/PUT /api/ops/agent-config;鉴权/形状/422/永不回显)──


@pytest.fixture
def admin_env(ops_env, fake_catalog, auth_env):
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
    assert body["api_keys"] == {}
    assert body["tool_keys"] == {}  # PR3a:未配置 = 空映射(真实现态)
    assert body["catalog"] == FAKE_CATALOG
    assert body["catalog_source"] == "dynamic"


def test_put_tool_keys_roundtrip_no_key_echo(admin_env, client_as_admin):
    """PUT tool_keys → 遮蔽回显;GET 同形;盘上真落 key(同 api_keys 面)。"""
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"tool_keys": {"jina": "jina-route-SECRET-7777"}})
    assert r.status_code == 200
    assert "jina-route-SECRET-7777" not in r.text
    assert r.json()["tool_keys"]["jina"] == {"configured": True, "tail4": "7777"}
    g = client_as_admin.get("/api/ops/agent-config")
    assert g.status_code == 200
    assert "jina-route-SECRET-7777" not in g.text
    assert g.json()["tool_keys"]["jina"]["tail4"] == "7777"
    disk = json.loads((admin_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["tool_keys"]["jina"] == "jina-route-SECRET-7777"


def test_put_tool_keys_blank_or_unknown_slot_422(admin_env, client_as_admin):
    """值空串 = 422(非空校验);槽外 id = 422;均零写。"""
    for bad in ({"jina": ""}, {"unknown-tool": "sk-x"}):
        r = client_as_admin.put("/api/ops/agent-config", json={"tool_keys": bad})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"
        assert not (admin_env / "ops" / CONFIG_FILE).exists()  # 坏入参零写


def test_put_then_get_roundtrip_no_key_echo(admin_env, client_as_admin):
    """PUT → 200 状态回显(tail4,无完整 key);GET 同形;盘上真落 key。"""
    r = client_as_admin.put("/api/ops/agent-config", json={
        "model_health": "fake-prov/fake-7b", "model_discover": "glm-5.3",
        "api_keys": {"fake-prov": "sk-route-SECRET-4321"}})
    assert r.status_code == 200
    assert "sk-route-SECRET-4321" not in r.text
    assert r.json()["api_keys"]["fake-prov"] == {"configured": True, "tail4": "4321"}
    g = client_as_admin.get("/api/ops/agent-config")
    assert g.status_code == 200
    assert "sk-route-SECRET-4321" not in g.text
    assert g.json()["model_health"] == "fake-prov/fake-7b"
    disk = json.loads((admin_env / "ops" / CONFIG_FILE).read_text(encoding="utf-8"))
    assert disk["api_keys"]["fake-prov"] == "sk-route-SECRET-4321"


def test_put_unknown_model_422(admin_env, client_as_admin):
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"model_health": "not-a-model"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "glm-5.3-flash" in r.json()["error"]["message"]  # 消息带目录可读
    assert not (admin_env / "ops" / CONFIG_FILE).exists()  # 坏入参零写


def test_put_blank_key_keeps_current(admin_env, client_as_admin):
    client_as_admin.put("/api/ops/agent-config",
                        json={"api_keys": {"fake-prov": "sk-aa-ZZZZ"}})
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"model_discover": "glm-5.3", "api_keys": {"fake-prov": ""}})
    assert r.status_code == 200
    assert r.json()["api_keys"]["fake-prov"] == {"configured": True, "tail4": "ZZZZ"}
    assert r.json()["model_discover"] == "zai-coding-cn/glm-5.3"


def test_put_oversized_key_422_no_echo(admin_env, client_as_admin):
    long_key = "x" * 600
    r = client_as_admin.put("/api/ops/agent-config",
                            json={"api_keys": {"fake-prov": long_key}})
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
