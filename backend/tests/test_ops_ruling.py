"""P3 人裁写回四律(票 #135,TDD 红先行)。

钉住产品化批 Task P3 契约(docs/superpowers/plans/2026-10-19-ops-agent-productization.md
+ 原 T5 史档规格「写回四律」+ 票 #135 验收标准;期望值取自独立真源
docs/ops/precedents/_schema.md 与 test_precedent_schema.py 同款字面,不从被测模块
导入常量,防套套逻辑):

- POST /api/ops/ruling {package, suggestion, verdict, amendment}:人裁三动作
  (agreed/overruled/amended,T1 冻结 ruling_agreement 闭集去 pending)落判例
  ——新建条目或 superseded_by 链,原条目永不删;
- 四律:schema 校验(写入内容过 T1 九字段/reward 三列校验)/ superseded_by
  (指向存在的文件)/ 幂等(重复同裁零副作用,跨日同裁同样零副作用)/
  人裁逐字留痕(修正案原文进 human_ruling,一字不改);
- production_delta 恒 null(30 天写回独立后续批,未结案不补);
- 裁⑦「已批准待集成」清单自动维护 = queue.md(P1 append_queue 基座,勿另立
  第二清单):agreed + 建议动词 ∈ T4 冻结队列闭集(ENQUEUE/REJECT)→ 入队
  (action+source 去重幂等);overruled/amended 与无队列动词的建议零队列写。
"""

import re
from datetime import date
from pathlib import Path

import pytest
import yaml

# ── 独立真源字面(_schema.md / test_precedent_schema.py 同款)──
REQUIRED_FIELDS = [
    "id", "date", "subject", "context", "recommendation",
    "human_ruling", "reward", "lineage", "superseded_by",
]
REWARD_KEYS = {"hard_gates", "ruling_agreement", "production_delta"}
RULING_AGREEMENT_VALUES = {"agreed", "overruled", "amended", "pending"}
# T4 queue.md 行尾 vetoable 列(逐字)
VETOABLE_CELL = "是(否决=删除本行)"

PKG_NAME = "2026-10-20-discover-1030.md"
SUGGESTION_ENQUEUE = (
    "ENQUEUE threatview_c2 — CPS 镜像 cobaltstrike_ips 排他 57.0%(171/300),"
    "池内 threatfox 仅盖 1/3,建议单独立项直连"
)
AMENDMENT_VERBATIM = (
    "修正案:排他门按头部/尾部分档——头部 40k 片 ≥0.35、尾部单源片 ≥0.25;\n"
    '含 "双引号" 与:冒号 与 #井号;\n第三行逐字,不许改一个字。'
)
# P3 落判语义(设计裁记,见 _ops_store.write_ruling 注释):verdict 固定形前缀
PREFIX_AGREED = "人裁同意:建议照准。"
PREFIX_OVERRULED = "人裁否决:建议不成立。"
PREFIX_AMENDED_HEAD = "人裁修正,修正案逐字:\n"

PRECEDENT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-ruling-[0-9a-f]{10}\.md$")


@pytest.fixture
def store():
    """被测模块(RED 相位 = 写回函数不存在,逐测试失败而非收集错误;P1/P2 同型)。"""
    import ipdb._ops_store as ops_store
    return ops_store


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp:IP_RADAR_DATA_DIR 指隔离目录,不碰真 data/。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _mk_pkg(ops_env, name=PKG_NAME, text="# 裁决包\n\n## 建议\n\n- 候选与证据……\n"):
    pdir = ops_env / "ops" / "packages"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / name).write_text(text, encoding="utf-8")
    return pdir / name


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: 缺 frontmatter 起始围栏"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.name}: frontmatter 未闭合"
    return yaml.safe_load(text[4:end])


def _ruling_files(ops_env):
    pdir = ops_env / "ops" / "precedents"
    return sorted(p for p in pdir.glob("*.md") if p.name != "_schema.md")


# ── A. 写回四律(store 层)──────────────────────────────────────────────


def test_ruling_creates_schema_valid_precedent(store, ops_env):
    """首裁新建条目:九字段齐全、reward 恰三列、ruling_agreement 落 verdict、
    production_delta 恒 null、recommendation=suggestion 逐字、lineage 指包。"""
    _mk_pkg(ops_env)
    res = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                             today=date(2026, 10, 20))
    assert res["created"] is True
    assert res["superseded"] is None
    assert PRECEDENT_NAME_RE.match(res["precedent"]), res["precedent"]
    files = _ruling_files(ops_env)
    assert len(files) == 1 and files[0].name == res["precedent"]
    fm = _parse_frontmatter(files[0])
    for field in REQUIRED_FIELDS:
        assert field in fm, f"缺必填字段 {field}"
    assert set(fm["reward"]) == REWARD_KEYS
    assert fm["reward"]["ruling_agreement"] == "agreed"
    assert fm["reward"]["production_delta"] is None
    assert isinstance(fm["reward"]["hard_gates"], dict) and fm["reward"]["hard_gates"]
    assert fm["id"] == files[0].stem
    assert str(fm["date"]) == "2026-10-20"
    assert fm["recommendation"] == SUGGESTION_ENQUEUE  # 逐字(yaml 往返无损)
    assert f"ops/packages/{PKG_NAME}" in [str(x) for x in fm["lineage"]]
    assert fm["superseded_by"] is None
    assert fm["human_ruling"] == PREFIX_AGREED


def test_ruling_idempotent_zero_side_effects(store, ops_env):
    """重复同裁零副作用:判例文件数与字节不变、台账/清单零追加;跨日同裁
    同样零副作用(幂等键 = 目标+裁决内容,不是文件名)。"""
    _mk_pkg(ops_env)
    store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed", today=date(2026, 10, 20))
    before = [(p.name, p.read_bytes()) for p in _ruling_files(ops_env)]
    qpath = ops_env / "ops" / "queue.md"
    queue_before = qpath.read_bytes() if qpath.exists() else b""
    # 次日重复同一裁(同包同建议同 verdict)
    res = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                             today=date(2026, 10, 21))
    assert res["created"] is False
    assert res["queue_appended"] is False
    after = [(p.name, p.read_bytes()) for p in _ruling_files(ops_env)]
    assert after == before, "重复同裁不得新增/改写任何判例文件"
    queue_after = qpath.read_bytes() if qpath.exists() else b""
    assert queue_after == queue_before, "重复同裁不得改写待集成清单"


def test_ruling_amendment_verbatim(store, ops_env):
    """修正案逐字留痕:human_ruling = 固定头 + 修正案原文一字不改
    (多行/引号/冒号/井号全过 yaml 往返)。"""
    _mk_pkg(ops_env)
    res = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "amended",
                             AMENDMENT_VERBATIM, today=date(2026, 10, 20))
    fm = _parse_frontmatter(ops_env / "ops" / "precedents" / res["precedent"])
    assert fm["human_ruling"] == PREFIX_AMENDED_HEAD + AMENDMENT_VERBATIM
    assert fm["reward"]["ruling_agreement"] == "amended"


def test_ruling_amend_supersedes_original_kept(store, ops_env):
    """改判:新条目 + 旧条目 superseded_by 指链;原条目永不删、其余内容原样。"""
    _mk_pkg(ops_env)
    first = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                               today=date(2026, 10, 20))
    second = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "amended",
                                AMENDMENT_VERBATIM, today=date(2026, 10, 21))
    assert second["created"] is True
    assert second["superseded"] == first["precedent"]
    files = {p.name: p for p in _ruling_files(ops_env)}
    assert set(files) == {first["precedent"], second["precedent"]}, "原条目不得删"
    # 旧条目:仅 superseded_by 变化,decision 内容原样
    old_fm = _parse_frontmatter(files[first["precedent"]])
    assert old_fm["superseded_by"] == second["precedent"]
    assert old_fm["recommendation"] == SUGGESTION_ENQUEUE
    assert old_fm["reward"]["ruling_agreement"] == "agreed"
    # 新条目未被取代
    new_fm = _parse_frontmatter(files[second["precedent"]])
    assert new_fm["superseded_by"] is None
    # superseded_by 指向存在的文件(验收标准)
    target = ops_env / "ops" / "precedents" / old_fm["superseded_by"]
    assert target.is_file()


def test_ruling_revert_after_amend_reuses_content_address(store, ops_env):
    """同日改回原裁:内容寻址文件名复用,链保持单向一致(旧新条目不孤儿)。"""
    _mk_pkg(ops_env)
    first = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                               today=date(2026, 10, 20))
    store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "amended",
                       AMENDMENT_VERBATIM, today=date(2026, 10, 20))
    third = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                               today=date(2026, 10, 20))
    assert third["created"] is True
    assert third["precedent"] == first["precedent"]  # 同内容同址
    files = {p.name: p for p in _ruling_files(ops_env)}
    assert len(files) == 2  # 复用不繁殖
    # 全库恰一条 current(未被取代)条目
    currents = [n for n, p in files.items()
                if _parse_frontmatter(p)["superseded_by"] is None]
    assert currents == [third["precedent"]]


@pytest.mark.parametrize("verdict,prefix", [
    ("agreed", PREFIX_AGREED),
    ("overruled", PREFIX_OVERRULED),
])
def test_ruling_fixed_verdicts_production_delta_null(store, ops_env, verdict, prefix):
    """同意/否决固定形人裁留痕;production_delta 恒 null(独立后续批)。"""
    _mk_pkg(ops_env)
    res = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, verdict,
                             today=date(2026, 10, 20))
    fm = _parse_frontmatter(ops_env / "ops" / "precedents" / res["precedent"])
    assert fm["human_ruling"] == prefix
    assert fm["reward"]["production_delta"] is None


def test_ruling_validation_rejects_before_any_write(store, ops_env):
    """闭集/矛盾输入在写文件前拒绝(零副作用):verdict 闭集外、amended 缺
    修正案、非 amended 带修正案、空建议、包不存在。"""
    _mk_pkg(ops_env)
    store.init_ops_tree()
    with pytest.raises(ValueError):
        store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "pending")
    with pytest.raises(ValueError):
        store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "amended", amendment="  ")
    with pytest.raises(ValueError):
        store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed", amendment="多嘴")
    with pytest.raises(ValueError):
        store.write_ruling(PKG_NAME, "  ", "agreed")
    with pytest.raises(FileNotFoundError):
        store.write_ruling("2026-10-20-discover-9999.md", SUGGESTION_ENQUEUE,
                           "agreed")
    assert _ruling_files(ops_env) == [], "非法输入不得落任何判例文件"


def test_ruling_package_name_traversal_rejected(store, ops_env):
    """包名只认纯文件名(路径/点前缀一律拒),不得逃出 packages/。"""
    _mk_pkg(ops_env)
    for bad in ("../ledger.md", "sub/dir/x.md", ".hidden.md", ".."):
        with pytest.raises(ValueError):
            store.write_ruling(bad, SUGGESTION_ENQUEUE, "agreed")
    assert _ruling_files(ops_env) == []


def test_ruling_schema_validator_law(store):
    """四律之「schema 校验」的单元面:写入内容须过 T1 九字段/reward 三列校验,
    坍缩/缺列/非空 production_delta/悬空 superseded_by 一律拒。"""
    good = {
        "id": "x", "date": "2026-10-20", "subject": "s", "context": "c",
        "recommendation": "r", "human_ruling": "h",
        "reward": {"hard_gates": {"package": "ops/packages/p.md"},
                   "ruling_agreement": "agreed", "production_delta": None},
        "lineage": ["ops/packages/p.md"], "superseded_by": None,
    }
    store.validate_precedent_entry(good)  # 合法形不炸
    import copy

    def _bad(mutate):
        e = copy.deepcopy(good)
        mutate(e)
        with pytest.raises(ValueError):
            store.validate_precedent_entry(e)

    _bad(lambda e: e.pop("context"))                       # 缺字段
    _bad(lambda e: e.update(reward="agreed"))              # reward 坍缩成标量
    _bad(lambda e: e["reward"].pop("hard_gates"))           # reward 缺列
    _bad(lambda e: e["reward"].update(production_delta="82.7%"))  # 未结案不补
    _bad(lambda e: e["reward"].update(ruling_agreement="yolo"))   # 闭集外
    _bad(lambda e: e["reward"].update(hard_gates={}))      # 硬门映射不得空
    _bad(lambda e: e.update(superseded_by="2099-01-01-无此文件.md"))  # 悬空链


# ── B. 裁⑦「已批准待集成」清单自动维护(queue.md,P1 基座)──────────────


def test_ruling_agreed_enqueue_appends_queue_row(store, ops_env):
    """同意 ENQUEUE 建议 → queue.md 追加行(T4 冻结形状;轮次取自包名,
    evidence=ruling 溯源三列);重复同裁零追加(action+source 去重)。"""
    _mk_pkg(ops_env)
    res = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                             today=date(2026, 10, 20))
    assert res["queue_appended"] is True
    q = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    expected = ('| 2026-10-20 | discover | ENQUEUE | threatview_c2 | — | '
                'ruling:verdict="agreed";ruling:package="2026-10-20-discover-1030.md" '
                f'| {VETOABLE_CELL} |')
    assert expected in q.splitlines()
    # 幂等:重复同裁(含队列面)零副作用
    res2 = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "agreed",
                              today=date(2026, 10, 21))
    assert res2["queue_appended"] is False
    rows = [ln for ln in (ops_env / "ops" / "queue.md").read_text(
        encoding="utf-8").splitlines() if ln.startswith("| 2026-")]
    assert len(rows) == 1


def test_ruling_agreed_reject_verb_queues_reject_row(store, ops_env):
    """同意 REJECT 建议 → REJECT 行入队(T4 闭集内第二动词;人裁 REJECT
    不带机械谓词,predicate=—)。"""
    _mk_pkg(ops_env)
    res = store.write_ruling(PKG_NAME, "REJECT threatview_c2 — sunset 冻结判死",
                             "agreed", today=date(2026, 10, 20))
    assert res["queue_appended"] is True
    q = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    assert "| 2026-10-20 | discover | REJECT | threatview_c2 | — |" in q


def test_ruling_overruled_and_amended_zero_queue_writes(store, ops_env):
    """否决/修正不入队(裁⑦:入清单的是「同意」);队列文件字节不变。"""
    _mk_pkg(ops_env)
    store.init_ops_tree()
    qpath = ops_env / "ops" / "queue.md"
    before = qpath.read_bytes()
    r1 = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "overruled",
                            today=date(2026, 10, 20))
    assert r1["queue_appended"] is False
    r2 = store.write_ruling(PKG_NAME, SUGGESTION_ENQUEUE, "amended",
                            amendment=AMENDMENT_VERBATIM, today=date(2026, 10, 20))
    assert r2["queue_appended"] is False
    assert qpath.read_bytes() == before


def test_ruling_non_queueable_suggestion_precedent_only(store, ops_env):
    """无队列动词的建议(FLAG/ACCEPT/人裁……)同意后只落判例:不发明
    T4 闭集外的队列动词,清单零写。"""
    _mk_pkg(ops_env)
    store.init_ops_tree()
    qpath = ops_env / "ops" / "queue.md"
    before = qpath.read_bytes()
    res = store.write_ruling(PKG_NAME, "FLAG threatview_c2 — 快照多一手陈化",
                             "agreed", today=date(2026, 10, 20))
    assert res["created"] is True
    assert res["queue_appended"] is False
    assert qpath.read_bytes() == before
    assert len(_ruling_files(ops_env)) == 1, "判例仍须落(裁⑦唯一产物优先)"


# ── C. 路由层(POST /api/ops/ruling;鉴权/校验/闭环)───────────────────


@pytest.fixture
def admin_env(ops_env, auth_env):
    """路由测试面:ops 树 + admin 认证。"""
    _mk_pkg(ops_env)
    return ops_env


def _post_ruling(client, **body):
    return client.post("/api/ops/ruling", json=body)


def test_ruling_route_requires_admin(admin_env, auth_client):
    r = _post_ruling(auth_client, package=PKG_NAME, suggestion="ENQUEUE a — x",
                     verdict="agreed")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_ruling_route_forbidden_for_non_superuser(admin_env, auth_client):
    import asyncio
    from fastapi_users.password import PasswordHelper
    from ipdb import _auth

    async def _mk_peon():
        async with _auth._session_maker()() as s:
            s.add(_auth.User(email="peon3@ipradar.local",
                             hashed_password=PasswordHelper().hash("peon-pass-123"),
                             is_superuser=False, is_active=True))
            await s.commit()

    asyncio.run(_mk_peon())
    assert auth_client.post("/api/auth/jwt/login", data={
        "username": "peon3@ipradar.local", "password": "peon-pass-123"}).status_code == 204
    r = _post_ruling(auth_client, package=PKG_NAME, suggestion="ENQUEUE a — x",
                     verdict="agreed")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("body", [
    {"package": PKG_NAME, "suggestion": "s", "verdict": "veto"},      # 闭集外
    {"package": PKG_NAME, "suggestion": "s", "verdict": "amended"},   # 缺修正案
    {"package": PKG_NAME, "suggestion": "s", "verdict": "agreed",
     "amendment": "多嘴"},                                            # 矛盾
    {"package": PKG_NAME, "suggestion": "  ", "verdict": "agreed"},   # 空建议
    {"package": PKG_NAME, "verdict": "agreed"},                       # 缺建议
])
def test_ruling_route_validates_body(admin_env, client_as_admin, body):
    r = _post_ruling(client_as_admin, **body)
    assert r.status_code == 422


def test_ruling_route_package_not_found_404(admin_env, client_as_admin):
    r = _post_ruling(client_as_admin, package="2026-10-20-discover-9999.md",
                     suggestion="ENQUEUE a — x", verdict="agreed")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_ruling_route_creates_then_idempotent(admin_env, client_as_admin):
    """HTTP 面闭环:首裁 200 created=True;重复同裁 created=False 且判例
    文件字节不变(幂等经 API 可见)。"""
    r1 = _post_ruling(client_as_admin, package=PKG_NAME,
                      suggestion=SUGGESTION_ENQUEUE, verdict="agreed")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["created"] is True
    assert PRECEDENT_NAME_RE.match(body1["precedent"])
    assert body1["queue_appended"] is True
    pfile = admin_env / "ops" / "precedents" / body1["precedent"]
    first_bytes = pfile.read_bytes()
    r2 = _post_ruling(client_as_admin, package=PKG_NAME,
                      suggestion=SUGGESTION_ENQUEUE, verdict="agreed")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["created"] is False
    assert body2["precedent"] == body1["precedent"]
    assert pfile.read_bytes() == first_bytes


def test_ruling_route_amended_verbatim(admin_env, client_as_admin):
    r = _post_ruling(client_as_admin, package=PKG_NAME,
                     suggestion=SUGGESTION_ENQUEUE, verdict="amended",
                     amendment=AMENDMENT_VERBATIM)
    assert r.status_code == 200
    pfile = admin_env / "ops" / "precedents" / r.json()["precedent"]
    fm = _parse_frontmatter(pfile)
    assert fm["human_ruling"] == PREFIX_AMENDED_HEAD + AMENDMENT_VERBATIM


def test_item_sourced_agreed_enqueue_appends_queue_row(store, ops_env):
    """T3 审 P3①(票 #156 顺手件):条目来源 ENQUEUE 建议 agree → queue 行
    轮次列 = review(审阅动作非轮次产物,不伪造轮次名),evidence = item 溯源;
    与包来源名空间隔离,幂等去重(action+source)同键。"""
    from ipdb import _ops_items as items
    made = items.create_item(
        source="threatview_c2", probe_class="download",
        error_signature="http_410_gone",
        action="ENQUEUE threatview_c2 — 退订候选",
        args={"source": "threatview_c2"},
        evidence={"consecutive_failures": 7, "error_code": "HTTP 410"},
        impact="上游 410 永久下线,覆盖面收缩",
        rollback="重新启用源即可恢复;无不可逆变更",
        severity="high", cause_group="download_failure",
        summary="# 待审:threatview_c2 410\n", today=date(2026, 10, 23))
    item_id = made["item"]
    res = store.write_ruling(
        None, f"ENQUEUE threatview_c2 — 上游 410 永久下线(待审条目 {item_id})",
        "agreed", today=date(2026, 10, 23), item_id=item_id)
    assert res["queue_appended"] is True
    q = (ops_env / "ops" / "queue.md").read_text(encoding="utf-8")
    expected = ('| 2026-10-23 | review | ENQUEUE | threatview_c2 | — | '
                'ruling:verdict="agreed";ruling:item="' + item_id + '" '
                f'| {VETOABLE_CELL} |')
    assert expected in q.splitlines()
    # 幂等:重复同裁零追加
    res2 = store.write_ruling(
        None, f"ENQUEUE threatview_c2 — 上游 410 永久下线(待审条目 {item_id})",
        "agreed", today=date(2026, 10, 24), item_id=item_id)
    assert res2["queue_appended"] is False
    rows = [ln for ln in (ops_env / "ops" / "queue.md").read_text(
        encoding="utf-8").splitlines() if ln.startswith("| 2026-")]
    assert len(rows) == 1
