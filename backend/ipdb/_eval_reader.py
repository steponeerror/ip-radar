"""读 data/eval 报告聚合(spec 2026-08-28 §5.2,agent-ready PR②)。

进程间契约 = 文件:EvalManager 子进程经 CLI --json 落
{source}-{YYYYMMDD-HHMMSS}.json,本模块只读聚合。不加缓存
(登记源数 × 小 json,每请求扫目录可接受——spec 明示)。

排序键 = (generated_at, 文件名):generated_at 是日粒度串(report.py
实测),同日多报告靠文件名秒级时间戳分先后(T5 防覆盖修复的产物)。

#453 起读写同规:S37 环境子目录(monthly/gate/dev)已是写侧惯例,读侧
并看 根目录(S37 前的平铺旧件)+ monthly/ + dev/(存在才算);gate/ 是
回归门在镜像上的实验件,不进读面。逐源报告只认两道闸:①文件名形状
<源名>-<YYYYMMDD>-<HHMMSS>.json(源名字符集 [a-z0-9_]+);②解析出的
JSON 须带字符串 "source" 键。第二道闸是 2026-11-25 实现时发现的补丁
(#453 监督裁决口径):本机 backend/data/eval/monthly/ 里同形状的观测件
(northstar-<run_id>.json、temporal-<ts>.json)没有 source 键,纯形状
过滤会让 read_overview 按 r.get("source") or "unknown" 冒出 unknown 行。
模型报告 = model/model-*.json(不加 source 闸:模型报告是舰队级,无
source 字段)。
"""
import json
import re
from pathlib import Path

from . import _paths

# 逐源报告文件名形状(T5 文件名契约的机器可读版,#453):源名 [a-z0-9_]+
# + 秒级时间戳。northstar-*/temporal-* 撞形状但不带 source 键,由 _runs
# 的内容闸排除(出处见模块头)。
_REPORT_NAME_RE = re.compile(r"[a-z0-9_]+-\d{8}-\d{6}\.json")


def _dir() -> Path:
    return _paths.eval_dir()


def _dirs() -> list[Path]:
    """报告目录族 = 根 + monthly/ + dev/(存在才算;#453 读写同规)。
    gate/ 不进:回归门在镜像上的实验件,不该出现在源页。根缺席返回
    空(无话即无行,不虚构)。"""
    root = _dir()
    if not root.is_dir():
        return []
    out = [root]
    for sub in ("monthly", "dev"):
        d = root / sub
        if d.is_dir():
            out.append(d)
    return out


def _runs() -> list[dict]:
    """目录族内全部逐源报告,按 (generated_at, 文件名) 升序;每个附带 _f
    (文件名 stem)做 tie-break,输出前剥离。半写/损坏 json 跳过——一个坏
    文件不该炸掉整个端点。文件名形状 + "source" 为字符串双闸判定见模块头
    (#453:northstar-*/temporal-* 同形状观测件由此排除)。"""
    out = []
    for d in _dirs():
        for f in sorted(d.glob("*.json")):
            if not _REPORT_NAME_RE.fullmatch(f.name):
                continue
            try:
                r = json.loads(f.read_text())
            except ValueError:
                continue
            if not isinstance(r, dict) or not isinstance(r.get("source"), str):
                continue
            r["_f"] = f.stem
            out.append(r)
    out.sort(key=lambda r: (str(r.get("generated_at") or ""), r.get("_f") or ""))
    return out


def _metric(r: dict, k: str):
    """实测 schema:metrics 是 {k: {value, n}} 嵌套(report.py _metric_to_json)。
    键名大小写回退:__main__.py 的 metrics dict 里 MC/CG 是大写、oc 是小写
    (演练实测 OC 查成 null 的根因)。"""
    ms = r.get("metrics") or {}
    m = ms.get(k)
    if m is None and k.isupper():
        m = ms.get(k.lower())
    return m.get("value") if isinstance(m, dict) else m


def _verdict_state(r: dict) -> str:
    v = r.get("verdict")
    return v.get("state") if isinstance(v, dict) else str(v)


def _clean(r: dict) -> dict:
    r = dict(r)
    r.pop("_f", None)
    return r


def read_overview() -> list[dict]:
    """每源最新 verdict 摘要(verdict + 关键指标,输出自带判断)。"""
    latest: dict[str, dict] = {}
    for r in _runs():
        s = r.get("source") or "unknown"
        latest[s] = r               # _runs 已升序,后见者胜
    return [{"source": s, "verdict": _verdict_state(r),
             "at": r.get("generated_at"),
             "mc": _metric(r, "MC"), "cg": _metric(r, "CG"), "oc": _metric(r, "OC")}
            for s, r in sorted(latest.items())]


def read_source(source: str) -> dict:
    """单源历史 + 最新详情;源存在但无报告 → latest null + 空 history。"""
    runs = [r for r in _runs() if r.get("source") == source]
    return {"latest": _clean(runs[-1]) if runs else None,
            "history": [{"at": r.get("generated_at"),
                         "verdict": _verdict_state(r)} for r in runs]}


def read_model() -> dict | None:
    """最新舰队 corroboration-contrast 模型报告(model/ 子目录;
    source-eval model 任务)。#453 起跨目录族(根/monthly/dev 的 model/,
    同 _dirs;gate/model 不进)取最新 —— 月轮写 monthly/model/,S37 前
    旧件在根 model/。顶层 *.json 仍是逐源 verdict —— 两者不混。
    排序键与 _runs 同式:(generated_at, 文件名);键全等时后扫的目录胜
    (_runs 稳定排序后见者胜同款:dev > monthly > 根,与写入时间序一致)。"""
    best, best_key = None, ("", "")
    for d in _dirs():
        m = d / "model"
        if not m.is_dir():
            continue
        for f in sorted(m.glob("model-*.json")):
            try:
                r = json.loads(f.read_text())
            except ValueError:
                continue
            if isinstance(r, dict):
                key = (str(r.get("generated_at") or ""), f.stem)
                if key >= best_key:
                    best, best_key = r, key
    # pairs = offline assertion history, not API payload — spec 2026-09-02-brief §5.1
    if best is not None:
        best.pop("pairs", None)
    return best
