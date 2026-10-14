# backend/ipdb/_eval/layer_builders.py
"""三层语料构建器: 中性层/非指控基础设施层/共识代理层 (spec §2.1).

威胁真值层归 truth_layer.py(T4, 自带 rir/扫描/健康度三闸); 本模块产
其余三层资产, 全部经 assets.save_asset 落 <out_dir>/ips.txt+meta.json
(版本化+指纹, 装配走 layered.assemble_four_layers 的 <root>/<kind>/ 布局)。

- 中性层(spec §2.1 600 静态): neutral_ips.json 原样包装, 无采样 → 无
  run_seed(W0 静态资产逐轮恒定, S36 只辖采样路径)。
- 非指控基础设施层: 解析器侧(root_servers+dns_public 键集剔 VPN 段,
  调用方用 non_vpn_resolvers 过滤)+ 云/CDN 段内 run_seed 确定性采样
  177(spec §2.1 口径 497=320+177; 原型实测 2026-10-12 yardstick §三)。
- 共识代理层: 逐源采 30(IP 配额, spec §2.1; Q22 裁决=诊断层, 容量
  独立声明 —— 池竭 ~19源×30≈570 上限不设闸不封顶, member_count 恒如实)。

S36 纪律: 凡采样必带必填 kw-only run_seed(run 级随机 seed, 防源名/
文件内容可预测的定向策展, 对抗审查 R1#1 第14轮条款); 同 run_seed
逐字节可复现, run_seed 变则指纹变。宁少算: 输入不足配额全取不炸。
"""
from __future__ import annotations

import ipaddress
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from .assets import AssetMeta, fingerprint, save_asset

# 云/CDN 采样配额(spec §2.1: 非指控基础设施层 497 = 320 解析器 + 177 云/CDN)
CLOUD_SAMPLE_N = 177
# 共识层逐源 IP 配额(spec §2.1 逐源采 30; Q22: 诊断层容量独立声明)
PER_SOURCE_N = 30

_NEUTRAL_ASSET = Path(__file__).parent / "neutral_ips.json"


def _today() -> str:
    # truth_layer 同款: 日期粒度, 同日两跑逐字节可复现
    return datetime.now(timezone.utc).date().isoformat()


def build_neutral_asset(out_dir: Path, *, version: str) -> AssetMeta:
    """kind=neutral: 静态中性语料(neutral_ips.json, 现值 600)原样包装成
    版本化资产。无采样路径 → 不收 run_seed(S36 只辖采样; 静态资产逐轮
    恒定, W0 中性层)。member_count = 静态源实数, 换源如实跟随。"""
    members = sorted(json.loads(_NEUTRAL_ASSET.read_text()))
    meta = AssetMeta(
        version=version,
        kind="neutral",
        fingerprint=fingerprint(members),
        member_count=len(members),
        params={"source": _NEUTRAL_ASSET.name},
        eval_env="monthly",  # EVAL_ENV 隔离(T11)前先钉 monthly, truth_layer 同款
        created_at=_today(),
    )
    save_asset(Path(out_dir), members, meta)
    return meta


def non_vpn_resolvers(resolver_ips: list[str], vpn_prefixes: list[str]) -> list[str]:
    """剔除落入任一 VPN 段的解析器 IP, 返回去重定序保留集。

    vpn_prefixes = CIDR/bare-IP 前缀表(strict=False 容忍主机位脏写);
    调用方先以 root_servers+dns_public 键集喂 resolver_ips, 再过滤出
    非指控基础设施层的 320 侧输入(spec §2.1)。
    """
    nets = [ipaddress.ip_network(p, strict=False) for p in vpn_prefixes]
    return sorted({ip for ip in resolver_ips
                   if not any(ipaddress.ip_address(ip) in n for n in nets)})


def _sample_cloud_hosts(cloud_ranges: list[str], needed: int,
                        rng: random.Random) -> tuple[list[str], int]:
    """云/CDN 段内确定性采样, (≤needed 个互异主机, 跳过的 v6 段数)。

    方法(采样指纹纪律锚点, meta.params.sample_method 同名登记):
    段经 ip_network 规范化去重后按 (网络地址, 前缀长) 排序, 逐段用同一
    rng.randrange(num_addresses) 取一个主机(全段均匀, 含网络/广播地址,
    /32 亦可采); 撞重则弃该段继续; 采满 needed 或段尽即止 —— 段不足
    配额时如实短(宁少算, member_count 如实), 不回绕补采。
    段 version != 4 跳过不炸(生产 cloud_ranges 中间文件 aws/gcp/azure
    混 v6_prefixes; 宁少算), 跳过计数返调用方入 params —— 无证据即无话,
    但跳了多少要说。跳过不消耗 rng 也不改 v4 段相对序, v6 段存在与否
    不改变 v4 采样(排序在前, 循环内逐段跳)。
    """
    nets = sorted({ipaddress.ip_network(c, strict=False) for c in cloud_ranges},
                  key=lambda n: (int(n.network_address), n.prefixlen))
    out: list[str] = []
    seen: set[str] = set()
    skipped_v6 = 0
    for net in nets:
        if len(out) >= needed:
            break
        if net.version != 4:
            skipped_v6 += 1
            continue
        ip = str(ipaddress.IPv4Address(int(net.network_address) + rng.randrange(net.num_addresses)))
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out, skipped_v6


def build_infra_asset(out_dir: Path, *, version: str, run_seed: int,
                      cloud_ranges: list[str], resolver_ips: list[str]) -> AssetMeta:
    """kind=infra: 非指控基础设施层资产(spec §2.1)。

    members = 解析器输入(去重)∪ 云/CDN 采样 177(CLOUD_SAMPLE_N)。
    run_seed(S36 必填 kw-only)只喂云侧 rng; resolver_ips 侧应为调用方
    经 non_vpn_resolvers 过滤后的干净清单(320 侧口径)。params 记采样
    方法+输入指纹+两侧计数(第14轮: 报告记采样指纹, 语料指纹条款同构)。
    """
    rng = random.Random(run_seed)
    resolvers = sorted(set(resolver_ips))
    cloud, skipped_v6 = _sample_cloud_hosts(cloud_ranges, CLOUD_SAMPLE_N, rng)
    members = sorted(set(resolvers) | set(cloud))
    meta = AssetMeta(
        version=version,
        kind="infra",
        fingerprint=fingerprint(members),
        member_count=len(members),
        params={
            "run_seed": run_seed,
            "sample_method": "sorted-block-one-host",
            "n_resolvers": len(resolvers),
            "n_cloud_sampled": len(cloud),
            "skipped_v6_blocks": skipped_v6,
            "cloud_target": CLOUD_SAMPLE_N,
            "resolver_fingerprint": fingerprint(resolvers),
            "cloud_ranges_fingerprint": fingerprint(list(cloud_ranges)),
        },
        eval_env="monthly",
        created_at=_today(),
    )
    save_asset(Path(out_dir), members, meta)
    return meta


def build_consensus_asset(out_dir: Path, *, version: str, run_seed: int,
                          source_keysets: dict[str, list[str]],
                          per_source: int = PER_SOURCE_N) -> AssetMeta:
    """kind=consensus: 共识代理层资产(spec §2.1 逐源采 30, IP 配额)。

    rng 单实例 seed=run_seed(S36 必填 kw-only), 按源名字典序逐源
    rng.sample 消耗(顺序即契约: 换源名序=换采样结果); 宁少算 —— 键集
    不足 per_source 全取, 空键集贡献零, 均不炸。去重并集排序落盘;
    Q22: 诊断层容量独立声明, member_count = 并集实数(池竭不设闸)。
    """
    rng = random.Random(run_seed)
    members: set[str] = set()
    for name in sorted(source_keysets):
        keys = sorted(set(source_keysets[name]))
        members.update(rng.sample(keys, min(per_source, len(keys))))
    out = sorted(members)
    meta = AssetMeta(
        version=version,
        kind="consensus",
        fingerprint=fingerprint(out),
        member_count=len(out),
        params={
            "run_seed": run_seed,
            "per_source": per_source,
            "n_sources": len(source_keysets),
        },
        eval_env="monthly",
        created_at=_today(),
    )
    save_asset(Path(out_dir), out, meta)
    return meta


def build_all_monthly(assets_root: Path, *, version: str, run_seed: int,
                      cloud_ranges: list[str], resolver_ips: list[str],
                      source_keysets: dict[str, list[str]]) -> dict[str, AssetMeta]:
    """月轮三件套(truth 不产: T4 自有三闸, 健康度不过即拒出版)。

    目录布局 assets_root/<kind>/ = layered.assemble_four_layers 的
    load 路径; 缺 truth 目录由装配侧出显式 NO-LAYER 哨兵(§2.3 禁跳层)。
    """
    root = Path(assets_root)
    return {
        "neutral": build_neutral_asset(root / "neutral", version=version),
        "infra": build_infra_asset(root / "infra", version=version,
                                   run_seed=run_seed, cloud_ranges=cloud_ranges,
                                   resolver_ips=resolver_ips),
        "consensus": build_consensus_asset(root / "consensus", version=version,
                                           run_seed=run_seed,
                                           source_keysets=source_keysets),
    }
