#!/usr/bin/env python3
"""same-start 碰撞全源审计(grill Q5,2026-10-11)。

`_lmdb.py` docstring 红线:每源必须 ZERO same-start 碰撞(同 start 异长
CIDR 同键后写覆盖,超网剩余段静默丢失)。rebuild 写循环内绊线只查相邻对
(流式 O(1) 内存预算);本脚本查全量:对注册表全部启用源拦截
rebuild_dual_family 的 records 流——每源真实 rebuild 前半程(parse/harvest
产物,零影子提取器,不随 harvester 漂移;对照:audit_lmdb_invariants.py
是逐文件嗅探口径),按 start 分组,组内出现 >1 种 prefixlen 即违例。

数据目录只读(fusion_replay_gate 同款保证):
  - IP_RADAR_POOL_CHILD=1:cleanup_stale 直返,不 rmtree 镜像(caida_asorg
    rebuild→load 会走到);
  - InfraServicesSource._sync_projection 置 no-op:投影自愈是写路径
    (Task 5,2026-10-11);
  - rebuild_dual_family 换 spy:不建 staging、不写 ptr/sidecar,零写调用。

用法:python scripts/audit_same_start.py [--data DIR]
(主仓 venv:/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python)
退出码:0 全过(含免疫)/ 1 有违例或错误 / 2 配置错误。
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from array import array
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]   # scripts/ -> 仓库根
BACKEND_DIR = REPO_ROOT / "backend"


class _Collector:
    """单源 records 流 → (start, prefixlen) 紧凑收集,后置分组判违例。

    v4 打包 array('Q')((start<<6)|plen,排序分组;ipinfo_lite 3.3M 行
    ~27MB,内存平坦);v6 的 128-bit start 装不进 Q,但 v6 源全是小表,
    用 dict 存原始 cidr 串直报。
    """

    def __init__(self):
        self.v4 = array("Q")
        self.v6: dict[int, dict[int, str]] = {}   # start → {plen: 原始 cidr}
        self.rows = 0

    def feed(self, cidr: str) -> None:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return                    # 与写循环同宽容度:坏行不计
        self.rows += 1
        start = int(net.network_address)
        if isinstance(net, ipaddress.IPv6Network):
            self.v6.setdefault(start, {}).setdefault(net.prefixlen, cidr)
        else:
            self.v4.append((start << 6) | net.prefixlen)

    def analyze(self) -> tuple[list[str], int]:
        """→ (违例行, distinct start 键数 v4+v6)。每个违例 start 一行,
        组内全部异长 CIDR 由短到长 '&' 连接。"""
        out: list[str] = []
        keys = len(self.v6)
        vals = sorted(self.v4)
        i = 0
        while i < len(vals):
            start = vals[i] >> 6
            plens: list[int] = []
            j = i
            while j < len(vals) and (vals[j] >> 6) == start:
                p = vals[j] & 63      # 排序后同 plen 相邻,顺带去重重复行
                if not plens or p != plens[-1]:
                    plens.append(p)
                j += 1
            keys += 1
            if len(plens) > 1:
                out.append(" & ".join(
                    str(ipaddress.IPv4Network((start, p))) for p in plens))
            i = j
        for start, by_plen in self.v6.items():
            if len(by_plen) > 1:
                out.append(" & ".join(
                    by_plen[p] for p in sorted(by_plen)))
        return out, keys


_last: _Collector | None = None        # spy 每次 rebuild 交出的收集器


def _install_spy() -> None:
    """rebuild_dual_family → 只读 spy。

    全部 rebuild 变体(三套基类 + firehol/ipinfo_lite 直调 +
    commit_dual_family 共同尾巴)都在方法体内延迟 `from ._lmdb import`,
    提交期取模块属性——patch 模块属性即全量截获。返回 (0, 0) 对齐调用方
    解包形状;owner 内存态不落任何 sidecar。
    """
    import ipdb._sources._lmdb as lmdb_mod

    def spy(records, v4_base, v6_base, **kwargs):
        global _last
        col = _Collector()
        stream = records() if callable(records) else records
        for cidr, _ev in stream:
            col.feed(cidr)
        _last = col
        return (0, 0)

    lmdb_mod.rebuild_dual_family = spy


def main() -> int:
    default_data = BACKEND_DIR / "data"
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=default_data,
                    help=f"数据目录(默认 {default_data};worktree 跑时指主仓)")
    args = ap.parse_args()
    data_dir: Path = args.data.resolve()
    if not data_dir.is_dir():
        print(f"error: data dir not found: {data_dir}", file=sys.stderr)
        return 2

    global _last
    # 导入 ipdb 前定环境(fusion_replay_gate 同款):DATA_DIR 决定注册表
    # 实例化到哪个库;POOL_CHILD 关掉 load 路径的启动清理写。
    os.environ["IP_RADAR_DATA_DIR"] = str(data_dir)
    os.environ["IP_RADAR_POOL_CHILD"] = "1"
    sys.path.insert(0, str(BACKEND_DIR))
    _install_spy()                    # 触发 ipdb 包导入(含 _registry)
    from ipdb._sources.infra_services import InfraServicesSource
    InfraServicesSource._sync_projection = lambda self: None  # 只读:写路径禁用
    import ipdb._registry as reg

    audited = [s for s in reg._sources if reg.is_enabled(s.name)]
    disabled = [s.name for s in reg._sources if not reg.is_enabled(s.name)]
    print(f"auditing {len(audited)} enabled sources under {data_dir}"
          + (f" ({len(disabled)} disabled skipped: {','.join(disabled)})"
             if disabled else ""))
    violators = errors = 0
    for src in audited:
        _last = None
        if not src._path.exists():
            print(f"{src.name}: SKIPPED no raw file ({src._path.name})")
            continue
        try:
            src.rebuild()
        except Exception as e:        # noqa: BLE001 — 审计逐源活着,不整体死
            print(f"{src.name}: ERROR {type(e).__name__}: {e} FAIL")
            errors += 1
            continue
        if _last is None:
            print(f"{src.name}: IMMUNE no records flow (no LMDB per-IP face)")
            continue
        viols, keys = _last.analyze()
        if viols:
            violators += 1
            print(f"{src.name}: rows={_last.rows} keys={keys} "
                  f"VIOLATIONS={len(viols)}")
            for v in viols:
                print(f"    {v}")
        else:
            print(f"{src.name}: rows={_last.rows} keys={keys} CLEAN")
    print(f"--- summary: {len(audited)} enabled sources, "
          f"{violators} with same-start violations, {errors} errored")
    return 1 if (violators or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
