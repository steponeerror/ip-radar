"""CLI: wires the pure harness to the real ipdb._registry.

  python -m ipdb._eval <source>      # single-source verdict + report
  python -m ipdb._eval --rebuild     # rebuild the frozen benchmark corpus
  python -m ipdb._eval --all         # per-source verdict table (no ranking in v1)
  python -m ipdb._eval --model       # fleet corroboration-contrast model + acceptance suite
  python -m ipdb._eval --temporal    # λ_s prequential confirmation rate over model history (W1)
  python -m ipdb._eval --sentinel <source>  # 物化生效性哨兵(Q18 §3.2, materialize_source.sh 2/3)
  python -m ipdb._eval --gate <source>      # 接入关(spec §3.1: S7 镜像对齐→双口径报告)
  python -m ipdb._eval --canary      # 季度 canary 冻结判例复跑(S10)
"""
import argparse
import json
import os
import random
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path

from . import config
from .ablation import run_ablation
from .assets import fingerprint
from .benign import BenignChecker
from .corpus import Corpus, build_benchmark, sample_source_ips, stable_seed
from .independence import oc_suspicion_pairs
from .metrics import (compute_other_distribution, mc, cg, conflict, oc,
                      fp_proxy, other_pct, confidence_uplift, dead_slot_fill,
                      pairs)
from .origin import origin_map
from .pairwise import pairwise_oc, source_pair_sets
from .report import write_report
from .suite import run_suite, write_model_report
from .verdict import assess

_PKG_DIR = Path(__file__).resolve().parent              # backend/ipdb/_eval
_REPO_ROOT = _PKG_DIR.parents[2]                        # _eval -> ipdb -> backend -> repo root
# 报告目录(spec 2026-08-28 §5.2):运行时状态区,env 可覆盖;write_report 自带 mkdir
# S37 环境隔离(spec 待办9):REPORT_DIR = base/<env>,env ∈ monthly|gate|dev
# (默认 dev)——rc_history 读的 model/ 历史随目录命名空间天然不跨环境混读;
# 非法 env fail loud:静默回落 dev 会让 dev/gate 读到 monthly 的模型历史。
def eval_env() -> str:
    env = os.environ.get("IP_RADAR_EVAL_ENV", "dev")
    if env not in ("monthly", "gate", "dev"):
        raise ValueError(
            f"IP_RADAR_EVAL_ENV must be one of monthly|gate|dev, got {env!r}")
    return env


def report_dir() -> Path:
    """call-time 解析(测试免 reload;月轮脚本经 monthly_eval.sh 注入 env)。"""
    return Path(os.environ.get(
        "IP_RADAR_EVAL_DIR",
        str(_REPO_ROOT / "backend" / "data" / "eval"))) / eval_env()


# T9 gate 镜像参数(S7/Q11, spec 2026-10-12-eval-loop-hardening-design.md §3.1):
# prod host 缺省 = monthly_eval.sh PROD_HOST 同值(生产卷唯一既存部署事实, 不
# 复制进 config.py 造第二真源);mirror dir 缺省 = spec §3.1 本地常驻
# .eval-gate-mirror/(.gitignore 已忽略)。env 覆盖照 _registry.DATA_DIR
# (IP_RADAR_DATA_DIR)先例 —— call-time 解析(report_dir 同款, 测试免 reload)。
_GATE_PROD_HOST_ENV = "IP_RADAR_GATE_PROD_HOST"
_GATE_MIRROR_DIR_ENV = "IP_RADAR_GATE_MIRROR_DIR"
_PROD_HOST_DEFAULT = "root@203.88.124.85"          # monthly_eval.sh 同值
_GATE_MIRROR_DEFAULT = _REPO_ROOT / ".eval-gate-mirror"   # spec §3.1, 已 gitignore


def gate_prod_host() -> str:
    return os.environ.get(_GATE_PROD_HOST_ENV, _PROD_HOST_DEFAULT)


def gate_mirror_dir() -> Path:
    return Path(os.environ.get(_GATE_MIRROR_DIR_ENV,
                               str(_GATE_MIRROR_DEFAULT)))


@contextmanager
def _gate_env():
    """--gate/--canary CLI 的 env 钉(S37;run_gate/run_canary 内嵌 pin 的
    CLI 前置同款, T4/T7 pin 先例):CLI 先钉 gate 使 call-time report_dir()
    解析进 base/gate —— 否则未设 env 时报告落 dev 目录却带 gate 标签(S37
    跨 env 混读)。显式 monthly/dev → fail-loud 拒跑(内嵌 pin 同语义);
    退出还原。"""
    prev = os.environ.get("IP_RADAR_EVAL_ENV")
    if prev not in (None, "gate"):
        raise ValueError(f"IP_RADAR_EVAL_ENV={prev!r}: gate 族命令必须跑在 "
                         "env 'gate' (S37 fail-loud)")
    if prev is None:
        os.environ["IP_RADAR_EVAL_ENV"] = "gate"
    try:
        yield
    finally:
        if prev is None:
            del os.environ["IP_RADAR_EVAL_ENV"]


# 导入期快照:CLI 每次进程启动即等价 report_dir();保留模块属性作为
# main() 的读取点与既有测试 monkeypatch 缝(tests/eval/test_eval_temporal)。
REPORT_DIR = report_dir()
CORPUS_PATH = _PKG_DIR / "corpus.json"                  # curated in-package asset (spec §5)
NEUTRAL_ASSET = _PKG_DIR / "neutral_ips.json"           # W0 中性层静态资产(T1)


def _load_corpus() -> Corpus:
    """--model/--dsem 入口统一装填:frozen benchmark + 静态中性层
    (W0 层2,资产逐轮恒定,运行期只加载不重采样)。中性层进
    all_ips → 进快照。"""
    corpus = Corpus.load(CORPUS_PATH) if CORPUS_PATH.exists() else Corpus()
    corpus.neutral = json.loads(NEUTRAL_ASSET.read_text())
    return corpus

_JSON_HINT = "确认 DB 已 load / corpus 存在(--rebuild)"


def _rc_history(source_name: str, model_dir: Path) -> list[int]:
    """W4:REPORT_DIR/model 历史报告里该源 rc 序列(升序,同日期多份取
    字典序最后,惯例同 _eval_reader)。旧报告无 source_health 键 → 无条目
    —— 首轮(本任务之后才有的证据)自然为空,assess 只判 empty。"""
    if not model_dir.exists():
        return []
    by_date: dict[str, tuple[str, dict]] = {}
    for f in sorted(model_dir.glob("model-*.json")):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        sh = r.get("source_health") if isinstance(r, dict) else None
        if not isinstance(sh, dict):
            continue
        date = str(r.get("generated_at") or "")
        if date not in by_date or f.stem > by_date[date][0]:
            by_date[date] = (f.stem, sh)
    out = []
    for date in sorted(by_date):
        entry = by_date[date][1].get(source_name)
        if isinstance(entry, dict) and isinstance(entry.get("rc"), int):
            out.append(entry["rc"])
    return out


def _json_error(code: str, message: str, hint: str, rc: int = 1) -> None:
    """--json 模式统一错误出口:stdout 合法 JSON + 非零退出(spec §5.2);
    rc 可覆写(T9 gate 镜像失配族 rc=3, 与通用 rc=1 区分)。"""
    print(json.dumps({"error": {"code": code, "message": message, "hint": hint}},
                     ensure_ascii=False))
    sys.exit(rc)


def _gate_cli_fail(rc: int, code: str, message: str, hint: str,
                   as_json: bool) -> None:
    """gate 族子命令失败出口:--json → stdout JSON 信封(§5.2);否则 stderr
    清洁行 + 退出码(退出码契约见各 handler 注释, 不裸栈)。"""
    if as_json:
        _json_error(code, message, hint, rc=rc)
    print(f"拒绝: {message}\n  ({hint})", file=sys.stderr)
    sys.exit(rc)


def _real_registry():
    """Bind the real ipdb._registry to the harness's injected interfaces."""
    import ipdb._registry as reg

    def lookup(ip, asof=None):
        # asof(T10 时钟锚)仅月轮读数用; 其它调用方单参不变
        return reg.lookup(ip, asof=asof).to_dict()

    def toggle(name, enabled):
        # in-memory only — NEVER reg.set_source_enabled (which persists).
        # 必须重赋值而非 .add/.discard 原地改(与 set_source_enabled 同款):
        # registry 身份键控缓存(_enabled_cache/_org_hooks_cache,Task 4)按
        # _disabled 对象身份失效,原地改会让消融 baseline/candidate 恒同、
        # 指标静默全零(终审 Critical-1,2026-10-11)。
        if enabled:
            reg._disabled = reg._disabled - {name}
        else:
            reg._disabled = reg._disabled | {name}

    from types import SimpleNamespace
    return SimpleNamespace(
        sources=reg._sources,
        load_db=reg.load_db,
        lookup=lookup,
        toggle=toggle,
    )


def run_for_source(source_name: str, registry=None, corpus_path=CORPUS_PATH,
                   out_dir=None, benign=None, run_seed: int | None = None):
    registry = registry or _real_registry()
    benign = benign or BenignChecker()
    # S37:out_dir 缺省按当前 env 解析(月轮 monthly / 本地 dev 各归各目录)
    out_dir = report_dir() if out_dir is None else out_dir
    rng = random.Random(stable_seed(source_name))

    corpus = Corpus.load(corpus_path) if corpus_path.exists() else Corpus()
    # S36:run 级 seed 缺省显式随机(randbits 64)——不回退源名/文件内容
    # 派生的可预测纯函数(那正是本任务要堵的洞),先于 candidate 采样注入
    run_seed = run_seed if run_seed is not None else secrets.randbits(64)
    # dynamic candidate stratum: fresh sample each run.
    src_obj = next((s for s in registry.sources if s.name == source_name), None)
    if src_obj is not None:
        corpus.candidate_ips = sample_source_ips(src_obj, config.CORPUS_CANDIDATE_N,
                                                 rng, run_seed=run_seed)

    baseline, candidate_snap = run_ablation(registry.lookup, registry.toggle,
                                            source_name, corpus)

    total_pairs = len(pairs(candidate_snap)) or 1
    _mc = mc(baseline, candidate_snap, source_name, total_pairs)
    metrics = {
        "MC": _mc,
        "CG": cg(baseline, candidate_snap, source_name),
        "conflict": conflict(baseline, candidate_snap),
        "oc": oc(baseline, candidate_snap, source_name),
        "dead_slot_fill": dead_slot_fill(baseline, candidate_snap),
        "confidence_uplift": confidence_uplift(baseline, candidate_snap),
        "fp": fp_proxy([ip for ip, _ in _mc.detail], benign),
        "other": other_pct(compute_other_distribution(src_obj, rng)),
    }
    # n-floor (spec §7): candidate-asserted (ip,type) pairs. Counts ONLY the
    # candidate's contribution so the floor actually protects niche sources
    # (counting any-source classifications would always exceed the floor).
    candidate_touched = len(pairs(candidate_snap, source_name))
    # OC suspicion across all source pairs (advisory), fed by the D4 pairwise
    # OC table over the baseline snapshot (= full fleet minus the candidate).
    # Same-declared-cluster pairs (firehol x ipsum) are pre-filtered inside.
    flags = oc_suspicion_pairs(pairwise_oc(source_pair_sets(baseline)))
    from ipdb._registry import SOURCE_CATEGORIES
    category = SOURCE_CATEGORIES.get(source_name, "other")
    # W4:rc(record_count)与历史中位 → NO-DATA 前置判定(死源先告警,
    # 在 asset 早退/n-floor 之前;该路径不接 neutral/origin,T2 裁决既定)
    h = src_obj.health() if src_obj is not None else None
    verdict = assess(metrics, candidate_touched, flags, source_category=category,
                     rc=h.record_count if h is not None else None,
                     rc_history=_rc_history(source_name, Path(out_dir) / "model"))
    md, js = write_report(source_name, verdict, metrics, corpus, out_dir,
                          run_seed=run_seed, eval_env=eval_env(),
                          sampling_fingerprint=fingerprint(corpus.candidate_ips))
    return md, js, verdict


def _load_prev_action_block(out_dir: Path) -> tuple[list, dict]:
    """上轮 action-block.json → (ActionItem 列表, header dict); 缺文件 →
    ([], {}); 坏 JSON 直接炸 —— 静默清零会丢整月携带项, 必须响。"""
    from .monthly import ActionItem
    p = Path(out_dir) / "action-block.json"
    if not p.is_file():
        return [], {}
    data = json.loads(p.read_text())
    items = [ActionItem(**d) for d in data.get("items", [])]
    return items, data.get("header") or {}


def _cloud_v4_ranges(src) -> list[str]:
    """cloud_ranges 源中间文件 → v4 CIDR 清单(§2.1 非指控基础设施层输入)。

    键集正则(_source_ips)剥 CIDR mask 且只吃单文件, 而 cloud_ranges 的
    _path 是目录 → 走源模块 _FEEDS 的 parse 函数直读中间文件(与引擎
    harvest 同码, 单一真实路径); v6 段接线侧即滤(":" 判族), 构建器侧
    另有 version!=4 跳过保险(skipped_v6_blocks 记账)。缺源/缺文件 →
    空(宁少算: 无云段采样, 不炸报告)。"""
    from ipdb._sources import cloud_ranges as _cr
    if src is None:
        return []
    out: list[str] = []
    for _provider, _fetch, parse, filename, _rel, _stale in _cr._FEEDS:
        p = Path(getattr(src, "_path", "")) / filename
        if p.is_file():
            out += [c for c in parse(p.read_bytes()) if ":" not in c]
    return out


def _resolver_ips(srcs: dict) -> list[str]:
    """解析器侧键集 = root_servers ∪ dns_public(§2.1 的 320 侧输入)。

    root_servers.cache 明文 A/AAAA 行 → 键集正则(v4 过滤内置); dns_public.md
    是 sdns:// base64 stamp, 明文 IP 不在文件内(正则恒空)→ 走源模块
    _decode_stamp_ip(harvest 同码纯函数), v6 stamp 弃(宁少算)。"""
    from ipdb._sources.dns_public import _decode_stamp_ip
    from .keysets import _source_ips
    ips: list[str] = []
    rs = srcs.get("root_servers")
    if rs is not None:
        ips += _source_ips(rs)
    dp = srcs.get("dns_public")
    if dp is not None and Path(getattr(dp, "_path", "")).is_file():
        for ln in Path(dp._path).read_text(errors="ignore").splitlines():
            if not ln.startswith("sdns://"):
                continue
            ip = _decode_stamp_ip(ln[len("sdns://"):].strip())
            if ip and ":" not in ip:
                ips.append(ip)
    return sorted(set(ips))


def _vpn_prefixes(src) -> list[str]:
    """x4bnet_vpn 原样 v4 CIDR/裸 IP 行(保留 mask): 键集正则剥 mask 会把
    VPN 段缩成网络地址单点、过滤失真; 逐行原读(IpListSource.parse_raw
    同款跳注释/空行, ":" 弃 v6)。缺源/缺文件 → 空表 = 无段可剔。"""
    if src is None:
        return []
    p = Path(getattr(src, "_path", ""))
    if not p.is_file():
        return []
    return [ln.strip() for ln in p.read_text(errors="ignore").splitlines()
            if ln.strip() and not ln.strip().startswith("#") and ":" not in ln]


def _oc_latest(out_dir: Path) -> dict[str, float]:
    """S28 冗余度% 数据源: <out_dir>/<source>-<ts>.json(--all 先于
    --readout 落同目录, report.py 秒级 ts 命名)按文件名 ts 取每源最新
    → {源名: metrics.oc.value}。非该形状文件(action-block/mirror-
    manifest/temporal-*)逐个跳过(无该路径即无话); 坏 JSON 跳过不炸
    (_rc_history 同款宽容)。"""
    out: dict[str, tuple[str, float]] = {}
    for p in sorted(Path(out_dir).glob("*-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        m = d.get("metrics")
        oc = m.get("oc") if isinstance(m, dict) else None
        v = oc.get("value") if isinstance(oc, dict) else None
        name = d.get("source")
        if not isinstance(name, str) or not isinstance(v, (int, float)):
            continue
        if name not in out or p.name > out[name][0]:
            out[name] = (p.name, float(v))
    return {k: v for k, (_, v) in out.items()}


def run_readout(registry, out_dir, *, assets_dir=None, keysets_dir=None,
                run_seed=None, run_id=None):
    """§4.2/S26 月轮读数接线: 组合既有纯件, 不实现新读数。

    链: 生产输入(镜像内源文件) → 三件套资产(S36 run_seed) → 键集快照+
    长记忆(T5) → 四层装配(缺 truth = NO-LAYER 哨兵, 报告照发) → 逐层
    读数(F10 快照, asof 锚 = 真值层 created_at, 缺真值层 → None 走普通
    查询, 不虚构锚) → ε 敏感性(真值层 OK 才算, 否则 None → 哨兵行) →
    行动区块 + 月报 + action-block.json(header 快照供下轮 prev 对比)。
    assets/keysets 跨 env 共享(语料/键集是事实不是报告, spec §4.2)。"""
    from dataclasses import asdict
    from datetime import date, datetime, timezone
    from .assets import load_asset
    from .disclosures import render_disclosures
    from .keysets import _source_ips, export_source_keysets, long_memory_ips
    from .layer_builders import PER_SOURCE_N, build_all_monthly, non_vpn_resolvers
    from .layered import assemble_four_layers, epsilon_sensitivity, layered_readout
    from .monthly import (compose_action_block, compose_monthly_md,
                          load_dispositions, render_anchor_oc,
                          render_consensus_diag, render_scorecard,
                          render_steal_parking_diag)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_seed = secrets.randbits(64) if run_seed is None else run_seed
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    srcs = {s.name: s for s in registry.sources}
    threat_srcs = [s for s in registry.sources
                   if getattr(s, "category", None) == "threat"]
    assets_root = (Path(assets_dir) if assets_dir else
                   _REPO_ROOT / "backend" / "data" / "eval" / "assets")
    source_keysets = {s.name: _source_ips(s) for s in threat_srcs}
    metas = build_all_monthly(
        assets_root, version=run_id, run_seed=run_seed,
        cloud_ranges=_cloud_v4_ranges(srcs.get("cloud_ranges")),
        resolver_ips=non_vpn_resolvers(
            _resolver_ips(srcs), _vpn_prefixes(srcs.get("x4bnet_vpn"))),
        source_keysets=source_keysets)
    # truth 资产 = ops 侧经 truth_layer 三闸产出(§2.1), 在场才入指纹表
    truth_dir = assets_root / "truth"
    if truth_dir.is_dir():
        metas["truth"] = load_asset(truth_dir)[1]

    keysets_root = (Path(keysets_dir) if keysets_dir else
                    _REPO_ROOT / "backend" / "data" / "eval" / "keysets")
    export_source_keysets(
        registry.sources, keysets_root, run_id,
        corpus_fingerprint=fingerprint(
            [f"{k}:{m.fingerprint}" for k, m in sorted(metas.items())]))
    long_memory = long_memory_ips(keysets_root)

    layers = assemble_four_layers(assets_root)
    truth = layers["truth"]
    asof = None
    if truth.status == "OK":
        created = datetime.fromisoformat(metas["truth"].created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        asof = created.timestamp()
    readout = layered_readout(registry.lookup, layers, out_dir=out_dir,
                              run_id=run_id, asof=asof,
                              sources=registry.sources,
                              long_memory=long_memory)
    eps = (epsilon_sensitivity(truth.hit_members, n=len(truth.members),
                               seed=run_seed)
           if truth.status == "OK" else None)

    # Q22 诊断层统计: desync(预期指控源不再指控)需逐成员重查引擎, 不便宜
    # → 不算, 渲染侧 N/A(无证据即无话)。
    actual = len(layers["consensus"].members)
    stats = {
        # P1-1: 分母 = sum(min(PER_SOURCE_N, |键集|)) —— 目录形源(键集提取
        # 结构性贡献 0, 如 firehol/blocklist_de)不入分母, 池竭规则只对
        # 回声收窄(键集实缩)发话, 不再月月假警
        "expected_pool": sum(min(PER_SOURCE_N, len(v))
                             for v in source_keysets.values()),
        "actual": actual,
        "pool": actual,
        "contributing_sources": sum(1 for v in source_keysets.values() if v),
        # 目录形源(_path 为目录, 键集提取结构性不可行, 如 blocklist_de):
        # 键集贡献为零是形状使然, 计数披露不虚拟补
        "catalog_excluded": sum(1 for s in threat_srcs
                                if Path(getattr(s, "_path", "")).is_dir()),
        "desync": None,
    }
    readout["assembly_stats"] = stats

    prev_items, prev_header = _load_prev_action_block(out_dir)
    dispositions = load_dispositions(out_dir)
    today = date.today()
    items = compose_action_block(readout, prev_items, dispositions, today)

    model_dir = out_dir / "model"
    history = []
    if model_dir.is_dir():
        for f in sorted(model_dir.glob("model-*.json")):
            try:  # _rc_history 同款: 坏历史报告跳过不炸
                history.append(json.loads(f.read_text()))
            except ValueError:
                continue
    corpus = {k: {"version": m.version, "fingerprint": m.fingerprint}
              for k, m in metas.items()}
    prev_fp = {k: (v.get("fingerprint") if isinstance(v, dict) else v)
               for k, v in (prev_header.get("corpus") or {}).items()}
    md = compose_monthly_md(
        readout,
        render_disclosures(readout, metas, extra=[
            f"run_seed={run_seed}(S36: 采样 seed 逐字节可复现, 逐资产真值在"
            " meta.params.run_seed —— infra 输入指纹未变时沿用前轮 seed,"
            " 冻结采样防指纹噪声)"]),
        items, render_scorecard(history, registry.sources,
                                oc_latest=_oc_latest(out_dir)),
        render_consensus_diag(stats) + render_anchor_oc(keysets_root),
        {"eval_env": eval_env(), "corpus": corpus,
         "prev_fingerprints": prev_fp,
         "annual": dispositions.get("last_annual_review"),
         "today": today, "epsilon": eps},
        steal_parking_lines=render_steal_parking_diag(keysets_root))
    md_path = out_dir / f"monthly-{run_id}.md"
    md_path.write_text(md, encoding="utf-8")
    (out_dir / "action-block.json").write_text(json.dumps(
        {"header": {"run_id": run_id, "run_seed": run_seed,
                   "eval_env": eval_env(), "today": today.isoformat(),
                   "epsilon": eps, "corpus": corpus},
         "items": [asdict(i) for i in items]},
        indent=1, ensure_ascii=False), encoding="utf-8")
    return md_path, items, readout


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m ipdb._eval")
    p.add_argument("source", nargs="?", help="source name to evaluate")
    p.add_argument("--rebuild", action="store_true", help="rebuild frozen benchmark corpus")
    p.add_argument("--all", action="store_true", help="evaluate every source (no ranking in v1)")
    p.add_argument("--model", action="store_true",
                   help="fleet corroboration-contrast model + acceptance suite")
    p.add_argument("--audit", action="store_true",
                   help="lineage audit over persisted model history (advisory, B1)")
    p.add_argument("--anchors", action="store_true",
                   help="known-answer anchor set regression gate (spec §5.2)")
    p.add_argument("--dsem", action="store_true",
                   help="DS-EM fair fight: market vs declared vs pi-hat T3 (advisory)")
    p.add_argument("--temporal", action="store_true",
                   help="λ_s prequential confirmation rate over model history (W1)")
    p.add_argument("--demand", action="store_true",
                   help="答案率探针:双队列(舰队语料+随机可路由)per-field "
                        "answer-rate(罗盘批 2026-10-10,discover Step 1 四输入之一)")
    p.add_argument("--readout", action="store_true",
                   help="月轮四层读数管线(§4.2/S26): 三件套资产构建+四层"
                        "读数+行动区块+月报 monthly-*.md")
    p.add_argument("--assets-dir", default=None,
                   help="语料资产根目录(默认 <repo>/backend/data/eval/assets, "
                        "跨 env 共享; truth 层由 ops 侧经三闸产出)")
    p.add_argument("--gate", metavar="SOURCE",
                   help="接入关(spec §3.1): S7 镜像对齐后跑双口径报告, "
                        "EVAL_ENV=gate 强制; 报告必附 PR")
    p.add_argument("--canary", action="store_true",
                   help="季度 canary(S10): 冻结判例复跑, all_match=False → "
                        "rc=1(腐化告警可见)但报告照写")
    p.add_argument("--sentinel", metavar="SOURCE",
                   help="生效性哨兵(Q18 §3.2): pass=True→rc 0, False→rc 1, "
                        "N/A(geo_asn)→rc 0+说明行; materialize_source.sh 消费")
    p.add_argument("--run-seed", type=int, default=None,
                   help="run 级 seed(T2 纪律: 显式传则可复现; 缺省 = "
                        "各入口稳定缺省 —— sentinel 名派生 / gate 随机但落报告)")
    p.add_argument("--json", action="store_true", help="机器可读 JSON 到 stdout")
    args = p.parse_args(argv)

    # --temporal 只读已落盘 model 历史,不碰 registry/DB —— 前置于 load_db
    if args.temporal:
        from .temporal import temporal_report
        rep = temporal_report(REPORT_DIR / "model", out_dir=REPORT_DIR)
        if rep["n_rounds"] < 2:
            if args.json:
                print(json.dumps({"error": {"code": "insufficient_rounds",
                      "message": "insufficient rounds (need >= 2)",
                      "hint": "每月 --model 落盘后轮次自然累积"}}, ensure_ascii=False))
            else:
                print("insufficient rounds")
            sys.exit(2)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=1))
            return
        print(f"temporal λ_s: {rep['n_rounds']} rounds, "
              f"{len(rep['windows'])} windows")
        for w in rep["windows"]:
            skip = f"  skipped: {', '.join(w['skipped'])}" if w["skipped"] else ""
            print(f"  window {w['from']} -> {w['to']}{skip}")
            rows = sorted(w["per_source"].items(),
                          key=lambda kv: (-(kv[1]["lam"] if kv[1]["lam"] is not None
                                            else -1.0), kv[0]))
            for s, st in rows:
                lam = f"{st['lam']:.3f}" if st["lam"] is not None else "—"
                ci = (f"[{st['ci_lo']:.3f}, {st['ci_hi']:.3f}]"
                      if st["ci_lo"] is not None else "—")
                print(f"    {s:<20} n={st['n_uniq']:<5} k={st['n_conf']:<4} "
                      f"λ={lam} {ci}")
        pre = rep["preregistration"]
        fmt = lambda v: f"{v:.3f}" if v is not None else "—"
        print(f"  preregistration: above λ={fmt(pre['above']['lam'])} "
              f"vs below λ={fmt(pre['below']['lam'])}, "
              f"Fisher p={pre['fisher_p']:.4f}, direction={pre['direction']}")
        print(f"  report: {rep.get('report_path')}")
        return

    registry = _real_registry()
    if args.json:
        # --json 下前置失败也必须走 stdout JSON 信封,不许 stderr 裸栈(spec §5.2)
        try:
            registry.load_db()
        except Exception as e:
            _json_error("internal", f"load_db failed: {e}", _JSON_HINT)
    else:
        registry.load_db()

    if args.demand:
        from .demand import run as demand_run
        print(demand_run(registry.lookup, registry.sources,
                         as_json=args.json))
        return
    if args.rebuild:
        bench = build_benchmark(registry.sources, config.CORPUS_PER_TYPE_N)
        bench.save(CORPUS_PATH)
        print(f"rebuilt corpus -> {CORPUS_PATH}")
        return
    if args.model:
        from ipdb._merge import SOURCE_RELIABILITY
        corpus = _load_corpus()
        # W0 层1:自采样偏差治理 —— 语料成员在源 raw 文件内的佐证剔除
        origin = origin_map(registry.sources, corpus.all_ips())
        result = run_suite(registry.lookup, corpus,
                           declared_r=dict(SOURCE_RELIABILITY), origin=origin,
                           sources=registry.sources)
        md, js = write_model_report(result, REPORT_DIR)
        if args.json:
            print(Path(js).read_text())
        else:
            print(f"model suite: "
                  f"{sum(1 for c in result['checks'].values() if c['pass'])}"
                  f"/{len(result['checks'])} checks pass\n  report: {md}")
        return
    if args.audit:
        # T8（T14 缓议清偿）：audit 升格报告族写者 —— audit_report 落
        # model/audit-<ts>.json；stdout/退出码位等价（advisory 不拦）
        from .audit import audit_report
        res = audit_report(REPORT_DIR / "model", out_dir=REPORT_DIR)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            print("lineage audit (advisory):")
            print(f"  rounds: {res['n_rounds']}")
            for s in res["recommended_derived"]:
                print(f"  {s}: " + "; ".join(
                    f"<= {u} (flow {fab}:{fba}, contain {c:.2f})"
                    for u, fab, fba, c in res["relations"][s]))
            print(f"  C-3: {'PASS' if res['c3']['pass'] else 'CHECK'} "
                  f"(false accusations: {res['c3']['false_accusations']}, "
                  f"known-missing: {res['c3']['missing_known']}, "
                  f"recall: {res['c3']['recall']:.2f})")
        return
    if args.anchors:
        # T8（T14 缓议清偿）：anchors 升格报告族写者 —— anchors_report 落
        # model/anchors-<ts>.json（失败也落盘，证据不灭）；stdout/退出码位等价
        from .anchors import ANCHORS, anchors_report
        fails = anchors_report(registry.lookup, out_dir=REPORT_DIR)
        if args.json:
            print(json.dumps({"failures": fails}, ensure_ascii=False))
        else:
            for f in fails:
                print(f"ANCHOR FAIL {f['ip']} ({f['expect']}): {f['reason']}")
            total = len(ANCHORS)
            print(f"anchors: {total - len(fails)}/{total} pass")
        sys.exit(1 if fails else 0)
    if args.dsem:
        from ipdb._merge import SOURCE_RELIABILITY
        from .dsem_cli import run_dsem_report
        corpus = _load_corpus()
        origin = origin_map(registry.sources, corpus.all_ips())
        res = run_dsem_report(registry.lookup, corpus,
                              declared_r=dict(SOURCE_RELIABILITY),
                              out_dir=REPORT_DIR, origin=origin)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            ff = res["fair_fight"]
            print("DS-EM fair fight (advisory; pi-hat = truth-rate, "
                  "theta = corroboration — never accuracy):")
            print(f"market:   {ff['market_t3']}")
            print(f"declared: {ff['declared_t3']}")
            print(f"pi-hat:   {ff['pihat_t3']}  "
                  f"(beats declared: {ff['pihat_beats_declared']})")
        return
    if args.readout:
        md_path, items, res = run_readout(registry, REPORT_DIR,
                                          assets_dir=args.assets_dir)
        print(f"readout: {len(items)} action items, "
              f"degraded={'yes' if res['degraded'] else 'no'}")
        print(f"  report: {md_path}")
        return
    # ── T9 gate 族子命令(spec §3.1/§3.2; 镜像前置 S7)────────────
    if args.gate is not None:
        # 接入关 CLI: ensure_gate_mirror(S7: 跑前镜像对齐, 失配拒跑
        # fail-closed)→ run_gate(双口径+triggers 节已在报告内, T4/T6)→
        # 报告路径回显。退出码契约: 镜像失配/同步失败 → rc=3(与通用 rc=1
        # 区分 —— 运维一眼认「对齐未过, gate 根本没跑」);env 错位/未知源
        # → rc=1;其余内部异常不吞(裸栈可查, 证据链完整)。
        from .gate import run_gate
        from .gate_mirror import GateMirrorMisalignedError, ensure_gate_mirror
        try:
            with _gate_env():
                try:
                    # 镜像参数从 env/常量读(见 gate_prod_host/gate_mirror_dir
                    # 出处注释; 不发明新配置面)
                    ensure_gate_mirror(gate_prod_host(), gate_mirror_dir())
                except (GateMirrorMisalignedError, RuntimeError) as e:
                    _gate_cli_fail(3, "gate_mirror_misaligned",
                                   f"S7 fail-closed: gate 拒跑 —— {e}",
                                   "重跑本命令重试 rsync, 或人工比对生产/镜像 .ptr",
                                   args.json)
                res = run_gate(args.gate, registry, report_dir(),
                               run_seed=args.run_seed,
                               assets_dir=args.assets_dir)
        except ValueError as e:
            _gate_cli_fail(1, "bad_request", str(e),
                           "gate 族命令须 IP_RADAR_EVAL_ENV=gate 或未设(S37); "
                           "源名查 GET /api/sources", args.json)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        else:
            n_rev = len(res["triggers"]["mandatory_review"])
            print(f"gate: {args.gate} "
                  f"verdict={res['candidate_stratum']['verdict']['state']} "
                  f"(强制人裁旗标 {n_rev} 条, 详见报告)")
            print(f"  report: {res['report']['md']}")
        return
    if args.canary:
        # 季度 canary CLI(S10): run_canary → 报告;all_match=False →
        # rc=1(腐化告警须可见)但报告照写(run_canary 恒落盘, 证据不灭)。
        from .canary import run_canary
        try:
            with _gate_env():
                res = run_canary(registry, report_dir())
        except ValueError as e:
            _gate_cli_fail(1, "bad_request", str(e),
                           "canary 须 IP_RADAR_EVAL_ENV=gate 或未设(S37)",
                           args.json)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            ok = sum(1 for c in res["cases"] if c["matched"])
            print(f"canary: all_match={res['all_match']} "
                  f"({ok}/{len(res['cases'])} 判例复现)")
            for a in res["alarms"]:
                print(f"  {a}")
            print(f"  report: {res['report']['md']}")
        sys.exit(0 if res["all_match"] else 1)
    if args.sentinel is not None:
        # 生效性哨兵 CLI(Q18 §3.2; materialize_source.sh 2/3 透传本 rc):
        #   pass=True → rc 0;pass=False → rc 1(探针失配或 fail-closed 通道
        #   NO-MEMBERS/UNKNOWN-CATEGORY/NO-ASSET-AXIS);pass=None(N/A,
        #   geo_asn 标量轴=非目标 spec §9/S13)→ rc 0 + N/A 说明行 ——
        #   N/A≠失败, 物化流程继续进 gate 提示分支;键集口径 coverage_check
        #   由本 CLI 分派(T2 消费面约定), 信息行不改 rc。
        # run_seed 纪律照 T2: --run-seed 显式传则可复现, 缺省 =
        # stable_seed(名派生, 进程无关稳定)。哨兵不落报告 → 不钉 env。
        from .keysets import _source_ips
        from .sentinel import coverage_check, sentinel_probe
        src = next((s for s in registry.sources
                    if s.name == args.sentinel), None)
        if src is None:
            if args.json:
                _json_error("source_not_found",
                            f"no source named {args.sentinel!r}",
                            "GET /api/sources 或查 backend/ipdb/_sources/ 确认源名")
            p.error(f"no source named {args.sentinel!r}")
        r = sentinel_probe(src, registry.lookup, seed=args.run_seed)
        cov = (coverage_check(src, _source_ips(src))
               if r["pass"] is None else None)
        if args.json:
            out = dict(r)
            out["coverage_check"] = cov
            print(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            ok = "—" if r["ok"] is None else f"{r['ok']}/{r['n']}"
            print(f"sentinel: {r['source']} channel={r['channel']} "
                  f"pass={r['pass']} status={r['status']} "
                  f"({ok}, seed={r['seed']})")
            if r.get("reason"):
                prefix = "N/A: " if r["pass"] is None else ""
                print(f"  {prefix}{r['reason']}")
            for pr in r["probes"]:
                if pr["expected"] != pr["actual"]:
                    print(f"  FAIL {pr['ip']}: expected {pr['expected']}, "
                          f"actual {pr['actual']}")
            if cov is not None:
                c = "—" if cov["covered"] is None else f"{cov['covered']:.2%}"
                print(f"  coverage_check(键集口径, 信息行不改 rc): "
                      f"covered={c} (n={cov['n']}, hits={cov['hits']})")
        sys.exit(0 if r["pass"] is not False else 1)
    if args.all:
        if args.json:
            results = []
            for s in registry.sources:
                try:
                    _, js, _ = run_for_source(s.name, registry=registry)
                    results.append(json.loads(Path(js).read_text()))
                except Exception as e:
                    results.append({"source": s.name, "error": {
                        "code": "internal", "message": str(e), "hint": _JSON_HINT}})
            print(json.dumps(results, ensure_ascii=False))
            return
        for s in registry.sources:
            _, _, v = run_for_source(s.name, registry=registry)
            print(f"{s.name:<20} {v.state}")
        return
    if not args.source:
        if args.json:
            _json_error("bad_request", "source required (or pass --all / --rebuild)",
                        "用法:python -m ipdb._eval <source> [--all|--rebuild] --json")
        p.error("source required (or pass --all / --rebuild)")
    if args.json:
        if next((s for s in registry.sources if s.name == args.source), None) is None:
            _json_error("source_not_found", f"no source named {args.source!r}",
                        "GET /api/sources 或查 backend/ipdb/_sources/ 确认源名")
        try:
            md, js, v = run_for_source(args.source, registry=registry)
        except Exception as e:
            _json_error("internal", str(e), _JSON_HINT)
        # 复用 write_report 的 render_json 序列化(顶层已含 source/generated_at)
        print(json.dumps(json.loads(Path(js).read_text()), ensure_ascii=False))
        return
    md, _, v = run_for_source(args.source, registry=registry)
    print(f"{args.source}: {v.state}\n  report: {md}")


if __name__ == "__main__":
    main()
