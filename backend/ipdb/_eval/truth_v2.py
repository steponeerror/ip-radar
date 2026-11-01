"""真值语料 v2 构建器: 自建行为观测 → 90 天滚动窗真值资产(ADR 0017).

与 v1 truth_layer.py(Hornet 静态卷)的分界: v1 输入=蜜罐静态 IP 名单+
冻结 cutoff(2024-07-02); v2 输入=小机周快照目录(T0 采集器产物,
scripts/truth_v2_weekly_snapshot.sh 格式)+ 预留的 honyport CSV 组件,
cutoff 随窗滚动。本模块只做 eval 侧纯文件语料, 不碰 LMDB/rebuild,
运行期零网络(ADR 0017 §7: 真值数据永不入池/private_sources)。

管线(issue #260 验收线):
  周快照 CSV → 90 天滚动窗(窗界=全组件最新快照日锚定, 数据派生保字节
  级可复现)→ ops 白名单(文件传入, 默认空)→ RFC1918/保留段剔 →
  扫描段滤(scanner_ranges.csv 首列机制, 缺件 raise 不静默缩水)→
  RIR 滚动 cutoff(分配日 ≥ 窗起点的段内 IP 剔, ADR 0017 §6 推广
  ADR 0002 §2 到滚动窗)→ 组件闸(单组件 ≥1,000 独立攻击 IP 才入装配,
  ADR 0017 §4)→ 版本化资产(月度重切)+ 双 pin sidecar(成员指纹入
  meta.json + 输入 sha256 入 provenance.json, S12 版本化 + sinkhole
  provenance 先例)。

三闸负例(测试面 test_eval_truth_v2.py): RIR 滚动 cutoff / 扫描段滤
(缺件 raise)/ 组件闸 1,000(不足=不装配+哨兵状态件, 不 raise)。

v1 的 MIN_RIR_RANGES=10_000 段闸不套用(ADR 0017 §6: 量闸以组件 1,000
取代 Hornet 的 10,000 段闸; rir 数据面仅保「空面 fail-loud」底线)。
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import date, timedelta
from pathlib import Path

from .assets import AssetMeta, fingerprint, save_asset
from .layer_builders import scanner_ranges_prefixes
from .truth_layer import apply_rir_filter, apply_scanner_filter, parse_rir_delegated

# ADR 0017 §3: 90 天滚动窗(业界留存窗共识 30-90 天的上限, 月度重切)
WINDOW_DAYS = 90
# ADR 0017 §4: 组件闸 —— 单数据组件 ≥1,000 独立攻击 IP 才入装配
MIN_COMPONENT_IPS = 1_000
# 资产 kind(assets.KINDS 同步扩展; 与 Hornet 的 truth 分立, T3 并排对照用)
ASSET_KIND = "truth_v2"


def window_bounds(anchor: date) -> tuple[date, date]:
    """锚日(全组件最新快照日)→ (窗起, 窗止), 含两端共 WINDOW_DAYS 天。

    锚日从数据派生而非墙钟: 同输入重跑字节级一致(issue #260 验收线)
    的前提; 窗起点当日观测属本版, 前一天属上一版(边界归属测试钉住)。
    """
    return anchor - timedelta(days=WINDOW_DAYS - 1), anchor


def parse_snapshot_csv(path: Path) -> tuple[date, dict[str, int]]:
    """T0 周快照 CSV → (采集日, {ip: attempts})。

    头部 `# captured_at=YYYY-MM-DDT...` 行取日期部分为采集日; 数据行
    `ip,attempts`。缺 captured_at / 坏行 / 非 v4 / 非整数 attempts 一律
    ValueError 炸出 —— 坏快照不许静默缩水(parse_rir_delegated 同款哲学)。
    """
    captured: str | None = None
    rows: dict[str, int] = {}
    in_body = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            for part in line.split():
                if part.startswith("captured_at="):
                    captured = part.split("=", 1)[1]
            continue
        if not in_body:
            if line.strip() == "ip,attempts":
                in_body = True
            continue
        if not line.strip():
            continue
        ip, _, attempts = line.partition(",")
        rows[str(ipaddress.IPv4Address(ip.strip()))] = int(attempts.strip())
    if captured is None:
        raise ValueError(f"snapshot {path}: missing captured_at header")
    if not in_body:
        raise ValueError(f"snapshot {path}: missing 'ip,attempts' header")
    return date.fromisoformat(captured[:10]), rows


def load_snapshots(snap_dir: Path) -> list[tuple[Path, date, dict[str, int]]]:
    """组件目录 → 按文件名序的 [(路径, 采集日, 行)]。目录缺席 → FileNotFound
    Error; 空目录 → ValueError(锚日无从派生 = 输入面坏, fail-loud)。"""
    d = Path(snap_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"snapshots dir not found: {d}")
    files = sorted(d.glob("*.csv"))
    if not files:
        raise ValueError(f"no snapshots (*.csv) under {d}")
    out = []
    for p in files:
        day, rows = parse_snapshot_csv(p)
        out.append((p, day, rows))
    return out


def load_rir_ranges(rir_dir: Path) -> list[tuple[int, int, str]]:
    """rir_delegated 数据面目录({reg}.txt 五件)→ ipv4 段表(复用
    parse_rir_delegated, ADR 0017 §6)。空面(0 段)ValueError: rir 闸
    静默失能 = 排除面无声缩水。"""
    d = Path(rir_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"rir dir not found: {d}")
    out: list[tuple[int, int, str]] = []
    for p in sorted(d.glob("*.txt")):
        out.extend(parse_rir_delegated(
            p.read_text(encoding="utf-8").splitlines()))
    if not out:
        raise ValueError(f"rir face collapsed: 0 ipv4 ranges under {d}")
    return out


def load_ops_allowlist(path: Path | None) -> list[str]:
    """自家运维源白名单(ADR 0017 §8): 一行一个 v4, # 注释/空行跳过;
    传入路径缺席 → FileNotFoundError; 坏行 ValueError(白名单失配=
    静默放行运维 IP, fail-loud)。None(默认) = 无白名单。"""
    if path is None:
        return []
    out: list[str] = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        token = ln.strip()
        if not token or token.startswith("#"):
            continue
        out.append(str(ipaddress.IPv4Address(token)))
    return out


def apply_reserved_filter(ips) -> tuple[list[str], int]:
    """剔 RFC1918(10/8, 172.16/12, 192.168/16)及保留段(环回/链路本地/
    CGNAT 100.64/10/文档段/240/4/广播等)。判定 = not is_global: 该属性
    即上述全部非全球可路由面的标准谓词(ipaddress 库语义), 宁少算 ——
    不可路由段上的"攻击观测"无跨库比对价值。"""
    kept, dropped = [], 0
    for ip in ips:
        if ipaddress.IPv4Address(ip).is_global:
            kept.append(ip)
        else:
            dropped += 1
    return kept, dropped


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean_component(snapshots: list[tuple[Path, date, dict[str, int]]],
                     w_start: date, w_end: date,
                     allowlist: list[str], scanner_prefixes: list[str],
                     rir_ranges, rir_cutoff: str) -> dict:
    """单组件清洗链: 窗 → 白名单 → 保留段 → 扫描段 → rir 滚动闸。
    返回逐级计数 + 终局成员(证据不灭失: 败因可审计)。"""
    raw = set()
    for _, _, rows in snapshots:
        raw |= rows.keys()
    in_window = set()
    for _, day, rows in snapshots:
        if w_start <= day <= w_end:
            in_window |= rows.keys()
    allow_set = set(allowlist)
    kept = sorted(in_window)
    counts = {
        "n_snapshots": len(snapshots),
        "n_snapshots_in_window": sum(
            1 for _, day, _ in snapshots if w_start <= day <= w_end),
        "raw_unique": len(raw),
        "removed_by_window": len(raw) - len(in_window),
        "n_attempts_in_window": sum(sum(rows.values())
                                    for _, day, rows in snapshots
                                    if w_start <= day <= w_end),
    }
    kept = [ip for ip in kept if ip not in allow_set]
    counts["removed_by_allowlist"] = len(in_window) - len(kept)
    kept, n_reserved = apply_reserved_filter(kept)
    counts["removed_by_reserved"] = n_reserved
    kept, n_scan = apply_scanner_filter(kept, scanner_prefixes)
    counts["removed_by_scanner_filter"] = n_scan
    kept, n_rir = apply_rir_filter(kept, rir_ranges, cutoff=rir_cutoff)
    counts["removed_by_rir_gate"] = n_rir
    counts["member_count"] = len(kept)
    counts["members"] = kept
    return counts


def run_truth_v2(components: dict[str, Path], *, rir_dir: Path,
                 scanner_csv: Path, allowlist: Path | None,
                 out_root: Path, eval_env: str) -> dict:
    """装配入口(纯文件 IO): 组件目录 → 版本化 v2 真值资产。

    输出布局 out_root/<version>/: 过闸 → ips.txt + meta.json +
    provenance.json(S12 版本化 + 双 pin sidecar); 全组件不过闸 → 仅
    status.json 哨兵(不 raise, ADR 0017 §4)。created_at = 锚日(数据
    派生)而非墙钟 —— 同输入重跑字节级一致。互斥红线: 产物只在 eval
    语料目录, 永不写 private_sources/池(ADR 0017 §7)。
    """
    if not components:
        raise ValueError("no components given (--truth-v2-component name=dir)")
    scanner_prefixes = scanner_ranges_prefixes(scanner_csv)  # 缺件自然 raise
    rir_ranges = load_rir_ranges(rir_dir)
    allowlist_path = allowlist
    allowlist = load_ops_allowlist(allowlist)

    snapshots = {name: load_snapshots(Path(d))
                 for name, d in sorted(components.items())}
    anchor = max(day for snaps in snapshots.values() for _, day, _ in snaps)
    w_start, w_end = window_bounds(anchor)
    version = f"truthv2-{anchor:%Y%m}"
    rir_cutoff = w_start.isoformat()       # 滚动 cutoff = 窗起点(ADR 0017 §6)

    comp_stats: dict[str, dict] = {}
    for name in sorted(snapshots):
        comp_stats[name] = _clean_component(
            snapshots[name], w_start, w_end, allowlist,
            scanner_prefixes, rir_ranges, rir_cutoff)
        comp_stats[name]["gate_passed"] = (
            comp_stats[name]["member_count"] >= MIN_COMPONENT_IPS)

    members = sorted({ip for st in comp_stats.values() if st["gate_passed"]
                      for ip in st["members"]})
    vdir = Path(out_root) / version

    def _comp_prov(name: str) -> dict:
        st = comp_stats[name]
        return {
            "files": [
                {"name": p.name, "sha256": _sha256_file(p),
                 "captured_at": day.isoformat()}
                for p, day, _ in snapshots[name]],
            "gate_passed": st["gate_passed"],
            **{k: v for k, v in st.items() if k != "members"},
        }

    inputs_pin = {
        "components": {name: _comp_prov(name) for name in sorted(comp_stats)},
        "ops_allowlist": (
            {"provided": True, "n": len(allowlist),
             "sha256": _sha256_file(allowlist_path)}
            if allowlist_path is not None else {"provided": False, "n": 0}),
        "scanner_ranges": {
            "path": str(scanner_csv), "n_prefixes": len(scanner_prefixes),
            "sha256": _sha256_file(scanner_csv),
            "fingerprint": fingerprint(list(scanner_prefixes))},
        "rir": {
            "dir": str(rir_dir), "n_ranges": len(rir_ranges),
            "cutoff": rir_cutoff,
            "fingerprint": fingerprint(
                [f"{s}|{v}|{d}" for s, v, d in rir_ranges]),
            "files": [
                {"name": p.name, "sha256": _sha256_file(p)}
                for p in sorted(Path(rir_dir).glob("*.txt"))]},
    }

    if not members:
        # 组件闸全败: 不装配 + 哨兵状态件 + 不 raise(ADR 0017 §4)
        vdir.mkdir(parents=True, exist_ok=True)
        status = {
            "kind": f"{ASSET_KIND}_status",
            "status": "insufficient",
            "version": version, "eval_env": eval_env,
            "window": {"start": w_start.isoformat(),
                       "end": w_end.isoformat(), "days": WINDOW_DAYS},
            "min_component_ips": MIN_COMPONENT_IPS,
            "components": {n: {k: v for k, v in st.items() if k != "members"}
                           for n, st in comp_stats.items()},
            "inputs": inputs_pin,
            "note": ("no component cleared the 1,000-IP component gate; "
                     "v2 stays appendix-only, Hornet keeps the verdict "
                     "(ADR 0017 §4)"),
        }
        (vdir / "status.json").write_text(
            json.dumps(status, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return {"status": "insufficient", "version": version,
                "window": status["window"], "member_count": 0,
                "components": {n: {"gate_passed": False,
                                   "member_count": st["member_count"]}
                               for n, st in comp_stats.items()},
                "out_dir": vdir}

    meta = AssetMeta(
        version=version,
        kind=ASSET_KIND,
        fingerprint=fingerprint(members),
        member_count=len(members),
        params={
            "window_start": w_start.isoformat(),
            "window_end": w_end.isoformat(),
            "window_days": WINDOW_DAYS,
            "rir_cutoff": rir_cutoff,
            "min_component_ips": MIN_COMPONENT_IPS,
            "rir_fingerprint": inputs_pin["rir"]["fingerprint"],
            "scanlist_fingerprint": inputs_pin["scanner_ranges"]["fingerprint"],
            "allowlist_fingerprint": fingerprint(list(allowlist)),
            "components": {
                n: {k: v for k, v in st.items() if k != "members"}
                for n, st in comp_stats.items()},
        },
        eval_env=eval_env,
        created_at=anchor.isoformat(),   # 锚日派生, 保字节级一致(非墙钟)
    )
    save_asset(vdir, members, meta)
    provenance = {
        "kind": f"{ASSET_KIND}_provenance",
        "adr": "0017",
        "generated": anchor.isoformat(),
        "window": {"start": w_start.isoformat(), "end": w_end.isoformat(),
                   "days": WINDOW_DAYS},
        "inputs": inputs_pin,
        "method": ("clean chain per component: 90d window -> ops allowlist "
                   "-> reserved segments -> scanner prefixes -> rolling rir "
                   "cutoff (>= window start dropped); component gate >=1000; "
                   "corpus = union of passing components"),
        "notes": [
            "真值↔考生互斥: 本语料永不入池/private_sources(ADR 0017 §7)",
            "honyport CSV 组件经 --truth-v2-component name=dir 并入(接口预留)",
            "输入快照来源: scripts/truth_v2_weekly_snapshot.sh(T0 采集器)",
        ],
    }
    (vdir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return {"status": "published", "version": version,
            "fingerprint": meta.fingerprint, "member_count": len(members),
            "window": provenance["window"],
            "components": {n: {"gate_passed": st["gate_passed"],
                               "member_count": st["member_count"]}
                           for n, st in comp_stats.items()},
            "asset_dir": vdir}
