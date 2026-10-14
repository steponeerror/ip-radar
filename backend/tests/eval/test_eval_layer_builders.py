# backend/tests/eval/test_eval_layer_builders.py
"""三层语料构建器: 中性层/非指控基础设施层/共识代理层 (spec §2.1)。

truth 层归 T4 自有三闸, 不在此。全 fake 输入零网络; 断言面 = S36
run_seed 纪律(采样层必填 kw-only)+ 逐字节确定性 + 宁少算(输入不足
全取不炸, member_count 恒如实)+ Q22 共识层容量独立声明。
"""
import json
from pathlib import Path

from ipdb._eval.assets import fingerprint, load_asset
from ipdb._eval.layer_builders import (
    CLOUD_SAMPLE_N,
    build_all_monthly,
    build_consensus_asset,
    build_infra_asset,
    build_neutral_asset,
    non_vpn_resolvers,
)
from ipdb._eval.layered import assemble_four_layers

# 包内静态中性资产(与 corpus.json 同目录)
_STATIC_NEUTRAL = Path(__file__).resolve().parents[2] / "ipdb" / "_eval" / "neutral_ips.json"

# 与中性静态资产(公网单播)零重叠的假输入: 10/8 块 + TEST-NET-1 解析器
_BLOCKS = [f"10.{i // 100}.{i % 100}.0/24" for i in range(200)]
_RESOLVERS = ["192.0.2.1", "192.0.2.2"]
_KEYSETS = {
    "src_a": [f"10.100.0.{i}" for i in range(1, 41)],   # 40 > 30: 配额生效
    "src_b": [f"10.101.0.{i}" for i in range(1, 11)],   # 10 < 30: 不足全取
    "src_c": [f"10.102.0.{i}" for i in range(1, 51)],
}


def test_neutral_roundtrip_wraps_static_asset(tmp_path):
    out = tmp_path / "neutral"
    meta = build_neutral_asset(out, version="v-test")
    static = json.loads(_STATIC_NEUTRAL.read_text())
    assert len(static) == 600  # 静态资产现值 600, 换源如实跟随
    members, loaded = load_asset(out)
    assert loaded.kind == "neutral" and loaded.version == "v-test"
    assert members == sorted(static)
    assert loaded.member_count == len(static) == 600  # member_count 如实
    assert loaded.fingerprint == fingerprint(sorted(static)) == meta.fingerprint


def test_non_vpn_resolvers_filters_cidr_and_bare_prefixes():
    assert non_vpn_resolvers(
        ["1.2.3.4", "10.0.0.5", "10.9.9.9", "192.0.2.1"], ["10.0.0.0/8"]
    ) == ["1.2.3.4", "192.0.2.1"]
    assert non_vpn_resolvers(["1.2.3.4", "1.2.3.5"], ["1.2.3.4"]) == ["1.2.3.5"]
    # 无 VPN 段: 去重定序全保留
    assert non_vpn_resolvers(["9.9.9.9", "8.8.8.8", "9.9.9.9"], []) == ["8.8.8.8", "9.9.9.9"]


def test_infra_samples_177_distinct_plus_resolvers(tmp_path):
    out = tmp_path / "infra"
    meta = build_infra_asset(out, version="v1", run_seed=1,
                             cloud_ranges=_BLOCKS, resolver_ips=_RESOLVERS)
    members, loaded = load_asset(out)
    assert loaded.kind == "infra"
    cloud = [m for m in members if m.startswith("10.")]
    assert len(cloud) == CLOUD_SAMPLE_N == 177
    assert len(members) == len(set(members)) == 177 + len(_RESOLVERS)
    assert loaded.member_count == meta.member_count == 179
    assert loaded.params["n_cloud_sampled"] == 177
    assert loaded.params["n_resolvers"] == len(_RESOLVERS)


def test_infra_short_ranges_honest_fewer_no_crash(tmp_path):
    # 宁少算: 云段不足 177 → 如实短, 不炸
    out = tmp_path / "infra"
    meta = build_infra_asset(out, version="v1", run_seed=1,
                             cloud_ranges=_BLOCKS[:3], resolver_ips=_RESOLVERS)
    assert meta.member_count == 3 + len(_RESOLVERS)
    assert meta.params["n_cloud_sampled"] == 3


def test_infra_deterministic_bytes_and_seed_sensitivity(tmp_path):
    a, b, c = (tmp_path / f"d{i}" for i in range(3))
    m1 = build_infra_asset(a, version="v1", run_seed=42,
                           cloud_ranges=_BLOCKS, resolver_ips=_RESOLVERS)
    m2 = build_infra_asset(b, version="v1", run_seed=42,
                           cloud_ranges=_BLOCKS, resolver_ips=_RESOLVERS)
    m3 = build_infra_asset(c, version="v1", run_seed=43,
                           cloud_ranges=_BLOCKS, resolver_ips=_RESOLVERS)
    for name in ("ips.txt", "meta.json"):  # 同 seed 两次 = 逐字节相同
        assert (a / name).read_bytes() == (b / name).read_bytes()
    assert m1.fingerprint == m2.fingerprint
    assert m3.fingerprint != m1.fingerprint  # 采样指纹纪律: seed 变指纹变


def test_consensus_per_source_cap_and_honest_union(tmp_path):
    out = tmp_path / "consensus"
    meta = build_consensus_asset(out, version="v1", run_seed=7,
                                 source_keysets=_KEYSETS)
    members, loaded = load_asset(out)
    assert loaded.kind == "consensus"
    assert len(members) == len(set(members))
    assert loaded.member_count == meta.member_count == 30 + 10 + 30  # 去重并集
    assert loaded.member_count <= 3 * 30  # ≤90 封顶不强制, 只如实
    assert set(_KEYSETS["src_b"]) <= set(members)  # 不足 per_source 全取不炸
    assert sum(m.startswith("10.100.") for m in members) == 30  # 逐源配额生效


def test_consensus_determinism_and_seed_sensitivity(tmp_path):
    a, b, c = (tmp_path / f"d{i}" for i in range(3))
    m1 = build_consensus_asset(a, version="v1", run_seed=42, source_keysets=_KEYSETS)
    m2 = build_consensus_asset(b, version="v1", run_seed=42, source_keysets=_KEYSETS)
    m3 = build_consensus_asset(c, version="v1", run_seed=43, source_keysets=_KEYSETS)
    for name in ("ips.txt", "meta.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    assert m1.fingerprint == m2.fingerprint != m3.fingerprint


def test_infra_skips_v6_blocks_honest_fewer_and_counts(tmp_path):
    # 生产 cloud_ranges 中间文件混 v6 段(aws ipv6_prefixes/gcp ipv6Prefix/azure
    # 双族, _sources/cloud_ranges.py): 采样器跳过不炸(宁少算), 计数如实入
    # params.skipped_v6_blocks; 跳过不消耗 rng 也不改 v4 相对序 → 采样结果
    # 与纯 v4 输入逐字节相同(同 seed)。
    mixed = ["2600:1f00::/24", *_BLOCKS[:5], "2a01::/32", *_BLOCKS[5:20]]
    a, b = tmp_path / "mixed", tmp_path / "v4only"
    meta_mixed = build_infra_asset(a, version="v1", run_seed=5,
                                   cloud_ranges=mixed, resolver_ips=_RESOLVERS)
    meta_v4 = build_infra_asset(b, version="v1", run_seed=5,
                                cloud_ranges=_BLOCKS[:20],
                                resolver_ips=_RESOLVERS)
    assert meta_mixed.fingerprint == meta_v4.fingerprint
    assert (a / "ips.txt").read_bytes() == (b / "ips.txt").read_bytes()
    _, loaded = load_asset(a)
    assert loaded.params["skipped_v6_blocks"] == 2


def test_build_all_monthly_layout_matches_four_layer_assembler(tmp_path):
    root = tmp_path / "assets"
    metas = build_all_monthly(root, version="v1", run_seed=99,
                              cloud_ranges=_BLOCKS, resolver_ips=_RESOLVERS,
                              source_keysets=_KEYSETS)
    assert set(metas) == {"neutral", "infra", "consensus"}  # truth 归 T4 不产
    # 目录布局 = layered.assemble_four_layers 的 load 路径 <root>/<kind>/
    for kind, meta in metas.items():
        assert (root / kind / "ips.txt").is_file()
        assert meta.kind == kind
    layers = assemble_four_layers(root)
    assert layers["truth"].status == "NO-LAYER"  # 缺 truth = 显式哨兵
    for kind in ("neutral", "infra", "consensus"):
        assert layers[kind].status == "OK"
        assert layers[kind].members  # 非空层
        assert layers[kind].removed_overlap == 0  # 测试输入互斥
