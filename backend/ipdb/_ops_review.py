"""ops 审阅 API 四键(P1 §3,票 #155,spec #152 §3)。

POST /api/ops/items/{id}/review 的编排本体:verdict ∈ {agree, modify,
ignore, snooze} 四键 → 可逆闭集动作直接执行(或集外「仅立项」)+ 判例
落盘(_ops_store.write_ruling 四律复用,条目来源 item_id 关联 = T1 预留
判例扩展位)+ 条目状态迁移(_ops_items.set_status / snooze_item,合法
迁移闭集)。本模块零 LLM、零自建定时器;存储原语在 _ops_items,判例/
队列语义在 _ops_store,不重复实现。

设计裁记(出处):
- 可逆闭集(spec #152 §3):{retry_download, disable_source, pause_source}。
  * retry_download = 任务管理器入队一次下载(_registry.manager.enqueue_one;
    ops 轮在飞时任务排队等待 —— 串行车道既有语义,不另设道);
  * disable/pause 并档:_registry 启停面只有单一布尔(_disabled 集合 +
    set_source_enabled 持久化),无 pause 原语;pause 的「临时」只存在于
    审阅意图与条目 rollback 文案(重新启用即恢复,走同一启停面),不发明
    第二启停原语(宁少算勿多算,按现成机制能力据实裁)。
- 集外动作 = 判例 only + 待集成清单既有闭集语义(裁⑦「仅立项」):条目
  动作描述不以 ENQUEUE/REJECT 起头 → write_ruling/_maybe_queue 既有判式
  自然零队列写;真出现闭集动词时按 T4 冻结语义入队(不发明第二套)。
  响应恒标 proposal_only=True(「仅立项」标记,T4 渲染面不重推导闭集)。
- 失败语义 = 分步提交 + 幂等自愈,不吞不回滚:各步天然幂等(执行面
  enqueue 同源在飞去重/启停幂等、update_args 同值零写、write_ruling 语义
  键、set_status 同态零写),任一步失败 → 500 显式上抛,已落步骤保持
  (跨步回滚本身要写更多状态,违背证据不灭失);重放经各步幂等面零重复
  副作用。判例与状态只在动作落地后写 —— 不落「已同意」的假账。
- snooze 不落判例:snooze 是对「何时再看」的调度,不是对建议本身的人裁
  (不置可否);判例面只收 agree/modify/ignore 三裁。到期回 active =
  list_items 读取面惰性判定(spec #152 §3「不自建定时器」,why 见彼处);
  到期后再裁,彼时落判。
- ignore 的 reason 载位:写回四律冻结 overruled 人裁留痕为固定形、修正案
  只随 amended → reason 无既有载位;载入 suggestion 组成面(四律约束的
  「suggestion 逐字往返」仍成立,幂等键含 suggestion → 同理由同裁零副
  作用),理由随判例永不灭失(哲学①)。
- 终态条目拒审(done/dismissed,422):T1 状态机「复开 = 新条目链指」;
  重复同裁(双击/重试重放)→ 422 零副作用,幂等由各步幂等面与
  write_ruling 语义键承担(宁拒勿假:不能验证「同裁」就绝不静默吸收)。
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import _ops_items, _ops_store

# 四键闭集(spec #152 §3;真源 = spec,路由/前端不另立第二拼写)
REVIEW_VERDICTS = ("agree", "modify", "ignore", "snooze")
# 可逆闭集(spec #152 §3):agree/modify 落此集 → 直接执行;集外 → 仅立项
REVERSIBLE_ACTIONS = ("retry_download", "disable_source", "pause_source")
# 四键 → 判例 verdict 映射(snooze 不落判例,故无映射)
_RULING_OF = {"agree": "agreed", "modify": "amended", "ignore": "overruled"}

# ── adopt_rule:抑制规则库唯一写口(P5 #167;C稿 §4.2)──────────────────────
# RETRO 步(pipeline/steps.mjs retroDiff)产 adopt_rule 候选条目仅立项;人裁
# agree/modify 才经此处写入 rules/suppressions.json——永不自动生效(责任线
# DESIGN.md §3;写口=本四键面是铁律)。规则可逆=删行即回;review_at 90 天
# 到点 RETRO 报复审(防规则腐烂)。
ADOPT_RULE_ACTION = "adopt_rule"
# 谓词/动作闭集与 Node 侧 steps.mjs RULE_PREDICATES/RULE_ACTIONS 同词表镜像
# (双向注释律:两侧改词表须先过 selftest-pipeline G_RETRO 闭集断言)
RULE_PREDICATES = ("bucket", "url_shape", "source", "error_family")
RULE_ACTIONS = ("suppress", "annotate")
_RULE_ID_RE = re.compile(r"^R(\d+)$")
_RULE_REVIEW_DAYS = 90


def _rules_path() -> Path:
    return _ops_store.ops_root() / "rules" / "suppressions.json"


def _adopt_rule(item_id: str, args: dict, today: date) -> str:
    """adopt_rule 条目 args → 追加进 rules/suppressions.json,返回规则 id。

    args = {match: {谓词: 值…}, action: suppress|annotate, note: str}(RETRO
    候选草案面);闭集校验失败 = 条目数据坏 → ExecutionError(500 显式,不伪装
    配置错)。id = 现库最大 R<n> + 1;version 自增;adopted_via = 条目 id
    (谱系可回算);review_at = adopted + 90 天(C稿 §4.2)。
    """
    if not isinstance(args, dict):
        raise ExecutionError(f"adopt_rule args 必须是映射: {args!r}")
    match = args.get("match")
    action = args.get("action")
    note = args.get("note")
    if not isinstance(match, dict) or not match:
        raise ExecutionError(f"adopt_rule args.match 必须是非空映射(谓词闭集 {'/'.join(RULE_PREDICATES)}): {match!r}")
    for k in match:
        if k not in RULE_PREDICATES:
            raise ExecutionError(f"adopt_rule 谓词闭集外: {k!r}(闭集 {'/'.join(RULE_PREDICATES)})")
    for k, v in match.items():
        if not isinstance(v, str) or not v.strip():
            raise ExecutionError(f"adopt_rule match.{k} 必须是非空字符串: {v!r}")
    if action not in RULE_ACTIONS:
        raise ExecutionError(f"adopt_rule action 闭集外: {action!r}(闭集 {'/'.join(RULE_ACTIONS)})")
    if not isinstance(note, str) or not note.strip():
        raise ExecutionError("adopt_rule args.note 必须是非空字符串(人读理由面)")
    path = _rules_path()
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ExecutionError(f"抑制规则库不可解析({path}): {e}") from e
        if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
            raise ExecutionError(f"抑制规则库形状非法({path}):缺 rules 数组")
        rules = list(doc["rules"])
        version = doc.get("version", 0)
        if not isinstance(version, int):
            raise ExecutionError(f"抑制规则库 version 非整数({path})")
    else:  # 零规则起步:空库建形(规则文件缺席=合法零规则态,非坏文件)
        rules, version = [], 0
    ids = [int(m.group(1)) for r in rules
           if isinstance(r, dict) and (m := _RULE_ID_RE.match(str(r.get("id", ""))))]
    rid = f"R{(max(ids) if ids else 0) + 1}"
    review_at = today + timedelta(days=_RULE_REVIEW_DAYS)
    rules.append({"id": rid, "adopted": today.isoformat(),
                  "adopted_via": f"item:{item_id}",
                  "match": match, "action": action, "note": note,
                  "review_at": review_at.isoformat()})
    _ops_store.atomic_write_text(
        path, json.dumps({"version": version + 1, "rules": rules},
                         ensure_ascii=False, indent=2) + "\n")
    return rid


class ReviewValidationError(ValueError):
    """请求面校验失败 → 422(信封 validation_error;分键参数/闭集/形状/
    非法迁移)。与执行失败(ExecutionError → 500)分面,不混装。"""


class ExecutionError(RuntimeError):
    """可逆动作执行失败 → 500 显式不吞(模块头「分步提交 + 幂等自愈」)。"""


def _suggestion_line(fm: dict) -> str:
    """判例 suggestion = 条目摘要行(spec #152 §3「suggestion 来源 = 条目」):
    动作 + 后果 + 条目 id 关联。证据/args 全量在条目里,不复制(宁少算勿
    多算,防双源漂移);不以 ENQUEUE/REJECT 起头 → 不会误撞待集成清单
    队列判式。"""
    return f"{fm['action']} — {fm['impact']}(待审条目 {fm['id']})"


def _parse_wake_at(raw) -> str:
    """wake_at 校验 + 归一:ISO 8601、必须带时区(naive 拒,不按本地猜)、
    须未来时(过去时 = 无意义的立即到期,422);归一为 UTC ISO 存储
    (与 wake_at 校验/惰性唤醒比较面同口径)。"""
    if not isinstance(raw, str) or not raw.strip():
        raise ReviewValidationError("snooze 必填 wake_at(ISO 8601,带时区,未来时)")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise ReviewValidationError(f"wake_at 非法(ISO 8601): {raw!r}") from None
    if dt.tzinfo is None:
        raise ReviewValidationError(f"wake_at 必须带时区(如 +08:00 或 Z): {raw!r}")
    if dt <= datetime.now(timezone.utc):
        raise ReviewValidationError(f"wake_at 已是过去时: {raw!r}")
    return dt.astimezone(timezone.utc).isoformat()


def _execute_action(action: str, args: dict) -> str:
    """可逆闭集动作直接执行面(T3 seam:测试替换点;真源裁记见模块头)。

    惰性 import _registry:本模块保持免拉 registry 链可独立导入(_registry
    无环,调用时解析);执行环境失败(unknown source 等)原样上抛,由
    review_item 包成 ExecutionError(500 显式)。
    """
    source = args.get("source")
    if not isinstance(source, str) or not source:
        raise ReviewValidationError(
            f"args.source 缺失/非字符串,无法执行 {action}: {args!r}")
    from . import _registry
    if action == "retry_download":
        _registry.manager.enqueue_one(source)
        return f"retry_download {source}(已入队一次下载)"
    # disable/pause 并档(模块头裁记):同一启停面,区别只在意图与回滚文案
    _registry.set_source_enabled(source, False)
    label = "pause_source(带 wake 语义的停用)" if action == "pause_source" \
        else "disable_source"
    return f"{label} {source}(已停用,重新启用即恢复)"


def _validate_request(verdict, *, args, reason, wake_at) -> None:
    """分键参数互斥/必填(闭集外 verdict 已在调用面拒):
    agree 零参数 / modify 只 args / ignore 只 reason / snooze 只 wake_at
    (OpsRulingIn「修正案只随 amended」同律:矛盾输入写前拒)。"""
    allowed = {"agree": (), "modify": ("args",),
               "ignore": ("reason",), "snooze": ("wake_at",)}[verdict]
    given = {"args": args, "reason": reason, "wake_at": wake_at}
    for key, val in given.items():
        if val is not None and key not in allowed:
            raise ReviewValidationError(f"{verdict} 不接受参数 {key}(分键参数互斥)")


def review_item(item_id: str, verdict: str, *, args=None, reason=None,
                wake_at=None, today=None) -> dict:
    """四键审阅编排(POST /api/ops/items/{id}/review 的本体;路由只做
    错误面映射)。步骤序 = 实质(执行/改 args)→ 判例 → 状态(模块头
    「分步提交 + 幂等自愈」)。返回字段 = OpsItemReviewOut 契约面。
    """
    if verdict not in REVIEW_VERDICTS:
        raise ReviewValidationError(
            f"verdict 必须在闭集内: {'/'.join(REVIEW_VERDICTS)},实际 {verdict!r}")
    _validate_request(verdict, args=args, reason=reason, wake_at=wake_at)
    # 名形状先行(422 面):与坏文件(损坏 → 原样 ValueError → 500 面)分诊
    try:
        _ops_items.validate_item_id(item_id)
    except ValueError as e:
        raise ReviewValidationError(str(e)) from None
    fm = _ops_items.load_item(item_id)   # FileNotFoundError → 404;损坏 → 500
    if fm["status"] in ("done", "dismissed"):
        raise ReviewValidationError(
            f"条目已终态({fm['status']}):终态复开 = 新条目链指,"
            "不可就地再审(T1 状态机)")

    if verdict == "snooze":
        wake = _parse_wake_at(wake_at)
        res = _ops_items.snooze_item(item_id, wake)
        return {"item": item_id, "verdict": "snooze", "status": res["to"],
                "executed": False, "proposal_only": False,
                "precedent": None, "created": None, "superseded": None,
                "queue_appended": None, "wake_at": res["wake_at"]}

    old_args = fm["args"]
    amendment = None
    if verdict == "modify":
        if not isinstance(args, dict):
            raise ReviewValidationError("modify 必填 args(映射,新动作参数)")
        # 原值逐字进判例修正案(write_ruling amended 语义):json 确定性
        # 序化(sort_keys)→ 同改同裁幂等;新值一并入案,改后可回算
        amendment = ("条目 args 原值(逐字):"
                     + json.dumps(old_args, sort_keys=True, ensure_ascii=False)
                     + ";改后:"
                     + json.dumps(args, sort_keys=True, ensure_ascii=False))
        _ops_items.update_args(item_id, args)   # 同值 = 幂等零写
        eff_args = args
    else:
        eff_args = old_args

    suggestion = _suggestion_line(fm)
    if verdict == "ignore":
        if not isinstance(reason, str) or not reason.strip():
            raise ReviewValidationError("ignore 必填 reason(非空;判例输入)")
        suggestion = f"{suggestion};忽略理由:{reason}"   # 载位裁记见模块头

    executed = False
    proposal_only = False
    if verdict in ("agree", "modify"):
        if fm["action"] == ADOPT_RULE_ACTION:
            # P5 #167:adopt_rule 候选采纳 = 抑制规则库唯一写口(C稿 §4.2;模块头
            # 裁记上方)。agree/modify(modify 先改 args 再采纳)均落规则;下一轮
            # VERIFY 即生效。不属于 spec #152 可逆闭集——独立分支,词表闭集见
            # RULE_PREDICATES/RULE_ACTIONS(与 RETRO 候选产面同词表)。
            _adopt_rule(item_id, eff_args, today or date.today())
            executed = True
        elif fm["action"] in REVERSIBLE_ACTIONS:
            try:
                _execute_action(fm["action"], eff_args)
            except ReviewValidationError:
                raise
            except Exception as e:   # 不吞:执行失败 = 500,判例/状态零写
                # T3 审 P2(票 #155→#156 顺手件):modify 半程失败时
                # update_args 已落盘,重放会从已变异 fm 重算「原值」——
                # 预捕获 old_args 进 500 证据面,真原值不灭失(哲学①)。
                orig = (f";args 原值(预捕获): "
                        f"{json.dumps(old_args, sort_keys=True, ensure_ascii=False)}"
                        if verdict == "modify" else "")
                raise ExecutionError(
                    f"动作执行失败({fm['action']} {eff_args!r}){orig}: {e}") from e
            executed = True
        else:
            proposal_only = True   # 集外动作:「仅立项」恒标(模块头裁记)

    ruling = _ops_store.write_ruling(
        None, suggestion, _RULING_OF[verdict], amendment,
        today=today, item_id=item_id)
    status_res = _ops_items.set_status(
        item_id, "dismissed" if verdict == "ignore" else "done")
    return {"item": item_id, "verdict": verdict, "status": status_res["to"],
            "executed": executed, "proposal_only": proposal_only,
            "precedent": ruling["precedent"], "created": ruling["created"],
            "superseded": ruling["superseded"],
            "queue_appended": ruling["queue_appended"], "wake_at": None}
