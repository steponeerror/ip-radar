"""P1 审阅 API 四键(票 #155,TDD;spec #152 §3)。

钉住四键契约(独立真源 = spec #152 §3 字面与判例固定形文案,不从被测模块
导入常量,防套套逻辑;判例固定形沿 test_ops_ruling 同款字面):

- POST /api/ops/items/{id}/review {verdict, args?, reason?, wake_at?}:
  * agree:action ∈ 可逆闭集 {retry_download, disable_source, pause_source}
    → 直接执行(retry=任务管理器入队一次下载;disable/pause=源启停既有
    机制,无第二原语则并档)+ 判例 agreed + status done;集外 action →
    判例 only + 待集成清单既有闭集动词语义(「仅立项」恒标 proposal_only,
    队列零写);
  * modify:就地改条目 args,原值逐字进判例修正案(amended 语义),改后
    按 agree 同规则执行/立项;
  * ignore:必填 reason(缺 → 422 信封 validation_error);reason 即判例
    输入(overruled 的判例化);status dismissed;
  * snooze:wake_at(ISO;过去时/非法/naive → 422);status snoozed;
    到期回 active = list_items 读取面惰性判定(无定时器),到期后再审照走;
- 判例落盘 = write_ruling 四律复用(item_id 关联 = T1 预留位;幂等键防
  重复同裁);终态条目拒审(复开 = 新条目链指);
- 错误面:未知条目 404 / 坏 verdict·缺 reason·坏 wake_at·分键参数互斥
  422 / 执行失败 500 显式不吞(判例与状态零写)。
"""

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

# ── 独立真源字面(spec #152 §3 / 判例固定形同 test_ops_ruling)──
REVIEW_VERDICTS = ("agree", "modify", "ignore", "snooze")
REVERSIBLE_ACTIONS = ("retry_download", "disable_source", "pause_source")
OUT_OF_SET_ACTION = "refresh_source"          # T2 超龄探测器真实集外动作
PREFIX_AGREED = "人裁同意:建议照准。"
PREFIX_OVERRULED = "人裁否决:建议不成立。"
PREFIX_AMENDED_HEAD = "人裁修正,修正案逐字:\n"
PRECEDENT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-ruling-[0-9a-f]{10}\.md$")
WAKE_FUTURE = "2030-06-01T08:00:00+08:00"


@pytest.fixture
def review():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误;P1 同型)。"""
    import ipdb._ops_review as ops_review
    return ops_review


@pytest.fixture
def items():
    import ipdb._ops_items as ops_items
    return ops_items


@pytest.fixture
def store():
    import ipdb._ops_store as ops_store
    return ops_store


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp:IP_RADAR_DATA_DIR 指隔离目录,不碰真 data/。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _mk(**over):
    """create_item 参数默认包;dedup 三元组默认 source=spamhaus_drop。"""
    kw = dict(
        source="spamhaus_drop", probe_class="download",
        error_signature="http_403_anonymous",
        action="retry_download", args={"source": "spamhaus_drop"},
        evidence={"consecutive_failures": 3, "error_code": "HTTP 403"},
        impact="spamhaus_drop 数据停更,威胁覆盖面收缩",
        rollback="重新触发下载即可恢复;无不可逆变更",
        severity="high", cause_group="download_failure",
        summary="# 待审:源 spamhaus_drop 下载失败\n\n详见 evidence。\n",
        today=date(2026, 10, 23),
    )
    kw.update(over)
    return kw


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: 缺 frontmatter 起始围栏"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.name}: frontmatter 未闭合"
    return yaml.safe_load(text[4:end])


def _ruling_files(ops_env):
    pdir = ops_env / "ops" / "precedents"
    return sorted(p for p in pdir.glob("*.md") if p.name != "_schema.md")


def _queue_rows(ops_env):
    qpath = ops_env / "ops" / "queue.md"
    if not qpath.exists():
        return []
    return [ln for ln in qpath.read_text(encoding="utf-8").splitlines()
            if ln.startswith("| 20")]


def _suggestion(fm: dict) -> str:
    """条目摘要行(判例 suggestion 契约面;逐字钉住防漂移)。"""
    return f"{fm['action']} — {fm['impact']}(待审条目 {fm['id']})"


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, action, args):
        self.calls.append((action, dict(args)))
        return f"stubbed {action}"


@pytest.fixture
def admin_env(ops_env, auth_env):
    """路由测试面:ops 树 + admin 认证。"""
    return ops_env


@pytest.fixture
def stub_exec(review, monkeypatch):
    """执行面 stub:记录调用、不碰真 registry(T3 seam = _execute_action)。"""
    rec = _Recorder()
    monkeypatch.setattr(review, "_execute_action", rec)
    return rec


# ── A. agree:可逆闭集直接执行 + 留痕 ─────────────────────────────────


def test_agree_in_set_executes_rules_done(admin_env, client_as_admin, items,
                                          stub_exec):
    """agree × retry_download:真调用执行面(动作+args 原样)、判例 agreed
    (suggestion = 条目摘要行逐字、item_id 关联、lineage 指条目)、
    status done、不立项(proposal_only=False)、队列零写。"""
    r = items.create_item(**_mk())
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "agree"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"] == r["item"] and body["verdict"] == "agree"
    assert body["status"] == "done"
    assert body["executed"] is True and body["proposal_only"] is False
    assert stub_exec.calls == [("retry_download", {"source": "spamhaus_drop"})]
    assert PRECEDENT_NAME_RE.match(body["precedent"])
    assert body["created"] is True and body["queue_appended"] is False
    fm = _parse_frontmatter(
        admin_env / "ops" / "precedents" / body["precedent"])
    assert fm["recommendation"] == _suggestion(
        {"action": "retry_download",
         "impact": "spamhaus_drop 数据停更,威胁覆盖面收缩",
         "id": r["item"]})
    assert fm["human_ruling"] == PREFIX_AGREED
    assert fm["reward"]["ruling_agreement"] == "agreed"
    assert fm["lineage"] == [f"ops/items/{r['item']}.md"]
    assert fm["reward"]["hard_gates"] == {"item": f"ops/items/{r['item']}.md"}
    assert fm["item_id"] == r["item"]
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r['item']}.md")["status"] == "done")
    assert _queue_rows(admin_env) == []


def test_agree_real_dispatch_registry(admin_env, client_as_admin, items,
                                      review, monkeypatch):
    """真执行面接线(非 stub):retry=manager.enqueue_one 一次;disable 与
    pause 并档走 set_source_enabled(src, False)—— registry 启停面单一布尔
    无 pause 原语,并档是据实裁(见 _ops_review 模块头),此处钉住不漂移。"""
    from ipdb import _registry

    enqueued = []
    toggled = []

    class _FakeManager:
        def enqueue_one(self, name):
            enqueued.append(name)

    monkeypatch.setattr(_registry, "manager", _FakeManager())
    monkeypatch.setattr(_registry, "set_source_enabled",
                        lambda name, enabled: toggled.append((name, enabled)))
    made = {action: items.create_item(**_mk(
        source=f"{action}_src", error_signature=f"sig_{action}",
        action=action, args={"source": f"{action}_src"}))["item"]
        for action in REVERSIBLE_ACTIONS}
    for item_id in made.values():
        resp = client_as_admin.post(f"/api/ops/items/{item_id}/review",
                                    json={"verdict": "agree"})
        assert resp.status_code == 200
        assert resp.json()["executed"] is True
    assert enqueued == ["retry_download_src"]
    assert toggled == [("disable_source_src", False),
                       ("pause_source_src", False)]


def test_agree_out_of_set_proposal_only(admin_env, client_as_admin, items,
                                        stub_exec):
    """集外动作(T2 超龄探测器 refresh_source)agree:判例 only + 待集成
    清单既有闭集语义 —— 队列零行(不以 ENQUEUE/REJECT 起头)、不执行、
    「仅立项」恒标(proposal_only=True);条目照旧 done。"""
    r = items.create_item(**_mk(action=OUT_OF_SET_ACTION))
    before = _queue_rows(admin_env)
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "agree"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is False and body["proposal_only"] is True
    assert stub_exec.calls == []                      # 不执行
    assert _queue_rows(admin_env) == before           # 队列零写
    fm = _parse_frontmatter(
        admin_env / "ops" / "precedents" / body["precedent"])
    assert fm["reward"]["ruling_agreement"] == "agreed"   # 判例仍落(唯一产物)
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r['item']}.md")["status"] == "done")


# ── B. modify:就地改 args + 原值逐字留痕 ─────────────────────────────


def test_modify_amendment_verbatim_new_args_executed(
        admin_env, client_as_admin, items, stub_exec):
    """modify:args 就地改(文件 frontmatter);原值逐字进判例修正案
    (amended 语义,固定头 + 原文);执行面收到的 = 新 args;status done。"""
    r = items.create_item(**_mk(args={"source": "a_src"}))
    resp = client_as_admin.post(
        f"/api/ops/items/{r['item']}/review",
        json={"verdict": "modify", "args": {"source": "b_src"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is True and body["proposal_only"] is False
    assert stub_exec.calls == [("retry_download", {"source": "b_src"})]
    fm_item = _parse_frontmatter(admin_env / "ops" / "items" / f"{r['item']}.md")
    assert fm_item["args"] == {"source": "b_src"}       # 就地改
    fm = _parse_frontmatter(
        admin_env / "ops" / "precedents" / body["precedent"])
    assert fm["reward"]["ruling_agreement"] == "amended"
    assert fm["human_ruling"] == (
        PREFIX_AMENDED_HEAD
        + '条目 args 原值(逐字):{"source": "a_src"};改后:{"source": "b_src"}')
    assert fm["item_id"] == r["item"]
    assert fm_item["status"] == "done"


def test_modify_out_of_set_and_missing_args(admin_env, client_as_admin, items,
                                            stub_exec):
    """modify 集外:立项(amended 判例 + proposal_only);modify 缺 args →
    422(validation_error 信封);422 时零写(条目仍 active、无判例)。"""
    r = items.create_item(**_mk(action=OUT_OF_SET_ACTION))
    resp = client_as_admin.post(
        f"/api/ops/items/{r['item']}/review",
        json={"verdict": "modify", "args": {"source": "b_src"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is False and body["proposal_only"] is True
    assert stub_exec.calls == []
    fm = _parse_frontmatter(
        admin_env / "ops" / "precedents" / body["precedent"])
    assert fm["reward"]["ruling_agreement"] == "amended"

    r2 = items.create_item(**_mk(source="c_src", error_signature="sig_c"))
    resp2 = client_as_admin.post(f"/api/ops/items/{r2['item']}/review",
                                 json={"verdict": "modify"})
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "validation_error"
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r2['item']}.md")["status"] == "active")
    assert len(_ruling_files(admin_env)) == 1   # 只剩上一段的 amended 判例


# ── C. ignore:reason 必填 + overruled 判例化 ──────────────────────────


def test_ignore_reason_into_precedent(admin_env, client_as_admin, items,
                                      stub_exec):
    """ignore:reason 即判例输入 —— suggestion 携带理由(载位裁记见
    _ops_review 模块头),verdict=overruled 固定形留痕;status dismissed;
    不执行任何动作。"""
    r = items.create_item(**_mk())
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "ignore",
                                      "reason": "该源已转镜像,失败属预期"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "dismissed"
    assert body["executed"] is False and body["proposal_only"] is False
    assert stub_exec.calls == []
    fm = _parse_frontmatter(
        admin_env / "ops" / "precedents" / body["precedent"])
    assert fm["reward"]["ruling_agreement"] == "overruled"
    assert fm["human_ruling"] == PREFIX_OVERRULED
    assert fm["recommendation"].endswith(";忽略理由:该源已转镜像,失败属预期")
    assert fm["item_id"] == r["item"]


def test_ignore_without_reason_422(admin_env, client_as_admin, items):
    """缺 reason / 空白 reason → 422 信封 validation_error,零写。"""
    r = items.create_item(**_mk())
    for bad in ({}, {"verdict": "ignore"}, {"verdict": "ignore", "reason": "  "}):
        resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                    json=bad)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"
    assert _ruling_files(admin_env) == []
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r['item']}.md")["status"] == "active")


# ── D. snooze:wake_at 校验 + 惰性唤醒 ─────────────────────────────────


def test_snooze_valid_and_bad_wake_at(admin_env, client_as_admin, items,
                                      stub_exec):
    """snooze:合法未来时 → status snoozed + frontmatter wake_at(归一 UTC)+
    不落判例(调度非人裁)、不执行;过去时/非法/naive/缺省 → 422。"""
    r = items.create_item(**_mk())
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "snooze", "wake_at": WAKE_FUTURE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "snoozed" and body["wake_at"].endswith("+00:00")
    assert body["precedent"] is None and body["created"] is None
    assert stub_exec.calls == [] and _ruling_files(admin_env) == []
    fm = _parse_frontmatter(admin_env / "ops" / "items" / f"{r['item']}.md")
    assert fm["status"] == "snoozed" and fm["wake_at"] == body["wake_at"]

    for bad in (None, "2020-01-01T00:00:00+08:00", "not-a-time",
                "2030-06-01T08:00:00"):
        payload = {"verdict": "snooze"}
        if bad is not None:
            payload["wake_at"] = bad
        r2 = items.create_item(**_mk(source="snooze_src",
                                     error_signature=f"sig_{bad!r}"))
        resp2 = client_as_admin.post(f"/api/ops/items/{r2['item']}/review",
                                     json=payload)
        assert resp2.status_code == 422, bad
        assert resp2.json()["error"]["code"] == "validation_error"
        assert (_parse_frontmatter(
            admin_env / "ops" / "items" / f"{r2['item']}.md")["status"]
            == "active")


def test_snooze_lazy_wake_then_review(admin_env, client_as_admin, items,
                                      stub_exec):
    """到期回 active = list_items 读取面惰性判定(无定时器):到期 snoozed
    呈现为 active、文件字节零改(status 仍 snoozed);到期后再 agree 照走
    (snoozed → done 合法迁移)—— spec #152 验收「snooze 到期回列」。"""
    r = items.create_item(**_mk())
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "snooze", "wake_at": WAKE_FUTURE})
    assert resp.status_code == 200
    assert [it["status"] for it in items.list_items()] == ["snoozed"]
    # 模拟时间流逝:把 wake_at 行改到过去(测试侧改文件 = 等价于睡到到期)
    p = admin_env / "ops" / "items" / f"{r['item']}.md"
    p.write_text(re.sub(r"^wake_at: .*$",
                        "wake_at: 2020-01-01T00:00:00+00:00",
                        p.read_text(encoding="utf-8"), flags=re.M),
                 encoding="utf-8")
    got = items.list_items()
    assert [it["status"] for it in got] == ["active"]      # 呈现面唤醒
    assert _parse_frontmatter(p)["status"] == "snoozed"   # 文件不动
    resp2 = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                 json={"verdict": "agree"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "done"


def test_snooze_resnooze_extends_wake(admin_env, client_as_admin, items):
    """snoozed → snoozed = 顺延唤醒(只改 wake_at,状态不动):不是重复
    同裁,是新的唤醒时刻。"""
    r = items.create_item(**_mk())
    first = client_as_admin.post(
        f"/api/ops/items/{r['item']}/review",
        json={"verdict": "snooze", "wake_at": WAKE_FUTURE})
    assert first.status_code == 200
    second = client_as_admin.post(
        f"/api/ops/items/{r['item']}/review",
        json={"verdict": "snooze",
              "wake_at": "2031-01-01T00:00:00+08:00"})
    assert second.status_code == 200
    fm = _parse_frontmatter(admin_env / "ops" / "items" / f"{r['item']}.md")
    assert fm["wake_at"] == second.json()["wake_at"]


# ── E. 幂等/错误面/状态机 ─────────────────────────────────────────────


def test_replay_same_review_zero_side_effects(admin_env, client_as_admin,
                                              items, stub_exec):
    """重复同裁(双击/重放):终态条目拒审 → 422 零副作用 —— 执行面恰一次、
    判例恰一份、条目/队列字节不变(幂等由 write_ruling 语义键 + 各步幂等
    面承担,宁拒勿假)。"""
    r = items.create_item(**_mk())
    first = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                 json={"verdict": "agree"})
    assert first.status_code == 200
    item_bytes = (admin_env / "ops" / "items" / f"{r['item']}.md").read_bytes()
    ruling_name = first.json()["precedent"]
    second = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                  json={"verdict": "agree"})
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "validation_error"
    assert stub_exec.calls == [("retry_download", {"source": "spamhaus_drop"})]
    assert [p.name for p in _ruling_files(admin_env)] == [ruling_name]
    assert (admin_env / "ops" / "items" / f"{r['item']}.md").read_bytes() \
        == item_bytes
    assert _queue_rows(admin_env) == []


def test_write_ruling_item_source_idempotent_unit(store, items, ops_env):
    """判例层幂等(item 来源直测):同 item 同建议同裁重复 → created=False
    零副作用;item_id 与 package 互斥;条目不存在 → FileNotFoundError。"""
    r = items.create_item(**_mk())
    fm = items.load_item(r["item"])
    sug = f"{fm['action']} — {fm['impact']}(待审条目 {r['item']})"
    one = store.write_ruling(None, sug, "agreed", today=date(2026, 10, 23),
                             item_id=r["item"])
    assert one["created"] is True
    before = [(p.name, p.read_bytes()) for p in _ruling_files(ops_env)]
    two = store.write_ruling(None, sug, "agreed", today=date(2026, 10, 24),
                             item_id=r["item"])
    assert two["created"] is False and two["precedent"] == one["precedent"]
    assert [(p.name, p.read_bytes()) for p in _ruling_files(ops_env)] == before
    with pytest.raises(ValueError, match="互斥"):
        store.write_ruling("p.md", sug, "agreed", item_id=r["item"])
    with pytest.raises(FileNotFoundError):
        store.write_ruling(None, sug, "agreed",
                           item_id="2026-10-23-item-0000000000")


def test_unknown_item_404_and_bad_shape_422(admin_env, client_as_admin):
    """未知条目 → 404 not_found 信封;坏形状 id → 422(收紧后的条目名
    形状,T1 review Finding 4 裁;路径分隔/点前缀同被收紧拒,遍历面不测
    HTTP 层 —— 客户端会归一化路径段,存储层拒绝已在 test_ops_items 钉)。"""
    resp = client_as_admin.post(
        "/api/ops/items/2026-10-23-item-0000000000/review",
        json={"verdict": "agree"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    for bad in ("ruling_like_name", "foo_bar"):
        resp2 = client_as_admin.post(f"/api/ops/items/{bad}/review",
                                     json={"verdict": "agree"})
        assert resp2.status_code == 422
        assert resp2.json()["error"]["code"] == "validation_error"


def test_bad_verdict_and_foreign_params_422(admin_env, client_as_admin, items):
    """坏 verdict / 分键参数互斥(agree 带 reason、snooze 带 args……)→ 422。"""
    r = items.create_item(**_mk())
    cases = [
        {"verdict": "later"},
        {"verdict": "agree", "reason": "多嘴"},
        {"verdict": "agree", "wake_at": WAKE_FUTURE},
        {"verdict": "ignore", "wake_at": WAKE_FUTURE},
        {"verdict": "snooze", "args": {"source": "x"}, "wake_at": WAKE_FUTURE},
        {"verdict": "modify", "args": {"source": "x"}, "reason": "多嘴"},
    ]
    for body in cases:
        resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                    json=body)
        assert resp.status_code == 422, body
        assert resp.json()["error"]["code"] == "validation_error"
    assert _ruling_files(admin_env) == []
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r['item']}.md")["status"] == "active")


def test_terminal_item_rejected(admin_env, client_as_admin, items, stub_exec):
    """终态条目拒审(done/dismissed → 任何键):T1 状态机「复开 = 新条目
    链指」;ignore 后 agree → 422 且零副作用(非法迁移面的审阅端点化)。"""
    r = items.create_item(**_mk())
    first = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                 json={"verdict": "ignore", "reason": "不再关注"})
    assert first.status_code == 200 and first.json()["status"] == "dismissed"
    n_rulings = len(_ruling_files(admin_env))
    second = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                  json={"verdict": "agree"})
    assert second.status_code == 422
    third = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                 json={"verdict": "snooze",
                                       "wake_at": WAKE_FUTURE})
    assert third.status_code == 422
    assert stub_exec.calls == []
    assert len(_ruling_files(admin_env)) == n_rulings


def test_execution_failure_500_nothing_faked(admin_env, client_as_admin,
                                              items, review, monkeypatch):
    """执行失败不吞:500 internal 显式;判例与状态零写(不落「已同意」
    假账),条目留 active 供重试/换键(分步自愈裁记)。"""
    r = items.create_item(**_mk())

    def _boom(action, args):
        raise RuntimeError("unknown source: spamhaus_drop")

    monkeypatch.setattr(review, "_execute_action", _boom)
    resp = client_as_admin.post(f"/api/ops/items/{r['item']}/review",
                                json={"verdict": "agree"})
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal"
    assert _ruling_files(admin_env) == []
    assert (_parse_frontmatter(
        admin_env / "ops" / "items" / f"{r['item']}.md")["status"] == "active")


# ── P5 #167 adopt_rule:抑制规则库唯一写口(RETRO 候选的人裁采纳面)────────────


def _mk_adopt_rule(**over):
    """adopt_rule 候选条目参数包(RETRO retroDiff 产面同形:args=match/action/note)。"""
    kw = dict(
        source="retro", probe_class="adopt_rule",
        error_signature="bucket=unreachable&error_family=http_404&source=ciarm",
        action="adopt_rule",
        args={"match": {"bucket": "unreachable", "source": "ciarm",
                        "error_family": "http_404"},
              "action": "suppress",
              "note": "同签信号已被四键 ignore 1 次而本轮仍幸存——机械误判候选"},
        evidence={"round_id": "2026-10-24-0400-health",
                  "signal_id": "https://x/ciarm.txt",
                  "dismissed_items": ["2026-10-23-item-deadbeef01"]},
        impact="采纳后同形信号将被 VERIFY 抑制规则压掉(留痕进 suppressed 工件)",
        rollback="删除 rules/suppressions.json 中对应规则行即恢复",
        severity="low", cause_group="rule_proposal",
        summary="# 待审(adopt_rule):抑制规则候选\n\n候选草案见 args。\n",
        today=date(2026, 10, 24),
    )
    kw.update(over)
    return kw


def _rules_doc(ops_env):
    p = ops_env / "ops" / "rules" / "suppressions.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def test_adopt_rule_agree_writes_suppression_rule(admin_env, client_as_admin,
                                                  items):
    """agree → 规则进 suppressions.json(唯一写口);条目 done + 判例 agreed。

    规则形状:id=R<max+1>、adopted_via=item:<id>、review_at=采纳+90 天、
    version 自增;响应 executed=True proposal_only=False(非「仅立项」)。
    """
    res = items.create_item(**_mk_adopt_rule())
    iid = res["item"]
    r = client_as_admin.post(f"/api/ops/items/{iid}/review",
                             json={"verdict": "agree"})
    assert r.status_code == 200
    body = r.json()
    assert body["executed"] is True
    assert body["proposal_only"] is False
    assert body["status"] == "done"
    doc = _rules_doc(admin_env)
    assert doc and doc["version"] == 1 and len(doc["rules"]) == 1
    rule = doc["rules"][0]
    assert rule["id"] == "R1"
    assert rule["adopted_via"] == f"item:{iid}"
    assert rule["adopted"] == "2026-10-24"
    assert rule["review_at"] == "2027-01-22"       # 采纳+90 天(10-24 → 次年 01-22)
    assert rule["match"] == {"bucket": "unreachable", "source": "ciarm",
                             "error_family": "http_404"}
    assert rule["action"] == "suppress"
    assert "机械误判候选" in rule["note"]


def test_adopt_rule_second_adoption_increments_id_and_version(
        admin_env, client_as_admin, items):
    """既有规则库(R12/R7 形)上再采纳:id=max+1 续号、version 自增、旧规则逐字保留。"""
    import ipdb._ops_store as ops_store
    rules_path = admin_env / "ops" / "rules" / "suppressions.json"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps({
        "version": 3, "rules": [
            {"id": "R7", "adopted": "2026-10-23", "adopted_via": "item:old",
             "match": {"bucket": "unreachable", "error_family": "http_429"},
             "action": "annotate", "note": "既有", "review_at": "2027-01-21"},
        ]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    res = items.create_item(**_mk_adopt_rule())
    iid = res["item"]
    r = client_as_admin.post(f"/api/ops/items/{iid}/review",
                             json={"verdict": "agree"})
    assert r.status_code == 200
    doc = _rules_doc(admin_env)
    assert doc["version"] == 4
    assert [x["id"] for x in doc["rules"]] == ["R7", "R8"]
    assert doc["rules"][0]["note"] == "既有"


def test_adopt_rule_modify_adopts_amended_args(admin_env, client_as_admin, items):
    """modify → 新 args 先落条目,采纳以改后草案为准(match 放宽=人裁显式行为)。"""
    res = items.create_item(**_mk_adopt_rule())
    iid = res["item"]
    new_args = {"match": {"bucket": "unreachable", "source": "ciarm"},
                "action": "annotate", "note": "改判:降 severity 不抑制"}
    r = client_as_admin.post(f"/api/ops/items/{iid}/review",
                             json={"verdict": "modify", "args": new_args})
    assert r.status_code == 200
    assert r.json()["executed"] is True
    rule = _rules_doc(admin_env)["rules"][0]
    assert rule["match"] == {"bucket": "unreachable", "source": "ciarm"}
    assert rule["action"] == "annotate"
    fm = items.load_item(iid)
    assert fm["args"] == new_args


def test_adopt_rule_ignore_dismisses_without_rule_write(admin_env,
                                                        client_as_admin, items):
    """ignore → 候选否决(dismissed+判例 overruled),规则库零写(RETRO 不再立项同 key)。"""
    res = items.create_item(**_mk_adopt_rule())
    iid = res["item"]
    r = client_as_admin.post(f"/api/ops/items/{iid}/review",
                             json={"verdict": "ignore",
                                   "reason": "404 是真信号,不压"})
    assert r.status_code == 200
    assert _rules_doc(admin_env) is None
    assert items.load_item(iid)["status"] == "dismissed"


def test_adopt_rule_bad_args_500_nothing_faked(admin_env, client_as_admin, items):
    """候选 args 闭集外(谓词闭集外)→ 500 显式;判例/状态/规则库零写(不落假账)。"""
    res = items.create_item(**_mk_adopt_rule(
        args={"match": {"status_code": "404"}, "action": "suppress",
              "note": "坏草案"}))
    iid = res["item"]
    r = client_as_admin.post(f"/api/ops/items/{iid}/review",
                             json={"verdict": "agree"})
    assert r.status_code == 500
    assert "谓词闭集外" in r.json()["error"]["message"]
    assert _rules_doc(admin_env) is None
    assert items.load_item(iid)["status"] == "active"
    assert _ruling_files(admin_env) == []


def test_review_route_requires_admin(admin_env, auth_client, items):
    r = items.create_item(**_mk())
    resp = auth_client.post(f"/api/ops/items/{r['item']}/review",
                            json={"verdict": "agree"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_modify_half_failure_preserves_old_args_in_500(admin_env, client_as_admin,
                                                       items, review, monkeypatch):
    """T4 审 P2 回归钉(票 #156 收尾批):modify 半程失败(args 已落盘、执行
    炸)→ 500 消息必含预捕获原值——真原值不随重放灭失(哲学①)。"""
    r = items.create_item(**_mk(args={"source": "spamhaus_drop"}))

    def _boom(action, args):
        raise RuntimeError("unknown source: gone_src")

    monkeypatch.setattr(review, "_execute_action", _boom)
    resp = client_as_admin.post(
        f"/api/ops/items/{r['item']}/review",
        json={"verdict": "modify", "args": {"source": "gone_src"}})
    assert resp.status_code == 500
    msg = resp.json()["error"]["message"]
    assert "args 原值(预捕获)" in msg
    assert '"source": "spamhaus_drop"' in msg
