# backend/tests/lookup/test_scan_units.py
"""#444 A 步:按键序扫描(_scan.py)的一致性钉。

核心合同(规格 §4.2):扫描单元的 result 与「在同一地址上调查询接口」
逐字段相同——期望值一律走真查询接口(夹具源 load 进 _registry 后
lookup(ip, asof=T)),不用手搓期望形状。

夹具数据布局(四威胁源 + 一资产类源):
- abuseipdb(威胁,嵌套库):大网段 1.0.0.0/16 套小网段 1.0.2.0/24、
  单地址 1.0.2.9(小网段内,钉「单地址优先于覆盖网段」)、9.9.9.9(多源
  同址);v6 族 2606:4700::1 单地址 + 2a00:1450:4001::/48 网段。
- blocklist_de(威胁,不相交库):9.9.9.9 单地址 + 10.0.0.0/8(保留
  网络地址的网段单元)。
- firehol(威胁,不相交库):1.0.1.0/24、3.3.0.0/16、6.9.0.0/16 网段 +
  4.4.4.4 单地址。
- greensnow(威胁,手搭库):3.3.3.3 单地址带字典引用证据
  (encode_value_ref)、1.0.9.9 单地址(嵌套大网段内、小网段外)、
  8.0.0.0→8.0.0.10 非对齐范围(不恰为一个 CIDR → 跳过计数)。
- danmeuk_tor(资产类):9.9.9.9(有威胁源,该地址仍产单元)、5.5.5.5
  (只有资产类 → 不产单元)。

相位纪律(py-lmdb 同进程同路径禁双开):建库(rebuild 后关 env)→
夹具源 load + 算 oracle → 关读句柄 → 开扫描器 → close → 再 load_db。
"""
import orjson
import pytest
import lmdb

import ipaddress

from ipdb import _registry
from ipdb._scan import open_unit_scanner
from ipdb._sources._lmdb import (
    HARVEST_REV,
    encode_key,
    encode_value,
    encode_value_ref,
    rebuild_lmdb,
)

ASOF = 1_765_000_000.0

ABUSEIPDB_V4 = [
    ("1.0.0.0/16", [{"classification_type": "abuse-reports",
                     "verdict": "malicious", "reliability": 0.9,
                     "first_seen": "2026-01-01", "last_seen": "2026-02-01"}]),
    ("1.0.2.0/24", [{"classification_type": "abuse-reports",
                     "verdict": "malicious", "reliability": 0.95,
                     "first_seen": "2026-01-05", "last_seen": "2026-02-10"}]),
    ("1.0.2.9", [{"classification_type": "abuse-reports",
                  "verdict": "malicious", "reliability": 0.99,
                  "first_seen": "2026-03-01"}]),
    ("9.9.9.9", [{"classification_type": "abuse-reports",
                  "verdict": "malicious", "reliability": 0.9,
                  "first_seen": "2026-01-05", "last_seen": "2026-02-10"}]),
]
ABUSEIPDB_V6 = [
    ("2a00:1450:4001::/48", [{"classification_type": "abuse-reports",
                              "verdict": "malicious", "reliability": 0.9}]),
    ("2606:4700::1", [{"classification_type": "abuse-reports",
                       "verdict": "malicious", "reliability": 0.9}]),
]
BLOCKLIST_DE_V4 = [
    ("9.9.9.9", [{"classification_type": "blacklist",
                  "verdict": "malicious", "reliability": 0.8,
                  "first_seen": "2026-01-01", "last_seen": "2026-03-03"}]),
    ("10.0.0.0/8", [{"classification_type": "blacklist",
                     "verdict": "malicious", "reliability": 0.8}]),
]
FIREHOL_V4 = [
    ("1.0.1.0/24", [{"classification_type": "blacklist",
                     "verdict": "malicious", "reliability": 0.7,
                     "first_seen": "2026-01-02", "last_seen": "2026-01-20"}]),
    ("3.3.0.0/16", [{"classification_type": "blacklist",
                     "verdict": "malicious", "reliability": 0.7}]),
    ("6.9.0.0/16", [{"classification_type": "blacklist",
                     "verdict": "malicious", "reliability": 0.7}]),
    ("4.4.4.4", [{"classification_type": "blacklist",
                  "verdict": "malicious", "reliability": 0.7}]),
]
DANMEUK_TOR_V4 = [
    ("9.9.9.9", [{"classification_type": "tor", "verdict": "suspicious",
                  "reliability": 0.7,
                  "first_seen": "2020-01-01", "last_seen": "2026-06-01"}]),
    ("5.5.5.5", [{"classification_type": "tor", "verdict": "suspicious",
                  "reliability": 0.7}]),
]

GREENSNOW_REF_EV = {"classification_type": "blacklist",
                    "verdict": "malicious", "reliability": 0.6,
                    "first_seen": "2026-04-01", "last_seen": "2026-04-05"}
GREENSNOW_INLINE_EV = {"classification_type": "blacklist",
                       "verdict": "malicious", "reliability": 0.6,
                       "first_seen": "2026-05-01"}

# oracle 地址:扫描有单元的地址 + 网段单元的网络地址(期望值全走查询接口)
ORACLE_IPS = (
    "9.9.9.9", "4.4.4.4", "3.3.3.3", "1.0.2.9", "1.0.9.9",
    "1.0.1.0", "1.0.2.0", "1.0.0.0", "6.9.0.0", "10.0.0.0",
    "2606:4700::1", "2a00:1450:4001::",
)


def _int4(ip):
    return int(ipaddress.IPv4Address(ip))


def _hand_build_greensnow(tmp_path, inst):
    """手搭 greensnow 的 epoch 1 库:3.3.3.3 走字典引用证据
    (encode_value_ref + payloads 子库),1.0.9.9 内联字典,
    8.0.0.0→8.0.0.10 非对齐范围(两边界非对齐,summarize 出 3 个 CIDR)。
    ptr/.count/.disjoint sidecar 手写(rebuild 路径不走)。"""
    base = inst._lmdb_base
    d = base.parent / f"{base.name}.1"
    d.mkdir(parents=True)
    env = lmdb.open(str(d), map_size=1 << 20, max_dbs=2, subdir=True)
    pay = env.open_db(b"payloads")
    with env.begin(write=True) as txn:
        payload = orjson.dumps([GREENSNOW_REF_EV])
        txn.put((1).to_bytes(8, "big"), payload, db=pay)
        txn.put(encode_key(_int4("3.3.3.3")),
                encode_value_ref(_int4("3.3.3.3"), 1))
        txn.put(encode_key(_int4("1.0.9.9")),
                encode_value(_int4("1.0.9.9"), GREENSNOW_INLINE_EV))
        txn.put(encode_key(_int4("8.0.0.0")),
                encode_value(_int4("8.0.0.10"),
                             dict(GREENSNOW_INLINE_EV)))
    env.close()
    (base.parent / f"{base.name}.ptr").write_text("1")
    (base.parent / f"{base.name}.count").write_text("3")
    (base.parent / f"{base.name}.disjoint").write_text("1 1")
    (base.parent / f"{base.name}.rev").write_text(str(HARVEST_REV))


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    proto = {}
    for s in _registry._sources:
        proto.setdefault(s.name, type(s))
    names = ("abuseipdb", "blocklist_de", "firehol", "greensnow",
             "danmeuk_tor")
    insts = [proto[n](tmp_path) for n in names]
    by_name = dict(zip(names, insts))
    envs = []
    rebuild_lmdb(ABUSEIPDB_V4, by_name["abuseipdb"]._lmdb_base, envs.append)
    rebuild_lmdb(ABUSEIPDB_V6, by_name["abuseipdb"]._lmdb6_base, envs.append,
                 ip_version=6)
    rebuild_lmdb(BLOCKLIST_DE_V4, by_name["blocklist_de"]._lmdb_base,
                 envs.append)
    rebuild_lmdb(FIREHOL_V4, by_name["firehol"]._lmdb_base, envs.append)
    rebuild_lmdb(DANMEUK_TOR_V4, by_name["danmeuk_tor"]._lmdb_base,
                 envs.append)
    _hand_build_greensnow(tmp_path, by_name["greensnow"])
    for e in envs:
        e.close()   # 同进程同路径禁双开:rebuild 句柄先关
    # oracle 相位:夹具源 load 进 _registry,期望值走真查询接口
    monkeypatch.setattr(_registry, "_sources", insts)
    _registry._enabled_cache["entry"] = None
    _registry._loaded_cache["entry"] = None
    for s in insts:
        s.load()
    oracle = {ip: _registry.lookup(ip, asof=ASOF).to_dict() for ip in ORACLE_IPS}
    # 关读句柄(引用计数即关 env),扫描器才能开同路径句柄
    for s in insts:
        s._reader = None
        s._reader6 = None
    yield {"insts": insts, "by_name": by_name, "oracle": oracle}


def _unit_ips(sc):
    return [u.ip for u in sc]


def _collect(sc):
    return {u.ip: u for u in sc}


def test_multi_source_same_address_matches_lookup(scan_env):
    """①多源同址(两威胁源+一资产类源都有 9.9.9.9 单地址)→ 扫描单元的
    result 与 lookup() 同字节。拆掉 _gather_items 的单地址命中分支
    (让单地址记录也让位给覆盖探测)即红。"""
    with open_unit_scanner(
            sources=scan_env["insts"], asof=ASOF,
            spill_dir=str(scan_env["insts"][0]._lmdb_base.parent)) as sc:
        units = _collect(sc)
    got = units["9.9.9.9"]
    assert orjson.dumps(got.result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["9.9.9.9"])
    assert got.is_cidr is False and got.is_v6 is False


def test_disjoint_cidr_and_single_precedence(scan_env):
    """②不相交库:3.3.3.3 在 firehol 3.3.0.0/16 内、自己带 greensnow
    单地址记录——单元证据 = greensnow 单地址 + firehol 覆盖网段,与
    lookup() 同字节(单地址优先 + 覆盖网段同路取齐)。1.0.2.9 钉
    「单地址优先」:同源(嵌套库)有覆盖网段也有单地址,取单地址。
    拆掉 find_covering 的 disjoint 二分分支即红(3.3.3.3 缺 firehol
    证据)。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    assert orjson.dumps(units["3.3.3.3"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["3.3.3.3"])
    assert orjson.dumps(units["1.0.2.9"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["1.0.2.9"])


def test_nested_cidr_selection(scan_env):
    """③嵌套库:1.0.9.9(大网段 1.0.0.0/16 内、小网段 1.0.2.0/24 外)
    的证据取大网段;9.9.9.9(两条网段外)两条都取不到;1.0.2.0 的
    网段单元取小网段。全部与 lookup() 同字节。拆掉 find_covering 的
    嵌套前缀探测(或 plens 收集漏掉单地址的 /32)即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    for ip in ("1.0.9.9", "9.9.9.9"):
        assert orjson.dumps(units[ip].result.to_dict()) == \
            orjson.dumps(scan_env["oracle"][ip]), ip
    assert orjson.dumps(units["1.0.2.0/24"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["1.0.2.0"])
    assert orjson.dumps(units["1.0.0.0/16"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["1.0.0.0"])


def test_cidr_units_text_and_skip_anomaly(scan_env):
    """④网段单元:文本是 CIDR、判定在网络地址上算(与 lookup(网络地址)
    同字节,6.9.0.0/16);非对齐范围 8.0.0.0→8.0.0.10 summarize 出 3 个
    CIDR → 跳过并计数。拆掉 _phase_cidr 的 len(nets)!=1 分支(产残单元)
    或 skipped 计数行即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
        stats = dict(sc.stats)
    cidr = units["6.9.0.0/16"]
    assert cidr.is_cidr is True and cidr.is_v6 is False
    assert orjson.dumps(cidr.result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["6.9.0.0"])
    assert "8.0.0.0-8.0.0.10" not in units
    assert stats["skipped_anomalies"] == 1


def test_v6_family(scan_env):
    """⑤v6 族一套:单地址单元 2606:4700::1 与网段单元
    2a00:1450:4001::/48 都与 lookup() 同字节(is_v6=True)。
    拆掉 _open_envs 的 v6 腿(read_ptr(_lmdb6_base))即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    for ip, oip in (("2606:4700::1", "2606:4700::1"),
                    ("2a00:1450:4001::/48", "2a00:1450:4001::")):
        assert units[ip].is_v6 is True, ip
        assert orjson.dumps(units[ip].result.to_dict()) == \
            orjson.dumps(scan_env["oracle"][oip]), ip


def test_asset_only_address_produces_no_unit(scan_env):
    """⑥只有资产类源记录、没有威胁类源记录的地址(5.5.5.5,tor 资产类)
    不产生单元;9.9.9.9(威胁+资产混合)仍产单元。拆掉 _phase_single
    的「组内要有威胁单地址」判空(改成任何记录都产单元)即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        ips = _unit_ips(sc)
    assert "5.5.5.5" not in ips
    assert "9.9.9.9" in ips


def test_disabled_and_private_sources_not_read(scan_env, monkeypatch):
    """⑦被禁用的源(firehol 进 _disabled)与私源(greensnow 进
    IP_RADAR_PRIVATE_SOURCES)在 sources=None 时都不读:其单元与证据
    不出现。拆掉 _scan.__init__ 的 enabled/_PRIVATE 过滤即红。"""
    reg = _registry
    monkeypatch.setattr(reg, "_PRIVATE", frozenset({"greensnow"}))
    monkeypatch.setattr(reg, "_disabled", {"firehol"})
    reg._enabled_cache["entry"] = None
    reg._loaded_cache["entry"] = None
    with open_unit_scanner(asof=ASOF) as sc:
        ips = _unit_ips(sc)
        stats = dict(sc.stats)
    assert "3.3.3.3" not in ips          # 私源的单地址不产单元
    assert "1.0.1.0/24" not in ips       # 禁用源的网段不产单元
    assert "4.4.4.4" not in ips
    assert "greensnow" not in stats["records"]
    assert "firehol" not in stats["records"]


def test_reserved_network_cidr_unit(scan_env):
    """⑧网络地址是保留地址(10.0.0.0/8 的网络地址 10.0.0.0)→ 单元
    result 与 lookup() 一样走保留地址短路。拆掉 fuse_items 的 v4
    is_reserved_addr 守卫(或扫描侧改绕过 fuse_items)即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    assert orjson.dumps(units["10.0.0.0/8"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["10.0.0.0"])


def test_ref_evidence_resolves_like_inline(scan_env):
    """⑨字典引用证据(greensnow 3.3.3.3 经 encode_value_ref 写)解出来
    和内联一样:单元 result 与 lookup() 同字节(查询路径同走
    resolve_evidence)。拆掉 _decode 的 int 解引用分支即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    assert orjson.dumps(units["3.3.3.3"].result.to_dict()) == \
        orjson.dumps(scan_env["oracle"]["3.3.3.3"])


def test_first_last_seen_threat_only(scan_env):
    """⑩最早最晚时间只从威胁类源取、文本序 min/max:9.9.9.9 威胁源给
    first 2026-01-01 / last 2026-03-03,资产类 tor 给 2020-01-01/2026-06-01
    不计入;firehol 1.0.1.0/24 网段单元取自己组记录的 2026-01-02/2026-01-20。
    拆掉 seen 收集里的 threat 过滤(把资产类也算进去)即红。"""
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        units = _collect(sc)
    u = units["9.9.9.9"]
    assert u.first_seen == "2026-01-01"
    assert u.last_seen == "2026-03-03"
    c = units["1.0.1.0/24"]
    assert c.first_seen == "2026-01-02"
    assert c.last_seen == "2026-01-20"


def test_epochs_pinned(scan_env):
    """⑪epochs 原样给出纪元号:各源 (v4 纪元, v6 纪元),没建 v6 族的源
    v6 位是 None。拆掉 _open_envs 的 epochs 填充(或 v6 位误填 v4 值)即红。"""
    from ipdb._sources._lmdb import read_ptr
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        epochs = dict(sc.epochs)
    for name in ("abuseipdb", "blocklist_de", "firehol", "greensnow",
                 "danmeuk_tor"):
        base = scan_env["by_name"][name]._lmdb_base
        assert epochs[name][0] == read_ptr(base), name
    for name in ("blocklist_de", "firehol", "greensnow", "danmeuk_tor"):
        assert epochs[name][1] is None, name
    assert epochs["abuseipdb"][1] == \
        read_ptr(scan_env["by_name"]["abuseipdb"]._lmdb6_base)


def test_scanner_opens_readahead_envs(scan_env, monkeypatch):
    """⑫扫描句柄开了预读(readahead=True;查询侧 open_env_read 是 False,
    顺序扫描要预读)。monkeypatch lmdb.open 记 kwargs,拆掉 _open_envs
    的 readahead=True(换成 False)即红。"""
    calls = []
    real_open = lmdb.open

    def spy_open(path, **kw):
        calls.append((str(path), dict(kw)))
        return real_open(path, **kw)

    monkeypatch.setattr(lmdb, "open", spy_open)
    with open_unit_scanner(sources=scan_env["insts"], asof=ASOF) as sc:
        list(sc)
    assert calls, "scanner opened no envs"
    assert all(kw.get("readahead") is True for _, kw in calls)
    assert all(kw.get("readonly") is True for _, kw in calls)
    assert all(kw.get("lock") is False for _, kw in calls)


def test_close_then_load_db_reopens(scan_env):
    """⑬扫描 close 后同进程 load_db() 重开同路径不报 already open
    (py-lmdb 同进程同路径禁双开;close 必须真关掉全部 env)。
    拆掉 close() 的 env.close 循环即红。"""
    sc = open_unit_scanner(sources=scan_env["insts"], asof=ASOF)
    list(sc)                     # 跑完一遍(建事务、写 spill)
    sc.close()
    _registry._loaded_cache["entry"] = None
    _registry.load_db()          # 不抛 lmdb.Error: already open 即过
    assert any(s.health().loaded for s in scan_env["insts"])
