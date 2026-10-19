# backend/ipdb/_eval/matrix_scan.py
"""语义契约矩阵现状扫描引擎 + diff 三桶(ADR 0003 Task 2)。

对四对象层取样 IP → lookup(to_dict 载荷)→ 按通道判定显形
(layer×label×channel 观测集合,存在性语义不计数)→ 与 matrix.json
裁决 diff:violation = observed × ruled illegal;pending = ruled
pending 格全集(观测与否都进,治理债可见);agreement = observed ×
legal;未观测格无断言(无证据即无话)。

通道判定口径(单一真源 ip_observations,勿另起副本):
- score:verdict ∈ _ACCUSING 的组且组级 confidence 非缺席
  (_types._ACCUSING 借道,anchors/exclusive 同源)——存档/弃权/资产
  证人永不进 P;
- UI:组 detected=true 的 verdict(任意,含 informational;生产路径
  _merge 恒 detected=True,threat 块 types 即由 detected 组构成)+
  asset(attributes 陈述)+ clean(threat 块空,净空缺省形态);
- stix:镜像 _stix_export.to_stix_bundle 判定点(黑盒最小面,不落盘,
  判定在内存载荷)——Indicator 只产 _ACCUSING 组(存档/弃权章不产),
  attributes 非空产 x_ipradar_attributes(asset);上游 _stix_export
  判定点变更须同步本镜像(守卫测试:test_eval_matrix_scan::
  test_stix_mirror_channel_matches_real_export);
- clean 在 score/stix 以「该通道无指控显形」观测(净空显形是缺省输出
  形态,matrix 全层 clean×三通道 legal)。

采样契约:infra 全量(资产规模小);truth/neutral/consensus 各稳定
seed ≤300(exclusive.sample_keys 同款 shuffle+cap)。层成员经
assemble_four_layers 交集审计(高优先层独占,回声不双计,哲学 3)。
观测证据 ≤3 IP + 涉及源名,供裁决包引用;lookup 失败即抛
(2026-10-10 假零判例,不 except-continue)。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .corpus import stable_seed
from .exclusive import DEFAULT_SEED, sample_keys
from .layered import assemble_four_layers
from .matrix import (ALL_CELL_IDS, LABELS, MATRIX_PATH, CellKey,
                     SemanticMatrix, load_matrix)
from .._types import _ACCUSING

SAMPLE_N = 300                            # truth/neutral/consensus 采样上限
FULL_SCAN_LAYERS = frozenset({"infra"})   # infra 全量(计划采样契约)
EVIDENCE_MAX = 3                          # 每格证据样本上限(裁决包引用)
# 引擎可产 verdict 四值(asset/clean 是缺省形态标签,非 verdict)
VERDICT_LABELS = frozenset(LABELS) - {"asset", "clean"}


@dataclass(frozen=True)
class Evidence:
    ip: str
    sources: tuple[str, ...]              # 涉及源名(排序定序)


@dataclass(frozen=True)
class CellObservation:
    cell: CellKey
    evidence: tuple[Evidence, ...]        # ≤EVIDENCE_MAX,查询序前 N


def _detail_sources(groups, *, accusing_only: bool) -> set[str]:
    """组 details → 源名集。score 证据只收指控证人(存档证人不进 P);
    缺 verdict 键兑底 malicious(exclusive.flagged_sources 同口径)。"""
    out: set[str] = set()
    for ca in groups:
        for d in ca.get("details") or ():
            if accusing_only and d.get("verdict", "malicious") not in _ACCUSING:
                continue
            if d.get("source"):
                out.add(d["source"])
    return out


def ip_observations(payload: dict) -> dict[tuple[str, str], set[str]]:
    """单 IP to_dict 载荷 → {(channel, label): 涉及源名集}。

    口径出处见模块注释;clean 无源名(缺省形态无证人)。
    """
    out: dict[tuple[str, str], set[str]] = {}

    def add(channel: str, label: str, sources=()) -> None:
        out.setdefault((channel, label), set()).update(sources)

    score_empty = True
    stix_accusing_empty = True
    for ca in (payload.get("classifications") or {}).values():
        verdict = ca.get("verdict")
        if verdict not in VERDICT_LABELS:
            continue
        all_srcs = _detail_sources([ca], accusing_only=False)
        if verdict in _ACCUSING:
            stix_accusing_empty = False
            add("stix", verdict, all_srcs)     # Indicator: x_verdict
            if ca.get("confidence") is not None:
                score_empty = False
                add("score", verdict,
                    _detail_sources([ca], accusing_only=True))
        if ca.get("detected"):
            add("UI", verdict, all_srcs)       # verdict 任意,含 informational
    attributes = payload.get("attributes") or {}
    if attributes:
        srcs = {s.get("source") for stmts in attributes.values()
                for s in stmts if s.get("source")}
        add("UI", "asset", srcs)
        add("stix", "asset", srcs)             # x_ipradar_attributes
    if not (payload.get("threat") or {}).get("types"):
        add("UI", "clean")                     # clean = threat 块空
    if score_empty:
        add("score", "clean")                  # 通道无指控显形的缺省形态
    if stix_accusing_empty:
        add("stix", "clean")
    return out


def channel_labels(payload: dict) -> dict[str, set[str]]:
    """载荷 → {channel: 观测标签集}(ip_observations 的视图,人读/测试用)。"""
    out: dict[str, set[str]] = {}
    for channel, label in ip_observations(payload):
        out.setdefault(channel, set()).add(label)
    return out


def layer_sample(kind: str, members: list[str], *, seed: int,
                 sample_n: int = SAMPLE_N) -> list[str]:
    """采样契约:infra 全量;其余层稳定 seed shuffle + 封顶
    (exclusive.sample_keys 同款;seed 经 stable_seed 按层名+CLI seed
    派生,同 seed 逐字节可复现)。"""
    if kind in FULL_SCAN_LAYERS:
        return list(members)
    return sample_keys(list(members),
                       stable_seed(f"matrix-scan|{kind}|{seed}"), sample_n)


def scan_layers(lookup_fn, layers: dict, *, seed: int = DEFAULT_SEED,
                sample_n: int = SAMPLE_N):
    """逐层取样逐 IP 查引擎 → (观测表, 层统计)。

    层成员来自 assemble_four_layers(交集审计,高优先层独占);NO-LAYER
    层不查不观测(缺层≠0 层,哨兵贯穿)。观测 = 存在性:每格记
    ≤EVIDENCE_MAX 条证据(查询序前 N),不计数。
    """
    observations: dict[CellKey, list[Evidence]] = {}
    layer_stats: dict[str, dict] = {}
    for kind, lr in layers.items():
        if lr.status != "OK":
            layer_stats[kind] = {"status": lr.status, "members": 0,
                                 "sampled": 0, "notes": list(lr.notes)}
            continue
        members = layer_sample(kind, lr.members, seed=seed, sample_n=sample_n)
        for ip in members:
            for (channel, label), srcs in ip_observations(
                    lookup_fn(ip)).items():
                evs = observations.setdefault((kind, label, channel), [])
                if len(evs) < EVIDENCE_MAX:
                    evs.append(Evidence(ip=ip, sources=tuple(sorted(srcs))))
        layer_stats[kind] = {"status": "OK", "members": len(lr.members),
                             "sampled": len(members)}
    frozen = {k: CellObservation(cell=k, evidence=tuple(v))
              for k, v in observations.items()}
    return frozen, layer_stats


def diff_matrix(matrix: SemanticMatrix,
                observations: dict[CellKey, CellObservation]) -> dict:
    """observed × ruled → 三桶(格序 = cell_id 字典序,报告确定)。

    pending 桶含全部 ruled pending 格(未观测的 evidence 为空,治理债
    可见);「observed 而格 legal 无出处」load_matrix 已拒
    (no-provenance-no-legal),此处无第二实现。
    """
    buckets = {"violation": [], "pending": [], "agreement": []}
    for cid in sorted(ALL_CELL_IDS):
        layer, label, channel = cid.split("|")
        key = (layer, label, channel)
        ruled = matrix.cells[key]
        obs = observations.get(key)
        entry = {"cell": cid, "state": ruled.state}
        if ruled.provenance:
            entry["provenance"] = ruled.provenance
        if ruled.note:
            entry["note"] = ruled.note
        entry["evidence"] = ([{"ip": e.ip, "sources": list(e.sources)}
                              for e in obs.evidence] if obs is not None else [])
        if ruled.state == "pending":
            buckets["pending"].append(entry)
        elif obs is not None and ruled.state == "illegal":
            buckets["violation"].append(entry)
        elif obs is not None and ruled.state == "legal":
            buckets["agreement"].append(entry)
    return buckets


def exit_code(counts: dict) -> int:
    """0/1/2 = 干净/有 pending/有 violation(violation 优先,
    --exclusive 先例退出码契约)。"""
    if counts["violation"]:
        return 2
    if counts["pending"]:
        return 1
    return 0


def _md_cell(cid: str) -> str:
    return cid.replace("|", "\\|")


def _md_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "—"
    return "; ".join(f"{e['ip']}({'/'.join(e['sources']) or '—'})"
                     for e in evidence)


def render_md(res: dict) -> str:
    """人读 md 报告:违例格逐格证据样本 + 建议栏「待裁」;pending /
    agreement / 层注记。stdout 输出不落盘(stix 黑盒最小面同纪律)。"""
    c = res["counts"]
    lines = [
        "# 语义契约矩阵现状扫描(--matrix-scan)",
        "",
        f"- seed={res['seed']} · eval_env={res['eval_env']} · "
        f"资产根={res['assets_dir']}",
        f"- 采样契约:infra 全量;truth/neutral/consensus 各稳定 seed "
        f"≤{res['sample_n']}(格语义 = 存在性,不计数)",
        f"- **violation {c['violation']} / pending {c['pending']} / "
        f"agreement {c['agreement']}** → exit {res['exit_code']}",
        "",
        "## 层",
        "",
        "| 层 | 状态 | 成员 | 实扫 |",
        "|---|---|---|---|",
    ]
    for kind, st in res["layers"].items():
        lines.append(f"| {kind} | {st['status']} | {st['members']} | "
                     f"{st['sampled']} |")
    lines += ["", "## 违例格(violation = 现状显形 × ruled illegal)", ""]
    if res["buckets"]["violation"]:
        lines += ["| 格 | 裁决 | 证据样本(≤3) | 建议 |", "|---|---|---|---|"]
        for e in res["buckets"]["violation"]:
            ruling = f"illegal({e['note']})" if e.get("note") else "illegal"
            lines.append(f"| {_md_cell(e['cell'])} | {ruling} | "
                         f"{_md_evidence(e['evidence'])} | 待裁 |")
    else:
        lines.append("(无)")
    lines += ["", "## 待裁格(pending = ruled pending,违例待裁)", ""]
    if res["buckets"]["pending"]:
        lines += ["| 格 | note | 证据样本(≤3) |", "|---|---|---|"]
        for e in res["buckets"]["pending"]:
            lines.append(f"| {_md_cell(e['cell'])} | {e.get('note') or '—'} | "
                         f"{_md_evidence(e['evidence'])} |")
    else:
        lines.append("(无)")
    lines += ["", "## 合法显形(agreement = observed ∧ legal)", ""]
    if res["buckets"]["agreement"]:
        lines += [f"- {_md_cell(e['cell'])}"
                  for e in res["buckets"]["agreement"]]
    else:
        lines.append("(无)")
    lines.append("")
    return "\n".join(lines)


def run_matrix_scan(lookup_fn, assets_root, *, matrix_path=None,
                    seed: int = DEFAULT_SEED, sample_n: int = SAMPLE_N,
                    eval_env: str | None = None) -> dict:
    """装配四层 → 取样扫描 → diff 三桶(CLI/套件共用入口,Task 3 接线点)。

    只读:lookup + 资产 + matrix.json,不落盘;eval_env 懒解析(仅进
    报告头,call-time fail-loud 同族;None → 读 __main__.eval_env,
    anchors_report 同款)。matrix_path=None → 模块 MATRIX_PATH
    (call-time 解析,测试可 monkeypatch)。
    """
    if matrix_path is None:
        matrix_path = MATRIX_PATH
    matrix = load_matrix(matrix_path)
    observations, layer_stats = scan_layers(
        lookup_fn, assemble_four_layers(Path(assets_root)),
        seed=seed, sample_n=sample_n)
    buckets = diff_matrix(matrix, observations)
    counts = {b: len(buckets[b]) for b in buckets}
    if eval_env is None:
        from .__main__ import eval_env as _env
        eval_env = _env()
    return {
        "seed": seed,
        "sample_n": sample_n,
        "eval_env": eval_env,
        "assets_dir": str(assets_root),
        "layers": layer_stats,
        "buckets": buckets,
        "counts": counts,
        "exit_code": exit_code(counts),
    }
