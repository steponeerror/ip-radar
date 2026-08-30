"""读 data/eval 报告聚合(spec 2026-08-28 §5.2,agent-ready PR②)。

进程间契约 = 文件:EvalManager 子进程经 CLI --json 落
{source}-{YYYYMMDD-HHMMSS}.json,本模块只读聚合。不加缓存
(29 源 × 小 json,每请求扫目录可接受——spec 明示)。

排序键 = (generated_at, 文件名):generated_at 是日粒度串(report.py
实测),同日多报告靠文件名秒级时间戳分先后(T5 防覆盖修复的产物)。
"""
import json
import os
from pathlib import Path


def _dir() -> Path:
    return Path(os.environ.get("IP_RADAR_EVAL_DIR")
                or Path(__file__).resolve().parents[1] / "data" / "eval")


def _runs() -> list[dict]:
    """目录内全部报告,按 (generated_at, 文件名) 升序;每个附带 _f(文件名
    stem)做 tie-break,输出前剥离。半写/损坏 json 跳过——一个坏文件不该
    炸掉整个端点。"""
    d = _dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if not isinstance(r, dict):
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
    source-eval model 任务)。顶层 *.json 仍是逐源 verdict —— 两者不混。
    排序键与 _runs 同式:(generated_at, 文件名)。"""
    d = _dir() / "model"
    if not d.exists():
        return None
    best, best_key = None, ("", "")
    for f in sorted(d.glob("model-*.json")):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if isinstance(r, dict):
            key = (str(r.get("generated_at") or ""), f.stem)
            if key > best_key:
                best, best_key = r, key
    return best
