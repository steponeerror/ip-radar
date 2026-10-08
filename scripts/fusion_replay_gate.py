#!/usr/bin/env python3
"""融合回放门(Task 3,C2/C3/C4 实证)—— 在生产数据镜像上并行重算
旧顶层选角(b3db5ee2)与新证据级融合(308310f1)的分数,逐 IP 流式聚合,
对部署门三判据给出 PASS/FAIL:

  C2  单指控组 IP 新旧分数恰好相等(退化恒等,全量计数)
  C3  benign 语料(指控 IP ∩ MISP warning lists 云/CDN/DNS 基础设施)
      分数 ≥70 占比:新 ≤ 旧(良性误报不升高)
  C4  Spearman ρ(分数 × dedup 后独立指控源数):新 ≥ 旧(佐证区分度不下降)

语料 = 31 个指控源(malicious/suspicious)LMDB v4 键起点(CIDR 起点)的
并集,k 路归并流式遍历,不物化 —— 每个起点代表该源一条区间证据;任意
被指控 IP 的证据集含于其最近左侧起点的证据集(evidence(x) ⊆
evidence(start(x)) 恒真;等号不总成立——起点证据可严格超于区间内成员),
故起点并集是无冗余的超集代表探测集。少量起点落在保留地址(查询短路)或纯存档证据
(firehol 子 feed informational verdict)→ 控池空,新旧同为 0/存档组
回退,恒等成立;C4 主口径取指控池非空语料,全探测到 ω 仅作语境。
benign 语料复用 `_eval` 基建:pymispwarninglists 装载 +
`_eval/config.IP_WARNINGLISTS` provider 口径(与 _eval.benign 同源);因库
内 slow_search 为 138ms/IP(全量不可行),区间包含判定改为本地折叠区间
数组 + bisect(语义同库 cidr 分支,启动时对样例自校验)。

内存红线(2026-10-03 教训):`main()` 首行设 `RLIMIT_DATA = 4GiB`(R3-F3:
import 本模块零副作用、不钳调用方 rlimit;CLI 跑语义不变)—— 限制
Python 侧匿名堆(brk + 私有匿名 mmap),超限分配立即 MemoryError(已
实测 5GiB bytearray 被拒)。不用 RLIMIT_AS:registry 需以只读 mmap 打开
全部 90 个 LMDB env,合计 map ≈ 6.94GB 地址空间,4GiB AS 下 load_db
直接不可能;红线本意是禁语料/结果全量物化(匿名堆),RLIMIT_DATA 精确
表达该约束。聚合器仅:直方图、列联表、计数器;逐 IP 处理完即丢。

用法(在 worktree 内跑主仓生产镜像;解释器用主仓 venv):
  /home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python \
      scripts/fusion_replay_gate.py \
      --data /home/huxiao/dev/pi-ip-lookup-tool/.eval-prod-data \
      --report <工作区>/replay-report.md
小切片自测:加 --limit 300(或系统抽样 --stride 100 --limit 250000)。

数据目录只读:导入 ipdb 前设 IP_RADAR_POOL_CHILD=1(Source.load 的
cleanup_stale 直接返回,绝不 rmtree 镜像),全程无写调用。
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import heapq
import ipaddress
import json
import os
import resource
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]          # scripts/ -> 仓库根
BACKEND_DIR = REPO_ROOT / "backend"                       # 代码 = 脚本所在仓(worktree)

# 与 b3db5ee2 / _merge._assess_classification 同一的 verdict 优先级(旧规则冻结语义)
_PRECEDENCE = {"malicious": 0, "suspicious": 1, "benign": 2, "informational": 3}
# 指控章语义口径(源筛选/组计数用;实现侧 live 口径从 _types 导入,见 main)
_ACCUSING = frozenset({"malicious", "suspicious"})

# C3 阈值（判据给定）与次级观察阈值
C3_THRESHOLD = 70
C3_THRESHOLD_HI = 90


def old_rule(result) -> int:
    """旧顶层选角，逐字内联自 b3db5ee2:backend/ipdb/_types.py threat_summary()
    —— 最坏 verdict（优先级最小）组内取 max 组置信度。只进本脚本，绝不回生产代码。"""
    detected = [v for v in result.classifications.values() if v.detected]
    if not detected:
        return 0
    worst = min(detected, key=lambda v: _PRECEDENCE.get(v.verdict, 99))
    return max(v.confidence for v in detected if v.verdict == worst.verdict)


def fusion_pool(result, coefficient, accusing_verdicts) -> dict[str, float]:
    """镜像 _types.threat_summary 的指控章池化循环（同源跨组取 max）；
    指控章集合用 _types._ACCUSING live 导入（与本脚本重算交叉核对，
    失配会计入 xcheck_bad，防镜像与实现漂移）。"""
    pool: dict[str, float] = {}
    for v in result.classifications.values():
        if v.verdict not in accusing_verdicts:
            continue
        for d in v.details:
            if d.get("verdict") not in accusing_verdicts:
                continue
            c = coefficient(d["reliability"], d.get("first_seen"), v.type)
            src = d["source"]
            if src not in pool or c > pool[src]:
                pool[src] = c
    return pool


def spearman_from_contingency(counts: dict[tuple[int, int], int]) -> float:
    """列联表精确 Spearman ρ(并列取中秩;Pearson-of-midranks)。
    counts[(score, k)] = IP 数;score∈0..100,k = dedup 后独立源数 —— 表
    尺寸 ≤101×32,内存 O(1),不存 per-IP 对。"""
    if not counts:
        return float("nan")
    nx: Counter = Counter()
    ny: Counter = Counter()
    for (x, y), c in counts.items():
        nx[x] += c
        ny[y] += c
    n = sum(nx.values())

    def midranks(marg: Counter) -> dict[int, float]:
        out, below = {}, 0
        for v in sorted(marg):
            cnt = marg[v]
            out[v] = below + (cnt + 1) / 2     # 区间 [below+1, below+cnt] 的中点
            below += cnt
        return out

    rx, ry = midranks(nx), midranks(ny)
    ex = sum(c * rx[x] for x, c in nx.items()) / n
    ey = sum(c * ry[y] for y, c in ny.items()) / n
    vx = sum(c * (rx[x] - ex) ** 2 for x, c in nx.items()) / n
    vy = sum(c * (ry[y] - ey) ** 2 for y, c in ny.items()) / n
    cxy = sum(c * (rx[x] - ex) * (ry[y] - ey) for (x, y), c in counts.items()) / n
    if vx == 0 or vy == 0:
        return float("nan")
    return cxy / (vx * vy) ** 0.5


class BenignIndex:
    """benign 基础设施包含判定:复用 _eval.benign 的 pymispwarninglists
    装载与 _provider/IP_WARNINGLISTS 口径,把命中的 provider 列表折叠为
    有序不相交区间数组,bisect 判包含(语义 = 库 slow_search 的 cidr 分支;
    启动时对样例与库逐一对拍)。"""

    def __init__(self, loader):
        from ipdb._eval.benign import _provider          # 复用 _eval 口径函数
        from ipdb._eval import config
        wl = loader()
        ivs: list[tuple[int, int, str]] = []
        for lst in wl.warninglists.values():
            prov = _provider(lst.name)
            if not prov:
                continue
            for entry in lst.list:
                try:
                    net = ipaddress.ip_network(str(entry), strict=False)
                except (ValueError, TypeError):
                    continue
                if net.version != 4:
                    continue
                ivs.append((int(net.network_address), int(net.broadcast_address), prov))
        ivs.sort()
        starts, ends, provs = [], [], []
        for s, e, p in ivs:                              # 折叠重叠/相邻区间,保留任一 provider 标签
            if starts and s <= ends[-1] + 1:
                if e > ends[-1]:
                    ends[-1] = e
                continue
            starts.append(s); ends.append(e); provs.append(p)
        self._starts, self._ends, self._provs = starts, ends, provs

    def provider(self, ip_int: int) -> str | None:
        i = bisect.bisect_right(self._starts, ip_int) - 1
        if i >= 0 and ip_int <= self._ends[i]:
            return self._provs[i]
        return None

    def cross_check(self, loader, ips: list[str]) -> int:
        """与库 slow_search(含 CIDR 的权威包含判定)对拍,返回二值失配数
        (折叠归并后具体 provider 名可不同,命中与否必须一致)。"""
        from ipdb._eval.benign import _provider
        slow = type(loader())(slow_search=True)          # 同列表慢模式 = 权威包含判定
        bad = 0
        for ip in ips:
            lib = next((_provider(h.name) for h in (slow.search(ip) or [])
                        if _provider(h.name)), None)
            mine = self.provider(int(ipaddress.IPv4Address(ip)))
            if (lib is None) != (mine is None):
                bad += 1
        return bad


def iter_source_starts(source):
    """单个指控源 LMDB v4 键起点流(CIDR 起点;跳过 payloads 描述符键)。
    复用 registry 已打开的 _reader(py-lmdb 同进程禁双开)。"""
    from ipdb._sources._lmdb import PAYLOADS_NAME
    env = source._reader
    with env.begin() as txn:                             # 长只读事务:全程无写者,安全
        cur = txn.cursor()
        ok = cur.first()
        while ok:
            key = cur.key()
            if key != PAYLOADS_NAME:
                yield int.from_bytes(key, "big")
            ok = cur.next()


def merged_union(starts_iterables):
    """k 路归并去重:全序唯一键起点流,内存 O(k)。"""
    prev = None
    for v in heapq.merge(*starts_iterables):
        if v != prev:
            prev = v
            yield v


def read_hwm_kb() -> int:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmHWM"):
                return int(line.split()[1])
    return -1


def fmt_ip(v: int) -> str:
    return str(ipaddress.IPv4Address(v))


def main() -> int:
    # 内存红线(R3-F3):4GiB 匿名堆硬顶在 main() 首行设置 —— CLI 跑语义
    # 不变,而 import 本模块零副作用(测试/工具可安全 import,不钳调用方
    # rlimit)。必须在下方重导入 ipdb 前生效;理由见模块 docstring
    # (RLIMIT_AS 与只读 mmap 数据面互斥,不可用)。
    resource.setrlimit(resource.RLIMIT_DATA, (4 * 1024**3, 4 * 1024**3))
    ap = argparse.ArgumentParser(description="融合回放门:C2/C3/C4 实证(流式,内存红线)")
    ap.add_argument("--data", default=str(REPO_ROOT / ".eval-prod-data"),
                    help="生产数据镜像目录(默认 <脚本仓>/.eval-prod-data;worktree 跑时指主仓)")
    ap.add_argument("--stride", type=int, default=1,
                    help="系统抽样步长:每 N 个探测 IP 取 1(默认全量)")
    ap.add_argument("--limit", type=int, default=0,
                    help="处理探测 IP 上限(0=不限;小切片自测用)")
    ap.add_argument("--report", default="",
                    help="Markdown 报告输出路径（缺省=stdout）")
    ap.add_argument("--dump-movers", default="",
                    metavar="PATH",
                    help="C3 补证 + 终审 Important-1:阈值穿越 IP 逐条流式落盘 JSONL"
                         "(ip/old/new/direction/k/provider;direction=up 为新晋 ≥70"
                         " old<70≤new;down 为跌出 ≥70 old≥70>new,即 fail2ban"
                         " 退封方向),不进内存")
    args = ap.parse_args()

    data_dir = Path(args.data).resolve()
    if not data_dir.is_dir():
        print(f"数据目录不存在: {data_dir}", file=sys.stderr)
        return 2
    # 只读语义:导入 ipdb 前设旗标(Source.load 的 cleanup_stale 早退,不 rmtree)
    os.environ["IP_RADAR_POOL_CHILD"] = "1"
    os.environ["IP_RADAR_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(BACKEND_DIR))

    t_start = time.time()
    import ipdb._registry as reg
    import ipdb._logodds as _lo
    import ipdb._types as _types
    from ipdb._eval.benign import _default_loader
    from ipdb._eval import config as _eval_config
    from ipdb._sources._lmdb import read_ptr
    providers = list(_eval_config.IP_WARNINGLISTS)

    log = lambda msg: print(msg, file=sys.stderr, flush=True)

    reg.load_db()

    # ── 指控源集合（与 lookup 同一使能口径）──
    accusing = [
        s for s in reg._enabled_sources()
        if getattr(s, "classification_type", None)
        and getattr(s, "verdict", "malicious") in _ACCUSING
        and s._reader is not None
    ]
    src_meta = []
    iters = []
    for s in accusing:
        src_meta.append({"name": s.name, "type": s.classification_type,
                         "verdict": s.verdict, "epoch": read_ptr(s._lmdb_base)})
        iters.append(iter_source_starts(s))

    # ── benign 基础设施索引(复用 _eval 装载与 provider 口径)──
    benign = BenignIndex(_default_loader)

    # 对拍自检:索引与库 slow_search 权威 CIDR 包含二值一致(口径不可漂移)
    xcheck_ips = ["52.95.120.130", "13.107.42.14", "1.1.1.1", "8.8.8.8",
                  "203.0.113.7"]                          # 已知 AWS/Azure/DNS/保留样例
    ab = next((s for s in accusing if s.name == "abuseipdb"), None)
    if ab is not None:
        for i, v in enumerate(iter_source_starts(ab)):
            if i >= 15:
                break
            xcheck_ips.append(fmt_ip(v))
    bad_benign = benign.cross_check(_default_loader, xcheck_ips)
    if bad_benign:
        log(f"benign 索引对拍失配 {bad_benign}/{len(xcheck_ips)} —— 中止")
        return 3
    log(f"benign 对拍: {len(xcheck_ips)} 样例与库 slow_search 二值一致")

    # ── 聚合器(内存只留这些)──
    n_probe = 0
    n_accused = 0                       # 指控池非空(<探测总数:保留地址/纯存档证据等空池起点不计;首轮实测空池 19,173 个,恰=k_hist[0])
    hist_old = [0] * 101
    hist_new = [0] * 101
    cont_old: dict[tuple[int, int], int] = {}     # 全探测到列联(语境)
    cont_new: dict[tuple[int, int], int] = {}
    cont_acc_old: dict[tuple[int, int], int] = {}  # 指控池非空(判据主口径)
    cont_acc_new: dict[tuple[int, int], int] = {}
    k_hist: Counter = Counter()
    moved_up = moved_down = moved_same = 0
    delta_sum = 0
    c2_strict_n = c2_strict_bad = 0     # 严格:恰好一个 detected 组且指控
    c2_loose_n = c2_loose_bad = 0       # 宽:恰一个指控组(可有 benign/存档组)
    c2_examples: list[dict] = []
    benign_n = 0
    benign_ge70_old = benign_ge70_new = 0
    benign_ge90_old = benign_ge90_new = 0
    benign_prov: Counter = Counter()
    benign_ge70_new_prov: Counter = Counter()
    xcheck_bad = 0                      # 本地重算融合分 vs threat_summary 失配
    n_err = 0
    n_movers70 = 0                       # C3 补证:上行穿越 old<70≤new 计数(与落盘独立)
    n_movers_down = 0                    # 终审 Important-1:下行穿越 old≥70>new 计数(fail2ban 退封方向)
    # 落盘句柄交给 with 托管(nullcontext 兼容未开 --dump-movers 的运行):
    # 中途异常退出也保证 close→flush,已缓冲的画像行不丢。
    movers_cm = (open(args.dump_movers, "w", encoding="utf-8")
                 if args.dump_movers else contextlib.nullcontext())

    log(f"数据: {data_dir}")
    log(f"指控源 {len(accusing)} 个;stride={args.stride} limit={args.limit or '∞'}")
    log(f"benign 区间索引: {len(benign._starts):,} 个折叠区间")

    t_probe = time.time()
    with movers_cm as movers_fh:
        for raw in merged_union(iters):
            n_probe += 1
            if args.stride > 1 and (n_probe - 1) % args.stride != 0:
                continue
            ip = fmt_ip(raw)
            try:
                result = reg.lookup(ip)
                new_conf = result.threat_summary()["confidence"]   # 生产融合实现（worktree 代码）
                old_conf = old_rule(result)
                pool = fusion_pool(result, _lo.coefficient, _types._ACCUSING)
            except Exception as e:                          # 单 IP 失败不终止整轮
                n_err += 1
                if n_err <= 5:
                    log(f"lookup 错误 {ip}: {e!r}")
                continue

            n_accused += 1 if pool else 0
            # 交叉核对:本地镜像池化重算 == 生产 threat_summary(防脚本镜像漂移)
            if pool:
                mine = _lo.assertion_confidence(
                    [c for _, c in _lo.dedup_lineage(list(pool.items()))])
                if mine != new_conf:
                    xcheck_bad += 1

            deduped = _lo.dedup_lineage(list(pool.items())) if pool else []
            k = len(deduped)

            # C2:恒等计数(严格/宽两口径)
            detected = [v for v in result.classifications.values() if v.detected]
            accusing_groups = [v for v in detected if v.verdict in _ACCUSING]
            if len(detected) == 1 and len(accusing_groups) == 1:
                c2_strict_n += 1
                if old_conf != new_conf:
                    c2_strict_bad += 1
                    if len(c2_examples) < 10:
                        c2_examples.append({"ip": ip, "old": old_conf, "new": new_conf,
                                            "strict": True})
            if len(accusing_groups) == 1:
                c2_loose_n += 1
                if old_conf != new_conf:
                    c2_loose_bad += 1
                    if len(c2_examples) < 10:
                        c2_examples.append({"ip": ip, "old": old_conf, "new": new_conf,
                                            "strict": False})

            # 直方图 / 列联表 / 变动统计
            hist_old[old_conf] += 1
            hist_new[new_conf] += 1
            cont_old[(old_conf, k)] = cont_old.get((old_conf, k), 0) + 1
            cont_new[(new_conf, k)] = cont_new.get((new_conf, k), 0) + 1
            if pool:                                          # 判据主口径：指控语料
                cont_acc_old[(old_conf, k)] = cont_acc_old.get((old_conf, k), 0) + 1
                cont_acc_new[(new_conf, k)] = cont_acc_new.get((new_conf, k), 0) + 1
            k_hist[k] += 1
            d = new_conf - old_conf
            delta_sum += d
            if d > 0:
                moved_up += 1
            elif d < 0:
                moved_down += 1
            else:
                moved_same += 1

            # C3:benign 基础设施（警告表 provider 口径）上的误报
            prov = benign.provider(raw)
            if prov is not None:
                benign_n += 1
                benign_prov[prov] += 1
                if old_conf >= C3_THRESHOLD:
                    benign_ge70_old += 1
                if new_conf >= C3_THRESHOLD:
                    benign_ge70_new += 1
                    benign_ge70_new_prov[prov] += 1
                if old_conf >= C3_THRESHOLD_HI:
                    benign_ge90_old += 1
                if new_conf >= C3_THRESHOLD_HI:
                    benign_ge90_new += 1

            # C3 补证 + 终审 Important-1:阈值穿越画像流式落盘(provider 可为 null)
            # direction="up"   = 新晋 ≥70(old<70≤new),沿用 C3 补证口径;
            # direction="down" = 跌出 ≥70(old≥70>new),即 fail2ban 退封方向——
            # 封禁决策取查询时点分数,分数回落不追溯已下发的封禁。
            if old_conf < C3_THRESHOLD <= new_conf:
                direction = "up"
            elif old_conf >= C3_THRESHOLD > new_conf:
                direction = "down"
            else:
                direction = None
            if direction == "up":
                n_movers70 += 1
            elif direction == "down":
                n_movers_down += 1
            if direction is not None and movers_fh is not None:
                movers_fh.write(json.dumps(
                    {"ip": ip, "old": old_conf, "new": new_conf,
                     "direction": direction, "k": k,
                     "provider": prov}, ensure_ascii=False) + "\n")

            if n_probe % 200_000 == 0:
                rate = n_probe / (time.time() - t_probe)
                log(f"  {n_probe:,} probes | {rate:,.0f}/s | "
                    f"elapsed {time.time()-t_probe:,.0f}s | VmHWM {read_hwm_kb()/1e6:.2f}GB")

            if args.limit and n_probe >= args.limit:
                break

    elapsed = time.time() - t_start
    hwm_kb = read_hwm_kb()

    # ── 判据 ──（C4 主口径 = 指控池非空语料；全探测到 ω 仅作语境）
    rho_old = spearman_from_contingency(cont_acc_old)
    rho_new = spearman_from_contingency(cont_acc_new)
    rho_all_old = spearman_from_contingency(cont_old)
    rho_all_new = spearman_from_contingency(cont_new)
    c2_pass = (c2_strict_bad == 0 and c2_loose_bad == 0)
    c3_rate_old = benign_ge70_old / benign_n if benign_n else None
    c3_rate_new = benign_ge70_new / benign_n if benign_n else None
    c3_pass = None if benign_n == 0 else (c3_rate_new <= c3_rate_old)
    c4_pass = None if (rho_old != rho_old or rho_new != rho_new) else (rho_new >= rho_old)

    def bucket(h: list[int]) -> list[int]:
        return [sum(h[b * 10:(b + 1) * 10]) for b in range(11)]  # 0-9,...,90-99,100

    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            cwd=REPO_ROOT, capture_output=True, text=True
                            ).stdout.strip() or "?"
    summary = {
        "data_dir": str(data_dir),
        "code_commit": commit,
        "stride": args.stride, "limit": args.limit or None,
        "n_probe_union_starts": n_probe,
        "n_accused": n_accused, "n_err": n_err, "xcheck_bad": xcheck_bad,
        "runtime_sec": round(elapsed, 1), "vm_hwm_gb": round(hwm_kb / 1e6, 3),
        "rlimit": "RLIMIT_DATA=4GiB(匿名堆;LMDB 只读 mmap 豁免)",
        "C2": {"strict_n": c2_strict_n, "strict_bad": c2_strict_bad,
               "loose_n": c2_loose_n, "loose_bad": c2_loose_bad,
               "pass": c2_pass, "examples": c2_examples},
        "C3": {"benign_n": benign_n, "ge70_old": benign_ge70_old,
               "ge70_new": benign_ge70_new,
               "rate_old": c3_rate_old, "rate_new": c3_rate_new,
               "ge90_old": benign_ge90_old, "ge90_new": benign_ge90_new,
               "pass": c3_pass},
        "C4": {"rho_old": None if rho_old != rho_old else round(rho_old, 6),
               "rho_new": None if rho_new != rho_new else round(rho_new, 6),
               "rho_all_old": None if rho_all_old != rho_all_old else round(rho_all_old, 6),
               "rho_all_new": None if rho_all_new != rho_all_new else round(rho_all_new, 6),
               "pass": c4_pass},
        "movement": {"up": moved_up, "same": moved_same, "down": moved_down,
                     "mean_delta": round(delta_sum / n_accused, 4) if n_accused else None},
        "movers70": {"n": n_movers70, "n_down": n_movers_down,
                     "dump": args.dump_movers or None},
        "k_hist_top": dict(sorted(k_hist.items(), key=lambda kv: -kv[1])[:8]),
    }

    # ── Markdown 报告 ──
    def pct(x):
        return "N/A" if x is None else f"{x*100:.3f}%"

    lines = []
    lines.append("# 融合回放门报告(C2/C3/C4 实证)")
    lines.append("")
    lines.append(f"- 生成: {time.strftime('%Y-%m-%d %H:%M:%S %z')} | 代码 commit `{commit}`")
    lines.append(f"- 数据镜像: `{data_dir}`(只读;IP_RADAR_POOL_CHILD=1,全程零写)")
    lines.append(f"- 命令: `{sys.executable} scripts/fusion_replay_gate.py --data {data_dir}"
                 + (f" --stride {args.stride}" if args.stride > 1 else "")
                 + (f" --limit {args.limit}" if args.limit else "") + "`")
    lines.append(f"- 耗时: {elapsed:,.0f}s | 内存峰值 VmHWM: {hwm_kb/1e6:.2f}GB | "
                 f"内存红线: RLIMIT_DATA=4GiB(RLIMIT_AS 与 6.94GB 只读 LMDB mmap 互斥,见脚本头注)")
    lines.append(f"- 语料: {len(accusing)} 指控源(malicious/suspicious)v4 键起点并集 "
                 f"k 路归并流式;stride={args.stride};v6 排除(指控源 v6 记录占比 <0.1%)")
    lines.append(f"- 探测 IP(去重后并集成员数): **{n_probe:,}**;lookup 异常 {n_err};"
                 f"指控池非空 {n_accused:,}")
    lines.append(f"- 脚本镜像池化 vs 生产 threat_summary 交叉核对失配: {xcheck_bad}"
                 f"(应≈0;>0 说明脚本镜像与实现漂移)")
    lines.append("")
    lines.append("## 判据")
    lines.append("")
    lines.append("### C2 单指控组新旧恒等 —— " + ("**PASS**" if c2_pass else "**FAIL**"))
    lines.append(f"- 严格口径(恰 1 detected 组且指控): {c2_strict_n:,} IP,失配 {c2_strict_bad}")
    lines.append(f"- 宽口径(恰 1 指控组,可有 benign/存档组): {c2_loose_n:,} IP,失配 {c2_loose_bad}")
    if c2_examples:
        lines.append(f"- 失配样例: {json.dumps(c2_examples, ensure_ascii=False)}")
    lines.append("")
    lines.append("### C3 benign 语料 ≥70 占比 新≤旧 —— "
                 + ("**PASS**" if c3_pass else "**FAIL**" if c3_pass is not None else "**N/A(空语料)**"))
    lines.append(f"- benign 语料 = 指控 IP ∩ MISP warning lists 云/CDN/DNS provider "
                 f"（口径同 `_eval.benign`/`_eval/config.IP_WARNINGLISTS`，{len(providers)} 个 provider；")
    lines.append("  区间包含经折叠区间数组+bisect，与库 slow_search 对拍同语义）")
    lines.append(f"- 语料量: {benign_n:,};≥70:旧 {benign_ge70_old:,}({pct(c3_rate_old)})"
                 f" vs 新 {benign_ge70_new:,}({pct(c3_rate_new)})")
    lines.append(f"- 次级观察 ≥{C3_THRESHOLD_HI}:旧 {benign_ge90_old:,} vs 新 {benign_ge90_new:,}")
    if benign_n:
        lines.append("- provider 分布: " + ", ".join(
            f"{p}={c:,}(新≥70: {benign_ge70_new_prov.get(p, 0):,})"
            for p, c in benign_prov.most_common()))
    lines.append("")
    lines.append("### C4 ρ(分数×独立源数) 新≥旧 —— "
                 + ("**PASS**" if c4_pass else "**FAIL**" if c4_pass is not None else "**N/A**"))
    lines.append(f"- Spearman ρ(列联表精确,并列中秩;k=dedup_lineage 后独立指控源数):")
    lines.append(f"  - 旧(选角): {summary['C4']['rho_old']}")
    lines.append(f"  - 新(融合): {summary['C4']['rho_new']}")
    lines.append(f"  - 语境(全探测到,含空指控池):旧 {summary['C4']['rho_all_old']} "
                 f"vs 新 {summary['C4']['rho_all_new']}")
    lines.append(f"- k 分布 top: {summary['k_hist_top']}")
    lines.append("")
    lines.append("## 分数直方图(10 分桶,指控并集)")
    lines.append("")
    lines.append("| 分数段 | 旧(选角) | 新(融合) |")
    lines.append("|---|---:|---:|")
    bo, bn = bucket(hist_old), bucket(hist_new)
    for b in range(11):
        lo, hi = b * 10, b * 10 + (9 if b < 10 else 0)
        lines.append(f"| {lo}–{hi} | {bo[b]:,} | {bn[b]:,} |")
    lines.append("")
    lines.append(f"变动:升 {moved_up:,} | 平 {moved_same:,} | 降 {moved_down:,}"
                 f"| 平均 Δ(new−old) = {summary['movement']['mean_delta']}")
    lines.append("")
    lines.append("## 机器可读摘要")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, ensure_ascii=False, indent=1))
    lines.append("```")
    report = "\n".join(lines) + "\n"

    # 源指纹(复算锚点:各源 epoch)
    lines2 = ["", "## 附录:源 epoch 指纹", ""]
    lines2.append("| 源 | 类型 | verdict | LMDB epoch |")
    lines2.append("|---|---|---|---|")
    for m in sorted(src_meta, key=lambda x: x["name"]):
        lines2.append(f"| {m['name']} | {m['type']} | {m['verdict']} | {m['epoch']} |")
    report += "\n".join(lines2) + "\n"

    if movers_fh is not None:
        log(f"movers 落盘: {args.dump_movers}"
            f"(上行新晋 ≥70 {n_movers70:,} 条;下行跌出 ≥70 {n_movers_down:,} 条)")

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report)
        log(f"报告已写: {args.report}")
    else:
        print(report)
    log(f"完成: {elapsed:,.0f}s | VmHWM {hwm_kb/1e6:.2f}GB | "
        f"C2={'PASS' if c2_pass else 'FAIL'} "
        f"C3={'PASS' if c3_pass else 'FAIL' if c3_pass is not None else 'N/A'} "
        f"C4={'PASS' if c4_pass else 'FAIL' if c4_pass is not None else 'N/A'}")
    return 0



if __name__ == "__main__":
    sys.exit(main())
