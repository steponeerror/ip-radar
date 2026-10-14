# backend/ipdb/_eval/canary.py
"""季度 canary(S10, spec 2026-10-12-eval-loop-hardening-design.md §3.2/§8):
冻结已知判例表逐案 toggle 复跑对照期望。

失配 = 流程腐化告警行, **不自动修复** —— 声明 r 同款红线(测量建言,
人裁终局): canary 是腐化探测器不是执行器; 判例期望是标尺, 标尺旁的
任何「顺手修一下」都会让腐化悄悄通过下一季(哲学 6: 一切声明可证伪的
前提是标尺不动)。

判例期望冻结在代码里(KNOWN_CASES)而非运行时读外部期望文件 —— 读侧
期望即可被腐化悄悄改写, 冻结即锚。表不可变: tuple + frozen dataclass
+ MappingProxyType(写侧全 TypeError)。

两判例(spec §8 S10 原文「已知判例(greensnow 结构性零+一个 POSITIVE)
季度复跑,不匹配=流程腐化告警」, 控制器裁定 POSITIVE 判例 = threatfox,
只钉这两例不扩):
- greensnow 结构性零(loop-prototype 演示 B 判例, docs/research/
  2026-10-12-loop-prototype.md): 生产谱系锚 LINEAGE_ANCHORS
  firehol→greensnow 在场遮蔽 —— greensnow 关掉 → firehol 复活顶班 →
  舰队融合命中集 ON/OFF 不变(四层 delta 全 0.00pp, 逐 IP 实证
  eff 源 {greensnow}→{firehol} 精确翻转)。冻结读数断言
  fleet_hit_delta=0; 不复现 = 谱系锚/装配机制腐化。
- threatfox POSITIVE(首月轮月报判例, backend/data/eval/
  threatfox-20260927-161242.md: POSITIVE-UNVERIFIED, benefit_high=True,
  MC=0.1266 —— 自域效益在场): 自有指控在引擎载荷可见。计数本身随数据
  刷新漂移, 冻结稳定属性 PRESENT(>0) 而非具体数(冻结具体数 = 每季
  必假告警, 标尺自腐)。

探针 = 判例源原始文件采样 n 个已知成员(corpus.sample_source_ips 正则
提取, eval 包唯一真实键集通路, sentinel 同款 stable_seed 名派生缺省
—— 季度复跑可比); toggle 复跑复用 Phase 1 ablation.run_ablation
(OFF 基线 → ON, finally 复启候选同款纪律)。判例不可复跑(源消失/原始
文件空)→ fail-closed 记失配告警(无证据 ≠ 通过, 哲学 2), actual=None
不冒充读数。

eval_env=gate 强制(S37 fail-loud, run_gate 同款): 显式 monthly/dev →
raise —— 环境标签错位会令 rc_history/报告目录跨 env 混读; 未设 →
进程内钉 gate 退出还原。报告 canary-<ts>.md/.json(ts = report.py
落地件同形 %Y%m%d-%H%M%S), md 人面 + json 机件(gitignored 同族)。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .ablation import run_ablation
from .corpus import Corpus, sample_source_ips, stable_seed

# _accusing_sources/_accusing_types 私有名跨模块借道(口径同源勿复刻,
# sentinel 同款先例): 指控章单一口径 —— 组级 verdict ∈ _ACCUSING /
# 组 details 逐源 verdict ∈ _ACCUSING(缺键兑底 malicious)。
from .layered import _accusing_sources, _accusing_types

PRESENT = ">0"
"""期望谓词: 读数必须在场(>0)。计数随数据刷新漂移(loop-prototype:
greensnow 判例 16/20 而非 20/20), 冻结稳定属性不冻具体数。"""

# 探针数缺省 = 哨兵/loop-prototype 环1 判例形态 20(「哨兵 20/20」同款
# 量级; spec §3.2 Q18 哨兵同值先例)
PROBE_N = 20

_ENV_KEY = "IP_RADAR_EVAL_ENV"


@dataclass(frozen=True)
class KnownCase:
    """单条冻结判例: 期望读数映射随用例存储, 不可变(写侧 TypeError)。"""
    case: str
    source: str
    expected: Mapping[str, object]
    why: str   # 出处锚(判例从哪轮实测冻结), 报告不渲染、审阅面可查


KNOWN_CASES: tuple[KnownCase, ...] = (
    KnownCase(
        case="greensnow-structural-zero",
        source="greensnow",
        expected=MappingProxyType({
            "own_accusing_on": PRESENT,   # 在场: 自有指控可见(基线判例事实)
            "own_accusing_off": 0,        # 关闭 → 自有贡献消失(toggle 真关)
            "fleet_hit_delta": 0,         # 结构性零: firehol 顶班, 命中集不动
        }),
        why="loop-prototype 演示 B(2026-10-12): 谱系锚 firehol→greensnow "
            "交换, 四层 delta 全 0.00pp, 逐 IP {greensnow}→{firehol} 翻转",
    ),
    KnownCase(
        case="threatfox-positive",
        source="threatfox",
        expected=MappingProxyType({
            "own_accusing_on": PRESENT,   # POSITIVE: 自域效益在场(>0)
            "own_accusing_off": 0,
        }),
        why="首月轮月报 threatfox-20260927-161242: POSITIVE-UNVERIFIED, "
            "benefit_high=True, MC=0.1266",
    ),
)


def _own_accusing(snapshot: dict, source: str) -> int:
    """快照中该源自身指控的探针数(他源同指不顶替, 回声禁令)。"""
    return sum(1 for p in snapshot.values()
               if source in _accusing_sources(p))


def _fleet_hit_delta(off: dict, on: dict) -> int:
    """两臂舰队融合命中集对称差 = 结构性零判据的读数形态。

    命中 = 载荷含 ≥1 指控组(layered hit_members 同口径 _accusing_types);
    对称差 0 ⟺ 逐探针融合判定 ON/OFF 不变(可替换性), 非「无影响」的
    安慰性零(loop-prototype 演示 B 措辞)。"""
    def hits(snap: dict) -> set:
        return {ip for ip, p in snap.items() if _accusing_types(p)}
    return len(hits(off) ^ hits(on))


def _actual_readings(kc: KnownCase, off: dict, on: dict) -> dict:
    """期望表声明的读数逐项回算(不产未声明读数 —— 期望表即读数清单)。"""
    actual = {
        "own_accusing_on": _own_accusing(on, kc.source),
        "own_accusing_off": _own_accusing(off, kc.source),
    }
    if "fleet_hit_delta" in kc.expected:
        actual["fleet_hit_delta"] = _fleet_hit_delta(off, on)
    return actual


def _one_matches(expected, actual) -> bool:
    return actual > 0 if expected == PRESENT else actual == expected


def _matches(expected: Mapping, actual: Mapping) -> bool:
    return (set(expected) == set(actual)
            and all(_one_matches(e, actual[k]) for k, e in expected.items()))


def _alarm(kc: KnownCase, detail: str) -> str:
    """腐化告警行: 只告警, 不携带也不触发任何修复动作(S10/声明 r)。"""
    return (f"⚠ 流程腐化告警(S10): 判例 `{kc.case}`(source "
            f"`{kc.source}`){detail} —— 冻结期望失配, canary 只告警"
            "不自动修复(声明 r 红线: 测量建言, 人裁终局)。")


def _replay_case(kc: KnownCase, reg, probe_n: int) -> dict:
    """单判例 toggle 复跑 → {case, source, expected, actual, matched, ...}。

    不可复跑(源不在 reg / 原始文件空)→ fail-closed: matched=False +
    actual=None(无读数 ≠ 零读数, 哲学 2)+ 告警行。
    """
    base = {"case": kc.case, "source": kc.source,
            "expected": dict(kc.expected)}
    src_obj = next((s for s in reg.sources if s.name == kc.source), None)
    if src_obj is None:
        return {**base, "actual": None, "matched": False, "n_probes": 0,
                "seed": None,
                "alarm": _alarm(kc, "不可复跑 —— 源已不在 reg.sources"
                                    "(判例前提漂移, 需人裁重冻)")}
    seed = stable_seed(kc.source)   # 名派生缺省(sentinel 同款), 复跑可比
    probes = sample_source_ips(src_obj, probe_n, rng=random.Random(seed))
    if not probes:
        return {**base, "actual": None, "matched": False, "n_probes": 0,
                "seed": seed,
                "alarm": _alarm(kc, "不可复跑 —— 原始文件无可提取探针")}
    # OFF 基线 → ON(Phase 1 落地件; finally 复启候选)
    off_snap, on_snap = run_ablation(
        reg.lookup, reg.toggle, kc.source, Corpus(candidate_ips=probes))
    actual = _actual_readings(kc, off_snap, on_snap)
    matched = _matches(kc.expected, actual)
    diffs = ([f"{k}: 期望 {e} 实测 {actual[k]}"
              for k, e in kc.expected.items()
              if not _one_matches(e, actual[k])]
             + ([f"读数集漂移: 期望 {sorted(kc.expected)} "
                 f"实测 {sorted(actual)}"]
                if set(kc.expected) != set(actual) else []))
    return {**base, "actual": actual, "matched": matched,
            "n_probes": len(probes), "seed": seed,
            "alarm": None if matched else _alarm(kc, "; ".join(diffs))}


def _render_md(cases: list[dict], alarms: list[str], all_match: bool,
               probe_n: int) -> str:
    """canary 报告 md: 判例逐读数行 + 告警节(零失配也留哨兵行 ——
    未触发 ≠ 未评估, gate 报告同纪律)。"""
    lines = [
        "# 季度 canary(S10, eval_env=gate)",
        "",
        f"- 判例期望冻结于代码 `KNOWN_CASES`(表不可变; 运行时不读外部"
        "期望文件 —— 读侧期望可被腐化悄悄改写, 冻结即锚)",
        f"- 探针 = 判例源原始文件采样 n={probe_n}(stable_seed 名派生, "
        "季度复跑可比);toggle 复跑 = ablation.run_ablation"
        "(OFF 基线 → ON,finally 复启)",
        "",
        f"**all_match: {all_match}**",
        "",
        "| case | source | reading | expected | actual | matched |",
        "|---|---|---|---|---|---|",
    ]
    for c in cases:
        if c["actual"] is None:
            lines.append(f"| {c['case']} | {c['source']} | — | — | — "
                         "| ❌(不可复跑) |")
            continue
        for k in sorted(c["expected"]):
            e, a = c["expected"][k], c["actual"][k]
            ok = "✅" if _one_matches(e, a) else "❌"
            lines.append(f"| {c['case']} | {c['source']} | {k} | {e} | "
                         f"{a} | {ok} |")
    lines += ["", "## 流程腐化告警(S10)", ""]
    if alarms:
        lines += [f"- {a}" for a in alarms]
    else:
        lines.append("- 无失配:判例期望全部复现(哨兵行:未触发 ≠ 未评估)。")
    lines += [
        "",
        "_测量建言, 人裁终局(声明 r);canary 只告警, 无任何修复动作"
        "(S10)。判例增改须人裁重冻(表冻结, 非运行时可配)。_",
    ]
    return "\n".join(lines) + "\n"


def run_canary(reg, out_dir, *, probe_n: int = PROBE_N) -> dict:
    """季度 canary 主入口: 逐判例 toggle 复跑对照冻结期望, 落
    canary-<ts>.md/.json(eval_env=gate)。

    返回 {"all_match": bool, "cases": [...], "alarms": [...],
    "report": {...}, ...}(cases 每条含 case/expected/actual/matched)。
    失配只产告警行 —— 本函数无任何修复路径(无权重调整/无源启停变更/
    无期望改写; toggle 副作用仅 run_ablation 的 finally 复启)。
    eval_env=gate 强制(S37 fail-loud, run_gate 同款纪律)。
    """
    prev = os.environ.get(_ENV_KEY)
    if prev not in (None, "gate"):
        raise ValueError(
            f"{_ENV_KEY}={prev!r}: canary must run in env 'gate' "
            "(S37 fail-loud)")
    if prev is None:
        os.environ[_ENV_KEY] = "gate"
    try:
        return _run_canary(reg, out_dir, probe_n=probe_n)
    finally:
        if prev is None:
            del os.environ[_ENV_KEY]


def _run_canary(reg, out_dir, *, probe_n: int) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = [_replay_case(kc, reg, probe_n) for kc in KNOWN_CASES]
    alarms = [c["alarm"] for c in cases if c["alarm"]]
    all_match = all(c["matched"] for c in cases)
    payload = {
        "kind": "canary",
        "eval_env": "gate",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).date().isoformat(),
        "probe_n": probe_n,
        "all_match": all_match,
        "cases": cases,
        "alarms": alarms,
    }
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    md_path = out / f"canary-{ts}.md"
    js_path = out / f"canary-{ts}.json"
    md_path.write_text(_render_md(cases, alarms, all_match, probe_n),
                       encoding="utf-8")
    js_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                       encoding="utf-8")
    return {**payload, "report": {"md": str(md_path), "json": str(js_path)}}
