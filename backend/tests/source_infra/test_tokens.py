"""sources-redesign Task 1 — _tokens store + admin API + 源使用点读取回归.

裁决基线(plan 2026-10-17 grill,已冻结):
- UI 值优先于 .env:load() 覆盖 os.environ;tokens.json 落 DATA_DIR(数据卷)
- token 完整值永不回显:出参仅 configured+tail4(≤4 字符);日志不打值
- 清除回落 _BOOT_SNAPSHOT(启动快照;.env 五 key 保留不动是其前提)
- 源侧一律使用点读取:env 热更即时生效,无需重建实例
"""
import json
import logging
import os
import stat

import pytest

from ipdb import _registry
from ipdb import _tokens

MANAGED_VARS = ["ABUSEIPDB_API_KEY", "IPINFO_TOKEN", "IP2PROXY_TOKEN",
               "OTX_API_KEY", "ABUSECH_AUTH_KEY"]

# 双源共享 key 的冻结映射(env var → 两源);票 #276 ABUSECH 扩裁入表,
# 与 OTX 同模式
DUAL_SOURCE_VARS = {"OTX_API_KEY": ["otx", "otx_subscribed"],
                    "ABUSECH_AUTH_KEY": ["threatfox", "urlhaus"]}


@pytest.fixture
def token_env(tmp_path, monkeypatch):
    """DATA_DIR 指向 tmp + 五个受管 env 清零(monkeypatch 自动还原 environ)。"""
    for var in MANAGED_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(_registry, "DATA_DIR", tmp_path)
    return tmp_path


# ── store ──

def test_load_missing_file_is_noop(token_env):
    _tokens.load()
    assert all(os.environ.get(v) is None for v in MANAGED_VARS)


def test_load_overrides_env_ui_priority(token_env, monkeypatch):
    (token_env / "tokens.json").write_text(
        json.dumps({"IPINFO_TOKEN": "ui-val"}), encoding="utf-8")
    monkeypatch.setenv("IPINFO_TOKEN", "boot-val")   # .env 注入的启动值
    _tokens.load()
    assert os.environ["IPINFO_TOKEN"] == "ui-val"


def test_load_ignores_foreign_keys_and_blank_values(token_env):
    (token_env / "tokens.json").write_text(json.dumps(
        {"IPINFO_TOKEN": "  ", "UNMANAGED_VAR": "x"}), encoding="utf-8")
    _tokens.load()
    assert "IPINFO_TOKEN" not in os.environ
    assert "UNMANAGED_VAR" not in os.environ


def test_load_bad_json_noop_with_warning(token_env, caplog, monkeypatch):
    (token_env / "tokens.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("IPINFO_TOKEN", "boot-val")
    with caplog.at_level(logging.WARNING, logger="ipdb._tokens"):
        _tokens.load()
    assert os.environ["IPINFO_TOKEN"] == "boot-val"
    assert "tokens.json" in caplog.text


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root 读文件不受 chmod 000 限制")
def test_load_unreadable_file_noop_with_warning(token_env, caplog):
    # 终审 I-1:重部署卷权限/UID 变化 → OSError 不得穿到 lifespan brick 启动
    path = token_env / "tokens.json"
    path.write_text(json.dumps({"IPINFO_TOKEN": "ui-val"}), encoding="utf-8")
    path.chmod(0o000)
    with caplog.at_level(logging.WARNING, logger="ipdb._tokens"):
        _tokens.load()
    assert "IPINFO_TOKEN" not in os.environ
    assert "tokens.json" in caplog.text


def test_set_token_persists_and_applies(token_env):
    _tokens.set_token("IPINFO_TOKEN", "abcd1234")
    stored = json.loads((token_env / "tokens.json").read_text(encoding="utf-8"))
    assert stored == {"IPINFO_TOKEN": "abcd1234"}
    assert os.environ["IPINFO_TOKEN"] == "abcd1234"


def test_set_token_file_mode_0600_no_tmp_left(token_env):
    _tokens.set_token("IPINFO_TOKEN", "abcd1234")
    mode = stat.S_IMODE((token_env / "tokens.json").stat().st_mode)
    assert mode == 0o600
    assert list(token_env.glob("tokens.json.tmp")) == []


def test_set_token_rejects_unknown_var_empty_and_overlong(token_env):
    with pytest.raises(ValueError):
        _tokens.set_token("NOT_MANAGED", "x")
    with pytest.raises(ValueError):
        _tokens.set_token("IPINFO_TOKEN", "   ")
    with pytest.raises(ValueError):
        _tokens.set_token("IPINFO_TOKEN", "x" * 513)


def test_clear_falls_back_to_boot_snapshot(token_env, monkeypatch):
    monkeypatch.setitem(_tokens._BOOT_SNAPSHOT, "IPINFO_TOKEN", "boot-val")
    _tokens.set_token("IPINFO_TOKEN", "ui-val")
    _tokens.clear_token("IPINFO_TOKEN")
    assert os.environ["IPINFO_TOKEN"] == "boot-val"
    assert "IPINFO_TOKEN" not in json.loads(
        (token_env / "tokens.json").read_text(encoding="utf-8"))


def test_clear_pops_when_no_boot_value(token_env, monkeypatch):
    monkeypatch.setitem(_tokens._BOOT_SNAPSHOT, "IPINFO_TOKEN", None)
    _tokens.set_token("IPINFO_TOKEN", "ui-val")
    _tokens.clear_token("IPINFO_TOKEN")
    assert os.environ.get("IPINFO_TOKEN") is None


def test_clear_rejects_unknown_var(token_env):
    with pytest.raises(ValueError):
        _tokens.clear_token("NOT_MANAGED")


def test_status_reports_configured_and_tail4_only(token_env, monkeypatch):
    monkeypatch.setenv("ABUSEIPDB_API_KEY", "supersecret-token")
    out = _tokens.status()
    by_var = {r["env_var"]: r for r in out}
    assert set(by_var) == set(MANAGED_VARS)
    assert by_var["ABUSEIPDB_API_KEY"] == {
        "env_var": "ABUSEIPDB_API_KEY", "sources": ["abuseipdb"],
        "configured": True, "tail4": "oken"}
    assert by_var["IPINFO_TOKEN"]["configured"] is False
    assert by_var["IPINFO_TOKEN"]["tail4"] is None
    assert by_var["OTX_API_KEY"]["sources"] == ["otx", "otx_subscribed"]
    assert by_var["ABUSECH_AUTH_KEY"]["sources"] == ["threatfox", "urlhaus"]
    # 死常量复活(终审 P2):DUAL_SOURCE_VARS 与 store 冻结集对账——
    # 恰好是「一 key 双源」的 var 闭集,值也逐字对齐,漂移即红。
    assert DUAL_SOURCE_VARS == {v: list(s) for v, s in _tokens.MANAGED.items()
                                if len(s) == 2}
    assert "supersecret-token" not in json.dumps(out)


# ── 一 key 双源:设/清一次,两源同明暗(票 #276;OTX 同模式)──

def test_abusech_one_key_lights_both_sources_set_once(token_env, monkeypatch):
    # 双源共享一个 env var:set_token 一次,threatfox/urlhaus 同亮
    monkeypatch.setitem(_tokens._BOOT_SNAPSHOT, "ABUSECH_AUTH_KEY", None)
    _tokens.set_token("ABUSECH_AUTH_KEY", "abusech-k3y")
    assert os.environ["ABUSECH_AUTH_KEY"] == "abusech-k3y"
    row = {r["env_var"]: r for r in _tokens.status()}["ABUSECH_AUTH_KEY"]
    assert row["sources"] == ["threatfox", "urlhaus"]   # 两源共用同一行/同一 var
    assert row["configured"] is True
    assert row["tail4"] == "-k3y"   # "abusech-k3y"[-4:]
    # 照 OTX 模式:双源共享 key 在冻结映射里同表
    assert _tokens.MANAGED["ABUSECH_AUTH_KEY"] == ["threatfox", "urlhaus"]


def test_abusech_clear_once_darks_both_sources_no_boot_value(
        token_env, monkeypatch):
    # 无 env 启动值:清除即从 environ 移除,两源同灭(回落语义对 5 变量成立)
    monkeypatch.setitem(_tokens._BOOT_SNAPSHOT, "ABUSECH_AUTH_KEY", None)
    _tokens.set_token("ABUSECH_AUTH_KEY", "abusech-k3y")
    _tokens.clear_token("ABUSECH_AUTH_KEY")
    assert os.environ.get("ABUSECH_AUTH_KEY") is None
    row = {r["env_var"]: r for r in _tokens.status()}["ABUSECH_AUTH_KEY"]
    assert row["configured"] is False
    assert row["tail4"] is None
    assert "ABUSECH_AUTH_KEY" not in json.loads(
        (token_env / "tokens.json").read_text(encoding="utf-8"))


def test_status_reads_effective_environ(token_env, monkeypatch):
    # effective = 当前 os.environ(.env 注入的启动值计入 configured)
    monkeypatch.setenv("IP2PROXY_TOKEN", "startup-value")
    by_var = {r["env_var"]: r for r in _tokens.status()}
    assert by_var["IP2PROXY_TOKEN"]["configured"] is True
    assert by_var["IP2PROXY_TOKEN"]["tail4"] == "alue"


# ── admin API ──

API = "/api/admin/tokens"


def test_tokens_api_requires_admin(auth_client, token_env):
    probes = [("get", API, None),
              ("put", f"{API}/IPINFO_TOKEN", {"value": "x"}),
              ("delete", f"{API}/IPINFO_TOKEN", None)]
    for method, path, body in probes:
        r = (auth_client.request(method, path, json=body) if body is not None
             else auth_client.request(method, path))
        assert r.status_code == 401, f"{method} {path} 不应匿名可达"
        assert r.json()["error"]["code"] == "unauthorized"


def test_put_unknown_var_422_envelope(client_as_admin, token_env):
    r = client_as_admin.put(f"{API}/NOT_MANAGED", json={"value": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_delete_unknown_var_422_envelope(client_as_admin, token_env):
    r = client_as_admin.delete(f"{API}/NOT_MANAGED")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_put_then_status_reflects(client_as_admin, token_env):
    r = client_as_admin.put(f"{API}/IPINFO_TOKEN", json={"value": "abcd1234"})
    assert r.status_code == 204
    assert os.environ["IPINFO_TOKEN"] == "abcd1234"
    assert json.loads(
        (token_env / "tokens.json").read_text(encoding="utf-8"))["IPINFO_TOKEN"] \
        == "abcd1234"
    rows = {row["env_var"]: row for row in client_as_admin.get(API).json()}
    assert rows["IPINFO_TOKEN"]["configured"] is True
    assert rows["IPINFO_TOKEN"]["tail4"] == "1234"


def test_delete_then_status_reflects(client_as_admin, token_env, monkeypatch):
    monkeypatch.setitem(_tokens._BOOT_SNAPSHOT, "IPINFO_TOKEN", None)
    client_as_admin.put(f"{API}/IPINFO_TOKEN", json={"value": "abcd1234"})
    r = client_as_admin.delete(f"{API}/IPINFO_TOKEN")
    assert r.status_code == 204
    assert os.environ.get("IPINFO_TOKEN") is None
    rows = {row["env_var"]: row for row in client_as_admin.get(API).json()}
    assert rows["IPINFO_TOKEN"]["configured"] is False
    assert rows["IPINFO_TOKEN"]["tail4"] is None


def test_api_and_logs_never_echo_full_value(client_as_admin, token_env, caplog):
    token = "abcd1234-supersecret"
    with caplog.at_level(logging.DEBUG):
        put = client_as_admin.put(f"{API}/IPINFO_TOKEN", json={"value": token})
        assert put.status_code == 204
        listing = client_as_admin.get(API)
        delete = client_as_admin.delete(f"{API}/IPINFO_TOKEN")
        assert delete.status_code == 204
    assert token not in put.text
    assert token not in listing.text
    assert token not in caplog.text


def test_put_overlong_value_422_without_echo(client_as_admin, token_env):
    value = "x" * 513
    r = client_as_admin.put(f"{API}/IPINFO_TOKEN", json={"value": value})
    assert r.status_code == 422
    assert value not in r.text   # 永不回显硬约束:校验失败也不带值


# ── 源使用点读取回归(mock env 变更后无需重建实例)──

def test_abuseipdb_reads_key_at_download_time(tmp_path, monkeypatch):
    import ipdb._sources.abuseipdb as mod
    from ipdb._sources.abuseipdb import AbuseIPDBSource
    monkeypatch.delenv("ABUSEIPDB_API_KEY", raising=False)
    seen = {}

    def fake_download_file(url, dest, token=None, headers=None, **kw):
        seen["key"] = headers["Key"]
        dest.write_bytes(json.dumps({"data": [{"ipAddress": "1.2.3.4"}]}).encode())

    monkeypatch.setattr(mod, "download_file", fake_download_file)
    s = AbuseIPDBSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError):
        s.download()                                  # 未配置:构造期不炸,download 期炸
    monkeypatch.setenv("ABUSEIPDB_API_KEY", "k-late")  # env 热更,同一实例
    s.download()
    assert seen["key"] == "k-late"


def test_ipinfo_lite_reads_token_at_download_time(tmp_path, monkeypatch):
    import gzip as _gzip
    import ipdb._sources.ipinfo_lite as mod
    from ipdb._sources.ipinfo_lite import IPinfoLiteSource
    monkeypatch.delenv("IPINFO_TOKEN", raising=False)
    seen = {}

    def fake_download_file(url, dest, token=None, headers=None, **kw):
        seen["url"] = url
        dest.write_bytes(_gzip.compress(b"network,country_code\n1.1.1.0/24,AU\n"))

    monkeypatch.setattr(mod, "download_file", fake_download_file)
    s = IPinfoLiteSource(data_dir=tmp_path)
    s.download()                                      # 未配置:warning + no-op
    assert seen == {}
    monkeypatch.setenv("IPINFO_TOKEN", "late-token")   # env 热更,同一实例
    s.download()
    assert "late-token" in seen["url"]


def test_ip2proxy_reads_token_at_download_time(tmp_path, monkeypatch):
    from ipdb._sources.ip2proxy import IP2ProxySource
    monkeypatch.delenv("IP2PROXY_TOKEN", raising=False)
    s = IP2ProxySource(data_dir=tmp_path)
    assert s._url == ""
    monkeypatch.setenv("IP2PROXY_TOKEN", "late-token")  # env 热更,同一实例
    assert "late-token" in s._url


def test_threatfox_reads_key_at_download_time(tmp_path, monkeypatch):
    # 票 #276 B 裁决(2026-11-02 supervisor):ABUSECH_AUTH_KEY 入 MANAGED 后,
    # __init__ 期捕获使 web 面填值到不了 download()(实例先于 _tokens.load()
    # 构造,热更即断,重启也救不回)——改用点读取,照其余四源模式。
    import ipdb._sources.threatfox as mod
    from ipdb._sources.threatfox import ThreatFoxSource
    monkeypatch.delenv("ABUSECH_AUTH_KEY", raising=False)
    seen = {}

    def fake_download_file(url, dest, token=None, headers=None, secret=None, **kw):
        seen["url"] = url
        seen["secret"] = secret
        # 非 zip 体带 first_seen_utc 列头即可过 200-OK 坏体守卫(票 #159)
        dest.write_bytes(b"first_seen_utc,ioc_value\n2026-01-01,\"1.2.3.4\"\n")

    monkeypatch.setattr(mod, "download_file", fake_download_file)
    s = ThreatFoxSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError):
        s.download()                                    # 未配置:构造期不炸,download 期炸
    monkeypatch.setenv("ABUSECH_AUTH_KEY", "late-key")  # env 热更,同一实例
    s.download()
    assert "/late-key/" in seen["url"]                  # keyed URL 使用点取新值
    assert seen["secret"] == "late-key"
    assert b"first_seen_utc" in (tmp_path / "threatfox.csv").read_bytes()


def test_urlhaus_reads_key_at_download_time(tmp_path, monkeypatch):
    # 同上(B 裁决):urlhaus 同改使用点读取
    import ipdb._sources.urlhaus as mod
    from ipdb._sources.urlhaus import URLhausSource
    monkeypatch.delenv("ABUSECH_AUTH_KEY", raising=False)
    seen = {}

    def fake_download_file(url, dest, token=None, headers=None, secret=None, **kw):
        seen["url"] = url
        seen["secret"] = secret
        # # 注释块开头即可过 200-OK 坏体守卫(票 #159)
        dest.write_bytes(b"# urlhaus online\nid,dateadded,url\n")

    monkeypatch.setattr(mod, "download_file", fake_download_file)
    s = URLhausSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError):
        s.download()                                    # 未配置:构造期不炸,download 期炸
    monkeypatch.setenv("ABUSECH_AUTH_KEY", "late-key")  # env 热更,同一实例
    s.download()
    assert "/late-key/" in seen["url"]
    assert seen["secret"] == "late-key"
    assert b"id,dateadded" in (tmp_path / "urlhaus.csv").read_bytes()
