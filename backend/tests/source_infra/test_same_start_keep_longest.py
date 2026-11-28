"""#480 同起点碰撞,收获落盘时只留最长前缀(2026-11-28 裁决)。

旧行为(键 = 只有起点,前缀长度不进键):同起点不同长度的两条 CIDR 键
逐字节相同,`_flush` 的 `txn.put` 缺省覆盖 → 后写胜,超网剩余段静默丢失。
新行为:写前读旧值比 end(对齐 CIDR 里前缀长者 end 更小)→ 只留前缀最
长的一条;完全相同的重复行(end 相同)维持后写胜。

代价钉进测试当文档:宽段里窄段之外的地址从此没有这条证据(查询侧 miss
断言);窄段内地址拿到更细的证据。.count 语义不变 = env 实际键数(碰撞
本来就被同键合并,一条都不少,#480 事实包 §1.4)。
"""
import ipaddress

import pytest

import ipdb._sources._lmdb as lmdb_mod
from ipdb._sources._base import CsvSource, IpListSource
from ipdb._sources._lmdb import (
    PAYLOADS_NAME, count_path, cov_path, decode_value, disjoint_path,
    encode_key, encode_key6, open_env_read, ptr_path, read_ptr, rebuild_lmdb)


class _List(IpListSource):
    name, filename, fields = "t", "t.txt", ("is_malicious",)


def _end(cidr: str) -> int:
    return int(ipaddress.ip_network(cidr, strict=False).broadcast_address)


def _rebuild(tmp_path, records, ip_version=4):
    base = tmp_path / ("t.v6.txt.lmdb" if ip_version == 6 else "t.txt.lmdb")
    n_keys = rebuild_lmdb(records, base, reader_setter=lambda env: None,
                          ip_version=ip_version)
    epoch = read_ptr(base)
    env = open_env_read(tmp_path / f"{base.name}.{epoch}")
    return base, env, n_keys


def _survivor(env, start_ip: str, ip_version: int = 4):
    """→ (幸存记录的 end, payload bytes)。payload 经 payloads 字典解引。"""
    key = (encode_key6 if ip_version == 6 else encode_key)(
        int(ipaddress.ip_address(start_ip)))
    pay_db = env.open_db(PAYLOADS_NAME)
    with env.begin() as txn:
        raw = txn.get(key)
        assert raw is not None, f"no record at start {start_ip}"
        end, ref = decode_value(raw)
        payload = txn.get(ref.to_bytes(8, "big"), db=pay_db)
    return end, payload


# ── 单元:写前读旧值只留最长前缀 ─────────────────────────────────────

def test_narrower_prefix_survives_wide_written_last(tmp_path):
    """① /24 先、/16 后 → /24 胜(旧行为这里 /16 覆盖,行为变化点)。"""
    narrow, wide = {"tag": "narrow"}, {"tag": "wide"}
    _, env, n_keys = _rebuild(tmp_path, [
        ("10.0.0.0/24", narrow), ("10.0.0.0/16", wide)])
    assert n_keys == 1
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert narrow["tag"].encode() in payload


def test_narrower_prefix_survives_wide_written_first(tmp_path):
    """② 顺序反过来 /16 先、/24 后 → 还是 /24 胜(与旧行为一致但裁决
    来源变了:现在是「前缀长」,不是「后写」)。"""
    narrow, wide = {"tag": "narrow"}, {"tag": "wide"}
    _, env, _ = _rebuild(tmp_path, [
        ("10.0.0.0/16", wide), ("10.0.0.0/24", narrow)])
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert narrow["tag"].encode() in payload


@pytest.mark.parametrize("order", [
    ("10.0.0.0/22", "10.0.0.0/23", "10.0.0.0/24"),
    ("10.0.0.0/24", "10.0.0.0/23", "10.0.0.0/22"),
    ("10.0.0.0/23", "10.0.0.0/24", "10.0.0.0/22"),
])
def test_triple_nesting_any_order_longest_wins(tmp_path, order):
    """③ 三重嵌套 /22+/23+/24 任意顺序 → /24 胜。"""
    payloads = {c: {"tag": c} for c in order}
    _, env, n_keys = _rebuild(
        tmp_path, [(c, payloads[c]) for c in order])
    assert n_keys == 1
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert b"10.0.0.0/24" in payload


def test_identical_cidr_duplicate_last_write_wins(tmp_path):
    """④ 完全相同的 CIDR 重复两行 → 后写胜(payload 用后者的,end 相同
    不当碰撞)。"""
    first, second = {"tag": "first"}, {"tag": "second"}
    _, env, n_keys = _rebuild(tmp_path, [
        ("10.0.0.0/24", first), ("10.0.0.0/24", second)])
    assert n_keys == 1
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert b"second" in payload
    assert b"first" not in payload


def test_collision_pair_non_adjacent_within_batch(tmp_path):
    """⑤a 碰撞对之间隔着别的记录(同 batch 非相邻)→ 仍 /24 胜。"""
    narrow, wide = {"tag": "narrow"}, {"tag": "wide"}
    _, env, _ = _rebuild(tmp_path, [
        ("10.0.0.0/24", narrow),
        ("10.9.9.0/24", {"tag": "filler"}),
        ("10.0.0.0/16", wide)])
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert narrow["tag"].encode() in payload


def test_collision_pair_split_across_batches(tmp_path, monkeypatch):
    """⑤b 碰撞组拆到两个 batch(BATCH_SIZE=2)→ 跨 batch 仍正确
    (batch 2 的宽条不得覆盖 batch 1 的窄条;反向亦然)。"""
    monkeypatch.setattr(lmdb_mod, "BATCH_SIZE", 2)
    narrow, wide = {"tag": "narrow"}, {"tag": "wide"}
    _, env, _ = _rebuild(tmp_path, [
        ("10.0.0.0/24", narrow),        # batch 1
        ("10.9.9.0/24", {"tag": "f1"}),  # batch 1
        ("10.0.0.0/16", wide),          # batch 2 ← 跨 batch 碰撞
        ("10.8.8.0/24", {"tag": "f2"}),  # batch 2
    ])
    end, payload = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")
    assert narrow["tag"].encode() in payload

    base2 = tmp_path / "t.rev.txt.lmdb"
    rebuild_lmdb([("10.0.0.0/16", wide),        # batch 1
                  ("10.9.9.0/24", {"tag": "f1"}),
                  ("10.0.0.0/24", narrow),      # batch 2
                  ("10.8.8.0/24", {"tag": "f2"})],
                 base2, reader_setter=lambda env: None)
    epoch = read_ptr(base2)
    env2 = open_env_read(tmp_path / f"{base2.name}.{epoch}")
    end, _ = _survivor(env2, "10.0.0.0")
    assert end == _end("10.0.0.0/24")


@pytest.mark.parametrize("order", [
    ("2001:db8::/32", "2001:db8::/48"),
    ("2001:db8::/48", "2001:db8::/32"),
])
def test_ipv6_same_start_pair_same_rule(tmp_path, order):
    """⑥ v6 同起点一对(16 字节键腿)→ 同规则;/48 胜。"""
    payloads = {c: {"tag": c} for c in order}
    _, env, n_keys = _rebuild(tmp_path, [(c, payloads[c]) for c in order],
                              ip_version=6)
    assert n_keys == 1
    end, payload = _survivor(env, "2001:db8::", ip_version=6)
    assert end == _end("2001:db8::/48")   # >2⁶⁴−1,v4 侧不受影响
    assert b"2001:db8::/48" in payload


# ── sidecar / 提交序不回归(⑦⑧)─────────────────────────────────────

def test_sidecars_and_key_count_unregressed(tmp_path):
    """⑦⑧ 碰撞组下:.count 仍 = env 实际键数;.cov/.disjoint 有值;
    ptr 指向新 epoch。#480 不少一条记录(键数不变,变的是幸存内容)。"""
    (tmp_path / "t.txt").write_text(
        "10.0.0.0/24\n10.0.0.0/16\n10.1.0.0/24\n", encoding="utf-8")
    s = _List(data_dir=tmp_path)
    ret = s.rebuild()
    base = tmp_path / "t.txt.lmdb"
    assert ret == 2                    # 10.0.0.0 碰撞归一 + 10.1.0.0
    assert count_path(base).read_text().strip() == "2"
    assert s._count == 2
    assert cov_path(base).exists() and int(cov_path(base).read_text()) > 0
    epoch = read_ptr(base)
    assert disjoint_path(base).read_text().startswith(str(epoch))
    # 幸存的是 /24(证据内容变了,count 不变)
    env = open_env_read(tmp_path / f"{base.name}.{epoch}")
    end, _ = _survivor(env, "10.0.0.0")
    assert end == _end("10.0.0.0/24")


# ── 查询侧:代价钉进测试当文档 ─────────────────────────────────────

def test_query_cost_wide_only_addresses_lose_evidence(tmp_path):
    """窄段胜出后:窄段内地址拿到窄证据;宽段里窄段之外的地址查不到
    (这条证据彻底消失——#480 已接受的双向代价,emerging_threats 形)。"""
    (tmp_path / "t.txt").write_text(
        "45.144.212.0/24\n45.144.212.0/22\n", encoding="utf-8")
    s = _List(data_dir=tmp_path)
    s.rebuild()
    hit = s.query("45.144.212.5")          # 窄段内:拿到 /24 那条
    assert hit, "narrow-range address must still resolve"
    miss = s.query("45.144.213.1")         # /22 里 /24 之外:证据消失
    assert miss == {}


# ── 真数据小夹具(原始行亲核自 .eval-prod-data 镜像,只读抄录;
#    行号为 2026-11-28 快照行号,内容为准)───────────────────────────

_TRUE_GROUPS = {
    "cloud_ranges/alibaba.txt:2-3":
        ["8.128.4.0/22", "8.128.4.0/23"],
    "emerging_threats/emerging-block-ips.txt:201-202":
        ["45.144.212.0/24", "45.144.212.0/22"],
    # 语义不同的两条主张(RTBH attacker /32 vs Spamhaus infrastructure /24)
    # 也按前缀裁决——已接受的翻判代价(事实包 §1.5)。
    "ziyadnz.csv:47819-47820":
        ["2.57.122.0", "2.57.122.0/24"],
    # 跨文件冲突主张(chinatelecom vs othernet),嵌套是巧合不是层级。
    "cn_isp isp/chinatelecom.txt:6 vs isp/othernet.txt:11":
        ["1.119.192.0/21", "1.119.192.0/20"],
}


def _make_list_source(tmp_path, filename: str) -> IpListSource:
    """最简 IpListSource:filename 指向 tmp_path 里的裸 CIDR 行文件。"""

    class _Fx(IpListSource):
        pass

    _Fx.name, _Fx.filename, _Fx.fields = "fx", filename, ("is_malicious",)
    return _Fx(data_dir=tmp_path)


@pytest.mark.parametrize("group", sorted(_TRUE_GROUPS))
def test_real_fixture_collision_group_keeps_longest(tmp_path, group):
    cidrs = _TRUE_GROUPS[group]
    narrow = max(cidrs, key=lambda c: ipaddress.ip_network(
        c, strict=False).prefixlen)
    start = str(ipaddress.ip_network(cidrs[0], strict=False).network_address)
    prev = None
    for order in (cidrs, list(reversed(cidrs))):
        name = f"fx{abs(hash(group)) % 10000}.txt"
        (tmp_path / name).write_text("\n".join(order) + "\n", encoding="utf-8")

        if prev is not None:
            prev._reader.close()    # convention 7:同 base 换实例先关旧 reader
        s = _make_list_source(tmp_path, name)
        s.rebuild()
        prev = s
        base = tmp_path / f"{name}.lmdb"
        epoch = read_ptr(base)
        env = open_env_read(tmp_path / f"{base.name}.{epoch}")
        end, _ = _survivor(env, start)
        assert end == _end(narrow), f"{group} order={order}: survivor != {narrow}"


def test_ziyadnz_semantic_conflict_resolves_by_prefix(tmp_path):
    """ziyadnz 语义翻判组钉死:/32 attacker 与 /24 infrastructure 同起点,
    修后 .0 = /32 那条(attacker),.1-.255 无证据——按前缀裁决、不看
    语义。用 CsvSource 真解析路径(原始行是 9 列 csv,不是裸 CIDR 行)。"""
    (tmp_path / "z.csv").write_text(
        "2.57.122.0,ipv4,False,RTBH (Turkiye),1,government-feed,20,"
        "2026-11-23T21:25:56Z,2026-11-23T21:25:56Z\n"
        "2.57.122.0/24,ipv4,True,Spamhaus DROP,1,infrastructure,20,"
        "2026-11-16T09:44:49Z,2026-11-23T21:25:56Z\n", encoding="utf-8")

    class _Z(CsvSource):
        name, filename, fields = "z", "z.csv", ("is_malicious",)

        def parse_row(self, row):
            if len(row) < 4:
                return None
            return {"_ip": row[0].strip(), "is_malicious": True,
                    "extra": {"feed": row[3].strip()}}

    s = _Z(data_dir=tmp_path)
    s.rebuild()
    assert s.query("2.57.122.0"), "narrow /32 keeps its evidence"
    assert s.query("2.57.122.1") == {}, "wide-only address loses evidence"
