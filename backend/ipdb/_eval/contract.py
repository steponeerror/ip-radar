# backend/ipdb/_eval/contract.py
"""质量要求表 runner(ADR 0021 / #349):读 quality_contract.json 声明表,
逐腿执行现有质量读数,汇总产「质量报告」(JSON + markdown)。

定位 = 结缔组织,不是第二套工具:腿原样包现有读数面(工具本体不改,
行为零改动);本模块只做 声明表校验 → 逐腿执行 → 报告单汇总。

契约行 schema(quality-contract/1,字段终稿 #349):
  id / dimension / metric / oracle / expectation / verdict / track /
  trigger / provenance —— 判决语义 verdict ∈ gate|finding|score
  (ADR 0008 两轨的判决面),track ∈ baseline|improvement(保底|爬坡),
  trigger ∈ round|change|evolution(轮|改动|演化三触发面总表)。

oracle 三种取数方式:
  subprocess  {"argv": [...]}   argv 尾接 sys.executable 整段执行
              (如 ["-m", "ipdb._eval", "--anchors", "--json"] 即原样调
              旧子命令);cwd 钉 backend(cd backend 惯例,免
              ModuleNotFoundError)。argv 项可含整项占位符 $NAME,由
              params 绑定(CLI --contract-param;内置缺省 DATA_DIR/
              MANIFEST);未绑定 → 该腿无读数,不虚构。
  func        {"ref": "pkg.mod.fn"}  零参可调用,返回 JSON-able 读数;
              verdict=gate 的 func 腿读数须为含布尔 "pass" 键的 dict。
  none        {"reason": "..."}  无 oracle → 报告单显形「无读数(理由)」,
              绝不静默省略(覆盖账本 = 表本身;缺读数不虚构,#261 验收线)。

判决语义:gate 腿 = subprocess rc==0 / func 读数 pass=True 持门;finding
与 score 腿只记录不判门。runner 自身不持门:rc 0 = 报告产出(腿红态在
报告内),契约表不合法才 fail loud(rc=2)。坏腿(异常/坏输出)跳过但
记入报告单 failures 面,证据不灭失,不炸整单。
"""
from __future__ import annotations

import datetime as _dt
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "quality-contract/1"
REPORT_SCHEMA = "quality-report/1"
CONTRACT_PATH = Path(__file__).resolve().parent / "quality_contract.json"

REQUIRED_ROW_FIELDS = ("id", "dimension", "metric", "oracle", "expectation",
                       "verdict", "track", "trigger", "provenance")
VERDICTS = frozenset({"gate", "finding", "score"})
TRACKS = frozenset({"baseline", "improvement"})
TRIGGERS = frozenset({"round", "change", "evolution"})
ORACLE_KINDS = frozenset({"subprocess", "func", "none"})
_TOP_KEYS = frozenset({"schema", "rows", "comment"})

# subprocess 腿 cwd:cd backend 惯例(monthly_eval.sh run_step 同款)——
# python -m ipdb.* 从仓根/backend/ipdb 跑会 ModuleNotFoundError:ipdb
# (contract.py → parents[2] = backend;踩坑实测:parents[1]=backend/ipdb)
_BACKEND_DIR = Path(__file__).resolve().parents[2]

_READING_MD_MAX = 160        # md 读数列截断(JSON 件存全量)


class ContractError(ValueError):
    """契约表不合法(schema/枚举/oracle 形状):fail loud,CLI rc=2。"""


# ── 表装载与校验 ──────────────────────────────────────────────────────

def validate_contract(doc) -> dict:
    """校验声明表(quality-contract/1);不合法 raise ContractError,消息
    具名行 id 与字段。未知字段拒收(拼写防呆),返回原 doc。"""
    if not isinstance(doc, dict):
        raise ContractError(f"契约表顶层须为对象,得到 {type(doc).__name__}")
    if doc.get("schema") != SCHEMA:
        raise ContractError(f"契约表 schema 须为 {SCHEMA!r},"
                            f"得到 {doc.get('schema')!r}")
    stray = set(doc) - _TOP_KEYS
    if stray:
        raise ContractError(f"契约表顶层未知字段: {sorted(stray)}")
    rows = doc.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ContractError("契约表 rows 须为非空数组")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        rid = row.get("id", f"<row#{i}>") if isinstance(row, dict) \
            else f"<row#{i}>"
        if not isinstance(row, dict):
            raise ContractError(f"{rid}: 行须为对象")
        missing = [f for f in REQUIRED_ROW_FIELDS if f not in row]
        if missing:
            raise ContractError(f"{rid}: 缺字段 {', '.join(missing)}")
        stray_row = set(row) - set(REQUIRED_ROW_FIELDS)
        if stray_row:
            raise ContractError(f"{rid}: 行未知字段 {sorted(stray_row)} "
                                f"(schema {SCHEMA} 防拼错)")
        if row["id"] in seen:
            raise ContractError(f"{row['id']}: id 重复")
        seen.add(row["id"])
        for field, allowed in (("verdict", VERDICTS), ("track", TRACKS),
                               ("trigger", TRIGGERS)):
            if row[field] not in allowed:
                raise ContractError(
                    f"{rid}: {field} 须 ∈ {sorted(allowed)},"
                    f"得到 {row[field]!r}")
        _validate_oracle(rid, row["oracle"])
    return doc


def _validate_oracle(rid: str, oracle) -> None:
    if not isinstance(oracle, dict):
        raise ContractError(f"{rid}: oracle 须为对象")
    kind = oracle.get("kind")
    if kind not in ORACLE_KINDS:
        raise ContractError(f"{rid}: oracle.kind 须 ∈ "
                            f"{sorted(ORACLE_KINDS)},得到 {kind!r}")
    if kind == "subprocess":
        argv = oracle.get("argv")
        if (not isinstance(argv, list) or not argv
                or not all(isinstance(a, str) for a in argv)):
            raise ContractError(f"{rid}: subprocess oracle.argv 须为非空"
                                "字符串数组(尾接 sys.executable 整段执行)")
    elif kind == "func":
        ref = oracle.get("ref")
        if not isinstance(ref, str) or "." not in ref:
            raise ContractError(f"{rid}: func oracle.ref 须为可导入点路径"
                                "(如 ipdb._eval.anchors.run_anchors)")
    else:                                     # none
        if not str(oracle.get("reason") or "").strip():
            raise ContractError(f"{rid}: none oracle 须带非空 reason"
                                "(无读数的理由进报告单,不留哑字段)")


def load_contract(path) -> dict:
    """读契约表 JSON 并校验;不可读/非 JSON/不合法 → ContractError。"""
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ContractError(f"契约表不可读/非 JSON: {p}: {e}") from e
    return validate_contract(doc)


# ── 逐腿执行 ─────────────────────────────────────────────────────────

def _default_params() -> dict[str, str]:
    """占位符内置缺省绑定(可被 CLI --contract-param 覆盖):DATA_DIR 取
    registry 数据目录单一真源(registry_data_dir 同款,__main__ 先例);
    MANIFEST 落本命令自己的报告目录,缺省名带 env 后缀——env=monthly 时
    report_dir 与 monthly_eval.sh S7 的 mirror-manifest.json 同目录,同名
    缺省会在未设 IP_RADAR_DATA_DIR 时用本地树读数覆写镜像 S7 基线
    (评审 P2-1),故按 env 隔离命名。"""
    from .__main__ import eval_env, registry_data_dir, report_dir
    return {"DATA_DIR": str(registry_data_dir()),
            "MANIFEST": str(report_dir() / f"mirror-manifest-{eval_env()}.json")}


def _resolve_argv(argv: list[str], params: dict) -> tuple[list[str], list[str]]:
    """整项占位符替换:$NAME 命中 params → 绑定值;未命中记入 missing
    (该腿无读数,不虚构)。只支持整项占位,不支持内嵌拼接。"""
    out, missing = [], []
    for a in argv:
        if a.startswith("$") and len(a) > 1:
            if a[1:] in params:
                out.append(str(params[a[1:]]))
            else:
                missing.append(a)
        else:
            out.append(a)
    return out, missing


def _resolve_func(ref: str):
    """点路径解析:importlib 模段 + getattr 属性链。失败原样上抛(由
    _run_leg 收口成 failure,证据不灭失)。"""
    mod_name, _, attr = ref.rpartition(".")
    if not mod_name:
        raise ImportError(f"ref 无模块段: {ref}")
    obj = importlib.import_module(mod_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def _parse_stdout(text: str):
    """腿 stdout 解析:空/非 JSON → (None, err);JSON dict 且仅有 error
    键 = §5.2 错误信封(如 --exclusive 对照闸失败),按 failure 留痕
    (红态观察,非无读数;评审 P2-3)。"""
    s = (text or "").strip()
    if not s:
        return None, "stdout 为空"
    try:
        parsed = json.loads(s)
    except ValueError as e:
        return None, f"stdout 非 JSON: {e}"
    if isinstance(parsed, dict) and set(parsed) == {"error"}:
        err = parsed["error"]
        return None, (f"腿报错误信封: {err.get('code')}: "
                      f"{err.get('message')}")
    return parsed, None


def _new_result(row: dict) -> dict:
    return {**row, "status": None, "reading": None, "gate_pass": None,
            "rc": None, "error": None, "reason": None, "elapsed_s": None}


def _run_leg(row: dict, params: dict) -> dict:
    """执行一行契约腿。出口三态:ok(读数在手)/ no-reading(无读数,
    理由留痕)/ failure(腿坏,error 留痕,不炸整单)。gate 腿在 ok 态
    附加 gate_pass 判定(rc==0 / 读数 pass 键)。"""
    res = _new_result(row)
    t0 = time.monotonic()
    oracle = row["oracle"]
    try:
        if oracle["kind"] == "none":
            res["status"] = "no-reading"
            res["reason"] = oracle["reason"]
            return res
        if oracle["kind"] == "subprocess":
            argv, missing = _resolve_argv(oracle["argv"], params)
            if missing:
                res["status"] = "no-reading"
                res["reason"] = f"oracle 参数未绑定: {', '.join(missing)}"
                return res
            proc = subprocess.run(
                [sys.executable, *argv], cwd=_BACKEND_DIR,
                env=os.environ.copy(), capture_output=True, text=True)
            res["rc"] = proc.returncode
            parsed, err = _parse_stdout(proc.stdout)
            if err is not None:
                res["status"] = "failure"
                res["error"] = (f"{err} (rc={proc.returncode}; stderr: "
                                f"{proc.stderr.strip()[-400:]!r})")
                return res
            res["status"] = "ok"
            res["reading"] = parsed
            if row["verdict"] == "gate":
                res["gate_pass"] = proc.returncode == 0
            return res
        # func
        fn = _resolve_func(oracle["ref"])
        reading = fn()
        json.dumps(reading, default=str)          # 读数须 JSON-able
        res["status"] = "ok"
        res["reading"] = reading
        if row["verdict"] == "gate":
            if not (isinstance(reading, dict)
                    and isinstance(reading.get("pass"), bool)):
                res["status"] = "failure"
                res["error"] = ("func gate 腿读数须为含布尔 pass 键的 dict,"
                                f"得到 {type(reading).__name__}")
                return res
            res["gate_pass"] = reading["pass"]
        return res
    except Exception as e:                        # 坏腿收口:留痕不炸整单
        res["status"] = "failure"
        res["error"] = f"{type(e).__name__}: {e}"
        return res
    finally:
        res["elapsed_s"] = round(time.monotonic() - t0, 3)


# ── 报告单汇总 ───────────────────────────────────────────────────────

def _summarize(rows: list[dict]) -> dict:
    gate_ran = [r for r in rows
                if r["verdict"] == "gate" and r["status"] in ("ok", "failure")]
    return {
        "n_rows": len(rows),
        "n_ok": sum(1 for r in rows if r["status"] == "ok"),
        "n_no_reading": sum(1 for r in rows if r["status"] == "no-reading"),
        "n_failures": sum(1 for r in rows if r["status"] == "failure"),
        # 评审 P2-2:分母收「真跑过」的 gate 腿(ok+failure),崩掉的
        # gate 腿计入分母并单列 n_gate_failed,防「gate 0/0 过」假绿;
        # no-reading 的 gate 腿(oracle=none)从未运行,只入 n_no_reading。
        "n_gate_total": len(gate_ran),
        "n_gate_pass": sum(1 for r in gate_ran
                           if r["status"] == "ok" and r["gate_pass"]),
        "n_gate_failed": sum(1 for r in gate_ran if r["status"] == "failure"),
    }


def _cell(v, limit: int | None = None) -> str:
    s = str(v).replace("|", "\\|").replace("\n", " ").strip()
    if limit is not None and len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _fmt_reading(reading) -> str:
    s = json.dumps(reading, ensure_ascii=False, separators=(",", ":"),
                   default=str)
    return s[: _READING_MD_MAX - 1] + "…" if len(s) > _READING_MD_MAX else s


def render_markdown(report: dict) -> str:
    """质量报告 md 面:逐维度一行(维度/指标/读数/期望/判决/轨道/触发
    /出处);无读数显式一行「无读数(理由)」,不静默省略。"""
    s = report["summary"]
    lines = [
        "# 质量报告(quality report)",
        "",
        f"- 生成: {report['generated_at']} / env: {report['eval_env']}",
        f"- 契约表: {report['contract']['path']}"
        f"(schema {report['contract'].get('schema', SCHEMA)},"
        f" {report['contract']['n_rows']} 行)",
        f"- 汇总: 读数 {s['n_ok']} / 无读数 {s['n_no_reading']}"
        f" / 失败 {s['n_failures']};gate 腿 {s['n_gate_pass']}/"
        f"{s['n_gate_total']} 过,崩 {s['n_gate_failed']}"
        f"(runner 是编排面不持门,腿红态在本单)",
        "",
        "| 维度 | 指标 | 读数 | 期望 | 判决 | 轨道 | 触发 | 出处 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        if r["status"] == "no-reading":
            reading = f"无读数({_cell(r.get('reason') or '', 120)})"
        elif r["status"] == "failure":
            reading = "失败(见下方 failures 面)"
        else:
            reading = _cell(_fmt_reading(r.get("reading")))
        verdict = r["verdict"]
        if r["verdict"] == "gate" and r["status"] == "ok":
            verdict += " ✓" if r.get("gate_pass") else " ✗"
        lines.append("| " + " | ".join((
            _cell(r["dimension"]), _cell(r["metric"], 80), reading,
            _cell(r["expectation"], 100), verdict, _cell(r["track"]),
            _cell(r["trigger"]), _cell(r["provenance"], 100))) + " |")
    lines += ["", "## failures(证据不灭失)", ""]
    if report["failures"]:
        for f in report["failures"]:
            lines.append(f"- **{f['id']}**({_cell(f['dimension'])}): "
                         f"{_cell(f['error'], 300)}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def run_contract(contract_path=None, *, params: dict | None = None,
                 out_dir=None) -> dict:
    """读表 → 逐腿执行 → 汇总质量报告;out_dir 给定时落
    <out_dir>/model/quality-report-<ts>.json + .md(ts 形制同 anchors-*,
    monthly.py truth-v2-readout-* 落件先例)。契约表不合法 →
    ContractError 上抛(CLI rc=2);腿级红态全部留在报告内。"""
    path = Path(contract_path) if contract_path else CONTRACT_PATH
    doc = load_contract(path)
    from .__main__ import eval_env           # call-time 解析(测试免 reload)
    bound = {**_default_params(), **(params or {})}
    rows = [_run_leg(r, bound) for r in doc["rows"]]
    failures = [{"id": r["id"], "dimension": r["dimension"],
                 "error": r["error"], "rc": r["rc"]}
                for r in rows if r["status"] == "failure"]
    report = {
        "kind": "quality-report",
        "schema": REPORT_SCHEMA,
        "eval_env": eval_env(),
        "generated_at": _dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"),
        "contract": {"path": str(path), "schema": doc["schema"],
                     "n_rows": len(rows)},
        "params": {k: str(v) for k, v in bound.items()},   # 绑定留档可复算
        "rows": rows,
        "failures": failures,
        "summary": _summarize(rows),
    }
    if out_dir is not None:
        d = Path(out_dir) / "model"
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(
            _dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        jpath = d / f"quality-report-{ts}.json"
        mpath = d / f"quality-report-{ts}.md"
        jpath.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                    default=str), encoding="utf-8")
        mpath.write_text(render_markdown(report), encoding="utf-8")
        report["paths"] = {"json": str(jpath), "md": str(mpath)}
    return report
