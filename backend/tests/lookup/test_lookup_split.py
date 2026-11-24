# backend/tests/lookup/test_lookup_split.py
"""#444 A 步:lookup() 拆分(collect 取数 / fuse 只融合)的一致性钉。

拆分合同(规格 §4.1):fuse(collect(ip), asof=T) 与 lookup(ip, asof=T)
对同一数据逐字节相等。夹具用真源类在临时目录建小库(照 tests/core/
test_lmdb_codec.py 的 rebuild_lmdb 办法),把 _registry._sources 换成
夹具实例并失效 _enabled/_loaded 两缓存。守卫路径(v6 非全球/组播、
v4 保留地址、解析错)与数据路径分别钉;守卫不带 _db_loaded 门这条
合同由 test_fuse_items_guard_paths 钉在 fuse_items 上。
"""
import ipaddress
import orjson
import pytest

from ipdb import _registry
from ipdb._sources._lmdb import rebuild_lmdb

# 钉死的衰减锚刻:置信度随时间连续衰减,两边必须同一时刻才可比
ASOF = 1_765_000_000.0

# 三个真源类:两个威胁类(同一地址都有单地址记录,测多源同址)、
# 一个带分类的资产类(tor,测资产类证据同路收进)
SOURCES = ("abuseipdb", "blocklist_de", "danmeuk_tor")

V4_RECORDS = {
    "abuseipdb": [
        ("9.9.9.9", [{"classification_type": "abuse-reports",
                      "verdict": "malicious", "reliability": 0.9,
                      "first_seen": "2026-03-01", "last_seen": "2026-03-02"}]),
        ("5.6.7.8", [{"classification_type": "abuse-reports",
                      "verdict": "malicious", "reliability": 0.9,
                      "first_seen": "2026-04-01"}]),
    ],
    "blocklist_de": [
        ("9.9.9.9", [{"classification_type": "blacklist",
                      "verdict": "malicious", "reliability": 0.8,
                      "first_seen": "2026-01-01", "last_seen": "2026-05-06"}]),
    ],
    "danmeuk_tor": [
        ("9.9.9.9", [{"classification_type": "tor",
                      "verdict": "suspicious", "reliability": 0.7,
                      "first_seen": "2025-01-01"}]),
    ],
}

V6_RECORDS = {
    "abuseipdb": [
        # v6 段必须全球可路由(文档段 2001:db8::/32 is_global=False 会走
        # reserved 短路,当不了正常命中夹具;conftest tiny_db_v6 先例)
        ("2a00:1450:4001::1", [{"classification_type": "abuse-reports",
                                "verdict": "malicious", "reliability": 0.9}]),
    ],
}

IPS = (
    "9.9.9.9",        # 多源同址:两威胁源 + 一资产类源都有单地址记录
    "5.6.7.8",        # 单源命中
    "8.8.8.8",        # 全源 miss → benign 0(同查询接口弃权形状)
    "2a00:1450:4001::1",   # v6 命中
    "2606:4700::1",   # v6 miss
)
# 守卫短路组:collect() 本身无守卫(守卫在 lookup/fuse_items),这些地址
# 不进 fuse(collect(...)) 的字节比对,只进守卫组比对。
GUARD_IPS = (
    "10.0.0.5",       # v4 保留地址 → reserved 短路
    "fe80::1",        # v6 链路本地 → reserved 短路
    "224.0.0.1",      # v4 组播 → reserved 短路
    "999.999.1.1",    # 解析错 → error 结果
)


@pytest.fixture
def split_env(tmp_path, monkeypatch):
    proto = {}
    for s in _registry._sources:
        proto.setdefault(s.name, type(s))
    insts = [proto[name](tmp_path) for name in SOURCES]
    by_name = dict(zip(SOURCES, insts))
    envs = []
    for name in SOURCES:
        if name in V4_RECORDS:
            rebuild_lmdb(V4_RECORDS[name], by_name[name]._lmdb_base,
                         envs.append)
        if name in V6_RECORDS:
            rebuild_lmdb(V6_RECORDS[name], by_name[name]._lmdb6_base,
                         envs.append, ip_version=6)
    for e in envs:
        e.close()   # py-lmdb 同进程同路径禁双开,rebuild 句柄先关(conftest 同款)
    monkeypatch.setattr(_registry, "_sources", insts)
    _registry._enabled_cache["entry"] = None
    _registry._loaded_cache["entry"] = None
    for s in insts:
        s.load()
    yield insts
    # 恢复由 monkeypatch 兜底;_enabled/_loaded 缓存键持旧 _sources 身份,
    # is 比对失配自动重算,无需手动清


def _b(d):
    """to_dict → 字节:断言逐字节相等而非 dict 相等(拆分合同按字节钉)。"""
    return orjson.dumps(d)


def test_fuse_collect_equals_lookup(split_env):
    """任务书 2.1 验收①:夹具里每个 IP,fuse(collect(...), asof=T) 与
    lookup(ip, asof=T) 的 to_dict() 逐字节相等;直接调 lookup 与走拆出
    两段得到的 LookupResult 相等。它钉的是 lookup() 尾部确实接的是
    fuse(collect(...)):拆掉这处接线(改回内联旧体)即红。collect/ingest
    里改了什么它看不见——两边走的是同一段代码,那段由
    test_fuse_items_matches_lookup 和全量回归看着。"""
    for ip in IPS:
        want = _registry.lookup(ip, asof=ASOF)
        addr = ipaddress.ip_address(ip) if _parseable(ip) else None
        if addr is not None:
            got = _registry.fuse(_registry.collect(ip, addr), asof=ASOF)
        else:
            got = _registry.fuse(_registry.collect(ip), asof=ASOF)
        assert isinstance(got, type(want))
        assert _b(got.to_dict()) == _b(want.to_dict()), ip
        assert _b(got.to_dict()) == _b(
            _registry.fuse(_registry.collect(ip), asof=ASOF).to_dict()), ip


def _parseable(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def _items_for(insts, ip):
    """扫描侧的 items 形状:只对可解析地址查库;不可解析地址在真流程
    里根本不会产生扫描证据,这里传空列表、由 fuse_items 的守卫短路。"""
    if not _parseable(ip):
        return []
    return [(s, s.query(ip)) for s in insts]


def test_fuse_items_matches_lookup(split_env):
    """fuse_items 按 (source, raw) 序列喂证据,与 lookup 同字节:扫描侧
    (规格 §4.2)的入口合同。items 顺序 = _enabled_sources 顺序;拆掉
    fuse_items 里的 ingest 循环或排序段即红。"""
    for ip in IPS:
        got = _registry.fuse_items(ip, _items_for(split_env, ip), asof=ASOF)
        want = _registry.lookup(ip, asof=ASOF)
        assert _b(got.to_dict()) == _b(want.to_dict()), ip


def test_fuse_items_guard_paths(split_env):
    """fuse_items 守卫与 lookup 相同(解析错/v6 非全球与组播/v4 保留
    地址 → 同一短路结果),但不走 _db_loaded 门:拆掉任一守卫分支即红
    (对应短路结果的 to_dict 与 lookup 不再一致)。"""
    for ip in ("999.999.1.1", "10.0.0.5", "fe80::1", "224.0.0.1"):
        got = _registry.fuse_items(ip, _items_for(split_env, ip), asof=ASOF)
        want = _registry.lookup(ip, asof=ASOF)
        assert _b(got.to_dict()) == _b(want.to_dict()), ip
    # 不走 _db_loaded 门:全部源卸载后 fuse_items 仍可用(lookup 会炸)。
    # _loaded_cache 只缓存 True 且键是 _sources 身份,卸 reader 不触发
    # 重算,这里手动清缓存同 conftest 惯例。
    saved = [(s, s._reader) for s in split_env]
    for s in split_env:
        s._reader = None
    _registry._loaded_cache["entry"] = None
    try:
        got = _registry.fuse_items("9.9.9.9", [], asof=ASOF)
        assert got.classifications == {}
        with pytest.raises(RuntimeError, match="Database not loaded"):
            _registry.lookup("9.9.9.9")
    finally:
        for s, r in saved:
            s._reader = r


def test_new_input_container_shapes(split_env):
    """new_input 的容器类型与拆分前 lookup() 局部建法一致(任务书 2.1:
    该是 defaultdict 的还是 defaultdict)。拆掉任一容器的 defaultdict
    形状(换成普通 dict)即红。"""
    from collections import defaultdict
    inp = _registry.new_input("9.9.9.9", ipaddress.ip_address("9.9.9.9"))
    assert isinstance(inp.field_values, defaultdict)
    assert isinstance(inp.attributes, defaultdict)
    assert isinstance(inp.observations, list)
    assert type(inp.field_extras) is dict        # defaultdict 也过 isinstance
    # stash 键 = 旁路表键序(#315)
    assert list(inp.stash.keys()) == [spec.key for spec in _registry._BYPASS_SPECS]
