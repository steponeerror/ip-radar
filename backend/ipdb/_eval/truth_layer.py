"""威胁真值层 ETL: rir 日期闸① + 扫描段滤 + 输入健康度 (spec §2.2/S9).

Hornet 65 Niner 原始蜜罐 IP → 可出版 truth 资产(经 assets.save_asset):
- 闸① rir 过滤: 分配日期 ≥2024-07-02 的段内 IP 剔除, 2024-07-01(含)及
  更早保留 —— 防重分配假阴性惩罚正确行为(grill 待办12 逐字对齐)。
  日期按 YYYYMMDD 整数比较, 不做日期解析。
- 扫描段滤: 扫描器 CIDR/bare-IP 前缀表内 IP 剔除(方法论混杂输入侧)。
- 输入健康度(S9): rir 段数 <10_000 或扫描清单空 → degraded →
  build_truth_layer 抛 TruthLayerDegradedError 且不写盘 —— DEGRADED
  拒出版优先于「宁可出版」, 不得静默剔光后出版读数。

meta.params 携带 rir/scanlist 输入指纹(S37 rir 快照纳入语料版本化,
§2.3 互锁)。闸②长记忆分拆(F5)/闸③k 双报(F6)不属本模块(归读数任务)。
"""
import ipaddress
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ipdb._eval.assets import AssetMeta, fingerprint, save_asset

# 闸①边界已冻结, 勿改: ≥2024-07-02 剔除; 2024-07-01(含)及更早保留(spec §2.2)
RIR_CUTOFF = "2024-07-02"
# S9 输入健康度地板: rir 快照段数低于此值 = 输入坍塌, 拒出版
MIN_RIR_RANGES = 10_000


class TruthLayerDegradedError(RuntimeError):
    """三闸输入坍塌(S9): 拒绝出版, 不是静默剔光。"""


def parse_rir_delegated(lines: Iterable[str]) -> list[tuple[int, int, str]]:
    """delegated-extended 行 → ipv4 段 (start_int, host_count, date)。

    收 ≥7 字段且 type=ipv4、status=allocated/assigned 的行: 真格式带第
    8 列 opaque-id(2026-10-14 首真数据实测: 7 字段断言 → 镜像五文件 0
    段),富余列忽略; 版本行(type 非ipv4)、汇总行(status=summary)自然出
    局。结构合法但字段坏(如 start 非 IP)则 ValueError 炸出 —— 坏快照不
    许静默缩水。
    """
    out = []
    for line in lines:
        parts = line.strip().split("|")
        if len(parts) < 7 or parts[2] != "ipv4" or parts[6] not in ("allocated", "assigned"):
            continue
        out.append((int(ipaddress.IPv4Address(parts[3])), int(parts[4]), parts[5]))
    return out


def _drop_in_ranges(ips: Iterable[str], pairs: list[tuple[int, int]]) -> tuple[list[str], int]:
    """剔落入任一 (start, size) 段的 IP, 返回 (保留, 剔除数)。

    先排序合并为不相交闭区间再做 bisect 判定: 一次 O(log n)/IP,
    且对重叠输入仍精确(rir 闸与扫描段滤共用; 扫描清单 ~百条线性亦可,
    共用一套更省)。
    """
    merged: list[tuple[int, int]] = []
    for s, e in sorted((s, s + v - 1) for s, v in pairs if v > 0):
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    starts = [s for s, _ in merged]
    kept, dropped = [], 0
    for ip in ips:
        n = int(ipaddress.IPv4Address(ip))
        i = bisect_right(starts, n) - 1
        if i >= 0 and n <= merged[i][1]:
            dropped += 1
        else:
            kept.append(ip)
    return kept, dropped


def apply_rir_filter(ips: Iterable[str], rir_ranges, cutoff: str = RIR_CUTOFF) -> tuple[list[str], int]:
    # YYYYMMDD 整数比较, 不解析日期; ≥cutoff 分配段 = 新近重分配证据 → 剔
    cutoff_int = int(cutoff.replace("-", ""))
    fresh = [(s, v) for s, v, d in rir_ranges if int(d) >= cutoff_int]
    return _drop_in_ranges(ips, fresh)


def apply_scanner_filter(ips: Iterable[str], prefixes: list[str]) -> tuple[list[str], int]:
    # bare IP 经 ip_network 即 /32; strict=False 容忍前缀表里的主机位脏写
    nets = [ipaddress.ip_network(p, strict=False) for p in prefixes]
    pairs = [(int(n.network_address), n.num_addresses) for n in nets]
    return _drop_in_ranges(ips, pairs)


def gates_health(rir_ranges, scanner_prefixes) -> dict:
    return {
        "rir_ok": len(rir_ranges) >= MIN_RIR_RANGES,
        "scanner_ok": len(scanner_prefixes) > 0,
        "degraded": len(rir_ranges) < MIN_RIR_RANGES or not scanner_prefixes,
    }


def build_truth_layer(raw_ips, rir_ranges, scanner_prefixes, out_dir, version) -> AssetMeta:
    health = gates_health(rir_ranges, scanner_prefixes)
    if health["degraded"]:
        # 健康检查先于任何落盘动作: DEGRADED 时目录必须无产出(S9)
        raise TruthLayerDegradedError(f"truth-layer input gates degraded: {health}")
    after_rir, n_rir = apply_rir_filter(raw_ips, rir_ranges)
    members, n_scan = apply_scanner_filter(after_rir, scanner_prefixes)
    members = sorted(set(members))  # 语料成员语义=去重定序, 资产字节确定
    meta = AssetMeta(
        version=version,
        kind="truth",
        fingerprint=fingerprint(members),
        member_count=len(members),
        params={
            # S37: 两输入快照指纹入语料版本化; rir 侧经解析产物规范化
            # (start|value|date), 同输入同指纹
            "rir_fingerprint": fingerprint([f"{s}|{v}|{d}" for s, v, d in rir_ranges]),
            "scanlist_fingerprint": fingerprint(list(scanner_prefixes)),
            "rir_cutoff": RIR_CUTOFF,
            "removed_by_rir_gate": n_rir,
            "removed_by_scanner_filter": n_scan,
        },
        eval_env="monthly",  # EVAL_ENV 隔离(T11)前先钉 monthly
        created_at=datetime.now(timezone.utc).date().isoformat(),
    )
    save_asset(Path(out_dir), members, meta)
    return meta
