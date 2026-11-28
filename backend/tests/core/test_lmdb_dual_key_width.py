"""#575 步 1:读侧双形态(键长 4/16 旧格式 ∪ 5/17 新格式)单元测试。

任务书纪律:测试内直接 lmdb.open 手搭小库,不经 rebuild —— 测的是读侧
接口面,不 patch 私有符号。断言口径(设计稿 §6 步 1):
- 旧键库(4/16B)结果与改前相同(单条 dict 早退语义逐字保持);
- 新键库(5/17B = 起点 + plen 尾字节)交叠区地址返回两条证据、窄在前、
  顺序稳定;单地址(plen 32/128)照常命中;
- v6 含超 2⁶⁴−1 的字符串端点形态(encode_value 的 str 分支)。
"""
import lmdb

from ipdb._sources._lmdb import (
    detect_disjoint,
    encode_value,
    lookup,
)


def _hand_env(tmp_path, rows, name):
    """手搭小库:rows = [(key_bytes, end_int, evidence)]。值走 encode_value
    (含 >2⁶⁴−1 字符串端点分支),证据 inline dict —— 不涉 payloads 字典。"""
    env = lmdb.open(str(tmp_path / f"{name}.lmdb"), map_size=1 << 20)
    with env.begin(write=True) as txn:
        for k, end, ev in rows:
            txn.put(k, encode_value(end, ev))
    return env


W16 = {"v": "wide16"}
N24 = {"v": "narrow24"}
S32 = {"v": "single32"}


# ── 旧格式 4B 键:行为零变化 ────────────────────────────────────

def test_old_width_v4_results_unchanged(tmp_path):
    """旧键库逐字保持改前语义:嵌套探测首个命中早退返回单条 dict。"""
    env = _hand_env(tmp_path, [
        (b"\x01\x00\x00\x00", 0x0100FFFF, W16),      # 1.0.0.0/16
        (b"\x01\x02\x03\x04", 0x01020304, S32),      # 单地址记录
        (b"\x14\x00\x00\x00", 0x1400FFFF, {"v": "other16"}),
    ], "old4")
    assert lookup(env, 0x01000007) == W16            # /16 容器命中
    assert lookup(env, 0x01020304) == S32            # /32 精确命中
    assert lookup(env, 0x01000107) == W16            # /16 内、/32 外
    assert lookup(env, 0x15000001) is None           # 真 miss(跑满 33 层)


def test_old_width_v6_results_unchanged(tmp_path):
    """v6 旧键 16B:字符串端点(>2⁶⁴−1)形态下行为不变。"""
    start = 0x20010DB8000000000000000000000000
    env = _hand_env(tmp_path, [
        (start.to_bytes(16, "big"), start + 2**80 - 1, {"v": "v6w48"}),
    ], "old16")
    assert lookup(env, start + 1, ip_version=6) == {"v": "v6w48"}
    assert lookup(env, start + (1 << 80), ip_version=6) is None


def test_old_width_disjoint_fastpath_unchanged(tmp_path):
    """disjoint 库快路径(回扫)在旧键库上原样:greatest start ≤ ip。"""
    env = _hand_env(tmp_path, [
        (b"\x0a\x00\x00\x00", 0x0A0000FF, {"v": "a"}),
        (b"\x14\x00\x00\x00", 0x1400FFFF, {"v": "c"}),
    ], "oldd")
    assert detect_disjoint(env) is True
    assert lookup(env, 0x0A000005, disjoint=True) == {"v": "a"}
    assert lookup(env, 0x0A0F0000, disjoint=True) is None


# ── 新格式 5B 键(v4) ──────────────────────────────────────────

NEW_V4 = [
    # 同起点 1.0.0.0:/16(宽)与 /24(窄)两条都存 —— 键尾 plen 字节
    (b"\x01\x00\x00\x00\x10", 0x0100FFFF, W16),
    (b"\x01\x00\x00\x00\x18", 0x010000FF, N24),
    (b"\x01\x02\x03\x04\x20", 0x01020304, S32),      # 单地址 = plen 32
]


def test_new_width_v4_overlap_returns_both_narrow_first(tmp_path):
    """交叠区地址:两条证据、窄在前、顺序稳定(设计稿 §4.1 定死拼接序)。"""
    env = _hand_env(tmp_path, NEW_V4, "new4")
    assert lookup(env, 0x01000007) == [N24, W16]
    # 顺序稳定:同库同地址重复查询逐字节同序
    assert lookup(env, 0x01000007) == [N24, W16]


def test_new_width_v4_wide_only_returns_single_item_list(tmp_path):
    """只落宽条范围(/16 内、/24 外):单条证据,list 形态(新格式恒 list)。"""
    env = _hand_env(tmp_path, NEW_V4, "new4b")
    assert lookup(env, 0x01000107) == [W16]


def test_new_width_v4_bare_ip_plen32_hits(tmp_path):
    """单地址(裸 IP)= plen 32 记录照常命中;旁邻地址不误收。"""
    env = _hand_env(tmp_path, NEW_V4, "new4c")
    assert lookup(env, 0x01020304) == [S32]
    assert lookup(env, 0x01020305) is None


def test_new_width_v4_miss_returns_none(tmp_path):
    env = _hand_env(tmp_path, NEW_V4, "new4d")
    assert lookup(env, 0x15000001) is None


def test_new_width_v4_disjoint_fastpath(tmp_path):
    """新格式 disjoint 库(无嵌套)快路径:5B 键起点段相等即 exact start。"""
    env = _hand_env(tmp_path, [
        (b"\x0a\x00\x00\x00\x18", 0x0A0000FF, {"v": "a"}),
        (b"\x14\x00\x00\x00\x10", 0x1400FFFF, {"v": "c"}),
    ], "newd")
    assert detect_disjoint(env) is True
    assert lookup(env, 0x0A000005, disjoint=True) == {"v": "a"}
    assert lookup(env, 0x0A0F0000, disjoint=True) is None
    assert lookup(env, 0x14000001, disjoint=True) == {"v": "c"}


def test_new_width_same_start_flips_detect_disjoint_to_false(tmp_path):
    """同起点两条共存 = 真嵌套:detect_disjoint 判 False(设计稿 §3,.disjoint
    翻 0 的机制,步 2 重建后 8 个碰撞源预期走这条)。"""
    env = _hand_env(tmp_path, NEW_V4[:2], "new4e")
    assert detect_disjoint(env) is False


# ── 新格式 17B 键(v6,含字符串端点) ──────────────────────────

V6_START = 0x20010DB8000000000000000000000000
V6_W48 = {"v": "v6wide48"}
V6_N64 = {"v": "v6narrow64"}
V6_S128 = {"v": "v6single128"}


def test_new_width_v6_overlap_and_string_endpoints(tmp_path):
    """v6 新键 17B:同起点 /48+/64 两条,端点均超 2⁶⁴−1(encode_value 字符串
    分支),_end_int 快路径对带引号形式透明;交叠区窄在前。再钉三层嵌套:
    /128 单地址叠在 /48+/64 之上 → 三条证据、窄在前。"""
    env = _hand_env(tmp_path, [
        (V6_START.to_bytes(16, "big") + b"\x30",
         V6_START + 2**80 - 1, V6_W48),
        (V6_START.to_bytes(16, "big") + b"\x40",
         V6_START + 2**64 - 1, V6_N64),
        ((V6_START + 1).to_bytes(16, "big") + b"\x80",
         V6_START + 1, V6_S128),                   # 单地址 = plen 128
    ], "new16")
    assert lookup(env, V6_START + 1, ip_version=6) == [V6_S128, V6_N64, V6_W48]
    # 只落 /48(/64 之外):单条
    assert lookup(env, V6_START + 2**64, ip_version=6) == [V6_W48]
    # /48 之外:真 miss
    assert lookup(env, V6_START + 2**80, ip_version=6) is None


def test_old_width_v6_detect_disjoint_true_still(tmp_path):
    """旧 v6 库(16B 键)disjoint 判定不受双形态改动影响。"""
    env = _hand_env(tmp_path, [
        (b"\x20\x01\x0d\xb8" + b"\x00" * 12, 2**128 - 1, {"v": "x"}),
    ], "old16d")
    assert detect_disjoint(env) is True
