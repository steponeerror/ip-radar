"""sinkhole 污染探针(ADR 0013 / issue #233 T2)。

已知 sinkhole 段(MISP misp-warninglists sinkholes,203 项 = 186 裸 IP
+ 17 CIDR;eval-only 语料 sinkhole_ranges.json,双 pin 见 sidecar
sinkhole_ranges.provenance.json:MISP version 20261014 + list.json 内容
SHA256 + 上游 brakmic/Sinkholes @ 1a284cd9)被指控源命中记污染分不记
恶意分 ——「把 sinkhole IP 当 C2 上榜」是已知 FP 模式(GLOSSARY「污染
探针」)。语料永不进 LMDB/产品源;运行期零网络(取数一次性,已固化)。

口径(全部既有原语,零新机制;结构照 agg_share.py 个案):
- 探针语料 = 启用指控源 raw 文件的稳定采样(agg_share.probe_ips 原样
  复用:per-source stable_seed + 容量帽截断,同 seed 逐字节可复算);
- 成员判定 = 精确裸 IP 相等 + CIDR 线性包含(203 条无性能问题,勿引
  truth_layer 二分机 —— 规模不配机械;探针采样面 v4-only);
- 污染归因 = lookup 载荷指控池按生产同款重算(by_source 取 max 系数 →
  dedup_lineage,agg_share.py:49-66 逐字先例),per-IP accuser 并集内
  的源才记命中 —— 裸用 detail.source 会让镜像对(firehol/greensnow)
  双计,违「宁少算」;同源同 IP 多指控组只记一次;
- 分层 = CIDR 基(强信号)vs 单 IP 基(弱信号:union-never-replace 政
  策让已退役 sinkhole IP 永驻列表,存在回收重指派残余风险 —— provenance
  sidecar/notes 条件);
- artifact 保留原始 (source, ip, sinkhole_entry) 三元组可回查,不裸给
  结论;per-源污染读数 = 命中数/|probe|;
- v0 只测量不持门(ADR 0013:阈值冻结另走验收门):无阈值,exit 恒 0
  (操作失败原样上抛除外,2026-10-10 假零判例)。
"""
from __future__ import annotations

import datetime as _dt
import ipaddress
import json
from pathlib import Path

from .agg_share import SAMPLE_PER_SOURCE, TOTAL_CAP, probe_ips
from .exclusive import DEFAULT_SEED
from .._logodds import coefficient, dedup_lineage
from .._types import _ACCUSING

SINKHOLE_ASSET = Path(__file__).parent / "sinkhole_ranges.json"
SINKHOLE_PROVENANCE = Path(__file__).parent / "sinkhole_ranges.provenance.json"


def load_sinkhole_ranges(asset: Path = SINKHOLE_ASSET) -> dict[str, list[str]]:
    """加载 eval-only sinkhole 语料 → {"ip": [...], "cidr": [...]};条目
    MISP 原拼写(裸 IP 不带 /32,勿在语料文件改写)。坏条目(不可解析
    v4 地址/网段)ValueError 炸出 —— 静默缩水=证据灭失。"""
    d = json.loads(Path(asset).read_text(encoding="utf-8"))
    ips, cidrs = d.get("ip") or [], d.get("cidr") or []
    for e in ips:
        ipaddress.IPv4Address(e)          # 解析即校验,坏值 ValueError
    for e in cidrs:
        net = ipaddress.ip_network(e, strict=False)
        if net.version != 4:
            raise ValueError(f"non-IPv4 sinkhole entry: {e!r}")
    if not ips and not cidrs:
        raise ValueError("empty sinkhole corpus (203 entries expected)")
    return {"ip": list(ips), "cidr": list(cidrs)}


def sinkhole_match(ip: str, ranges: dict[str, list[str]]) -> str | None:
    """成员判定:精确裸 IP 相等 → CIDR 线性包含;返回命中条目原串(分层
    依据 = 含 '/')或 None。非法 token(_IP_RE 允许 999.x)非成员不炸
    —— 成员判定语义,非 lookup 假零面。"""
    for entry in ranges["ip"]:
        if ip == entry:
            return entry
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for entry in ranges["cidr"]:
        if addr in ipaddress.ip_network(entry, strict=False):
            return entry
    return None


def sinkhole_probe(lookup_fn, probe_ips: list[str],
                   ranges: dict[str, list[str]] | None = None) -> dict:
    """纯函数:probe_ips × sinkhole 语料 → 污染读数结构(见模块 docstring
    口径)。单个 lookup 失败原样上抛,不 except-continue(假零判例)。"""
    if ranges is None:
        ranges = load_sinkhole_ranges()
    n_probe = len(probe_ips)
    n_members = n_members_cidr = n_members_ip = 0
    hits: dict[str, int] = {}
    hits_cidr: dict[str, int] = {}
    hits_ip: dict[str, int] = {}
    evidence: list[dict] = []
    for ip in probe_ips:
        entry = sinkhole_match(ip, ranges)
        if entry is None:
            continue
        n_members += 1
        is_cidr = "/" in entry
        if is_cidr:
            n_members_cidr += 1
        else:
            n_members_ip += 1
        payload = lookup_fn(ip)
        accusers_ip: set[str] = set()      # per-IP 并集:同源多组只记一次
        for ctype, ca in (payload.get("classifications") or {}).items():
            # 指控池重算(生产 _merge 同款:同源取 max 系数 → dedup_lineage;
            # agg_share.py:49-66 逐字先例 —— 裸用 detail.source 镜像对双计)
            by_source: dict[str, float] = {}
            for d in ca.get("details") or ():
                if d.get("verdict") not in _ACCUSING:
                    continue
                src = d.get("source")
                if not src:
                    continue
                c = coefficient(d.get("reliability", 0.5),
                                d.get("first_seen"), ctype)
                if src not in by_source or c > by_source[src]:
                    by_source[src] = c
            accusers_ip |= {s for s, _ in dedup_lineage(sorted(by_source.items()))}
        for src in sorted(accusers_ip):
            hits[src] = hits.get(src, 0) + 1
            if is_cidr:
                hits_cidr[src] = hits_cidr.get(src, 0) + 1
            else:
                hits_ip[src] = hits_ip.get(src, 0) + 1
            evidence.append({"source": src, "ip": ip,
                             "sinkhole_entry": entry})

    def _share(n: int):
        return (n / n_probe) if n_probe else None   # 零探针≠零污染(缺层≠0)

    side = json.loads(SINKHOLE_PROVENANCE.read_text(encoding="utf-8"))
    return {
        "kind": "sinkhole_probe",
        "n_probe": n_probe,
        "n_members": n_members,
        "n_members_cidr": n_members_cidr,
        "n_members_ip": n_members_ip,
        "polluted_sources": {
            src: {"hits": h, "share": _share(h),
                  "hits_cidr": hits_cidr.get(src, 0),
                  "share_cidr": _share(hits_cidr.get(src, 0)),
                  "hits_ip": hits_ip.get(src, 0),
                  "share_ip": _share(hits_ip.get(src, 0))}
            for src, h in sorted(hits.items())
        },
        "evidence": evidence,               # 原始三元组,不裸给结论
        "corpus": {                          # 双 pin 随件(sidecar 透传)
            "version": side["misp"]["version"],
            "sha256": side["misp"]["sha256"],
            "upstream_commit": side["upstream"]["commit_sha"],
            "entries": side["entries"],
        },
        "note": ("pollution reads, not malicious scores (sinkhole IP on a "
                 "feed = known FP pattern); bare-IP layer carries "
                 "reassignment residual risk (union-never-replace); "
                 "measurement only, no gate (ADR 0013)"),
    }


def run_sinkhole_probe(registry, out_dir=None) -> dict:
    """CLI 装配:启用指控源 → 采样(agg_share.probe_ips 同款,采样参数
    随件可回算)→ 污染读数;可选落 <out_dir>/model/sinkhole-probe-<ts>
    .json(agg-share 报告族同形,ts 同款;env 已编码在 REPORT_DIR =
    base/<env>,勿在件内重复);本腿只测量,异常原样上抛。"""
    res = sinkhole_probe(
        registry.lookup, probe_ips(list(registry.sources)))
    res["sample"] = {"per_source": SAMPLE_PER_SOURCE, "total": TOTAL_CAP,
                     "seed": DEFAULT_SEED,
                     "method": "per-source stable_seed(name) + total-cap "
                               "sample_keys (agg_share.probe_ips)"}
    if out_dir is not None:
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        (d / f"sinkhole-probe-{ts}.json").write_text(json.dumps(
            res, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    return res
